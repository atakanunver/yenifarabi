"""voice_node/serializer.py — Faz 1b: tahta <-> ses düğümü kablo biçimi.

İkili websocket mesajı = PCM16 mono ham ses (giriş 16 kHz — tahtanın
mikrofonu; çıkış frame'lerinin sample_rate'i `piper_http.py`'nin ürettiği
24 kHz'tir, `FastAPIWebsocketOutputTransport.write_audio_frame` bunu olduğu
gibi iletir). Metin websocket mesajı = tek satır JSON kontrol paketi.

Kontrol paketi biçimi (bkz. `voice_node/CLAUDE.md` "Tel protokolü"):

Tahta -> düğüm:
  {"tip": "ptt_basla"}
  {"tip": "ptt_bitir"}
  {"tip": "arac_sonuc", "id": "<call_id>", "sonuc": {...}}
  {"tip": "baglam", "kip": "...", "ders": "..."}

Düğüm -> tahta:
  {"tip": "arac_cagri", "id": "...", "ad": "...", "arg": {...}}
  {"tip": "transkript", "metin": "...", "stt_ms": 123}
  {"tip": "metrik", "asama": "stt|llm_ilk_icerik|tts_ilk_ses|uctan_uca", "ms": 123}
  {"tip": "hata", "mesaj": "..."}

"ptt_bitir" ÖZEL: deserialize burada ~200 ms bekler (bkz. plan "Bas-konuş" —
`transports/base_input.py` içindeki `_audio_in_queue`, ham ses baytlarını
ayrı bir arka plan görevinde tüketiyor; JSON kontrol mesajları ise
`_receive_messages()` döngüsünde DOĞRUDAN `push_frame` ile iletiliyor —
websocket'ten SIRAYLA okunan son ses baytı ile hemen ardından gelen
"ptt_bitir" arasında bir yarış var: ses arka plan kuyruğunda beklerken
kontrol mesajı onu GEÇEBİLİR. Bekleme burada, `process_frame` İÇİNDE DEĞİL
(bkz. `bas_konus.py` docstring'i) — bir FrameProcessor'ın kendi kuyruğunu
bloklamaz, yalnızca bu tek deserialize çağrısını geciktirir, arka plan ses
tüketici görevi bu sürede rahatça yetişir.
"""

from __future__ import annotations

import asyncio
import json
import logging

from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InputTransportMessageFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    OutputTransportMessageUrgentFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer

log = logging.getLogger("ses_dugumu.serializer")

GIRIS_ORNEKLEME_HIZI = 16000
PTT_BITIR_GECIKME_SN = 0.2


class TahtaSesSerializer(FrameSerializer):
    """PCM16 ikili ses + tek satır JSON kontrol — tahtanın mevcut
    `websockets`/`sounddevice`/`numpy` yığınıyla doğrudan uyumlu, yeni bir
    paket kurulmasını gerektirmez (plan "Onaylı kararlar" — Taşıma)."""

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if self.should_ignore_frame(frame):
            return None
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio
        if isinstance(frame, (OutputTransportMessageFrame, OutputTransportMessageUrgentFrame)):
            try:
                return json.dumps(frame.message, ensure_ascii=False)
            except (TypeError, ValueError) as e:
                log.warning("kontrol mesajı JSON'a çevrilemedi: %s: %s", type(e).__name__, e)
                return None
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, (bytes, bytearray)):
            return InputAudioRawFrame(
                audio=bytes(data), sample_rate=GIRIS_ORNEKLEME_HIZI, num_channels=1
            )

        try:
            mesaj = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            log.warning("bozuk JSON kontrol mesajı görmezden gelindi")
            return None
        if not isinstance(mesaj, dict) or "tip" not in mesaj:
            log.warning("geçersiz kontrol mesajı biçimi görmezden gelindi")
            return None

        if mesaj.get("tip") == "ptt_bitir":
            # Bkz. modül docstring'i — ses kuyruğunun yetişmesi için bilinçli
            # gecikme, yalnızca BU mesajın dispatch edilmesini geciktirir.
            await asyncio.sleep(PTT_BITIR_GECIKME_SN)

        return InputTransportMessageFrame(message=mesaj)
