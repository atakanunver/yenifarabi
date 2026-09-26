"""voice_node/oturum.py — Faz 1b: tahta başına Pipecat pipeline'ı.

Pipeline (plan): `transport.input()` -> `BasKonus` -> `SttPaylasimli` ->
`user_aggregator` -> `OpenAILLMService` -> `PiperHttpTTS` ->
`transport.output()` -> `assistant_aggregator`.

Bağlama araç EKLENMEZ — üç tahta aracı (`pdf_sayfa`, `yks_sorulari`,
`pencere_kapat`) yalnızca `register_function` ile YANIT tarafında bağlanır,
Brain (`server/ses_cephe.py`) hangi aracın çağrılacağına kendi Ollama
turunda karar verir (bkz. `araclar.py` docstring'i).
"""

from __future__ import annotations

import logging
import os

import aiohttp
from araclar import araclari_kaydet
from bas_konus import BasKonus
from fastapi import WebSocket
from gozlemci import Gozlemci
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import (
    PipelineParams,
    PipelineWorker,
    ProcessorUnusablePolicy,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.turns.user_mute import AlwaysUserMuteStrategy, FunctionCallUserMuteStrategy
from pipecat.turns.user_start import ExternalUserTurnStartStrategy
from pipecat.turns.user_stop import ExternalUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner
from piper_http import PiperHttpTTS
from serializer import TahtaSesSerializer
from stt_paylasimli import SttPaylasimli

log = logging.getLogger("ses_dugumu.oturum")

BRAIN_URL = os.environ.get("BRAIN_URL", "http://127.0.0.1:8000").rstrip("/")
PIPER_URL = os.environ.get("PIPER_URL", "http://127.0.0.1:5050").rstrip("/")
PIPER_SES = os.environ.get("PIPER_SES", "tr_TR-dfki-medium")
WHISPER_MODEL_DIR = os.environ.get(
    "WHISPER_MODEL_DIR", "/mnt/farabi-data/farabi/ses/whisper/large-v3-turbo"
)
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8_float16")
FARABI_SES_TOKEN = os.environ.get("FARABI_SES_TOKEN", "")


async def oturum_calistir(
    websocket: WebSocket,
    *,
    board_key: str,
    kip: str,
    ders: str | None,
) -> None:
    """Tek bir tahta websocket bağlantısı için pipeline'ı kurar ve
    bağlantı kapanana kadar çalıştırır (senkron değil — `await` ile bloklar,
    çağıran `app.py` her bağlantı için ayrı bir task/coroutine içinde
    çağırır)."""
    arac_futures: dict = {}

    def baglam_guncelle(mesaj: dict):
        nonlocal kip, ders
        yeni_kip = mesaj.get("kip")
        yeni_ders = mesaj.get("ders")
        if yeni_kip:
            kip = yeni_kip
        if yeni_ders is not None:
            ders = yeni_ders
        log.info("bağlam güncellendi kip=%s", kip)

    serializer = TahtaSesSerializer()
    bas_konus = BasKonus(arac_futures=arac_futures, baglam_geldi=baglam_guncelle)

    transport = FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
            allowed_origins=[],
        ),
    )

    async with aiohttp.ClientSession() as http_oturum:
        stt = SttPaylasimli(
            model=WHISPER_MODEL_DIR,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE,
            settings=SttPaylasimli.Settings(language=Language.TR),
        )

        tts = PiperHttpTTS(base_url=PIPER_URL, aiohttp_session=http_oturum, voice=PIPER_SES)

        llm = OpenAILLMService(
            base_url=f"{BRAIN_URL}/v1",
            api_key=FARABI_SES_TOKEN or "gerekli-degil",
            default_headers={"X-Farabi-Board-Key": board_key},
            settings=OpenAILLMService.Settings(
                model="farabi-brain",
                extra={"metadata": {"kip": kip, "ders": ders or ""}},
            ),
        )
        araclari_kaydet(llm, arac_futures)

        context = LLMContext()
        user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
            context,
            user_params=LLMUserAggregatorParams(
                user_turn_strategies=UserTurnStrategies(
                    start=[ExternalUserTurnStartStrategy(enable_interruptions=False)],
                    stop=[ExternalUserTurnStopStrategy(wait_for_transcript=True)],
                ),
                user_mute_strategies=[AlwaysUserMuteStrategy(), FunctionCallUserMuteStrategy()],
                vad_analyzer=None,
            ),
        )

        pipeline = Pipeline(
            [
                transport.input(),
                bas_konus,
                stt,
                user_aggregator,
                llm,
                tts,
                transport.output(),
                assistant_aggregator,
            ]
        )

        worker = PipelineWorker(
            pipeline,
            params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
            observers=[Gozlemci()],
            # RTVI dışı bırakılır — `PipelineWorker` varsayılan olarak
            # `enable_rtvi=True`, kendi RTVIProcessor'ını pipeline'ın EN
            # BAŞINA ekleyip bizim JSON kontrol mesajlarımızı ("ptt_basla"
            # vb.) "Ignoring not RTVI message" diyerek YUTUYOR (plan
            # "Onaylı kararlar" — RTVI; e2e testiyle doğrulandı).
            enable_rtvi=False,
            processor_unusable_policy=ProcessorUnusablePolicy.END,
        )

        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)

        @transport.event_handler("on_client_disconnected")
        async def _kapandi(_transport, _client):
            log.info("tahta bağlantısı kapandı")
            await runner.cancel()

        await runner.run()
