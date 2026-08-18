"""server/metin_araclari.py — kelime-örtüşme eşleştirmesi için paylaşılan
normalizasyon yardımcıları.

`_norm`/`_kelimeler` daha önce `server/icerik.py` ve `server/yks.py`'de
birebir aynı (satır satır identik) iki kopya olarak duruyordu — buraya
taşındı (2026-08-18), her iki dosya da buradan import ediyor. Saf,
yan-etkisiz fonksiyonlar; davranış DEĞİŞMEDİ, yalnızca konumları.
"""

import re
import unicodedata

_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", (s or "")).translate(_TR).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def kelimeler(s: str) -> set[str]:
    return {k for k in norm(s).split() if len(k) > 3}
