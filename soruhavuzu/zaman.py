"""soruhavuzu/zaman.py — GPU üretimi yalnızca ders saati dışında (hafta içi 07:30–17:05 yasak)."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

TR = ZoneInfo("Europe/Istanbul")
BASLA, BITIS = time(7, 30), time(17, 5)


def bugun_istanbul() -> date:
    return datetime.now(TR).date()


def uretim_serbest(an: datetime | None = None) -> bool:
    an = (an or datetime.now(TR)).astimezone(TR)
    if an.isoweekday() >= 6:
        return True
    return not (BASLA <= an.time() < BITIS)
