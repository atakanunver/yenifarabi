#!/usr/bin/env python3
"""dashboard/scripts/dyk_ice_aktar.py — DYK kursu .xlsx dosyalarından config/dyk.json üretir
(biçim: bkz. dashboard/dyk.py). Tek seferlik.

    venv/bin/python scripts/dyk_ice_aktar.py <10ADERSLIK_klasoru> <12BDERSLIK_klasoru> [--zorla]

Yalnızca stdlib (zipfile + xml.etree). Her xlsx: tek sayfa, başlık satırı
`SIRA | OKUL NO | ÖĞRENCİ AD-SOYAD`; SIRA'ya güvenilmez, OKUL NO int'e çevrilir.
Dosya varsa --zorla olmadan ezilmez. Rapor kişisel veri içermez (yalnız sayılar).
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent.parent
VARSAYILAN_CIKTI = DASHBOARD / "config" / "dyk.json"

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_ASCII = str.maketrans("ÇĞİIÖŞÜ", "CGIIOSU")

DERSLER = {  # kod son eki -> (11. sınıf adı, 12. sınıf adı, öğretmen)
    # Öğretmen adı public depoya girmez: boş bırakılır, /admin/dyk panelinden girilir.
    "COGRAFYA": ("Coğrafya", "Coğrafya", ""),
    "DIN": ("Din Kültürü ve Ahlak Bilgisi", "Din Kültürü ve Ahlak Bilgisi", ""),
    "EDEBIYAT": ("Türk Dili ve Edebiyatı", "Türk Dili ve Edebiyatı", ""),
    "KIMYA": ("Kimya", "Kimya", ""),
    "TARIH": ("Tarih", "Tarih / İnkılap Tarihi", ""),
}
SINIFLAR = {"11": ("10-A", "11. Sınıf DYK"), "12": ("12-B", "12. Sınıf DYK")}

_HB = ("16:00", "17:30")  # hafta içi bloğu
_C1, _C3 = ("09:00", "10:30"), ("10:40", "12:10")  # cumartesi blokları
_PROGRAM_TASLAK = {  # (gün, blok, ders_no, ders)
    "11": [("pazartesi", _HB, 1, "COGRAFYA"), ("carsamba", _HB, 1, "EDEBIYAT"),
           ("persembe", _HB, 1, "DIN"), ("cuma", _HB, 1, "KIMYA"),
           ("cumartesi", _C1, 1, "KIMYA"), ("cumartesi", _C3, 3, "TARIH")],
    "12": [("pazartesi", _HB, 1, "DIN"), ("sali", _HB, 1, "EDEBIYAT"),
           ("carsamba", _HB, 1, "KIMYA"), ("persembe", _HB, 1, "COGRAFYA"),
           ("cuma", _HB, 1, "TARIH"), ("cumartesi", _C1, 1, "TARIH")],
}


def _buyuk(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def ders_kodu(dosya_adi: str) -> str:
    """"11 TARİH (BOTH).xlsx" -> TARIH (parantez, sayı, Türkçe harf farkı çözülür)."""
    govde = re.sub(r"\(.*?\)", "", Path(dosya_adi).stem)
    govde = re.sub(r"^\s*\d+\s*", "", govde).strip()
    return _buyuk(govde).translate(_ASCII)


def _sutun(ref: str) -> str:
    return re.match(r"[A-Z]+", ref).group(0)


def xlsx_ayristir(yol: Path) -> list[dict]:
    """Tek sayfalı xlsx -> [{no, ad_soyad}] (başlık satırından sonrası, ham)."""
    with zipfile.ZipFile(yol) as z:
        paylasilan = []
        if "xl/sharedStrings.xml" in z.namelist():
            kok = ET.fromstring(z.read("xl/sharedStrings.xml"))
            paylasilan = ["".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t"))
                          for si in kok.findall("m:si", _NS)]
        sayfa = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    satirlar, baslik_goruldu = [], False
    for row in sayfa.iter(f"{{{_NS['m']}}}row"):
        hucre = {}
        for c in row.findall("m:c", _NS):
            v = c.find("m:v", _NS)
            if c.get("t") == "s" and v is not None:
                deger = paylasilan[int(v.text)]
            elif c.get("t") == "inlineStr":
                deger = "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
            else:
                deger = v.text if v is not None else ""
            hucre[_sutun(c.get("r"))] = (deger or "").strip()
        if not baslik_goruldu:
            baslik_goruldu = "OKUL NO" in _buyuk(hucre.get("B", ""))
            continue
        no, ad = hucre.get("B", ""), hucre.get("C", "")
        if not no and not ad:
            continue  # boş satır
        satirlar.append({"no": int(float(no)), "ad_soyad": ad})
    if not baslik_goruldu:
        raise ValueError(f"{yol.name}: başlık satırı (SIRA | OKUL NO | ÖĞRENCİ AD-SOYAD) bulunamadı")
    return satirlar


def klasor_isle(grup: str, klasor: Path) -> dict:
    dersler, goruldu = [], set()
    for yol in sorted(klasor.glob("*.xlsx")):
        son = ders_kodu(yol.name)
        if son not in DERSLER or son in goruldu:
            raise ValueError(f"{yol.name}: tanınmayan ya da yinelenen ders ({son})")
        goruldu.add(son)
        uyeler, gorulen = [], {}
        for u in xlsx_ayristir(yol):
            if u["no"] not in gorulen:
                gorulen[u["no"]] = u["ad_soyad"]
                uyeler.append(u)
            elif gorulen[u["no"]] == u["ad_soyad"]:
                print(f"UYARI {yol.name}: okul no {u['no']} aynı adla iki kez, tekrarı atlandı")
            else:
                raise ValueError(f"{yol.name}: okul no {u['no']} farklı adlarla birden çok kez var")
        ad11, ad12, ogretmen = DERSLER[son]
        dersler.append({"kod": f"DYK-{grup}-{son}", "ad": ad11 if grup == "11" else ad12,
                        "ogretmen": ogretmen, "uyeler": uyeler})
    eksik = set(DERSLER) - goruldu
    if eksik:
        raise ValueError(f"{klasor}: eksik ders dosyası: {sorted(eksik)}")
    derslik, ad = SINIFLAR[grup]
    return {"derslik": derslik, "ad": ad, "dersler": dersler}


def program_uret() -> dict:
    return {
        grup: [{"gun": gun, "bas": blok[0], "bit": blok[1],
                "kod": f"DYK-{grup}-{ders}", "ders_no": no}
               for gun, blok, no, ders in taslak]
        for grup, taslak in _PROGRAM_TASLAK.items()
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("klasor11", type=Path, help="11. sınıf (10-A derslik) xlsx klasörü")
    ap.add_argument("klasor12", type=Path, help="12. sınıf (12-B derslik) xlsx klasörü")
    ap.add_argument("--cikti", type=Path, default=VARSAYILAN_CIKTI)
    ap.add_argument("--zorla", action="store_true", help="var olan dosyayı ez")
    a = ap.parse_args()

    if a.cikti.exists() and not a.zorla:
        print(f"HATA {a.cikti} var; ezmek için --zorla", file=sys.stderr)
        return 1
    try:
        siniflar = {"11": klasor_isle("11", a.klasor11), "12": klasor_isle("12", a.klasor12)}
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as e:
        print(f"HATA {e}", file=sys.stderr)
        return 1
    for s in siniflar.values():
        for d in s["dersler"]:
            print(f"{d['kod']}: üye {len(d['uyeler'])}")
    veri = {"siniflar": siniflar, "program": program_uret()}
    a.cikti.parent.mkdir(parents=True, exist_ok=True)
    gecici = a.cikti.with_name(a.cikti.name + ".tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(gecici, 0o600)
    os.replace(gecici, a.cikti)
    print(f"yazıldı: {a.cikti}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
