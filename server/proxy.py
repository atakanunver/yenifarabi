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

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, Field

import saglayicilar

router = APIRouter()


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
        veri = await dosya.read()
        mime = dosya.content_type or "image/jpeg"
        metin = saglayicilar.gorsel_uret(gorev, istem, veri, mime)
        return UretimYanit(status="ok", metin=metin,
                            latency_ms=int((time.perf_counter() - t0) * 1000), request_id=request_id)
    except Exception as e:
        return UretimYanit(status="hata", hata=f"{type(e).__name__}: {e}",
                            latency_ms=int((time.perf_counter() - t0) * 1000), request_id=request_id)
