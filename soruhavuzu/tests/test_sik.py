from soruhavuzu import calistir, sik, vt
from soruhavuzu.tests.conftest import ORNEK_SORU


def test_atifli_sik_degismez():
    sec = ["Yalnız I", "A ve B", "Hepsi", "Hiçbiri"]
    assert sik.kanonik_sira("Hangisi?", sec, 2) == (sec, 2)
    sec2 = ["x", "y", "z", "Yukarıdakilerin hepsi"]
    assert sik.kanonik_sira("q", sec2, 0) == (sec2, 0)
    sec3 = ["Yalnız A ve B", "bir", "iki", "üç"]
    assert sik.kanonik_sira("q", sec3, 1) == (sec3, 1)


def test_sayisal_kucukten_buyuge():
    sec = ["12", "3,5", "-2", "7"]
    yeni, di = sik.kanonik_sira("q", sec, 0)
    assert yeni == ["-2", "3,5", "7", "12"]
    assert yeni[di] == "12"


def test_sayisal_birimli():
    sec = ["30°", "10°", "20°", "40°"]
    yeni, di = sik.kanonik_sira("q", sec, 2)
    assert yeni == ["10°", "20°", "30°", "40°"] and yeni[di] == "20°"


def test_dogru_metin_korunur_ve_idempotent():
    sec = ["elma", "armut", "kiraz", "üzüm"]
    for d in range(4):
        yeni, di = sik.kanonik_sira("Hangi meyve?", sec, d)
        assert yeni[di] == sec[d]
        assert sorted(yeni) == sorted(sec)
        assert sik.kanonik_sira("Hangi meyve?", *sik.kanonik_sira("Hangi meyve?", sec, d)) == (yeni, di)


def test_dagilim_dengeli():
    sayim = [0, 0, 0, 0]
    for i in range(400):
        _, di = sik.kanonik_sira(f"soru {i}", [f"doğru {i}", f"b{i}", f"c{i}", f"d{i}"], 0)
        sayim[di] += 1
    assert min(sayim) >= 72, sayim


def test_soru_ekle_kanonik_sirayla_ekler(conn):
    bid = vt.birim_ekle(conn, "kitap", "k:s", "matematik", 12, "E", "m")
    sid = vt.soru_ekle(conn, bid, {**ORNEK_SORU, "secenekler": ["8", "4", "3", "2"], "dogru_index": 2})
    with conn.cursor() as cur:
        cur.execute("SELECT secenekler, dogru_index FROM soru WHERE id=%s", (sid,))
        sec, di = cur.fetchone()
    assert sec == ["2", "3", "4", "8"] and sec[di] == "3"


def test_sik_karistir_gecmise_donuk(conn):
    bid = vt.birim_ekle(conn, "kitap", "k:k", "matematik", 12, "E", "m")
    ids = []
    for i in range(6):
        sid = vt.soru_ekle(conn, bid, {**ORNEK_SORU, "soru": f"s{i}"})
        ids.append(sid)
    # ekleme zaten kanonik; bozup geçmiş durumu taklit et
    with conn.cursor() as cur:
        cur.execute("UPDATE soru SET secenekler='[\"d1\",\"a1\",\"c1\",\"b1\"]'::jsonb, dogru_index=0 WHERE id=%s", (ids[0],))
        cur.execute("UPDATE soru SET durum='red' WHERE id=%s", (ids[1],))
        cur.execute("UPDATE soru SET secenekler='[\"d2\",\"a2\",\"c2\",\"b2\"]'::jsonb, dogru_index=0 WHERE id=%s", (ids[1],))
    conn.commit()
    kuru = calistir.sik_karistir(conn, kuru=True)
    assert kuru["degisen"] == 1
    with conn.cursor() as cur:
        cur.execute("SELECT secenekler FROM soru WHERE id=%s", (ids[0],))
        assert cur.fetchone()[0] == ["d1", "a1", "c1", "b1"]  # kuru yazmadı
    s = calistir.sik_karistir(conn)
    assert s["degisen"] == 1  # 'red' satırı kapsam dışı
    with conn.cursor() as cur:
        cur.execute("SELECT secenekler, dogru_index FROM soru WHERE id=%s", (ids[0],))
        sec, di = cur.fetchone()
        assert sorted(sec) == ["a1", "b1", "c1", "d1"] and sec[di] == "d1"
        cur.execute("SELECT secenekler FROM soru WHERE id=%s", (ids[1],))
        assert cur.fetchone()[0] == ["d2", "a2", "c2", "b2"]
    assert calistir.sik_karistir(conn)["degisen"] == 0
