"""server/ders_plani.py — kitap sayfalarından 40 dk ders planı.

Ağ yok, gerçek sağlayıcı yok: `saglayicilar.metin_uret` monkeypatch'lenir.
Kitap indeksi/metni tmp_path'te sahte (test_icerik.py::TestPdfSayfaMetni
deseni). `icerik.SAYFA_ONBELLEK` ve `ders_plani.PLAN_ONBELLEK` de tmp_path'e
yönlendirilir — gerçek /mnt/farabi-data önbelleğine yazılmamalı."""

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ders_plani as dp  # noqa: E402
import icerik as ic  # noqa: E402
import saglayicilar  # noqa: E402

SAYFALAR = {
    "20": {"metin": "Sabit hızlı hareket: eşit zamanda eşit yer değiştirme. Hız 12 m/s.", "supheli": 0},
    "21": {"metin": "Sabit hızlı harekette ivme sıfırdır. x-t grafiği doğrudur.", "supheli": 0},
    "22": {"metin": "Örnek: 12 m / 4 s = 3 m/s. Sabit hızlı hareket.", "supheli": 1},
}


@pytest.fixture
def kitap(tmp_path, monkeypatch):
    (tmp_path / "kitaplar.json").write_text(json.dumps({"kitaplar": [{
        "dosya": "fizik-10.pdf", "ders": "fizik", "sinif": 10,
        "yol": str(tmp_path / "fizik-10.pdf"),
        "bolumler": [{"no": 1, "tur": "Ünite", "ad": "KUVVET VE HAREKET",
                      "ilk_sayfa": 20, "son_sayfa": 40, "yontem": "metin"}],
    }]}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "fizik-10.pdf").write_bytes(b"")
    (tmp_path / "fizik-10.json").write_text(json.dumps({"sayfalar": SAYFALAR}, ensure_ascii=False),
                                            encoding="utf-8")
    (tmp_path / "eslemeler").mkdir()
    monkeypatch.setattr(ic, "KITAP_PATH", tmp_path / "kitaplar.json")
    monkeypatch.setattr(ic, "METIN_DIZINI", tmp_path)
    monkeypatch.setattr(ic, "ESLEME_DIR", tmp_path / "eslemeler")
    monkeypatch.setattr(ic, "SAYFA_ONBELLEK", tmp_path / "_sayfa_secimi.json")
    monkeypatch.setattr(dp, "PLAN_ONBELLEK", tmp_path / "ders_plani")
    ic._METIN_ONBELLEK.clear()
    return tmp_path


@pytest.fixture
def llm(monkeypatch):
    cagrilar = []
    davranis = {"sonuc": "1. KAVRAMLAR\nHız 12 m/s (PDF s. 20)\n3. AKIŞ\n[ÜRETİLMİŞ ÖRNEK] 77 m"}

    def _sahte(gorev, istem, sistem=None):
        cagrilar.append((gorev, istem, sistem))
        if isinstance(davranis["sonuc"], Exception):
            raise davranis["sonuc"]
        return davranis["sonuc"]

    monkeypatch.setattr(saglayicilar, "metin_uret", _sahte)
    return cagrilar, davranis


def _istek(**kw):
    varsayilan = dict(ders="fizik", sinif="10", konu="Sabit Hızlı Hareket", tema="Kuvvet ve Hareket")
    varsayilan.update(kw)
    return dp.PlanIstek(**varsayilan)


class TestDersPlaniUret:
    def test_ok_kaynak_istemde_gorev_ders_plani(self, kitap, llm):
        cagrilar, _ = llm
        y = dp.ders_plani_uret(_istek())
        assert y.status == "ok"
        assert y.kitap == "fizik-10.pdf"
        assert y.sayfalar and all(20 <= s <= 40 for s in y.sayfalar)
        assert y.supheli_sembol == 1
        gorev, istem, sistem = cagrilar[0]
        assert gorev == "ders_plani"
        assert "eşit zamanda eşit yer değiştirme" in istem
        assert "[ÜRETİLMİŞ ÖRNEK]" in sistem

    def test_tema_eslesmezse_bulunamadi_ve_llm_cagrilmaz(self, kitap, llm):
        cagrilar, _ = llm
        y = dp.ders_plani_uret(_istek(tema=""))  # "Sabit Hızlı Hareket" ≠ "KUVVET VE HAREKET"
        assert y.status == "bulunamadi"
        assert "ilk_sayfa" in y.mesaj
        assert cagrilar == []

    def test_elle_aralik_12_sayfaya_kirpilir(self, kitap, llm):
        y = dp.ders_plani_uret(_istek(tema="", ilk_sayfa=20, son_sayfa=200))
        assert y.sayfalar == list(range(20, 32))

    def test_ters_aralik_bulunamadi(self, kitap, llm):
        y = dp.ders_plani_uret(_istek(ilk_sayfa=30, son_sayfa=20))
        assert y.status == "bulunamadi"

    def test_onbellek_ve_zorla(self, kitap, llm):
        cagrilar, _ = llm
        assert dp.ders_plani_uret(_istek()).onbellekten is False
        ikinci = dp.ders_plani_uret(_istek())
        assert ikinci.onbellekten is True and ikinci.status == "ok"
        assert len(cagrilar) == 1
        assert dp.ders_plani_uret(_istek(zorla=True)).onbellekten is False
        assert len(cagrilar) == 2

    def test_saglayici_hatasi_hata_doner_onbellege_yazmaz(self, kitap, llm):
        _, davranis = llm
        davranis["sonuc"] = RuntimeError("'ders_plani' görevi için hiçbir sağlayıcı yanıt vermedi")
        y = dp.ders_plani_uret(_istek())
        assert y.status == "hata" and "sağlayıcı" in y.mesaj
        assert not list((kitap / "ders_plani").rglob("*.json"))

    def test_kontrol_uyarilari_doner(self, kitap, llm):
        _, davranis = llm
        davranis["sonuc"] = "1. KAVRAMLAR\nHız 99 m/s (PDF s. 20)\n3. AKIŞ\n[ÜRETİLMİŞ ÖRNEK] 77"
        y = dp.ders_plani_uret(_istek())
        assert any("99" in u for u in y.kontrol_uyarilari)
        assert not any("77" in u for u in y.kontrol_uyarilari)


class TestKaynaktaOlmayanSayilar:
    def test_yalnizca_1_2_bolumdeki_kaynak_disi_sayilar(self):
        plan = ("# 1. KAVRAMLAR\nHız 12 m/s (PDF s. 22), ivme 0\n"
                "## 2. TAHTA TASARIMI\n| 99 | 3,6 |\n"
                "# 3. 40 DAKİKALIK AKIŞ\n00–05 ... [ÜRETİLMİŞ ÖRNEK] 77 m")
        kaynak = "[s.22]\n12 m / 4 s = 3 m/s, ortalama 3,6 m/s, ivme 0"
        assert dp.kaynakta_olmayan_sayilar(plan, kaynak) == ["99"]

    def test_bolum_3_yoksa_tum_plan_denetlenir(self):
        assert dp.kaynakta_olmayan_sayilar("Hız 5 m/s", "hız 12") == ["5"]


class TestEndpoint:
    def test_router_200_ve_auth_bagli(self, kitap, llm, monkeypatch):
        monkeypatch.setenv("FARABI_AUTH_REQUIRED", "0")
        app = FastAPI()
        app.include_router(dp.router)
        y = TestClient(app).post("/api/egitim/ders_plani", json={
            "ders": "fizik", "sinif": "10", "konu": "Sabit Hızlı Hareket", "tema": "Kuvvet ve Hareket"})
        assert y.status_code == 200 and y.json()["status"] == "ok"
        assert dp.router.dependencies, "router auth.dogrula_tahta'ya bağlı olmalı"
