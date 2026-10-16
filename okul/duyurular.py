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
    conn.execute("DELETE FROM duyuru WHERE id = ?", (duyuru_id,))  # duyuru_okuma CASCADE
    conn.commit()
    return True


def okuma_kaydet(conn: sqlite3.Connection, k: sqlite3.Row, liste: list[sqlite3.Row]) -> None:
    """Kullanıcının /duyurular sayfasında gördüğü duyuruları bir kez 'okundu' işaretler."""
    if not liste:
        return
    simdi = zaman.simdi_str()
    conn.executemany(
        "INSERT OR IGNORE INTO duyuru_okuma (duyuru_id, kullanici_id, zaman) VALUES (?, ?, ?)",
        [(d["id"], k["id"], simdi) for d in liste],
    )
    conn.commit()


def _kitle(conn: sqlite3.Connection) -> dict[int, dict]:
    """Aktif öğrenci/veli/öğretmenler: {id: {rol, ad, siniflar}} (sınıfı olmayanın kümesi boş)."""
    kitle: dict[int, dict] = {}
    sorgu = (
        "SELECT u.id, u.rol, u.ad_soyad, s.sinif FROM kullanici u LEFT JOIN ("
        " SELECT kullanici_id AS kid, sinif FROM ogrenci WHERE kullanici_id IS NOT NULL"
        " UNION SELECT vo.veli_id, o.sinif FROM veli_ogrenci vo JOIN ogrenci o ON o.id = vo.ogrenci_id"
        " UNION SELECT ogretmen_id, sinif FROM ogretmen_gorev"
        ") s ON s.kid = u.id WHERE u.aktif = 1 AND u.rol IN ('ogrenci','veli','ogretmen')"
    )
    for r in conn.execute(sorgu):
        g = kitle.setdefault(r["id"], {"rol": r["rol"], "ad": r["ad_soyad"], "siniflar": set()})
        if r["sinif"]:
            g["siniflar"].add(r["sinif"])
    return kitle


def _hedefte_mi(d: sqlite3.Row, u: dict) -> bool:
    if d["hedef_tur"] == "okul":
        return True
    if d["hedef_tur"] == "rol":
        return u["rol"] == d["hedef"]
    return d["hedef"] in u["siniflar"]


def okuma_raporu(conn: sqlite3.Connection, d: sqlite3.Row) -> dict:
    """Duyurunun hedef kitlesi için okuma özeti: rol, sınıf×rol ve okumayanların listesi.

    Veli/öğretmen birden çok sınıfta olabilir: sınıf tablosunda her sınıfta sayılır, rol toplamında bir kez.
    """
    okuyan = {
        r[0] for r in conn.execute("SELECT kullanici_id FROM duyuru_okuma WHERE duyuru_id = ?", (d["id"],))
    }
    roller = {r: [0, 0] for r in ("ogrenci", "veli", "ogretmen")}
    siniflar: dict[str, dict[str, list[int]]] = {}
    okumayan = []
    for kid, u in _kitle(conn).items():
        if not _hedefte_mi(d, u):
            continue
        okudu = kid in okuyan
        roller[u["rol"]][1] += 1
        roller[u["rol"]][0] += okudu
        yerler = [d["hedef"]] if d["hedef_tur"] == "sinif" else sorted(u["siniflar"])
        for s in yerler:
            c = siniflar.setdefault(s, {r: [0, 0] for r in roller})[u["rol"]]
            c[1] += 1
            c[0] += okudu
        if not okudu:
            okumayan.append({"id": kid, "rol": u["rol"], "ad": u["ad"], "siniflar": sorted(u["siniflar"])})
    okumayan.sort(key=lambda x: (x["rol"], x["ad"]))
    return {"roller": roller, "siniflar": dict(sorted(siniflar.items())), "okumayan": okumayan}
