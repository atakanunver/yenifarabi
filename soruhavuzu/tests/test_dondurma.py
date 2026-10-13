"""12. sınıf dondurma (2026-10-10): üretim sırası, denetim ve sınıflandırma 12'ye dokunmaz."""
from datetime import date

from soruhavuzu import vt
from soruhavuzu.tests.conftest import ORNEK_SORU

HAFTALAR = {1: date(2026, 9, 14)}


def test_dondurma_siradaki_kazanim_12yi_atlar(conn):
    vt.kazanim_upsert(conn, {"sinif": 12, "ders": "fizik", "hafta": 1, "kod": None, "metin": "on iki"})
    assert vt.siradaki_kazanim(conn, date(2026, 10, 13), HAFTALAR, set()) is None
    vt.kazanim_upsert(conn, {"sinif": 10, "ders": "fizik", "hafta": 1, "kod": None, "metin": "on"})
    assert vt.siradaki_kazanim(conn, date(2026, 10, 13), HAFTALAR, set())["sinif"] == 10


def test_dondurma_denetlenecekler_12yi_atlar(conn):
    for sinif in (12, 10):
        bid = vt.birim_ekle(conn, "kitap", f"k:{sinif}", "matematik", sinif, "E", "m")
        vt.soru_ekle(conn, bid, {**ORNEK_SORU, "sinif": sinif, "soru": f"s{sinif}"})
    assert [s["sinif"] for s in vt.denetlenecekler(conn, 10)] == [10]


def test_tekrar_temizle_birebir_kopyayi_isaretler_dondurma_12ye_dokunmaz(conn):
    from soruhavuzu import tekrar

    for sinif in (10, 12):
        bid = vt.birim_ekle(conn, "kitap", f"k:{sinif}", "matematik", sinif, "E", "m")
        for _ in range(2):
            vt.soru_ekle(conn, bid, {**ORNEK_SORU, "sinif": sinif})
    # aynı metin ama farklı şıklar kopya sayılmaz
    vt.soru_ekle(conn, bid, {**ORNEK_SORU, "sinif": 12, "secenekler": ["1", "3", "5", "9"]})
    assert tekrar.kopyalari_isaretle(conn, kuru=True) == 1
    assert tekrar.kopyalari_isaretle(conn) == 1
    with conn.cursor() as cur:
        cur.execute("SELECT sinif, count(*) FROM soru WHERE durum='kopya' GROUP BY 1")
        assert cur.fetchall() == [(10, 1)]
