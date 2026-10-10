"""Öğrenci/veli/öğretmen sayfalarının paylaştığı veri toplama yardımcıları.

Dış kaynak hatası sayfayı düşürmez: ilgili alan None döner, şablon 'şu an alınamıyor' yazar.
"""

import sqlite3
from datetime import timedelta

import odevler
import sinavlar
import zaman
from ayarlar import AYAR
from kaynaklar import KaynakHatasi, kazanim, program, yoklama


def bugunku_dersler(sinif: str) -> list[tuple[int, str]] | None:
    try:
        return program.bugun(sinif, zaman.simdi().date())
    except KaynakHatasi:
        return None


def haftalik_program(sinif: str):
    try:
        return program.haftalik(sinif)
    except KaynakHatasi:
        return None


def kazanim_ozeti(
    conn: sqlite3.Connection, ogrenci: sqlite3.Row
) -> tuple[dict, list, bool]:
    """(ozet, form sonuçları, form kaynağı erişilebilir mi)."""
    try:
        form = kazanim.form_sonuclari(ogrenci["okul_no"])
        erisildi = True
    except KaynakHatasi:
        form, erisildi = [], False
    o = kazanim.ozet(form, odevler.ogrenci_kazanim_satirlari(conn, ogrenci["id"]))
    return o, form, erisildi


def ders_ozeti(o: dict) -> list[tuple[str, int, int]]:
    return kazanim.ders_ozeti(o, AYAR.kazanim_esik)


def devamsizlik(ogrenci: sqlite3.Row, gun: int | None = None):
    baslangic = (
        (zaman.simdi() - timedelta(days=gun)).strftime("%Y-%m-%d") if gun else None
    )
    try:
        return yoklama.devamsizlik(ogrenci["okul_no"], ogrenci["sinif"], baslangic)
    except KaynakHatasi:
        return None


def devamsizlik_gunlere_gore(kayitlar) -> list[tuple[str, list]]:
    gunler: dict[str, list] = {}
    for d in kayitlar:
        gunler.setdefault(d.tarih, []).append(d)
    return list(gunler.items())


def bekleyen_odevler(
    conn: sqlite3.Connection, ogrenci: sqlite3.Row
) -> list[sqlite3.Row]:
    return [o for o in odevler.ogrenci_odevleri(conn, ogrenci) if o["durum"] is None]


def yaklasan_sinavlar(conn: sqlite3.Connection, sinif: str, gun: int = 14) -> list[sqlite3.Row]:
    bugun = zaman.simdi().date()
    son = (bugun + timedelta(days=gun)).strftime("%Y-%m-%d")
    return [s for s in sinavlar.sinif_sinavlari(conn, sinif, bugun.strftime("%Y-%m-%d")) if s["tarih"] <= son]
