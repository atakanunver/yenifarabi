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

import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sentence_transformers import CrossEncoder, SentenceTransformer

import auth
import client_durum
import db
import ders_hafizasi
import dosya
import icerik
import kazanim
import proxy
import uzak_model
import ders_plani
import belge_arsiv
import webui
import yks
from rag import EMBED_MODEL, RERANK_MODEL, RagMotoru
from version import VERSION, major_version

DB_HOST = "127.0.0.1"
DB_NAME = os.environ.get("FARABI_DB_NAME", "farabi")
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
# 2026-10-03 (kullanıcı kararı): RAG GPU'dan kaldırıldı — iki RTX 3060
# tamamen Ollama'ya (qwen3.8:27b) ayrıldı, öncelik Ollama. False iken
# embedding/reranker hiç yüklenmez (GPU'ya dokunulmaz), veritabanı ve kod
# diskte kalır; /api/egitim/question "hata" döner, tahtadaki kitap_sorusu
# sessizce kısıtlı metne düşer (ders bozulmaz). Geri açmak: True + restart
# (ve Ollama'nın GPU 0 payını yeniden değerlendir — DECISIONS.md).
#
# 2026-10-03 (ikinci karar, kullanıcı): RAG CPU'da yeniden AÇIK — iki GPU
# Ollama'da kalır. Open WebUI Farabi modları /api/webui/ara üzerinden
# kitap/mevzuat parçası alır (docs/superpowers/specs/2026-10-03-openwebui-
# farabi-modlar-design.md). CPU ölçümü DECISIONS.md 2026-10-03'te.
RAG_AKTIF = True

EMBED_DEVICE = "cpu"
RERANK_DEVICE = "cpu"
# Reranker YÜKLENMEZ (2026-10-03, kullanıcı kararı C): CPU'da 20 adayın
# rerank'i medyan 9,9 sn sürdü (DECISIONS.md). Open WebUI yalnızca vektör
# aramasıyla çalışır (RagMotoru.ara). Tahta yolu (sorgula) reranker'sız
# çalışamaz → /api/egitim/question bugünkü gibi "hata" döner (davranış
# değişmez). Geri açmak: True + restart (CPU'da ~10 sn/soru).
RERANK_YUKLE = False

# 2026-10-04: bge-m3 + reranker bilgehan'ın GTX 1660 Ti'sinde (farabi-embed,
# kaynak `embed_servisi/`). URL/anahtar systemd drop-in'inden gelir
# (/etc/systemd/system/farabi-api.service.d/embed.conf — anahtar repoya
# girmez). URL boşsa eski davranış: yerel CPU, RERANK_YUKLE'ye göre.
# Ayarlıysa gömme + rerank tamamen uzakta (aşağıdaki lifespan notu).
UZAK_EMBED_URL = os.environ.get("FARABI_EMBED_URL", "").strip()
UZAK_EMBED_ANAHTAR = os.environ.get("FARABI_EMBED_ANAHTAR", "")

