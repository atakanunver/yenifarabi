"""Duyurular: ekleme yetkisi ve hedefe göre görünürlük."""

import sqlite3

import yetki
import zaman

ROLLER = ("ogrenci", "veli", "ogretmen", "yonetici")


def ekleyebilir_mi(
    conn: sqlite3.Connection, k: sqlite3.Row, hedef_tur: str, hedef: str | None
) -> bool:
    if k["rol"] == "yonetici":
        if hedef_tur == "okul":
            return True
        if hedef_tur == "rol":
            return hedef in ROLLER
        return hedef_tur == "sinif" and bool(hedef)
    if k["rol"] == "ogretmen":
        return hedef_tur == "sinif" and hedef in yetki.ogretmen_siniflari(conn, k["id"])
    return False


def duyuru_ekle(
    conn: sqlite3.Connection,
    yazar_id: int,
    baslik: str,
    metin: str,
    hedef_tur: str,
    hedef: str | None = None,
    bitis: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO duyuru (yazar_id, baslik, metin, hedef_tur, hedef, yayin, bitis)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            yazar_id,
            baslik.strip(),
            metin.strip(),
            hedef_tur,
            hedef,
            zaman.simdi_str(),
            bitis or None,
        ),
    )
    conn.commit()
    return cur.lastrowid


def gorunur_duyurular(
    conn: sqlite3.Connection, k: sqlite3.Row, limit: int = 50
) -> list[sqlite3.Row]:
    simdi = zaman.simdi_str()
    temel = (
        "SELECT d.*, u.ad_soyad AS yazar FROM duyuru d JOIN kullanici u ON u.id = d.yazar_id"
        " WHERE d.yayin <= ? AND (d.bitis IS NULL OR d.bitis >= ?)"
    )
    params: list = [simdi, simdi]
    siniflar = yetki.kullanici_siniflari(conn, k)
    if siniflar is not None:
        yer = ",".join("?" * len(siniflar)) or "NULL"
        temel += (
            " AND (d.hedef_tur = 'okul' OR (d.hedef_tur = 'rol' AND d.hedef = ?)"
            f" OR (d.hedef_tur = 'sinif' AND d.hedef IN ({yer})))"
        )
        params += [k["rol"], *siniflar]
    temel += " ORDER BY d.yayin DESC, d.id DESC LIMIT ?"
    params.append(limit)
    return conn.execute(temel, params).fetchall()


def sil(conn: sqlite3.Connection, k: sqlite3.Row, duyuru_id: int) -> bool:
    d = conn.execute("SELECT * FROM duyuru WHERE id = ?", (duyuru_id,)).fetchone()
    if d is None or (k["rol"] != "yonetici" and d["yazar_id"] != k["id"]):
        return False
    conn.execute("DELETE FROM duyuru WHERE id = ?", (duyuru_id,))
    conn.commit()
    return True
