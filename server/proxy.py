"""server/proxy.py — bulut LLM proxy (saglayicilar.py havuzunun HTTP yüzü).

client/actions/file_processor.py, web_search.py, youtube_video.py,
tools/kitap_ozet.py, tools/sembol_temizle.py, benchmark/soru_taslak.py'nin
hepsi aynı deseni kullanıyordu: `core/saglayicilar.metin_uret`/`gorsel_uret`'i
DOĞRUDAN import edip çağırmak. Anahtarlar server'a taşındığı için (Faz 9)
bu çağrı artık yerel değil, HTTP olmalı — bu dosya o tek HTTP yüzeyi.

Görev adları (`gorev`) client'takiyle birebir aynı: saglayicilar.py'nin
GOREV_ZINCIRLERI sözlüğündeki anahtarlar (gorsel, arama_sentez, belge_ozet,
video_ozet, kitap_ozet, sembol_duzelt, soru_taslak) — yeni bir görev eklemek
istenirse yalnızca orada tanımlanır, burada değişiklik gerekmez.
"""

import time
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

import auth
import saglayicilar

# FAZ 1 (IMPLEMENT) — bkz. icerik.py'deki aynı değişikliğin notu.
router = APIRouter(dependencies=[Depends(auth.dogrula_tahta)])

# 2026-09-02 (REFACTORING_PLAN R-2, SECURITY_ANALYSIS S-04) — `gorsel_uret`
# yükleme boyutunu HİÇ sınırlamıyordu: `await dosya.read()` dosyanın tamamını
# koşulsuz belleğe alıyordu. `dosya.py`'nin `dosya_isle`'si aynı sınıftan bir
# yüzey ama orada YUKLEME_LIMIT_MB=60 var ve parça parça okunup sınır aşılınca
# hemen durduruluyor — bu uç o korumadan yoksundu. Kimliği doğrulanmış tek bir
# büyük yükleme farabi-api.service'i belleğe boğabilir, servis çökerse TÜM
# tahtaların içerik/RAG yolu düşer.
#
# Değer bilerek `dosya.py` ile AYNI (60) — yeni bir politika icat etmemek için.
# Görsele özel daha dar bir sınır savunulabilir (ölçülen gerçek yük: biyoloji-9
# tam sayfa render'ı, JPEG q85, 277 KB) ama Kural 10 gereği ölçmeden
# daraltılmıyor; buradaki amaç sınırsızlığı bitirmek.
# `dosya.py`'den import EDİLMİYOR: proxy.py bugün yalnızca auth+saglayicilar'a
# bağlı, tek bir sabit için yeni bir modül kenarı eklemeye değmez.
GORSEL_LIMIT_MB = 60
_OKUMA_PARCASI = 1 << 20        # 1 MB — dosya.py ile aynı


class MetinIstek(BaseModel):
    gorev: str
    istem: str = Field(..., max_length=200_000)
    sistem: str | None = None


class UretimYanit(BaseModel):
    status: str  # "ok" | "hata"
    metin: str | None = None
    hata: str | None = None
    latency_ms: int
    request_id: str


@router.post("/api/egitim/metin_uret", response_model=UretimYanit)
def metin_uret_endpoint(istek: MetinIstek) -> UretimYanit:
    t0 = time.perf_counter()
    request_id = str(uuid.uuid4())
    try:
        metin = saglayicilar.metin_uret(istek.gorev, istek.istem, istek.sistem)
        return UretimYanit(status="ok", metin=metin,
                            latency_ms=int((time.perf_counter() - t0) * 1000), request_id=request_id)
    except Exception as e:
        return UretimYanit(status="hata", hata=f"{type(e).__name__}: {e}",
                            latency_ms=int((time.perf_counter() - t0) * 1000), request_id=request_id)


@router.post("/api/egitim/gorsel_uret", response_model=UretimYanit)
async def gorsel_uret_endpoint(
    gorev: str = Form(...),
    istem: str = Form(...),
    dosya: UploadFile = File(...),
) -> UretimYanit:
    t0 = time.perf_counter()
    request_id = str(uuid.uuid4())
    try:
        # Parça parça oku, sınır aşılırsa DERHAL bırak — dosyanın tamamı
        # hiçbir zaman belleğe alınmaz (dosya.py::dosya_isle ile aynı desen).
        sinir = GORSEL_LIMIT_MB * 1024 * 1024
        parcalar: list[bytes] = []
        boyut = 0
        while True:
            parca = await dosya.read(_OKUMA_PARCASI)
            if not parca:
                break
            boyut += len(parca)
            if boyut > sinir:
                # 500 DEĞİL: client'ın Kural 2 düşüş yolu `status`a bakıyor,
                # çıplak bir hata dersi bozardı.
                return UretimYanit(
                    status="hata",
                    hata=f"Görsel {GORSEL_LIMIT_MB}MB sınırını aşıyor.",
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                    request_id=request_id)
            parcalar.append(parca)
        veri = b"".join(parcalar)
        mime = dosya.content_type or "image/jpeg"
        metin = saglayicilar.gorsel_uret(gorev, istem, veri, mime)
        return UretimYanit(status="ok", metin=metin,
                            latency_ms=int((time.perf_counter() - t0) * 1000), request_id=request_id)
    except Exception as e:
        return UretimYanit(status="hata", hata=f"{type(e).__name__}: {e}",
                            latency_ms=int((time.perf_counter() - t0) * 1000), request_id=request_id)
