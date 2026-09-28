"""otomasyon.py birim testleri."""

import json
from datetime import date
from unittest.mock import patch

import pytest

import db
import otomasyon
import yoklama_kaynak


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_yolu = tmp_path / "test_otomasyon.db"
    yedek_dizini = tmp_path / "yedek"
    monkeypatch.setattr(db, "DB_YOLU", db_yolu)
    monkeypatch.setattr(db, "YEDEK_DIZINI", yedek_dizini)
    db.semayi_kur()
    conn = db.baglanti()
    yield conn
    conn.close()


def test_okul_gunu_mu():
    pazartesi = date(2026, 9, 21)
    cuma = date(2026, 9, 25)
    cumartesi = date(2026, 9, 26)
    pazar = date(2026, 9, 27)

    assert otomasyon.okul_gunu_mu(pazartesi) is True
    assert otomasyon.okul_gunu_mu(cuma) is True
    assert otomasyon.okul_gunu_mu(cumartesi) is False
    assert otomasyon.okul_gunu_mu(pazar) is False


def test_ilk_ders_devamsizlar_ve_veliler(test_db, monkeypatch):
    # Öğrenci ve velilerini ekle
    siniflar = {s["ad"]: s["id"] for s in db.siniflar_listele(test_db)}
    sinif_9a = siniflar["9-A"]
    sinif_10a = siniflar["10-A"]

    # 9-A'da Ali Kaya (anne ve baba telefonlu)
    ali_id = db.kisi_ekle(
        test_db, "Ali Kaya", None, sinif_9a, "ogrenci", okul_no=101
    )
    db.kisi_ekle(
        test_db, "Fatma Kaya", "05321112233", sinif_9a, "veli", ogrenci_kisi_id=ali_id, veli_rol="anne"
    )
    db.kisi_ekle(
        test_db, "Mehmet Kaya", "05322223344", sinif_9a, "veli", ogrenci_kisi_id=ali_id, veli_rol="baba"
    )

    # 9-A'da Veli Çelik (telefonsuz velili veya velisiz)
    db.kisi_ekle(
        test_db, "Veli Çelik", None, sinif_9a, "ogrenci", okul_no=102
    )

    # 9-A'da Can Demir (izinli)
    can_id = db.kisi_ekle(
        test_db, "Can Demir", None, sinif_9a, "ogrenci", okul_no=103
    )
    db.kisi_ekle(
        test_db, "Ayşe Demir", "05323334455", sinif_9a, "veli", ogrenci_kisi_id=can_id, veli_rol="anne"
    )

    # Sahte yoklama satırları
    sahte_satirlar = [
        # 9-A 1. ders: alındı, Ali Kaya ve Veli Çelik yok, Can Demir izinli ve yok
        {
            "sinif": "9-A",
            "ders_no": 1,
            "durum": "alindi",
            "yok_isimleri": ["Ali Kaya", "Veli Çelik", "Can Demir"],
            "izinli_isimleri": ["Can Demir"],
            "kaydedilme_saati": "08:25",
        },
        # 9-A 2. ders: (1. ders derlemesinde DİKKATE ALINMAMALI)
        {
            "sinif": "9-A",
            "ders_no": 2,
            "durum": "alindi",
            "yok_isimleri": ["Ali Kaya"],
            "izinli_isimleri": [],
            "kaydedilme_saati": "09:15",
        },
        # 10-A 1. ders: tahta ulaşılamaz (HARİÇ TUTULMALI, devamsız üretmemeli)
        {
            "sinif": "10-A",
            "ders_no": 1,
            "durum": "tahta_ulasilamaz",
            "yok_isimleri": ["Ahmet Yılmaz"],
            "izinli_isimleri": [],
            "kaydedilme_saati": "08:15",
        },
    ]

    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: sahte_satirlar)

    sonuc = otomasyon.ilk_ders_devamsizlar(test_db, "2026-09-25")

    assert "9-A" in sonuc["dahil_siniflar"]
    haric_isimler = [h["sinif"] for h in sonuc["haric_siniflar"]]
    assert "10-A" in haric_isimler

    # Can Demir izinli olduğu için SMS listesinde olmamalı!
    ogrenci_adlari = [o["ad_soyad"] for o in sonuc["ogrenciler"]]
    assert "Ali Kaya" in ogrenci_adlari
    assert "Veli Çelik" in ogrenci_adlari
    assert "Can Demir" not in ogrenci_adlari
    assert sonuc["izinli_sayisi"] == 1

    # Ali Kaya'nın 2 velisine de SMS çıkmalı
    smsler = sonuc["gonderilecek_smsler"]
    assert len(smsler) == 2
    veli_adlari = {s["veli_ad"] for s in smsler}
    assert "Fatma Kaya" in veli_adlari
    assert "Mehmet Kaya" in veli_adlari

    for s in smsler:
        assert "Ali Kaya" in s["mesaj"]
        assert s["veli_ad"] in s["mesaj"]


