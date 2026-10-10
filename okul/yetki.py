"""Tek yetki merkezi: kim hangi öğrenciyi/sınıfı görebilir. Yetkisiz → 404."""

import sqlite3

import zaman
from fastapi import HTTPException
from metin import normalize_isim

Satir = sqlite3.Row


def ogretmen_siniflari(conn: sqlite3.Connection, ogretmen_id: int) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT sinif FROM ogretmen_gorev WHERE ogretmen_id = ? ORDER BY sinif",
            (ogretmen_id,),
        )
    ]


def ogretmen_gorevleri(
    conn: sqlite3.Connection, ogretmen_id: int
) -> list[tuple[str, str]]:
    return [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT sinif, ders FROM ogretmen_gorev WHERE ogretmen_id = ? ORDER BY sinif, ders",
            (ogretmen_id,),
        )
    ]


def veli_cocuklari(conn: sqlite3.Connection, veli_id: int) -> list[Satir]:
    return conn.execute(
        "SELECT o.* FROM veli_ogrenci vo JOIN ogrenci o ON o.id = vo.ogrenci_id"
        " WHERE vo.veli_id = ? ORDER BY o.ad_soyad",
        (veli_id,),
    ).fetchall()


def ogrenci_kaydi(conn: sqlite3.Connection, kullanici_id: int) -> Satir | None:
    return conn.execute(
        "SELECT * FROM ogrenci WHERE kullanici_id = ?", (kullanici_id,)
    ).fetchone()


def kullanici_siniflari(conn: sqlite3.Connection, k: Satir) -> list[str] | None:
    """Kullanıcının ilgili olduğu sınıflar; None = tüm okul (yönetici)."""
    if k["rol"] == "yonetici":
        return None
    if k["rol"] == "ogretmen":
        return ogretmen_siniflari(conn, k["id"])
    if k["rol"] == "veli":
        return sorted({c["sinif"] for c in veli_cocuklari(conn, k["id"])})
    o = ogrenci_kaydi(conn, k["id"])
    return [o["sinif"]] if o else []


def ogrenci_gorebilir(conn: sqlite3.Connection, k: Satir, ogrenci_id: int) -> bool:
    o = conn.execute("SELECT * FROM ogrenci WHERE id = ?", (ogrenci_id,)).fetchone()
    if o is None:
        return False
    rol = k["rol"]
    if rol == "yonetici":
        return True
    if rol == "ogrenci":
        return o["kullanici_id"] == k["id"]
    if rol == "veli":
        return (
            conn.execute(
                "SELECT 1 FROM veli_ogrenci WHERE veli_id = ? AND ogrenci_id = ?",
                (k["id"], ogrenci_id),
            ).fetchone()
            is not None
        )
    if rol == "ogretmen":
        return o["sinif"] in ogretmen_siniflari(conn, k["id"])
    return False


def ogrenci_getir(conn: sqlite3.Connection, k: Satir, ogrenci_id: int) -> Satir:
    if not ogrenci_gorebilir(conn, k, ogrenci_id):
        raise HTTPException(404)
    return conn.execute("SELECT * FROM ogrenci WHERE id = ?", (ogrenci_id,)).fetchone()


def sinif_yetkili(conn: sqlite3.Connection, k: Satir, sinif: str) -> bool:
    if k["rol"] == "yonetici":
        return True
    return k["rol"] == "ogretmen" and sinif in ogretmen_siniflari(conn, k["id"])


def sinif_ders_yetkili(
    conn: sqlite3.Connection, k: Satir, sinif: str, ders: str
) -> bool:
    if k["rol"] == "yonetici":
        return True
    if k["rol"] != "ogretmen":
        return False
    hedef = normalize_isim(ders)
    return any(
        s == sinif and normalize_isim(d) == hedef
        for s, d in ogretmen_gorevleri(conn, k["id"])
    )


def erisim_kaydet(
    conn: sqlite3.Connection,
    k: Satir,
    eylem: str,
    ogrenci_id: int | None,
    ip: str | None,
) -> None:
    conn.execute(
        "INSERT INTO erisim_log (kullanici_id, eylem, ogrenci_id, zaman, ip) VALUES (?, ?, ?, ?, ?)",
        (k["id"], eylem, ogrenci_id, zaman.simdi_str(), ip),
    )
    conn.commit()
