#!/usr/bin/env python3
"""e-Okul öğrenci listesini okul_ana ile karşılaştırır. Yazmak için --uygula gerekir."""

import argparse
import csv
import os
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import okul_ana_veri as veri


def tr_buyuk(s):
    return s.translate(str.maketrans("iı", "İI")).upper()


def anahtar(s):
    return " ".join(s.upper().translate(str.maketrans("ÇĞİÖŞÜ", "CGIOSU")).split())


def baslik(satir):
    alanlar = {}
    for i, hucre in satir.items():
        ad = anahtar(hucre).replace(" ", "")
        if ad in ("OKULNO", "OGRENCINO"):
            alanlar["no"] = i
        elif ad in ("SINIF", "SINIF/SUBE"):
            alanlar["sinif"] = i
        elif ad in ("CINSIYET", "CINSIYETI"):
            alanlar["CINSIYET"] = i
        elif ad == "OGRENCIAD-SOYAD":
            alanlar["ADISOYADI"] = i
        elif ad in ("ADISOYADI", "ADI", "SOYADI"):
            alanlar[ad] = i
    if "no" in alanlar and (
        "ADISOYADI" in alanlar or {"ADI", "SOYADI"} <= alanlar.keys()
    ):
        return alanlar


def xlsx_sayfalari(yol):
    with zipfile.ZipFile(yol) as z:
        ortak = []
        if "xl/sharedStrings.xml" in z.namelist():
            ortak = [
                "".join(t.text or "" for t in si.findall(".//{*}t"))
                for si in ET.fromstring(z.read("xl/sharedStrings.xml"))
            ]
        isimler = {}
        if "xl/workbook.xml" in z.namelist():
            baglar = {
                b.get("Id"): posixpath.normpath(
                    posixpath.join("xl", b.attrib["Target"])
                ).lstrip("/")
                for b in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
            }
            for sheet in ET.fromstring(z.read("xl/workbook.xml")).findall(
                ".//{*}sheet"
            ):
                rid = next(v for k, v in sheet.attrib.items() if k.endswith("}id"))
                isimler[baglar[rid]] = sheet.attrib["name"]
        for dosya in z.namelist():
            if not re.fullmatch(r"xl/worksheets/[^/]+\.xml", dosya):
                continue
            satirlar = []
            for row in ET.fromstring(z.read(dosya)).findall(".//{*}sheetData/{*}row"):
                satir = {}
                for c in row.findall("{*}c"):
                    deger = c.findtext("{*}v", "")
                    if c.get("t") == "s":
                        deger = ortak[int(deger)]
                    elif c.get("t") == "inlineStr":
                        deger = "".join(t.text or "" for t in c.findall(".//{*}t"))
                    satir[c.attrib["r"].rstrip("0123456789")] = deger.strip()
                satirlar.append(satir)
            yield isimler.get(dosya, Path(dosya).stem), satirlar


def sayfalar(yol):
    if yol.suffix.lower() == ".xlsx":
        yield from xlsx_sayfalari(yol)
    elif yol.suffix.lower() == ".csv":
        with yol.open(encoding="utf-8-sig", newline="") as f:
            for ayrac in (";", ",", "\t"):
                f.seek(0)
                rows = (dict(enumerate(r)) for r in csv.reader(f, delimiter=ayrac))
                if any(baslik(r) for r in rows):
                    f.seek(0)
                    yield (
                        yol.name,
                        (dict(enumerate(r)) for r in csv.reader(f, delimiter=ayrac)),
                    )
                    return
            yield yol.name, []
    else:
        raise ValueError("Dosya XLSX veya CSV olmalı.")


def sinif_adi(s):
    m = re.fullmatch(
        r"(9|10|11|12)(?:\.?\s*SINIF)?\s*[/\-]\s*([A-Z0-9]{1,3})(?:\s+SUBESI)?",
        anahtar(s),
    )
    if not m:
        raise ValueError("sınıf geçersiz")
    return "-".join(m.groups())


