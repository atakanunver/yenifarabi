"""Dilek/istek/şikayet kutusu: rol yetkisi, CSRF, doğrulama, hız sınırı, durum, gizlilik, geri alma."""


import auth
import kutu
import pytest
from fastapi.testclient import TestClient


def _istemci():
    from app import app

    return TestClient(app)


def _kisi(conn, yeni_kullanici, rol, kadi):
    k = yeni_kullanici(conn, rol, kadi.title(), kadi, sifre="Parola123")
    if rol == "ogrenci":
        conn.execute(
            "INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (?, ?, '9-A', ?)", (k + 100, kadi.title(), k)
        )
        conn.commit()
    return k


def _oturum(c, conn, kid):
    c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, kid))


def _csrf(c, yol="/kutu"):
    return c.get(yol).text.split('name="csrf" value="')[1].split('"')[0]


def _gonder(c, tur="dilek", metin="Kantin geç açılıyor"):
    return c.post("/kutu/gonder", data={"csrf": _csrf(c), "tur": tur, "metin": metin}, follow_redirects=False)


@pytest.mark.parametrize("rol", ["ogrenci", "ogretmen"])
def test_ogrenci_ve_ogretmen_gonderir(conn, yeni_kullanici, rol):
    k = _kisi(conn, yeni_kullanici, rol, "g" + rol)
    with _istemci() as c:
        _oturum(c, conn, k)
        assert _gonder(c).status_code == 303
        assert "Kantin geç açılıyor" in c.get("/kutu").text and "Yeni" in c.get("/kutu").text
    assert conn.execute("SELECT COUNT(*) FROM kutu_kayit WHERE kullanici_id = ?", (k,)).fetchone()[0] == 1


@pytest.mark.parametrize("rol", ["veli", "yonetici"])
def test_veli_ve_yonetici_gonderemez(conn, yeni_kullanici, rol):
    k = _kisi(conn, yeni_kullanici, rol, "x" + rol)
    with _istemci() as c:
        _oturum(c, conn, k)
        assert c.get("/kutu").status_code == 404
        assert c.post("/kutu/gonder", data={"tur": "dilek", "metin": "x"}).status_code in (400, 404)
    assert conn.execute("SELECT COUNT(*) FROM kutu_kayit").fetchone()[0] == 0


@pytest.mark.parametrize("rol", ["ogrenci", "ogretmen", "veli"])
def test_yonetici_sayfasi_diger_roller_goremez(conn, yeni_kullanici, rol):
    k = _kisi(conn, yeni_kullanici, rol, "y" + rol)
    with _istemci() as c:
        _oturum(c, conn, k)
        assert c.get("/yonetici/kutu").status_code == 404
        assert c.post("/yonetici/kutu/1/durum", data={"durum": "okundu"}).status_code in (400, 404)


def test_girissiz_yonlendirir():
    with _istemci() as c:
        assert c.get("/kutu", follow_redirects=False).status_code == 303
        assert c.get("/yonetici/kutu", follow_redirects=False).status_code == 303


def test_csrf_zorunlu(conn, yeni_kullanici):
    k = _kisi(conn, yeni_kullanici, "ogrenci", "csrfli")
    with _istemci() as c:
        _oturum(c, conn, k)
        assert c.post("/kutu/gonder", data={"csrf": "yanlis", "tur": "dilek", "metin": "x"}).status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM kutu_kayit").fetchone()[0] == 0


def test_dogrulama(conn, yeni_kullanici):
    k = _kisi(conn, yeni_kullanici, "ogrenci", "dogrula")
    with _istemci() as c:
        _oturum(c, conn, k)
        assert _gonder(c, metin="   ").status_code == 400
        assert _gonder(c, metin="a" * (kutu.AZAMI_METIN + 1)).status_code == 400
        assert _gonder(c, tur="reklam").status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM kutu_kayit").fetchone()[0] == 0


def test_saatlik_hiz_siniri(conn, yeni_kullanici):
    k = _kisi(conn, yeni_kullanici, "ogretmen", "hizli")
    for i in range(kutu.SAAT_AZAMI):
        kutu.ekle(conn, k, "istek", f"m{i}")
    with pytest.raises(kutu.KutuHatasi) as e:
        kutu.ekle(conn, k, "istek", "fazla")
    assert e.value.kod == 429


def test_yonetici_adli_gorur_ve_durum_isaretler(conn, yeni_kullanici):
    ogr = _kisi(conn, yeni_kullanici, "ogrenci", "kimli")
    yon = _kisi(conn, yeni_kullanici, "yonetici", "mudur")
    kid = kutu.ekle(conn, ogr, "sikayet", "<b>Sınıf soğuk</b>")
    with _istemci() as c:
        _oturum(c, conn, yon)
        r = c.get("/yonetici/kutu")
        assert "Kimli" in r.text and "9-A" in r.text and "&lt;b&gt;Sınıf soğuk" in r.text  # ad+sınıf görünür, HTML kaçışlı
        assert c.get("/yonetici").text.count("1 yeni") == 1  # ana sayfa rozeti
        csrf = _csrf(c, "/yonetici/kutu")
        assert c.post(f"/yonetici/kutu/{kid}/durum", data={"csrf": csrf, "durum": "cozuldu"}, follow_redirects=False).status_code == 303
        assert c.post("/yonetici/kutu/999/durum", data={"csrf": csrf, "durum": "okundu"}).status_code == 404
        assert c.post(f"/yonetici/kutu/{kid}/durum", data={"csrf": csrf, "durum": "bozuk"}).status_code == 404
        assert "Sınıf soğuk" not in c.get("/yonetici/kutu?durum=yeni").text  # çözülen kayıt 'yeni' filtresinde yok
    assert conn.execute("SELECT durum FROM kutu_kayit WHERE id = ?", (kid,)).fetchone()[0] == "cozuldu"
    with _istemci() as c:
        _oturum(c, conn, ogr)
        assert "Çözüldü" in c.get("/kutu").text  # gönderen durumu görür


def test_baskasinin_kaydi_gorunmez(conn, yeni_kullanici):
    a = _kisi(conn, yeni_kullanici, "ogrenci", "ayse")
    b = _kisi(conn, yeni_kullanici, "ogrenci", "berk")
    kutu.ekle(conn, a, "dilek", "Ayşe'nin gizli dileği")
    with _istemci() as c:
        _oturum(c, conn, b)
        assert "gizli dileği" not in c.get("/kutu").text


def test_geri_al_tabloyu_siler(conn):
    from scripts import geri_al

    assert 14 in geri_al.GERI and "kutu_kayit" in geri_al.GERI[14]
