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
