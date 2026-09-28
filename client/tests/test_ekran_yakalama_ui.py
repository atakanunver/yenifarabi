"""
ui.py — ekran yakalama: Farabi önde ise kendini gizleyip geri getirmesi,
ve gizlilik kelime filtresi (`_ekran_baslik_gizli_mi`/`_aktif_pencere_basligi`).

Offscreen Qt (`QT_QPA_PLATFORM=offscreen`); gerçek X/xprop'a hiç gidilmez —
`_aktif_pencere_basligi` monkeypatch'lenir. `_pencere_onceki_durumu` saf bir
fonksiyon, Qt'siz de test edilir.
"""

import os
import sys
import threading
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("PyQt6")

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import ui

_app = QApplication.instance() or QApplication([])


# ── _pencere_onceki_durumu — saf fonksiyon ───────────────────────────────

def test_pencere_onceki_durumu_tam_ekran():
    assert ui._pencere_onceki_durumu(tam_ekran=True, buyutulmus=False) == "fullscreen"


def test_pencere_onceki_durumu_buyutulmus():
    assert ui._pencere_onceki_durumu(tam_ekran=False, buyutulmus=True) == "maximized"


def test_pencere_onceki_durumu_normal():
    assert ui._pencere_onceki_durumu(tam_ekran=False, buyutulmus=False) == "normal"


def test_pencere_onceki_durumu_tam_ekran_oncelikli():
    # Bir pencere aynı anda hem tam ekran hem "büyütülmüş" bayrağı taşıyabilir
    # (Qt'de fullscreen maximized'i de işaretleyebilir) — fullscreen önce
    # kontrol edilmeli, geri yüklemede kaybolmasın.
    assert ui._pencere_onceki_durumu(tam_ekran=True, buyutulmus=True) == "fullscreen"


# ── Gizlilik kelime filtresi ──────────────────────────────────────────────

@pytest.mark.parametrize("baslik", [
    "e-Okul Yoklama Sistemi",
    "YOKLAMA - 9/A",
    "MEBBİS Giriş",
    "tahtayoklama - Mozilla Firefox",
    "eokul.meb.gov.tr",
])
def test_ekran_baslik_gizli_mi_pozitif(baslik):
    assert ui._ekran_baslik_gizli_mi(baslik) is True


@pytest.mark.parametrize("baslik", [
    "9. Sınıf Biyoloji — Sayfa 84",
    "GeoGebra Classic",
    "",
    None,
    "Farabi — Yapay Zekâ Öğretmen",
])
def test_ekran_baslik_gizli_mi_negatif(baslik):
    assert ui._ekran_baslik_gizli_mi(baslik) is False


# ── MainWindow._ekran_goruntusu_yakala — gizlilik entegrasyonu ──────────

def _pencere(monkeypatch):
    monkeypatch.setattr(ui.MainWindow, "_check_config", lambda self: True, raising=False)
    return ui.MainWindow("face.png")


def test_gizli_baslikta_yakalama_yapilmaz_ve_dosya_yazilmaz(monkeypatch, tmp_path):
    w = _pencere(monkeypatch)
    monkeypatch.setattr(w, "_EKRAN_GORUNTUSU_DIZINI", tmp_path, raising=False)
    monkeypatch.setattr(ui, "_aktif_pencere_basligi", lambda: "e-Okul Yoklama")

    ctx = {"event": threading.Event(), "path": "", "gizli": False}
    # onceki=None: "Farabi önde değildi" yolunu simüle eder — gizlilik
    # denetimi Farabi önde olsun olmasın uygulanır (bkz. ui.py docstring'i).
    w._ekran_goruntusu_cek(ctx, onceki=None)

    assert ctx["gizli"] is True
    assert ctx["path"] == ""
    assert ctx["event"].is_set()
    assert list(tmp_path.glob("*.png")) == []


