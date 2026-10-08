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
    monkeypatch.setattr(yks, "HARITA_YOLU", tmp_path / "yok" / "yks_konu.json")
    monkeypatch.setattr(yks, "_harita_onbellek", yks._HARITA_YUKLENMEDI)
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


# 2026-10-08: yks.py artık şıksız/etiketsiz sayfayı soru saymıyor; eski testlerin
# sahte gövdelerine bu şık satırı eklendi (test niyetleri değişmedi).
SIK = "\nA) bir B) iki C) üç D) dört E) beş"


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
        10: "İngilizce YDT present perfect tense sorusu kamera tasarım" + SIK,
        20: "İngilizce YDT present perfect tense sorusu farklı kamera metni" + SIK,
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
        10: "fizik hareket hız zaman grafiği sorusu" + SIK,
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
    _metin_dosyasi_yaz(izole_arsiv, "arsiv1.txt", {10: "kimya asit baz tepkime sorusu" + SIK})

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
            "efsaneleri üzerine bir okuma parçası sorusu" + SIK,
        82: "TARİH-1\nEski Çağ Medeniyetlerinde ilk yazılı hukuk metinleri "
            "üzerine bir soru" + SIK,
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
        5: "başlıksız düz metin — fizik hareket hız zaman grafiği sorusu" + SIK,
    })

    yanit = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="9-A", ders="Fizik", konu="hareket hız zaman")
    )
    assert yanit.status == "ok"
    assert yanit.sayfa == 5


def test_gosterim_hem_yeni_arama_hem_sonrakinde_kaydedilir(izole_arsiv, sahte_kayit):
    _metin_dosyasi_yaz(izole_arsiv, "arsiv1.txt", {
        10: "matematik türev limit sorusu birinci" + SIK,
        20: "matematik türev limit sorusu ikinci" + SIK,
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


# ── 2026-10-08: konu eşleşmesi + soru sayfası filtresi + harita ─────────────────

def _harita_yaz(izole_arsiv, harita: dict, monkeypatch):
    import json
    yol = izole_arsiv / "yks_konu.json"
    yol.write_text(json.dumps(harita, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(yks, "HARITA_YOLU", yol)
    monkeypatch.setattr(yks, "_harita_onbellek", yks._HARITA_YUKLENMEDI)


def test_dortgenlerde_aci_kapak_degil_dortgen_sayfasi_doner(izole_arsiv, sahte_kayit):
    _metin_dosyasi_yaz(izole_arsiv, "matdosya.txt", {
        # Kapak: yalnızca ders adı, soru/şık yok (olaydaki s.113 gibi)
        113: "MATEMATİK\nM A T E M A T İ K",
        # Konu dışı ama şıklı matematik sayfası
        117: "MATEMATİK\n2019-AYT eşitsizlik çözüm kümesi" + SIK,
        # Hedef
        181: "MATEMATİK\n2020-AYT ABCD dörtgeninde açı ölçüsü kaç derecedir?" + SIK,
    })
    yanit = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="11-A", ders="matematik", konu="DÖRTGENLERDE AÇI"))
    assert yanit.status == "ok"
    assert yanit.sayfa == 181
    assert yanit.toplam == 1  # kapak ve konu dışı sayfa aday bile değil
    assert "UYDURMA" in yanit.metin


def test_siksiz_etiketsiz_sayfa_asla_aday_olmaz(izole_arsiv, sahte_kayit):
    _metin_dosyasi_yaz(izole_arsiv, "d.txt", {
        5: "olasılık olasılık olasılık hakkında uzun bir açıklama, soru yok",
    })
    yanit = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="9-A", ders="matematik", konu="olasılık"))
    assert yanit.status == "bos"


def test_yalniz_ders_kelimesiyle_eslesen_sayfalar_bos_doner(izole_arsiv, sahte_kayit):
    _metin_dosyasi_yaz(izole_arsiv, "d.txt", {
        10: "MATEMATİK 2019-AYT matematik sorusu fonksiyon limit" + SIK,
        11: "MATEMATİK 2020-AYT matematik sorusu integral alan" + SIK,
    })
    yanit = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="9-A", ders="matematik", konu="dörtgenlerde açı"))
    assert yanit.status == "bos"
    # model ders adını konuya da yazarsa ders kelimesi puana girmemeli
    yanit2 = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="9-A", ders="matematik", konu="matematik dörtgen"))
    assert yanit2.status == "bos"


def test_harita_etiketi_govdeden_ustun_gelir(izole_arsiv, sahte_kayit, monkeypatch):
    _metin_dosyasi_yaz(izole_arsiv, "h.txt", {
        # Gövdede sorgu kelimeleri bol geçiyor ama etiketi başka konu
        10: "2019-AYT dörtgen açı dörtgen açı hesabı" + SIK,
        # Gövdede kelimeler zayıf, etiket tam dörtgen
        20: "2019-AYT şekilde ABCD için açı ölçüsü bulunuz" + SIK,
    })
    _harita_yaz(izole_arsiv, {"h": {
        "sayfa_konu": {"10": ["Çember"], "20": ["Özel Dörtgenler"]},
        "cevap_anahtari_baslangic": None}}, monkeypatch)
    yanit = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="9-A", ders="matematik", konu="dörtgen açı", adet=2))
    assert yanit.status == "ok"
    assert yanit.sayfa == 20
    assert "Özel Dörtgenler" in yanit.metin


def test_cevap_anahtari_bolgesi_aday_degildir(izole_arsiv, sahte_kayit, monkeypatch):
    _metin_dosyasi_yaz(izole_arsiv, "c.txt", {
        10: "2019-AYT limit sorusu" + SIK,
        50: "2019-AYT limit cevap listesi" + SIK,
    })
    _harita_yaz(izole_arsiv, {"c": {"sayfa_konu": {}, "cevap_anahtari_baslangic": 40}},
                monkeypatch)
    yanit = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="9-A", ders="matematik", konu="limit", adet=3))
    assert yanit.status == "ok"
    assert yanit.toplam == 1 and yanit.sayfa == 10


def test_dosyalar_arasi_ayni_sayfa_tekillestirilir(izole_arsiv, sahte_kayit):
    govde = "MATEMATİK\n2020-AYT üçgende açı ortay uzunluğu" + SIK
    _metin_dosyasi_yaz(izole_arsiv, "a.txt", {181: govde})
    _metin_dosyasi_yaz(izole_arsiv, "b.txt", {79: govde})
    yanit = yks.yks_sorusu_endpoint(
        yks.YksIstek(derslik="9-A", ders="matematik", konu="üçgende açı", adet=3))
    assert yanit.status == "ok" and yanit.toplam == 1


def test_kelime_eslesmesi_ek_toleransi():
    assert yks._kelime_eslesir("dortgen", "dortgenlerde")
    assert yks._kelime_eslesir("aci", "acilari")
    assert not yks._kelime_eslesir("aci", "aciklama")
    assert not yks._kelime_eslesir("tarih", "tarla")
    assert not yks._kelime_eslesir("dort", "dortgen")  # 4 harfli kök yanlış pozitifi
