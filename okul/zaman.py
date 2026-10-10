"""Tek saat kaynağı — testler simdi'yi yamalar."""

from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")
BICIM = "%Y-%m-%d %H:%M:%S"


def simdi() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


def simdi_str() -> str:
    return simdi().strftime(BICIM)
