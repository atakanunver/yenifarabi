"""VAPID anahtar çiftini üretip config/gizli.json'a yazar (Web Push için).

    venv/bin/python scripts/vapid_olustur.py "mailto:idare@ornek.k12.tr"   # konu: iletişim adresi
    venv/bin/python scripts/vapid_olustur.py "mailto:..." --zorla            # mevcut çifti DEĞİŞTİRİR

--zorla çiftin açık anahtarını değiştirir: mevcut tüm abonelikler geçersiz olur (kullanıcılar yeniden açmalı).
Özel anahtar ekrana basılmaz. Dosya 0600 yazılır.
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

GIZLI = Path(__file__).resolve().parent.parent / "config" / "gizli.json"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def uret() -> tuple[str, str]:
    k = ec.generate_private_key(ec.SECP256R1())
    ozel = k.private_numbers().private_value.to_bytes(32, "big")
    acik = k.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return _b64(ozel), _b64(acik)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("konu", help='iletişim, örn. "mailto:idare@ornek.k12.tr"')
    ap.add_argument("--zorla", action="store_true")
    a = ap.parse_args()
    if not a.konu.startswith(("mailto:", "https://")):
        print("Konu 'mailto:' ya da 'https://' ile başlamalı.", file=sys.stderr)
        return 2
    g = json.loads(GIZLI.read_text(encoding="utf-8")) if GIZLI.exists() else {}
    if g.get("vapid_ozel") and not a.zorla:
        print("VAPID çifti zaten var; değiştirmek için --zorla.", file=sys.stderr)
        return 1
    g["vapid_ozel"], g["vapid_acik"] = uret()
    g["vapid_konu"] = a.konu
    GIZLI.parent.mkdir(parents=True, exist_ok=True)
    GIZLI.write_text(json.dumps(g, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(GIZLI, 0o600)
    print("VAPID çifti yazıldı (özel anahtar gösterilmedi). Servisi yeniden başlatın.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
