"""Zil çizelgesi (tahtayoklama/data/zil.json) + okul takvimi (config/takvim.json) — salt-okunur.

Saat widget'ı ve program sayfasındaki giriş-çıkış tablosu buradan beslenir. Sunucu ilk durumu
hesaplar; static/saat.js aynı kuralla (yarı açık [başlangıç, bitiş)) her saniye günceller.
"""

import json
from datetime import date, datetime

from ayarlar import AYAR

from kaynaklar import KaynakHatasi

_onbellek: dict = {}


def _oku(yol) -> dict:
    try:
        mtime = yol.stat().st_mtime
        kayit = _onbellek.get(yol)
        if not kayit or kayit[0] != mtime:
            veri = json.loads(yol.read_text(encoding="utf-8"))
            if not isinstance(veri, dict):
                raise ValueError("nesne değil")
            _onbellek[yol] = kayit = (mtime, veri)
    except (OSError, ValueError) as e:
        raise KaynakHatasi(f"{yol.name} okunamadı: {e}") from e
    return kayit[1]


def dersler() -> list[tuple[int, str, str]]:
    """[(no, "08:10", "08:50"), ...] — zil.json okunamazsa KaynakHatasi."""
    try:
        return sorted(
            (int(d["no"]), str(d["baslangic"]), str(d["bitis"]))
            for d in _oku(AYAR.zil_yolu).get("dersler", [])
        )
    except (KeyError, TypeError, ValueError) as e:
        raise KaynakHatasi(f"zil.json bozuk: {e}") from e


def ogle_arasi() -> tuple[str, str] | None:
    try:
        o = _oku(AYAR.zil_yolu).get("ogle_arasi") or {}
        return (o["baslangic"], o["bitis"]) if o else None
    except (KaynakHatasi, KeyError, TypeError):
        return None


def _takvim() -> dict:
    """Takvim okunamazsa boş: o zaman yalnızca hafta sonu kuralı uygulanır."""
    try:
        return _oku(AYAR.takvim_yolu)
    except KaynakHatasi:
        return {}


def tatil_adi(tarih: date) -> str | None:
    """Okul günü değilse nedeni ("Hafta sonu", "Cumhuriyet Bayramı", ...), okul günüyse None."""
    try:
        gunler = _oku(AYAR.zil_yolu).get("ders_gunleri") or [1, 2, 3, 4, 5]
    except KaynakHatasi:
        gunler = [1, 2, 3, 4, 5]
    if tarih.isoweekday() not in gunler:
        return "Hafta sonu"
    t = _takvim()
    g = tarih.isoformat()
    for tatil in t.get("tatiller", []):
        if tatil.get("baslangic", "") <= g <= tatil.get("bitis", ""):
            return tatil.get("ad") or "Tatil"
    donem = t.get("donem") or {}
    if donem and not (donem.get("baslangic", "") <= g <= donem.get("bitis", "9999")):
        return "Yaz tatili"
    return None


def gunun_dersleri(tarih: date) -> list[tuple[int, str, str]]:
    """O günün ders saatleri; yarım günde kesim saatinde/sonra başlayan dersler düşer."""
    kesim = (_takvim().get("yarim_gun") or {}).get(tarih.isoformat())
    return [d for d in dersler() if not kesim or d[1] < kesim]


def durum(an: datetime) -> dict:
    """Widget'ın ilk metni. tur: tatil | once | ders | teneffus | ogle | bitti | yok."""
    try:
        tatil = tatil_adi(an.date())
        if tatil:
            return {"tur": "tatil", "metin": tatil}
        liste = gunun_dersleri(an.date())
    except KaynakHatasi:
        return {"tur": "yok", "metin": ""}
    if not liste:
        return {"tur": "yok", "metin": ""}
    saat = an.strftime("%H:%M")
    if saat < liste[0][1]:
        return {"tur": "once", "metin": f"1. ders {liste[0][1]}'de başlıyor"}
    for i, (no, bas, bit) in enumerate(liste):
        if bas <= saat < bit:
            return {"tur": "ders", "no": no, "metin": f"{no}. ders", "bas": bas, "bit": bit}
        sonraki = liste[i + 1] if i + 1 < len(liste) else None
        if sonraki and bit <= saat < sonraki[1]:
            ogle = ogle_arasi()
            tur = "ogle" if ogle and ogle[0] <= saat < ogle[1] else "teneffus"
            ad = "Öğle arası" if tur == "ogle" else "Teneffüs"
            return {"tur": tur, "metin": f"{ad} · {sonraki[0]}. ders {sonraki[1]}"}
    return {"tur": "bitti", "metin": "Dersler bitti"}


def widget_verisi(an: datetime) -> dict:
    """_saat.html için: ilk durum + JS'in canlı hesaplaması için o günün çizelgesi."""
    ilk = durum(an)
    veri = {"durum": ilk, "dersler": [], "ogle": None, "tarih": an.date().isoformat(), "saat": an.strftime("%H:%M")}
    if ilk["tur"] not in ("tatil", "yok"):
        veri["dersler"] = [list(d) for d in gunun_dersleri(an.date())]
        veri["ogle"] = ogle_arasi()
    return veri
