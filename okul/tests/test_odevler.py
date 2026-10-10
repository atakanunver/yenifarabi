import odevler
import pytest


def _soru(metin, dogru, kazanim=""):
    return {
        "metin": metin,
        "siklar": ["a", "b", "c", "d"],
        "dogru": dogru,
        "kazanim": kazanim,
        "kaynak": "elle",
    }


def test_form_sorulari_elle_ve_havuz():
    form = {
        "soru_1": "2+2?",
        "sik_1_0": "3",
        "sik_1_1": "4",
        "sik_1_2": "5",
        "sik_1_3": "6",
        "dogru_1": "1",
        "kazanim_1": "Toplama",
        "soru_2": "",
    }
    havuz = [
        {
            "id": 7,
            "soru": "H?",
            "secenekler": ["w", "x", "y", "z"],
            "dogru_index": 2,
            "konu": "Konu",
        }
    ]
    s = odevler.form_sorulari(form, havuz)
    assert s[0] == {
        "metin": "2+2?",
        "siklar": ["3", "4", "5", "6"],
        "dogru": 1,
        "kazanim": "Toplama",
        "kaynak": "elle",
    }
    assert s[1] == {
        "metin": "H?",
        "siklar": ["w", "x", "y", "z"],
        "dogru": 2,
        "kazanim": "Konu",
        "kaynak": "havuz:7",
    }


def test_form_sorulari_eksik_sik_hata():
    with pytest.raises(odevler.OdevHatasi):
        odevler.form_sorulari({"soru_1": "x", "sik_1_0": "a", "dogru_1": "0"}, [])


def test_teslim_normalize():
    assert odevler.teslim_normalize("2026-10-20T15:30") == "2026-10-20 15:30:00"
    assert odevler.teslim_normalize("2026-10-20") == "2026-10-20 23:59:00"
    with pytest.raises(odevler.OdevHatasi):
        odevler.teslim_normalize("dün")


def test_test_odevi_soru_ister(conn, ornek):
    with pytest.raises(odevler.OdevHatasi):
        odevler.odev_olustur(
            conn,
            ornek["ogretmen"],
            "9-A",
            "matematik",
            "test",
            "T",
            "",
            "2026-10-20",
            [],
        )


def test_puanlama():
    sorular = [
        dict(_soru("a", 0), id=1),
        dict(_soru("b", 1), id=2),
        dict(_soru("c", 2), id=3),
    ]
    assert odevler.test_puanla(sorular, {1: 0, 2: 3, 3: None}) == (1, 3, 33)
    assert odevler.test_puanla(sorular, {1: 0, 2: 1, 3: 2}) == (3, 3, 100)


def test_test_teslim_tek_seferlik_ve_kazanim_satirlari(conn, ornek, saat):
    oid = odevler.odev_olustur(
        conn,
        ornek["ogretmen"],
        "9-A",
        "matematik",
        "test",
        "Kesirler",
        "",
        "2026-10-20",
        [_soru("s1", 0, "Kesir toplama"), _soru("s2", 1, "Kesir çarpma")],
    )
    odev = odevler.odev_getir(conn, oid)
    ids = [s["id"] for s in odevler.sorular(conn, oid)]
    puan = odevler.test_teslim_et(conn, odev, ornek["ogr1"], {ids[0]: 0, ids[1]: 0})
    assert puan == 50
    with pytest.raises(odevler.OdevHatasi):
        odevler.test_teslim_et(conn, odev, ornek["ogr1"], {ids[0]: 0, ids[1]: 1})
    assert odevler.teslim_getir(conn, oid, ornek["ogr1"])["puan"] == 50
    assert sorted(odevler.ogrenci_kazanim_satirlari(conn, ornek["ogr1"])) == [
        ("matematik", "Kesir toplama", True),
        ("matematik", "Kesir çarpma", False),
    ]


def test_klasik_yapti_ve_ogrenci_listesi(conn, ornek, saat):
    oid = odevler.odev_olustur(
        conn,
        ornek["ogretmen"],
        "9-A",
        "matematik",
        "klasik",
        "Sayfa 12",
        "1-10 arası",
        "2026-10-20",
        [],
    )
    odev = odevler.odev_getir(conn, oid)
    liste = odevler.ogrenci_odevleri(
        conn,
        conn.execute("SELECT * FROM ogrenci WHERE id=?", (ornek["ogr1"],)).fetchone(),
    )
    assert [(o["baslik"], o["durum"]) for o in liste] == [("Sayfa 12", None)]
    odevler.yapti_isaretle(conn, odev, ornek["ogr1"])
    odevler.yapti_isaretle(conn, odev, ornek["ogr1"])  # idempotent
    liste = odevler.ogrenci_odevleri(
        conn,
        conn.execute("SELECT * FROM ogrenci WHERE id=?", (ornek["ogr1"],)).fetchone(),
    )
    assert liste[0]["durum"] == "yapti"
    ogr2 = conn.execute("SELECT * FROM ogrenci WHERE id=?", (ornek["ogr2"],)).fetchone()
    assert odevler.ogrenci_odevleri(conn, ogr2) == []


def test_sonuc_tablosu(conn, ornek, saat):
    oid = odevler.odev_olustur(
        conn,
        ornek["ogretmen"],
        "9-A",
        "matematik",
        "test",
        "T",
        "",
        "2026-10-20",
        [_soru("s1", 0, "K1"), _soru("s2", 1, "K2")],
    )
    odev = odevler.odev_getir(conn, oid)
    ids = [s["id"] for s in odevler.sorular(conn, oid)]
    odevler.test_teslim_et(conn, odev, ornek["ogr1"], {ids[0]: 0, ids[1]: 0})
    t = odevler.sonuc_tablosu(conn, odev)
    assert [(o["ad_soyad"], o["puan"]) for o in t["ogrenciler"]] == [("Ali Veli", 50)]
    assert t["kazanimlar"] == [("K1", 1, 1), ("K2", 0, 1)]
    assert t["teslim_sayisi"] == 1


def test_ogretmen_odevleri(conn, ornek, saat):
    odevler.odev_olustur(
        conn, ornek["ogretmen"], "9-A", "matematik", "klasik", "A", "", "2026-10-20", []
    )
    yon = conn.execute(
        "SELECT * FROM kullanici WHERE id=?", (ornek["yonetici"],)
    ).fetchone()
    hoca = conn.execute(
        "SELECT * FROM kullanici WHERE id=?", (ornek["ogretmen"],)
    ).fetchone()
    assert len(odevler.ogretmen_odevleri(conn, hoca)) == 1
    assert len(odevler.ogretmen_odevleri(conn, yon)) == 1
