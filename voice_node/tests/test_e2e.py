"""tests/test_e2e.py — sahte SSE Brain + sahte STT/TTS ile uçtan uca akış.

Gerçek Whisper/Piper/ağ YOK — yalnızca `OpenAILLMService`'in gerçek
`openai` HTTP istemcisi, 127.0.0.1'de aiohttp ile kurulan SAHTE bir Brain'e
konuşuyor (`server/ses_cephe.py`'nin `/v1/chat/completions` SSE biçimini
birebir taklit eder). Akış: ilk tur -> Brain `tool_calls` (pdf_sayfa)
döner -> `araclar.py` handler'ı `arac_cagri` mesajını pushlar -> test
`bas_konus._kontrol_isle` üzerinden `arac_sonuc` simüle eder -> future
çözülür -> ikinci tur Brain'e `tool` mesajıyla gider -> Brain düz metin
döner."""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiohttp import web
from araclar import araclari_kaydet
from bas_konus import BasKonus
from pipecat.frames.frames import (
    EndFrame,
    InputAudioRawFrame,
    InputTransportMessageFrame,
    OutputTransportMessageUrgentFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.services.tts_service import TTSService
from pipecat.tests.utils import QueuedFrameProcessor
from pipecat.transcriptions.language import Language
from pipecat.turns.user_mute import AlwaysUserMuteStrategy, FunctionCallUserMuteStrategy
from pipecat.turns.user_start import ExternalUserTurnStartStrategy
from pipecat.turns.user_stop import ExternalUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.utils.time import time_now_iso8601
from pipecat.workers.runner import WorkerRunner

SAHTE_TRANSKRIPT = "kırk beşinci sayfayı açar mısın"


class _SahteVadKonusmaVar:
    def num_frames_required(self):
        return 160

    @property
    def params(self):
        class P:
            confidence = 0.7

        return P()

    def voice_confidence(self, parca: bytes) -> float:
        return 1.0


class SahteSTT(SegmentedSTTService):
    @property
    def wants_wav_segments(self) -> bool:
        return False

    async def run_stt(self, audio: bytes):
        yield TranscriptionFrame(SAHTE_TRANSKRIPT, "", time_now_iso8601(), Language.TR)


class SahteTTS(TTSService):
    def __init__(self, **kwargs):
        super().__init__(push_start_frame=True, push_stop_frames=True, sample_rate=24000, **kwargs)

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str, context_id: str):
        yield TTSAudioRawFrame(b"\x00\x00" * 100, 24000, 1, context_id=context_id)


def _sse(veri: dict) -> bytes:
    return f"data: {json.dumps(veri, ensure_ascii=False)}\n\n".encode()


class SahteBrain:
    """`server/ses_cephe.py::/v1/chat/completions`'ın SSE biçimini taklit
    eder — `messages`'ta `role: tool` varsa (araç sonucu geldiyse) düz metin,
    yoksa `pdf_sayfa` için `tool_calls` döner."""

    def __init__(self):
        self.istekler: list[dict] = []
        self.basliklar: list[dict] = []

    async def handle(self, request: web.Request) -> web.StreamResponse:
        govde = await request.json()
        self.istekler.append(govde)
        self.basliklar.append(dict(request.headers))

        resp = web.StreamResponse(
            status=200, headers={"Content-Type": "text/event-stream"}
        )
        await resp.prepare(request)

        tamamlanma_id = "chatcmpl-test"
        olusturma = int(time.time())
        taban = {"id": tamamlanma_id, "object": "chat.completion.chunk", "created": olusturma,
                 "model": "farabi-brain"}

        mesajlar = govde.get("messages", [])
        arac_sonucu_var = any(m.get("role") == "tool" for m in mesajlar)

        if not arac_sonucu_var:
            delta = {
                "role": "assistant",
                "tool_calls": [{
                    "index": 0, "id": "call_abcd1234", "type": "function",
                    "function": {"name": "pdf_sayfa", "arguments": json.dumps({"sayfa": 45})},
                }],
            }
            await resp.write(_sse({**taban, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}))
            await resp.write(_sse({**taban, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}))
        else:
            await resp.write(_sse({**taban, "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Sayfa açıldı."}, "finish_reason": None}]}))
            await resp.write(_sse({**taban, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}))

        await resp.write(b"data: [DONE]\n\n")
        await resp.write_eof()
        return resp


