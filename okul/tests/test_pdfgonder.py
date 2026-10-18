"""PDF gönder + PDF'ten foto teslimli ödev: yükleme, yetki, teslim."""

import dosyalar
import odevler
import pytest
import sinifpdf
from ayarlar import AYAR

PDF = b"%PDF-1.4\n" + b"x" * 200
JPG = b"\xff\xd8\xff\xe0" + b"j" * 200


def _pdf(conn, ornek):
    k = conn.execute("SELECT * FROM kullanici WHERE id = ?", (ornek["ogretmen"],)).fetchone()
    return k, sinifpdf.gonder(conn, k, "9-A", "matematik", "Senaryo", "senaryo.pdf", PDF)


def _odev_satiri(conn, odev_id):
    return odevler.odev_getir(conn, odev_id)


def test_pdf_kaydi_ve_sahte_icerik(conn, ornek):
    k, pid = _pdf(conn, ornek)
    p = sinifpdf.pdf_getir(conn, pid)
    assert dosyalar.yol("pdf", p["depo_adi"]).exists()
    with pytest.raises(dosyalar.DosyaHatasi):
        sinifpdf.gonder(conn, k, "9-A", "matematik", "x", "x.pdf", b"MZ" + b"0" * 50)
    with pytest.raises(PermissionError):
        sinifpdf.gonder(conn, k, "9-B", "matematik", "x", "x.pdf", PDF)


def test_pdf_yetkisi(conn, ornek):
    k, pid = _pdf(conn, ornek)
    gor = lambda kid: sinifpdf.pdf_gorebilir(  # noqa: E731
        conn, conn.execute("SELECT * FROM kullanici WHERE id = ?", (kid,)).fetchone(), pid
    )
    assert gor(ornek["ogretmen"]) and gor(ornek["yonetici"])
    assert gor(ornek["ogr1_k"]) is not None
    assert gor(ornek["ogr2_k"]) is None
    assert gor(ornek["veli1"]) is None


def test_odev_ver_ve_foto(conn, ornek):
    k, pid = _pdf(conn, ornek)
    pdf = sinifpdf.pdf_getir(conn, pid)
    oid = sinifpdf.odev_ver(conn, k, pdf, "Senaryo çözümü", "", "2030-01-01T10:00", "12", "18")
    odev = _odev_satiri(conn, oid)
    assert "12-18" in odev["aciklama"]
    eki = sinifpdf.odev_eki(conn, oid)
    assert (eki["sayfa_bas"], eki["sayfa_bit"]) == (12, 18)
    sinifpdf.foto_yukle(conn, odev, ornek["ogr1"], JPG)
    t = odevler.teslim_getir(conn, oid, ornek["ogr1"])
    assert t["durum"] == "yapti"
    ilk = sinifpdf.foto_getir(conn, oid, ornek["ogr1"])["depo_adi"]
    sinifpdf.foto_yukle(conn, odev, ornek["ogr1"], JPG + b"2")
    yeni = sinifpdf.foto_getir(conn, oid, ornek["ogr1"])["depo_adi"]
    assert ilk != yeni
    assert not dosyalar.yol("odev_foto", ilk).exists()
    with pytest.raises(dosyalar.DosyaHatasi):
        sinifpdf.foto_yukle(conn, odev, ornek["ogr1"], b"%PDF-1.4 yok")


def test_foto_yetkisi_ve_silme(conn, ornek):
    k, pid = _pdf(conn, ornek)
    oid = sinifpdf.odev_ver(conn, k, sinifpdf.pdf_getir(conn, pid), "O", "", "2030-01-01T10:00", "", "")
    sinifpdf.foto_yukle(conn, odevler.odev_getir(conn, oid), ornek["ogr1"], JPG)
    kul = lambda kid: conn.execute("SELECT * FROM kullanici WHERE id = ?", (kid,)).fetchone()  # noqa: E731
    assert sinifpdf.foto_gorebilir(conn, kul(ornek["ogretmen"]), oid, ornek["ogr1"])
    assert sinifpdf.foto_gorebilir(conn, kul(ornek["ogr1_k"]), oid, ornek["ogr1"])
    assert sinifpdf.foto_gorebilir(conn, kul(ornek["ogr2_k"]), oid, ornek["ogr1"]) is None
    assert sinifpdf.foto_gorebilir(conn, kul(ornek["veli1"]), oid, ornek["ogr1"]) is None
    depo = sinifpdf.foto_getir(conn, oid, ornek["ogr1"])["depo_adi"]
    sinifpdf.odev_silinirken(conn, oid)
    assert not dosyalar.yol("odev_foto", depo).exists()
    assert AYAR.dosya_dizini.exists()


