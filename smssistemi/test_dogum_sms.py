import json
from datetime import date

import db
import dogum_sms
import pytest
import sms_gonderici


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "t.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    db.semayi_kur()
    conn = db.baglanti()
    yield conn
    conn.close()


@pytest.fixture
def giden(monkeypatch):
    """Gerçek modem yok: toplu_gonder'i sahte, gönderilenleri listeler."""
    liste = []

    def sahte(ayarlar, kisiler, cb, durdur_bayragi, bekleme_sn):
        for isim, tel, mesaj in kisiler:
            liste.append((isim, tel, mesaj))
            cb(isim, tel, mesaj, "gonderildi", None)

    monkeypatch.setattr(sms_gonderici, "modem_ayarlarini_yukle", dict)
    monkeypatch.setattr(sms_gonderici, "toplu_gonder", sahte)
    return liste


def _kisi(conn, ad, tur, dogum, telefon, sinif="9-A"):
    sid = conn.execute("SELECT id FROM siniflar WHERE ad = ?", (sinif,)).fetchone()[0]
    conn.execute("INSERT INTO kisiler (ad_soyad, telefon, sinif_id, tur, dogum_tarihi) VALUES (?,?,?,?,?)", (ad, telefon, sid, tur, dogum))
    conn.commit()


def test_alicilar_ogrenci_ve_personel_veli_ayrilan_hariç(test_db):
    _kisi(test_db, "Ayşe Kaya", "ogrenci", "2009-10-27", "05551110001")
    _kisi(test_db, "Mehmet Demir", "personel", "1980-10-27", "05551110002", "Personel")
    _kisi(test_db, "Veli Kişi", "veli", "1980-10-27", "05551110003")
    _kisi(test_db, "Ayrılan", "ogrenci", "2009-10-27", "05551110004", "Bilinmeyen Sınıf")
    _kisi(test_db, "Başka Gün", "ogrenci", "2009-10-28", "05551110005")
    a = dogum_sms.alicilar(test_db, date(2026, 10, 27))
    assert [x["isim"] for x in a["alicilar"]] == ["Ayşe Kaya", "Mehmet Demir"]


def test_pazartesi_hafta_sonu_doganlari_kapsar(test_db):
    for ad, gun in (("Cmt", "24"), ("Paz", "25"), ("Cuma", "23")):
        _kisi(test_db, ad, "ogrenci", f"2009-10-{gun}", f"0555111{gun}00")
    assert [x["isim"] for x in dogum_sms.alicilar(test_db, date(2026, 10, 26))["alicilar"]] == ["Cmt", "Paz"]


def test_29_subat_artik_olmayan_yilda_28inde_artik_yilda_yalniz_29unda(test_db):
    _kisi(test_db, "Artik", "ogrenci", "2008-02-29", "05551110009")
    assert len(dogum_sms.alicilar(test_db, date(2026, 2, 28))["alicilar"]) == 1
    assert len(dogum_sms.alicilar(test_db, date(2028, 2, 28))["alicilar"]) == 0
    assert len(dogum_sms.alicilar(test_db, date(2028, 2, 29))["alicilar"]) == 1


def test_telefonsuz_gecersiz_ve_tekrar_eden_numara(test_db):
    _kisi(test_db, "A", "ogrenci", "2009-10-27", "05551110001")
    _kisi(test_db, "B", "ogrenci", "2009-10-27", "05551110001")  # aynı numara
    _kisi(test_db, "C", "ogrenci", "2009-10-27", None)
    _kisi(test_db, "D", "ogrenci", "2009-10-27", "123")
    a = dogum_sms.alicilar(test_db, date(2026, 10, 27))
    assert [x["isim"] for x in a["alicilar"]] == ["A"] and a["telefonsuz"] == 2


def test_varsayilan_kuru_sms_gitmez_ama_sonuc_yazilir(test_db, giden):
    _kisi(test_db, "Ayşe Kaya", "ogrenci", "2009-10-27", "05551110001")
    r = dogum_sms.calistir(test_db, date(2026, 10, 27), tetikleyen="otomatik_zamanlayici")
    assert r["durum"] == "kuru" and giden == []
    assert json.loads(db.ayar_oku(test_db, "dogum_sms_son_sonuc"))["alici_sayisi"] == 1
    assert dogum_sms.calistir(test_db, date(2026, 10, 27), tetikleyen="otomatik_zamanlayici")["durum"] == "kuru_zaten"


def test_gercek_mod_gonderir_son_tarih_yazar_ikinci_cagri_atlanir(test_db, giden):
    _kisi(test_db, "Ayşe Kaya", "ogrenci", "2009-10-27", "05551110001")
    db.ayar_yaz(test_db, "dogum_sms_gercek", "1")
    r = dogum_sms.calistir(test_db, date(2026, 10, 27), tetikleyen="otomatik_zamanlayici")
    assert r["durum"] == "tamamlandi" and len(giden) == 1 and "Ayşe Kaya" in giden[0][2]
    assert db.ayar_oku(test_db, "dogum_sms_son_tarih") == "2026-10-27"
    assert test_db.execute("SELECT COUNT(*) FROM gonderimler WHERE gonderim_id LIKE 'dgm_%'").fetchone()[0] == 1
    assert dogum_sms.calistir(test_db, date(2026, 10, 27), tetikleyen="otomatik_zamanlayici")["durum"] == "zaten_calisti"
    assert len(giden) == 1


def test_hic_sms_denenmediyse_son_tarih_yazilmaz(test_db, monkeypatch):
    _kisi(test_db, "Ayşe Kaya", "ogrenci", "2009-10-27", "05551110001")
    db.ayar_yaz(test_db, "dogum_sms_gercek", "1")
    monkeypatch.setattr(sms_gonderici, "modem_ayarlarini_yukle", dict)
    monkeypatch.setattr(sms_gonderici, "toplu_gonder",
                        lambda a, k, cb, durdur_bayragi, bekleme_sn: [cb(i, t, m, "hata", "BAĞLANTI HATASI: x") for i, t, m in k])
    assert dogum_sms.calistir(test_db, date(2026, 10, 27), tetikleyen="otomatik_zamanlayici")["durum"] == "basarisiz"
    assert not db.ayar_oku(test_db, "dogum_sms_son_tarih")


def test_test_telefonu_yalniz_o_numaraya_ve_kayit_yazmaz(test_db, giden):
    _kisi(test_db, "Ayşe Kaya", "ogrenci", "2009-10-27", "05551110001")
    r = dogum_sms.calistir(test_db, date(2026, 10, 27), test_telefon="0555 222 00 00")
    assert r["durum"] == "test" and [g[1] for g in giden] == ["05552220000"]
    assert not db.ayar_oku(test_db, "dogum_sms_son_tarih") and not db.ayar_oku(test_db, "dogum_sms_son_sonuc")
    with pytest.raises(ValueError):
        dogum_sms.calistir(test_db, date(2026, 10, 27), test_telefon="abc")


def test_kilit_mesgulse_hemen_doner(test_db):
    import otomasyon
    with otomasyon._CALISMA_KILIDI:
        assert dogum_sms.calistir_thread()["durum"] == "calisiyor"
