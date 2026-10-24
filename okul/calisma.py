"""Serbest çalışma ve yanlışları tekrar: XP/rozet/haftalık hedefe BAĞLI DEĞİL (tekrar edilebilir, sömürülemesin).

Sunulan her soru `calisma_soru`'ya anlık kopya olarak yazılır; doğru şık cevaptan önce istemciye gitmez.
Tekrar havuzu: son TEKRAR_GUN günde Günlük Görev / Maraton / çalışmada yanlış yapılan, sonradan doğru yapılmamış,
bildirimle gizlenmemiş ve bugün çalışmada yanıtlanmamış sorular (pas ve "hatalı" kodları yanlış sayılmaz).
"""

import json
import random
import sqlite3
from datetime import timedelta

import arena
import gayret
import maraton
import soru_bildirim
import zaman
from kaynaklar import arena_soru

TEKRAR_GUN = 30
PAS = -3
_KAYITLAR = """
SELECT t.kullanici_id AS u, c.soru_id AS sid, c.cevap_zamani AS z, c.cevap = c.dogru_index AS ok, c.soru, c.secenekler,
       c.dogru_index, c.konu, c.kazanim_kod AS kod, 0 AS bugun_calisma
  FROM bilgi_cevap c JOIN bilgi_tur t ON t.id = c.tur_id WHERE c.cevap >= 0
UNION ALL
SELECT m.kullanici_id, s.soru_id, s.cevap_zamani, s.cevap = s.dogru_index, s.soru, s.secenekler,
       s.dogru_index, s.konu, NULL, 0
  FROM maraton_soru s JOIN maraton m ON m.id = s.maraton_id WHERE s.cevap >= 0
UNION ALL
SELECT kullanici_id, soru_id, cevap_zamani, cevap = dogru_index, soru, secenekler,
       dogru_index, konu, kazanim_kod, substr(cevap_zamani, 1, 10) = ?
  FROM calisma_soru WHERE cevap >= 0
"""


class CalismaHatasi(Exception):
    pass


def yanlislar(conn: sqlite3.Connection, kullanici_id: int) -> list[dict]:
    """Tekrar edilecek sorular (soru başına en son yanlış kayıt)."""
    bugun = zaman.simdi().strftime("%Y-%m-%d")
    sinir = (zaman.simdi() - timedelta(days=TEKRAR_GUN)).strftime(zaman.BICIM)
    gizli = set(soru_bildirim.gizli_idler(conn))
    kayitlar = conn.execute(f"WITH k AS ({_KAYITLAR}) SELECT * FROM k WHERE u = ? ORDER BY z", (bugun, kullanici_id)).fetchall()
    son: dict[int, dict] = {}
    for r in kayitlar:  # z artan: sonraki kayıt öncekini ezer
        if r["ok"]:
            son.pop(r["sid"], None)
        else:
            son[r["sid"]] = {**dict(r), "z": r["z"]}
    bugun_calisilan = {r["sid"] for r in kayitlar if r["bugun_calisma"]}
    return [
        s for sid, s in son.items()
        if s["z"] >= sinir and sid not in gizli and sid not in bugun_calisilan
    ]


def tekrar_sayisi(conn: sqlite3.Connection, kullanici_id: int) -> int:
    return len(yanlislar(conn, kullanici_id))


def getir(conn: sqlite3.Connection, calisma_id: int, kullanici_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM calisma_soru WHERE id = ? AND kullanici_id = ?", (calisma_id, kullanici_id)
    ).fetchone()


def acik(conn: sqlite3.Connection, kullanici_id: int) -> sqlite3.Row | None:
    """Cevaplanmamış sunulan soru (yenileyerek soru değiştirmeyi engeller)."""
    return conn.execute(
        "SELECT * FROM calisma_soru WHERE kullanici_id = ? AND cevap IS NULL ORDER BY id DESC LIMIT 1", (kullanici_id,)
    ).fetchone()


