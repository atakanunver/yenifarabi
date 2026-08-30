"""
main.py::FarabiLive._on_teacher_command()'ın "durdur" dalı — DUR konuşma
sırasında geldiğinde bağlantıyı zorla yenileme escalasyonu (bkz. main.py'nin
_DurZorlama docstring'i).

Regresyon: 2026-08-30, 9-A canlı test — öğretmen "dur" dedi, _sesi_sustur()
yerel kuyruğu boşalttı ama Gemini sunucu tarafında üretime devam etti,
Farabi 6 "dur" komutundan SONRA bile yeni bir YKS sorusunu baştan okumaya
başladı. Ağ yok — event/loop mock'lanır.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("sounddevice", reason="ses bağımlılıkları olmadan atlanır")

import main  # noqa: E402


def _farabi_live(is_speaking: bool, loop: asyncio.AbstractEventLoop) -> main.FarabiLive:
    f = main.FarabiLive.__new__(main.FarabiLive)
    f._loop = loop
    f._son_etkinlik = 0.0
    f._video_yuzunden_susturuldu = False
    f._is_speaking = is_speaking
    f._durdur_zorla_event = asyncio.Event()
    f._durdur_zorla_istendi = False
    f.session = None
    f.motor = SimpleNamespace(duraklat=lambda *_a: None, mudahale=lambda *_a: None)
    f.ui = SimpleNamespace(write_log=lambda *_a: None, set_state=lambda *_a: None, muted=False)
    f._sesi_sustur = lambda: 0
    return f


async def _calistir(is_speaking: bool, anahtar: str, mevcut_istendi: bool = False) -> main.FarabiLive:
    """`_on_teacher_command` gerçek bir event loop bekliyor (sonunda
    `asyncio.run_coroutine_threadsafe` çağırıyor) — bu yüzden testler
    `asyncio.run()` içinden, `get_running_loop()` ile gerçek loop'u
    kullanarak çalışır; yalnızca `call_soon_threadsafe`'in hedefi olan
    `_durdur_zorla_event`/`_sesi_sustur` mock'lanır."""
    loop = asyncio.get_running_loop()
    f = _farabi_live(is_speaking, loop)
    f._durdur_zorla_istendi = mevcut_istendi
    f._on_teacher_command(anahtar, f"[ÖĞRETMEN KOMUTU] test-{anahtar}")
    await asyncio.sleep(0)   # call_soon_threadsafe ile zamanlanan işin çalışmasına izin ver
    return f


class TestDurdurZorlamaEscalasyonu:
    def test_konusurken_durdur_zorlama_tetiklenir(self):
        f = asyncio.run(_calistir(is_speaking=True, anahtar="durdur"))
        assert f._durdur_zorla_istendi is True
        assert f._durdur_zorla_event.is_set()

    def test_sessizken_durdur_zorlama_tetiklenmez(self):
        f = asyncio.run(_calistir(is_speaking=False, anahtar="durdur"))
        assert f._durdur_zorla_istendi is False
        assert not f._durdur_zorla_event.is_set()

    def test_devam_zorlama_bayragini_etkilemez(self):
        # "devam" dalı zorlama bayrağına dokunmaz — run()'ın except bloğu
        # zaten bağlantı yenilenince bunu sıfırlıyor, burada DEĞİL.
        f = asyncio.run(_calistir(is_speaking=True, anahtar="devam", mevcut_istendi=True))
        assert f._durdur_zorla_istendi is True