durum: dict = {"hazir": False, "motor": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if RAG_AKTIF:
        if RERANK_YUKLE:
            print(f"Modeller yükleniyor: {EMBED_MODEL} ({EMBED_DEVICE}), {RERANK_MODEL} ({RERANK_DEVICE})…")
        else:
            print(f"Modeller yükleniyor: {EMBED_MODEL} ({EMBED_DEVICE}); reranker yüklenmedi (RERANK_YUKLE=False)…")
        # fp16 (2026-10-03): GPU 0'ı Ollama (qwen3.8:27b, iki karta
        # yayılı) ile paylaşıyor; fp32'de ikisi ~4,5-5,7 GB tutuyordu, model
        # tamamen GPU'ya sığmıyordu. BAAI'nin kendi örnekleri de bu modelleri
        # fp16 çalıştırır; 40 soruluk ölçümle doğrulandı (DECISIONS.md). Sorgu
        # vektörü pgvector'a giderken float32'ye çevrilir (pgvector.Vector).
        reranker = None
        if UZAK_EMBED_URL:
            # 2026-10-04 (kullanıcı kararı): "Farabi CPU boşta kalsın, tüm RAG
            # bilgehan'da" — gömme de rerank de uzakta, Farabi'de HİÇ model
            # yüklenmez (yerel geri dönüş yok). bilgehan kapalıysa arama
            # "hata" döner: Open WebUI kaynaksız sürer, tahta kısıtlı metne düşer.
            embed_model, reranker = uzak_model.olustur(UZAK_EMBED_URL, UZAK_EMBED_ANAHTAR)
            print(f"Uzak gömme + rerank: {UZAK_EMBED_URL} — Farabi'de model yüklenmedi")
        else:
            embed_model = SentenceTransformer(EMBED_MODEL, device=EMBED_DEVICE)
            if EMBED_DEVICE.startswith("cuda"):
                # fp16 yalnızca GPU'da anlamlı; CPU'da fp32 kalır.
                embed_model.half()
        if not UZAK_EMBED_URL and RERANK_YUKLE:
            reranker = CrossEncoder(RERANK_MODEL, device=RERANK_DEVICE)
            if RERANK_DEVICE.startswith("cuda"):
                reranker.model.half()
        durum["motor"] = RagMotoru(embed_model, reranker)
        webui.MOTOR = durum["motor"]

        # Isınma sorgusu — ölçüldü (2026-08-13): servis yeniden başladıktan
        # sonraki İLK gerçek soru ~13.6sn sürüyor (sonrakiler ~0.85sn), muhtemelen
        # GPU'nun ilk çağrıda CUDA kernellerini derlemesi/ısınması. Client
        # (kitap_sorusu.py) POST için 10sn timeout kullanıyor, yani soğuk servis
        # sonrası ilk ders sorusu timeout'a düşüp sessizce _SINIRLI_DEVAM'a
        # kayabilirdi. Bu maliyeti burada, servis ayağa kalkarken (hiç öğrenci
        # yokken) ödüyoruz; DB'ye/`metrik` veya `soru_log`'a yazmaması için
        # RagMotoru.sorgula() yerine embed+rerank doğrudan çağrılıyor — sahte bir
        # istek gerçek sorgu istatistiklerini kirletmesin diye.
        try:
            _t0 = time.perf_counter()
            print("Isınma sorgusu: modeller ilk kez çalıştırılıyor…")
            embed_model.encode("ısınma sorgusu", normalize_embeddings=True)
            if reranker is not None:
                reranker.predict([("ısınma sorgusu", "ısınma için örnek kaynak metni.")])
            print(f"Isınma tamamlandı ({time.perf_counter() - _t0:.1f}sn) — gömme {UZAK_EMBED_URL or EMBED_DEVICE} hazır.")
        except Exception as e:
            print(f"UYARI: ısınma sorgusu başarısız oldu ({type(e).__name__}: {e}) — ilk gerçek istek yavaş olabilir.")

    else:
        print("RAG kapalı (RAG_AKTIF=False) — embedding/reranker yüklenmedi, GPU kullanılmıyor.")

    db.baslat(DB_HOST, DB_NAME, DB_USER)
    durum["hazir"] = True
    print("Sunucu hazır.")
    yield
    db.kapat()


app = FastAPI(title="Farabi Brain API", lifespan=lifespan)
# Faz 2 (server-taşıma) — ders_icerigi + pdf_sayfa + yks + bulut LLM proxy;
# durum["hazir"] kontrolüne bağlı değil, her biri kendi dosya/DB/API-anahtar
# kontrolünü kendi yapar (RAG modeli gerekmez).
app.include_router(icerik.router)
app.include_router(yks.router)
app.include_router(kazanim.router)
app.include_router(proxy.router)
app.include_router(ders_plani.router)
app.include_router(dosya.router)
# 10 tahtaya ölçekleme (analiz raporu §5/§6) — durum["hazir"]'a bağlı değil,
# yalnızca kendi tablosunu okur/yazar, RAG modeli gerekmez.
app.include_router(client_durum.router)
# ders_hafizasi taşıması (2026-08-18) — durum["hazir"]'a bağlı değil, yalnızca
# yedekler/ders_kaydi/ dosyalarını okur, RAG modeli gerekmez.
app.include_router(ders_hafizasi.router)
# Open WebUI Farabi modları (2026-10-03) — kendi anahtarıyla korunur
# (webui.webui_anahtari_dogrula), tahta auth'una bağlı DEĞİL.
app.include_router(webui.router)
app.include_router(belge_arsiv.router)  # Atos "Belge Kalıcı Kayıt" aracı
# GeoGebra çevrimdışı paketi (2026-09-25) — client/actions/geogebra.py'nin
# yerel köprüsü dosyaları buradan çekip tahtada önbelleğe alır (paket ~120 MB,
# git'e girmez, her tahtaya ayrı kopyalanmaz). Auth YOK, bilerek: içerik
# GeoGebra'nın herkese açık, ücretsiz dağıtımı — öğrenci/ders verisi değil.
# Dizin yoksa yol hiç bağlanmaz, tahta yerel paket yollarına düşer.
GEOGEBRA_DIR = icerik.DATA_DIR / "geogebra" / "GeoGebra"
if GEOGEBRA_DIR.is_dir():
    app.mount("/geogebra", StaticFiles(directory=GEOGEBRA_DIR), name="geogebra")


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
    # FAZ 1 (2026-09-02): chunk_egitim.id ile chunk_tablo.id ayrı dizilerden
    # geliyor — tablo kaynakları NEGATİF chunk_id ile döner (-12 =
    # chunk_tablo.id 12), bkz. rag.py. Alan tipi değişmedi (int), mevcut
    # istemciler etkilenmez.
    chunk_id: int
    # Yeni, VARSAYILANLI alan — geriye dönük uyumlu: eski client'lar bu
    # alanı hiç okumuyor (client/actions/kitap_sorusu.py yalnızca
    # `page` ve `book` kullanıyor, koddan doğrulandı).
    tur: str = "metin"   # "metin" | "tablo"


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
    # FAZ 1 (IMPLEMENT) — kasıtlı olarak auth DIŞI: systemd/izleme araçları
    # (`systemctl status`, gelecekteki bir healthcheck) board anahtarı
    # taşımaz; bu uç yalnızca "süreç ayakta mı" der, ders/kitap/tahta
    # içeriği DÖNDÜRMEZ — korunacak bir sır yok. Bkz. FAZ 1 raporu
    # "AUTH KAPSAMI" bölümü.
    return {"status": "ok"}


@app.get("/ready")
def ready():
    # Aynı gerekçe — bkz. health() üstündeki not.
    if not durum["hazir"]:
        raise HTTPException(status_code=503, detail="Modeller/DB henüz hazır değil")
    return {"status": "ready"}


@app.get("/api/version", dependencies=[Depends(auth.dogrula_tahta)])
def version_bilgisi(
    x_farabi_client_version: str | None = Header(
        default=None, alias="X-Farabi-Client-Version"
    ),
):
    """Check the calling board's API compatibility before it starts work."""
    if not x_farabi_client_version:
        raise HTTPException(
            status_code=400,
            detail="X-Farabi-Client-Version header eksik; istemci güncellenmeli.",
        )

    try:
        client_major = major_version(x_farabi_client_version)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Geçersiz istemci sürümü: {x_farabi_client_version!r}",
        )

    if client_major != major_version(VERSION):
        raise HTTPException(
            status_code=426,
            detail={
                "hata": "MAJOR sürüm uyumsuzluğu",
                "client_version": x_farabi_client_version,
                "server_version": VERSION,
            },
        )

    return {
        "status": "ok",
        "client_version": x_farabi_client_version,
        "server_version": VERSION,
        "uyari": (
            "MINOR/PATCH sürümleri farklı; planlı güncelleme önerilir."
            if x_farabi_client_version != VERSION
            else None
        ),
    }


