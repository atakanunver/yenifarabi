"""Kullanıcı başına tema: varsayılan, kaydetme, geçersiz kod, CSRF, izolasyon, veli."""

import auth
import db
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


def test_varsayilan_tema_defter(istemci, ornek):
    giris(istemci, "101", "ali-sifre")
    r = istemci.get("/profil")
    assert r.status_code == 200 and 'data-tema="defter"' in r.text
    assert "temalar.css" in r.text


def test_tema_kaydolur_ve_sayfalarda_gorunur(istemci, ornek, conn):
    csrf = giris(istemci, "101", "ali-sifre")
    r = istemci.post("/profil/tema", data={"csrf": csrf, "tema": "neon"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/profil"
    assert 'data-tema="neon"' in istemci.get("/profil").text
    assert 'data-tema="neon"' in istemci.get("/ogrenci").text
    assert conn.execute("SELECT tema FROM kullanici_tema WHERE kullanici_id = ?", (ornek["ogr1_k"],)).fetchone()[0] == "neon"
    # tekrar seçim güncellenir (UPSERT), ikinci satır oluşmaz
    istemci.post("/profil/tema", data={"csrf": csrf, "tema": "tahta"})
    assert conn.execute("SELECT COUNT(*) FROM kullanici_tema WHERE kullanici_id = ?", (ornek["ogr1_k"],)).fetchone()[0] == 1
    assert 'data-tema="tahta"' in istemci.get("/profil").text


def test_gecersiz_tema_422_ve_degismez(istemci, ornek, conn):
    csrf = giris(istemci, "101", "ali-sifre")
    istemci.post("/profil/tema", data={"csrf": csrf, "tema": "harita"})
    for kotu in ("yok", "", "defter<script>", "../x"):
        r = istemci.post("/profil/tema", data={"csrf": csrf, "tema": kotu})
        assert r.status_code == 422
    assert conn.execute("SELECT tema FROM kullanici_tema WHERE kullanici_id = ?", (ornek["ogr1_k"],)).fetchone()[0] == "harita"


def test_csrf_olmadan_reddedilir(istemci, ornek, conn):
    giris(istemci, "101", "ali-sifre")
    assert istemci.post("/profil/tema", data={"tema": "neon"}).status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM kullanici_tema").fetchone()[0] == 0


def test_kullanicilar_birbirini_etkilemez(istemci, ornek):
    csrf = giris(istemci, "101", "ali-sifre")
    istemci.post("/profil/tema", data={"csrf": csrf, "tema": "gokyuzu"})
    giris(istemci, "201", "ayse-sifre")
    assert 'data-tema="defter"' in istemci.get("/profil").text


def test_giris_yapmamis_tema_secemez(istemci, ornek):
    r = istemci.post("/profil/tema", data={"tema": "neon"}, follow_redirects=False)
    assert r.status_code in (303, 400, 401, 404)
    assert 'data-tema="defter"' in istemci.get("/giris").text


def test_veli_orman_temasinda_ve_secemez(istemci, ornek, conn):
    token = auth.oturum_ac(conn, ornek["veli1"])
    istemci.cookies.clear()
    istemci.cookies.set(auth.COOKIE_ADI, token)
    csrf = auth.csrf_token(token)
    assert istemci.post("/profil/tema", data={"csrf": csrf, "tema": "neon"}).status_code == 404
    assert 'data-tema="harita"' in istemci.get("/veli").text  # veli orman haritası temasında sabit


def test_tema_listesi_tutarli():
    import pathlib

    import tema

    assert tema.VARSAYILAN in tema.TEMALAR and tema.gecerli("neon") and not tema.gecerli("x")
    css = pathlib.Path("static/temalar.css").read_text(encoding="utf-8")
    for kod in tema.TEMALAR:
        if kod != tema.VARSAYILAN:
            assert f'data-tema="{kod}"' in css


def test_gocu_27_ve_geri_alma_betigi():
    assert len(db.GOCLER) >= 27
    import importlib.util
    import pathlib

    s = importlib.util.spec_from_file_location("geri_al", pathlib.Path("scripts/geri_al.py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    assert "kullanici_tema" in m.GERI[27]
