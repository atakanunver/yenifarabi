"""tests/test_serializer.py — TahtaSesSerializer: PCM<->frame, JSON kontrol,
ptt_bitir gecikmesi. Gerçek ağ/model YOK."""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipecat.frames.frames import (
    InputAudioRawFrame,
    InputTransportMessageFrame,
    OutputAudioRawFrame,
    OutputTransportMessageUrgentFrame,
)
from serializer import PTT_BITIR_GECIKME_SN, TahtaSesSerializer


def test_deserialize_binary_pcm():
    async def _run():
        s = TahtaSesSerializer()
        frame = await s.deserialize(b"\x01\x02\x03\x04")
        assert isinstance(frame, InputAudioRawFrame)
        assert frame.audio == b"\x01\x02\x03\x04"
        assert frame.sample_rate == 16000
        assert frame.num_channels == 1

    asyncio.run(_run())


def test_deserialize_ptt_basla_no_delay():
    async def _run():
        s = TahtaSesSerializer()
        t0 = time.monotonic()
        frame = await s.deserialize(json.dumps({"tip": "ptt_basla"}))
        gecen = time.monotonic() - t0
        assert isinstance(frame, InputTransportMessageFrame)
        assert frame.message == {"tip": "ptt_basla"}
        assert gecen < 0.05

    asyncio.run(_run())


def test_deserialize_ptt_bitir_gecikmeli():
    async def _run():
        s = TahtaSesSerializer()
        t0 = time.monotonic()
        frame = await s.deserialize(json.dumps({"tip": "ptt_bitir"}))
        gecen = time.monotonic() - t0
        assert isinstance(frame, InputTransportMessageFrame)
        assert frame.message == {"tip": "ptt_bitir"}
        assert gecen >= PTT_BITIR_GECIKME_SN - 0.01

    asyncio.run(_run())


def test_deserialize_arac_sonuc():
    async def _run():
        s = TahtaSesSerializer()
        mesaj = {"tip": "arac_sonuc", "id": "call_x", "sonuc": {"durum": "ok"}}
        frame = await s.deserialize(json.dumps(mesaj))
        assert isinstance(frame, InputTransportMessageFrame)
        assert frame.message == mesaj

    asyncio.run(_run())


def test_deserialize_bozuk_json_none():
    async def _run():
        s = TahtaSesSerializer()
        assert await s.deserialize("{bozuk") is None
        assert await s.deserialize(json.dumps({"baska": "alan"})) is None
        assert await s.deserialize(json.dumps(["liste"])) is None

    asyncio.run(_run())


def test_serialize_audio_bytes():
    async def _run():
        s = TahtaSesSerializer()
        frame = OutputAudioRawFrame(audio=b"\xaa\xbb", sample_rate=24000, num_channels=1)
        out = await s.serialize(frame)
        assert out == b"\xaa\xbb"

    asyncio.run(_run())


def test_serialize_kontrol_json():
    async def _run():
        s = TahtaSesSerializer()
        frame = OutputTransportMessageUrgentFrame(
            message={"tip": "arac_cagri", "id": "call_1", "ad": "pdf_sayfa", "arg": {"sayfa": 5}}
        )
        out = await s.serialize(frame)
        assert isinstance(out, str)
        veri = json.loads(out)
        assert veri["tip"] == "arac_cagri"
        assert veri["ad"] == "pdf_sayfa"

    asyncio.run(_run())
