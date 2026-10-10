from datetime import timedelta

import duyurular


def _k(conn, kid):
    return conn.execute("SELECT * FROM kullanici WHERE id = ?", (kid,)).fetchone()


def _basliklar(conn, kid):
    return {d["baslik"] for d in duyurular.gorunur_duyurular(conn, _k(conn, kid))}


def test_hedefe_gore_gorunurluk(conn, ornek, saat):
    y = ornek["yonetici"]
    duyurular.duyuru_ekle(conn, y, "Okul", "x", "okul")
    duyurular.duyuru_ekle(conn, y, "9A", "x", "sinif", "9-A")
    duyurular.duyuru_ekle(conn, y, "9B", "x", "sinif", "9-B")
    duyurular.duyuru_ekle(conn, y, "Veliler", "x", "rol", "veli")
    assert _basliklar(conn, ornek["ogr1_k"]) == {"Okul", "9A"}
    assert _basliklar(conn, ornek["ogr2_k"]) == {"Okul", "9B"}
    assert _basliklar(conn, ornek["veli1"]) == {"Okul", "9A", "Veliler"}
    assert _basliklar(conn, ornek["ogretmen"]) == {"Okul", "9A"}
    assert _basliklar(conn, y) == {"Okul", "9A", "9B", "Veliler"}


def test_suresi_gecen_gizlenir(conn, ornek, saat):
    bitis = (saat["an"] + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    duyurular.duyuru_ekle(conn, ornek["yonetici"], "Kisa", "x", "okul", bitis=bitis)
    assert _basliklar(conn, ornek["ogr1_k"]) == {"Kisa"}
    saat["an"] += timedelta(days=2)
    assert _basliklar(conn, ornek["ogr1_k"]) == set()


def test_ekleme_yetkisi(conn, ornek):
    ogr = _k(conn, ornek["ogretmen"])
    yon = _k(conn, ornek["yonetici"])
    assert duyurular.ekleyebilir_mi(conn, ogr, "sinif", "9-A")
    assert not duyurular.ekleyebilir_mi(conn, ogr, "sinif", "9-B")
    assert not duyurular.ekleyebilir_mi(conn, ogr, "okul", None)
    assert duyurular.ekleyebilir_mi(conn, yon, "okul", None)
    assert duyurular.ekleyebilir_mi(conn, yon, "rol", "veli")
    assert not duyurular.ekleyebilir_mi(conn, yon, "rol", "mudur")
    assert not duyurular.ekleyebilir_mi(conn, _k(conn, ornek["veli1"]), "sinif", "9-A")
