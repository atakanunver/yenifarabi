"""Soru Maratonu için onaylı soru havuzu (PostgreSQL soru_havuzu) — yalnızca SELECT.

Postgres'e yazılmaz: soru_kullanim / kullanim_sayisi'na dokunulmaz (arena'nın alanları).
Tekrar engeli okul.db'de, öğrenci bazlıdır (maraton.py).
"""

import random

from kaynaklar.kazanim import _baglan

MIN_SORU = 10

GORUNEN_AD = {
    "matematik": "Matematik",
    "fizik": "Fizik",
    "kimya": "Kimya",
    "biyoloji": "Biyoloji",
    "tarih": "Tarih",
    "cografya": "Coğrafya",
    "edebiyat": "Edebiyat",
    "din": "Din Kültürü",
    "ingilizce": "İngilizce",
    "felsefe": "Felsefe",
    "turkce": "Türkçe",
    "gorsel_sanatlar": "Görsel Sanatlar",
    "muzik": "Müzik",
    "beden": "Beden Eğitimi",
    "bilisim": "Bilişim",
}

_FILTRE = (
    "durum = 'onayli' AND secenekler IS NOT NULL AND dogru_index IS NOT NULL"
    " AND jsonb_array_length(secenekler) >= 2"
)


def ders_adi(kod: str) -> str:
    """Kısa havuz kodundan görünen ad; bilinmeyen kodun yalnızca baş harfi büyütülür."""
    if kod in GORUNEN_AD:
        return GORUNEN_AD[kod]
    return (kod[:1].upper() + kod[1:]).replace("_", " ")


def dersler(sinif: int) -> list[tuple[str, int]]:
    """[(ders_kodu, onaylı soru sayısı)] — en az MIN_SORU sorusu olanlar, alfabetik."""
    with _baglan() as c, c.cursor() as cur:
        cur.execute(
            f"SELECT ders, count(*) FROM soru WHERE sinif = %s AND {_FILTRE}"
            " GROUP BY ders HAVING count(*) >= %s ORDER BY ders",
            (sinif, MIN_SORU),
        )
        return [(r[0], r[1]) for r in cur.fetchall()]


def _satir(r) -> dict:
    return {
        "id": r[0],
        "konu": r[1],
        "soru": r[2],
        "secenekler": [str(s) for s in r[3]],
        "dogru_index": int(r[4]),
        "kaynak": r[5],
    }


_SUTUN = "id, konu, soru, secenekler, dogru_index, kaynak"


def sorular(
    sinif: int,
    ders: str,
    haric_ids: list[int],
    n: int = 10,
    gorulme: dict[int, int] | None = None,
) -> list[dict]:
    """n rastgele soru. Önce haric_ids dışındakiler; yetmezse en az görülenlerle tamamlanır."""
    haric = list(haric_ids)
    with _baglan() as c, c.cursor() as cur:
        cur.execute(
            f"SELECT {_SUTUN} FROM soru WHERE sinif = %s AND ders = %s AND {_FILTRE}"
            " AND id <> ALL(%s) ORDER BY random() LIMIT %s",
            (sinif, ders, haric, n),
        )
        sonuc = [_satir(r) for r in cur.fetchall()]
        if len(sonuc) < n and haric:
            cur.execute(
                f"SELECT {_SUTUN} FROM soru WHERE sinif = %s AND ders = %s AND {_FILTRE}"
                " AND id = ANY(%s)",
                (sinif, ders, haric),
            )
            eski = [_satir(r) for r in cur.fetchall()]
            random.shuffle(eski)
            g = gorulme or {}
            eski.sort(key=lambda s: g.get(s["id"], 0))  # kararlı: eşitlikte rastgele
            sonuc += eski[: n - len(sonuc)]
    random.shuffle(sonuc)
    return sonuc
