#!/usr/bin/env python3
"""aSc "Öğretmen Ders Programları" PDF'inden öğretmen listesini üretir (2026-10-13).

Çıktı: tahtayoklama/dashboard/config/ogretmenler.json (gitignore'lu — personel adları
public repoya gitmez). /api/okul/ogretmen ucu ve Open WebUI "Okul Bilgisi" aracı `ogretmenler`i,
panonun ders hücresi `program`ı (sınıf → gün → ders no → öğretmen adları) okur (2026-10-14).
Ders programı değişince (yeni aSc PDF) yeniden çalıştırılır.

TC/telefon/e-posta İÇERMEZ; yalnızca ad soyad, verdiği ders kısaltmaları ve sınıflar.

Kullanım (server/ venv'iyle):
    server/venv/bin/python tahtayoklama/dashboard/scripts/ogretmen_listesi_uret.py [PDF]
"""

import json
import re
import sys
from pathlib import Path

import pymupdf

PDF = Path("/mnt/farabi-data/farabi/mudur/anadolu öğrt.pdf")
CIKTI = Path(__file__).resolve().parents[1] / "config" / "ogretmenler.json"
DERS_PROGRAMI = Path(__file__).resolve().parents[2] / "data" / "ders_programi.json"
ATLA = re.compile(
    r"^(\d+(-[A-Z])?|\d{1,2}:\d{2}.*|Pa|Sa|Ça|Pe|Cu|Rehber|Hedef|Kulüp|MTAL DERS"
    r"|İMAM HATİP DERS|Ders Planı.*|aSc.*|Öğretmen\b.*)$"
)


def sayfadan(metin: str) -> dict | None:
    satirlar = metin.splitlines()
    ad = next((s[len("Öğretmen ") :].strip() for s in satirlar if s.startswith("Öğretmen ")), "")
    if not ad:
        return None
    dersler = sorted(
        {re.sub(r"^S(?=[A-Z])", "", s) for s in satirlar if s and not ATLA.match(s)}
    )
    siniflar = sorted({s for s in satirlar if re.fullmatch(r"\d+-[A-Z]", s)})
    return {"ad_soyad": ad, "dersler": dersler, "siniflar": siniflar}


GUNLER = ["pazartesi", "sali", "carsamba", "persembe", "cuma"]
GUN_ETIKETLERI = ("Pa", "Sa", "Ça", "Pe", "Cu")
SINIF_DESENI = re.compile(r"^\d+-[A-Z]$")


def program_cikar(belge, ders_programi: dict) -> tuple[dict, list]:
    """Her öğretmen sayfasındaki 5 gün x 8 ders ızgarasından {sınıf: {gün: {ders no: [ad]}}} çıkarır.

    Izgara kelime koordinatlarından okunur (sütun = başlık satırındaki 1-8 numaralarının x'i,
    gün = Pa/Sa/Ça/Pe/Cu etiketinin y'si). Çift saatlik birleşik hücrede metin yalnızca ilk
    sütunda durur; ders_programi.json'da bir sonraki saat aynı dersse ona da yazılır.
    Döndürdüğü ikinci değer, ızgarası okunamayan ya da programda karşılığı olmayan kayıtlardır."""
    sonuc: dict = {}
    sorunlar: list = []
    for sayfa in belge:
        ad = next(
            (s[len("Öğretmen ") :].strip() for s in sayfa.get_text().splitlines() if s.startswith("Öğretmen ")),
            "",
        )
        if not ad:
            continue
        kelimeler = sayfa.get_text("words")
        baslik = {int(k[4]): (k[0] + k[2]) / 2 for k in kelimeler if k[4].isdigit() and abs(k[1] - 76) < 4 and 1 <= int(k[4]) <= 8}
        gun_y = sorted((k[1], k[4]) for k in kelimeler if k[4] in GUN_ETIKETLERI and k[0] < 60)
        if len(baslik) != 8 or len(gun_y) != 5:
            sorunlar.append((ad, "ızgara okunamadı"))
            continue
        sol = [baslik[i] - 46 for i in range(1, 9)] + [baslik[8] + 46]
        for k in kelimeler:
            if not SINIF_DESENI.match(k[4]):
                continue
            ders_no = next((i + 1 for i in range(8) if sol[i] <= k[0] < sol[i + 1]), None)
            gun = GUNLER[min(range(5), key=lambda i: abs(k[1] - (gun_y[i][0] + 10)))]
            gunluk = ders_programi.get(k[4], {}).get(gun, {})
            ders = gunluk.get(str(ders_no))
            if ders_no is None or ders is None:
                sorunlar.append((ad, k[4], gun, ders_no))
                continue
            for no in (ders_no, ders_no + 1) if gunluk.get(str(ders_no + 1)) == ders else (ders_no,):
                adlar = sonuc.setdefault(k[4], {}).setdefault(gun, {}).setdefault(str(no), [])
                if ad not in adlar:
                    adlar.append(ad)
    return sonuc, sorunlar


def main() -> None:
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else PDF
    belge = pymupdf.open(pdf)
    liste = [o for o in (sayfadan(s.get_text()) for s in belge) if o]
    ders_programi = json.loads(DERS_PROGRAMI.read_text(encoding="utf-8")).get("siniflar", {})
    program, sorunlar = program_cikar(belge, ders_programi)
    CIKTI.write_text(json.dumps({"ogretmenler": liste, "program": program}, ensure_ascii=False, indent=1), encoding="utf-8")
    CIKTI.chmod(0o600)
    dolu = sum(len(sl) for g in ders_programi.values() for sl in g.values())
    atanan = sum(len(sl) for g in program.values() for sl in g.values())
    print(f"{len(liste)} öğretmen yazıldı: {CIKTI}")
    print(f"program: {atanan}/{dolu} ders saatine öğretmen atandı, {len(sorunlar)} sorunlu kayıt")
    for sorun in sorunlar:
        print("  uyarı:", sorun)


if __name__ == "__main__":
    main()
