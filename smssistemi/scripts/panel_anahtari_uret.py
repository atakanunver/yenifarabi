"""Panel API anahtarı üretir (secrets.token_urlsafe(32)).

Yazılan dosyalar (chmod 600), AYNI anahtar:
  smssistemi/config/panel.json            {"anahtar": ...}
  --dashboard-yolu verilirse o dosya (örn. ../tahtayoklama/dashboard/config/sms_panel.json;
  bir dizin verilirse içine config/sms_panel.json)
Mevcut dosya --yenile olmadan EZİLMEZ. Anahtar ekrana YAZILMAZ.
"""

import argparse
import json
import os
import secrets
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
VARSAYILAN_PANEL = KOK / "config" / "panel.json"


def _yaz(yol: Path, anahtar: str) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(yol, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"anahtar": anahtar}, f)
    os.chmod(yol, 0o600)


def _oku(yol: Path) -> str:
    try:
        return str(json.loads(yol.read_text(encoding="utf-8")).get("anahtar") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def calistir(panel_yolu: Path, dashboard_yolu: Path | None, yenile: bool) -> list[str]:
    """Dönen: ekrana basılacak durum satırları (anahtar içermez)."""
    if dashboard_yolu is not None and dashboard_yolu.is_dir():
        dashboard_yolu = dashboard_yolu / "config" / "sms_panel.json"
    mevcut = _oku(panel_yolu) if not yenile else ""
    anahtar = mevcut or secrets.token_urlsafe(32)
    mesajlar = []
    for yol, ad in ((panel_yolu, "smssistemi"), (dashboard_yolu, "dashboard")):
        if yol is None:
            continue
        if yol.exists() and not yenile:
            mesajlar.append(f"{ad}: {yol} mevcut, ezilmedi (--yenile ile değiştir)")
        else:
            _yaz(yol, anahtar)
            mesajlar.append(f"{ad}: {yol} yazıldı")
    return mesajlar


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dashboard-yolu", type=Path, default=None)
    ap.add_argument("--yenile", action="store_true", help="mevcut anahtarı yeniden üret, dosyaları ez")
    a = ap.parse_args(argv)
    for satir in calistir(VARSAYILAN_PANEL, a.dashboard_yolu, a.yenile):
        print(satir)


if __name__ == "__main__":
    main()
