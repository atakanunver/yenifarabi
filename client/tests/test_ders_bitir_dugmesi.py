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


def _farabi_live(loop, ders_bitti_event) -> main.FarabiLive:
    f = main.FarabiLive.__new__(main.FarabiLive)
    f._loop = loop
    f._ders_bitti_event = ders_bitti_event
    return f


class TestOnDersBitir:
    def test_oturum_acikken_dersi_bitir_planlanir(self):
        async def _calistir():
            loop = asyncio.get_running_loop()
            f = _farabi_live(loop, asyncio.Event())
            cagrilar = []

            async def _sahte_dersi_bitir(sebep):
                cagrilar.append(sebep)

            f._dersi_bitir = _sahte_dersi_bitir
            f._on_ders_bitir()
            await asyncio.sleep(0.05)
            return cagrilar

        assert asyncio.run(_calistir()) == ["öğretmen dersi bitirdi"]

    def test_loop_yokken_sessiz_kalir(self):
        f = _farabi_live(None, None)
        f._on_ders_bitir()   # exception atmamalı

    def test_oturum_yokken_sessiz_kalir(self):
        async def _calistir():
            loop = asyncio.get_running_loop()
            f = _farabi_live(loop, None)   # bağlantı yok, ders sürmüyor
            cagrilar = []

            async def _sahte_dersi_bitir(sebep):
                cagrilar.append(sebep)

            f._dersi_bitir = _sahte_dersi_bitir
            f._on_ders_bitir()
            await asyncio.sleep(0.05)
            return cagrilar

        assert asyncio.run(_calistir()) == []


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
