"""Dilek/istek/şikayet kutusu: öğrenci ve öğretmen yöneticiye yazar.

Gönderen yöneticiye ADLI görünür (formda uyarılır). Yönetici yalnızca durum işaretler (yeni/okundu/çözüldü), yazışma yok.
Veli kapsam dışı. Metin yalnızca düz metin olarak gösterilir (şablonda otomatik kaçış).
"""

import sqlite3
from datetime import timedelta

import sohbet
import yetki
import zaman

ROLLER = ("ogrenci", "ogretmen")
TURLER = {"dilek": "Dilek", "istek": "İstek", "sikayet": "Şikayet"}
DURUMLAR = {"yeni": "Yeni", "okundu": "Okundu", "cozuldu": "Çözüldü"}
AZAMI_METIN = 1000
SAAT_AZAMI = 5  # kullanıcı başına saatte en çok kayıt


class KutuHatasi(Exception):
    def __init__(self, mesaj: str, kod: int = 400):
        super().__init__(mesaj)
        self.mesaj = mesaj
        self.kod = kod


def ekle(conn: sqlite3.Connection, kullanici_id: int, tur: str, metin: str) -> int:
    if tur not in TURLER:
        raise KutuHatasi("Geçersiz tür.")
    m = sohbet.metin_duzenle(metin)
    if not m:
        raise KutuHatasi("Metin boş olamaz.")
    if len(m) > AZAMI_METIN:
        raise KutuHatasi(f"Metin en çok {AZAMI_METIN} karakter olabilir.")
    saat_once = (zaman.simdi() - timedelta(hours=1)).strftime(zaman.BICIM)
    son = conn.execute(
        "SELECT COUNT(*) FROM kutu_kayit WHERE kullanici_id = ? AND olusturma >= ?", (kullanici_id, saat_once)
    ).fetchone()[0]
    if son >= SAAT_AZAMI:
        raise KutuHatasi("Bir saatte en çok 5 kayıt gönderebilirsin; biraz sonra tekrar dene.", 429)
    cur = conn.execute(
        "INSERT INTO kutu_kayit (kullanici_id, tur, metin, olusturma) VALUES (?, ?, ?, ?)",
        (kullanici_id, tur, m, zaman.simdi_str()),
    )
    conn.commit()
    return cur.lastrowid


def _kayit(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["tur_ad"] = TURLER[d["tur"]]
    d["durum_ad"] = DURUMLAR[d["durum"]]
    d["zaman"] = sohbet.gorunum_zamani(d["olusturma"])
    return d


def benim(conn: sqlite3.Connection, kullanici_id: int, limit: int = 50) -> list[dict]:
    """Yalnızca kullanıcının kendi kayıtları (en yeni önce)."""
    return [
        _kayit(r)
        for r in conn.execute(
            "SELECT * FROM kutu_kayit WHERE kullanici_id = ? ORDER BY id DESC LIMIT ?", (kullanici_id, limit)
        )
    ]


def liste(conn: sqlite3.Connection, durum: str | None = None, tur: str | None = None, limit: int = 200) -> list[dict]:
    """Yönetici listesi: gönderen adı/rolü/sınıfı ile (en yeni önce)."""
    kosul, p = [], []
    if durum in DURUMLAR:
        kosul.append("m.durum = ?")
        p.append(durum)
    if tur in TURLER:
        kosul.append("m.tur = ?")
        p.append(tur)
    where = ("WHERE " + " AND ".join(kosul)) if kosul else ""
    sonuc = []
    for r in conn.execute(
        f"SELECT m.*, u.ad_soyad, u.rol FROM kutu_kayit m JOIN kullanici u ON u.id = m.kullanici_id"
        f" {where} ORDER BY m.id DESC LIMIT ?",
        [*p, limit],
    ):
        d = _kayit(r)
        d["sinif"] = ""
        if r["rol"] == "ogrenci":
            o = yetki.ogrenci_kaydi(conn, r["kullanici_id"])
            d["sinif"] = o["sinif"] if o else ""
        sonuc.append(d)
    return sonuc


def durum_ayarla(conn: sqlite3.Connection, kayit_id: int, durum: str) -> bool:
    if durum not in DURUMLAR:
        return False
    n = conn.execute(
        "UPDATE kutu_kayit SET durum = ?, guncelleme = ? WHERE id = ?", (durum, zaman.simdi_str(), kayit_id)
    ).rowcount
    conn.commit()
    return n > 0


def yeni_sayisi(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM kutu_kayit WHERE durum = 'yeni'").fetchone()[0]
