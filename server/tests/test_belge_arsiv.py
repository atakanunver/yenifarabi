"""belge_arsiv.py — gerçek idari_yukle/bge-m3/DB'ye gitmez (rag_yukle yamalanır)."""

import base64

import auth
import belge_arsiv as ba
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ANAHTAR = "webui-test-anahtari"


@pytest.fixture
def ist(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "webui_anahtari", lambda: ANAHTAR)
    monkeypatch.setattr(ba, "KLASOR", tmp_path)
    yuklenen = []

    def sahte_yukle(yol):
        yuklenen.append(yol)
        return "yuklendi", 3, "Belge"

    monkeypatch.setattr(ba, "rag_yukle", sahte_yukle)
    app = FastAPI()
    app.include_router(ba.router)
    return TestClient(app), tmp_path, yuklenen


def _gonder(c, ad, veri, anahtar=ANAHTAR):
    return c.post(
        "/api/webui/belge-kaydet",
        headers={"X-Farabi-WebUI-Key": anahtar},
        json={"ad": ad, "icerik_b64": base64.b64encode(veri).decode()},
    )


def test_anahtarsiz_401(ist):
    c, _, _ = ist
    assert _gonder(c, "a.pdf", b"x", anahtar="yanlis").status_code == 401


def test_kaydeder_ve_yukler(ist):
    c, klasor, yuklenen = ist
    y = _gonder(c, "nöbet.pdf", b"%PDF-1").json()
    assert y == {
        "durum": "ok",
        "ad": "nöbet.pdf",
        "belge": "Belge",
        "arsiv": "kaydedildi",
        "rag": "yuklendi",
        "parca": 3,
    }
    assert (klasor / "nöbet.pdf").read_bytes() == b"%PDF-1" and yuklenen == [
        klasor / "nöbet.pdf"
    ]
    assert not list(klasor.glob(".*"))  # geçici dosya kalmaz


def test_ayni_icerik_baska_adla_ikinci_kopya_yazilmaz(ist):
    c, klasor, yuklenen = ist
    (klasor / "personel bilgi2026.xlsx").write_bytes(b"ayni")
    y = _gonder(c, "personel bilgi.xlsx", b"ayni").json()
    assert y["arsiv"] == "zaten_vardi" and y["ad"] == "personel bilgi2026.xlsx"
    assert sorted(p.name for p in klasor.iterdir()) == ["personel bilgi2026.xlsx"]


def test_ayni_ad_farkli_icerik_gunceller(ist):
    c, klasor, _ = ist
    (klasor / "plan.docx").write_bytes(b"eski")
    assert _gonder(c, "plan.docx", b"yeni").json()["arsiv"] == "guncellendi"
    assert (klasor / "plan.docx").read_bytes() == b"yeni"


@pytest.mark.parametrize("ad", ["../../etc/passwd.pdf", "/tmp/x.pdf", "..\\..\\y.pdf"])
def test_yol_bilesenleri_atilir(ist, ad):
    c, klasor, _ = ist
    y = _gonder(c, ad, b"%PDF").json()
    assert y["durum"] == "ok" and (klasor / y["ad"]).exists() and "/" not in y["ad"]


@pytest.mark.parametrize("ad", ["virus.exe", ".gizli.pdf", "notlar.txt"])
def test_desteklenmeyen_tur_kaydedilmez(ist, ad):
    c, klasor, yuklenen = ist
    assert _gonder(c, ad, b"x").json()["durum"] == "desteklenmiyor"
    assert not list(klasor.iterdir()) and not yuklenen


def test_bozuk_base64_400(ist):
    c, _, _ = ist
    r = c.post(
        "/api/webui/belge-kaydet",
        headers={"X-Farabi-WebUI-Key": ANAHTAR},
        json={"ad": "a.pdf", "icerik_b64": "%%%"},
    )
    assert r.status_code == 400


def test_rag_hatasi_bildirilir(ist, monkeypatch):
    c, _, _ = ist
    monkeypatch.setattr(ba, "rag_yukle", lambda yol: ("hata", None, "Belge"))
    y = _gonder(c, "a.pdf", b"%PDF").json()
    assert y["durum"] == "rag_hatasi" and y["arsiv"] == "kaydedildi"
