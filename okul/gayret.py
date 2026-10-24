"""Gayret (süreç) XP'si (2026-10-24): öğrenci bir soruya gerçekten zaman ayırdıkça XP kazanır — doğru/yanlış fark etmez.

Soru başına sayılan süre: ALT_SN'den az ise 0 (rastgele dokunuş), UST_SN'de kırpılır (sayfayı açık bırakıp beklemek
kazandırmasın); her SN_BASINA_XP sn = 1 XP (kesirler atılır). Günde en çok GUNLUK_EN_COK XP. Yalnızca gerçekten cevap
verilen sorular (süre dolumu/pas/hatalı bildirim sayılmaz). Defter: bilgi_xp kaynak 'gayret', ref soru başına tekil (çift
gönderim iki kez yazmaz). Geçerli: 9-11. sınıf (Arena XP'siyle aynı). Maraton, Günlük Görev ve Çalışma'dan çağrılır; commit etmez.
"""

import sqlite3
from datetime import datetime

import zaman

ALT_SN = 5
UST_SN = 60
SN_BASINA_XP = 10
GUNLUK_EN_COK = 60
MIN_DUZEY, MAX_DUZEY = 9, 11


def gecen(bas: str | None, son: str) -> float:
    """İki zaman damgası (zaman.BICIM) arası saniye; başlangıç yoksa 0."""
    if not bas:
        return 0.0
    return max(0.0, (datetime.strptime(son, zaman.BICIM) - datetime.strptime(bas, zaman.BICIM)).total_seconds())  # noqa: DTZ007


def xp_hesapla(saniye: float) -> int:
    """Tek soru için XP: ALT_SN altı 0; UST_SN'ye kırpılır; SN_BASINA_XP sn = 1 XP."""
    if saniye < ALT_SN:
        return 0
    return int(min(saniye, UST_SN) // SN_BASINA_XP)


def _duzey_uygun(conn: sqlite3.Connection, kid: int) -> bool:
    r = conn.execute("SELECT sinif FROM ogrenci WHERE kullanici_id = ?", (kid,)).fetchone()
    try:
        return MIN_DUZEY <= int(r["sinif"].split("-")[0]) <= MAX_DUZEY
    except (TypeError, ValueError, AttributeError):
        return False


def yazilan(conn: sqlite3.Connection, kid: int, ref: str) -> int:
    """Bu soru için daha önce yazılmış gayret XP'si (yoksa 0): ekranda gösterim için."""
    r = conn.execute("SELECT miktar FROM bilgi_xp WHERE kullanici_id = ? AND kaynak = 'gayret' AND ref = ?", (kid, ref)).fetchone()
    return r[0] if r else 0


def ver(conn: sqlite3.Connection, kid: int, ref: str, saniye: float) -> int:
    """Bu soru için gayret XP'si yazar (commit etmez); yazılan miktarı döner (günlük sınır/çift gönderim/uygunsuz sınıf -> 0)."""
    xp = xp_hesapla(saniye)
    if xp <= 0 or not _duzey_uygun(conn, kid):
        return 0
    gun = zaman.simdi().strftime("%Y-%m-%d")
    bugunku = conn.execute(
        "SELECT COALESCE(SUM(miktar), 0) FROM bilgi_xp WHERE kullanici_id = ? AND kaynak = 'gayret' AND gun = ?", (kid, gun)
    ).fetchone()[0]
    miktar = min(xp, GUNLUK_EN_COK - bugunku)
    if miktar <= 0:
        return 0
    yazildi = conn.execute(
        "INSERT OR IGNORE INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (?, 'gayret', ?, ?, ?, ?)",
        (kid, ref, miktar, gun, zaman.simdi_str()),
    ).rowcount
    return miktar if yazildi == 1 else 0
