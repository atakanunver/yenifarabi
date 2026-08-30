"""Panonun ortak giriş şifresini belirler, hash'ini config/gizli.json'a yazar.

Kullanım: dashboard/ dizininden `venv/bin/python scripts/sifre_belirle.py`
"""

import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth import sifre_hashle  # noqa: E402

GIZLI_YOLU = Path(__file__).resolve().parent.parent / "config" / "gizli.json"


def main() -> None:
    sifre = getpass.getpass("Yeni pano şifresi: ")
    tekrar = getpass.getpass("Tekrar: ")
    if sifre != tekrar:
        print("Şifreler eşleşmiyor.", file=sys.stderr)
        sys.exit(1)
    if len(sifre) < 6:
        print("Şifre en az 6 karakter olmalı.", file=sys.stderr)
        sys.exit(1)

    GIZLI_YOLU.parent.mkdir(parents=True, exist_ok=True)
    GIZLI_YOLU.write_text(
        json.dumps({"sifre_hash": sifre_hashle(sifre)}, indent=2),
        encoding="utf-8",
    )
    print(f"Yazıldı: {GIZLI_YOLU}")


if __name__ == "__main__":
    main()
