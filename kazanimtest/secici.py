"""kazanimtest/secici.py — Kazanım metnine en yakın aday sorular.

Önce MEB `kazanim_test_soru` (farabi DB, pgvector; yalnızca cevabı dolu + 4 şıklı satırlar),
sonra soru havuzu `soru` (durum='onayli'; bu tabloda embedding yok → bge-m3 ile burada
hesaplanır). Embedding: server/main.py gibi `SentenceTransformer("BAAI/bge-m3")` ama CPU.
Ders eşlemesi `soruhavuzu.dersler.ders_anahtari` ile yapılır (MEB tablosunda "Fizik",
"Türk Dili ve Edebiyatı" gibi başlık-biçimli adlar var).
"""

import json
import os

import psycopg2
import psycopg2.extras

from soruhavuzu.dersler import ders_anahtari

EMBED_MODEL = "BAAI/bge-m3"
_MODEL = None


def baglan(dbname: str):
    return psycopg2.connect(host="127.0.0.1", dbname=dbname, user="farabi")


def gomme_modeli():
    global _MODEL
    if _MODEL is None:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(EMBED_MODEL, device="cpu")
    return _MODEL


def vektor(metin: str, model=None) -> list[float]:
    m = model or gomme_modeli()
    return [float(x) for x in m.encode(metin, normalize_embeddings=True)]


def _kosinus(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def meb_adaylari(conn, duzey: int, ders: str, kvek: list[float], limit: int) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT DISTINCT ders FROM kazanim_test_soru WHERE sinif = %s", (duzey,))
        adlar = [r["ders"] for r in cur.fetchall() if ders_anahtari(r["ders"] or "") == ders]
        if not adlar:
            return []
        cur.execute(
            "SELECT id, soru_metni, secenekler, cevap, kaynak_dosya, soru_no, "
            "embedding <=> %s::vector AS mesafe FROM kazanim_test_soru "
            "WHERE sinif = %s AND ders = ANY(%s) AND embedding IS NOT NULL "
            "AND cevap IS NOT NULL AND btrim(cevap) ~ '^[A-Da-d]$' "
            "ORDER BY mesafe LIMIT %s",
            ("[" + ",".join(f"{x:.6f}" for x in kvek) + "]", duzey, adlar, limit * 3),
        )
        satirlar = cur.fetchall()
    sonuc = []
    for r in satirlar:
        sec = r["secenekler"]
        if isinstance(sec, str):
            sec = json.loads(sec)
        if not isinstance(sec, dict) or sorted(sec) != ["A", "B", "C", "D"]:
            continue
        sonuc.append(
            {
                "kimlik": f"meb:{r['id']}",
                "kaynak": "meb",
                "db_id": r["id"],
                "soru": r["soru_metni"],
                "secenekler": [str(sec[h]) for h in "ABCD"],
                "dogru_index": "ABCD".index(r["cevap"].strip().upper()),
                "etiket": f"MEB kazanım testi ({r['kaynak_dosya']}, soru {r['soru_no']})",
                "benzerlik": 1.0 - float(r["mesafe"]),
            }
        )
    return sonuc[:limit]


def havuz_adaylari(conn, duzey: int, ders: str, kvek: list[float], limit: int, model=None) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id, konu, soru, secenekler, dogru_index, kaynak, kullanim_sayisi FROM soru "
            "WHERE sinif = %s AND ders = %s AND durum = 'onayli' "
            "ORDER BY kullanim_sayisi, id LIMIT 800",
            (duzey, ders),
        )
        satirlar = cur.fetchall()
    if not satirlar:
        return []
    m = model or gomme_modeli()
    vekler = m.encode([f"{r['konu']}. {r['soru']}" for r in satirlar], normalize_embeddings=True)
    sonuc = []
    for r, v in zip(satirlar, vekler):
        sec = r["secenekler"]
        if isinstance(sec, str):
            sec = json.loads(sec)
        if not isinstance(sec, list) or len(sec) != 4:
            continue
        sonuc.append(
            {
                "kimlik": f"havuz:{r['id']}",
                "kaynak": "havuz",
                "db_id": r["id"],
                "soru": r["soru"],
                "secenekler": [str(x) for x in sec],
                "dogru_index": int(r["dogru_index"]),
                "etiket": r["kaynak"],
                "benzerlik": _kosinus(kvek, [float(x) for x in v]),
            }
        )
    sonuc.sort(key=lambda a: -a["benzerlik"])
    return sonuc[:limit]


def adaylar(farabi_conn, havuz_conn, duzey: int, ders: str, kazanim_metni: str, azami: int = 30, model=None) -> list[dict]:
    """MEB önce (benzerlik sırasıyla), kalan yer onaylı havuzdan; toplam ≤ azami."""
    kvek = vektor(kazanim_metni, model)
    liste = meb_adaylari(farabi_conn, duzey, ders, kvek, azami)
    if len(liste) < azami:
        liste += havuz_adaylari(havuz_conn, duzey, ders, kvek, azami - len(liste), model)
    return liste[:azami]
