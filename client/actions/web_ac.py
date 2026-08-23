"""
actions/web_ac.py — Öğretmen talimat modunda GERÇEK tarayıcıyı açar.

ÖĞRETMEN TALİMAT MODUNA ÖZEL (kip="talimat") — normal derste bu araç modele
hiç bildirilmez (bkz. actions/kayit.py, kip alanı). site_goster.py bilinçli
olarak tarayıcısız: bir derste öğrenciye adres çubuğu/link/geri tuşu
vermemek için (bkz. o dosyanın docstring'i). Bu araç tam tersi bir bağlamda
var — ders anlatımının OLMADIĞI, öğretmenin tahtayı doğrudan sesle
yönettiği bir modda gerçek, sınırsız tarayıcı erişimi kullanıcı tarafından
BİLEREK istendi (2026-08-23). site_goster'ın beyaz listesi burada
KASITLI OLARAK yok — yalnızca file:/javascript:/data: şemaları reddedilir,
bu bir beyaz liste değil, salt bir hijyen tabanı.

Aynı "tahtada auth yok" kısıtı burada da geçerli (bkz. CLAUDE.md, Teacher
panel bölümü): mikrofon açıkken konuşan herkes bu aracın gözünde
"öğretmen"dir — bu bilinerek kabul edilen bir risktir, kod tarafında
çözülmüş değildir.
"""

import subprocess
from urllib.parse import quote_plus

from config import is_mac, is_linux

# Öğretmenin tek kelimeyle söyleyeceği en olası hedefler — kullanıcının
# verdiği örnekler burada birebir karşılanır ("google aç", "eba.gov.tr aç",
# "youtube aç", "internet aç").
_KISAYOLLAR = {
    "internet":  "https://www.google.com",
    "google":    "https://www.google.com",
    "eba":       "https://www.eba.gov.tr",
    "eba.gov.tr": "https://www.eba.gov.tr",
    "youtube":   "https://www.youtube.com",
    "wikipedia": "https://www.wikipedia.org",
    "vikipedi":  "https://www.wikipedia.org",
    "meb":       "https://www.meb.gov.tr",
    "e-okul":    "https://e-okul.meb.gov.tr",
    "eokul":     "https://e-okul.meb.gov.tr",
    "gmail":     "https://mail.google.com",
}

_YASAKLI_SEMALAR = ("file:", "javascript:", "data:")


def _url_yap(hedef: str) -> str | None:
    h = hedef.strip()
    h_alt = h.lower()
    if not h:
        return None
    if h_alt in _KISAYOLLAR:
        return _KISAYOLLAR[h_alt]
    for sema in _YASAKLI_SEMALAR:
        if h_alt.startswith(sema):
            return None
    if "://" in h:
        return h
    if " " not in h and "." in h:
        return f"https://{h}"
    return f"https://www.google.com/search?q={quote_plus(h)}"


def _ac(url: str) -> None:
    if is_mac():
        subprocess.Popen(["open", url])
    elif is_linux():
        subprocess.Popen(["xdg-open", url])
    else:
        subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)


def web_ac(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}
    hedef = (params.get("hedef") or "").strip()

    if player:
        player.write_log(f"[TALİMAT] web_ac: '{hedef}'")

    if not hedef:
        return "Hangi siteyi açacağımı söyleyin."

    url = _url_yap(hedef)
    if url is None:
        return f"'{hedef}' açılamıyor — geçersiz adres."

    try:
        _ac(url)
    except Exception as e:
        return f"Tarayıcı açılamadı: {e}"

    return f"Açılıyor: {hedef}"
