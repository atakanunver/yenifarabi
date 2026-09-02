"""
server/proxy.py — bulut LLM rölesinin sınırları ve hata sözleşmesi.

Ağ yok, gerçek sağlayıcı yok: `saglayicilar.metin_uret`/`gorsel_uret`
monkeypatch'lenir. Auth `FARABI_AUTH_REQUIRED=0` ile devre dışı bırakılır —
auth'un KENDİSİ test_auth.py'nin işi, burada test edilen şey proxy'nin
davranışı.

R-2 (docs/REFACTORING_PLAN.md): `gorsel_uret` yükleme boyutunu hiç
sınırlamıyordu; `dosya_isle` aynı sınıftan bir yüzey olmasına rağmen orada
YUKLEME_LIMIT_MB=60 vardı. Bu dosya o boşluğun kapandığını ve kapalı
kaldığını garanti eder.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# server/ modülleri paket değil, düz modül — sys.path bu yüzden import'tan
# ÖNCE ayarlanmalı (test_auth.py/test_icerik.py ile aynı desen).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import proxy
import saglayicilar


@pytest.fixture
def istemci(monkeypatch):
    """Auth kapalı, sağlayıcılar sahte bir TestClient.

    `main.app` yerine yalnızca proxy router'ı bağlanmış küçük bir app —
    main.app'i kurmak model yüklemesini de tetikleyebilir (lifespan),
    burada gereksiz."""
    from fastapi import FastAPI

    monkeypatch.setenv("FARABI_AUTH_REQUIRED", "0")
    app = FastAPI()
    app.include_router(proxy.router)
    return TestClient(app)


def _gorsel_cagrisini_sahtele(monkeypatch, sonuc="tamam"):
    """Gerçek buluta gitmeyi engeller; çağrıldıysa kaydeder."""
    cagrilar = []

    def _sahte(gorev, istem, veri, mime):
        cagrilar.append((gorev, istem, len(veri), mime))
        if isinstance(sonuc, Exception):
            raise sonuc
        return sonuc

    monkeypatch.setattr(saglayicilar, "gorsel_uret", _sahte)
    return cagrilar


class TestGorselBoyutSiniri:
    def test_sinir_altindaki_gorsel_saglayiciya_gider(self, istemci, monkeypatch):
        cagrilar = _gorsel_cagrisini_sahtele(monkeypatch, "Sayfada mitoz anlatılıyor.")
        y = istemci.post("/api/egitim/gorsel_uret",
                         data={"gorev": "gorsel", "istem": "Bu sayfada ne var?"},
                         files={"dosya": ("s.jpg", b"X" * 1024, "image/jpeg")})
        assert y.status_code == 200
        assert y.json()["status"] == "ok"
        assert y.json()["metin"] == "Sayfada mitoz anlatılıyor."
        assert len(cagrilar) == 1
        assert cagrilar[0][2] == 1024, "sağlayıcıya eksik/fazla bayt gitti"

    def test_sinir_ustundeki_gorsel_REDDEDILIR(self, istemci, monkeypatch):
        """R-2'nin asıl iddiası. SECURITY_ANALYSIS S-04: sınırsız yükleme
        farabi-api.service'i belleğe boğabilir; servis çökerse TÜM
        tahtaların içerik/RAG yolu düşer."""
        cagrilar = _gorsel_cagrisini_sahtele(monkeypatch)
        buyuk = b"X" * ((proxy.GORSEL_LIMIT_MB * 1024 * 1024) + 1024)
        y = istemci.post("/api/egitim/gorsel_uret",
                         data={"gorev": "gorsel", "istem": "soru"},
                         files={"dosya": ("buyuk.jpg", buyuk, "image/jpeg")})
        assert y.status_code == 200          # 500 DEĞİL — Kural 2 düşüş yolu
        assert y.json()["status"] == "hata"
        assert str(proxy.GORSEL_LIMIT_MB) in y.json()["hata"]
        assert cagrilar == [], "sınır aşıldığı hâlde bulut sağlayıcı çağrıldı"

    def test_sinir_dosya_py_ile_ayni(self):
        """İki yükleme yüzeyi aynı politikayı paylaşmalı; biri sıkı biri
        gevşek olursa saldırgan gevşek olanı seçer."""
        import dosya
        assert proxy.GORSEL_LIMIT_MB == dosya.YUKLEME_LIMIT_MB


class TestHataSozlesmesi:
    """Proxy hiçbir koşulda çıplak 500 dönmemeli: client Kural 2 gereği
    `status` alanına bakıp sessizce kısıtlayıcı bir metne düşüyor."""

    def test_saglayici_patlarsa_status_hata(self, istemci, monkeypatch):
        _gorsel_cagrisini_sahtele(monkeypatch, RuntimeError("tüm zincir öldü"))
        y = istemci.post("/api/egitim/gorsel_uret",
                         data={"gorev": "gorsel", "istem": "soru"},
                         files={"dosya": ("s.jpg", b"X" * 10, "image/jpeg")})
        assert y.status_code == 200
        assert y.json()["status"] == "hata"
        assert "tüm zincir öldü" in y.json()["hata"]

    def test_metin_uret_saglayici_patlarsa_status_hata(self, istemci, monkeypatch):
        def _patla(gorev, istem, sistem=None):
            raise RuntimeError("kota bitti")
        monkeypatch.setattr(saglayicilar, "metin_uret", _patla)
        y = istemci.post("/api/egitim/metin_uret",
                         json={"gorev": "belge_ozet", "istem": "özetle"})
        assert y.status_code == 200
        assert y.json()["status"] == "hata"

    def test_metin_uret_mutlu_yol(self, istemci, monkeypatch):
        monkeypatch.setattr(saglayicilar, "metin_uret",
                            lambda gorev, istem, sistem=None: "Özet.")
        y = istemci.post("/api/egitim/metin_uret",
                         json={"gorev": "belge_ozet", "istem": "özetle"})
        assert y.json()["status"] == "ok"
        assert y.json()["metin"] == "Özet."
        assert y.json()["request_id"]

    def test_istem_uzunluk_siniri_korunuyor(self, istemci, monkeypatch):
        """`istem` alanındaki max_length=200_000 pydantic doğrulaması —
        aşılırsa 422, sağlayıcıya hiç gidilmez."""
        cagrildi = []
        monkeypatch.setattr(saglayicilar, "metin_uret",
                            lambda *a, **k: cagrildi.append(1) or "x")
        y = istemci.post("/api/egitim/metin_uret",
                         json={"gorev": "belge_ozet", "istem": "A" * 200_001})
        assert y.status_code == 422
        assert cagrildi == []
