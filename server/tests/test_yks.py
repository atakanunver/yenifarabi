"""
server/yks.py — YKS soru arama + sıradaki-soru ilerlemesi + geçmiş-ders
tekrarını engelleme (2026-08-21), ağsız/dosya-tabanlı test.

`_daha_once_gosterildi_mi`/`_gosterimi_kaydet` gerçek DB'ye BAĞLANMAZ —
monkeypatch'lenir (aynı `test_ders_hafizasi.py`'nin dosya-izolasyon
deseninin DB karşılığı). Her test kendi izole METIN_DIR'ını ve taze
_OTURUMLAR/kayıt durumunu kullanır.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yks  # noqa: E402


@pytest.fixture
def izole_arsiv(monkeypatch, tmp_path):
    monkeypatch.setattr(yks, "METIN_DIR", tmp_path)
    monkeypatch.setattr(yks, "_OTURUMLAR", {})
    return tmp_path


@pytest.fixture
def sahte_kayit(monkeypatch):
    """_daha_once_gosterildi_mi / _gosterimi_kaydet'i gerçek DB'siz izler."""
    durum = {"gosterilmisler": set(), "kayitlar": []}

    def _oku(derslik):
        return set(durum["gosterilmisler"])

    def _kaydet(derslik, dosya_adi, sayfa, ders, konu):
        durum["kayitlar"].append((derslik, dosya_adi, sayfa, ders, konu))
        durum["gosterilmisler"].add((dosya_adi, sayfa))

    monkeypatch.setattr(yks, "_daha_once_gosterildi_mi", _oku)
    monkeypatch.setattr(yks, "_gosterimi_kaydet", _kaydet)
    return durum


def _metin_dosyasi_yaz(dizin: Path, ad: str, sayfalar: dict[int, str]) -> Path:
    dizin.mkdir(parents=True, exist_ok=True)
    parcalar = []
    for no, govde in sayfalar.items():
        parcalar.append(f"\n\n===SAYFA {no}===\n\n{govde}")
    yol = dizin / ad
    yol.write_text("".join(parcalar), encoding="utf-8")
    return yol


def test_daha_once_gosterilen_soru_yeni_aramada_adaylardan_cikarilir(izole_arsiv, sahte_kayit):
    _metin_dosyasi_yaz(izole_arsiv, "arsiv1.txt", {
        10: "İngilizce YDT present perfect tense sorusu kamera tasarım",
        20: "İngilizce YDT present perfect tense sorusu farklı kamera metni",
    })
    # sayfa 10 daha önce BU derslike gösterilmiş.
    sahte_kayit["gosterilmisler"].add(("arsiv1", 10))

    yanit = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="9-A", ders="İngilizce", konu="present perfect tense")
    )
    assert yanit.status == "ok"
    assert yanit.sayfa == 20  # sayfa 10 dışlandı, sayfa 20 döndü
    assert ("9-A", "arsiv1", 20, "İngilizce", "present perfect tense") in sahte_kayit["kayitlar"]


def test_tum_adaylar_gosterilmisse_tekrar_durumu_doner(izole_arsiv, sahte_kayit):
    _metin_dosyasi_yaz(izole_arsiv, "arsiv1.txt", {
        10: "fizik hareket hız zaman grafiği sorusu",
    })
    sahte_kayit["gosterilmisler"].add(("arsiv1", 10))

    yanit = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="9-A", ders="Fizik", konu="hareket hız zaman")
    )
    assert yanit.status == "tekrar"
    assert yanit.dosya_adi is None
    assert "daha önceki" in yanit.metin


def test_db_erisilemezse_dedup_sessizce_atlanir_akis_bozulmaz(izole_arsiv, monkeypatch):
    """_daha_once_gosterildi_mi/_gosterimi_kaydet'i DEĞİL, altlarındaki
    db.baglanti()'yi patlatır — böylece gerçekten kendi fail-open
    try/except'lerinin çalıştığı test edilir (fonksiyonun tamamını
    monkeypatch'lemek bu iç mantığı hiç çağırmadan atlar)."""
    _metin_dosyasi_yaz(izole_arsiv, "arsiv1.txt", {10: "kimya asit baz tepkime sorusu"})

    class _PatlayanBaglanti:
        def __enter__(self):
            raise RuntimeError("DB bağlantısı yok")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(yks.db, "baglanti", lambda: _PatlayanBaglanti())

    yanit = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="9-A", ders="Kimya", konu="asit baz tepkime")
    )
    # dedup okuma/kaydetme patlasa bile soru normal şekilde sunulur.
    assert yanit.status == "ok"
    assert yanit.dosya_adi == "arsiv1"
    assert yanit.sayfa == 10


