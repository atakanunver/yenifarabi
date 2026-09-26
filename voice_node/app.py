"""voice_node/app.py — Faz 1b: FastAPI giriş noktası.

`loguru`'yu INFO'ya indirmek `pipecat` import edilmeden ÖNCE yapılmalı —
pipecat kendi modülleri import edilirken zaten loguru'ya DEBUG seviyeli
satırlar yazıyor (plan "Loglama" — `stt.py:452`, `base_llm.py:324`
transkript/LLM bağlamını DEBUG'da basıyor; INFO'da bunlar hiç oluşmaz)."""

from __future__ import annotations

import ipaddress
import logging
import os
import sys

from loguru import logger as _loguru_logger

_loguru_logger.remove()
_loguru_logger.add(sys.stderr, level=os.environ.get("LOGURU_LEVEL", "INFO"))

logging.basicConfig(
    level=os.environ.get("LOGURU_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

import asyncio
from contextlib import asynccontextmanager

import stt_paylasimli
from fastapi import FastAPI, WebSocket
from oturum import (
    WHISPER_COMPUTE,
    WHISPER_DEVICE,
    WHISPER_MODEL_DIR,
    oturum_calistir,
)

log = logging.getLogger("ses_dugumu.app")


@asynccontextmanager
async def _yasam_dongusu(_app: FastAPI):
    log.info("ses düğümü başlıyor — Whisper ön-ısıtma (%s, %s, %s)",
              WHISPER_MODEL_DIR, WHISPER_DEVICE, WHISPER_COMPUTE)
    try:
        await asyncio.to_thread(stt_paylasimli.isindir, WHISPER_MODEL_DIR, WHISPER_DEVICE, WHISPER_COMPUTE)
        log.info("Whisper ön-ısıtma tamamlandı")
    except Exception as e:  # noqa: BLE001 — ön-ısıtma başarısız olsa da servis ayağa kalkmalı (CLAUDE.md Kural 2)
        log.error("Whisper ön-ısıtma başarısız: %s: %s", type(e).__name__, e)
    yield


app = FastAPI(title="Farabi ses düğümü", lifespan=_yasam_dongusu)


def _izinli_aglar() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    ham = os.environ.get("IZINLI_AGLAR", "192.168.23.0/24,127.0.0.1/32,::1/128")
    aglar = []
    for parca in ham.split(","):
        parca = parca.strip()
        if not parca:
            continue
        try:
            aglar.append(ipaddress.ip_network(parca, strict=False))
        except ValueError:
            log.warning("IZINLI_AGLAR içinde geçersiz ağ tanımı: %r", parca)
    return aglar


_AGLAR = _izinli_aglar()


def _adres_izinli_mi(host: str | None) -> bool:
    if not host:
        return False
    try:
        adres = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(adres in ag for ag in _AGLAR)


@app.get("/health")
def health() -> dict:
    return {"durum": "ok"}


@app.websocket("/ses")
async def ses_websocket(websocket: WebSocket) -> None:
    host = websocket.client.host if websocket.client else None
    if not _adres_izinli_mi(host):
        log.warning("ses websocket reddi — izinli olmayan adres: %s", host)
        await websocket.close(code=4003)
        return

    board_key = websocket.headers.get("x-farabi-board-key")
    if not board_key:
        log.warning("ses websocket reddi — X-Farabi-Board-Key eksik")
        await websocket.close(code=4001)
        return

    kip = websocket.query_params.get("kip", "ogretmenli")
    ders = websocket.query_params.get("ders")

    await websocket.accept()
    log.info("tahta bağlandı adres=%s kip=%s", host, kip)
    try:
        await oturum_calistir(websocket, board_key=board_key, kip=kip, ders=ders)
    except Exception as e:  # noqa: BLE001 — bir oturumun çökmesi süreci/diğer tahtaları etkilememeli
        log.error("oturum hatası: %s: %s", type(e).__name__, e)
