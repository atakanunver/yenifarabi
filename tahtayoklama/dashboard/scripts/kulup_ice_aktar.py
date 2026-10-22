#!/usr/bin/env python3
"""dashboard/scripts/kulup_ice_aktar.py — kulüp .docx dosyalarından
config/kulupler.json üretir (biçim: bkz. dashboard/kulupler.py).

    venv/bin/python scripts/kulup_ice_aktar.py --kuru   # yalnız rapor, dosya yazılmaz
    venv/bin/python scripts/kulup_ice_aktar.py          # config/kulupler.json yazar

Yalnızca stdlib (zipfile + re). Her docx: tablo dışı paragraflar (kulüp adı,
danışman, "DERS İŞLENECEK SINIF 10-A") + tek tablo (SIRA, SINIF, NO, AD-SOYAD).
Üyeler pano DB'sindeki (salt-okunur) aktif öğrencilerle NO'ya göre eşleştirilir,
ad pano'dan alınır; bulunamayan atlanır. Rapor kişisel veri içermez (sıra/sınıf/no).
"""

import argparse
import html
import json
import os
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent.parent
VARSAYILAN_KAYNAK = Path("/mnt/farabi-data/farabi/KULÜP DOSYASI")
VARSAYILAN_CIKTI = DASHBOARD / "config" / "kulupler.json"
PANO_DB = DASHBOARD / "veri" / "yoklama_pano.db"

_ASCII = str.maketrans("ÇĞİIÖŞÜçğıöşü", "CGIIOSUcgiosu")


