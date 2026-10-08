from datetime import date

from soruhavuzu import vt
from soruhavuzu.tests.conftest import ORNEK_SORU

HAFTALAR = {1: date(2026, 9, 14), 4: date(2026, 10, 5), 5: date(2026, 10, 12), 10: date(2026, 11, 23)}


def _k(conn, hafta, metin, ders="matematik"):
    return vt.kazanim_upsert(conn, {"sinif": 10, "ders": ders, "hafta": hafta, "kod": None, "metin": metin})


def test_yaklasan_hafta_once_ayni_metin_tek(conn):
    uzak = _k(conn, 10, "uzak kazanım")
    yakin = _k(conn, 5, "yakın kazanım")
    _k(conn, 4, "yakın kazanım")          # aynı metin, önceki hafta — tek aday olmalı
    s = vt.siradaki_kazanim(conn, date(2026, 10, 8), HAFTALAR, set())
    assert s["metin"] == "yakın kazanım" and s["hafta"] == 4
    assert vt.siradaki_kazanim(conn, date(2026, 10, 8), HAFTALAR, {s["id"]})["id"] == uzak
    assert yakin != uzak


def test_hedefe_ulasan_ve_kaynak_yok_atlanir(conn):
    a = _k(conn, 4, "a")
    b = _k(conn, 4, "b")
    bid = vt.birim_ekle(conn, "kitap", "k:1", "matematik", 10, "E", "m")
    for i in range(14):
        vt.soru_ekle(conn, bid, {**ORNEK_SORU, "sinif": 10, "soru": f"s{i}"}, kazanim_id=a, kazanim_kaynak="uretim")
    vt.kazanim_isaretle(conn, b, "kaynak_yok")
    assert vt.siradaki_kazanim(conn, date(2026, 10, 8), HAFTALAR, set()) is None
