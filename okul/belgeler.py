"""Vesikalık fotoğraf ve yıllık plan kayıtları (dosyalar.py saklar, burası kim neyi görür/değiştirir)."""

import sqlite3

import dosyalar
import yetki
import zaman

# --- vesikalık fotoğraf ---


def foto_gorebilir(conn: sqlite3.Connection, k: sqlite3.Row, hedef_id: int) -> bool:
    """Öğrenci fotoğrafı: kendisi, velisi, sınıfına giren öğretmen, yönetici.
    Öğretmen/yönetici fotoğrafı: kendisi ve yönetici. Öğrenciler birbirini göremez."""
    if k["id"] == hedef_id or k["rol"] == "yonetici":
        return True
    hedef = conn.execute(
        "SELECT rol FROM kullanici WHERE id = ?", (hedef_id,)
    ).fetchone()
    if hedef is None or hedef["rol"] != "ogrenci":
        return False
    o = yetki.ogrenci_kaydi(conn, hedef_id)
    return (
        o is not None
        and k["rol"] in ("veli", "ogretmen")
        and yetki.ogrenci_gorebilir(conn, k, o["id"])
    )


def foto_degistir(conn: sqlite3.Connection, k: sqlite3.Row, veri: bytes) -> None:
    if k["rol"] == "veli":
        raise dosyalar.DosyaHatasi("Veli hesaplarında fotoğraf bulunmaz.")
    yeni = dosyalar.foto_kaydet(veri)
    eski = conn.execute(
        "SELECT foto FROM kullanici WHERE id = ?", (k["id"],)
    ).fetchone()["foto"]
    conn.execute("UPDATE kullanici SET foto = ? WHERE id = ?", (yeni.depo_adi, k["id"]))
    conn.commit()
    dosyalar.sil("foto", eski)


def foto_sil(conn: sqlite3.Connection, k: sqlite3.Row) -> None:
    eski = conn.execute(
        "SELECT foto FROM kullanici WHERE id = ?", (k["id"],)
    ).fetchone()["foto"]
    conn.execute("UPDATE kullanici SET foto = NULL WHERE id = ?", (k["id"],))
    conn.commit()
    dosyalar.sil("foto", eski)


# --- yıllık plan ---


def plan_yukle(
    conn: sqlite3.Connection,
    k: sqlite3.Row,
    sinif: str,
    ders: str,
    dosya_adi: str,
    veri: bytes,
) -> int:
    if k["rol"] != "ogretmen" or not yetki.sinif_ders_yetkili(conn, k, sinif, ders):
        raise PermissionError
    yeni = dosyalar.plan_kaydet(veri, dosya_adi)
    eski = conn.execute(
        "SELECT * FROM yillik_plan WHERE ogretmen_id = ? AND sinif = ? AND ders = ?",
        (k["id"], sinif, ders),
    ).fetchone()
    temiz_ad = (dosya_adi or "plan").replace("\\", "/").rsplit("/", 1)[-1][:150]
    conn.execute(
        "INSERT INTO yillik_plan (ogretmen_id, sinif, ders, dosya_adi, depo_adi, tur, boyut, yukleme)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (ogretmen_id, sinif, ders) DO UPDATE SET dosya_adi = excluded.dosya_adi,"
        " depo_adi = excluded.depo_adi, tur = excluded.tur, boyut = excluded.boyut, yukleme = excluded.yukleme",
        (
            k["id"],
            sinif,
            ders,
            temiz_ad,
            yeni.depo_adi,
            yeni.tur,
            yeni.boyut,
            zaman.simdi_str(),
        ),
    )
    conn.commit()
    if eski:
        dosyalar.sil("plan", eski["depo_adi"])
    return conn.execute(
        "SELECT id FROM yillik_plan WHERE ogretmen_id = ? AND sinif = ? AND ders = ?",
        (k["id"], sinif, ders),
    ).fetchone()[0]


def plan_getir(
    conn: sqlite3.Connection, k: sqlite3.Row, plan_id: int
) -> sqlite3.Row | None:
    """Yalnızca planın sahibi öğretmen ve yönetici; başkası için None (404)."""
    p = conn.execute("SELECT * FROM yillik_plan WHERE id = ?", (plan_id,)).fetchone()
    if p is None or (k["rol"] != "yonetici" and p["ogretmen_id"] != k["id"]):
        return None
    return p


def plan_sil(conn: sqlite3.Connection, k: sqlite3.Row, plan_id: int) -> bool:
    p = plan_getir(conn, k, plan_id)
    if p is None:
        return False
    conn.execute("DELETE FROM yillik_plan WHERE id = ?", (plan_id,))
    conn.commit()
    dosyalar.sil("plan", p["depo_adi"])
    return True


def ogretmen_planlari(conn: sqlite3.Connection, ogretmen_id: int) -> list[dict]:
    """Görev başına bir satır: plan yüklüyse bilgisiyle, değilse plan=None."""
    planlar = {
        (p["sinif"], p["ders"]): p
        for p in conn.execute(
            "SELECT * FROM yillik_plan WHERE ogretmen_id = ?", (ogretmen_id,)
        )
    }
    return [
        {"sinif": s, "ders": d, "plan": planlar.get((s, d))}
        for s, d in yetki.ogretmen_gorevleri(conn, ogretmen_id)
    ]


def tum_planlar(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Yönetici: her görev için plan durumu (eksikler dahil)."""
    return conn.execute(
        "SELECT g.sinif, g.ders, u.id AS ogretmen_id, u.ad_soyad, p.id AS plan_id, p.dosya_adi, p.tur, p.boyut, p.yukleme"
        " FROM ogretmen_gorev g JOIN kullanici u ON u.id = g.ogretmen_id"
        " LEFT JOIN yillik_plan p ON p.ogretmen_id = g.ogretmen_id AND p.sinif = g.sinif AND p.ders = g.ders"
        " WHERE u.aktif = 1 ORDER BY (p.id IS NOT NULL), u.ad_soyad, g.sinif, g.ders"
    ).fetchall()
