"""farabi-embed — bge-m3 gömme + bge-reranker-v2-m3 yeniden sıralama servisi.

2026-10-04: Farabi'nin iki RTX 3060'ı tamamen Ollama'da (qwen3.8:27b), RAG
modelleri CPU'ya itilmişti (reranker CPU'da ~10 sn/soru → kapalıydı). Bu
servis aynı modelleri bilgehan'ın GPU'larında çalıştırır (dağılım aşağıda);
Farabi `server/uzak_model.py` ile HTTP üzerinden çağırır, pgvector ve LLM
Farabi'de kalır.

Davranış Farabi'deki yerel kullanımla birebir aynı tutuldu: SentenceTransformer
`.encode(normalize_embeddings=...)`, CrossEncoder `.predict()` (varsayılan
aktivasyon, skor 0..1 — rag.py'deki ESIK_RERANK 0,5 bu ölçekte).

Kart/hassasiyet (2026-10-04 ölçümü, 30 aday × ~625 token):
  GTX 1660 Ti fp16 19,4 sn | fp32 4,4 sn   (TU116'da tensor çekirdeği yok —
  RTX 3060    fp16  0,7 sn | fp32 2,1 sn    fp16 orada fp32'den YAVAŞ)
→ reranker (üretimde kullanılan tek parça) RTX 3060'ta fp16; gömme (yalnızca
toplu indeksleme için) 1660 Ti'de fp32. Cihazlar PCI sırasıyla (servis
dosyasında CUDA_DEVICE_ORDER=PCI_BUS_ID): cuda:0 = 1660 Ti, cuda:1 = 3060.

Her model kendi kilidiyle sıraya alınır (aynı kartta iki istek VRAM'i
ikiye katlamasın); iki model farklı kartlarda olduğundan birbirini beklemez.
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
EMBED_DEVICE = os.environ.get("FARABI_EMBED_DEVICE", "cuda:0")
EMBED_FP16 = os.environ.get("FARABI_EMBED_FP16", "0") == "1"
RERANK_DEVICE = os.environ.get("FARABI_RERANK_DEVICE", "cuda:1")
RERANK_FP16 = os.environ.get("FARABI_RERANK_FP16", "1") == "1"
ANAHTAR = os.environ.get("FARABI_EMBED_ANAHTAR", "")
MAKS_METIN = 256  # tek istekte en fazla metin/çift
MAKS_KARAKTER = 20_000  # tek metin üst sınırı (OOM koruması)

_embed_kilit = threading.Lock()
_rerank_kilit = threading.Lock()
_sayac = {"embed": 0, "rerank": 0, "hata": 0}
_son_ms: dict[str, int | None] = {"embed": None, "rerank": None}
_baslangic = time.time()

embed_model = SentenceTransformer(EMBED_MODEL, device=EMBED_DEVICE)
reranker = CrossEncoder(RERANK_MODEL, device=RERANK_DEVICE)
if EMBED_FP16 and EMBED_DEVICE.startswith("cuda"):
    embed_model.half()
if RERANK_FP16 and RERANK_DEVICE.startswith("cuda"):
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
        with _embed_kilit, torch.inference_mode():
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
        with _rerank_kilit, torch.inference_mode():
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
    gpu = []
    for i in range(torch.cuda.device_count() if torch.cuda.is_available() else 0):
        bos, toplam = torch.cuda.mem_get_info(i)
        gpu.append({
            "cihaz": f"cuda:{i}",
            "ad": torch.cuda.get_device_name(i),
            "vram_kullanilan_mib": round((toplam - bos) / 2**20),
            "vram_toplam_mib": round(toplam / 2**20),
        })
    return {
        "durum": "ok",
        "embed_model": EMBED_MODEL,
        "rerank_model": RERANK_MODEL,
        "embed_cihaz": f"{EMBED_DEVICE} {'fp16' if EMBED_FP16 else 'fp32'}",
        "rerank_cihaz": f"{RERANK_DEVICE} {'fp16' if RERANK_FP16 else 'fp32'}",
        "calisma_suresi_sn": round(time.time() - _baslangic),
        "sayaclar": dict(_sayac),
        "son_ms": dict(_son_ms),
        "gpu": gpu,
    }