def test_karma_dosyada_ders_baslikla_filtrelenir(izole_arsiv, sahte_kayit):
    """2026-08-30, 9-A canlı hatası: 'Tarih' istenince AYT_EA gibi KARMA
    (Türk Dili + Tarih + Coğrafya tek dosyada) bir kaynaktan Türk Dili
    sorusu geliyordu — gerçek dosyada doğrulandı, her sayfa kendi bölüm
    başlığını (ör. 'TARİH-1') ilk satırında tekrarlıyor. `ders` artık bu
    başlığa göre SERT filtre, yalnızca skor önyargısı değil."""
    _metin_dosyasi_yaz(izole_arsiv, "karma.txt", {
        20: "TÜRK DİLİ VE EDEBİYATI\nEski Çağ uygarlıklarının yaratılış "
            "efsaneleri üzerine bir okuma parçası sorusu",
        82: "TARİH-1\nEski Çağ Medeniyetlerinde ilk yazılı hukuk metinleri "
            "üzerine bir soru",
    })

    yanit = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="9-A", ders="Tarih", konu="Eski Çağ Medeniyetleri")
    )
    assert yanit.status == "ok"
    assert yanit.sayfa == 82   # TARİH-1 başlıklı sayfa, Türk Dili DEĞİL

    # Aynı sorgu, ders verilmeden — eski davranış hâlâ mümkün (bilerek
    # gevşek), ikisi de aday olabilir; yalnızca REGRESYON olmadığını
    # doğruluyoruz (en az bir sonuç dönüyor).
    yks._OTURUMLAR.clear()
    sahte_kayit["gosterilmisler"].clear()
    yanit2 = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="9-A", konu="Eski Çağ Medeniyetleri")
    )
    assert yanit2.status == "ok"


def test_temiz_baslik_yoksa_eski_davranisa_duser(izole_arsiv, sahte_kayit):
    """TYT gibi dosyalarda temiz bölüm başlığı yok (ölçüldü) — filtre bu
    durumda hiçbir sayfayı elemeMELİ, eski (yalnızca kelime skoru)
    davranışa düşmeli."""
    _metin_dosyasi_yaz(izole_arsiv, "karisik.txt", {
        5: "başlıksız düz metin — fizik hareket hız zaman grafiği sorusu",
    })

    yanit = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="9-A", ders="Fizik", konu="hareket hız zaman")
    )
    assert yanit.status == "ok"
    assert yanit.sayfa == 5


def test_gosterim_hem_yeni_arama_hem_sonrakinde_kaydedilir(izole_arsiv, sahte_kayit):
    _metin_dosyasi_yaz(izole_arsiv, "arsiv1.txt", {
        10: "matematik türev limit sorusu birinci",
        20: "matematik türev limit sorusu ikinci",
    })

    ilk = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="9-A", ders="Matematik", konu="türev limit", adet=2)
    )
    assert ilk.status == "ok"
    assert len(sahte_kayit["kayitlar"]) == 1

    sonraki = yks.yks_sorusu_endpoint(yks.YksIstek(derslik="9-A", sonraki=True))
    assert sonraki.status == "ok"
    assert len(sahte_kayit["kayitlar"]) == 2
    # sonraki çağrı orijinal arama sorgusunun ders/konu'sunu taşımalı.
    assert sahte_kayit["kayitlar"][1][3] == "Matematik"
    assert sahte_kayit["kayitlar"][1][4] == "türev limit"