@app.post("/api/egitim/question", response_model=SoruYanit,
          dependencies=[Depends(auth.dogrula_tahta)])
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

        if durum["motor"] is None or durum["motor"].reranker is None:
            # RAG kapalı ya da reranker yüklenmedi (2026-10-03 kararı C) —
            # tahta yolu reranker'sız çalışmaz; bugünkü davranış korunur.
            return SoruYanit(status="hata", latency_ms=0, request_id=request_id)
        sonuc = durum["motor"].sorgula(conn, istek.kitap_id, istek.soru, sinif=sinif, ders=ders)

    kaynaklar = [
        Kaynak(book=kitap_adi, page=k["sayfa"], chunk_id=k["chunk_id"],
               tur=k.get("tur", "metin"))
        for k in sonuc["sources"]
    ]
    return SoruYanit(
        status=sonuc["status"],
        answer=sonuc.get("answer"),
        sources=kaynaklar,
        latency_ms=sonuc["latency_ms"],
        request_id=request_id,
    )


@app.get("/api/egitim/kitaplar", response_model=list[KitapBilgisi],
         dependencies=[Depends(auth.dogrula_tahta)])
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


@app.post("/api/egitim/ders_kaydi_yedek", dependencies=[Depends(auth.dogrula_tahta)])
def ders_kaydi_yedek(istek: DersKaydiYedek):
    """Client, oturum kapanışında (`_temiz_kapan`) kendi ders kaydı dosyasının
    içeriğini buraya tek seferlik yedekler (client/core/transcript.py,
    `logs/ders/*.txt`) — tahtanın diski kaybolsa bile ders kaydı elde kalsın
    diye. Bu docstring önceden "hiçbir şey bunu geri OKUMUYOR" diyordu —
    2026-08-18'de eklenen `server/ders_hafizasi.py` tam olarak bu dizini
    (`yedekler/ders_kaydi/<derslik>/`) okuyor, o iddia artık YANLIŞ; düzeltme
    burada kayıtlı. DB'ye gömülmez, düz dosya olarak saklanır — "dosya
    içeriği DB'ye gömülmez" ilkesiyle aynı ruhta."""
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
