from unittest.mock import MagicMock

from soruhavuzu import kaynak, uretici

KAZ = {"id": 7, "sinif": 10, "ders": "matematik", "hafta": 5, "kod": "10.1.3", "metin": "10.1.3. Üçgenin alanı"}


def _farabi(kitaplar, parcalar):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.side_effect = [kitaplar, parcalar]
    return conn


class Gomucu:
    def encode(self, metinler, normalize_embeddings=True):
        return [[0.1] * 1024 for _ in metinler]


def test_kitap_yoksa_none():
    assert kaynak.bul(_farabi([(1, "Fizik")], []), Gomucu(), 10, "matematik", "x") is None


def test_dusuk_skor_none_yuksek_skor_birlesik_metin():
    dusuk = _farabi([(10, "Matematik")], [(1, 12, "a", 0.60)])      # mesafe 0.60 → skor 0.40
    assert kaynak.bul(dusuk, Gomucu(), 10, "matematik", "x") is None
    iyi = _farabi([(10, "Matematik")], [(1, 12, "alan formülü", 0.30), (2, 13, "üçgen", 0.35)])
    k = kaynak.bul(iyi, Gomucu(), 10, "matematik", "x")
    assert k["chunk_idler"] == [1, 2] and "alan formülü" in k["metin"] and abs(k["skor"] - 0.70) < 1e-9
    assert k["etiket"] == "Matematik 10, s. 12-13"


def test_istem_kazanimi_icerir():
    istem = uretici.istem_kazanim(KAZ, {"etiket": "Matematik 10, s. 12", "metin": "KAYNAK"})
    kullanici = istem[1]["content"]
    assert "KAZANIM: 10.1.3. Üçgenin alanı" in kullanici and "KAYNAK" in kullanici
    assert "bu kazanımı ölçmeli" in kullanici


def test_kitap_yoksa_kazanim_testi_tablosuna_gitmez():
    """Kitap yok → kaynak_yok (spec §4.2); kazanim_test_soru'dan kaynak türetmek ayrı karardır."""
    conn = _farabi([(1, "Fizik")], [])
    assert kaynak.bul(conn, Gomucu(), 10, "matematik", "x") is None
    cur = conn.cursor.return_value.__enter__.return_value
    assert not any("kazanim_test_soru" in str(c.args[0]) for c in cur.execute.call_args_list)


def test_dusuk_skorda_da_kazanim_testi_tablosuna_gitmez():
    conn = _farabi([(10, "Matematik")], [(1, 12, "a", 0.60)])
    assert kaynak.bul(conn, Gomucu(), 10, "matematik", "x") is None
    cur = conn.cursor.return_value.__enter__.return_value
    assert not any("kazanim_test_soru" in str(c.args[0]) for c in cur.execute.call_args_list)
