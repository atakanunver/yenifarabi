"""Biten haftanın ödüllerini kayda yazar (idempotent; hafta zaten kapalıysa bir şey eklemez).

Günlük systemd zamanlayıcısı çağırır (okul/systemd/farabi-okul-odul-kapat.timer): kiosk ya da yönetici sayfası
pazartesi açılmasa da sonuç yazılsın. Elle: venv/bin/python scripts/odul_kapat.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import oduller


def main() -> None:
    conn = db.baglanti()
    try:
        hb = oduller.onceki_hafta(oduller.hafta_basi())
        print(f"{hb} haftası: eklenen ödül {oduller.kapat(conn, hb)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
