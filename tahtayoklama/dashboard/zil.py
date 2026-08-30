"""tahtayoklama/data/zil.json okuma + ders-zamanlama yardımcıları.

yoklama.py'deki _simdiki_ders / _ders_baslangicindan_gecen_dk mantığının
server-side kopyası — PyQt6 bağımlılığı almamak için kasıtlı kod tekrarı
(bkz. yoklama.py'nin kendi docstring'i: data/zil.json zaten Farabi'nin
client/config/zil.json'undan bağımsız bir kopya olarak tasarlandı).
"""

from datetime import date, datetime, time as dtime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo
import json

ZIL_DOSYASI = (
    Path(__file__).resolve().parent.parent / "data" / "zil.json"
)

# Tahtalar fiziksel olarak okulda, Türkiye saatinde çalışıyor — pano hangi
# sunucuda/hangi sistem saat diliminde barındırılırsa barındırılsın, ders
# zamanlaması KARŞILAŞTIRMALARI her zaman İstanbul saatiyle yapılmalı (bu
# dev ortamı UTC, tahtalar +03 — canlı SSH ile doğrulandı, 2026-08-23).
ISTANBUL = ZoneInfo("Europe/Istanbul")


def simdi_istanbul() -> datetime:
    return datetime.now(ISTANBUL)


@lru_cache(maxsize=1)
def _zil_yukle() -> dict:
    return json.loads(ZIL_DOSYASI.read_text(encoding="utf-8"))


def yenile() -> None:
    """config elle değiştiyse önbelleği temizler (ör. /api/yenile-zil)."""
    _zil_yukle.cache_clear()


def _saat_ayristir(s: str) -> dtime:
    saat, dakika = s.split(":")
    return dtime(int(saat), int(dakika))


def ders_saatleri() -> list[dict]:
    return _zil_yukle().get("dersler", [])


def ders_gunleri() -> set[int]:
    return set(_zil_yukle().get("ders_gunleri", [1, 2, 3, 4, 5]))


# yoklama.py'deki UYARI_ESIGI_DK sabitiyle birebir aynı tutulmalı
# (data/zil.json'da böyle bir alan yok, yoklama.py'de de sabit kodlu).
UYARI_ESIGI_DK = 10


def ders_baslangic_bitis(ders_no: int) -> tuple[dtime, dtime] | None:
    for ders in ders_saatleri():
        if ders["no"] == ders_no:
            return _saat_ayristir(ders["baslangic"]), _saat_ayristir(ders["bitis"])
    return None


def simdiki_ders(simdi: dtime | None = None) -> int | None:
    simdi = simdi or simdi_istanbul().time()
    for ders in ders_saatleri():
        baslangic = _saat_ayristir(ders["baslangic"])
        bitis = _saat_ayristir(ders["bitis"])
        if baslangic <= simdi < bitis:
            return ders["no"]
    return None


def gecen_dk(ders_no: int, simdi: dtime | None = None) -> int | None:
    """Dersin başlangıcından bu yana geçen dakika — ders zil.json'da yoksa None."""
    simdi = simdi or simdi_istanbul().time()
    aralik = ders_baslangic_bitis(ders_no)
    if aralik is None:
        return None
    baslangic, _ = aralik
    return (simdi.hour * 60 + simdi.minute) - (baslangic.hour * 60 + baslangic.minute)


def okul_gunu_mu(tarih: date) -> bool:
    return tarih.isoweekday() in ders_gunleri()


def ilk_ders_saati() -> dtime | None:
    dersler = ders_saatleri()
    return _saat_ayristir(dersler[0]["baslangic"]) if dersler else None


def son_ders_bitis_saati() -> dtime | None:
    dersler = ders_saatleri()
    return _saat_ayristir(dersler[-1]["bitis"]) if dersler else None
