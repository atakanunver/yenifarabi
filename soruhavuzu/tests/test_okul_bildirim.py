from soruhavuzu import okul_bildirim, vt
from soruhavuzu.tests.conftest import ORNEK_SORU


def _veri(sid, kisi, turler):
    return {"esik": 2, "sorular": [{"soru_id": sid, "kisi": kisi, "turler": turler, "son": "x"}]}


def _onayli(conn):
    bid = vt.birim_ekle(conn, "kitap", "k:1", "fizik", 10, "E", "m")
    sid = vt.soru_ekle(conn, bid, {**ORNEK_SORU, "sinif": 10})
    with conn.cursor() as cur:
        cur.execute("UPDATE soru SET durum='onayli' WHERE id=%s", (sid,))
    conn.commit()
    return sid


def _durum(conn, sid):
    with conn.cursor() as cur:
        cur.execute("SELECT durum FROM soru WHERE id=%s", (sid,))
        return cur.fetchone()[0]


def test_esik_alti_askiya_almaz_ama_kaydeder(conn):
    sid = _onayli(conn)
    r = okul_bildirim.isle(conn, _veri(sid, 1, {"sekil": 1}))
    assert r == {"yazilan": 1, "askiya": 0} and _durum(conn, sid) == "onayli"


def test_esikte_askiya_alir_ve_idempotent(conn):
    sid = _onayli(conn)
    okul_bildirim.isle(conn, _veri(sid, 2, {"sekil": 2}))
    assert _durum(conn, sid) == "askida"
    okul_bildirim.isle(conn, _veri(sid, 2, {"sekil": 2}))
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM soru_geri_bildirim WHERE soru_id=%s", (sid,))
        assert cur.fetchone()[0] == 1


def test_okul_kapali_ya_da_anahtarsiz_atlanir(conn):
    assert okul_bildirim.calistir(conn, cekici=lambda: None) is None
    def hata():
        raise OSError("kapalı")
    assert okul_bildirim.calistir(conn, cekici=hata) is None
