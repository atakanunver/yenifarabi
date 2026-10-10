import pytest
import yetki
from fastapi import HTTPException


def _k(conn, kid):
    return conn.execute("SELECT * FROM kullanici WHERE id = ?", (kid,)).fetchone()


def test_ogrenci_yalnizca_kendini_gorur(conn, ornek):
    k = _k(conn, ornek["ogr1_k"])
    assert yetki.ogrenci_gorebilir(conn, k, ornek["ogr1"])
    assert not yetki.ogrenci_gorebilir(conn, k, ornek["ogr2"])


def test_veli_yalnizca_cocugunu_gorur(conn, ornek):
    k = _k(conn, ornek["veli1"])
    assert yetki.ogrenci_gorebilir(conn, k, ornek["ogr1"])
    assert not yetki.ogrenci_gorebilir(conn, k, ornek["ogr2"])
    assert [c["id"] for c in yetki.veli_cocuklari(conn, ornek["veli1"])] == [
        ornek["ogr1"]
    ]


def test_ogretmen_yalnizca_gorevli_sinifi_gorur(conn, ornek):
    k = _k(conn, ornek["ogretmen"])
    assert yetki.ogrenci_gorebilir(conn, k, ornek["ogr1"])
    assert not yetki.ogrenci_gorebilir(conn, k, ornek["ogr2"])
    assert yetki.sinif_ders_yetkili(conn, k, "9-A", "matematik")
    assert not yetki.sinif_ders_yetkili(conn, k, "9-A", "fizik")
    assert not yetki.sinif_ders_yetkili(conn, k, "9-B", "matematik")
    assert yetki.sinif_yetkili(conn, k, "9-A")
    assert not yetki.sinif_yetkili(conn, k, "9-B")


def test_yonetici_her_seyi_gorur(conn, ornek):
    k = _k(conn, ornek["yonetici"])
    assert yetki.ogrenci_gorebilir(conn, k, ornek["ogr2"])
    assert yetki.sinif_ders_yetkili(conn, k, "12-B", "fizik")
    assert yetki.kullanici_siniflari(conn, k) is None


def test_kullanici_siniflari(conn, ornek):
    assert yetki.kullanici_siniflari(conn, _k(conn, ornek["ogr1_k"])) == ["9-A"]
    assert yetki.kullanici_siniflari(conn, _k(conn, ornek["veli1"])) == ["9-A"]
    assert yetki.kullanici_siniflari(conn, _k(conn, ornek["ogretmen"])) == ["9-A"]


def test_ogrenci_getir_yetkisizde_404(conn, ornek):
    k = _k(conn, ornek["veli1"])
    assert yetki.ogrenci_getir(conn, k, ornek["ogr1"])["okul_no"] == 101
    with pytest.raises(HTTPException) as e:
        yetki.ogrenci_getir(conn, k, ornek["ogr2"])
    assert e.value.status_code == 404
    with pytest.raises(HTTPException):
        yetki.ogrenci_getir(conn, k, 99999)


def test_erisim_kaydi(conn, ornek):
    k = _k(conn, ornek["veli1"])
    yetki.erisim_kaydet(conn, k, "devamsizlik", ornek["ogr1"], "1.2.3.4")
    r = conn.execute("SELECT * FROM erisim_log").fetchone()
    assert (r["kullanici_id"], r["eylem"], r["ogrenci_id"], r["ip"]) == (
        ornek["veli1"],
        "devamsizlik",
        ornek["ogr1"],
        "1.2.3.4",
    )
