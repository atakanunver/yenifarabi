"""SQLite bağlantı yardımcıları ve şema — smssistemi'nin tek durum kaynağı.
tahtayoklama/dashboard'un db.py deseninin bağımsız kopyası (kod paylaşımı
yok, bkz. docs/superpowers/specs/2026-09-19-smssistemi-design.md)."""

import sqlite3
from pathlib import Path

DB_YOLU = Path(__file__).resolve().parent / "veri" / "smssistemi.db"

SEMA = """
CREATE TABLE IF NOT EXISTS gonderimler (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    gonderim_id   TEXT NOT NULL,
    isim          TEXT,
    telefon       TEXT NOT NULL,
    mesaj         TEXT NOT NULL,
    durum         TEXT NOT NULL,
    hata_metni    TEXT,
    zaman         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS oturumlar (
    token             TEXT PRIMARY KEY,
    olusturma_zamani  TEXT NOT NULL DEFAULT (datetime('now')),
    son_gorulme       TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def baglanti() -> sqlite3.Connection:
    DB_YOLU.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_YOLU)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def semayi_kur() -> None:
    conn = baglanti()
    try:
        conn.executescript(SEMA)
        conn.commit()
    finally:
        conn.close()


def gonderim_kaydet(
    conn: sqlite3.Connection,
    gonderim_id: str,
    isim: str,
    telefon: str,
    mesaj: str,
    durum: str,
    hata_metni: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO gonderimler (gonderim_id, isim, telefon, mesaj, durum, hata_metni) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (gonderim_id, isim, telefon, mesaj, durum, hata_metni),
    )
    conn.commit()


def gonderim_satirlari(conn: sqlite3.Connection, gonderim_id: str) -> list[dict]:
    satirlar = conn.execute(
        "SELECT isim, telefon, durum, hata_metni, zaman FROM gonderimler "
        "WHERE gonderim_id = ? ORDER BY id",
        (gonderim_id,),
    ).fetchall()
    return [dict(r) for r in satirlar]


def gonderim_ozetleri(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    satirlar = conn.execute(
        "SELECT gonderim_id, "
        "MIN(zaman) AS ilk_zaman, "
        "COUNT(*) AS toplam, "
        "SUM(CASE WHEN durum = 'gonderildi' THEN 1 ELSE 0 END) AS basarili, "
        "SUM(CASE WHEN durum = 'hata' THEN 1 ELSE 0 END) AS hatali "
        "FROM gonderimler GROUP BY gonderim_id ORDER BY ilk_zaman DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in satirlar]


def gonderim_basarisizlari(conn: sqlite3.Connection, gonderim_id: str) -> list[tuple[str, str, str]]:
    satirlar = conn.execute(
        "SELECT isim, telefon, mesaj FROM gonderimler "
        "WHERE gonderim_id = ? AND durum = 'hata' AND telefon != '' "
        "ORDER BY id",
        (gonderim_id,),
    ).fetchall()
    return [(r["isim"], r["telefon"], r["mesaj"]) for r in satirlar]
