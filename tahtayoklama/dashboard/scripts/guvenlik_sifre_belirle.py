"""Güvenlik ekranının (/guvenlik) şifresini belirler → config/guvenlik.json.

Her çalıştırmada çerez imza anahtarı da yenilenir: şifre değişince açık kalan
eski güvenlik oturumları düşer. "telefonlar" listesi (ekranın altındaki
numaralar, ör. [{"ad": "Müdür", "no": "05xx..."}]) korunur.

Kullanım: dashboard/ dizininden `venv/bin/python scripts/guvenlik_sifre_belirle.py`
(TTY yoksa şifre stdin'den iki satır olarak okunur.)
"""

import getpass
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth import sifre_hashle  # noqa: E402

YOL = Path(__file__).resolve().parent.parent / "config" / "guvenlik.json"


def _oku(soru: str) -> str:
    if sys.stdin.isatty():
        return getpass.getpass(soru)
    return sys.stdin.readline().rstrip("\n")


def main() -> None:
    sifre = _oku("Yeni güvenlik şifresi: ")
    tekrar = _oku("Tekrar: ")
    if sifre != tekrar:
        print("Şifreler eşleşmiyor.", file=sys.stderr)
        sys.exit(1)
    if len(sifre) < 6:
        print("Şifre en az 6 karakter olmalı.", file=sys.stderr)
        sys.exit(1)

    eski = json.loads(YOL.read_text(encoding="utf-8")) if YOL.exists() else {}
    yeni = {
        "sifre_hash": sifre_hashle(sifre),
        "anahtar": secrets.token_hex(32),
        "telefonlar": eski.get("telefonlar", [{"ad": "Acil", "no": "112"}]),
    }
    YOL.parent.mkdir(parents=True, exist_ok=True)
    YOL.write_text(json.dumps(yeni, ensure_ascii=False, indent=2), encoding="utf-8")
    YOL.chmod(0o600)
    print(f"Yazıldı: {YOL}")


if __name__ == "__main__":
    main()
