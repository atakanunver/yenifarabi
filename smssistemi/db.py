"""SQLite bağlantı yardımcıları ve şema — smssistemi'nin tek durum kaynağı.
tahtayoklama/dashboard'un db.py deseninin bağımsız kopyası (kod paylaşımı
yok, bkz. docs/superpowers/specs/2026-09-19-smssistemi-design.md)."""

import re
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

CREATE TABLE IF NOT EXISTS siniflar (
    id  INTEGER PRIMARY KEY AUTOINCREMENT,
    ad  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS kisiler (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_soyad  TEXT NOT NULL,
    telefon   TEXT,
    sinif_id  INTEGER NOT NULL REFERENCES siniflar (id),
    tur       TEXT NOT NULL CHECK (tur IN ('ogrenci', 'veli'))
);
"""

_VARSAYILAN_SINIFLAR = ["9-A", "9-B", "10-A", "10-B", "11-A", "11-B", "12-A", "12-B"]


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
        if conn.execute("SELECT COUNT(*) FROM siniflar").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO siniflar (ad) VALUES (?)", [(ad,) for ad in _VARSAYILAN_SINIFLAR]
            )
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


# --- Rehber: sınıflar --------------------------------------------------


_SINIF_AD_RE = re.compile(r"^(\d+)-([A-Za-zÇĞİÖŞÜçğıöşü]+)$")


def _sinif_sira_anahtari(ad: str) -> tuple[int, int, str]:
    """'9-A' gibi adları sayı+şubeye göre sıralar ('10-A' 'ad' sütununda
    metinsel sıralamada '9-A'dan önce gelir) — dashboard'un
    `_sinif_sira_anahtari`'sıyla aynı desen, bağımsız kopya."""
    eslesme = _SINIF_AD_RE.match(ad)
    if eslesme:
        return (0, int(eslesme.group(1)), eslesme.group(2))
    return (1, 0, ad)


def siniflar_listele(conn: sqlite3.Connection) -> list[dict]:
    siniflar = [dict(r) for r in conn.execute("SELECT id, ad FROM siniflar")]
    siniflar.sort(key=lambda s: _sinif_sira_anahtari(s["ad"]))
    return siniflar


def sinif_ekle(conn: sqlite3.Connection, ad: str) -> int:
    conn.execute("INSERT OR IGNORE INTO siniflar (ad) VALUES (?)", (ad,))
    conn.commit()
    return conn.execute("SELECT id FROM siniflar WHERE ad = ?", (ad,)).fetchone()["id"]


def sinif_sil(conn: sqlite3.Connection, sinif_id: int) -> bool:
    """Sınıfta kayıtlı kişi varsa silmez, False döner (route bunu kullanıcıya bildirir)."""
    kullanimda = conn.execute(
        "SELECT COUNT(*) FROM kisiler WHERE sinif_id = ?", (sinif_id,)
    ).fetchone()[0]
    if kullanimda:
        return False
    conn.execute("DELETE FROM siniflar WHERE id = ?", (sinif_id,))
    conn.commit()
    return True


# --- Rehber: kişiler -----------------------------------------------------


def kisi_ekle(conn: sqlite3.Connection, ad_soyad: str, telefon: str | None, sinif_id: int, tur: str) -> int:
    imlec = conn.execute(
        "INSERT INTO kisiler (ad_soyad, telefon, sinif_id, tur) VALUES (?, ?, ?, ?)",
        (ad_soyad, telefon or None, sinif_id, tur),
    )
    conn.commit()
    return imlec.lastrowid


def kisi_guncelle(
    conn: sqlite3.Connection, kisi_id: int, ad_soyad: str, telefon: str | None, sinif_id: int, tur: str
) -> None:
    conn.execute(
        "UPDATE kisiler SET ad_soyad = ?, telefon = ?, sinif_id = ?, tur = ? WHERE id = ?",
        (ad_soyad, telefon or None, sinif_id, tur, kisi_id),
    )
    conn.commit()


def kisi_sil(conn: sqlite3.Connection, kisi_id: int) -> None:
    conn.execute("DELETE FROM kisiler WHERE id = ?", (kisi_id,))
    conn.commit()


def kisi_bul_isimle(conn: sqlite3.Connection, ad_soyad: str, sinif_id: int, tur: str) -> dict | None:
    """Toplu yüklemede eşleştirme için — isim/sınıf/tür birebir (boşluk/büyük-küçük
    harf farkı gözetmeksizin) eşleşen kişiyi bulur."""
    satir = conn.execute(
        "SELECT id, telefon FROM kisiler "
        "WHERE sinif_id = ? AND tur = ? AND lower(trim(ad_soyad)) = lower(trim(?))",
        (sinif_id, tur, ad_soyad),
    ).fetchone()
    return dict(satir) if satir else None


def kisiler_listele(
    conn: sqlite3.Connection, sinif_id: int | None = None, tur: str | None = None
) -> list[dict]:
    kosullar = []
    degerler: list = []
    if sinif_id is not None:
        kosullar.append("k.sinif_id = ?")
        degerler.append(sinif_id)
    if tur is not None:
        kosullar.append("k.tur = ?")
        degerler.append(tur)
    kosul_str = f"WHERE {' AND '.join(kosullar)}" if kosullar else ""
    satirlar = conn.execute(
        f"SELECT k.id, k.ad_soyad, k.telefon, k.tur, k.sinif_id, s.ad AS sinif_ad "
        f"FROM kisiler k JOIN siniflar s ON s.id = k.sinif_id "
        f"{kosul_str} ORDER BY s.ad, k.tur, k.ad_soyad",
        degerler,
    ).fetchall()
    return [dict(r) for r in satirlar]


def kisiler_telefonlu(conn: sqlite3.Connection, sinif_id: int, tur: str) -> list[tuple[str, str]]:
    """SMS hedefi doldurmak için — yalnızca telefonu dolu olan kişiler."""
    satirlar = conn.execute(
        "SELECT ad_soyad, telefon FROM kisiler "
        "WHERE sinif_id = ? AND tur = ? AND telefon IS NOT NULL AND telefon != '' "
        "ORDER BY ad_soyad",
        (sinif_id, tur),
    ).fetchall()
    return [(r["ad_soyad"], r["telefon"]) for r in satirlar]
