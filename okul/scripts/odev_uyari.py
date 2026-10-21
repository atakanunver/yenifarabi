"""Teslimi yaklaşan ödevler için öğrencilere push uyarısı (ödev başına bir kez; 08-20 arası).

Saatlik systemd zamanlayıcısı çağırır (okul/systemd/farabi-okul-odev-uyari.timer). Elle: venv/bin/python scripts/odev_uyari.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import push
import zaman


def main() -> None:
    conn = db.baglanti()
    try:
        print(f"uyarılan ödev: {push.yaklasan_odev_uyar(conn, zaman.simdi())}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
