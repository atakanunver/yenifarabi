"""Beklenmeyen sunucu hatasında ham 'Internal Server Error' yerine 'Ş.M.U.A.L Bakım Yapılıyor ...' sayfası (503)."""

import pytest
from fastapi.testclient import TestClient
from rotalar import ortak


@pytest.fixture
def istemci():
    from app import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _patlat(monkeypatch):
    def patla(*a, **k):
        raise RuntimeError("test hatası")

    monkeypatch.setattr(ortak, "kazanim_ozeti", patla)


def test_beklenmeyen_hata_bakim_sayfasi(istemci, ornek, monkeypatch):
    istemci.post("/giris", data={"kullanici_adi": "101", "sifre": "ali-sifre"})
    _patlat(monkeypatch)
    r = istemci.get("/ogrenci")
    assert r.status_code == 503
    assert "Ş.M.U.A.L Bakım Yapılıyor ..." in r.text and "Internal Server Error" not in r.text
    assert r.headers["cache-control"] == "no-store" and r.headers["retry-after"] == "30"
    assert 'http-equiv="refresh"' in r.text  # otomatik yenilenir


def test_json_istekte_json_bakim_mesaji(istemci, ornek, monkeypatch):
    istemci.post("/giris", data={"kullanici_adi": "101", "sifre": "ali-sifre"})
    _patlat(monkeypatch)
    r = istemci.get("/ogrenci", headers={"Accept": "application/json"})
    assert r.status_code == 503 and r.json() == {"mesaj": "Ş.M.U.A.L Bakım Yapılıyor ..."}


def test_bilinen_hatalar_degismedi(istemci, ornek):
    assert istemci.get("/yok-boyle-bir-sayfa").status_code == 404
    istemci.post("/giris", data={"kullanici_adi": "101", "sifre": "ali-sifre"})
    assert istemci.get("/yonetici").status_code == 404  # yetkisiz: eski 404 davranışı
    assert "Bakım" not in istemci.get("/yonetici").text
