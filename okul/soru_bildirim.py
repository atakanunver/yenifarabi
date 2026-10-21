"""Öğrencinin "bu soruda sorun var" bildirimi.

Soru havuzu (Postgres) okuldan salt-okunur olduğu için bildirimler okul.db'dedir. ESIK farklı öğrenci bildirince
soru okul içinde gizlenir (gizli_idler → kaynaklar'a `yasak`); havuzdaki asıl karantina soruhavuzu'nun
gece turunda /api/soru-bildirim'den okunarak yapılır."""

import re
import sqlite3

import zaman

TURLER = {
    "cevap": "Cevap yanlış",
    "sekil": "Şekil / grafik yok",
    "alakasiz": "Alakasız",
    "sacma": "Saçma / hatalı yazılmış",
    "anlasilmiyor": "Soru anlaşılmıyor",
}
ROLLER = ("ogrenci", "ogretmen", "yonetici", "tahta")
# Gizleme için ağırlıklı toplam ESIK'e ulaşınca soru gizlenir: 2 öğrenci, ya da 1 öğretmen/yönetici.
AGIRLIK = {"ogrenci": 1, "ogretmen": 2, "yonetici": 2, "tahta": 1}
ESIK = 2
GUNLUK_LIMIT = 20  # öğrenci
PERSONEL_LIMIT = 30  # öğretmen/yönetici
TAHTA_LIMIT = 30  # şube başına günde
SUBE_DESEN = re.compile(r"^\d{1,2}-[A-ZÇĞİÖŞÜ]$")


class BildirimHatasi(ValueError):
    pass


def gordu_mu(conn: sqlite3.Connection, kullanici_id: int, soru_id: int) -> bool:
    """Öğrenci bu soruyu gerçekten sunulmuş mu (Maraton ya da Günlük Görev)? Rastgele id bildirimini engeller."""
    return (
        conn.execute(
            "SELECT 1 FROM maraton_soru s JOIN maraton m ON m.id = s.maraton_id"
            " WHERE m.kullanici_id = ? AND s.soru_id = ? LIMIT 1",
            (kullanici_id, soru_id),
        ).fetchone()
        is not None
        or conn.execute(
            "SELECT 1 FROM bilgi_cevap c JOIN bilgi_tur t ON t.id = c.tur_id"
            " WHERE t.kullanici_id = ? AND c.soru_id = ? LIMIT 1",
            (kullanici_id, soru_id),
        ).fetchone()
        is not None
        or conn.execute(
            "SELECT 1 FROM calisma_soru WHERE kullanici_id = ? AND soru_id = ? LIMIT 1", (kullanici_id, soru_id)
        ).fetchone()
        is not None
    )


def _havuzda_var(soru_id: int) -> bool:
    from kaynaklar import KaynakHatasi
    from kaynaklar import soru as havuz

    try:
        return soru_id in havuz.getir([soru_id])
    except KaynakHatasi as e:
        raise BildirimHatasi("Soru havuzuna şu an ulaşılamıyor.") from e


def bildir(
    conn: sqlite3.Connection, kullanici_id: int, soru_id: int, tur: str, rol: str = "ogrenci", kaynak: str = ""
) -> bool:
    """True = yeni kayıt, False = bu soru zaten bildirilmiş. Öğrenci yalnızca kendine sunulan soruyu bildirir;
    öğretmen/yönetici havuzdaki her soruyu bildirebilir (günlük limit ayrı)."""
    if tur not in TURLER:
        raise BildirimHatasi("Geçersiz bildirim türü.")
    if rol not in ("ogrenci", "ogretmen", "yonetici"):
        raise BildirimHatasi("Geçersiz rol.")
    if rol == "ogrenci":
        if not gordu_mu(conn, kullanici_id, soru_id):
            raise BildirimHatasi("Bu soru sana gösterilmemiş.")
    elif not _havuzda_var(soru_id):
        raise BildirimHatasi("Soru bulunamadı.")
    bugun = zaman.simdi_str()[:10]
    limit = GUNLUK_LIMIT if rol == "ogrenci" else PERSONEL_LIMIT
    if (
        conn.execute(
            "SELECT count(*) FROM soru_bildirim WHERE kullanici_id = ? AND substr(zaman, 1, 10) = ?",
            (kullanici_id, bugun),
        ).fetchone()[0]
        >= limit
    ):
        raise BildirimHatasi("Bugünkü bildirim sınırına ulaştın.")
    cur = conn.execute(
        "INSERT OR IGNORE INTO soru_bildirim (soru_id, kullanici_id, tur, zaman, rol, kaynak) VALUES (?, ?, ?, ?, ?, ?)",
        (soru_id, kullanici_id, tur, zaman.simdi_str(), rol, kaynak),
    )
    conn.commit()
    return cur.rowcount == 1


