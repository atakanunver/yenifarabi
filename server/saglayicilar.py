"""server/saglayicilar.py — Gemini DIŞI metin/görsel sağlayıcı havuzu.

client/core/saglayicilar.py'den taşındı (Faz 2/9, server-taşıma planı) —
mantık BİREBİR korunur (GOREV_ZINCIRLERI, soğuma mantığı, zincir dene
sırası). Tek fonksiyonel fark: `CONFIG_PATH` artık server/config/api_keys.json
(yalnızca 5 bulut sağlayıcı anahtarı — Gemini burada YOK, o client'ta kalıyor,
canlı ses oturumu mimari kısıtı gereği, bkz. mimari.md §14) ve `ollama`
sağlayıcısı server'da GERÇEKTEN çalışır (client'ta Ollama hiç kurulu değildi,
bu adım sessizce hep atlanıyordu — burada bonus bir düzelme, davranış
değişikliği DEĞİL, zaten var olan "son çare" zincirinin ilk kez işlevsel
hâle gelmesi).
"""

import base64
import json
import logging
import time
from pathlib import Path

log = logging.getLogger("saglayicilar")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

SOGUMA_SURESI_SN: float = 4 * 60 * 60
_son_basarisizlik: dict[str, float] = {}


def _soguma_hakeder_mi(exc: Exception) -> bool:
    m = f"{type(exc).__name__}: {exc}".lower()
    return any(k in m for k in (
        "402", "401", "429",
        "insufficient_quota", "insufficient balance",
        "rate limit", "rate_limited", "quota",
        "resource_exhausted", "unauthorized", "invalid_api_key", "invalid api key",
    ))


def _sogumada_mi(saglayici: str) -> bool:
    t = _son_basarisizlik.get(saglayici)
    return t is not None and (time.monotonic() - t) < SOGUMA_SURESI_SN


