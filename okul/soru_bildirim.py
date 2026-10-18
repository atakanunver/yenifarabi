"""Öğrencinin "bu soruda sorun var" bildirimi.

Soru havuzu (Postgres) okuldan salt-okunur olduğu için bildirimler okul.db'dedir. ESIK farklı öğrenci bildirince
soru okul içinde gizlenir (gizli_idler → kaynaklar'a `yasak`); havuzdaki asıl karantina soruhavuzu'nun
gece turunda /api/soru-bildirim'den okunarak yapılır."""

import sqlite3

import zaman

TURLER = {
    "sekil": "Şekil / grafik görünmüyor",
    "cevap": "Cevap yanlış görünüyor",
    "anlasilmiyor": "Soru anlaşılmıyor",
}
ESIK = 2  # bu kadar farklı öğrenci bildirirse soru gizlenir
GUNLUK_LIMIT = 20


class BildirimHatasi(ValueError):
    pass


def gordu_mu(conn: sqlite3.Connection, kullanici_id: int, soru_id: int) -> bool:
    """Öğrenci bu soruyu gerçekten sunulmuş mu (Maraton ya da Günlük Görev)? Rastgele id bildirimini engeller."""
    return (
        conn.execute(
            "SELECT 1 FROM maraton_soru s JOIN maraton m ON m.id = s.maraton_id"
            " WHERE m.kullanici_id = ? AND s.soru_id = ? LIMIT 1",
            (kullanici_id, soru_id),
        ).fetchone()
        is not None
        or conn.execute(
            "SELECT 1 FROM bilgi_cevap c JOIN bilgi_tur t ON t.id = c.tur_id"
            " WHERE t.kullanici_id = ? AND c.soru_id = ? LIMIT 1",
            (kullanici_id, soru_id),
        ).fetchone()
        is not None
    )


def bildir(conn: sqlite3.Connection, kullanici_id: int, soru_id: int, tur: str) -> bool:
    """True = yeni kayıt, False = bu soru zaten bildirilmiş."""
    if tur not in TURLER:
        raise BildirimHatasi("Geçersiz bildirim türü.")
    if not gordu_mu(conn, kullanici_id, soru_id):
        raise BildirimHatasi("Bu soru sana gösterilmemiş.")
    bugun = zaman.simdi_str()[:10]
    if (
        conn.execute(
            "SELECT count(*) FROM soru_bildirim WHERE kullanici_id = ? AND substr(zaman, 1, 10) = ?",
            (kullanici_id, bugun),
        ).fetchone()[0]
        >= GUNLUK_LIMIT
    ):
        raise BildirimHatasi("Bugünkü bildirim sınırına ulaştın.")
    cur = conn.execute(
        "INSERT OR IGNORE INTO soru_bildirim (soru_id, kullanici_id, tur, zaman) VALUES (?, ?, ?, ?)",
        (soru_id, kullanici_id, tur, zaman.simdi_str()),
    )
    conn.commit()
    return cur.rowcount == 1


def bildirdi_mi(conn: sqlite3.Connection, kullanici_id: int, soru_id: int) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM soru_bildirim WHERE kullanici_id = ? AND soru_id = ?", (kullanici_id, soru_id)
        ).fetchone()
        is not None
    )


def gizli_idler(conn: sqlite3.Connection) -> list[int]:
    """ESIK ya da daha çok farklı öğrencinin bildirdiği sorular (okulda gösterilmez)."""
    return [
        r[0]
        for r in conn.execute(
            "SELECT soru_id FROM soru_bildirim GROUP BY soru_id HAVING count(*) >= ?", (ESIK,)
        )
    ]


def ozet(conn: sqlite3.Connection) -> list[dict]:
    """Soru başına: {soru_id, kisi, turler{tur: sayı}, son} — en çok bildirilen önce."""
    sonuc: dict[int, dict] = {}
    for r in conn.execute(
        "SELECT soru_id, tur, count(*) AS n, max(zaman) AS son FROM soru_bildirim GROUP BY soru_id, tur"
    ):
        d = sonuc.setdefault(r["soru_id"], {"soru_id": r["soru_id"], "kisi": 0, "turler": {}, "son": ""})
        d["turler"][r["tur"]] = r["n"]
        d["kisi"] += r["n"]
        d["son"] = max(d["son"], r["son"])
    return sorted(sonuc.values(), key=lambda d: (-d["kisi"], d["son"]), reverse=False)
