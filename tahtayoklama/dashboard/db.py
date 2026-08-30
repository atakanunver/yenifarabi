"""SQLite bağlantı yardımcıları ve şema — dashboard'un tek durum kaynağı.

server/tahtalar.json'a YAZILMAZ; bu DB dashboard'un kendi tahta/sınıf
kaydını tutar (bkz. CLAUDE.md "server/tahtalar.json'a geri yazma
YAPILMAZ").
"""

import sqlite3
from pathlib import Path

DB_YOLU = Path(__file__).resolve().parent / "veri" / "yoklama_pano.db"

SEMA = """
CREATE TABLE IF NOT EXISTS siniflar (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ad            TEXT NOT NULL UNIQUE,
    aktif         INTEGER NOT NULL DEFAULT 1,
    guncelleme_zamani TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ogrenciler (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sinif_id      INTEGER NOT NULL REFERENCES siniflar(id) ON DELETE CASCADE,
    no            INTEGER NOT NULL,
    ad_soyad      TEXT NOT NULL,
    cinsiyet      TEXT,
    aktif         INTEGER NOT NULL DEFAULT 1,
    UNIQUE(sinif_id, no)
);

CREATE TABLE IF NOT EXISTS tahtalar (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ad            TEXT NOT NULL UNIQUE,
    ip            TEXT NOT NULL,
    mac           TEXT,
    ssh_kullanici TEXT NOT NULL DEFAULT 'ogretmen',
    -- yoklama.py'yi çalıştıran python yolu tahtadan tahtaya FARKLI —
    -- canlı doğrulandı (2026-08-23): 9-A hariç hepsi kendi
    -- ~/tahtayoklama/venv'ini kullanıyor, yalnızca 9-A Farabi'nin
    -- ~/farabi/client/venv'ini kullanıyor. Faz 4 uzaktan başlatma bunu
    -- sabit kodlamak yerine buradan okumalı.
    python_yolu   TEXT NOT NULL DEFAULT '/home/ogretmen/tahtayoklama/venv/bin/python',
    sinif_id      INTEGER REFERENCES siniflar(id) ON DELETE SET NULL,
    aktif         INTEGER NOT NULL DEFAULT 1,
    guncelleme_zamani TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS yoklama_onbellek (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tarih         TEXT NOT NULL,
    sinif         TEXT NOT NULL,
    ders_no       INTEGER NOT NULL,
    durum         TEXT NOT NULL,
    yok_isimleri  TEXT,
    izinli_isimleri TEXT,
    kaynak_tahta  TEXT,
    kaydedilme_saati TEXT,
    guncelleme_zamani TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(tarih, sinif, ders_no)
);

CREATE TABLE IF NOT EXISTS oturumlar (
    token         TEXT PRIMARY KEY,
    olusturma_zamani TEXT NOT NULL DEFAULT (datetime('now')),
    son_gorulme   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def baglanti() -> sqlite3.Connection:
    """Kısa ömürlü bağlantı — her çağrıda yeni, WAL modunda (bu ölçekte
    10 tahta / okul günü başına birkaç yüz satır — eşzamanlılık baskısı
    yok, per-call açmak yeterince basit ve güvenli)."""
    DB_YOLU.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_YOLU)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def semayi_kur() -> None:
    conn = baglanti()
    try:
        conn.executescript(SEMA)
        conn.commit()
    finally:
        conn.close()
