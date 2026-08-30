"""
core/saglayicilar.py — Gemini DIŞI metin/görsel görevleri için sunucu proxy'si.

Server-taşıma (2026-08-14): bu modül artık bulut sağlayıcılara (Groq/
Mistral/DeepSeek/OpenRouter/NVIDIA) DOĞRUDAN bağlanmıyor — anahtarlar
server'a taşındı (`server/config/api_keys.json`, CLAUDE.md Kural 9 gereği
client'ta anahtar yazılmaz). Gerçek sağlayıcı havuzu + görev zincirleri +
soğuma mantığı artık `server/saglayicilar.py`de; bu dosya yalnızca
`/api/egitim/metin_uret` ve `/api/egitim/gorsel_uret`'e HTTP çağrısı yapan
ince bir istemci.

KRİTİK: `metin_uret`/`gorsel_uret` FONKSİYON İMZALARI (ad, parametre sırası,
dönüş tipi — düz `str`) BİREBİR KORUNDU. `actions/file_processor.py`,
`actions/web_search.py`, `actions/youtube_video.py`, `tools/kitap_ozet.py`,
`tools/sembol_temizle.py` hepsi `from core import saglayicilar` edip bu iki
fonksiyonu aynen çağırıyor — imza değişseydi hepsi tek tek güncellenmesi
gerekirdi. Bunun yerine tek bu dosya değişti, çağıranlar HİÇ dokunulmadı.

Hata davranışı da korundu: sunucu başarısız olursa (ya da hiçbir sağlayıcı
yanıt vermezse) `RuntimeError` YÜKSELİR, sessizce boş/uydurma yanıt DÖNMEZ —
eski client-taraflı `_zinciri_dene`'nin "failure text is binding" ilkesiyle
aynı. Çağıran taraf kendi "sınırlı devam et" mesajını üretir.
"""

from core.tahta import auth_headers as _auth_headers
from core.tahta import sunucu_url as _sunucu_url

ZAMAN_ASIMI_METIN = 45.0    # bulut LLM zinciri birden fazla sağlayıcı deneyebilir
ZAMAN_ASIMI_GORSEL = 45.0


def metin_uret(gorev: str, istem: str, sistem: str | None = None) -> str:
    """Salt metin görevler (özet, sentez, analiz, düzeltme)."""
    import requests
    try:
        r = requests.post(
            f"{_sunucu_url()}/api/egitim/metin_uret",
            json={"gorev": gorev, "istem": istem, "sistem": sistem},
            headers=_auth_headers(),
            timeout=ZAMAN_ASIMI_METIN,
        )
        r.raise_for_status()
        veri = r.json()
    except Exception as e:
        raise RuntimeError(f"metin_uret sunucusuna ulaşılamadı: {type(e).__name__}: {e}")

    if veri.get("status") != "ok":
        raise RuntimeError(veri.get("hata") or f"'{gorev}' görevi sunucuda başarısız oldu.")
    return veri["metin"]


def gorsel_uret(gorev: str, istem: str, resim_bytes: bytes, mime: str = "image/jpeg") -> str:
    """Görsel + metin isteyen görevler. Konuşma DÖNMEZ, yalnızca metin döner."""
    import requests
    try:
        r = requests.post(
            f"{_sunucu_url()}/api/egitim/gorsel_uret",
            data={"gorev": gorev, "istem": istem},
            files={"dosya": ("gorsel.jpg", resim_bytes, mime)},
            headers=_auth_headers(),
            timeout=ZAMAN_ASIMI_GORSEL,
        )
        r.raise_for_status()
        veri = r.json()
    except Exception as e:
        raise RuntimeError(f"gorsel_uret sunucusuna ulaşılamadı: {type(e).__name__}: {e}")

    if veri.get("status") != "ok":
        raise RuntimeError(veri.get("hata") or f"'{gorev}' görevi sunucuda başarısız oldu.")
    return veri["metin"]
