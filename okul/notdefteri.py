"""Öğretmenin kişisel not defteri. Yalnızca sahibine görünür (yönetici dahil); push/rapor/duyuruya girmez."""

import sqlite3

import zaman

METIN_AZAMI = 2000
NOT_AZAMI = 500


class NotHatasi(ValueError):
    pass


def _metin(metin: str) -> str:
    metin = (metin or "").strip()
    if not metin:
        raise NotHatasi("Not boş olamaz.")
    if len(metin) > METIN_AZAMI:
        raise NotHatasi(f"Not en çok {METIN_AZAMI} karakter olabilir.")
    return metin


def ekle(conn: sqlite3.Connection, kullanici_id: int, metin: str, sinif: str | None = None, ders: str | None = None, yapilacak: bool = False) -> int:
    metin = _metin(metin)
    if conn.execute("SELECT count(*) FROM ogretmen_not WHERE kullanici_id = ?", (kullanici_id,)).fetchone()[0] >= NOT_AZAMI:
        raise NotHatasi(f"En çok {NOT_AZAMI} not saklanır; eskilerini silin.")
    simdi = zaman.simdi_str()
    cur = conn.execute(
        "INSERT INTO ogretmen_not (kullanici_id, metin, sinif, ders, yapilacak, olusturma, guncelleme) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (kullanici_id, metin, sinif or None, ders or None, int(yapilacak), simdi, simdi),
    )
    conn.commit()
    return cur.lastrowid


def getir(conn: sqlite3.Connection, kullanici_id: int, not_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM ogretmen_not WHERE id = ? AND kullanici_id = ?", (not_id, kullanici_id)).fetchone()


def liste(conn: sqlite3.Connection, kullanici_id: int, limit: int = 100) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM ogretmen_not WHERE kullanici_id = ? ORDER BY tamam, guncelleme DESC, id DESC LIMIT ?",
        (kullanici_id, limit),
    ).fetchall()


def yapilacaklar(conn: sqlite3.Connection, kullanici_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM ogretmen_not WHERE kullanici_id = ? AND yapilacak = 1 AND tamam = 0 ORDER BY id", (kullanici_id,)
    ).fetchall()


def guncelle(conn: sqlite3.Connection, kullanici_id: int, not_id: int, metin: str, yapilacak: bool) -> bool:
    metin = _metin(metin)
    cur = conn.execute(
        "UPDATE ogretmen_not SET metin = ?, yapilacak = ?, guncelleme = ? WHERE id = ? AND kullanici_id = ?",
        (metin, int(yapilacak), zaman.simdi_str(), not_id, kullanici_id),
    )
    conn.commit()
    return cur.rowcount > 0


def tamam_degistir(conn: sqlite3.Connection, kullanici_id: int, not_id: int) -> bool:
    cur = conn.execute(
        "UPDATE ogretmen_not SET tamam = 1 - tamam, guncelleme = ? WHERE id = ? AND kullanici_id = ?",
        (zaman.simdi_str(), not_id, kullanici_id),
    )
    conn.commit()
    return cur.rowcount > 0


def sil(conn: sqlite3.Connection, kullanici_id: int, not_id: int) -> bool:
    cur = conn.execute("DELETE FROM ogretmen_not WHERE id = ? AND kullanici_id = ?", (not_id, kullanici_id))
    conn.commit()
    return cur.rowcount > 0
