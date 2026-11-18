"""PDF gönderirken soru havuzuna katkı: varsayılan Evet, onay, uygunluk, hata durumunda PDF bozulmaz."""

import pytest
from test_web_belge_sinav import giris, istemci  # noqa: F401

PDF = b"%PDF-1.4\n" + b"x" * 200


@pytest.fixture
def hoca(request, conn, ornek):
    c = request.getfixturevalue("istemci")
    # ornek öğretmeni: 9-A matematik. Havuzda karşılığı olmayan ders + 12. sınıf ekle.
    conn.executemany(
        "INSERT INTO ogretmen_gorev (ogretmen_id, sinif, ders) VALUES (?, ?, ?)",
        [(ornek["ogretmen"], "9-A", "beden eğitimi"), (ornek["ogretmen"], "12-A", "matematik")],
    )
    conn.commit()
    return c, giris(c, "hoca", "hoca-sifre")


def _gonder(c, csrf, secim="9-A|matematik", **alanlar):
    veri = {"csrf": csrf, "secim": secim, "baslik": "Tarama"}
    veri.update(alanlar)
    return c.post("/ogretmen/pdf", data=veri, files={"dosya": ("s.pdf", PDF, "application/pdf")}, follow_redirects=False)


def _sayilar(conn):
    return (
        conn.execute("SELECT count(*) FROM sinif_pdf").fetchone()[0],
        conn.execute("SELECT count(*) FROM soru_katki").fetchone()[0],
    )


def test_evet_ve_onay_katki_olusur(hoca, conn):
    c, csrf = hoca
    r = _gonder(c, csrf, havuza="evet", havuz_onay="1", cevap="1-A 2-C 3-B")
    assert r.status_code == 303
    assert r.headers["location"].endswith("/odev?havuz=sirada")
    assert _sayilar(conn) == (1, 1)
    kt = conn.execute("SELECT * FROM soru_katki").fetchone()
    assert (kt["sinif"], kt["ders"], kt["cevap"], kt["durum"]) == (9, "matematik", "ACB", "bekliyor")
    assert conn.execute("SELECT count(*) FROM soru_katki WHERE baslik = 'Tarama'").fetchone()[0] == 1
    sayfa = c.get(r.headers["location"])
    assert sayfa.status_code == 200 and "soru havuzu kuyruğuna alındı" in sayfa.text


def test_hayir_veya_alan_yok_katki_olusmaz(hoca, conn):
    c, csrf = hoca
    assert _gonder(c, csrf, havuza="hayir", havuz_onay="1").headers["location"].endswith("/odev")
    assert _gonder(c, csrf).status_code == 303
    assert _sayilar(conn) == (2, 0)


def test_onaysiz_evet_pdf_var_katki_yok_uyari(hoca, conn):
    c, csrf = hoca
    r = _gonder(c, csrf, havuza="evet", cevap="ABC")
    assert r.status_code == 303 and r.headers["location"].endswith("?havuz=onaysiz")
    assert _sayilar(conn) == (1, 0)
    assert "izin onayı işaretlenmediği" in c.get(r.headers["location"]).text


@pytest.mark.parametrize("secim", ["9-A|beden eğitimi", "12-A|matematik"])
def test_uygun_olmayan_ders_katki_yok(hoca, conn, secim):
    c, csrf = hoca
    r = _gonder(c, csrf, secim, havuza="evet", havuz_onay="1")
    assert r.status_code == 303 and r.headers["location"].endswith("?havuz=uygunsuz")
    assert _sayilar(conn) == (1, 0)
    assert "soru havuzu yok" in c.get(r.headers["location"]).text


def test_bozuk_cevap_anahtari_pdf_var_katki_yok(hoca, conn):
    c, csrf = hoca
    r = _gonder(c, csrf, havuza="evet", havuz_onay="1", cevap="1-A 3-B")
    assert r.status_code == 303 and r.headers["location"].endswith("?havuz=cevap")
    assert _sayilar(conn) == (1, 0)
    assert "cevap anahtarı okunamadığı" in c.get(r.headers["location"]).text


def test_bilinmeyen_havuz_kodu_metin_yansitmaz(hoca, conn):
    c, csrf = hoca
    r = _gonder(c, csrf, havuza="hayir")
    sayfa = c.get(r.headers["location"] + "?havuz=<b>x</b>")
    assert sayfa.status_code == 200 and "<b>x</b>" not in sayfa.text


def test_form_uygun_secimleri_gosterir(hoca):
    c, _ = hoca
    t = c.get("/ogretmen/pdf").text
    assert 'name="havuza" value="evet" checked' in t and 'name="havuz_onay"' in t
    assert "9-A · matematik" in t and "12-A · matematik" not in t.split("Havuza uygun seçimler:")[1].split("</p>")[0]


def test_eski_soru_uret_410_surer(hoca, conn):
    c, csrf = hoca
    assert _gonder(c, csrf, soru_uret="1", havuza="evet", havuz_onay="1").status_code == 410
    assert _sayilar(conn) == (0, 0)
