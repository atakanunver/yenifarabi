"""tests/test_bas_konus.py — bas-konuş çerçeve sırası + boş-basış filtresi.

Gerçek Silero modeli YÜKLENMEZ — `vad` parametresiyle sahte bir VAD enjekte
edilir (bkz. `bas_konus.py::BasKonus.__init__`), böylece test yalnızca
BİZİM frame-sıralama mantığımızı doğrular, Silero'nun kendi doğruluğunu
DEĞİL (o zaten pipecat/Silero'nun kendi test kapsamında)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bas_konus import BasKonus
from pipecat.frames.frames import (
    InputAudioRawFrame,
    InputTransportMessageFrame,
    ProposedUserStartedSpeakingFrame,
    ProposedUserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.tests.utils import run_test


class _SahteVadKonusmaVar:
    def num_frames_required(self):
        return 160

    @property
    def params(self):
        class P:
            confidence = 0.7

        return P()

    def voice_confidence(self, parca: bytes) -> float:
        return 1.0  # her zaman "konuşma var"


class _SahteVadSessiz:
    def num_frames_required(self):
        return 160

    @property
    def params(self):
        class P:
            confidence = 0.7

        return P()

    def voice_confidence(self, parca: bytes) -> float:
        return 0.0  # her zaman "sessizlik"


def _ses_parcasi(n_bayt: int = 3200) -> bytes:
    return b"\x11\x22" * (n_bayt // 2)


def test_konusmali_basis_frame_sirasi():
    async def _run():
        bas_konus = BasKonus(arac_futures={}, vad=_SahteVadKonusmaVar())
        gonderilenler = [
            InputTransportMessageFrame(message={"tip": "ptt_basla"}),
            InputAudioRawFrame(audio=_ses_parcasi(), sample_rate=16000, num_channels=1),
            InputTransportMessageFrame(message={"tip": "ptt_bitir"}),
        ]
        down, _up = await run_test(
            bas_konus,
            frames_to_send=gonderilenler,
            start_timeout=5.0,
            expected_down_frames=[
                VADUserStartedSpeakingFrame,
                ProposedUserStartedSpeakingFrame,
                InputAudioRawFrame,
                VADUserStoppedSpeakingFrame,
                ProposedUserStoppedSpeakingFrame,
            ],
        )
        # Tek büyük ses çerçevesi tüm basılı segmenti içermeli.
        ses_cercevesi = next(f for f in down if isinstance(f, InputAudioRawFrame))
        assert ses_cercevesi.audio == _ses_parcasi()

    asyncio.run(_run())


def test_bos_basis_hicbir_sey_gondermez():
    async def _run():
        bas_konus = BasKonus(arac_futures={}, vad=_SahteVadSessiz())
        gonderilenler = [
            InputTransportMessageFrame(message={"tip": "ptt_basla"}),
            InputAudioRawFrame(audio=_ses_parcasi(), sample_rate=16000, num_channels=1),
            InputTransportMessageFrame(message={"tip": "ptt_bitir"}),
        ]
        down, _up = await run_test(
            bas_konus,
            frames_to_send=gonderilenler,
            start_timeout=5.0,
            expected_down_frames=[],
        )
        assert down == []

    asyncio.run(_run())


def test_basili_degilken_ses_dusurulur():
    async def _run():
        bas_konus = BasKonus(arac_futures={}, vad=_SahteVadKonusmaVar())
        # ptt_basla HİÇ gönderilmiyor — ses basılı değilken geliyor.
        gonderilenler = [
            InputAudioRawFrame(audio=_ses_parcasi(), sample_rate=16000, num_channels=1),
        ]
        down, _up = await run_test(
            bas_konus,
            frames_to_send=gonderilenler,
            start_timeout=5.0,
            expected_down_frames=[],
        )
        assert down == []

    asyncio.run(_run())


def test_arac_sonuc_future_cozer():
    async def _run():
        futures: dict[str, asyncio.Future] = {}
        loop = asyncio.get_event_loop()
        gelecek = loop.create_future()
        futures["call_1"] = gelecek
        bas_konus = BasKonus(arac_futures=futures, vad=_SahteVadKonusmaVar())
        gonderilenler = [
            InputTransportMessageFrame(
                message={"tip": "arac_sonuc", "id": "call_1", "sonuc": {"durum": "ok"}}
            ),
        ]
        await run_test(
            bas_konus, frames_to_send=gonderilenler, start_timeout=5.0, expected_down_frames=[]
        )
        assert gelecek.done()
        assert gelecek.result() == {"durum": "ok"}
        assert "call_1" not in futures

    asyncio.run(_run())
