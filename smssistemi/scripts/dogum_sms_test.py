#!/usr/bin/env python3
"""Doğum günü SMS'ini YALNIZ verilen numaraya (örnek isim "Test") gönderir; kayıt/son tarih yazmaz.

Kullanım:  venv/bin/python scripts/dogum_sms_test.py 05XXXXXXXXX
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import dogum_sms  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    conn = db.baglanti()
    try:
        sonuc = dogum_sms.calistir(conn, test_telefon=sys.argv[1], bekleme_sn=0)
    finally:
        conn.close()
    print(sonuc)
    return 0 if sonuc["basarili_sayisi"] == 1 else 1


if __name__ == "__main__":
    sys.exit(main())
