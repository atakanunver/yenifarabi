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
    assert r == {"yazilan": 1, "askiya": 0, "acilan": 0} and _durum(conn, sid) == "onayli"


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


def test_agirlik_esigi_ogretmen_tek_bildirimle_askiya_alir(conn):
    sid = _onayli(conn)
    veri = {"esik": 2, "sorular": [{"soru_id": sid, "kisi": 1, "agirlik": 2, "turler": {"sacma": 1}, "son": "x"}]}
    assert okul_bildirim.isle(conn, veri)["askiya"] == 1 and _durum(conn, sid) == "askida"
    with conn.cursor() as cur:
        cur.execute("SELECT tur FROM soru_geri_bildirim WHERE soru_id=%s", (sid,))
        assert cur.fetchone()[0] == "soru_hatali"


def test_yeni_turler_eslenir(conn):
    sid = _onayli(conn)
    okul_bildirim.isle(conn, _veri(sid, 1, {"alakasiz": 1}))
    with conn.cursor() as cur:
        cur.execute("SELECT tur FROM soru_geri_bildirim WHERE soru_id=%s", (sid,))
        assert cur.fetchone()[0] == "kazanim_uyumsuz"


def test_yonetici_iptali_soruyu_geri_acar_ama_baska_askiyi_acmaz(conn):
    sid = _onayli(conn)
    okul_bildirim.isle(conn, _veri(sid, 2, {"sekil": 2}))
    assert _durum(conn, sid) == "askida"
    r = okul_bildirim.isle(conn, {"esik": 2, "sorular": [], "iptal": [sid]})
    assert r["acilan"] == 1 and _durum(conn, sid) == "onayli"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM soru_geri_bildirim WHERE soru_id=%s", (sid,))
        assert cur.fetchone()[0] == 0
    # AGY denetimiyle askıya alınmış soru (not öneki farklı) iptal listesinde olsa da açılmaz
    bid = vt.birim_ekle(conn, "kitap", "k:2", "fizik", 10, "E2", "m")
    diger = vt.soru_ekle(conn, bid, {**ORNEK_SORU, "sinif": 10, "soru": "başka soru?"})
    with conn.cursor() as cur:
        cur.execute("UPDATE soru SET durum='askida', denetim_notu='agy: hatalı' WHERE id=%s", (diger,))
    conn.commit()
    assert okul_bildirim.isle(conn, {"esik": 2, "sorular": [], "iptal": [diger]})["acilan"] == 0
    assert _durum(conn, diger) == "askida"
