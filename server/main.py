"""server/main.py — Faz 1 API iskeleti (docs/mimari.md §9, §15 [1]).

/health, /ready, /api/egitim/question, /api/egitim/kitaplar,
/api/egitim/ders_kaydi_yedek var. mimari.md §9'da listelenen geri kalanı
(lesson/start, teacher/command, WS /ws/classroom/{id}) henüz yok. Ses YOK ve
gelmeyecek — Gemini Live kalıcı karar (mimari.md §14), bu server yalnızca
metin tabanlı RAG cevabı üretir.

Çalıştırma:
    venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
(server/ dizininden, flat import'lar bu yüzden paket değil doğrudan modül.)
"""

import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

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
# GPU'ya taşındı. 2026-08-12'ye kadar tek kartta ikisi birden sığmıyordu
# çünkü qwen2.5:14b (Ollama) o zaman her iki karta da otomatik yayılıyordu;
# embedding/reranker bu yüzden ayrı kartlara bölünmüştü. 2026-08-12'de
# Ollama'nın systemd servisi kendi kartına (CUDA_VISIBLE_DEVICES) sabitlendi
# — artık bu servisin gördüğü tek kart tamamen boş, ikisi de aynı kartta
# rahatça sığıyor. CUDA_DEVICE_ORDER=PCI_BUS_ID olmadan CUDA'nın kendi kart
# numaralandırması nvidia-smi'ninkiyle TERS olabiliyor (bununla debug edildi,
# bkz. farabi-api.service) — bu yüzden hem burada hem ollama.service'te
# CUDA_DEVICE_ORDER açıkça PCI_BUS_ID'ye sabitlendi, "cuda:0" ne demek
# belirsiz kalmasın.
EMBED_DEVICE = "cuda:0"
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


class DersKaydiYedek(BaseModel):
    derslik: str = Field(..., max_length=50)
    dosya_adi: str = Field(..., max_length=200)
    # Bir ders kaydı metni birkaç yüz KB'ı geçmez; 2MB geniş bir tavan.
    icerik: str = Field(..., max_length=2_000_000)


YEDEK_DIR = Path(__file__).resolve().parent / "yedekler" / "ders_kaydi"
# Ağdan gelen derslik/dosya_adi doğrudan dosya yoluna giriyor — path
# traversal'a karşı sıkı doğrulama şart. "/" bu kümede YOK (çok segmentli
# traversal engellenir); tek başına ".." gibi bir değer regex'i geçebilir,
# bu yüzden aşağıda ayrıca is_relative_to ile kapsam dışına çıkmadığı
# doğrulanıyor (regex TEK BAŞINA yeterli değil).
_GUVENLI_AD = re.compile(r"^[A-Za-z0-9ÇĞİÖŞÜçğıöşü_.-]+$")


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


@app.post("/api/egitim/ders_kaydi_yedek")
def ders_kaydi_yedek(istek: DersKaydiYedek):
    """Client, oturum kapanışında (`_temiz_kapan`) kendi ders kaydı dosyasının
    içeriğini buraya tek seferlik yedekler (client/core/transcript.py,
    `logs/ders/*.txt`) — tahtanın diski kaybolsa bile ders kaydı elde kalsın
    diye. Yalnızca yedek: hiçbir şey bunu geri OKUMUYOR (client kendi
    hafızası için kendi yerel dosyalarını kullanıyor, bkz.
    actions/ders_hafizasi.py). DB'ye gömülmez, düz dosya olarak saklanır —
    "dosya içeriği DB'ye gömülmez" ilkesiyle aynı ruhta."""
    if not _GUVENLI_AD.match(istek.derslik) or not _GUVENLI_AD.match(istek.dosya_adi):
        raise HTTPException(status_code=400, detail="Geçersiz derslik/dosya_adi")
    if not istek.dosya_adi.endswith(".txt"):
        raise HTTPException(status_code=400, detail="dosya_adi .txt ile bitmeli")

    # KRİTİK: containment SABİT YEDEK_DIR'e göre kontrol edilmeli — derslik'in
    # kendisi zaten YEDEK_DIR dışına taşımış olabilir (ör. derslik=".."),
    # hedef_dizin'e göre kontrol etmek bu durumda traversal'ı KAÇIRIR (bulundu
    # ve düzeltildi: canlı test ".." ile YEDEK_DIR'in bir üstüne dosya yazdı).
    yedek_dir_r = YEDEK_DIR.resolve()
    hedef_dizin = (YEDEK_DIR / istek.derslik).resolve()
    if not hedef_dizin.is_relative_to(yedek_dir_r):
        raise HTTPException(status_code=400, detail="Geçersiz derslik")
    hedef_dizin.mkdir(parents=True, exist_ok=True)
    hedef_yol = (hedef_dizin / istek.dosya_adi).resolve()
    if not hedef_yol.is_relative_to(yedek_dir_r):
        raise HTTPException(status_code=400, detail="Geçersiz dosya yolu")

    hedef_yol.write_text(istek.icerik, encoding="utf-8")
    return {"status": "ok"}
