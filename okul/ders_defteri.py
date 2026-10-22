"""Ders defteri: öğretmenin "bu ders için kazanım işlendi" kaydı. Yalnızca sahibine görünür; kimse (yönetici dahil) okumaz."""

import sqlite3
from datetime import date

import zaman

NOT_AZAMI = 500


def isaretle(
    conn: sqlite3.Connection, kullanici_id: int, tarih: date, ders_no: int, sinif: str, ders: str,
    kazanim: str | None, islendi: bool = True, notu: str = "",
) -> None:
    conn.execute(
        "INSERT INTO ders_defteri (kullanici_id, tarih, ders_no, sinif, ders, kazanim, islendi, notu, zaman)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(kullanici_id, tarih, ders_no, sinif) DO UPDATE SET islendi = excluded.islendi,"
        " kazanim = excluded.kazanim, notu = excluded.notu, zaman = excluded.zaman",
        (kullanici_id, tarih.isoformat(), ders_no, sinif, ders, kazanim, int(islendi), (notu or "").strip()[:NOT_AZAMI], zaman.simdi_str()),
    )
    conn.commit()


def gunun_kayitlari(conn: sqlite3.Connection, kullanici_id: int, tarih: date) -> dict[tuple[int, str], sqlite3.Row]:
    return {
        (r["ders_no"], r["sinif"]): r
        for r in conn.execute(
            "SELECT * FROM ders_defteri WHERE kullanici_id = ? AND tarih = ?", (kullanici_id, tarih.isoformat())
        )
    }
