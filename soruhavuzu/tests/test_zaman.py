from datetime import datetime
from zoneinfo import ZoneInfo

from soruhavuzu import zaman

TR = ZoneInfo("Europe/Istanbul")


def test_ders_saati_penceresi():
    # 00:00 - 06:00 arası serbest
    assert zaman.uretim_serbest(datetime(2026, 10, 5, 2, 30, tzinfo=TR)) is True
    assert zaman.uretim_serbest(datetime(2026, 10, 5, 5, 59, tzinfo=TR)) is True
    # 06:00 ve sonrası yasak
    assert zaman.uretim_serbest(datetime(2026, 10, 5, 6, 0, tzinfo=TR)) is False
    assert zaman.uretim_serbest(datetime(2026, 10, 5, 12, 0, tzinfo=TR)) is False
    assert zaman.uretim_serbest(datetime(2026, 10, 5, 17, 10, tzinfo=TR)) is False
    assert zaman.uretim_serbest(datetime(2026, 10, 5, 23, 59, tzinfo=TR)) is False
