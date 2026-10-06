"""havuz.py — soru_havuzu veritabanından (yalnızca AGY onaylı) anında soru çeker.

Havuz boş/erişilemezse None döner; çağıran mevcut RAG+Ollama / statik akışa düşer.
Kullanıcı kararı (2026-10-05): AGY denetiminden geçmemiş soru oyunlara GİTMEZ."""

import logging
import random

log = logging.getLogger("arena.havuz")
SUTUNLAR = "id, konu, zorluk, soru, kisa_cevap, secenekler, dogru_index, kaynak"
RENKLER = [
    ("from-blue-600 to-indigo-600", "text-blue-400 bg-blue-500/20 border-blue-500/40"),
    (
        "from-emerald-600 to-teal-600",
        "text-emerald-400 bg-emerald-500/20 border-emerald-500/40",
    ),
    (
        "from-amber-600 to-orange-600",
        "text-amber-400 bg-amber-500/20 border-amber-500/40",
    ),
    (
        "from-purple-600 to-pink-600",
        "text-purple-400 bg-purple-500/20 border-purple-500/40",
    ),
]


def _db_sorgu(sql, parametreler):
    import psycopg2

    with psycopg2.connect(
        host="127.0.0.1", dbname="soru_havuzu", user="farabi", connect_timeout=3
    ) as c, c.cursor() as cur:
        cur.execute(sql, parametreler)
        return cur.fetchall()


def _kullanildi(ids, sorgu):
    if not ids or sorgu is not None:
        return
    try:
        import psycopg2

        with psycopg2.connect(
            host="127.0.0.1", dbname="soru_havuzu", user="farabi", connect_timeout=3
        ) as c:
            with c.cursor() as cur:
                cur.execute(
                    "UPDATE soru SET kullanim_sayisi = kullanim_sayisi + 1 WHERE id = ANY(%s)",
                    (list(ids),),
                )
    except Exception as e:  # noqa: BLE001 — sayaç yardımcı
        log.warning("kullanım sayacı yazılamadı: %s", e)


def _cek(ders, sinif, konu, sorgu, limit=400):
    sql = (
        f"SELECT {SUTUNLAR} FROM soru WHERE durum = 'onayli' AND ders = %s AND sinif = %s "
        + ("AND konu ILIKE %s " if konu else "")
        + "ORDER BY kullanim_sayisi, random() LIMIT %s"
    )
    p = (ders, sinif) + ((f"%{konu}%",) if konu else ()) + (limit,)
    try:
        return (sorgu or _db_sorgu)(sql, p)
    except Exception as e:  # noqa: BLE001 — havuz yardımcı; hata = eski akış
        log.warning("havuz okunamadı: %s", e)
        return None


def jeopardy_seti(
    ders: str, sinif: int, konu: str = "", sorgu=None
) -> list[dict] | None:
    """4 konu × 4 zorluk (100–400 puan); ollama_soru_uret ile aynı biçim."""
    satirlar = _cek(ders, sinif, konu, sorgu)
    if not satirlar:
        return None
    konular: dict[str, dict[int, tuple]] = {}
    for s in satirlar:
        konular.setdefault(s[1], {}).setdefault(s[2], s)
    tam = [k for k, z in konular.items() if len(z) == 4]
    if len(tam) < 4:
        return None
    random.shuffle(tam)
    cikti, ids = [], []
    for i, k in enumerate(tam[:4]):
        renk, rozet = RENKLER[i]
        sorular = []
        for z in (1, 2, 3, 4):
            s = konular[k][z]
            ids.append(s[0])
            sorular.append(
                {
                    "points": z * 100,
                    "q": s[3],
                    "a": s[4],
                    "kaynak": s[7],
                    "answered": False,
                }
            )
        cikti.append(
            {
                "id": f"havuz_kat_{i + 1}",
                "name": k,
                "color": renk,
                "badgeColor": rozet,
                "questions": sorular,
            }
        )
    _kullanildi(ids, sorgu)
    return cikti


def petek_sorulari(ders: str, sinif: int, adet: int, sorgu=None) -> list[dict] | None:
    """HexaFetih: her petek için FARKLI bir çoktan seçmeli soru."""
    satirlar = _cek(ders, sinif, "", sorgu)
    if not satirlar or len(satirlar) < adet:
        return None
    secilen = satirlar[:adet]
    _kullanildi([s[0] for s in secilen], sorgu)
    return [
        {
            "konu": s[1],
            "q": s[3],
            "secenekler": list(s[5]),
            "a": s[5][s[6]],
            "kaynak": s[7],
        }
        for s in secilen
    ]


def duello_sorulari(ders: str, sinif: int, adet: int = 10, sorgu=None) -> list[dict] | None:
    """Tahta Düellosu: 10 adet çoktan seçmeli yarışma sorusu."""
    return petek_sorulari(ders, sinif, adet, sorgu)

