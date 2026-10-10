"""Şifre (scrypt), oturum, CSRF, deneme sınırlama ve veli SMS kodu."""

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta

import zaman

COOKIE_ADI = "okul_oturum"
OTURUM_OMRU = timedelta(days=365)
SON_GORULME_ARALIGI = timedelta(days=1)

DENEME_ESIK = 5
DENEME_PENCERE = timedelta(minutes=15)
DENEME_BEKLEME = timedelta(seconds=60)

KOD_OMRU = timedelta(minutes=5)
KOD_AZAMI_DENEME = 5


def sifre_hashle(sifre: str, tuz: bytes | None = None) -> str:
    tuz = tuz or secrets.token_bytes(16)
    dk = hashlib.scrypt(sifre.encode("utf-8"), salt=tuz, n=2**14, r=8, p=1)
    return f"{tuz.hex()}${dk.hex()}"


def sifre_dogrula(sifre: str, hash_str: str | None) -> bool:
    if not hash_str:
        return False
    try:
        tuz_hex, dk_hex = hash_str.split("$", 1)
    except ValueError:
        return False
    beklenen = hashlib.scrypt(
        sifre.encode("utf-8"), salt=bytes.fromhex(tuz_hex), n=2**14, r=8, p=1
    )
    return hmac.compare_digest(beklenen, bytes.fromhex(dk_hex))


def _ozet(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _zaman(s: str) -> datetime:
    return datetime.strptime(s, zaman.BICIM)


# --- oturum ---


def oturum_ac(
    conn: sqlite3.Connection, kullanici_id: int, cihaz: str | None = None
) -> str:
    token = secrets.token_urlsafe(32)
    simdi = zaman.simdi_str()
    conn.execute(
        "INSERT INTO oturum (token_hash, kullanici_id, olusturma, son_gorulme, cihaz)"
        " VALUES (?, ?, ?, ?, ?)",
        (_ozet(token), kullanici_id, simdi, simdi, (cihaz or "")[:200]),
    )
    conn.commit()
    return token


def oturum_kullanici(conn: sqlite3.Connection, token: str | None) -> sqlite3.Row | None:
    if not token:
        return None
    satir = conn.execute(
        "SELECT k.*, o.son_gorulme AS oturum_son FROM oturum o"
        " JOIN kullanici k ON k.id = o.kullanici_id"
        " WHERE o.token_hash = ? AND k.aktif = 1",
        (_ozet(token),),
    ).fetchone()
    if satir and zaman.simdi() - _zaman(satir["oturum_son"]) > SON_GORULME_ARALIGI:
        conn.execute(
            "UPDATE oturum SET son_gorulme = ? WHERE token_hash = ?",
            (zaman.simdi_str(), _ozet(token)),
        )
        conn.commit()
    return satir


def oturum_kapat(conn: sqlite3.Connection, token: str | None) -> None:
    if token:
        conn.execute("DELETE FROM oturum WHERE token_hash = ?", (_ozet(token),))
        conn.commit()


def diger_oturumlari_kapat(
    conn: sqlite3.Connection, kullanici_id: int, haric: str | None
) -> None:
    conn.execute(
        "DELETE FROM oturum WHERE kullanici_id = ? AND token_hash != ?",
        (kullanici_id, _ozet(haric or "")),
    )
    conn.commit()


def cerez_yaz(response, token: str, guvenli: bool) -> None:
    response.set_cookie(
        COOKIE_ADI,
        token,
        max_age=int(OTURUM_OMRU.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=guvenli,
        path="/",
    )


def csrf_token(token: str) -> str:
    return _ozet(f"csrf:{token}")[:32]


# --- deneme sınırlama ---


def engelli_mi(conn: sqlite3.Connection, anahtar: str) -> bool:
    r = conn.execute(
        "SELECT * FROM giris_deneme WHERE anahtar = ?", (anahtar,)
    ).fetchone()
    if r is None or r["sayac"] < DENEME_ESIK:
        return False
    return zaman.simdi() - _zaman(r["son_hata"]) < DENEME_BEKLEME


def hata_kaydet(conn: sqlite3.Connection, anahtar: str) -> None:
    r = conn.execute(
        "SELECT * FROM giris_deneme WHERE anahtar = ?", (anahtar,)
    ).fetchone()
    if r is None or zaman.simdi() - _zaman(r["son_hata"]) > DENEME_PENCERE:
        sayac = 1
    else:
        sayac = r["sayac"] + 1
    conn.execute(
        "INSERT INTO giris_deneme (anahtar, sayac, son_hata) VALUES (?, ?, ?)"
        " ON CONFLICT(anahtar) DO UPDATE SET sayac = excluded.sayac, son_hata = excluded.son_hata",
        (anahtar, sayac, zaman.simdi_str()),
    )
    conn.commit()


def hatalari_temizle(conn: sqlite3.Connection, anahtar: str) -> None:
    conn.execute("DELETE FROM giris_deneme WHERE anahtar = ?", (anahtar,))
    conn.commit()


# --- veli SMS kodu ---


def kod_uret(conn: sqlite3.Connection, telefon: str) -> str:
    kod = f"{secrets.randbelow(10**6):06d}"
    son = (zaman.simdi() + KOD_OMRU).strftime(zaman.BICIM)
    conn.execute(
        "INSERT INTO sms_kod (telefon, kod_hash, son_gecerlilik, deneme) VALUES (?, ?, ?, 0)"
        " ON CONFLICT(telefon) DO UPDATE SET kod_hash = excluded.kod_hash,"
        " son_gecerlilik = excluded.son_gecerlilik, deneme = 0",
        (telefon, _ozet(f"{telefon}:{kod}"), son),
    )
    conn.commit()
    return kod


def kod_dogrula(conn: sqlite3.Connection, telefon: str, kod: str) -> bool:
    r = conn.execute("SELECT * FROM sms_kod WHERE telefon = ?", (telefon,)).fetchone()
    if r is None:
        return False
    if r["deneme"] >= KOD_AZAMI_DENEME or zaman.simdi() > _zaman(r["son_gecerlilik"]):
        return False
    if hmac.compare_digest(r["kod_hash"], _ozet(f"{telefon}:{kod.strip()}")):
        conn.execute("DELETE FROM sms_kod WHERE telefon = ?", (telefon,))
        conn.commit()
        return True
    conn.execute("UPDATE sms_kod SET deneme = deneme + 1 WHERE telefon = ?", (telefon,))
    conn.commit()
    return False
