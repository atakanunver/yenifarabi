"""server/main.py — Faz 1 API iskeleti (docs/mimari.md §9, §15 [1]).

Şu an yalnızca /health, /ready, /api/egitim/question var. mimari.md §9'da
listelenen geri kalanı (lesson/start, teacher/command, WS /ws/classroom/{id})
henüz yok — STT/TTS/ders akışı Faz 1'in sonraki adımları.

Çalıştırma:
    venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
(server/ dizininden, flat import'lar bu yüzden paket değil doğrudan modül.)
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import CrossEncoder, SentenceTransformer

import db
from rag import EMBED_MODEL, RERANK_MODEL, RagMotoru

DB_HOST = "127.0.0.1"
DB_NAME = "farabi"
DB_USER = "farabi"

# CPU'da ölçüldü (2026-08-11): 20 adayı rerank etmek tek başına 4-10sn
# sürüyor, mimari.md'nin "ilk cevap ≤2sn" hedefini tek başına aşıyor.
# GPU'ya taşındı — ama tek kartta ikisi birden sığmadı: bge-m3 tek başına
# ~3.5GB VRAM alıyor (mimari.md §5'in tahmin ettiği ~2GB'dan fazla), her
# kartta qwen2.5:14b sonrası yalnızca ~4GB boş kalıyor. Bu yüzden ikiye
# bölündü: embedding GPU 1'de, reranker GPU 0'da.
EMBED_DEVICE = "cuda:1"
RERANK_DEVICE = "cuda:0"

durum: dict = {"hazir": False, "motor": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Modeller yükleniyor: {EMBED_MODEL} ({EMBED_DEVICE}), {RERANK_MODEL} ({RERANK_DEVICE})…")
    embed_model = SentenceTransformer(EMBED_MODEL, device=EMBED_DEVICE)
    reranker = CrossEncoder(RERANK_MODEL, device=RERANK_DEVICE)
    durum["motor"] = RagMotoru(embed_model, reranker)
    db.baslat(DB_HOST, DB_NAME, DB_USER)
    durum["hazir"] = True
    print("Sunucu hazır.")
    yield
    db.kapat()


app = FastAPI(title="Farabi Brain API", lifespan=lifespan)


class SoruIstek(BaseModel):
    kitap_id: int
    soru: str


class Kaynak(BaseModel):
    book: str
    page: int
    chunk_id: int


class SoruYanit(BaseModel):
    status: str
    answer: str | None = None
    sources: list[Kaynak] = []
    audio_url: str | None = None
    latency_ms: int
    request_id: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if not durum["hazir"]:
        raise HTTPException(status_code=503, detail="Modeller/DB henüz hazır değil")
    return {"status": "ready"}


@app.post("/api/egitim/question", response_model=SoruYanit)
def soru_sor(istek: SoruIstek):
    if not durum["hazir"]:
        raise HTTPException(status_code=503, detail="Sunucu henüz hazır değil")

    request_id = str(uuid.uuid4())
    with db.baglanti() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT sinif, ders FROM kitap WHERE id = %s", (istek.kitap_id,))
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"kitap_id={istek.kitap_id} bulunamadı")
        sinif, ders = row
        kitap_adi = f"{sinif}. Sınıf {ders}"

        sonuc = durum["motor"].sorgula(conn, istek.kitap_id, istek.soru, sinif=sinif, ders=ders)

    kaynaklar = [
        Kaynak(book=kitap_adi, page=k["sayfa"], chunk_id=k["chunk_id"])
        for k in sonuc["sources"]
    ]
    return SoruYanit(
        status=sonuc["status"],
        answer=sonuc.get("answer"),
        sources=kaynaklar,
        audio_url=None,  # TTS henüz yok — mimari.md §15 [6]
        latency_ms=sonuc["latency_ms"],
        request_id=request_id,
    )
