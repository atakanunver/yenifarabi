"""
Mikrofonsuz mod — arayüz (ui.py). Offscreen Qt; ağ yok.

Mikrofonsuz tahtada: öğretmen modu (yalnız sesli komut) seçilemez, varsayılan
öğrenci modudur, mikrofon düğmesi kapalıdır ve DERSİ BAŞLAT konuyu yazılı
sorar — konu boşken başlatılamaz.
"""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("PyQt6")

import ui                                   # noqa: E402
from PyQt6.QtWidgets import QApplication, QDialog   # noqa: E402

_app = QApplication.instance() or QApplication([])


def _pencere(monkeypatch, mikrofon: bool):
    monkeypatch.setattr(ui.tahta, "mikrofon_var", lambda: mikrofon)
    monkeypatch.setattr(ui.MainWindow, "_check_config", lambda self: True,
                        raising=False)
    return ui.MainWindow("face.png")


def test_mikrofonsuz_tahtada_ogrenci_modu_ve_kilitler(monkeypatch):
    w = _pencere(monkeypatch, mikrofon=False)
    assert w.mikrofonsuz is True
    assert w.talimat_modu is False
    assert not w._ogretmen_btn.isEnabled()
    assert not w._mute_btn.isEnabled()
    assert "MİKROFONSUZ" in w._mute_btn.text()
    w._toggle_mute()                      # F4 — etkisiz olmalı
    assert w._muted is False


def test_mikrofonlu_tahtada_davranis_degismedi(monkeypatch):
    w = _pencere(monkeypatch, mikrofon=True)
    assert w.mikrofonsuz is False
    assert w.talimat_modu is True          # eski varsayılan: öğretmen modu
    assert w._ogretmen_btn.isEnabled()
    assert w._mute_btn.isEnabled()


def test_ders_bitince_ogretmen_modu_kilitli_kalir(monkeypatch):
    w = _pencere(monkeypatch, mikrofon=False)
    w._dersi_sifirla_gorunumu()
    assert not w._ogretmen_btn.isEnabled()
    assert w._ogrenci_btn.isEnabled()


class TestKonuDiyalogu:
    def test_konu_bosken_baslatilamaz(self):
        d = ui._KonuDiyalogu(varsayilan_ders="Fizik")
        assert not d._tamam.isEnabled()
        d._alanlar["konu"].setText("   ")
        assert not d._tamam.isEnabled()
        d._alanlar["konu"].setText("Newton'un yasaları")
        assert d._tamam.isEnabled()

    def test_cerceve_yazilanlari_dondurur(self):
        d = ui._KonuDiyalogu(varsayilan_ders="Fizik")
        d._alanlar["konu"].setText(" Kuvvet ")
        d._alanlar["kazanim"].setText("F.9.2.1")
        assert d.cerceve() == {"ders": "Fizik", "konu": "Kuvvet",
                               "kazanim": "F.9.2.1"}


def test_dersi_baslat_vazgecilirse_baglanmaz(monkeypatch):
    w = _pencere(monkeypatch, mikrofon=False)
    cagrildi = []
    w.on_session_start = lambda: cagrildi.append(1)
    monkeypatch.setattr(ui._KonuDiyalogu, "exec",
                        lambda self: QDialog.DialogCode.Rejected)
    w._dersi_baslat()
    assert w._baslat_btn.isEnabled()
    assert w.baslangic_cercevesi is None


def test_dersi_baslat_konuyla_cerceveyi_saklar(monkeypatch):
    w = _pencere(monkeypatch, mikrofon=False)
    w.on_session_start = lambda: None

    def _kabul(self):
        self._alanlar["ders"].setText("Kimya")
        self._alanlar["konu"].setText("Mol kavramı")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ui._KonuDiyalogu, "exec", _kabul)
    w._dersi_baslat()
    assert w.baslangic_cercevesi == {"ders": "Kimya", "konu": "Mol kavramı",
                                     "kazanim": ""}
    assert not w._baslat_btn.isEnabled()
