from datetime import datetime
from zoneinfo import ZoneInfo

from soruhavuzu import zaman

TR = ZoneInfo("Europe/Istanbul")


def test_ders_saati_penceresi():
    assert (
        zaman.uretim_serbest(datetime(2026, 10, 5, 17, 10, tzinfo=TR)) is True
    )  # Pzt akşam
    assert zaman.uretim_serbest(datetime(2026, 10, 5, 7, 29, tzinfo=TR)) is True
    assert zaman.uretim_serbest(datetime(2026, 10, 5, 7, 30, tzinfo=TR)) is False
    assert zaman.uretim_serbest(datetime(2026, 10, 5, 12, 0, tzinfo=TR)) is False
    assert (
        zaman.uretim_serbest(datetime(2026, 10, 10, 12, 0, tzinfo=TR)) is True
    )  # Cumartesi
