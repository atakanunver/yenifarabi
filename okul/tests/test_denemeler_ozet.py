"""Deneme sınıf/okul özeti, PDF kaydı ve AI yorum depolama. Tüm veri sahte; sıralama YOK."""

import json

import db
import dosyalar
import denemeler

KAZ = {"ders": "Türkçe", "kazanim": "Paragraf"}


def _ogrenci(conn, no, ad, sinif):
    conn.execute(
        "INSERT INTO ogrenci (okul_no, ad_soyad, sinif) VALUES (?, ?, ?)", (no, ad, sinif)
    )


def _deneme(conn, satirlar, yayinda=1):
    """satirlar: [(okul_no, toplam_net, {ders: net}, [kazanım dict])]"""
    did = conn.execute(
        "INSERT INTO deneme (ad, yayinda, olusturma) VALUES ('D1', ?, 'x')", (yayinda,)
    ).lastrowid
    for no, net, dersler, kaz in satirlar:
        conn.execute(
            "INSERT INTO deneme_ogrenci (deneme_id, okul_no, veri) VALUES (?, ?, ?)",
            (did, no, json.dumps({"toplam_net": net, "dersler": dersler, "kazanimlar": kaz})),
        )
    conn.commit()
    return did


def _sinif(conn, sinif, netler, kaz=None, taban=1000):
    satirlar = []
    for i, net in enumerate(netler):
        no = taban + i
        _ogrenci(conn, no, f"Öğrenci {sinif}{i}", sinif)
        satirlar.append((no, net, {"Türkçe": net / 2}, kaz or []))
    return satirlar


def test_goc_v36_tablolari(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.GOCLER) >= 36
    for t in ("deneme_pdf", "deneme_sinif_yorum"):
        conn.execute(f"SELECT * FROM {t}")


def test_sinif_ozeti_5_ogrenci_ortalama_ve_ortak_eksik(conn):
    kaz = [{**KAZ, "d": 0, "y": 2, "b": 1}, {"ders": "Türkçe", "kazanim": "Dil", "d": 3, "y": 0, "b": 0}]
    sat = _sinif(conn, "11-A", [10, 20, 30, 40, 50], kaz)
    did = _deneme(conn, sat)
    o = denemeler.sinif_ozeti(conn, did, "11-A")
    assert o["katilim"] == 5
    assert o["ortalama_net"] == 30.0
    assert o["ders_ortalamalari"] == {"Türkçe": 15.0}
    assert [e["kazanim"] for e in o["ortak_eksikler"]] == ["Paragraf"]
    assert o["ortak_eksikler"][0]["basari"] == 0
    # sıra alanı yok, öğrenciler ada göre
    assert "sira" not in json.dumps(o, ensure_ascii=False).lower()
    adlar = [x["ad"] for x in o["ogrenciler"]]
    assert adlar == sorted(adlar)


def test_sinif_ozeti_5ten_az_ortalama_gizli(conn):
    did = _deneme(conn, _sinif(conn, "11-B", [10, 20, 30, 40]))
    o = denemeler.sinif_ozeti(conn, did, "11-B")
    assert o["katilim"] == 4
    assert o["ortalama_net"] is None and o["ders_ortalamalari"] is None
    assert o["ortak_eksikler"] == []
    assert len(o["ogrenciler"]) == 4  # öğretmen yine kendi öğrencilerini adıyla görür


def test_yayinda_olmayan_deneme_ogretmene_none_yoneticiye_acik(conn):
    did = _deneme(conn, _sinif(conn, "11-C", [1, 2, 3, 4, 5]), yayinda=0)
    assert denemeler.sinif_ozeti(conn, did, "11-C") is None
    assert denemeler.sinif_ozeti(conn, did, "11-C", yalniz_yayinda=False)["katilim"] == 5


def test_okul_ozeti_subeler_ada_gore_kucuk_sube_gizli(conn):
    sat = _sinif(conn, "11-A", [10, 20, 30, 40, 50]) + _sinif(conn, "12-B", [60, 70], taban=2000)
    did = _deneme(conn, sat)
    o = denemeler.okul_ozeti(conn, did, yalniz_yayinda=False)
    assert o["katilim"] == 7
    assert [s["sinif"] for s in o["subeler"]] == ["11-A", "12-B"]
    assert o["subeler"][0]["ortalama_net"] == 30.0
    assert o["subeler"][1]["ortalama_net"] is None  # <5


def test_pdf_kaydet_ve_yol(conn):
    d = dosyalar.deneme_pdf_kaydet(b"%PDF-1.4 sahte")
    assert d.tur == "pdf" and dosyalar.yol("deneme", d.depo_adi).read_bytes().startswith(b"%PDF-")
    did = _deneme(conn, [])
    denemeler.pdf_bagla(conn, did, 101, d.depo_adi)
    assert denemeler.pdf_dosyasi(conn, did, 101) == d.depo_adi
    assert denemeler.pdf_dosyasi(conn, did, 999) is None


def test_yorum_yaz_oku(conn):
    did = _deneme(conn, [])
    denemeler.yorum_yaz(conn, did, "11-A", "ilk")
    denemeler.yorum_yaz(conn, did, "11-A", "güncel")
    denemeler.yorum_yaz(conn, did, "", "okul")
    assert denemeler.yorum_oku(conn, did, "11-A") == "güncel"
    assert denemeler.yorum_oku(conn, did, "") == "okul"
    assert denemeler.yorum_oku(conn, did, "9-Z") == ""


def test_yukle_pdf_yolunu_baglar_ve_yenisiyle_degistirir(conn, ornek, tmp_path):
    pdf1 = tmp_path / "a.pdf"
    pdf1.write_bytes(b"%PDF-1.4 BIR")
    satir = {"okul_no": 101, "ad_soyad": "Ali Veli", "sinif": "9-A", "veri": {}, "pdf_yol": str(pdf1)}
    denemeler.yukle(conn, {"ad": "P", "ogrenciler": [satir]})
    did = conn.execute("SELECT id FROM deneme WHERE ad = 'P'").fetchone()[0]
    eski = denemeler.pdf_dosyasi(conn, did, 101)
    assert dosyalar.yol("deneme", eski).read_bytes() == b"%PDF-1.4 BIR"
    pdf1.write_bytes(b"%PDF-1.4 IKI")
    denemeler.yukle(conn, {"ad": "P", "ogrenciler": [satir]})
    yeni = denemeler.pdf_dosyasi(conn, did, 101)
    assert yeni != eski and dosyalar.yol("deneme", yeni).read_bytes() == b"%PDF-1.4 IKI"
    assert not dosyalar.yol("deneme", eski).exists()


def test_yukle_kuru_pdf_yazmaz(conn, ornek, tmp_path):
    pdf1 = tmp_path / "a.pdf"
    pdf1.write_bytes(b"%PDF-1.4 BIR")
    satir = {"okul_no": 101, "ad_soyad": "Ali Veli", "sinif": "9-A", "veri": {}, "pdf_yol": str(pdf1)}
    denemeler.yukle(conn, {"ad": "P", "ogrenciler": [satir]}, kuru=True)
    assert not (db.AYAR.dosya_dizini / "deneme").exists()


def test_siralama_bozuk_veri_none():
    assert denemeler._siralama({"sube": [1]}) is None
    assert denemeler._siralama(None) is None
    assert denemeler._siralama({"sube": [3, 7], "kurum": [6, 22], "genel": [5045, 9889], "yuzdelik": 51.02})["genel"] == [5045, 9889]
