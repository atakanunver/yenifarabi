"""server/main.py — Faz 1 API iskeleti (docs/mimari.md §9, §15 [1]).

/health, /ready, /api/egitim/question, /api/egitim/kitaplar var. mimari.md
§9'da listelenen geri kalanı (lesson/start, teacher/command, WS
/ws/classroom/{id}) henüz yok. Ses YOK ve gelmeyecek — Gemini Live kalıcı
karar (mimari.md §14), bu server yalnızca metin tabanlı RAG cevabı üretir.

Çalıştırma:
    venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
(server/ dizininden, flat import'lar bu yüzden paket değil doğrudan modül.)
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
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
    # max_length=500: ölçüldü (2026-08-11) — sınırsız uzunlukta bir soru
    # (~6000 karakter, tekrarlı metin) reranker'ı (cuda:0, qwen2.5:14b ile
    # aynı kart) CUDA OOM'a düşürdü. rag.py artık bu tür hataları da
    # yakalayıp `hata` durumu döndürüyor (bkz. rag.py sorgula), ama pahalı
    # bir GPU çağrısını hiç yapmadan reddetmek daha doğrusu — gerçek bir
    # sınıf sorusu birkaç cümleyi aşmaz.
    soru: str = Field(..., max_length=500)


class Kaynak(BaseModel):
    book: str
    page: int
    chunk_id: int


class SoruYanit(BaseModel):
    status: str
    answer: str | None = None
    sources: list[Kaynak] = []
    latency_ms: int
    request_id: str


class KitapBilgisi(BaseModel):
    id: int
    dosya_adi: str
    sinif: int
    ders: str


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
        latency_ms=sonuc["latency_ms"],
        request_id=request_id,
    )


@app.get("/api/egitim/kitaplar", response_model=list[KitapBilgisi])
def kitaplar_listesi():
    """Client bir kitabı yalnızca dosya adıyla tanıyor (`icerik/kitaplar.json`),
    `kitap_id` bilmiyor. `sinif_kitap` tablosu henüz boş (gerçek okul verisi
    yok) — bu yüzden client, dosya adının basename'ine göre eşleşme yapıyor.
    Geçici çözüm; `sinif_kitap` doldurulunca gerçek bağlam çözümüne (tahta_id
    → ders_programi → sinif_kitap) geçilebilir."""
    if not durum["hazir"]:
        raise HTTPException(status_code=503, detail="Sunucu henüz hazır değil")
    with db.baglanti() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, dosya_yolu, sinif, ders FROM kitap ORDER BY id")
            rows = cur.fetchall()
    return [
        KitapBilgisi(id=r[0], dosya_adi=r[1].rsplit("/", 1)[-1], sinif=r[2], ders=r[3])
        for r in rows
    ]
