"""
core/tahta.py — Tahtanın kimliği: hangi derslikte olduğu.

Her akıllı tahta belirli bir sınıfta durur (10-A, 11-B, 12-C…). Bu bilgi üç
yerde kullanılır:

  1. Arayüzde görünür — hangi tahtaya baktığını bilmek için.
  2. Sistem promptuna girer — Farabi hangi sınıfa ders verdiğini bilir.
  3. Plan aramasını daraltır — derslik 10-A ise `ders_icerigi` sınıfı 10
     olarak varsayar; öğretmenin her seferinde "10. sınıf" demesi gerekmez.

`config/api_keys.json` içindeki `derslik` alanından okunur, elle yazılır.
"""

import json
import re
from pathlib import Path

BASE_DIR    = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# "10-A", "10A", "10 A", "12-c" -> ("10", "A")
_DERSLIK_RE = re.compile(r"^\s*(\d{1,2})\s*[-/ ]?\s*([A-Za-zÇĞİÖŞÜçğıöşü]?)\s*$")


def derslik() -> str:
    """Tahtanın bulunduğu derslik, örn. '10-A'. Tanımsızsa boş dize."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            ham = str(json.load(f).get("derslik", "")).strip()
    except Exception:
        return ""
    if not ham:
        return ""
    m = _DERSLIK_RE.match(ham)
    if not m:
        return ham          # beklenmedik biçim: olduğu gibi göster
    sinif, sube = m.group(1), m.group(2).upper()
    return f"{sinif}-{sube}" if sube else sinif


def sinif_duzeyi() -> str:
    """
    Derslikten sınıf düzeyini çıkar: '10-A' -> '10'.

    `ders_icerigi` bunu varsayılan sınıf filtresi olarak kullanır; böylece
    tahta 10-A'daysa plan aramasında 10. sınıf kendiliğinden seçilir.
    """
    d = derslik()
    m = re.match(r"^(\d{1,2})", d)
    return m.group(1) if m else ""


def etiket() -> str:
    """Arayüzde gösterilecek etiket. Tanımsızsa uyarı metni döner."""
    d = derslik()
    return d if d else "DERSLİK TANIMSIZ"
