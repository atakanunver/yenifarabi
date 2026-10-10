"""Yollar ve ayarlar. Testler AYAR alanlarını monkeypatch.setattr ile değiştirir."""

import json
from dataclasses import dataclass, field
from pathlib import Path

KOK = Path(__file__).resolve().parent
FARABI = KOK.parent


@dataclass
class Ayarlar:
    db_yolu: Path = KOK / "veri" / "okul.db"
    pano_db_yolu: Path = field(
        default=FARABI / "tahtayoklama" / "dashboard" / "veri" / "yoklama_pano.db"
    )
    program_yolu: Path = FARABI / "mudur" / "ders_programi.json"
    havuz_db: str = "soru_havuzu"
    sms_url: str = "http://127.0.0.1:8020/api/arac/kod-sms"
    sms_anahtar: str = ""
    kazanim_esik: float = 0.7


def yukle() -> Ayarlar:
    a = Ayarlar()
    gizli = KOK / "config" / "gizli.json"
    if gizli.exists():
        a.sms_anahtar = json.loads(gizli.read_text(encoding="utf-8")).get(
            "sms_arac_anahtar", ""
        )
    return a


AYAR = yukle()
