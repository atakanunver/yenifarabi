"""Okul bilgisi API'si (/api/okul) ayarını config/okul.json'a yazar.

Kullanım: dashboard/ dizininden `venv/bin/python scripts/okul_anahtari_olustur.py [--zorla]`
İçerik: {"anahtar": ..., "ogrenci_izinli": [e-postalar]} — öğrenci bilgisine
erişebilecek Open WebUI hesapları (2026-10-04 kullanıcı kararı: İdare + Öğretmen,
tahta hesabı HARİÇ). Kişisel öğretmen hesapları elle listeye eklenebilir.
Dosya varsa --zorla verilmedikçe ÜZERİNE YAZILMAZ. Anahtar ekrana basılmaz.
"""

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

OKUL_YOLU = Path(__file__).resolve().parent.parent / "config" / "okul.json"
VARSAYILAN_IZINLI = ["idare@farabi.local", "ogretmen@farabi.local"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zorla", action="store_true", help="var olan dosyanın üzerine yaz")
    args = ap.parse_args()

    if OKUL_YOLU.exists() and not args.zorla:
        print(f"Zaten var: {OKUL_YOLU} (üzerine yazmak için --zorla)", file=sys.stderr)
        sys.exit(1)

    OKUL_YOLU.parent.mkdir(parents=True, exist_ok=True)
    icerik = json.dumps({"anahtar": secrets.token_urlsafe(32),
                         "ogrenci_izinli": VARSAYILAN_IZINLI}, indent=2, ensure_ascii=False)
    fd = os.open(OKUL_YOLU, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(icerik + "\n")
    os.chmod(OKUL_YOLU, 0o600)
    print(f"yazıldı: {OKUL_YOLU}")


if __name__ == "__main__":
    main()
