"""
actions/gorsel_uret.py — Ders için YENİ bir görsel üretir (Gemini Image),
tahtada gösterir ve yerel bir önbelleğe kaydeder.

Neden ARKA PLANDA çalışır (main.py'nin `_arkaplan` yardımcısıyla, `_isci`
DEĞİL): görsel üretimi onlarca saniye sürebilir; `ders_icerigi`'nin eskiden
alım döngüsünü 55,4 saniye kilitleyen hatasından ders alındı (bkz.
kayit.py/CLAUDE.md). Bu araç `_isci` gibi ÇAĞRIYI beklemez — main.py
`gorsel_uret`'i bir iş parçacığına atar ve SONUCUNU BEKLEMEDEN modele
hemen "hazırlanıyor" der, ders akmaya devam eder. Üretim bitince bu modül
`speak`/`player.show_image` ile SONUCU AYRICA bildirir — ikisi de zaten
her thread'den güvenli (`ui.py`'nin `_mute_sig`/`_screenshot_sig` ile aynı
Qt-sinyal deseni; `speak`, main.py'de `asyncio.run_coroutine_threadsafe`
kullanıyor).

Gemini anahtarı `core/anahtar.py`'nin AYNI havuzundan (Live oturumuyla
paylaşılan) alınır — ayrı bir sağlayıcı/anahtar türü eklenmiyor (Kural 8'i
tetiklemez): kök CLAUDE.md'nin "Gemini yalnızca client'ta kalıyor" kararı
zaten buydu, bu yalnızca aynı anahtarın ikinci bir kullanımı.

Sunucuya HİÇ gitmiyor — tamamen client-side. Auth/kota/arşiv-arama YOK
(2026-09-04 kullanıcı kararı: "limiti kaldır iptal et", "auth ile
uğraşmayalım", "yalnızca üret kaydet") — FAZ 0 analiz raporundaki
pgvector `visual_archive` + günlük kota tasarımı tamamen iptal edildi.

Kaydetme: en fazla 1600×1200 (`Image.thumbnail` — küçültür, asla büyütmez),
`icerik/onbellek/uretilen_gorseller/` altında, `pdf_sayfa.py` ile AYNI
LRU-cap deseni (en fazla `_CACHE_LIMIT` dosya, en eskisi silinir).

2026-09-04, gerçek anahtarla canlı test sırasında bulundu ve düzeltildi:
`part.as_image()` PIL Image DÖNDÜRMÜYOR — `google.genai.types.Image`
(pydantic model, `image_bytes`/`mime_type` alanları) döndürüyor; onun
`.thumbnail()`/`.save(path, format=...)` metodu yok, yalnızca `.save(path)`
(ham baytları OLDUĞU GİBİ yazar, yeniden boyutlandırmaz). İlk hali
`resim.thumbnail(...)` çağırıp `AttributeError` ile patlıyordu — hiç canlı
test edilmemişti. Ayrıca Gemini her zaman PNG döndürmüyor (JPEG de aldık,
`actions/pdf_sayfa.py`'nin kardeşi değil ama aynı sınıf hata) — dosya artık
gerçek `mime_type`'a göre kaydediliyor, her zaman `.png` DEĞİL.
"""

import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

from core import anahtar as core_anahtar
from google import genai
from google.genai import types
from PIL import Image as PILImage

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "icerik" / "onbellek" / "uretilen_gorseller"
_CACHE_LIMIT = 30

_FORMAT = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
_UZANTI = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}

# Yalnızca bu modülün tek tüketicisi — core/modeller.py'nin kendi
# docstring'i "bu dosyayı tekrar genişletmeyin" diyor (CANLI_MODEL'in tek
# tüketicisi Live oturumuydu); yeni bir Gemini tüketicisi için model adını
# oraya taşımak yerine burada, kullanan kodun yanında tutuyoruz.
GORSEL_URETIM_MODEL = "gemini-3.1-flash-image"

ZAMAN_ASIMI = 45.0  # saniye — kayit.py'deki Arac.zaman_asimi ile aynı değer
MAKS_BOYUT = (1600, 1200)


def _slug(metin: str) -> str:
    s = re.sub(r"[^0-9A-Za-zÇĞİÖŞÜçğıöşü]+", "_", metin.strip().lower()).strip("_")
    return (s or "gorsel")[:40]


