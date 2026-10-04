"""farabi-embed — bge-m3 gömme + bge-reranker-v2-m3 yeniden sıralama servisi.

2026-10-04: Farabi'nin iki RTX 3060'ı tamamen Ollama'da (qwen3.8:27b), RAG
modelleri CPU'ya itilmişti (reranker CPU'da ~10 sn/soru → kapalıydı). Bu
servis aynı modelleri bilgehan'ın GTX 1660 Ti'sinde (6 GB) fp16 çalıştırır;
Farabi `server/uzak_model.py` ile HTTP üzerinden çağırır, pgvector ve LLM
Farabi'de kalır.

Davranış Farabi'deki yerel kullanımla birebir aynı tutuldu: SentenceTransformer
`.encode(normalize_embeddings=...)`, CrossEncoder `.predict()` (varsayılan
aktivasyon, skor 0..1 — rag.py'deki ESIK_RERANK 0,5 bu ölçekte), fp16 (40
soruluk ölçümde fp32'den farkı ihmal edilebilir, bkz. Farabi DECISIONS.md
2026-10-03).

GPU tek kart: model çağrıları kilitle sıraya alınır (aynı anda iki istek
VRAM'i ikiye katlamasın).
"""

import os
import threading
import time

import torch
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import CrossEncoder, SentenceTransformer

EMBED_MODEL = os.environ.get("FARABI_EMBED_MODEL", "BAAI/bge-m3")
RERANK_MODEL = os.environ.get("FARABI_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
DEVICE = os.environ.get("FARABI_EMBED_DEVICE", "cuda:0")
ANAHTAR = os.environ.get("FARABI_EMBED_ANAHTAR", "")
MAKS_METIN = 256  # tek istekte en fazla metin/çift
MAKS_KARAKTER = 20_000  # tek metin üst sınırı (OOM koruması)

_kilit = threading.Lock()
_sayac = {"embed": 0, "rerank": 0, "hata": 0}
_son_ms: dict[str, int | None] = {"embed": None, "rerank": None}
_baslangic = time.time()

embed_model = SentenceTransformer(EMBED_MODEL, device=DEVICE)
reranker = CrossEncoder(RERANK_MODEL, device=DEVICE)
if DEVICE.startswith("cuda"):
    embed_model.half()
    reranker.model.half()
# Isınma: ilk gerçek istek CUDA çekirdek derlemesini ödemesin.
embed_model.encode("ısınma sorgusu", normalize_embeddings=True)
reranker.predict([("ısınma sorgusu", "ısınma için örnek kaynak metni.")])

app = FastAPI(title="farabi-embed")


def _yetki(anahtar: str | None) -> None:
    if ANAHTAR and anahtar != ANAHTAR:
        raise HTTPException(status_code=401, detail="anahtar gecersiz")


def _kirp(metin: str) -> str:
    return metin[:MAKS_KARAKTER]


class EmbedIstek(BaseModel):
    metinler: list[str] = Field(..., min_length=1, max_length=MAKS_METIN)
    normalize: bool = True


class RerankIstek(BaseModel):
    ciftler: list[tuple[str, str]] = Field(..., min_length=1, max_length=MAKS_METIN)


@app.post("/embed")
def embed(istek: EmbedIstek, x_farabi_embed_key: str | None = Header(default=None)):
    _yetki(x_farabi_embed_key)
    t0 = time.perf_counter()
    try:
        with _kilit, torch.inference_mode():
            v = embed_model.encode(
                [_kirp(m) for m in istek.metinler],
                normalize_embeddings=istek.normalize,
                show_progress_bar=False,
            )
    except Exception as e:
        _sayac["hata"] += 1
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e
    _sayac["embed"] += 1
    _son_ms["embed"] = int((time.perf_counter() - t0) * 1000)
    return {"vektorler": v.astype("float32").tolist()}


@app.post("/rerank")
def rerank(istek: RerankIstek, x_farabi_embed_key: str | None = Header(default=None)):
    _yetki(x_farabi_embed_key)
    t0 = time.perf_counter()
    try:
        with _kilit, torch.inference_mode():
            s = reranker.predict(
                [(_kirp(a), _kirp(b)) for a, b in istek.ciftler],
                show_progress_bar=False,
            )
    except Exception as e:
        _sayac["hata"] += 1
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e
    _sayac["rerank"] += 1
    _son_ms["rerank"] = int((time.perf_counter() - t0) * 1000)
    return {"skorlar": [float(x) for x in s]}


@app.get("/saglik")
def saglik():
    gpu = None
    if torch.cuda.is_available():
        bos, toplam = torch.cuda.mem_get_info()
        gpu = {
            "ad": torch.cuda.get_device_name(0),
            "vram_kullanilan_mib": round((toplam - bos) / 2**20),
            "vram_toplam_mib": round(toplam / 2**20),
        }
    return {
        "durum": "ok",
        "embed_model": EMBED_MODEL,
        "rerank_model": RERANK_MODEL,
        "cihaz": DEVICE,
        "calisma_suresi_sn": round(time.time() - _baslangic),
        "sayaclar": dict(_sayac),
        "son_ms": dict(_son_ms),
        "gpu": gpu,
    }
