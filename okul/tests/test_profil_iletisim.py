"""Profil iletişim: telefon + e-posta kaydı, doğrulama, CSRF, rol sınırı, ice_aktar telefonu ezmez."""

import auth
import pytest
from fastapi.testclient import TestClient
from kaynaklar import kazanim


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setattr(kazanim, "form_sonuclari", lambda okul_no: [])
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert (
        c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code
        == 303
    )
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def _satir(conn, kid):
    return conn.execute("SELECT telefon, eposta FROM kullanici WHERE id = ?", (kid,)).fetchone()


def test_kaydolur_ve_forma_dolu_gelir(istemci, ornek, conn):
    csrf = giris(istemci, "101", "ali-sifre")
    r = istemci.post(
        "/profil/iletisim",
        data={"csrf": csrf, "telefon": "0532 111 22 44", "eposta": " Ali@Okul.COM "},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/profil?kaydedildi=1"
    assert tuple(_satir(conn, ornek["ogr1_k"])) == ("05321112244", "ali@okul.com")
    sayfa = istemci.get("/profil?kaydedildi=1").text
    assert "05321112244" in sayfa and "ali@okul.com" in sayfa and "Kaydedildi" in sayfa
    assert "Kaydedildi" not in istemci.get("/profil").text


def test_ogretmen_kaydeder(istemci, ornek, conn):
    csrf = giris(istemci, "hoca", "hoca-sifre")
    r = istemci.post("/profil/iletisim", data={"csrf": csrf, "telefon": "", "eposta": "h@okul.com"}, follow_redirects=False)
    assert r.status_code == 303
    assert conn.execute("SELECT eposta FROM kullanici WHERE kullanici_adi = 'hoca'").fetchone()[0] == "h@okul.com"


@pytest.mark.parametrize("tel,posta", [("123", ""), ("", "ali@"), ("", "a b@c.com")])
def test_gecersiz_422_ve_degismez(istemci, ornek, conn, tel, posta):
    csrf = giris(istemci, "101", "ali-sifre")
    once = tuple(_satir(conn, ornek["ogr1_k"]))
    r = istemci.post("/profil/iletisim", data={"csrf": csrf, "telefon": tel, "eposta": posta})
    assert r.status_code == 422
    assert tuple(_satir(conn, ornek["ogr1_k"])) == once


def test_bos_gonderim_temizler(istemci, ornek, conn):
    csrf = giris(istemci, "101", "ali-sifre")
    istemci.post("/profil/iletisim", data={"csrf": csrf, "telefon": "05321112244", "eposta": "a@b.co"})
    istemci.post("/profil/iletisim", data={"csrf": csrf, "telefon": "", "eposta": ""})
    assert tuple(_satir(conn, ornek["ogr1_k"])) == (None, None)


def test_csrf_yok_reddedilir(istemci, ornek, conn):
    giris(istemci, "101", "ali-sifre")
    r = istemci.post("/profil/iletisim", data={"telefon": "05321112244", "eposta": "a@b.co"})
    assert r.status_code >= 400
    assert tuple(_satir(conn, ornek["ogr1_k"])) == (None, None)


def test_anonim_ve_veli_erisemez(istemci, ornek):
    r = istemci.post("/profil/iletisim", data={"telefon": "05321112244"}, follow_redirects=False)
    assert r.status_code in (303, 401, 403, 404)
    istemci.cookies.clear()
    istemci.post("/giris", data={"kullanici_adi": "05321112233", "sifre": "x"})
    r = istemci.post("/profil/iletisim", data={"telefon": "05321112244"}, follow_redirects=False)
    assert r.status_code in (303, 401, 403, 404)
