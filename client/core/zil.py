"""
core/zil.py — Zil çizelgesi ve ders saati bilgisi.

Hem `main.py` (sistem promptuna ders saati enjekte etmek için) hem `ui.py`
(sol paneldeki tarih/saat/ders göstergesi için) buna ihtiyaç duyuyor. `ui.py`
`main.py`'ı import edemeyeceği (döngüsel bağımlılık) için mantık burada.

Çizelge `config/zil.json` dosyasından okunur; örneği `config/zil.example.json`.

TÜRKÇE EK NOTU: buradan dönen metinler modele okutuluyor. Saat eklerini
("08:20'de") kodda üretmekten kaçınılır — ek okunan sayıya göre değişir
(yirmi-de, on-da, kırk-ta) ve model yanlış eki olduğu gibi tekrarlıyor.
Cümleler ek gerektirmeyecek biçimde kurulur ("başlama saati 08:20").
"""

import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ZIL_PATH = BASE_DIR / "config" / "zil.json"

GUN_ADLARI = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma",
              "Cumartesi", "Pazar"]


def cizelge() -> dict | None:
    """Zil çizelgesini oku. Dosya yoksa ya da bozuksa None."""
    try:
        with open(ZIL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _dk(hhmm: str) -> int:
    sa, mi = hhmm.split(":")
    return int(sa) * 60 + int(mi)


def ders_durumu(simdi: datetime | None = None) -> dict:
    """
    O anki ders durumunu döndürür:

        {"tur": "ders" | "teneffus" | "ogle" | "once" | "sonra" | "tatil" | "yok",
         "ders_no": int | None,
         "kisa": "3. DERS" gibi arayüz için kısa etiket,
         "metin": modele verilecek tam cümle}

    "yok" -> çizelge okunamadı; arayüz ders satırını göstermez, Farabi de
    ders saatinden söz etmez.
    """
    simdi = simdi or datetime.now()
    z = cizelge()
    if not z:
        return {"tur": "yok", "ders_no": None, "kisa": "", "metin": ""}

    if simdi.isoweekday() not in (z.get("ders_gunleri") or [1, 2, 3, 4, 5]):
        return {"tur": "tatil", "ders_no": None, "kisa": "DERS GÜNÜ DEĞİL",
                "metin": "Bugün ders günü değil."}

    an = simdi.hour * 60 + simdi.minute
    dersler = z.get("dersler") or []

    for d in dersler:
        try:
            bas, bit = _dk(d["baslangic"]), _dk(d["bitis"])
        except Exception:
            continue
        if bas <= an <= bit:
            kalan = bit - an
            if kalan <= 0:
                metin = f"{d['no']}. ders ({d['baslangic']}-{d['bitis']}) şu an bitiyor."
            elif kalan == 1:
                metin = f"{d['no']}. dersteyiz, bitmesine 1 dakika kaldı."
            else:
                metin = (f"{d['no']}. dersteyiz ({d['baslangic']}-{d['bitis']}), "
                         f"bitmesine {kalan} dakika kaldı.")
            # kalan_dk SAYI olarak da döner: ders motoru (core/ders_motoru.py)
            # süreyi metinden ayıklamak zorunda kalmasın.
            return {"tur": "ders", "ders_no": d["no"], "kalan_dk": kalan,
                    "kisa": f"{d['no']}. DERS  ·  {kalan} dk", "metin": metin}

    ogle = z.get("ogle_arasi") or {}
    try:
        if ogle and _dk(ogle["baslangic"]) <= an <= _dk(ogle["bitis"]):
            return {"tur": "ogle", "ders_no": None, "kisa": "ÖĞLE ARASI",
                    "metin": "Öğle arasındayız."}
    except Exception:
        pass

    for onceki, sonraki in zip(dersler, dersler[1:]):
        try:
            if _dk(onceki["bitis"]) < an < _dk(sonraki["baslangic"]):
                return {"tur": "teneffus", "ders_no": sonraki["no"],
                        "kisa": f"TENEFFÜS  ·  {sonraki['no']}. ders {sonraki['baslangic']}",
                        "metin": (f"Teneffüsteyiz; sıradaki ders {sonraki['no']}. ders, "
                                  f"başlama saati {sonraki['baslangic']}.")}
        except Exception:
            continue

    if dersler:
        try:
            if an < _dk(dersler[0]["baslangic"]):
                return {"tur": "once", "ders_no": None,
                        "kisa": f"DERS ÖNCESİ  ·  {dersler[0]['baslangic']}",
                        "metin": ("Dersler henüz başlamadı; ilk dersin başlama saati "
                                  f"{dersler[0]['baslangic']}.")}
            if an > _dk(dersler[-1]["bitis"]):
                return {"tur": "sonra", "ders_no": None, "kisa": "DERSLER BİTTİ",
                        "metin": "Bugünün dersleri bitti."}
        except Exception:
            pass

    return {"tur": "yok", "ders_no": None, "kisa": "", "metin": ""}


def selam(saat: int) -> str:
    """Saate göre Türkçe selam. 15:00'te 'Günaydın' demesin."""
    if 5 <= saat < 12:
        return "Günaydın"
    if 12 <= saat < 18:
        return "İyi günler"
    return "İyi akşamlar"


def tarih_metni(simdi: datetime | None = None) -> str:
    """'30 Temmuz 2026, Perşembe' — arayüzde göstermek için."""
    simdi = simdi or datetime.now()
    aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
             "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    return (f"{simdi.day} {aylar[simdi.month - 1]} {simdi.year}, "
            f"{GUN_ADLARI[simdi.weekday()]}")
