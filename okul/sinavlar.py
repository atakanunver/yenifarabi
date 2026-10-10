"""Sınav takvimi: yazılılar (görevli öğretmen, kendi sınıf-dersi) ve genel deneme sınavları (düzey bazlı)."""

import sqlite3
from datetime import date, datetime

import yetki
import zaman
from metin import sinif_seviyesi, tr_kucuk

DUZEYLER = (9, 10, 11, 12)


class SinavHatasi(ValueError):
    pass


class YetkiYok(SinavHatasi):
    pass


def _tarih(s: str) -> str:
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise SinavHatasi("Sınav tarihini seçin.") from None


def _ders_no(s) -> int | None:
    if s in (None, ""):
        return None
    try:
        n = int(s)
    except (TypeError, ValueError):
        raise SinavHatasi("Ders saati 1-10 arasında olmalı.") from None
    if not 1 <= n <= 10:
        raise SinavHatasi("Ders saati 1-10 arasında olmalı.")
    return n


def _duzeyler(liste) -> str:
    try:
        secili = sorted({int(x) for x in liste if str(x).strip()})
    except ValueError:
        raise SinavHatasi("Geçersiz sınıf düzeyi.") from None
    if any(d not in DUZEYLER for d in secili):
        raise SinavHatasi("Geçersiz sınıf düzeyi.")
    return ",".join(map(str, secili))  # boş = tüm okul


def yazili_ekle(
    conn, k, sinif, ders, tarih, ders_no=None, aciklama="", baslik=""
) -> int:
    ders = tr_kucuk((ders or "").strip())
    if not sinif or not ders or not yetki.sinif_ders_yetkili(conn, k, sinif, ders):
        raise YetkiYok("Bu sınıf ve derse sınav giremezsiniz.")
    baslik = (baslik or "").strip() or f"{ders[:1].upper()}{ders[1:]} yazılısı"
    cur = conn.execute(
        "INSERT INTO sinav (yazar_id, tur, baslik, sinif, ders, tarih, ders_no, aciklama, olusturma)"
        " VALUES (?, 'yazili', ?, ?, ?, ?, ?, ?, ?)",
        (
            k["id"],
            baslik[:120],
            sinif,
            ders,
            _tarih(tarih),
            _ders_no(ders_no),
            (aciklama or "").strip()[:1000],
            zaman.simdi_str(),
        ),
    )
    conn.commit()
    return cur.lastrowid


def deneme_ekle(conn, k, baslik, tarih, duzeyler, aciklama="") -> int:
    if k["rol"] not in ("ogretmen", "yonetici"):
        raise YetkiYok("Deneme sınavı giremezsiniz.")
    baslik = (baslik or "").strip()
    if not baslik:
        raise SinavHatasi("Deneme sınavının adını yazın (ör. 1. TYT Denemesi).")
    cur = conn.execute(
        "INSERT INTO sinav (yazar_id, tur, baslik, duzeyler, tarih, aciklama, olusturma)"
        " VALUES (?, 'deneme', ?, ?, ?, ?, ?)",
        (
            k["id"],
            baslik[:120],
            _duzeyler(duzeyler),
            _tarih(tarih),
            (aciklama or "").strip()[:1000],
            zaman.simdi_str(),
        ),
    )
    conn.commit()
    return cur.lastrowid


def getir(conn, sinav_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM sinav WHERE id = ?", (sinav_id,)).fetchone()


def duzenleyebilir(k, s) -> bool:
    return s is not None and (
        k["rol"] == "yonetici" or (k["rol"] == "ogretmen" and s["yazar_id"] == k["id"])
    )


def guncelle(
    conn, k, sinav_id: int, tarih, ders_no=None, aciklama="", baslik="", duzeyler=None
) -> None:
    s = getir(conn, sinav_id)
    if not duzenleyebilir(k, s):
        raise YetkiYok("Bu sınavı düzenleyemezsiniz.")
    if s["tur"] == "deneme":
        if not (baslik or "").strip():
            raise SinavHatasi("Deneme sınavının adını yazın.")
        conn.execute(
            "UPDATE sinav SET baslik = ?, tarih = ?, duzeyler = ?, aciklama = ? WHERE id = ?",
            (
                baslik.strip()[:120],
                _tarih(tarih),
                _duzeyler(duzeyler or []),
                (aciklama or "").strip()[:1000],
                sinav_id,
            ),
        )
    else:
        conn.execute(
            "UPDATE sinav SET baslik = ?, tarih = ?, ders_no = ?, aciklama = ? WHERE id = ?",
            (
                (baslik or "").strip()[:120] or s["baslik"],
                _tarih(tarih),
                _ders_no(ders_no),
                (aciklama or "").strip()[:1000],
                sinav_id,
            ),
        )
    conn.commit()


def sil(conn, k, sinav_id: int) -> bool:
    if not duzenleyebilir(k, getir(conn, sinav_id)):
        return False
    conn.execute("DELETE FROM sinav WHERE id = ?", (sinav_id,))
    conn.commit()
    return True


def deneme_duzeyi_kapsar(s, seviye: int) -> bool:
    return not s["duzeyler"] or str(seviye) in s["duzeyler"].split(",")


def sinif_sinavlari(
    conn, sinif: str, baslangic: str | None = None
) -> list[sqlite3.Row]:
    """Bir sınıfın öğrencisinin göreceği sınavlar: o sınıfın yazılıları + düzeyini kapsayan denemeler."""
    sql = "SELECT s.*, u.ad_soyad AS yazar FROM sinav s JOIN kullanici u ON u.id = s.yazar_id"
    params: list = []
    if baslangic:
        sql += " WHERE s.tarih >= ?"
        params.append(baslangic)
    seviye = sinif_seviyesi(sinif)
    return [
        s
        for s in conn.execute(
            sql + " ORDER BY s.tarih, s.ders_no IS NULL, s.ders_no", params
        )
        if (s["tur"] == "yazili" and s["sinif"] == sinif)
        or (s["tur"] == "deneme" and deneme_duzeyi_kapsar(s, seviye))
    ]


def ogretmen_sinavlari(conn, k, baslangic: str) -> list[sqlite3.Row]:
    """Öğretmen: kendi girdikleri + görevli sınıflarının yazılıları + tüm denemeler. Yönetici: hepsi."""
    satirlar = conn.execute(
        "SELECT s.*, u.ad_soyad AS yazar FROM sinav s JOIN kullanici u ON u.id = s.yazar_id"
        " WHERE s.tarih >= ? ORDER BY s.tarih, s.ders_no IS NULL, s.ders_no",
        (baslangic,),
    ).fetchall()
    if k["rol"] == "yonetici":
        return satirlar
    siniflar = set(yetki.ogretmen_siniflari(conn, k["id"]))
    return [
        s
        for s in satirlar
        if s["yazar_id"] == k["id"] or s["tur"] == "deneme" or s["sinif"] in siniflar
    ]


def kalan_gun(tarih: str) -> int:
    return (date.fromisoformat(tarih) - zaman.simdi().date()).days