def test_otomasyon_calistir_kuru(test_db, monkeypatch):
    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: [])
    sonuc = otomasyon.otomasyon_calistir(test_db, kuru=True, tarih="2026-09-25")
    assert sonuc["durum"] == "simulasyon"
    assert sonuc["kuru_calistirma"] is True
    # Kuru çalıştırma son tarihi güncellemez
    assert db.ayar_oku(test_db, otomasyon.AYAR_SON_TARIH) == ""


def test_otomasyon_calistir_canli_ve_idempotent(test_db, monkeypatch):
    siniflar = {s["ad"]: s["id"] for s in db.siniflar_listele(test_db)}
    sinif_9a = siniflar["9-A"]

    ogr_id = db.kisi_ekle(test_db, "Deniz Aras", None, sinif_9a, "ogrenci", okul_no=105)
    db.kisi_ekle(
        test_db, "Selin Aras", "05329998877", sinif_9a, "veli", ogrenci_kisi_id=ogr_id, veli_rol="anne"
    )

    sahte_satirlar = [
        {
            "sinif": "9-A",
            "ders_no": 1,
            "durum": "alindi",
            "yok_isimleri": ["Deniz Aras"],
            "izinli_isimleri": [],
            "kaydedilme_saati": "08:30",
        }
    ]
    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: sahte_satirlar)

    gonderilenler = []

    def mock_toplu_gonder(ayarlar, kisiler, callback, durdur_bayragi, bekleme_sn):
        for isim, tel, msg in kisiler:
            gonderilenler.append((isim, tel, msg))
            callback(isim, tel, msg, "gonderildi", None)

    monkeypatch.setattr(otomasyon.sms_gonderici, "toplu_gonder", mock_toplu_gonder)

    # 1. Çalıştırma: Gönderim yapmalı
    sonuc1 = otomasyon.otomasyon_calistir(
        test_db, kuru=False, tetikleyen="otomatik_zamanlayici", tarih="2026-09-25"
    )
    assert sonuc1["durum"] == "tamamlandi"
    assert len(gonderilenler) == 1
    assert gonderilenler[0][0] == "Selin Aras"
    assert db.ayar_oku(test_db, otomasyon.AYAR_SON_TARIH) == "2026-09-25"

    son_sonuc = json.loads(db.ayar_oku(test_db, otomasyon.AYAR_SON_SONUC))
    assert son_sonuc["veli_sms_sayisi"] == 1
    assert son_sonuc["basarili_sayisi"] == 1

    # 2. Çalıştırma: Aynı gün ikinci kez çalışırsa idempotent olmalı, tekrar SMS göndermemeli!
    sonuc2 = otomasyon.otomasyon_calistir(
        test_db, kuru=False, tetikleyen="otomatik_zamanlayici", tarih="2026-09-25"
    )
    assert sonuc2["durum"] == "zaten_calisti"
    # Hala 1 olmalı, artmamış olmalı
    assert len(gonderilenler) == 1


def test_otomasyon_gercek_toplu_gonder_ile_sms_gonderir(test_db, monkeypatch):
    """toplu_gonder MOCK'LANMADAN (yalnızca modem bağlantısı sahte): 2026-09-25'e
    kadar otomasyon durdur_bayragi=None veriyordu, toplu_gonder ilk .is_set()'te
    patlıyor ve HİÇ SMS gitmiyordu — mock'lu testler bunu göremiyordu."""
    from unittest.mock import MagicMock

    siniflar = {s["ad"]: s["id"] for s in db.siniflar_listele(test_db)}
    ogr_id = db.kisi_ekle(test_db, "Deniz Aras", None, siniflar["9-A"], "ogrenci", okul_no=105)
    db.kisi_ekle(
        test_db, "Selin Aras", "05329998877", siniflar["9-A"], "veli", ogrenci_kisi_id=ogr_id, veli_rol="anne"
    )
    monkeypatch.setattr(yoklama_kaynak, "gunun_satirlari", lambda tarih: [{
        "sinif": "9-A", "ders_no": 1, "durum": "alindi", "yok_isimleri": ["Deniz Aras"],
        "izinli_isimleri": [], "kaydedilme_saati": "08:30",
    }])

    class SahteBaglanti:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    gonderilen = []
    sahte_client = MagicMock()
    sahte_client.sms.send_sms.side_effect = lambda tel, msg, text_mode=None: gonderilen.append(tel)
    monkeypatch.setattr(otomasyon.sms_gonderici, "modem_ayarlarini_yukle", lambda: {})
    monkeypatch.setattr(otomasyon.sms_gonderici, "_baglan", lambda ayarlar: SahteBaglanti())
    monkeypatch.setattr(otomasyon.sms_gonderici, "Client", lambda conn: sahte_client)

    sonuc = otomasyon.otomasyon_calistir(
        test_db, kuru=False, tetikleyen="manuel_arayuz", tarih="2026-09-25", bekleme_sn=0
    )
    assert gonderilen == [["05329998877"]]
    assert sonuc["ozet"]["basarili_sayisi"] == 1
    assert sonuc["ozet"]["hatali_sayisi"] == 0