def _buyuk(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def _kucuk(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def _ad_katla(s: str) -> list[str]:
    """Karşılaştırma için: büyük harf, ASCII'ye katlanmış, sıralı sözcükler."""
    return sorted(_buyuk(s).translate(_ASCII).split())


def _baslik_yap(s: str) -> str:
    """"BEYAZAY KULÜBÜ" -> "Beyazay Kulübü" (Türkçe i/ı; "ve" küçük kalır)."""
    sozcukler = []
    for w in _kucuk(s).split():
        sozcukler.append(w if w == "ve" else _buyuk(w[0]) + w[1:])
    return " ".join(sozcukler)


def _metin(xml: str) -> str:
    return html.unescape("".join(re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", xml, flags=re.DOTALL)))


def docx_ayristir(yol: Path) -> dict:
    """{ad, danisman, sinif, satirlar: [{sira, sinif, no, ad_soyad}]} (ham, eşleştirmesiz)."""
    xml = zipfile.ZipFile(yol).read("word/document.xml").decode("utf-8")
    tablo = re.search(r"<w:tbl>.*?</w:tbl>", xml, flags=re.DOTALL)
    govde = xml.replace(tablo.group(0), "") if tablo else xml
    paragraflar = [m for m in (_metin(p).strip() for p in
                   re.findall(r"<w:p[ >].*?</w:p>", govde, flags=re.DOTALL)) if m]
    ad = danisman = sinif = None
    for p in paragraflar:
        if ad is None and re.search(r"KUL[ÜU]B[ÜU]\s*$", p):
            ad = _baslik_yap(p)
        elif danisman is None and p.startswith("DANIŞMAN"):
            danisman = p.partition(":")[2].strip() or None
        elif sinif is None and (m := re.match(r"DERS\s+İŞLENECEK\s+SINIF\s*:?\s*(\d{1,2})\s*[-/]\s*([A-Za-z])\s*$", p)):
            sinif = f"{m.group(1)}-{m.group(2).upper()}"
    satirlar = []
    for tr in re.findall(r"<w:tr[ >].*?</w:tr>", tablo.group(0) if tablo else "", flags=re.DOTALL):
        hucreler = [_metin(tc).strip() for tc in re.findall(r"<w:tc>.*?</w:tc>", tr, flags=re.DOTALL)]
        if len(hucreler) < 4 or not hucreler[0].isdigit() or not hucreler[2].isdigit():
            continue  # başlık / boş satır
        m = re.match(r"^(\d{1,2})\s*[-/]\s*([A-Za-z])$", hucreler[1])
        satirlar.append({
            "sira": int(hucreler[0]),
            "sinif": f"{m.group(1)}-{m.group(2).upper()}" if m else hucreler[1],
            "no": int(hucreler[2]),
            "ad_soyad": hucreler[3],
        })
    return {"ad": ad, "danisman": danisman, "sinif": sinif, "satirlar": satirlar}


def kod_uret(ad: str) -> str:
    """"Beyazay Kulübü" -> KULUP-BEYAZAY (ilk sözcük, ASCII)."""
    return "KULUP-" + _buyuk(ad.split()[0]).translate(_ASCII)


def eslestir(satirlar: list[dict], pano: dict, adlar: dict) -> tuple[list[dict], dict]:
    """pano: {(sinif_ad, no): (ad_soyad, aktif)}; adlar: {no: [(sinif_ad, ad_soyad)]}.
    Döner: (üyeler, sayaçlar). Kayıp/pasif/başka sınıfta-farklı-ad atlanır."""
    uyeler, say = [], {"eslesen": 0, "bulunamayan": 0, "pasif": 0, "ad_uyusmazligi": 0, "sinif_farki": 0, "notlar": []}
    for s in satirlar:
        kayit = pano.get((s["sinif"], s["no"]))
        if kayit is None:
            # NO başka bir sınıfta mı? Ad da tutuyorsa aynı öğrenci, sınıfı pano'dan al.
            diger = [(sn, ad) for sn, ad in adlar.get(s["no"], [])
                     if _ad_katla(ad) == _ad_katla(s["ad_soyad"])]
            if len(diger) == 1:
                say["sinif_farki"] += 1
                kayit = (diger[0][1], 1)
                s = dict(s, sinif=diger[0][0])
            else:
                say["bulunamayan"] += 1
                say["notlar"].append(f"sıra {s['sira']} ({s['sinif']}/{s['no']}): pano'da yok, atlandı")
                continue
        if not kayit[1]:
            say["pasif"] += 1
            say["notlar"].append(f"sıra {s['sira']} ({s['sinif']}/{s['no']}): pasif, atlandı")
            continue
        if _ad_katla(kayit[0]) != _ad_katla(s["ad_soyad"]):
            say["ad_uyusmazligi"] += 1
            say["notlar"].append(f"sıra {s['sira']} ({s['sinif']}/{s['no']}): ad uyuşmuyor, pano adı alındı")
        say["eslesen"] += 1
        uyeler.append({"no": s["no"], "ad_soyad": kayit[0], "sinif": s["sinif"]})
    return uyeler, say


def pano_oku(yol: Path) -> tuple[dict, dict]:
    conn = sqlite3.connect(f"file:{yol}?mode=ro", uri=True)
    try:
        satirlar = conn.execute(
            "SELECT s.ad, o.no, o.ad_soyad, o.aktif FROM ogrenciler o "
            "JOIN siniflar s ON s.id = o.sinif_id"
        ).fetchall()
    finally:
        conn.close()
    pano = {(sn, no): (ad, aktif) for sn, no, ad, aktif in satirlar}
    adlar: dict[int, list] = {}
    for sn, no, ad, aktif in satirlar:
        if aktif:
            adlar.setdefault(no, []).append((sn, ad))
    return pano, adlar


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--kuru", action="store_true", help="yalnız rapor yaz, dosya yazma")
    ap.add_argument("--kaynak", type=Path, default=VARSAYILAN_KAYNAK)
    ap.add_argument("--cikti", type=Path, default=VARSAYILAN_CIKTI)
    ap.add_argument("--pano", type=Path, default=PANO_DB)
    a = ap.parse_args()

    pano, adlar = pano_oku(a.pano)
    kulupler, kodlar, toplam = [], set(), 0
    for yol in sorted(a.kaynak.glob("*.docx")):
        d = docx_ayristir(yol)
        if not (d["ad"] and d["sinif"] and d["satirlar"]):
            print(f"HATA {yol.name}: ad/sınıf/tablo ayrıştırılamadı", file=sys.stderr)
            return 1
        kod = kod_uret(d["ad"])
        if kod in kodlar:
            print(f"HATA kod çakışması: {kod}", file=sys.stderr)
            return 1
        kodlar.add(kod)
        uyeler, say = eslestir(d["satirlar"], pano, adlar)
        toplam += len(d["satirlar"])
        kulupler.append({"kod": kod, "ad": d["ad"], "danisman": d["danisman"],
                         "sinif": d["sinif"], "uyeler": uyeler})
        print(f"{kod} (sınıf {d['sinif']}): üye {len(d['satirlar'])}, eşleşen {say['eslesen']}, "
              f"bulunamayan {say['bulunamayan']}, pasif {say['pasif']}, "
              f"sınıf farkı {say['sinif_farki']}, ad uyuşmazlığı {say['ad_uyusmazligi']}")
        for not_ in say["notlar"]:
            print(f"    {not_}")
    print(f"{len(kulupler)} kulüp, {toplam} üye, {sum(len(k['uyeler']) for k in kulupler)} eşleşen")
    if a.kuru:
        print("--kuru: dosya yazılmadı")
        return 0
    a.cikti.parent.mkdir(parents=True, exist_ok=True)
    gecici = a.cikti.with_name(a.cikti.name + ".tmp")
    gecici.write_text(json.dumps(kulupler, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(gecici, 0o600)
    os.replace(gecici, a.cikti)
    print(f"yazıldı: {a.cikti}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
