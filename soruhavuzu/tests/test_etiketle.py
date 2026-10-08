import numpy as np

from soruhavuzu import etiketle, vt
from soruhavuzu.tests.conftest import ORNEK_SORU


class SahteGomucu:
    """'alan' içeren metin [1,0], 'açı' içeren [0,1], diğerleri [-1.0, 0.2] normalize."""
    def encode(self, metinler, normalize_embeddings=True):
        cikti = []
        for m in metinler:
            v = np.array([1.0, 0.0]) if "alan" in m else np.array([0.0, 1.0]) if "açı" in m else np.array([-1.0, 0.2])
            cikti.append(v / np.linalg.norm(v))
        return cikti


def _hazirla(conn):
    k1 = vt.kazanim_upsert(conn, {"sinif": 12, "ders": "matematik", "hafta": 1, "kod": "12.1", "metin": "Üçgenin alanı"})
    vt.kazanim_upsert(conn, {"sinif": 12, "ders": "matematik", "hafta": 2, "kod": "12.2", "metin": "Dış açı"})
    bid = vt.birim_ekle(conn, "kitap", "k:1", "matematik", 12, "E", "metin")
    s1 = vt.soru_ekle(conn, bid, {**ORNEK_SORU, "soru": "Üçgenin alanı nedir?"})
    s2 = vt.soru_ekle(conn, bid, {**ORNEK_SORU, "soru": "Logaritma nedir?"})
    with conn.cursor() as cur:
        cur.execute("UPDATE soru SET durum='onayli'")
    conn.commit()
    return k1, s1, s2


def test_esik_ustu_etiketlenir_alti_kalir(conn):
    k1, s1, s2 = _hazirla(conn)
    sonuc = etiketle.etiketle(conn, SahteGomucu())
    assert sonuc["etiketlenen"] == 1
    with conn.cursor() as cur:
        cur.execute("SELECT id, kazanim_id, kazanim_kaynak FROM soru ORDER BY id")
        satirlar = cur.fetchall()
    assert satirlar[0] == (s1, k1, "etiket")
    assert satirlar[1][1] is None


def test_kuru_yazmaz(conn):
    _hazirla(conn)
    etiketle.etiketle(conn, SahteGomucu(), kuru=True)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM soru WHERE kazanim_id IS NOT NULL")
        assert cur.fetchone()[0] == 0