def _ekle(conn: sqlite3.Connection, kullanici_id: int, kaynak: str, s: dict, ders: str | None, kazanim_id: int | None) -> int:
    cur = conn.execute(
        "INSERT INTO calisma_soru (kullanici_id, kaynak, ders, kazanim_id, soru_id, kazanim_kod, soru, secenekler,"
        " dogru_index, konu, gosterim) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (kullanici_id, kaynak, ders, kazanim_id, s["soru_id"], s.get("kazanim_kod"), s["soru"], s["secenekler"],
         s["dogru_index"], s.get("konu"), zaman.simdi_str()),
    )
    conn.commit()
    return cur.lastrowid


def tekrar_baslat(conn: sqlite3.Connection, kullanici_id: int) -> int:
    mevcut = acik(conn, kullanici_id)
    if mevcut is not None:
        return mevcut["id"]
    havuz = yanlislar(conn, kullanici_id)
    if not havuz:
        raise CalismaHatasi("Tekrar edilecek soru kalmadı.")
    s = random.choice(havuz)
    return _ekle(conn, kullanici_id, "tekrar", {**s, "soru_id": s["sid"], "kazanim_kod": s["kod"]}, None, None)


def serbest_baslat(conn: sqlite3.Connection, kullanici_id: int, sinif: str, ders: str, kazanim_id: int | None) -> int:
    """KaynakHatasi yukarı geçer (havuz erişilemez)."""
    mevcut = acik(conn, kullanici_id)
    if mevcut is not None:
        return mevcut["id"]
    if ders not in arena.dersler_uygun(sinif):
        raise CalismaHatasi("Bu ders için çalışma açık değil.")
    duzey = maraton.duzey(sinif)
    if kazanim_id is not None and kazanim_id not in {k["id"] for k in arena_soru.kazanimlar(duzey, ders, soru_bildirim.gizli_idler(conn))}:
        raise CalismaHatasi("Bu kazanımda yeterli soru yok.")
    g = arena._gorulen(conn, kullanici_id)  # Arena+Maraton'da görülenler
    for r in conn.execute("SELECT soru_id FROM calisma_soru WHERE kullanici_id = ?", (kullanici_id,)):
        g[r[0]] = g.get(r[0], 0) + 1
    sorular = arena_soru.sorular(duzey, ders, list(g), 1, g, soru_bildirim.gizli_idler(conn), kazanim_id=kazanim_id)
    if not sorular:
        raise CalismaHatasi("Bu seçimde soru bulunamadı.")
    s = sorular[0]
    return _ekle(
        conn, kullanici_id, "serbest",
        {"soru_id": s["id"], "kazanim_kod": s["kazanim_kod"], "soru": s["soru"],
         "secenekler": json.dumps(s["secenekler"], ensure_ascii=False), "dogru_index": s["dogru_index"], "konu": s["konu"]},
        ders, kazanim_id,
    )


def cevapla(conn: sqlite3.Connection, kullanici_id: int, calisma_id: int, secim: int) -> dict:
    """`cevap IS NULL` koşulu çift gönderimi engeller."""
    c = getir(conn, calisma_id, kullanici_id)
    if c is None:
        raise CalismaHatasi("Soru bulunamadı.")
    if not 0 <= secim < len(json.loads(c["secenekler"])):
        raise CalismaHatasi("Geçersiz şık.")
    if conn.execute(
        "UPDATE calisma_soru SET cevap = ?, cevap_zamani = ? WHERE id = ? AND kullanici_id = ? AND cevap IS NULL",
        (secim, zaman.simdi_str(), calisma_id, kullanici_id),
    ).rowcount != 1:
        conn.rollback()
        raise CalismaHatasi("Bu soru zaten cevaplanmış.")
    gayret_xp = gayret.ver(conn, kullanici_id, f"c{calisma_id}", gayret.gecen(c["gosterim"], zaman.simdi_str()))
    conn.commit()
    return {"dogru": secim == c["dogru_index"], "dogru_index": c["dogru_index"], "gayret_xp": gayret_xp}


def gec(conn: sqlite3.Connection, kullanici_id: int, calisma_id: int) -> None:
    conn.execute(
        "UPDATE calisma_soru SET cevap = ?, cevap_zamani = ? WHERE id = ? AND kullanici_id = ? AND cevap IS NULL",
        (PAS, zaman.simdi_str(), calisma_id, kullanici_id),
    )
    conn.commit()
