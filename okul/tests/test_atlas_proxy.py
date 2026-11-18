"""Farabi Atlas portal içinde (iframe): /kure ve /api/atlas yalnız öğretmen/yönetici için :8099'a proxy'lenir."""

import auth
import httpx
import pytest
from fastapi.testclient import TestClient
from rotalar import atlas


@pytest.fixture
def istemci(ornek, monkeypatch):
    cagrilar = []

    def sahte(yontem, url, icerik, basliklar):
        cagrilar.append({"yontem": yontem, "url": url, "icerik": icerik, "basliklar": basliklar})
        if basliklar.get("range"):
            return httpx.Response(206, content=b"ab", headers={"content-type": "application/octet-stream", "content-range": "bytes 0-1/10", "accept-ranges": "bytes"})
        return httpx.Response(200, content=b"<html>atlas</html>", headers={"content-type": "text/html; charset=utf-8", "cache-control": "max-age=60", "set-cookie": "x=1"})

    monkeypatch.setattr(atlas, "_ilet", sahte)
    from app import app

    with TestClient(app) as c:
        c.cagrilar = cagrilar
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def test_girissiz_giris_sayfasina(istemci):
    r = istemci.get("/kure/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/giris"
    assert istemci.cagrilar == []


def test_ogrenci_ogretmen_sayfasi_404(istemci):
    giris(istemci, "101", "ali-sifre")
    assert istemci.get("/ogretmen/atlas").status_code == 404
    assert istemci.cagrilar == []


def test_ogretmen_proxy_ve_cerceve(istemci):
    giris(istemci, "hoca", "hoca-sifre")
    r = istemci.get("/kure/data/catalog.json?v=1", headers={"x-forwarded-for": "1.2.3.4"})
    assert r.status_code == 200 and r.text == "<html>atlas</html>"
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    assert r.headers["cache-control"] == "max-age=60"
    assert "set-cookie" not in r.headers or "x=1" not in r.headers["set-cookie"]
    c = istemci.cagrilar[-1]
    assert c["url"] == "http://127.0.0.1:8099/kure/data/catalog.json?v=1"
    assert "cookie" not in c["basliklar"] and "x-forwarded-for" not in c["basliklar"]
    sayfa = istemci.get("/ogretmen/atlas")
    assert sayfa.status_code == 200 and 'src="/kure/"' in sayfa.text
    assert sayfa.headers["x-frame-options"] == "DENY"


def test_range_iletilir(istemci):
    giris(istemci, "hoca", "hoca-sifre")
    r = istemci.get("/kure/data/world-lite.pmtiles", headers={"range": "bytes=0-1"})
    assert r.status_code == 206 and r.content == b"ab"
    assert r.headers["content-range"] == "bytes 0-1/10"
    assert istemci.cagrilar[-1]["basliklar"]["range"] == "bytes=0-1"


def test_api_post_govdesi_aynen(istemci):
    giris(istemci, "hoca", "hoca-sifre")
    istemci.post("/api/atlas/sessions", data={"csrf": "atlas-token", "className": "Sınıf etkinliği"})
    c = istemci.cagrilar[-1]
    assert c["yontem"] == "POST" and c["url"] == "http://127.0.0.1:8099/api/atlas/sessions"
    assert b"csrf=atlas-token" in c["icerik"]
    assert c["basliklar"]["content-type"].startswith("application/x-www-form-urlencoded")


def test_egik_cizgisiz_yonlendirme(istemci):
    giris(istemci, "hoca", "hoca-sifre")
    r = istemci.get("/kure", follow_redirects=False)
    assert r.status_code in (301, 307) and r.headers["location"] == "/kure/"


def test_atlas_kapali_502(istemci, monkeypatch):
    def hata(*_a):
        raise httpx.ConnectError("yok")

    monkeypatch.setattr(atlas, "_ilet", hata)
    giris(istemci, "hoca", "hoca-sifre")
    r = istemci.get("/kure/")
    assert r.status_code == 502 and "Atlas" in r.text


def test_onbellek_basligi(istemci, monkeypatch):
    monkeypatch.setattr(atlas, "_ilet", lambda *_a: httpx.Response(200, content=b"x", headers={"content-type": "text/javascript", "etag": '"e1"'}))
    giris(istemci, "hoca", "hoca-sifre")
    assert istemci.get("/kure/assets/index-abc.js").headers["cache-control"] == "public, max-age=31536000, immutable"
    r = istemci.get("/kure/data/catalog.json")
    assert r.headers["cache-control"] == "no-cache" and r.headers["etag"] == '"e1"'
    assert istemci.get("/api/atlas/context").headers["cache-control"] == "no-store"


OGRENCI_YASAK = [
    ("GET", "/api/atlas/sessions"),
    ("GET", "/api/atlas/sessions/abc"),
    ("POST", "/api/atlas/sessions"),
    ("POST", "/api/atlas/sessions/abc/action"),
    ("POST", "/api/atlas/context"),
    ("GET", "/api/atlas/wiki/TR-06/../../sessions"),
    ("GET", "/api/atlas/wiki/%2e%2e/sessions"),
    ("GET", "/api/atlas/wiki/TR-06/x"),
    ("GET", "/api/atlas/contextx"),
    ("GET", "/kure/%2e%2e/api/atlas/sessions"),
    ("GET", "/kure/../api/atlas/sessions"),
]


def test_ogrenci_kesif_modu(istemci, monkeypatch):
    govde = '{"teacher":"Tahta modu","classes":["Sınıf etkinliği"],"csrf":"t","demo":false,"independent":true}'.encode()

    def sahte(yontem, url, icerik, basliklar):
        istemci.cagrilar.append({"url": url, "yontem": yontem})
        return httpx.Response(200, content=govde, headers={"content-type": "application/json"})

    monkeypatch.setattr(atlas, "_ilet", sahte)
    giris(istemci, "101", "ali-sifre")
    sayfa = istemci.get("/ogrenci/atlas")
    assert sayfa.status_code == 200 and 'src="/kure/"' in sayfa.text and "sınıf oyunları tahtada oynanır" in sayfa.text
    assert istemci.get("/kure/data/catalog.json").status_code == 200
    assert istemci.get("/kure", follow_redirects=False).status_code == 307
    r = istemci.get("/api/atlas/context")
    assert r.status_code == 200 and r.json()["classes"] == [] and r.json()["teacher"] == "Keşif modu"
    assert istemci.get("/api/atlas/wiki/TR-06").status_code == 200
    assert [c["url"] for c in istemci.cagrilar] == [
        "http://127.0.0.1:8099/kure/data/catalog.json",
        "http://127.0.0.1:8099/api/atlas/context",
        "http://127.0.0.1:8099/api/atlas/wiki/TR-06",
    ]


@pytest.mark.parametrize(("yontem", "yol"), OGRENCI_YASAK)
def test_ogrenci_oturum_uclari_404_iletilmez(istemci, yontem, yol):
    csrf = giris(istemci, "101", "ali-sifre")
    r = istemci.request(yontem, yol, data={"csrf": csrf, "className": "Sınıf etkinliği"} if yontem == "POST" else None)
    assert r.status_code == 404
    assert istemci.cagrilar == []


def test_ogretmen_oturum_uclari_iletilir(istemci):
    giris(istemci, "hoca", "hoca-sifre")
    uclar = (("GET", "/api/atlas/sessions"), ("GET", "/api/atlas/sessions/abc"), ("POST", "/api/atlas/sessions"), ("POST", "/api/atlas/sessions/abc/action"))
    for yontem, yol in uclar:
        assert istemci.request(yontem, yol).status_code == 200
    assert [c["url"] for c in istemci.cagrilar] == ["http://127.0.0.1:8099" + y for _m, y in uclar]
    assert istemci.get("/ogrenci/atlas").status_code == 404


def test_veli_hepsine_404(istemci, monkeypatch):
    from test_web import _veli_girisi

    _veli_girisi(istemci, monkeypatch)
    for yontem, yol in (("GET", "/ogrenci/atlas"), ("GET", "/ogretmen/atlas"), ("GET", "/kure/"), ("GET", "/api/atlas/context"), ("GET", "/api/atlas/wiki/TR-06"), ("GET", "/api/atlas/sessions"), ("POST", "/api/atlas/sessions")):
        assert istemci.request(yontem, yol).status_code == 404, yol
    assert istemci.cagrilar == []
