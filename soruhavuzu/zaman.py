"""soruhavuzu/zaman.py — GPU üretimi yalnızca gece 00:00 ile sabah 06:00 arasında serbest."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

TR = ZoneInfo("Europe/Istanbul")
BASLA, BITIS = time(0, 0), time(6, 0)


def bugun_istanbul() -> date:
    return datetime.now(TR).date()


def uretim_serbest(an: datetime | None = None) -> bool:
    an = (an or datetime.now(TR)).astimezone(TR)
    t = an.time()
    # Yalnızca 00:00:00 ile 06:00:00 arası serbest
    return BASLA <= t < BITIS
