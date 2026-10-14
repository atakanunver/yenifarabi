import duyurular
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rotalar import pano


def _istemci(host):
    app = FastAPI()
    app.include_router(pano.router)
    return TestClient(app, client=(host, 5555))


def test_lan_okul_duyurusu_doner(conn, ornek, saat):
    duyurular.duyuru_ekle(conn, ornek["yonetici"], "Okul", "x", "okul")
    duyurular.duyuru_ekle(conn, ornek["yonetici"], "9A", "x", "sinif", "9-A")
    r = _istemci("192.168.23.254").get("/api/pano")
    assert r.status_code == 200
    assert [d["baslik"] for d in r.json()["duyurular"]] == ["Okul"]


def test_tunel_ve_dis_ip_404(conn, ornek, saat):
    assert _istemci("192.168.23.254").get("/api/pano", headers={"cf-ray": "1"}).status_code == 404
    assert _istemci("8.8.8.8").get("/api/pano").status_code == 404
