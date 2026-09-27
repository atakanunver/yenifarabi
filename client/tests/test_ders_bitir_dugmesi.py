"""
main.py::FarabiLive._on_ders_bitir() — DERSİ BİTİR düğmesinin (ui.py) çift
tıkına bağlanan köprü. Öğretmen mikrofon modu/talimat modu değiştirmek için
40 dakika beklemeden ya da tahtayı yeniden başlatmadan dersi bitirebilsin
diye eklendi (bkz. client/CLAUDE.md, "Teacher panel").

Ağ yok — `_dersi_bitir` mock'lanır, yalnızca `asyncio.run_coroutine_threadsafe`
ile gerçek loop'a doğru zamanlandığı doğrulanır (aynı desen:
tests/test_durdur_zorlama.py).
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("sounddevice", reason="ses bağımlılıkları olmadan atlanır")

import main  # noqa: E402


def _farabi_live(loop, ders_suruyor: bool, bitmekte: bool = False) -> main.FarabiLive:
    f = main.FarabiLive.__new__(main.FarabiLive)
    f._loop = loop
    f._oturum_izni = asyncio.Event()
    if ders_suruyor:
        f._oturum_izni.set()
    f._ders_bitti_istendi = bitmekte
    return f


def _bitir_ve_topla(ders_suruyor: bool, bitmekte: bool = False) -> list:
    async def _calistir():
        f = _farabi_live(asyncio.get_running_loop(), ders_suruyor, bitmekte)
        cagrilar = []

        async def _sahte_dersi_bitir(sebep):
            cagrilar.append(sebep)

        f._dersi_bitir = _sahte_dersi_bitir
        f._on_ders_bitir()
        await asyncio.sleep(0.05)
        return cagrilar

    return asyncio.run(_calistir())


class TestOnDersBitir:
    def test_ders_surerken_dersi_bitir_planlanir(self):
        assert _bitir_ve_topla(ders_suruyor=True) == ["öğretmen dersi bitirdi"]

    def test_loop_yokken_sessiz_kalir(self):
        f = _farabi_live(None, ders_suruyor=False)
        f._on_ders_bitir()   # exception atmamalı

    def test_ders_yokken_sessiz_kalir(self):
        # Dersler arasında `_oturum_izni` temizdir (run()'ın ders-bitti dalı).
        assert _bitir_ve_topla(ders_suruyor=False) == []

    def test_ders_zaten_bitmekteyken_ikinci_kez_bitirmez(self):
        # Zil/boşta kalma dersi bitirirken öğretmen de çift tıkladıysa
        # `_dersi_bitir` İKİNCİ kez çalışmamalı: bayrak bayat kalır ve bir
        # sonraki ders açılır açılmaz kapanırdı (+ çift yedekleme).
        assert _bitir_ve_topla(ders_suruyor=True, bitmekte=True) == []


class TestYenidenBaglanirkenBitir:
    def test_bayrak_acikken_run_baglanmadan_dersi_bitirir(self):
        # Bağlantı koptuğu sırada DERSİ BİTİR'e basıldıysa run() yeni
        # bağlantı açmadan ders-bitti dalına gitmeli (istek kaybolmamalı).
        import inspect
        kaynak = inspect.getsource(main.FarabiLive.run)
        once = kaynak.index("if self._ders_bitti_istendi:\n")
        baglan = kaynak.index("client.aio.live.connect")
        assert once < baglan
        assert "raise _DersBitti()" in kaynak[once:baglan]


class TestDersiBitirTekrarGirisi:
    def test_ayni_anda_iki_bitirme_tek_kapanis_yapar(self, monkeypatch):
        # Zil/boşta kalma/mikrofonsuz süre ile öğretmenin DERSİ BİTİR'i aynı
        # anda gelirse ikinci `_dersi_bitir` yedekleme beklemesi (≤6 sn)
        # sürerken girmemeli: çift kapanış satırı, çift yedekleme ve bayat
        # `_ders_bitti_istendi` (sonraki dersi açılır açılmaz kapatır).
        kapanis, yedek = [], []
        monkeypatch.setattr(main.transcript, "log_line", lambda *a, **k: None)
        monkeypatch.setattr(main.transcript, "log_session_end",
                            lambda: kapanis.append(1))

        async def _calistir():
            f = main.FarabiLive.__new__(main.FarabiLive)
            f._ders_bitti_istendi = False
            f._ders_bitti_event = asyncio.Event()

            def _yedekle():
                import time
                time.sleep(0.2)
                yedek.append(1)

            f._ders_kaydini_yedekle = _yedekle
            await asyncio.gather(f._dersi_bitir("zil"),
                                 f._dersi_bitir("öğretmen dersi bitirdi"))
            return f

        f = asyncio.run(_calistir())
        assert kapanis == [1]
        assert yedek == [1]
        assert f._ders_bitti_istendi is True
        assert f._ders_bitti_event.is_set()


class TestDersiBitirYenidenGiris:
    def test_yedekleme_suresince_ikinci_cagri_yoksayilir(self, monkeypatch):
        # Zil ve öğretmen aynı 6 sn'lik yedekleme penceresinde bitirirse
        # _dersi_bitir yalnızca bir kez işlemeli; ikinci çağrı bayrağı
        # sıfırlamadan sonra yeniden kuramamalı.
        monkeypatch.setattr(main.transcript, "log_line", lambda *a, **k: None)
        monkeypatch.setattr(main.transcript, "log_session_end", lambda: None)
        yedek = []

        async def _calistir():
            f = main.FarabiLive.__new__(main.FarabiLive)
            f._ders_bitti_event = asyncio.Event()
            f._ders_bitti_istendi = False
            f._ders_bitiriliyor = False

            def _yavas_yedek():
                import time
                yedek.append(1)
                time.sleep(0.1)

            f._ders_kaydini_yedekle = _yavas_yedek
            await asyncio.gather(f._dersi_bitir("zil"), f._dersi_bitir("öğretmen"))
            return f

        f = asyncio.run(_calistir())
        assert yedek == [1]
        assert f._ders_bitti_istendi is True
        assert f._ders_bitiriliyor is True   # yalnızca run()'ın ders-bitti dalı temizler
