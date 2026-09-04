"""
actions/gorsel_uret.py — Öğretmenin verdiği KONUdan eğitici bir görsel
üretir (metinden görsel, text-to-image) ve tahtada gösterir.

main.py bu aracı `_arkaplan()` ile ateşle-ve-unut (fire-and-forget) şeklinde
çağırır: model hemen "Görsel hazırlanıyor" onayını alır, ders akmaya devam
eder — bu fonksiyon iş parçacığında BİTTİKTEN sonra `player.show_image` ile
görseli ekrana koyar ve `speak()` ile sonucu AYRICA, canlı oturuma yeni bir
mesaj olarak bildirir (aynı desen: `youtube_video.py`'nin özet akışı).

Gemini image generation kullanılıyor — `core/saglayicilar.py`'deki
altı-sağlayıcı havuz (Groq/Mistral/DeepSeek/OpenRouter/NVIDIA) görsel
ÜRETMİYOR, yalnızca AÇIKLIYOR (server/saglayicilar.py::gorsel_uret,
resim_bytes alıyor — bambaşka bir iş). Bu yüzden bu araç o havuzdan değil,
doğrudan client'ta zaten duran Gemini anahtar havuzundan (core/anahtar.py,
Live oturumunun kullandığı AYNI havuz) geçiyor — server'a yeni bir görsel
üretim entegrasyonu eklemek yerine. Model adı core/modeller.py'de tek yerde
(GORSEL_URET_MODEL) — bkz. o dosyanın 2026-09-04 notu.
"""

import threading
from pathlib import Path

from google import genai
from google.genai import types

from core import anahtar
from core.modeller import GORSEL_URET_MODEL

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "icerik" / "onbellek" / "gorsel_uret"
_CACHE_LIMIT = 30

_kilit = threading.Lock()
_sayac = 0


_UZANTI = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _cache_yaz(veri: bytes, mime_type: str | None) -> Path:
    # Gemini her zaman PNG döndürmüyor (ör. bu araç JPEG de aldı, ölçüldü
    # 2026-09-04) — dosya adı gerçek formatla uyuşmazsa yanıltıcı olur,
    # `file`/harici araçlarla açıldığında uzantı-içerik çelişkisi görünür.
    global _sayac
    uzanti = _UZANTI.get((mime_type or "").lower(), ".png")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with _kilit:
        _sayac += 1
        ad = f"gorsel_{_sayac}{uzanti}"
    yol = CACHE_DIR / ad
    yol.write_bytes(veri)
    _cache_budala()
    return yol


def _cache_budala() -> None:
    """En fazla _CACHE_LIMIT dosya — fazlası en-eski-önce silinir (pdf_sayfa
    ile aynı LRU deseni, bkz. actions/pdf_sayfa.py)."""
    try:
        dosyalar = sorted(CACHE_DIR.glob("gorsel_*.*"), key=lambda p: p.stat().st_mtime)
        for eski in dosyalar[:-_CACHE_LIMIT]:
            eski.unlink(missing_ok=True)
    except Exception:
        pass


def gorsel_uret(parameters: dict | None = None, player=None, speak=None, **_) -> str | None:
    p = parameters or {}
    log = getattr(player, "write_log", None) or (lambda *_a: None)
    anons = speak or (lambda *_a: None)

    konu = (p.get("konu") or "").strip()
    if not konu:
        # main.py zaten iş parçacığı başlamadan önce aynı kontrolü yapıyor
        # (bkz. main.py'deki "gorsel_uret" dalı); burası yalnızca doğrudan
        # çağrıldığında (ör. testte) savunma.
        return "Konu belirtilmedi. 'konu' parametresiyle ne çizileceğini söyle."

    try:
        api_key = anahtar.simdiki()
    except RuntimeError as e:
        log(f"[Görsel Üret] anahtar yok: {e}")
        anons("Görsel üretemedim efendim, API anahtarı tanımlı değil.")
        return None

    try:
        client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        istem = (
            "Bir sınıf dersinde kullanılacak, eğitici, sade ve net bir "
            f"görsel/diyagram oluştur. Konu: {konu}. Görsel üzerinde metin/"
            "etiket varsa Türkçe olsun."
        )
        yanit = client.models.generate_content(
            model=GORSEL_URET_MODEL,
            contents=[istem],
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
    except Exception as e:
        log(f"[Görsel Üret] üretim hatası: {type(e).__name__}: {e}")
        anons(f"Görsel üretilirken bir sorun oluştu efendim, {konu} konusunu sözlü anlatalım.")
        return None

    veri = None
    mime_type = None
    try:
        for aday in yanit.candidates or []:
            for parca in (aday.content.parts or []):
                inline = getattr(parca, "inline_data", None)
                if inline is not None and inline.data:
                    veri = inline.data
                    mime_type = inline.mime_type
                    break
            if veri:
                break
    except Exception as e:
        log(f"[Görsel Üret] yanıt ayrıştırma hatası: {type(e).__name__}: {e}")

    if not veri:
        log("[Görsel Üret] yanıtta görsel verisi yok")
        anons(f"{konu} için görsel üretemedim efendim, sözlü anlatımla devam edelim.")
        return None

    onbellek_yolu = _cache_yaz(veri, mime_type)
    log(f"[Görsel Üret] '{konu}' için görsel üretildi: {onbellek_yolu}")

    if player is not None and hasattr(player, "show_image"):
        player.show_image(f"GÖRSEL — {konu}", str(onbellek_yolu))

    anons(f"{konu} ile ilgili görsel hazır efendim, ekranda gösteriyorum.")
    return f"{konu} için görsel üretildi ve ekranda gösterildi."
