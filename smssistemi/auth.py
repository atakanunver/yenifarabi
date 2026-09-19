"""Tek ortak şifreyle giriş — dashboard'un auth.py deseninin bağımsız
kopyası (bkz. docs/superpowers/specs/2026-09-19-smssistemi-design.md
"Güvenlik" bölümü — kod paylaşımı kasıtlı olarak yok)."""

import hashlib
import hmac
import json
import secrets
from pathlib import Path

from fastapi import HTTPException

GIZLI_YOLU = Path(__file__).resolve().parent / "config" / "gizli.json"
COOKIE_ADI = "smssistemi_oturum"


def sifre_hashle(sifre: str, tuz: bytes | None = None) -> str:
    tuz = tuz or secrets.token_bytes(16)
    dk = hashlib.scrypt(sifre.encode("utf-8"), salt=tuz, n=2**14, r=8, p=1)
    return f"{tuz.hex()}${dk.hex()}"


def sifre_dogrula(sifre: str, hash_str: str) -> bool:
    try:
        tuz_hex, dk_hex = hash_str.split("$", 1)
    except ValueError:
        return False
    tuz = bytes.fromhex(tuz_hex)
    beklenen = hashlib.scrypt(sifre.encode("utf-8"), salt=tuz, n=2**14, r=8, p=1)
    return hmac.compare_digest(beklenen, bytes.fromhex(dk_hex))


def _gizli_yukle() -> dict:
    if not GIZLI_YOLU.exists():
        raise HTTPException(
            500,
            "config/gizli.json yok — önce 'venv/bin/python scripts/sifre_belirle.py' çalıştırın.",
        )
    return json.loads(GIZLI_YOLU.read_text(encoding="utf-8"))


def giris_dene(sifre: str) -> bool:
    gizli = _gizli_yukle()
    return sifre_dogrula(sifre, gizli["sifre_hash"])


def oturum_olustur(conn) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO oturumlar (token) VALUES (?)", (token,))
    conn.commit()
    return token


def oturum_sil(conn, token: str) -> None:
    conn.execute("DELETE FROM oturumlar WHERE token = ?", (token,))
    conn.commit()


def oturum_gecerli_mi(conn, token: str | None) -> bool:
    if not token:
        return False
    satir = conn.execute("SELECT token FROM oturumlar WHERE token = ?", (token,)).fetchone()
    if satir is None:
        return False
    conn.execute("UPDATE oturumlar SET son_gorulme = datetime('now') WHERE token = ?", (token,))
    conn.commit()
    return True
