"""Bilgi Arenası Günlük Görev soruları (PostgreSQL soru_havuzu) — yalnızca SELECT.

Soru Maratonu havuz kodunu (kaynaklar/soru.py) olduğu gibi kullanır; bu modül yalnızca kazanım
bilgisini de döndürür. Kazanım eşleşmesi çoğunlukla otomatik atanmıştır: ekranda "tahmini" denir.
Postgres'e yazılmaz (soru_kullanim / kullanim_sayisi arena'nın alanları).
"""

import random

from kaynaklar.kazanim import _baglan
from kaynaklar.soru import _FILTRE

_SUTUN = (
    "s.id, s.konu, s.soru, s.secenekler, s.dogru_index, s.kazanim_id, k.kod, k.metin"
)
_KAYNAK = "soru s LEFT JOIN kazanim k ON k.id = s.kazanim_id"
_F = _FILTRE.replace("durum", "s.durum").replace("secenekler", "s.secenekler").replace(
    "dogru_index", "s.dogru_index"
)


def _satir(r) -> dict:
    return {
        "id": r[0],
        "konu": r[1],
        "soru": r[2],
        "secenekler": [str(x) for x in r[3]],
        "dogru_index": int(r[4]),
        "kazanim_id": r[5],
        "kazanim_kod": r[6],
        "kazanim_metin": r[7],
    }


def sorular(
    sinif: int,
    ders: str,
    haric_ids: list[int],
    n: int = 5,
    gorulme: dict[int, int] | None = None,
    yasak: list[int] | None = None,
) -> list[dict]:
    """n rastgele soru; önce görülmemişler, yetmezse en az görülenlerle tamamlanır. yasak: bildirimle gizlenenler."""
    haric = list(haric_ids)
    yasak = list(yasak or []) or [0]
    with _baglan() as c, c.cursor() as cur:
        cur.execute(
            f"SELECT {_SUTUN} FROM {_KAYNAK} WHERE s.sinif = %s AND s.ders = %s AND {_F}"
            " AND s.id <> ALL(%s) AND s.id <> ALL(%s) ORDER BY random() LIMIT %s",
            (sinif, ders, haric, yasak, n),
        )
        sonuc = [_satir(r) for r in cur.fetchall()]
        if len(sonuc) < n and haric:
            cur.execute(
                f"SELECT {_SUTUN} FROM {_KAYNAK} WHERE s.sinif = %s AND s.ders = %s AND {_F}"
                " AND s.id = ANY(%s) AND s.id <> ALL(%s)",
                (sinif, ders, haric, yasak),
            )
            eski = [_satir(r) for r in cur.fetchall()]
            random.shuffle(eski)
            g = gorulme or {}
            eski.sort(key=lambda s: g.get(s["id"], 0))
            sonuc += eski[: n - len(sonuc)]
    random.shuffle(sonuc)
    return sonuc
