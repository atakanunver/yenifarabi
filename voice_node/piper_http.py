"""voice_node/piper_http.py — Faz 1b: Piper HTTP TTS, `piper` paketi IMPORT
EDİLMEDEN.

`pipecat.services.piper.tts` modülünün TEPESİNDE (hem `PiperTTSService` hem
`PiperHttpTTSService` için ORTAK) `from piper import PiperVoice` var
(`services/piper/tts.py:29-35`, try/except ModuleNotFoundError -> ImportError)
— bu modülü import etmek `PiperHttpTTSService` GPL'siz kalsa bile `piper-tts`
paketinin voice_node venv'inde kurulu olmasını gerektirirdi. Piper GPL-3.0
(+ espeak-ng GPL) bilinçli olarak AYRI bir proje/venv'de izole edildi
(`voice_node/piper_servis/`, plan "Yeni bileşenler") — bu dosya
`PiperHttpTTSService.run_tts`'in (aynı dosya, satır 281-324) davranışını
`pipecat.services.tts_service.TTSService`'i DOĞRUDAN alt sınıflayarak
yeniden üretir, `piper` paketine hiç dokunmadan.

Uç nokta ve gövde biçimi `piper.http_server` kaynağından doğrulandı
(`piper/http_server.py::app_synthesize`, `POST /synthesize`,
`{"text":..., "voice":...}` -> WAV bayt akışı, gerçek servis testinde
22050 Hz mono 16-bit doğrulandı — pipeline çıkışı 24 kHz'e yeniden
örneklenir, `TTSService._stream_audio_frames_from_iterator` bunu WAV
başlığından okunan kaynak hızla otomatik yapar).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

import aiohttp
from pipecat.frames.frames import ErrorFrame, Frame, TTSStoppedFrame
from pipecat.services.tts_service import TTSService
from pipecat.utils.tracing.service_decorators import traced_tts

log = logging.getLogger("ses_dugumu.piper_http")

CIKIS_ORNEKLEME_HIZI = 24000


class PiperHttpTTS(TTSService):
    """İnce Piper HTTP istemcisi — `POST {base_url}/synthesize`."""

    def __init__(
        self,
        *,
        base_url: str,
        aiohttp_session: aiohttp.ClientSession,
        voice: str,
        **kwargs,
    ):
        super().__init__(
            push_start_frame=True,
            push_stop_frames=True,
            sample_rate=CIKIS_ORNEKLEME_HIZI,
            **kwargs,
        )
        self._url = f"{base_url.rstrip('/')}/synthesize"
        self._session = aiohttp_session
        self._voice = voice

    def can_generate_metrics(self) -> bool:
        return True

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        try:
            await self.start_tts_usage_metrics(text)
            gövde = {"text": text, "voice": self._voice}
            async with self._session.post(self._url, json=gövde) as yanit:
                if yanit.status != 200:
                    hata_metni = await yanit.text()
                    log.warning("piper HTTP hata %s: %s", yanit.status, hata_metni[:300])
                    yield ErrorFrame(error=f"Piper hata (durum: {yanit.status})")
                    yield TTSStoppedFrame(context_id=context_id)
                    return

                async for frame in self._stream_audio_frames_from_iterator(
                    yanit.content.iter_chunked(4096),
                    strip_wav_header=True,
                    context_id=context_id,
                ):
                    await self.stop_ttfb_metrics()
                    yield frame
        except Exception as e:  # noqa: BLE001 — TTS hatası dersi bozmamalı, hatayı frame olarak ilet
            log.warning("piper isteği başarısız: %s: %s", type(e).__name__, e)
            yield ErrorFrame(error=f"Piper isteği başarısız: {type(e).__name__}")
        finally:
            await self.stop_ttfb_metrics()