def _cache_budala() -> None:
    """En fazla _CACHE_LIMIT dosya — fazlası en-eski-önce silinir (pdf_sayfa.py ile aynı desen)."""
    try:
        dosyalar = sorted(CACHE_DIR.glob("*.*"), key=lambda p: p.stat().st_mtime)
        for eski in dosyalar[:-_CACHE_LIMIT]:
            eski.unlink(missing_ok=True)
    except Exception:
        pass


def _kaydet(veri: bytes, mime_type: str | None, konu: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    mime_type = (mime_type or "").lower()
    uzanti = _UZANTI.get(mime_type, ".png")
    bicim = _FORMAT.get(mime_type, "PNG")
    ad = f"{_slug(konu)}_{datetime.now():%Y%m%d_%H%M%S}{uzanti}"
    yol = CACHE_DIR / ad
    resim = PILImage.open(BytesIO(veri))
    resim.thumbnail(MAKS_BOYUT)
    resim.save(yol, format=bicim)
    _cache_budala()
    return yol


def _resimi_cikar(resp):
    """Yanıttaki ilk görsel Part'ın (bayt, mime_type) ikilisini döner, yoksa None."""
    try:
        for aday in resp.candidates or []:
            for parca in aday.content.parts or []:
                inline = getattr(parca, "inline_data", None)
                if inline is not None and inline.data:
                    return inline.data, inline.mime_type
    except Exception:
        pass
    return None


def _uret(anahtar: str, istem: str):
    client = genai.Client(api_key=anahtar)
    return client.models.generate_content(
        model=GORSEL_URETIM_MODEL,
        contents=istem,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            http_options=types.HttpOptions(timeout=int(ZAMAN_ASIMI * 1000)),
        ),
    )


def gorsel_uret(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    """
    Ağır kısım — main.py bunu `_arkaplan` ile bir iş parçacığına atar,
    SONUCUNU BEKLEMEZ. `konu` boş/yoksa main.py'nin dispatch dalı zaten
    thread başlatmadan önce senkron olarak reddediyor (bkz. main.py); buradaki
    kontrol yalnızca bu fonksiyon doğrudan çağrıldığında (ör. testte) savunma.
    """
    p = parameters or {}
    log = getattr(player, "write_log", None) or (lambda *_a: None)
    say = speak or (lambda *_a: None)

    konu = (p.get("konu") or "").strip()
    if not konu:
        return "Konu belirtilmedi."

    try:
        anahtar = core_anahtar.simdiki()
    except RuntimeError as e:
        log(f"[Görsel Üret] anahtar yok: {e}")
        say("Üzgünüm efendim, şu an görsel oluşturamıyorum.")
        return "Gemini anahtarı yok."

    istem = (
        f"Bir ders için eğitici bir görsel oluştur: {konu}. "
        "Sınıfta tahtada gösterime uygun, temiz, anlaşılır, doğru "
        "etiketlenmiş bir görsel/diyagram olsun."
    )

    resp, son_hata = None, None
    for deneme in range(2):
        try:
            resp = _uret(anahtar, istem)
            break
        except Exception as e:
            son_hata = e
            resp = None
            if deneme == 0 and core_anahtar.kota_hatasi_mi(e) and core_anahtar.sonrakine_gec():
                anahtar = core_anahtar.simdiki()
                continue
            break

    cikarilan = _resimi_cikar(resp) if resp is not None else None
    if cikarilan is None:
        log(f"[Görsel Üret] başarısız ({konu}): "
            f"{type(son_hata).__name__ if son_hata else 'yanıtta görsel yok'}: {son_hata or ''}")
        say("Üzgünüm efendim, görseli oluşturamadım.")
        return "Görsel oluşturulamadı."

    veri, mime_type = cikarilan
    yol = _kaydet(veri, mime_type, konu)
    log(f"[Görsel Üret] {konu} -> {yol.name}")
    if player is not None and hasattr(player, "show_image"):
        player.show_image(konu[:48], str(yol))
    say("Görsel hazır efendim, ekranda gösteriyorum.")
    return f"{konu} için görsel oluşturuldu ve ekranda gösteriliyor."