def bildir_tahta(conn: sqlite3.Connection, soru_id: int, tur: str, sube: str) -> bool:
    """Tahta Sınıf Arenası: kimliksiz, şube düzeyinde (aynı şube aynı soruyu günde 1 kez). Ağırlık 1."""
    if tur not in TURLER:
        raise BildirimHatasi("Geçersiz bildirim türü.")
    sube = (sube or "").strip().upper()
    if not SUBE_DESEN.match(sube):
        raise BildirimHatasi("Geçersiz şube.")
    if not _havuzda_var(soru_id):
        raise BildirimHatasi("Soru bulunamadı.")
    bugun = zaman.simdi_str()[:10]
    if (
        conn.execute(
            "SELECT count(*) FROM soru_bildirim WHERE kullanici_id IS NULL AND sube = ? AND substr(zaman, 1, 10) = ?",
            (sube, bugun),
        ).fetchone()[0]
        >= TAHTA_LIMIT
    ):
        raise BildirimHatasi("Bugünkü bildirim sınırına ulaşıldı.")
    cur = conn.execute(
        "INSERT OR IGNORE INTO soru_bildirim (soru_id, kullanici_id, tur, zaman, rol, kaynak, sube)"
        " VALUES (?, NULL, ?, ?, 'tahta', 'tahta', ?)",
        (soru_id, tur, zaman.simdi_str(), sube),
    )
    conn.commit()
    return cur.rowcount == 1


def iptal_et(conn: sqlite3.Connection, soru_id: int) -> int:
    """Yönetici: "sorun yok" — bu sorunun mevcut bildirimleri sayılmaz (soru yeniden açılır). Dönen: iptal edilen sayı."""
    cur = conn.execute("UPDATE soru_bildirim SET iptal = 1 WHERE soru_id = ? AND iptal = 0", (soru_id,))
    conn.commit()
    return cur.rowcount


def bildirdi_mi(conn: sqlite3.Connection, kullanici_id: int, soru_id: int) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM soru_bildirim WHERE kullanici_id = ? AND soru_id = ?", (kullanici_id, soru_id)
        ).fetchone()
        is not None
    )


_AGIRLIK_SQL = (
    "CASE rol WHEN 'ogretmen' THEN 2 WHEN 'yonetici' THEN 2 ELSE 1 END"
)  # AGIRLIK sözlüğüyle aynı tutulmalı


def iptal_idleri(conn: sqlite3.Connection) -> list[int]:
    """Yönetici "sorun yok" dedi: iptal edilmiş ve etkin bildirimi kalmamış sorular (soruhavuzu askıdan geri açar)."""
    return [
        r[0]
        for r in conn.execute(
            "SELECT soru_id FROM soru_bildirim GROUP BY soru_id HAVING max(iptal) = 1 AND min(iptal) = 1"
        )
    ]


def gizli_idler(conn: sqlite3.Connection) -> list[int]:
    """Ağırlıklı toplamı ESIK'e ulaşan sorular (okulda gösterilmez); yönetici iptali sayılmaz."""
    return [
        r[0]
        for r in conn.execute(
            f"SELECT soru_id FROM soru_bildirim WHERE iptal = 0 GROUP BY soru_id HAVING sum({_AGIRLIK_SQL}) >= ?",
            (ESIK,),
        )
    ]


def ozet(conn: sqlite3.Connection) -> list[dict]:
    """Soru başına: {soru_id, kisi, agirlik, roller{rol: sayı}, turler{tur: sayı}, son} — en çok bildirilen önce."""
    sonuc: dict[int, dict] = {}
    for r in conn.execute(
        "SELECT soru_id, tur, rol, count(*) AS n, max(zaman) AS son FROM soru_bildirim WHERE iptal = 0"
        " GROUP BY soru_id, tur, rol"
    ):
        d = sonuc.setdefault(
            r["soru_id"], {"soru_id": r["soru_id"], "kisi": 0, "agirlik": 0, "roller": {}, "turler": {}, "son": ""}
        )
        d["turler"][r["tur"]] = d["turler"].get(r["tur"], 0) + r["n"]
        d["roller"][r["rol"]] = d["roller"].get(r["rol"], 0) + r["n"]
        d["kisi"] += r["n"]
        d["agirlik"] += r["n"] * AGIRLIK[r["rol"]]
        d["son"] = max(d["son"], r["son"])
    return sorted(sonuc.values(), key=lambda d: (-d["agirlik"], -d["kisi"], d["son"]))
