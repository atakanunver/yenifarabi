"""kazanimlar.json → kazanim satırları."""
import json

from soruhavuzu import kazanimlar, vt

ORNEK = {"haftalar": {"1": "2026-09-14", "2": "2026-09-21"},
         "kazanimlar": {"9": {"kimya": {"1": "KİM.9.1.1. Kimya biliminin katkısı",
                                        "2": "KİM.9.1.1. Kimya biliminin katkısı"},
                              "beden eğitimi": {"1": "Spor"}},
                        "10": {"matematik": {"5": "10.1.3. Üçgenin alanı\n10.1.4. Dörtgenin alanı"}}}}


def test_oku_boler_esler_atlar(tmp_path):
    y = tmp_path / "k.json"
    y.write_text(json.dumps(ORNEK, ensure_ascii=False), encoding="utf-8")
    satirlar, atlanan = kazanimlar.oku(y)
    assert {"beden eğitimi"} == atlanan
    mat = [s for s in satirlar if s["ders"] == "matematik"]
    assert [(s["hafta"], s["kod"]) for s in mat] == [(5, "10.1.3"), (5, "10.1.4")]
    kim = [s for s in satirlar if s["ders"] == "kimya"]
    assert [s["hafta"] for s in kim] == [1, 2] and kim[0]["kod"] == "KİM.9.1.1"


def test_upsert_cogaltmaz(conn):
    k = {"sinif": 9, "ders": "kimya", "hafta": 1, "kod": "KİM.9.1.1", "metin": "KİM.9.1.1. X"}
    a = vt.kazanim_upsert(conn, k)
    b = vt.kazanim_upsert(conn, k)
    assert a == b
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM kazanim")
        assert cur.fetchone()[0] == 1
