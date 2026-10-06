"""server/kazanim.py — haftalık yıllık plan kazanımı, dosya-tabanlı ağsız test."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import auth  # noqa: E402
import kazanim as kz  # noqa: E402

# 2026-10-05 pazartesi; hafta 4 = 05.10-11.10, hafta 5 tatil (planda yok)
SALI = "2026-10-06"
TATIL = "2026-12-01"

PROGRAM = {"siniflar": {"12-A": {"sali": {"1": "matematik", "5": "hedef fizik"}}}}
PLAN = {
    "haftalar": {"4": "2026-10-05"},
    "kazanimlar": {"12": {
        "matematik": {"4": "12.1.2.2. Birinci kazanım\n12.1.2.3.  İkinci   kazanım\n"},
        "hedef fizik": {"4": "FİZ.12.1. Hedef kazanımı"},
    }},
}


@pytest.fixture
def veri(monkeypatch, tmp_path):
    (tmp_path / "ders_programi.json").write_text(json.dumps(PROGRAM), encoding="utf-8")
    (tmp_path / "kazanimlar.json").write_text(json.dumps(PLAN), encoding="utf-8")
    monkeypatch.setattr(kz, "VERI_DIR", tmp_path)
    kz._ONBELLEK.clear()
    return tmp_path


@pytest.fixture
def istemci(veri):
    app = FastAPI()
    app.include_router(kz.router)
    app.dependency_overrides[auth.dogrula_tahta] = lambda: None
    return TestClient(app)


def _al(c, derslik="12-A", ders_no=1, tarih=SALI):
    return c.get("/api/egitim/kazanim",
                 params={"derslik": derslik, "ders_no": ders_no, "tarih": tarih})


def test_normal_iki_kazanim(istemci):
    r = _al(istemci)
    assert r.status_code == 200
    assert r.json() == {
        "durum": "tamam", "ders": "matematik", "hafta": 4,
        "kazanimlar": ["12.1.2.2. Birinci kazanım", "12.1.2.3. İkinci kazanım"],
    }


def test_hedef_ders_adi(istemci):
    j = _al(istemci, ders_no=5).json()
    assert j["durum"] == "tamam" and j["ders"] == "hedef fizik"
    assert j["kazanimlar"] == ["FİZ.12.1. Hedef kazanımı"]


def test_bilinmeyen_derslik_yok(istemci):
    j = _al(istemci, derslik="fenlab").json()
    assert j["durum"] == "yok" and j["ders"] is None


def test_bos_ders_yok(istemci):
    assert _al(istemci, ders_no=7).json()["durum"] == "yok"


def test_tatil_haftasi_yok(istemci):
    j = _al(istemci, tarih=TATIL).json()
    assert j == {"durum": "yok", "ders": "matematik", "hafta": None}


def test_hafta_sonu_yok(istemci):
    assert _al(istemci, tarih="2026-10-10").json()["durum"] == "yok"


def test_bozuk_dosya_yok(istemci, veri):
    (veri / "kazanimlar.json").write_text("{bozuk", encoding="utf-8")
    kz._ONBELLEK.clear()
    assert _al(istemci).json() == {"durum": "yok"}


def test_eksik_dosya_yok(istemci, veri):
    (veri / "ders_programi.json").unlink()
    kz._ONBELLEK.clear()
    assert _al(istemci).json() == {"durum": "yok"}


def test_mtime_degisince_yeniden_okur(istemci, veri):
    assert _al(istemci).json()["durum"] == "tamam"
    yeni = json.loads(json.dumps(PLAN))
    yeni["kazanimlar"]["12"]["matematik"]["4"] = "Yeni"
    yol = veri / "kazanimlar.json"
    yol.write_text(json.dumps(yeni), encoding="utf-8")
    import os
    st = yol.stat()
    os.utime(yol, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert _al(istemci).json()["kazanimlar"] == ["Yeni"]


@pytest.mark.parametrize("derslik,ders_no", [("../x", 1), ("12 A", 1), ("12-A", 0), ("12-A", 13)])
def test_gecersiz_girdi_422(istemci, derslik, ders_no):
    assert _al(istemci, derslik=derslik, ders_no=ders_no).status_code == 422


def test_auth_gerekli(veri, monkeypatch):
    monkeypatch.setenv("FARABI_AUTH_REQUIRED", "1")
    monkeypatch.setattr(auth, "_board_keys", lambda: {"12-A": "gizli"})
    app = FastAPI()
    app.include_router(kz.router)
    c = TestClient(app)
    assert _al(c).status_code == 401
    r = c.get("/api/egitim/kazanim", params={"derslik": "12-A", "ders_no": 1, "tarih": SALI},
              headers={auth.HEADER_ADI: "gizli"})
    assert r.status_code == 200
