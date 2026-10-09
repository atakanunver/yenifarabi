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


class _UzakGomucu:
    """bilgehan GPU bge-m3 servisi (uzak_model) — encode(metin, normalize_embeddings=...) arayüzü."""

    def __init__(self, uzak):
        self._u = uzak

    def encode(self, metin, normalize_embeddings=True):
        return self._u.encode(metin, normalize_embeddings=normalize_embeddings)


def gomme_modeli():
    """2026-10-08: bilgehan GPU servisi (FARABI_EMBED_URL) varsa oradan; yoksa yerel CPU (eski yol)."""
    global _MODEL
    if _MODEL is None:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
        from uzak_model import ayar_oku, toplu_gomme_modeli

        url, _ = ayar_oku()
        if url:
            _MODEL = _UzakGomucu(toplu_gomme_modeli(EMBED_MODEL))
        else:
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


def kazanim_adaylari(conn, duzey: int, ders: str, kazanim_metni: str, limit: int) -> list[dict]:
    """Soru havuzunda `kazanim_id` ile bu kazanım metin(ler)ine bağlı onaylı sorular (benzerlik 1.0 sayılır).
    Yanıt şekli `havuz_adaylari` ile aynı; az kullanılan önce."""
    metinler = [m.strip() for m in (kazanim_metni or "").split("\n") if m.strip()]
    if conn is None or not metinler or limit <= 0:
        return []
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT s.id, s.konu, s.soru, s.secenekler, s.dogru_index, s.kaynak FROM soru s "
            "JOIN kazanim k ON k.id = s.kazanim_id "
            "WHERE k.sinif = %s AND k.ders = %s AND k.metin = ANY(%s) AND s.durum = 'onayli' "
            "ORDER BY s.kullanim_sayisi, s.id LIMIT %s",
            (duzey, ders, metinler, limit),
        )
        satirlar = cur.fetchall()
    sonuc = []
    for r in satirlar:
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
                "benzerlik": 1.0,
            }
        )
    return sonuc


def adaylar(farabi_conn, havuz_conn, duzey: int, ders: str, kazanim_metni: str, azami: int = 30, model=None) -> list[dict]:
    """MEB önce (benzerlik sırasıyla), sonra kazanim_id'li onaylı havuz soruları, kalan yer benzerlikle; toplam ≤ azami."""
    kvek = vektor(kazanim_metni, model)
    liste = meb_adaylari(farabi_conn, duzey, ders, kvek, azami)
    if len(liste) < azami:
        liste += kazanim_adaylari(havuz_conn, duzey, ders, kazanim_metni, azami - len(liste))
    if len(liste) < azami:
        var = {a["kimlik"] for a in liste}
        kalan = azami - len(liste)
        ek = havuz_adaylari(havuz_conn, duzey, ders, kvek, kalan + len(var), model)
        liste += [a for a in ek if a["kimlik"] not in var][:kalan]
    return liste[:azami]
