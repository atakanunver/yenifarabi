"""soruhavuzu/kazanimlar.py — yıllık plan kazanımları (tahtayoklama/data/kazanimlar.json) → kazanim satırları.
2026-10-08 kullanıcı kararı: her soru bir kazanımla; yalnız planı olan (sınıf, ders)."""

import json
import re
from datetime import date
from pathlib import Path

from soruhavuzu import dersler

VARSAYILAN = Path(__file__).resolve().parent.parent / "tahtayoklama" / "data" / "kazanimlar.json"
# "KİM.9.1.1." ya da "10.1.3." — sondaki nokta koddan sayılmaz
KOD_RE = re.compile(r"^\s*((?:[A-ZÇĞİÖŞÜ]{2,6}\.)?\d+(?:\.\d+)+)\.?\s")


def haftalar(yol: Path = VARSAYILAN) -> dict[int, date]:
    veri = json.loads(Path(yol).read_text(encoding="utf-8")).get("haftalar", {})
    return {int(h): date.fromisoformat(t) for h, t in veri.items()}


def oku(yol: Path = VARSAYILAN) -> tuple[list[dict], set[str]]:
    veri = json.loads(Path(yol).read_text(encoding="utf-8"))["kazanimlar"]
    satirlar, atlanan = [], set()
    for sinif, dersler_ in veri.items():
        for ders_ad, haftalar in dersler_.items():
            anahtar = dersler.ders_anahtari(ders_ad)
            if anahtar is None:
                atlanan.add(ders_ad)
                continue
            for hafta, metin in sorted(haftalar.items(), key=lambda x: int(x[0])):
                for parca in (m.strip() for m in str(metin).split("\n")):
                    if not parca:
                        continue
                    m = KOD_RE.match(parca + " ")
                    satirlar.append({"sinif": int(sinif), "ders": anahtar, "hafta": int(hafta),
                                     "kod": m.group(1) if m else None, "metin": parca})
    return satirlar, atlanan
