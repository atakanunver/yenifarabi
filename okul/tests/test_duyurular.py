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


def test_okuma_raporu(conn, ornek, saat):
    y = ornek["yonetici"]
    did = duyurular.duyuru_ekle(conn, y, "Okul", "x", "okul")
    d = conn.execute("SELECT * FROM duyuru WHERE id = ?", (did,)).fetchone()
    r0 = duyurular.okuma_raporu(conn, d)
    assert all(o[0] == 0 for o in r0["roller"].values())
    assert {x["rol"] for x in r0["okumayan"]} == {"ogrenci", "veli", "ogretmen"}
    k = _k(conn, ornek["ogr1_k"])
    duyurular.okuma_kaydet(conn, k, duyurular.gorunur_duyurular(conn, k))
    duyurular.okuma_kaydet(conn, k, duyurular.gorunur_duyurular(conn, k))  # tekrar: tek kayıt
    r1 = duyurular.okuma_raporu(conn, d)
    assert r1["roller"]["ogrenci"][0] == 1
    assert ornek["ogr1_k"] not in {x["id"] for x in r1["okumayan"]}
    assert r1["siniflar"]["9-A"]["ogrenci"][0] == 1


def test_okuma_hedef_ve_silme(conn, ornek, saat):
    y = ornek["yonetici"]
    did = duyurular.duyuru_ekle(conn, y, "9B", "x", "sinif", "9-B")
    d = conn.execute("SELECT * FROM duyuru WHERE id = ?", (did,)).fetchone()
    r = duyurular.okuma_raporu(conn, d)
    assert list(r["siniflar"]) == ["9-B"]
    assert ornek["ogr1_k"] not in {x["id"] for x in r["okumayan"]}
    k = _k(conn, ornek["ogr2_k"])
    duyurular.okuma_kaydet(conn, k, duyurular.gorunur_duyurular(conn, k))
    assert duyurular.sil(conn, _k(conn, y), did)
    assert conn.execute("SELECT count(*) FROM duyuru_okuma").fetchone()[0] == 0
