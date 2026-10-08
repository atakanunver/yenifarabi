"""Rehber kişi düzenleme: formda olmayan okul_no / veli_rol korunmalı (2026-10-08 hatası)."""

import app
import auth
import db
import pytest
from fastapi import Request


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "t.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    db.semayi_kur()
    conn = db.baglanti()
    yield conn
    conn.close()


def _istek(conn):
    token = auth.oturum_olustur(conn)
    return Request({"type": "http", "method": "POST", "path": "/",
                    "headers": [(b"cookie", f"{auth.COOKIE_ADI}={token}".encode())]})


@pytest.mark.anyio
async def test_duzenleme_okul_no_ve_veli_rolunu_korur(test_db):
    a = db.sinif_ekle(test_db, "11-A")
    b = db.sinif_ekle(test_db, "11-B")
    ogr = db.kisi_ekle(test_db, "Ogr", "05551112233", a, "ogrenci", okul_no=160)
    veli = db.kisi_ekle(test_db, "Veli", "05554445566", a, "veli",
                        ogrenci_kisi_id=ogr, veli_rol="anne")

    await app.rehber_kisi_duzenle(_istek(test_db), ogr, ad_soyad="Ogr", telefon="05551112233",
                                  sinif_id=b, tur="ogrenci", ogrenci_kisi_id=None)
    await app.rehber_kisi_duzenle(_istek(test_db), veli, ad_soyad="Veli", telefon="05554445566",
                                  sinif_id=b, tur="veli", ogrenci_kisi_id=str(ogr))

    o = test_db.execute("SELECT sinif_id, okul_no FROM kisiler WHERE id = ?", (ogr,)).fetchone()
    v = test_db.execute("SELECT veli_rol FROM kisiler WHERE id = ?", (veli,)).fetchone()
    assert (o["sinif_id"], o["okul_no"]) == (b, 160)
    assert v["veli_rol"] == "anne"