def test_arac_cagrisi_ve_ikinci_tur():
    async def _run():
        brain = SahteBrain()
        app = web.Application()
        app.router.add_post("/v1/chat/completions", brain.handle)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]

        try:
            arac_futures: dict[str, asyncio.Future] = {}
            bas_konus = BasKonus(arac_futures=arac_futures, vad=_SahteVadKonusmaVar())
            stt = SahteSTT()
            llm = OpenAILLMService(
                base_url=f"http://127.0.0.1:{port}/v1",
                api_key="test-token",
                default_headers={"X-Farabi-Board-Key": "ses-test-anahtar"},
                settings=OpenAILLMService.Settings(
                    model="farabi-brain",
                    extra={"metadata": {"kip": "ogretmenli", "ders": "biyoloji"}},
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
            tts = SahteTTS()

            gelen_up = asyncio.Queue()
            giden_down = asyncio.Queue()
            from pipecat.processors.frame_processor import FrameDirection

            kaynak = QueuedFrameProcessor(queue=gelen_up, queue_direction=FrameDirection.UPSTREAM)
            alici = QueuedFrameProcessor(queue=giden_down, queue_direction=FrameDirection.DOWNSTREAM)

            pipeline = Pipeline(
                [kaynak, bas_konus, stt, user_aggregator, llm, tts, assistant_aggregator, alici]
            )
            worker = PipelineWorker(
                pipeline, cancel_on_idle_timeout=False,
                params=PipelineParams(enable_metrics=False),
                enable_rtvi=False,
            )

            baslama_olayi = asyncio.Event()

            @worker.event_handler("on_pipeline_started")
            async def _basladi(worker, frame):
                baslama_olayi.set()

            async def akis_gonder():
                await asyncio.wait_for(baslama_olayi.wait(), timeout=5.0)
                await worker.queue_frame(
                    InputTransportMessageFrame(message={"tip": "ptt_basla"}), FrameDirection.DOWNSTREAM
                )
                await worker.queue_frame(
                    InputAudioRawFrame(audio=b"\x11\x22" * 1600, sample_rate=16000, num_channels=1),
                    FrameDirection.DOWNSTREAM,
                )
                await worker.queue_frame(
                    InputTransportMessageFrame(message={"tip": "ptt_bitir"}), FrameDirection.DOWNSTREAM
                )

                # arac_cagri mesajı giden_down'a düşene kadar bekle (kuyruk
                # aynı zamanda downstream'e iletilmeye devam eder — sadece
                # bir kopyasını burada okuyoruz), sonra tahtanın arac_sonuc
                # göndermesini simüle et.
                arac_cagri_mesaji = None
                for _ in range(200):
                    try:
                        f = giden_down.get_nowait()
                    except asyncio.QueueEmpty:
                        await asyncio.sleep(0.02)
                        continue
                    if isinstance(f, OutputTransportMessageUrgentFrame) and f.message.get("tip") == "arac_cagri":
                        arac_cagri_mesaji = f.message
                        break
                assert arac_cagri_mesaji is not None, "arac_cagri mesajı üretilmedi"
                assert arac_cagri_mesaji["ad"] == "pdf_sayfa"
                assert arac_cagri_mesaji["arg"] == {"sayfa": 45}

                await bas_konus._kontrol_isle({
                    "tip": "arac_sonuc", "id": arac_cagri_mesaji["id"],
                    "sonuc": {"durum": "ok", "sayfa": 45},
                })

                # ikinci Brain isteği gelene kadar bekle.
                for _ in range(200):
                    if len(brain.istekler) >= 2:
                        break
                    await asyncio.sleep(0.02)
                assert len(brain.istekler) >= 2, "ikinci Brain isteği gitmedi"

                await asyncio.sleep(0.3)
                await worker.queue_frame(EndFrame())

            runner_ = WorkerRunner()
            await runner_.add_workers(worker)
            await asyncio.wait_for(
                asyncio.gather(runner_.run(), akis_gonder()), timeout=20.0
            )

            # ── Doğrulamalar ────────────────────────────────────────────
            assert len(brain.istekler) >= 2
            ilk_istek = brain.istekler[0]
            assert ilk_istek.get("metadata") == {"kip": "ogretmenli", "ders": "biyoloji"}
            basliklar_kucuk = {k.lower(): v for k, v in brain.basliklar[0].items()}
            assert basliklar_kucuk.get("x-farabi-board-key") == "ses-test-anahtar"
            assert basliklar_kucuk.get("authorization") == "Bearer test-token"

            ikinci_istek = brain.istekler[1]
            roller = [m.get("role") for m in ikinci_istek.get("messages", [])]
            assert "tool" in roller
            tool_mesaji = next(m for m in ikinci_istek["messages"] if m.get("role") == "tool")
            assert "ok" in json.dumps(tool_mesaji.get("content"))

        finally:
            await runner.cleanup()

    asyncio.run(_run())
