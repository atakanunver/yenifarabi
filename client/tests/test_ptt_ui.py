"""Bas-konuş düğmesi (Farabi 2.0 yerel ses) — UI kabuğu."""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import ui  # noqa: E402

_app = QApplication.instance() or QApplication([])


def _pencere(monkeypatch):
    monkeypatch.setattr(ui.MainWindow, "_check_config", lambda self: True, raising=False)
    return ui.MainWindow("face.png")


def test_ptt_varsayilan_gizli_ve_sinyalle_gorunur(monkeypatch):
    w = _pencere(monkeypatch)
    assert w._ptt_btn.isHidden()
    w._ptt_sig.emit(True)
    _app.processEvents()
    assert not w._ptt_btn.isHidden()


def test_ptt_bas_birak_geri_cagrilari(monkeypatch):
    w = _pencere(monkeypatch)
    olaylar = []
    w.on_ptt_bas = lambda: olaylar.append("bas")
    w.on_ptt_birak = lambda: olaylar.append("birak")
    w._ptt_btn.pressed.emit()
    w._ptt_btn.released.emit()
    assert olaylar == ["bas", "birak"]


def test_ptt_geri_cagrisiz_patlamaz(monkeypatch):
    w = _pencere(monkeypatch)
    w._ptt_btn.pressed.emit()
    w._ptt_btn.released.emit()


def test_uyari_log_satirina_yazilir(monkeypatch):
    w = _pencere(monkeypatch)
    yazilan = []
    monkeypatch.setattr(w._log, "append_log", yazilan.append)
    w._uyari_sig.emit("Ses servisi kapalı (Bilgehan)")
    _app.processEvents()
    assert any("Ses servisi kapalı" in s for s in yazilan)