def test_zararsiz_baslikta_normal_yakalanir(monkeypatch, tmp_path):
    w = _pencere(monkeypatch)
    monkeypatch.setattr(w, "_EKRAN_GORUNTUSU_DIZINI", tmp_path, raising=False)
    monkeypatch.setattr(ui, "_aktif_pencere_basligi", lambda: "GeoGebra Classic")

    ctx = {"event": threading.Event(), "path": "", "gizli": False}
    w._ekran_goruntusu_cek(ctx, onceki=None)

    assert ctx.get("gizli", False) is False
    assert ctx["path"] != ""
    assert Path(ctx["path"]).exists()


def test_xprop_basarisiz_olursa_yakalamaya_devam_eder(monkeypatch, tmp_path):
    """xprop kurulu değil/patladıysa özellik BLOKE OLMAMALI — sessizce
    yakalamaya devam eder (bkz. modül CLAUDE.md'si)."""
    w = _pencere(monkeypatch)
    monkeypatch.setattr(w, "_EKRAN_GORUNTUSU_DIZINI", tmp_path, raising=False)
    monkeypatch.setattr(ui, "_aktif_pencere_basligi", lambda: None)

    ctx = {"event": threading.Event(), "path": "", "gizli": False}
    w._ekran_goruntusu_cek(ctx, onceki=None)

    assert ctx.get("gizli", False) is False
    assert ctx["path"] != ""


# ── Farabi önde ise gizlenip geri getirilmesi ────────────────────────────

def test_onde_ise_kendini_gizler_ve_geri_getirir(monkeypatch, tmp_path):
    w = _pencere(monkeypatch)
    monkeypatch.setattr(w, "_EKRAN_GORUNTUSU_DIZINI", tmp_path, raising=False)
    monkeypatch.setattr(ui, "_aktif_pencere_basligi", lambda: "GeoGebra Classic")

    # Offscreen platformda gerçek bir WM yok, isActiveWindow() hep False
    # döner — tasarımın öngördüğü gibi bu instance seviyesinde monkeypatch
    # edilir (bkz. görev talimatı).
    monkeypatch.setattr(w, "isActiveWindow", lambda: True)

    minimize_cagrildi = []
    orijinal_minimize = w.showMinimized

    def _izlenen_minimize():
        minimize_cagrildi.append(True)
        orijinal_minimize()

    monkeypatch.setattr(w, "showMinimized", _izlenen_minimize)

    geri_getir_cagrildi = []
    orijinal_geri = w._pencereyi_geri_getir

    def _izlenen_geri(onceki):
        geri_getir_cagrildi.append(onceki)
        orijinal_geri(onceki)

    monkeypatch.setattr(w, "_pencereyi_geri_getir", _izlenen_geri)

    ctx = {"event": threading.Event(), "path": "", "gizli": False}
    w._ekran_goruntusu_yakala(ctx)

    # QTimer.singleShot(400 ms, ...) — event loop'u pompalayıp zamanlayıcının
    # ateşlenmesini bekle (gerçek sleep yerine, offscreen'de de çalışır).
    QTest.qWait(800)
    assert ctx["event"].wait(timeout=2.0)

    assert minimize_cagrildi == [True]
    assert geri_getir_cagrildi == ["normal"]
    assert ctx["path"] != ""


def test_onde_degilse_hemen_yakalar_gizlemez(monkeypatch, tmp_path):
    w = _pencere(monkeypatch)
    monkeypatch.setattr(w, "_EKRAN_GORUNTUSU_DIZINI", tmp_path, raising=False)
    monkeypatch.setattr(ui, "_aktif_pencere_basligi", lambda: "GeoGebra Classic")
    monkeypatch.setattr(w, "isActiveWindow", lambda: False)

    minimize_cagrildi = []
    monkeypatch.setattr(w, "showMinimized", lambda: minimize_cagrildi.append(True))

    ctx = {"event": threading.Event(), "path": "", "gizli": False}
    w._ekran_goruntusu_yakala(ctx)

    assert ctx["event"].is_set()
    assert minimize_cagrildi == []
    assert ctx["path"] != ""