def aktar(c, yol, uygula=False):
    ogrenciler = {o["okul_no"]: o for o in veri.ogrenciler(c, pasifler=True)}
    siniflar = {s["ad"] for s in veri.siniflar(c)}
    say = Counter(eklenecek=0, güncellenecek=0, değişmeyen=0, hatalı=0)
    sinif_say = Counter()
    gorulen = set()
    nedenler = Counter()
    taninmayan = []
    taninan = 0
    for sayfa_adi, sayfa in sayfalar(yol):
        baslik_sinifi = None
        alanlar = None
        for row in sayfa:
            yeni_baslik = baslik(row)
            if yeni_baslik and ("sinif" in yeni_baslik or baslik_sinifi):
                alanlar = yeni_baslik
                continue
            if not alanlar:
                for hucre in row.values():
                    m = re.search(
                        r"\b(9|10|11|12)(?:\s*[/\-]\s*|\s+)([A-Z0-9]{1,3})\s+SINIFI\b",
                        anahtar(hucre),
                    )
                    if m:
                        baslik_sinifi = "-".join(m.groups())
                continue
            if not any(v.strip() for v in row.values()):
                continue
            r = {k: row.get(i, "").strip() for k, i in alanlar.items()}
            try:
                try:
                    no = veri._no(r["no"])
                except ValueError:
                    raise ValueError("no geçersiz") from None
                if no in gorulen:
                    raise ValueError("tekrarlanan no")
                adlar = (
                    [r["ADISOYADI"]] if "ADISOYADI" in r else [r["ADI"], r["SOYADI"]]
                )
                if not all(adlar):
                    raise ValueError("ad boş")
                try:
                    ad = veri._ad(" ".join(adlar))
                except ValueError:
                    raise ValueError("ad geçersiz") from None
                eski = ogrenciler.get(no, {})
                sinif = r.get("sinif", baslik_sinifi)
                seviye = re.fullmatch(r"(9|10|11|12)(?:\.?\s*SINIF)?", anahtar(sinif))
                if seviye:
                    sinif = eski.get("sinif") or ""
                    if not sinif.startswith(seviye[1] + "-"):
                        raise ValueError("şube yok")
                else:
                    sinif = sinif_adi(sinif)
                cinsiyet = eski.get("cinsiyet")
                if r.get("CINSIYET"):
                    cinsiyet = {
                        "E": "Erkek",
                        "ERKEK": "Erkek",
                        "K": "Kız",
                        "KIZ": "Kız",
                    }.get(anahtar(r["CINSIYET"]))
                    if not cinsiyet:
                        raise ValueError("cinsiyet geçersiz")
            except ValueError as hata:
                nedenler[str(hata)] += 1
                say["hatalı"] += 1
                continue
            gorulen.add(no)
            sinif_say[sinif] += 1
            if eski and veri.tr_kucuk(ad) == veri.tr_kucuk(eski["ad_soyad"]):
                ad = eski["ad_soyad"]
            else:
                ad = tr_buyuk(ad)
            if (seviye or eski.get("aktif")) and (ad, sinif, cinsiyet) == (
                eski["ad_soyad"],
                eski["sinif"],
                eski["cinsiyet"],
            ):
                say["değişmeyen"] += 1
                continue
            say["güncellenecek" if eski else "eklenecek"] += 1
            if uygula:
                if sinif not in siniflar:
                    veri.sinif_ekle(c, sinif)
                    siniflar.add(sinif)
                dogum = eski.get("dogum_tarihi")
                veri.ogrenci_kaydet(
                    c,
                    no,
                    ad,
                    cinsiyet,
                    eski.get("telefon"),
                    str(dogum) if dogum else None,
                    sinif,
                    yeni=not eski,
                )
                if seviye and not eski["aktif"]:
                    veri.ogrenci_pasif(c, no, False)
        if alanlar:
            taninan += 1
        else:
            taninmayan.append(sayfa_adi)
    return say, sinif_say, nedenler, taninmayan, taninan


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dosya", type=Path)
    ap.add_argument("--uygula", action="store_true")
    ap.add_argument("--dsn")
    a = ap.parse_args(argv)
    dsn = (a.dsn or os.environ.get("OKUL_ANA_DSN") or "").strip()
    if a.uygula and not dsn:
        ap.error("--uygula için --dsn veya OKUL_ANA_DSN gerekli")
    try:
        with psycopg.connect(dsn or veri.dsn(), row_factory=dict_row) as c:
            c.read_only = not a.uygula
            c.isolation_level = psycopg.IsolationLevel.SERIALIZABLE
            c.execute("SET LOCAL search_path = okul_ana")
            say, siniflar, nedenler, taninmayan, taninan = aktar(c, a.dosya, a.uygula)
    except (
        OSError,
        psycopg.Error,
        ValueError,
        csv.Error,
        zipfile.BadZipFile,
        ET.ParseError,
        KeyError,
        IndexError,
    ):
        print(
            "İçe aktarım tamamlanamadı. Dosyayı ve veritabanı bağlantısını kontrol edin.",
            file=sys.stderr,
        )
        return 1
    print(" ".join(f"{k}={v}" for k, v in say.items()))
    for sinif, adet in sorted(siniflar.items()):
        print(f"{sinif}={adet}")
    for neden, adet in sorted(nedenler.items()):
        print(f"{neden}={adet}")
    for sayfa in taninmayan:
        print(f"tanınmayan sayfa: {sayfa}")
    if not taninan:
        return 2
    if a.uygula:
        print("Panelden Yayınla'ya basın.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
