"""
core/anahtar.py — Gemini API anahtar havuzu ve kota dolunca devir.

Neden var: tek anahtarın aylık harcama sınırı dolduğunda oturum hiç açılmıyor
ve tahta ders ortasında sessizleşiyor ("1011 ... exceeded its monthly spending
cap"). Birden çok anahtar tanımlanıp sıradakine geçilebilsin diye.

Anahtar YEDİ ayrı yerden okunuyordu (main.py + altı action modülü), her biri
`api_keys.json`'ı kendisi açıyordu. Devir hepsinde geçerli olmak zorunda —
yoksa oturum yeni anahtara geçerken `web_search` ölü anahtarı kullanmaya devam
eder. Bu yüzden mantık `zil.py` / `tahta.py` gibi burada, tek noktada duruyor.

⚠️ ÖNEMLİ SINIR: aylık harcama sınırı Google Cloud PROJESİ başınadır. Aynı
projeden üretilmiş on anahtar aynı sınırı paylaşır; devir on kez denenip yine
aynı 1011 hatasına düşer. Bu özelliğin işe yaraması için anahtarların AYRI
PROJELERDEN olması gerekir.

Yapılandırma (config/api_keys.json):

    "gemini_api_keys": ["AIza...1", "AIza...2"]     ← havuz (tercih edilir)
    "gemini_api_key":  "AIza...1"                    ← tek anahtar (eski biçim)

İkisi de desteklenir; liste varsa o kullanılır. İlk açılıştaki tek anahtar
yazma yolu (ui.py) değişmedi.
"""

import json
import threading
from pathlib import Path

BASE_DIR    = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

ALAN_LISTE = "gemini_api_keys"
ALAN_TEK   = "gemini_api_key"

_kilit    = threading.Lock()
_indeks   = 0      # havuzdaki sıra
_devir    = 0      # son başarılı bağlantıdan bu yana kaç kez devredildi


def anahtarlar() -> list[str]:
    """
    Tanımlı anahtarlar, sırayla. Liste alanı önce, tek anahtar sonra.
    Yinelenenler atılır — aynı anahtarı iki kez denemek boşa deneme.
    """
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return []

    ham = cfg.get(ALAN_LISTE) or []
    if isinstance(ham, str):          # tek dize yazılmışsa da kabul et
        ham = [ham]
    tek = cfg.get(ALAN_TEK)
    if tek:
        ham = list(ham) + [tek]

    goruldu, sonuc = set(), []
    for a in ham:
        a = str(a or "").strip()
        if a and a not in goruldu:
            goruldu.add(a)
            sonuc.append(a)
    return sonuc


def adet() -> int:
    return len(anahtarlar())


def simdiki() -> str:
    """
    O anda kullanılacak anahtar. Hiç anahtar yoksa RuntimeError — çağıranların
    çoğu zaten KeyError bekliyordu, mesajı anlaşılır olsun.
    """
    liste = anahtarlar()
    if not liste:
        raise RuntimeError(
            "config/api_keys.json içinde gemini_api_key ya da gemini_api_keys yok."
        )
    with _kilit:
        return liste[_indeks % len(liste)]


def durum() -> str:
    """Log için: '2/10'."""
    n = adet()
    return f"{(_indeks % n) + 1}/{n}" if n else "0/0"


def kota_hatasi_mi(exc: Exception) -> bool:
    """
    Bu hata anahtar değiştirmeyi hak ediyor mu?

    DAR tutuluyor. Her hatada devretmek, geçersiz anahtar ya da yanlış model
    adı gibi gerçek hataları "on anahtarı da denedim, olmadı" hâline getirir —
    CLAUDE.md'deki yeniden bağlanma bölümü tam da bu yanlış teşhisi önlemek
    için yazılmıştı. Yalnızca kota/harcama sınırı işaretleri sayılır.
    """
    m = f"{type(exc).__name__}: {exc}".lower()
    return any(k in m for k in (
        "spending cap",
        "resource_exhausted",
        "resource exhausted",
        "quota",
        "429",
        "rate limit",
    ))


def sonrakine_gec() -> bool:
    """
    Sıradaki anahtara geç.

    Dönen değer: havuzda HENÜZ denenmemiş anahtar kaldıysa True. Bir turu
    tamamlayıp başa döndüysek False — çağıran o zaman "hepsi tükendi" diye
    kullanıcıya söyleyip normal geri çekilmeye (backoff) dönebilir.
    """
    global _indeks, _devir
    n = adet()
    if n <= 1:
        return False
    with _kilit:
        _indeks = (_indeks + 1) % n
        _devir += 1
        return _devir < n


def basarili() -> None:
    """Bağlantı kurulunca çağrılır — devir sayacı sıfırlanır."""
    global _devir
    with _kilit:
        _devir = 0
