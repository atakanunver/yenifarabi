"""voice_node/gozlemci.py — Faz 1b: metrik/transkript gözlemcisi.

`pipecat.observers.base_observer.BaseObserver` ile pipeline'daki HER
frame'i (kaynağı ne olursa olsun, doğrusal pipeline sırasına bağlı kalmadan)
görür — `MetricsFrame` ve `TranscriptionFrame` gibi frame'ler farklı
noktalarda üretildiği için tek bir sabit pipeline konumuna yerleştirilmiş
sıradan bir `FrameProcessor` bunların hepsini yakalayamazdı (plan
`turn-management-interruption-config.py` örneğindeki `TranscriptionLogObserver`
ile AYNI desen).

Loglama SADECE journal'a (`LOGURU_LEVEL=INFO` — CLAUDE.md gizlilik kuralı:
transkript METNİ asla journal'a yazılmaz, yalnızca uzunluk/süre). Board'a
görünür `{"tip":"transkript"|"metrik", ...}` kontrol mesajları YALNIZCA test
istemcisi (`wav_istemci.py`) için — üretim tahta istemcisi (Faz 1c) bu
mesajları görmezden gelebilir/hiç render etmeyebilir, board protokolüne
aykırı değil (bilinmeyen "tip" zaten BasKonus'ta yok sayılıyor, simetrik
olarak tahta tarafı da yeni "tip" değerlerini yok sayabilmeli)."""

from __future__ import annotations

import logging

from pipecat.frames.frames import (
    MetricsFrame,
    OutputTransportMessageUrgentFrame,
    TranscriptionFrame,
)
from pipecat.metrics.metrics import ProcessingMetricsData, TTFBMetricsData
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameDirection

log = logging.getLogger("ses_dugumu.gozlemci")


def _asama_adi(islemci_adi: str) -> str | None:
    ad = islemci_adi.lower()
    if "stt" in ad or "whisper" in ad:
        return "stt"
    if "llm" in ad or "openai" in ad:
        return "llm_ilk_icerik"
    if "tts" in ad or "piper" in ad:
        return "tts_ilk_ses"
    return None


class Gozlemci(BaseObserver):
    """`MetricsFrame` (TTFB) -> journal + board kontrol mesajı;
    `TranscriptionFrame` -> journal (yalnızca uzunluk) + board mesajı."""

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame

        if isinstance(frame, TranscriptionFrame):
            log.info("transkript alındı (uzunluk=%d karakter)", len(frame.text or ""))
            await data.source.push_frame(
                OutputTransportMessageUrgentFrame(message={"tip": "transkript", "metin": frame.text}),
                FrameDirection.DOWNSTREAM,
            )
            return

        if isinstance(frame, MetricsFrame):
            for oge in frame.data:
                if not isinstance(oge, (TTFBMetricsData, ProcessingMetricsData)):
                    continue
                asama = _asama_adi(oge.processor)
                if asama is None:
                    continue
                ms = int(oge.value * 1000)
                log.info("metrik asama=%s islemci=%s ms=%d", asama, oge.processor, ms)
                await data.source.push_frame(
                    OutputTransportMessageUrgentFrame(
                        message={"tip": "metrik", "asama": asama, "ms": ms}
                    ),
                    FrameDirection.DOWNSTREAM,
                )
