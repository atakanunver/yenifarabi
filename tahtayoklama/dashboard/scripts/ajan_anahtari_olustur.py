"""Makine API'si (/api/ajan) anahtarını config/ajan.json'a yazar.

Kullanım: dashboard/ dizininden `venv/bin/python scripts/ajan_anahtari_olustur.py [--zorla]`
Dosya varsa --zorla verilmedikçe ÜZERİNE YAZILMAZ. Anahtar ekrana basılmaz.
"""

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

AJAN_YOLU = Path(__file__).resolve().parent.parent / "config" / "ajan.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zorla", action="store_true", help="var olan anahtarın üzerine yaz")
    args = ap.parse_args()

    if AJAN_YOLU.exists() and not args.zorla:
        print(f"Zaten var: {AJAN_YOLU} (üzerine yazmak için --zorla)", file=sys.stderr)
        sys.exit(1)

    AJAN_YOLU.parent.mkdir(parents=True, exist_ok=True)
    icerik = json.dumps({"anahtar": secrets.token_urlsafe(32)}, indent=2)
    fd = os.open(AJAN_YOLU, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(icerik + "\n")
    os.chmod(AJAN_YOLU, 0o600)  # dosya önceden varsa (--zorla) izinleri de sıkılaştır
    print(f"yazıldı: {AJAN_YOLU}")


if __name__ == "__main__":
    main()
