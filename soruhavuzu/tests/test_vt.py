from soruhavuzu import vt
from soruhavuzu.tests.conftest import ORNEK_SORU


def test_birim_bir_kez_eklenir(conn):
    a = vt.birim_ekle(
        conn, "kitap", "kitap:36:1-3", "matematik", 12, "Matematik 12, s. 1", "metin"
    )
    b = vt.birim_ekle(
        conn, "kitap", "kitap:36:1-3", "matematik", 12, "Matematik 12, s. 1", "metin"
    )
    assert a is not None and b is None


def test_siradaki_birim_ve_isaretleme(conn):
    bid = vt.birim_ekle(conn, "kitap", "k:1", "matematik", 12, "E", "m")
    assert vt.siradaki_birim(conn)["id"] == bid
    vt.birim_isaretle(conn, bid, "islendi")
    assert vt.siradaki_birim(conn) is None


def test_soru_ekle_ve_denetim(conn):
    bid = vt.birim_ekle(conn, "kitap", "k:1", "matematik", 12, "E", "kaynak metin")
    sid = vt.soru_ekle(conn, bid, ORNEK_SORU)
    paket = vt.denetlenecekler(conn, 20)
    assert [p["id"] for p in paket] == [sid] and paket[0][
        "birim_metin"
    ] == "kaynak metin"
    vt.denetim_yaz(conn, sid, "onayli", "doğru")
    assert vt.denetlenecekler(conn, 20) == []


def test_denetlenecekler_en_az_onayli_grup_once(conn):
    b1 = vt.birim_ekle(conn, "kitap", "k:1", "matematik", 9, "E", "m")
    b2 = vt.birim_ekle(conn, "kitap", "k:2", "fizik", 12, "E", "m")
    # matematik 9: 2 onaylı (kaynak birim 1, düşük id), fizik 12: 0 onaylı
    for i in range(2):
        s = vt.soru_ekle(conn, b1, {**ORNEK_SORU, "ders": "matematik", "sinif": 9, "soru": f"o{i}"})
        vt.denetim_yaz(conn, s, "onayli", "ok")
    m = vt.soru_ekle(conn, b1, {**ORNEK_SORU, "ders": "matematik", "sinif": 9, "soru": "bekleyen"})
    f = vt.soru_ekle(conn, b2, {**ORNEK_SORU, "ders": "fizik", "sinif": 12, "soru": "f"})
    assert [p["id"] for p in vt.denetlenecekler(conn, 10)] == [f, m]
