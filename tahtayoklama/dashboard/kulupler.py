"""Kulüp tanımları (config/kulupler.json, gitignore'lu — öğrenci verisi içerir).

scripts/kulup_ice_aktar.py üretir. Biçim (liste):
    [{"kod": "KULUP-BEYAZAY", "ad": "Beyazay Kulübü", "danisman": "...",
      "sinif": "10-A", "uyeler": [{"no": 206, "ad_soyad": "Deniz Deneme", "sinif": "9-A"}]}]
Kulüp yoklaması sınıf yoklamasından AYRI tutulur (kulup_yoklama tablosu); kod
tahtada roster dosya adı ve kayıttaki `sinif` olur. Dosya yok/bozuksa boş liste.
"""

import json
from pathlib import Path

KULUP_DOSYASI = Path(__file__).resolve().parent / "config" / "kulupler.json"


def yukle() -> list[dict]:
    try:
        veri = json.loads(KULUP_DOSYASI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [k for k in veri if isinstance(k, dict) and k.get("kod")] if isinstance(veri, list) else []


def bul(kod: str) -> dict | None:
    return next((k for k in yukle() if k["kod"] == kod), None)


def isimler(kulup: dict) -> dict[str, str]:
    """no -> ad_soyad (yoklayici._roster_by_no ile aynı biçim)."""
    return {str(u["no"]): u["ad_soyad"] for u in kulup["uyeler"]}


def roster_json(kulup: dict) -> str:
    """Tahta roster'ı (admin._roster_payload_olustur ile aynı şema + "ad")."""
    return json.dumps(
        {
            "sinif": kulup["kod"],
            "ad": kulup["ad"],
            "ogrenciler": [
                {"no": u["no"], "ad_soyad": f"{u['ad_soyad']} ({u['sinif']})"}
                for u in kulup["uyeler"]
            ],
        },
        ensure_ascii=False, indent=2,
    )
