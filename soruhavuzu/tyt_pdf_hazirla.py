#!/usr/bin/env python3
"""MEBİ iki sütunlu TYT PDF'ini görselli, denetlenebilir arşive hazırlar.

Bu adım canlı veritabanına yazmaz. Cevap anahtarı ve 125 sıra doğrulanmadan çıktı üretmez.
"""
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import fitz
from PIL import Image

TESTLER = ("turkce", "sosyal", "matematik", "fen")
ADETLER = {"turkce": 40, "sosyal": 25, "matematik": 40, "fen": 20}


def _test_adi(metin):
    alt = "".join(c for c in unicodedata.normalize("NFKD", metin.casefold()) if not unicodedata.combining(c)).replace("ı", "i")
    if "turkce testi" in alt:
        return "turkce"
    if "sosyal bilimler testi" in alt:
        return "sosyal"
    if "temel matematik testi" in alt:
        return "matematik"
    if "fen bilimleri testi" in alt:
        return "fen"
    return None


def _ders(test, no):
    if test in ("turkce", "matematik"):
        return test
    if test == "fen":
        return "fizik" if no <= 7 else ("kimya" if no <= 14 else "biyoloji")
    return "tarih" if no <= 5 else ("cografya" if no <= 10 else ("felsefe" if no <= 15 or no >= 21 else "din"))


def _cevaplar(sayfa):
    bloklar = [b for b in sayfa.get_text("blocks") if 145 <= b[1] < 180 and len(re.findall(r"\d+\.\s*[A-E]", b[4])) >= 10]
    bloklar.sort(key=lambda b: b[0])
    if len(bloklar) != 4:
        raise ValueError(f"Cevap anahtarı dört sütunda bulunamadı: {len(bloklar)}")
    sonuc = {}
    for test, blok in zip(TESTLER, bloklar):
        cift = re.findall(r"(\d+)\.\s*([A-E])", blok[4])
        if [int(n) for n, _ in cift] != list(range(1, ADETLER[test] + 1)):
            raise ValueError(f"{test} cevap anahtarı eksik veya sırasız")
        sonuc[test] = {int(n): ord(harf) - ord("A") for n, harf in cift}
    return sonuc


def _pix(sayfa, rect):
    pix = sayfa.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), clip=fitz.Rect(rect), alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    # Sayfanın soluk filigranına değil gerçek metne/grafiğe göre alttaki boşluğu kırp.
    bbox = image.convert("L").point(lambda v: 255 if v < 235 else 0).getbbox()
    if bbox:
        image = image.crop((0, 0, image.width, min(image.height, bbox[3] + 30)))
    return image


def hazirla(pdf, hedef):
    pdf = Path(pdf)
    belge = fitz.open(pdf)
    if not len(belge):
        raise ValueError("PDF boş")
    cevap = _cevaplar(belge[-1])
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    sira = dict.fromkeys(TESTLER, 1)
    satirlar = []
    for sayfa_no in range(1, len(belge) - 1):
        sayfa = belge[sayfa_no]
        bloklar = sayfa.get_text("blocks")
        # Sınavın her soru sayfasındaki altbilgiyi kullan; açıklama sayfası
        # bütün test adlarını içerdiği için sayfa gövdesinden test saptanmaz.
        test = _test_adi(" ".join(b[4] for b in bloklar if b[1] >= 730))
        if not test:
            continue
        adaylar = []
        for b in bloklar:
            x, y = b[0], b[1]
            m = re.match(r"^\s*(\d{1,2})\s*\.(?:\s|\t)", b[4])
            if m and 65 < y < 720 and (x < 45 or 280 < x < 300):
                adaylar.append((0 if x < 45 else 1, y, int(m.group(1))))
        adaylar.sort()
        secilen = []
        for col, y, no in adaylar:
            if no == sira[test]:
                secilen.append((col, y, no))
                sira[test] += 1
        ortak = None
        for b in bloklar:
            m = re.search(r"(\d+)\s*[-–]\s*(\d+)\.\s*sorular[ıi].*?parçaya", b[4], re.I | re.S)
            if m and int(m.group(2)) == int(m.group(1)) + 1:
                bas = next((y for col, y, n in secilen if col == 0 and n == int(m.group(1))), None)
                if bas:
                    ortak = (int(m.group(1)), int(m.group(2)), (30, 73, 275, bas - 5))
        for col, y, no in secilen:
            ayni = [yy for cc, yy, _ in secilen if cc == col and yy > y]
            alt = min(ayni) - 5 if ayni else 720
            ust = max(73, y - 5)
            if ortak and no == ortak[0]:
                ust = 73
            x1, x2 = (30, 275) if col == 0 else (282, 525)
            gor = _pix(sayfa, (x1, ust, x2, alt))
            if ortak and no == ortak[1]:
                metin = _pix(sayfa, ortak[2])
                birlesik = Image.new("RGB", (max(metin.width, gor.width), metin.height + gor.height + 24), "white")
                birlesik.paste(metin, (0, 0))
                birlesik.paste(gor, (0, metin.height + 24))
                gor = birlesik
            ad = f"{test}-{no:02d}.png"
            hedef.mkdir(parents=True, exist_ok=True)
            gor.save(hedef / ad, optimize=True)
            satirlar.append({"test": test, "no": no, "ders": _ders(test, no), "sinif": 12,
                            "dogru_index": cevap[test][no], "sayfa": sayfa_no + 1, "gorsel": ad,
                            "kaynak_kimligi": f"yks:{sha}:{test}:{no}",
                            "secenek_tespit": sorted(set(re.findall(r"\b([A-E])\s*\)", sayfa.get_text(clip=fitz.Rect(x1, ust, x2, alt)))) )})
    for test in TESTLER:
        if sira[test] != ADETLER[test] + 1:
            raise ValueError(f"{test} soru sırası eksik: son bulunan {sira[test] - 1}/{ADETLER[test]}")
    eksikler = [f"{s['test']}-{s['no']}" for s in satirlar if s['secenek_tespit'] != list("ABCDE")]
    if eksikler:
        raise ValueError("Beş seçenek doğrulanamadı: " + ", ".join(eksikler))
    (hedef / "manifest.json").write_text(json.dumps({"pdf_sha256": sha, "sorular": satirlar}, ensure_ascii=False, indent=2), encoding="utf-8")
    return satirlar


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pdf", type=Path)
    p.add_argument("--cikti", type=Path, required=True)
    args = p.parse_args()
    if args.cikti.exists() and any(args.cikti.iterdir()):
        p.error("Çıktı dizini boş olmalı")
    satirlar = hazirla(args.pdf, args.cikti)
    print(f"{len(satirlar)} soru hazırlandı; veritabanına yazılmadı.")


if __name__ == "__main__":
    main()
