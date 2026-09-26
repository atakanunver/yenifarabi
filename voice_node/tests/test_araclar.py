"""tests/test_araclar.py — tahta araç köprüsü: future çözülür / zaman aşımı."""

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from araclar import TAHTA_YANIT_VERMEDI, tahta_arac_handler_olustur


@dataclass
class SahteLLM:
    pushed: list = field(default_factory=list)

    async def push_frame(self, frame, direction=None):
        self.pushed.append(frame)


@dataclass
class SahteFunctionCallParams:
    function_name: str
    tool_call_id: str
    arguments: dict[str, Any]
    llm: Any
    sonuclar: list = field(default_factory=list)

    async def result_callback(self, sonuc, **kwargs):
        self.sonuclar.append(sonuc)


def test_arac_cagrisi_pushlanir_ve_future_cozulur():
    async def _run():
        futures: dict[str, asyncio.Future] = {}
        handler = tahta_arac_handler_olustur("pdf_sayfa", futures)
        llm = SahteLLM()
        params = SahteFunctionCallParams(
            function_name="pdf_sayfa", tool_call_id="tc1", arguments={"sayfa": 5}, llm=llm
        )

        gorev = asyncio.create_task(handler(params))
        # handler'ın push_frame çağırıp future'ı futures'a koymasını bekle.
        for _ in range(100):
            if llm.pushed:
                break
            await asyncio.sleep(0.01)
        assert len(llm.pushed) == 1
        mesaj = llm.pushed[0].message
        assert mesaj["tip"] == "arac_cagri"
        assert mesaj["ad"] == "pdf_sayfa"
        assert mesaj["arg"] == {"sayfa": 5}
        call_id = mesaj["id"]
        assert call_id in futures

        futures[call_id].set_result({"durum": "ok", "sayfa": 5})
        await asyncio.wait_for(gorev, timeout=2.0)

        assert params.sonuclar == [{"durum": "ok", "sayfa": 5}]
        assert call_id not in futures

    asyncio.run(_run())


def test_arac_zaman_asimi():
    async def _run():
        futures: dict[str, asyncio.Future] = {}
        # pencere_kapat: plan zaman aşımı 8 sn, iç bekleme 8-0.5=7.5 sn —
        # testte hızlı olması için ZAMAN_ASIMLARI'nı geçici düşürüyoruz.
        import araclar

        eski = araclar.ZAMAN_ASIMLARI["pencere_kapat"]
        araclar.ZAMAN_ASIMLARI["pencere_kapat"] = 1.5
        try:
            handler = tahta_arac_handler_olustur("pencere_kapat", futures)
            llm = SahteLLM()
            params = SahteFunctionCallParams(
                function_name="pencere_kapat", tool_call_id="tc2", arguments={"hedef": "youtube"}, llm=llm
            )
            t0 = asyncio.get_event_loop().time()
            await asyncio.wait_for(handler(params), timeout=3.0)
            sure = asyncio.get_event_loop().time() - t0
            assert params.sonuclar == [TAHTA_YANIT_VERMEDI]
            assert sure < 1.5  # iç bekleme (timeout - 0.5) kadar sürmeli, plan değerinden az
        finally:
            araclar.ZAMAN_ASIMLARI["pencere_kapat"] = eski

    asyncio.run(_run())
