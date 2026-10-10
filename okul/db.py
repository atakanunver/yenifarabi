"""okul.db — şema, sürümlü göç (PRAGMA user_version), bağlantı."""

import sqlite3

from ayarlar import AYAR

SEMA_V1 = """
CREATE TABLE kullanici (
    id              INTEGER PRIMARY KEY,
    rol             TEXT NOT NULL CHECK (rol IN ('ogrenci','veli','ogretmen','yonetici')),
    ad_soyad        TEXT NOT NULL,
    kullanici_adi   TEXT UNIQUE,
    telefon         TEXT,
    sifre_hash      TEXT,
    sifre_degismeli INTEGER NOT NULL DEFAULT 1,
    aktif           INTEGER NOT NULL DEFAULT 1,
    olusturma       TEXT NOT NULL
);
CREATE UNIQUE INDEX kullanici_veli_telefon ON kullanici(telefon) WHERE rol = 'veli';

CREATE TABLE ogrenci (
    id            INTEGER PRIMARY KEY,
    okul_no       INTEGER NOT NULL UNIQUE,
    ad_soyad      TEXT NOT NULL,
    sinif         TEXT NOT NULL,
    kullanici_id  INTEGER UNIQUE REFERENCES kullanici(id)
);

CREATE TABLE veli_ogrenci (
    veli_id     INTEGER NOT NULL REFERENCES kullanici(id),
    ogrenci_id  INTEGER NOT NULL REFERENCES ogrenci(id),
    yakinlik    TEXT,
    PRIMARY KEY (veli_id, ogrenci_id)
);

CREATE TABLE ogretmen_gorev (
    ogretmen_id  INTEGER NOT NULL REFERENCES kullanici(id),
    sinif        TEXT NOT NULL,
    ders         TEXT NOT NULL,
    PRIMARY KEY (ogretmen_id, sinif, ders)
);

CREATE TABLE duyuru (
    id         INTEGER PRIMARY KEY,
    yazar_id   INTEGER NOT NULL REFERENCES kullanici(id),
    baslik     TEXT NOT NULL,
    metin      TEXT NOT NULL,
    hedef_tur  TEXT NOT NULL CHECK (hedef_tur IN ('okul','sinif','rol')),
    hedef      TEXT,
    yayin      TEXT NOT NULL,
    bitis      TEXT
);

CREATE TABLE odev (
    id           INTEGER PRIMARY KEY,
    ogretmen_id  INTEGER NOT NULL REFERENCES kullanici(id),
    sinif        TEXT NOT NULL,
    ders         TEXT NOT NULL,
    tur          TEXT NOT NULL CHECK (tur IN ('klasik','test')),
    baslik       TEXT NOT NULL,
    aciklama     TEXT NOT NULL DEFAULT '',
    teslim       TEXT NOT NULL,
    olusturma    TEXT NOT NULL
);

CREATE TABLE odev_soru (
    id       INTEGER PRIMARY KEY,
    odev_id  INTEGER NOT NULL REFERENCES odev(id) ON DELETE CASCADE,
    sira     INTEGER NOT NULL,
    metin    TEXT NOT NULL,
    siklar   TEXT NOT NULL,
    dogru    INTEGER NOT NULL,
    kazanim  TEXT NOT NULL DEFAULT '',
    kaynak   TEXT NOT NULL DEFAULT 'elle'
);

CREATE TABLE odev_teslim (
    odev_id     INTEGER NOT NULL REFERENCES odev(id) ON DELETE CASCADE,
    ogrenci_id  INTEGER NOT NULL REFERENCES ogrenci(id),
    durum       TEXT NOT NULL CHECK (durum IN ('yapti','tamam')),
    puan        INTEGER,
    cevaplar    TEXT,
    zaman       TEXT NOT NULL,
    PRIMARY KEY (odev_id, ogrenci_id)
);

CREATE TABLE oturum (
    token_hash    TEXT PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    olusturma     TEXT NOT NULL,
    son_gorulme   TEXT NOT NULL,
    cihaz         TEXT
);

CREATE TABLE sms_kod (
    telefon         TEXT PRIMARY KEY,
    kod_hash        TEXT NOT NULL,
    son_gecerlilik  TEXT NOT NULL,
    deneme          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE giris_deneme (
    anahtar   TEXT PRIMARY KEY,
    sayac     INTEGER NOT NULL,
    son_hata  TEXT NOT NULL
);

CREATE TABLE erisim_log (
    id            INTEGER PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL,
    eylem         TEXT NOT NULL,
    ogrenci_id    INTEGER,
    zaman         TEXT NOT NULL,
    ip            TEXT
);

CREATE TABLE aktarim_taslak (
    id         TEXT PRIMARY KEY,
    tur        TEXT NOT NULL,
    veri       TEXT NOT NULL,
    olusturma  TEXT NOT NULL
);
"""

GOCLER = [SEMA_V1]


def baglanti() -> sqlite3.Connection:
    AYAR.db_yolu.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(AYAR.db_yolu, timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def sema_kur() -> None:
    conn = baglanti()
    try:
        surum = conn.execute("PRAGMA user_version").fetchone()[0]
        for i in range(surum, len(GOCLER)):
            conn.executescript(GOCLER[i])
            conn.execute(f"PRAGMA user_version = {i + 1}")
        conn.commit()
    finally:
        conn.close()
