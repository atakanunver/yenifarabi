"""Belirli gün ve haftalar kartı (2026-10-26): MEB'in belirlediği günler/haftalar, gününde ve haftası boyunca.

Kaynak `config/belirli_gunler.json` (her istekte okunur, değişiklik restart istemez): {"liste": [{"ad", "tur": "gun"|"hafta",
"kural": {"tip", "deger"}}]}. Hareketli günler yıla göre hesaplanır; dosya yok/bozuksa boş liste. Tarih = Türkiye saati.
Kural tipleri (AA-GG = ay-gün):
  sabit "AA-GG" · aralik ["AA-GG","AA-GG"] · hafta_icerir "AA-GG" (o günün Pzt-Paz haftası)
  ayin_gunu [ay, n, haftagunu] (ayın n. Cumartesi'si vb.) · ayin_haftasi [ay, n] (ayın (n-1)*7+1 … n*7. günleri)
  ayin_haftasi_son_gun [ay, n] · ayin_haftasi_gunu [ay, n, haftagunu] · ayin_son_haftasi [ay] (ayın son 7 günü)
  ayin_son_pazartesi_haftasi [ay] · yila_ozel {"2027": ["AA-GG","AA-GG"]} (Diyanet'in belirlediği; yılı yoksa görünmez)
"""

import calendar
import json
import logging
from datetime import date, timedelta
from pathlib import Path

import zaman
from ayarlar import KOK

log = logging.getLogger("okul.belirli_gunler")
YOL = KOK / "config" / "belirli_gunler.json"
_HAFTA_GUNU = {"pazartesi": 0, "sali": 1, "carsamba": 2, "persembe": 3, "cuma": 4, "cumartesi": 5, "pazar": 6}
_AYLAR = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def _aa_gg(s: str, yil: int) -> date:
    ay, gun = s.split("-")
    return date(yil, int(ay), int(gun))


def _ayin_gunu(yil: int, ay: int, n: int, gun_adi: str) -> date:
    ilk = date(yil, ay, 1)
    return ilk + timedelta(days=(_HAFTA_GUNU[gun_adi] - ilk.weekday()) % 7 + 7 * (n - 1))


def _ayin_haftasi(yil: int, ay: int, n: int) -> tuple[date, date]:
    return date(yil, ay, (n - 1) * 7 + 1), date(yil, ay, n * 7)


def _hafta_pzt(g: date) -> tuple[date, date]:
    pzt = g - timedelta(days=g.weekday())
    return pzt, pzt + timedelta(days=6)


def _aralik(kural: dict, yil: int) -> tuple[date, date] | None:
    """Kuralın `yil` içinde başlayan (bas, bit) aralığı; yoksa None."""
    tip, d = kural["tip"], kural["deger"]
    if tip == "sabit":
        g = _aa_gg(d, yil)
        return g, g
    if tip == "aralik":
        bas = _aa_gg(d[0], yil)
        bit = _aa_gg(d[1], yil if d[1] >= d[0] else yil + 1)  # yıl sonunu aşan aralık
        return bas, bit
    if tip == "hafta_icerir":
        return _hafta_pzt(_aa_gg(d, yil))
    if tip == "ayin_gunu":
        g = _ayin_gunu(yil, d[0], d[1], d[2])
        return g, g
    if tip == "ayin_haftasi":
        return _ayin_haftasi(yil, d[0], d[1])
    if tip == "ayin_haftasi_son_gun":
        g = _ayin_haftasi(yil, d[0], d[1])[1]
        return g, g
    if tip == "ayin_haftasi_gunu":
        bas, bit = _ayin_haftasi(yil, d[0], d[1])
        g = bas + timedelta(days=(_HAFTA_GUNU[d[2]] - bas.weekday()) % 7)
        return (g, g) if g <= bit else None
    if tip == "ayin_son_haftasi":
        son = calendar.monthrange(yil, d[0])[1]
        return date(yil, d[0], son - 6), date(yil, d[0], son)
    if tip == "ayin_son_pazartesi_haftasi":
        son = date(yil, d[0], calendar.monthrange(yil, d[0])[1])
        return _hafta_pzt(son - timedelta(days=son.weekday()))
    if tip == "yila_ozel":
        a = d.get(str(yil))
        return (_aa_gg(a[0], yil), _aa_gg(a[1], yil if a[1] >= a[0] else yil + 1)) if a else None
    raise ValueError(f"bilinmeyen kural: {tip}")


def _metin(bas: date, bit: date) -> str:
    if bas == bit:
        return ""
    if bas.month == bit.month:
        return f"{bas.day}–{bit.day} {_AYLAR[bit.month]}"
    return f"{bas.day} {_AYLAR[bas.month]} – {bit.day} {_AYLAR[bit.month]}"


def bugun(yol: Path | None = None, tarih: date | None = None) -> list[dict]:
    """Bugün (veya `tarih`) denk gelen günler/haftalar: [{'ad', 'tur', 'metin'}]; önce günler, sonra haftalar."""
    tarih = tarih or zaman.simdi().date()
    try:
        liste = json.loads((yol or YOL).read_text(encoding="utf-8"))["liste"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        log.warning("belirli_gunler okunamadı: %s", type(e).__name__)
        return []
    sonuc = []
    for k in liste:
        try:
            for yil in (tarih.year - 1, tarih.year):  # yıl sonunu aşan aralıklar için bir önceki yıl da
                a = _aralik(k["kural"], yil)
                if a and a[0] <= tarih <= a[1]:
                    sonuc.append({"ad": str(k["ad"]), "tur": k["tur"], "metin": _metin(*a) if k["tur"] == "hafta" else ""})
                    break
        except (KeyError, ValueError, TypeError, IndexError) as e:
            log.warning("belirli_gunler kaydı atlandı (%s): %s", k.get("ad"), type(e).__name__)
    return sorted(sonuc, key=lambda s: s["tur"] != "gun")