SAGLAYICI_TANIMLARI = {
    "groq":       {"base_url": "https://api.groq.com/openai/v1",      "anahtar_alani": "groq_api_key"},
    "mistral":    {"base_url": "https://api.mistral.ai/v1",           "anahtar_alani": "mistral_api_key"},
    "deepseek":   {"base_url": "https://api.deepseek.com/v1",         "anahtar_alani": "deepseek_api_key"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1",        "anahtar_alani": "openrouter_api_key"},
    "nvidia":     {"base_url": "https://integrate.api.nvidia.com/v1", "anahtar_alani": "nvidia_api_key"},
    "ollama":     {"base_url": "http://127.0.0.1:11434/v1",           "anahtar_alani": None},
}

GOREV_ZINCIRLERI: dict[str, list[tuple[str, str]]] = {
    "gorsel": [
        ("groq",   "meta-llama/llama-4-scout-17b-16e-instruct"),
        ("nvidia", "meta/llama-3.2-90b-vision-instruct"),
    ],
    "arama_sentez": [
        ("deepseek", "deepseek-v4-flash"),
    ],
    "belge_ozet": [
        # 2026-08-25: Ollama (yerel, ucretsiz) birincil yapildi -- kullanicinin
        # acik karariyla ("PDF analizlerinde bulut token harcanmasin, yerel
        # Ollama kullanilsin"). Bulut saglayicilar fallback olarak kaldi --
        # Ollama servisi cokerse/yanit vermezse zincir otomatik oraya duser
        # (mimari.md SS2 "Farabi asla dersi bozmaz" ile ayni desen).
        ("ollama",   "qwen2.5:14b"),
        ("deepseek", "deepseek-v4-flash"),
        ("mistral",  "mistral-large-latest"),
    ],
    "video_ozet": [
        ("deepseek", "deepseek-v4-flash"),
        ("groq",     "openai/gpt-oss-120b"),
    ],
    "kitap_ozet": [
        ("nvidia",   "meta/llama-3.3-70b-instruct"),
        ("deepseek", "deepseek-v4-flash"),
        ("ollama",   "qwen2.5:14b"),
    ],
    "sembol_duzelt": [
        ("deepseek", "deepseek-v4-flash"),
        ("mistral",  "mistral-large-latest"),
    ],
    "soru_taslak": [
        ("deepseek", "deepseek-v4-flash"),
        ("mistral",  "mistral-large-latest"),
        ("nvidia",   "meta/llama-3.3-70b-instruct"),
        ("ollama",   "qwen2.5:14b"),
    ],
}

_EVRENSEL_METIN_YEDEK = ("openrouter", "openrouter/free")


def _config_oku() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _anahtar(saglayici: str) -> str | None:
    alan = SAGLAYICI_TANIMLARI[saglayici]["anahtar_alani"]
    return (_config_oku().get(alan) or "").strip() or None


def _istemci(saglayici: str):
    from openai import OpenAI
    if saglayici == "ollama":
        anahtar = "ollama"
    else:
        anahtar = _anahtar(saglayici)
        if not anahtar:
            return None
    return OpenAI(base_url=SAGLAYICI_TANIMLARI[saglayici]["base_url"],
                  api_key=anahtar, max_retries=0, timeout=30.0)


# 2026-08-25: qwen2.5:14b sistem mesajı olmadan çağrıldığında (bulut
# sağlayıcılarda sorun yaratmayan, ama bu modelde gözlenen bir davranış)
# yanıtın ortasında dile geçiş yapabiliyor (ör. Türkçe istemde Çince'ye
# kayma) — canlıda `belge_ozet` görevi Ollama'yı birincil sağlayıcı yapınca
# bulundu (bkz. raganaliz.txt). Bulut sağlayıcılar zaten örtük olarak
# isteğin dilinde cevap veriyordu, yalnızca Ollama'ya özel bir varsayılan
# sistem mesajı ekleniyor — diğer sağlayıcıların davranışı değişmiyor.
_OLLAMA_VARSAYILAN_SISTEM = (
    "Sadece Türkçe cevap ver. Başka hiçbir dile geçme. Kısa ve net yaz."
)


def _zinciri_dene(gorev: str, mesajlar: list[dict], evrensel_yedek: bool = True) -> str:
    if gorev not in GOREV_ZINCIRLERI:
        raise RuntimeError(f"Tanımsız görev: '{gorev}'")
    zincir = list(GOREV_ZINCIRLERI[gorev])
    if evrensel_yedek:
        zincir = zincir + [_EVRENSEL_METIN_YEDEK]

    son_hata: Exception | None = None
    for saglayici, model in zincir:
        if _sogumada_mi(saglayici):
            kalan_dk = (SOGUMA_SURESI_SN - (time.monotonic() - _son_basarisizlik[saglayici])) / 60
            log.info("%s: soğumada (~%.0f dk kaldı), atlanıyor", saglayici, kalan_dk)
            continue

        istemci = _istemci(saglayici)
        if istemci is None:
            log.info("%s: config/api_keys.json içinde anahtar yok, atlanıyor", saglayici)
            continue
        try:
            gonderilecek = mesajlar
            if saglayici == "ollama" and not any(m.get("role") == "system" for m in mesajlar):
                gonderilecek = [{"role": "system", "content": _OLLAMA_VARSAYILAN_SISTEM}] + mesajlar
            ekstra = {"temperature": 0.2} if saglayici == "ollama" else {}
            yanit = istemci.chat.completions.create(model=model, messages=gonderilecek, **ekstra)
            metin = (yanit.choices[0].message.content or "").strip()
            if metin:
                _son_basarisizlik.pop(saglayici, None)
                return metin
            son_hata = RuntimeError(f"{saglayici}/{model}: boş yanıt")
            log.warning("%s/%s boş yanıt döndü, sıradaki sağlayıcıya geçiliyor", saglayici, model)
        except Exception as e:
            son_hata = e
            if _soguma_hakeder_mi(e):
                _son_basarisizlik[saglayici] = time.monotonic()
                log.warning("%s/%s başarısız (%s): %s — %d saat soğumaya alındı, sıradaki sağlayıcıya geçiliyor",
                            saglayici, model, type(e).__name__, str(e)[:160], SOGUMA_SURESI_SN // 3600)
            else:
                log.warning("%s/%s başarısız (%s): %s — sıradaki sağlayıcıya geçiliyor",
                            saglayici, model, type(e).__name__, str(e)[:160])
            continue

    raise RuntimeError(f"'{gorev}' görevi için hiçbir sağlayıcı yanıt vermedi. Son hata: {son_hata}")


def metin_uret(gorev: str, istem: str, sistem: str | None = None) -> str:
    mesajlar = []
    if sistem:
        mesajlar.append({"role": "system", "content": sistem})
    mesajlar.append({"role": "user", "content": istem})
    return _zinciri_dene(gorev, mesajlar)


def gorsel_uret(gorev: str, istem: str, resim_bytes: bytes, mime: str = "image/jpeg") -> str:
    b64 = base64.b64encode(resim_bytes).decode("ascii")
    icerik = [
        {"type": "text", "text": istem},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ]
    return _zinciri_dene(gorev, [{"role": "user", "content": icerik}], evrensel_yedek=False)
