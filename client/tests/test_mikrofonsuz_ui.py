"""
Mikrofonsuz mod — arayüz (ui.py). Offscreen Qt; ağ yok.

Mikrofonsuz tahtada: öğretmen modu (yalnız sesli komut) seçilemez, varsayılan
öğrenci modudur, mikrofon düğmesi kapalıdır ve DERSİ BAŞLAT konuyu yazılı
sorar — konu boşken başlatılamaz.
"""

import builtins
import os
import sys
import threading
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


# ── Mikrofon modu — canlı (dokunmatik) geçiş ────────────────────────────────
#
# DERSİ BAŞLAT'tan önce panelde tek dokunuşla mikrofonlu/mikrofonsuz arasında
# geçiş — yalnızca bellek içi (self.mikrofonsuz); config dosyası hiç
# okunmaz/yazılmaz, yeniden başlatınca ayar dosyasındaki değere döner.

class TestMikrofonModuGecisi:
    def test_mikrofonsuzdan_mikrofonluya_gecis(self, monkeypatch):
        w = _pencere(monkeypatch, mikrofon=False)
        assert w.mikrofonsuz is True
        w._mikrofon_modu_degistir()
        assert w.mikrofonsuz is False
        assert w._ogretmen_btn.isEnabled()
        assert w._mute_btn.isEnabled()
        assert "MİKROFON AÇIK" in w._mute_btn.text()

    def test_mikrofonludan_mikrofonsuza_gecis(self, monkeypatch):
        w = _pencere(monkeypatch, mikrofon=True)
        assert w.mikrofonsuz is False
        w._mikrofon_modu_degistir()
        assert w.mikrofonsuz is True
        assert w.talimat_modu is False
        assert not w._ogretmen_btn.isEnabled()
        assert not w._mute_btn.isEnabled()
        assert "MİKROFONSUZ" in w._mute_btn.text()

    def test_gecis_dosyaya_asla_yazmaz(self, monkeypatch):
        w = _pencere(monkeypatch, mikrofon=True)
        yazma_denemeleri = []
        orig_open = builtins.open

        def _guard(dosya, *args, **kwargs):
            mod = args[0] if args else kwargs.get("mode", "r")
            if "api_keys" in str(dosya) and any(c in mod for c in "wa+"):
                yazma_denemeleri.append(dosya)
            return orig_open(dosya, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", _guard)
        w._mikrofon_modu_degistir()
        w._mikrofon_modu_degistir()
        assert yazma_denemeleri == []

    def test_dugme_ders_baslayinca_kilitlenir(self, monkeypatch):
        w = _pencere(monkeypatch, mikrofon=True)
        w.on_session_start = lambda: None
        w._dersi_baslat()
        assert not w._mikrofon_mod_btn.isEnabled()

    def test_dugme_ders_bitince_tekrar_acilir(self, monkeypatch):
        w = _pencere(monkeypatch, mikrofon=True)
        w.on_session_start = lambda: None
        w._dersi_baslat()
        w._dersi_sifirla_gorunumu()
        assert w._mikrofon_mod_btn.isEnabled()

    def test_talimat_modundan_cikinca_kilitlenir(self, monkeypatch):
        w = _pencere(monkeypatch, mikrofon=True)
        w._talimat_modundan_cik_gorunumu()
        assert not w._mikrofon_mod_btn.isEnabled()


# ── DERSİ BİTİR düğmesi ──────────────────────────────────────────────────
#
# Yalnızca ders sürerken aktif; çift tıkla çalışır (dokunmatik tahtada tek
# tık yanlışlıkla dersi bitirmemeli — DERSİ BAŞLAT ile aynı gerekçe).

class TestDersiBitirDugmesi:
    def test_baslangicta_kapali(self, monkeypatch):
        w = _pencere(monkeypatch, mikrofon=True)
        assert not w._bitir_btn.isEnabled()

    def test_oturum_acilinca_aktif_olur(self, monkeypatch):
        w = _pencere(monkeypatch, mikrofon=True)
        w._on_gemini_oturum_degisti(True)
        assert w._bitir_btn.isEnabled()

    def test_ders_bitince_tekrar_kapanir(self, monkeypatch):
        w = _pencere(monkeypatch, mikrofon=True)
        w._on_gemini_oturum_degisti(True)
        w._dersi_sifirla_gorunumu()
        assert not w._bitir_btn.isEnabled()

    def test_tek_tikla_tetiklenmez(self, monkeypatch):
        w = _pencere(monkeypatch, mikrofon=True)
        w._on_gemini_oturum_degisti(True)
        cagrildi = []
        w.on_ders_bitir = lambda: cagrildi.append(1)
        w._bitir_btn.click()
        assert cagrildi == []

    def test_cift_tikla_callback_bir_kez_cagrilir(self, monkeypatch):
        w = _pencere(monkeypatch, mikrofon=True)
        w._on_gemini_oturum_degisti(True)
        bitti = threading.Event()
        cagrildi = []

        def _cb():
            cagrildi.append(1)
            bitti.set()

        w.on_ders_bitir = _cb
        w._bitir_btn.mouseDoubleClickEvent(None)
        assert bitti.wait(timeout=2)
        assert cagrildi == [1]
        assert not w._bitir_btn.isEnabled()   # kendini kapatır, çift ateşlemeyi önler

    def test_callback_baglanmamissa_sessiz_kalir(self, monkeypatch):
        w = _pencere(monkeypatch, mikrofon=True)
        w._on_gemini_oturum_degisti(True)
        w.on_ders_bitir = None
        w._bitir_btn.mouseDoubleClickEvent(None)   # exception atmamalı
        assert w._bitir_btn.isEnabled()


def test_mikrofonsuzdan_sonra_mikrofonlu_derse_eski_konu_tasinmaz(monkeypatch):
    # Aynı süreçte: mikrofonsuz ders (konu yazıldı) → bitti → mikrofonluya
    # geçildi → yeni ders. main.py her DERSİ BAŞLAT'ta baslangic_cercevesi'ni
    # okuduğu için eski konu yeni derse sızmamalı.
    w = _pencere(monkeypatch, mikrofon=False)
    w.on_session_start = lambda: None
    w.baslangic_cercevesi = {"ders": "Kimya", "konu": "Mol", "kazanim": ""}
    w._dersi_sifirla_gorunumu()
    w._mikrofon_modu_degistir()           # → mikrofonlu
    w._talimat_modu_degistir(False)       # öğrenci modu, normal ders
    w._dersi_baslat()
    assert w.baslangic_cercevesi is None
