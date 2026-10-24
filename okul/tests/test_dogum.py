import sqlite3
from datetime import date

from ayarlar import AYAR
from fastapi import FastAPI
from fastapi.testclient import TestClient
from kaynaklar import KaynakHatasi, dogum
from rotalar import pano


def _sms_db(satirlar):
    c = sqlite3.connect(AYAR.sms_db_yolu)
    c.executescript(
        "CREATE TABLE siniflar (id INTEGER PRIMARY KEY, ad TEXT);"
        "CREATE TABLE kisiler (id INTEGER PRIMARY KEY, ad_soyad TEXT, sinif_id INTEGER, tur TEXT, dogum_tarihi TEXT);"
        "INSERT INTO siniflar VALUES (1,'9-A'),(2,'Personel'),(3,'Bilinmeyen Sınıf');"
    )
    c.executemany("INSERT INTO kisiler(ad_soyad, sinif_id, tur, dogum_tarihi) VALUES (?,?,?,?)", satirlar)
    c.commit()
    c.close()


def test_sali_yalniz_o_gun_ogrenci_sinifli_personel_sinifsiz():
    _sms_db([
        ("Ayşe Kaya", 1, "ogrenci", "2009-10-27"),
        ("Mehmet Demir", 2, "personel", "1980-10-27"),
        ("Başka Gün", 1, "ogrenci", "2009-10-28"),
        ("Ayrılan Öğrenci", 3, "ogrenci", "2009-10-27"),
        ("Veli Kişi", 1, "veli", "1980-10-27"),
    ])
    assert dogum.bugunun_dogumlari(date(2026, 10, 27)) == [
        {"ad": "Ayşe K.", "sinif": "9-A"},
        {"ad": "Mehmet D.", "sinif": None},
    ]


def test_pazartesi_hafta_sonu_dogumlarini_kapsar():
    _sms_db([("Cumartesi Doğan", 1, "ogrenci", "2009-10-24"), ("Pazar Doğan", 1, "ogrenci", "2009-10-25"),
             ("Cuma Doğan", 1, "ogrenci", "2009-10-23")])
    adlar = [k["ad"] for k in dogum.bugunun_dogumlari(date(2026, 10, 26))]  # pazartesi
    assert adlar == ["Cumartesi D.", "Pazar D."]


def test_29_subat_artik_olmayan_yilda_28_subatta():
    _sms_db([("Artık Doğan", 1, "ogrenci", "2008-02-29")])
    assert len(dogum.bugunun_dogumlari(date(2026, 2, 28))) == 1  # artık olmayan yıl: 28'inde kutlanır
    assert len(dogum.bugunun_dogumlari(date(2028, 2, 28))) == 0  # artık yıl: 29'unda kutlanır
    assert len(dogum.bugunun_dogumlari(date(2028, 2, 29))) == 1


def test_veritabani_yoksa_kaynak_hatasi():
    try:
        dogum.bugunun_dogumlari(date(2026, 10, 27))
    except KaynakHatasi:
        return
    raise AssertionError("KaynakHatasi bekleniyordu")


def test_pano_ucu_dogum_ogesini_basa_koyar_kaynak_yoksa_sorunsuz(monkeypatch, conn, ornek, saat):
    app = FastAPI()
    app.include_router(pano.router)
    istemci = TestClient(app, client=("192.168.23.254", 5555))
    assert istemci.get("/api/pano").status_code == 200  # sms.db yok -> kutlama atlanır, uç düşmez
    monkeypatch.setattr(pano.dogum, "bugunun_dogumlari", lambda _g: [{"ad": "Ayşe K.", "sinif": "9-A"}])
    d = istemci.get("/api/pano").json()["duyurular"][0]
    assert d["baslik"] == "DOĞUM GÜNÜ"
    assert "Ayşe K. (9-A)" in d["metin"] and "kutlu olsun" in d["metin"]
