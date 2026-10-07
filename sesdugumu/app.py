"""farabi2-ses HTTP uygulaması. Motorlar enjekte edilir (testte sahte, üretimde gerçek)."""
import asyncio
import logging
import time

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from .kaliplar import KALIPLAR
from .onbellek import Onbellek

log = logging.getLogger("farabi2-ses")
AZAMI_KARAKTER = 2000


class TTSIstek(BaseModel):
    metin: str


def uygulama_kur(tts, stt, kaliplari_isit: bool = True) -> FastAPI:
    app = FastAPI(title="farabi2-ses")
    onbellek = Onbellek()
    sayac = {"istek": 0}

    if kaliplari_isit:
        for metin in KALIPLAR.values():
            onbellek.koy(metin, tts.sentezle(metin))
        log.info("Kalıp cümleler hazır: %d", len(onbellek))

    @app.get("/saglik")
    async def saglik():
        return {"ok": True, "tts": tts is not None, "stt": stt is not None,
                "onbellek": len(onbellek), "bogulma": getattr(tts, "bogulma_sayisi", 0),
                "istek": sayac["istek"]}

    @app.post("/tts")
    async def tts_uc(istek: TTSIstek):
        metin = istek.metin.strip()
        if not metin or len(metin) > AZAMI_KARAKTER:
            raise HTTPException(400, "metin boş ya da çok uzun")
        sayac["istek"] += 1
        t = time.perf_counter()
        wav = onbellek.al(metin)
        isabet = wav is not None
        if not isabet:
            wav = await asyncio.to_thread(tts.sentezle, metin)
        ms = (time.perf_counter() - t) * 1000
        log.info("tts %s %.0f ms %r", "önbellek" if isabet else "üretim", ms, metin[:60])
        return Response(wav, media_type="audio/wav",
                        headers={"X-Onbellek": "1" if isabet else "0", "X-Uretim-Ms": f"{ms:.0f}"})

    @app.post("/stt")
    async def stt_uc(request: Request):
        veri = await request.body()
        sayac["istek"] += 1
        t = time.perf_counter()
        try:
            metin = await asyncio.to_thread(stt.coz, veri)
        except Exception as e:  # noqa: BLE001 — bozuk WAV, wave.Error vb.
            raise HTTPException(400, f"ses çözülemedi: {e}") from e
        ms = int((time.perf_counter() - t) * 1000)
        log.info("stt %d ms %r", ms, metin[:60])
        return {"metin": metin, "sure_ms": ms}

    return app
