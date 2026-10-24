"""Ders programı kopyalarının eşitlik denetimi (2026-10-24): `mudur/ders_programi.json` (Farabi client'ı
ve dijital okul bunu kullanır) ile panonun kopyası (`data/ders_programi.json`, ders etiketi) hücre hücre
karşılaştırılır. Yalnızca OKUR, hiçbir dosyaya yazmaz; düzeltme ilgili `ders_programi_yukle.py` ile elle yapılır."""

import json
from pathlib import Path

import ders_programi

MUDUR = Path("/home/ata/farabi/mudur/ders_programi.json")
_GUN = {"pazartesi": "Pazartesi", "sali": "Salı", "carsamba": "Çarşamba", "persembe": "Perşembe", "cuma": "Cuma"}
AZAMI_GOSTER = 10


def _oku(yol: Path) -> dict:
    siniflar = json.loads(yol.read_text(encoding="utf-8")).get("siniflar")
    if not isinstance(siniflar, dict):
        raise TypeError("siniflar yok")
    return siniflar


def program_farki(mudur: Path = MUDUR, pano: Path = ders_programi.DERS_PROGRAMI_DOSYASI) -> dict:
    """{'toplam': n, 'fark': [{'sinif','gun','saat','mudur','pano'}...]} ya da {'hata': 'neden'}."""
    try:
        a, b = _oku(mudur), _oku(pano)
    except (OSError, ValueError, TypeError) as e:
        return {"hata": f"{type(e).__name__}"}
    fark = []
    for sinif in sorted(set(a) | set(b)):
        for gun, gun_adi in _GUN.items():
            sa, sb = a.get(sinif, {}).get(gun, {}), b.get(sinif, {}).get(gun, {})
            for saat in sorted(set(sa) | set(sb), key=int):
                if sa.get(saat) != sb.get(saat):
                    fark.append({"sinif": sinif, "gun": gun_adi, "saat": saat, "mudur": sa.get(saat), "pano": sb.get(saat)})
    return {"toplam": len(fark), "fark": fark[:AZAMI_GOSTER]}