def test_sayfa_araligi():
    assert sinifpdf.sayfa_araligi("12", "18") == (12, 18)
    assert sinifpdf.sayfa_araligi("5", "") == (5, 5)
    assert sinifpdf.sayfa_araligi("", "") == (None, None)
    with pytest.raises(sinifpdf.PdfHatasi):
        sinifpdf.sayfa_araligi("9", "3")
    with pytest.raises(sinifpdf.PdfHatasi):
        sinifpdf.sayfa_araligi("a", "3")


# --- uçtan uca ---
from test_web_belge_sinav import giris, istemci, veli_giris  # noqa: E402,F401


def test_web_akis(istemci, conn, ornek):
    c = istemci
    csrf = giris(c, "hoca", "hoca-sifre")
    assert c.get("/ogretmen/pdf").status_code == 200
    r = c.post("/ogretmen/pdf", data={"csrf": csrf, "secim": "9-A|matematik", "baslik": "Senaryo"},
               files={"dosya": ("s.pdf", PDF, "application/pdf")}, follow_redirects=False)
    assert r.status_code == 303
    pid = int(r.headers["location"].split("/")[3])
    bozuk = c.post("/ogretmen/pdf", data={"csrf": csrf, "secim": "9-A|matematik"},
                   files={"dosya": ("s.pdf", b"yok", "application/pdf")})
    assert bozuk.status_code == 422
    assert c.post("/ogretmen/pdf", data={"csrf": csrf, "secim": "9-B|matematik"},
                  files={"dosya": ("s.pdf", PDF, "application/pdf")}).status_code == 404
    r = c.post(f"/ogretmen/pdf/{pid}/odev", data={"csrf": csrf, "baslik": "Ödev", "teslim": "2030-01-01T10:00",
               "sayfa_bas": "12", "sayfa_bit": "18"}, follow_redirects=False)
    assert r.status_code == 303
    oid = int(r.headers["location"].rsplit("/", 1)[1])

    csrf = giris(c, "101", "ali-sifre")
    assert c.get(f"/pdf/{pid}").status_code == 200
    assert "Senaryo" in c.get("/ogrenci/dosyalar").text
    assert "12-18" in c.get(f"/ogrenci/odev/{oid}").text
    r = c.post(f"/ogrenci/odev/{oid}/foto", data={"csrf": csrf}, files={"dosya": ("c.jpg", JPG, "image/jpeg")},
               follow_redirects=False)
    assert r.status_code == 303
    assert c.get(f"/odev-foto/{oid}/{ornek['ogr1']}").status_code == 200
    assert c.post(f"/ogrenci/odev/{oid}/foto", data={"csrf": csrf},
                  files={"dosya": ("c.pdf", PDF, "application/pdf")}).status_code == 400

    csrf = giris(c, "201", "ayse-sifre")
    assert c.get(f"/pdf/{pid}").status_code == 404
    assert c.get(f"/odev-foto/{oid}/{ornek['ogr1']}").status_code == 404
    assert c.post(f"/ogrenci/odev/{oid}/foto", data={"csrf": csrf},
                  files={"dosya": ("c.jpg", JPG, "image/jpeg")}).status_code == 404

    veli_giris(c, conn, ornek["veli1"])
    assert c.get(f"/pdf/{pid}").status_code == 404
    assert c.get(f"/odev-foto/{oid}/{ornek['ogr1']}").status_code in (403, 404)

    csrf = giris(c, "hoca", "hoca-sifre")
    assert "Fotoğraf" in c.get(f"/ogretmen/odev/{oid}").text
    assert c.get(f"/odev-foto/{oid}/{ornek['ogr1']}").status_code == 200
    assert c.post(f"/ogretmen/odev/{oid}/sil", data={"csrf": csrf}, follow_redirects=False).status_code == 303
    assert c.get(f"/odev-foto/{oid}/{ornek['ogr1']}").status_code == 404
