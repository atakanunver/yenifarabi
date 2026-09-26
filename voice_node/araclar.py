"""voice_node/araclar.py — Faz 1b: tahta araçları için future köprüsü.

Brain (`server/ses_cephe.py`), tahtada çalışması gereken üç araç için
(`pdf_sayfa`, `yks_sorulari`, `pencere_kapat`) OpenAI `tool_calls` biçiminde
bir delta döner. Pipecat'in `OpenAILLMService`'i bunu normal bir fonksiyon
çağrısı gibi ayrıştırıp `register_function` ile kayıtlı handler'ı çağırır —
bağlama (`context.tools`) bu üç aracın ŞEMASI hiç EKLENMEZ (plan "Bağlama
araç EKLENMEZ") çünkü hangi aracın ne zaman çağrılacağına Brain kendi
Ollama turunda karar veriyor; buradaki `register_function` yalnızca YANIT
tarafını (Brain'in kararını tahtaya iletmek) bağlıyor.

Akış: handler çağrılır -> `OutputTransportMessageUrgentFrame({"tip":
"arac_cagri", ...})` aşağı akışa (TTS'i atlayıp) push edilir -> tahta
aracı kendi tarafında çalıştırır -> `{"tip":"arac_sonuc","id":...,
"sonuc":{...}}` gönderir -> `bas_konus.py` bunu deserialize edip future'ı
çözer -> handler `params.result_callback(sonuc)` ile Brain'e ikinci turu
başlatır.

Zaman aşımları `client/actions/kayit.py` ile AYNI (plan): pdf_sayfa 10 sn,
yks_sorulari 15 sn, pencere_kapat 8 sn. Pipecat'in KENDİ `register_function
(timeout_secs=...)` mekanizmasıyla YARIŞMAMAK için buradaki iç bekleme
bilerek biraz KISA tutulur (plan zaman aşımı - 0.5 sn) — böylece Türkçe
"tahta yanıt vermedi" mesajı HER ZAMAN bizim tarafımızdan, pipecat'in kendi
(farklı biçimli) zaman aşımı mesajından ÖNCE üretilir.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from pipecat.frames.frames import OutputTransportMessageUrgentFrame
from pipecat.services.llm_service import FunctionCallParams

log = logging.getLogger("ses_dugumu.araclar")

# (araç adı -> zaman aşımı saniye) — client/actions/kayit.py ile aynı.
ZAMAN_ASIMLARI: dict[str, float] = {
    "pdf_sayfa": 10.0,
    "yks_sorulari": 15.0,
    "pencere_kapat": 8.0,
}

TAHTA_YANIT_VERMEDI = {"hata": "tahta yanıt vermedi"}


def tahta_arac_handler_olustur(ad: str, arac_futures: dict[str, asyncio.Future]):
    """`ad` (pdf_sayfa | yks_sorulari | pencere_kapat) için `register_function`
    handler'ı üretir. `arac_futures` oturuma özel, `bas_konus.py` ile
    PAYLAŞILAN sözlük — aynı referans her iki tarafa da verilmeli."""

    async def handler(params: FunctionCallParams) -> None:
        call_id = f"call_{uuid.uuid4().hex[:8]}"
        gelecek: asyncio.Future = asyncio.get_running_loop().create_future()
        arac_futures[call_id] = gelecek

        mesaj = {
            "tip": "arac_cagri",
            "id": call_id,
            "ad": ad,
            "arg": dict(params.arguments),
        }
        await params.llm.push_frame(OutputTransportMessageUrgentFrame(message=mesaj))

        zaman_asimi = ZAMAN_ASIMLARI.get(ad, 10.0)
        try:
            sonuc = await asyncio.wait_for(gelecek, timeout=max(1.0, zaman_asimi - 0.5))
        except TimeoutError:
            log.warning("tahta aracı zaman aşımına uğradı: ad=%s id=%s", ad, call_id)
            sonuc = dict(TAHTA_YANIT_VERMEDI)
        finally:
            arac_futures.pop(call_id, None)

        await params.result_callback(sonuc)

    return handler


def araclari_kaydet(llm, arac_futures: dict[str, asyncio.Future]) -> None:
    """Üç tahta aracını `llm.register_function` ile bağlar (plan madde 4)."""
    for ad, zaman_asimi in ZAMAN_ASIMLARI.items():
        llm.register_function(
            ad, tahta_arac_handler_olustur(ad, arac_futures), timeout_secs=zaman_asimi
        )
