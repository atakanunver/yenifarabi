"""osym_yukle.py — ÖSYM/YKS okul raporlarını (xls) ve genel istatistik tablosunu (docx) `osym` veri tabanına yükler.

    osym/venv/bin/python osym_yukle.py --sema
    osym/venv/bin/python osym_yukle.py --yukle <klasör> [--kuru]
    osym/venv/bin/python osym_yukle.py --docx "SON 15 YIL YERLEŞTİRME SONUÇLARI.docx"

Yıl ve rapor türü dosya adından değil, raporun başlığından ("... 2024 YILI SON SINIF ÖĞRENCİLERİ") okunur.
Aynı içerik (sha256) ikinci kez yüklenmez; aynı (yıl, rapor) için en yeni dosya `birincil` işaretlenir.
Bağlantı: OSYM_DSN ya da ~/.config/osym/baglanti. Veri öğrenci kimliği içerir; yalnızca yerel.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import os
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

YIL_ARALIK = (2022, 2026)  # "son 5 yıl"
_SADE = str.maketrans("çğıöşü", "cgiosu")
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def sade(v) -> str:
    """Türkçe harf/büyük-küçük harf ve boşluk duyarsız karşılaştırma anahtarı."""
    s = str(v if v is not None else "").replace("İ", "i").replace("I", "ı").lower().translate(_SADE)
    return " ".join(s.split())


def sayi(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    try:
        return float(str(v).strip().replace(",", "."))
    except ValueError:
        return None


def tam(v):
    n = sayi(v)
    return int(n) if n is not None else None


def metin(v):
    s = str(v if v is not None else "").strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s or None


def tc(v) -> str | None:
    s = metin(v)
    return s if s and re.fullmatch(r"\d{11}", s) else None


# --- ızgara (list[list]) ayrıştırıcıları ------------------------------------------------


def baslik_bilgisi(izgara, dosya_adi: str):
    """(yıl, rapor) — raporun başlık hücresinden; bulunamazsa (None, None)."""
    for satir in izgara[:8]:
        for h in satir:
            t = " ".join(str(h).split())
            m = re.search(r"(\d{4}) YILI SON SINIF", t)
            if not m:
                continue
            a = sade(t)
            if a.startswith("yks (osys) yerlestirme sonuclari"):
                return int(m[1]), "yerlestirme"
            if a.startswith("yks yerlestirme puanlari"):
                return int(m[1]), "yerlestirme_puani"
            if a.startswith("yks puanlar ve basari sirlari"):
                return int(m[1]), "ham_puan"
            if a.startswith("yks dogru yanlis sayilari"):
                return int(m[1]), "dogru_yanlis_ayt" if "ayt" in sade(dosya_adi) else "dogru_yanlis_tyt"
    return None, None


def baslik_satiri(izgara):
    """('Tc Kimlik No' hücreli satırın indeksi, sütunu) ya da (None, None)."""
    for i, satir in enumerate(izgara):
        for c, h in enumerate(satir):
            if sade(h) == "tc kimlik no":
                return i, c
    return None, None


def _etiketler(satir) -> dict[int, str]:
    return {c: sade(h) for c, h in enumerate(satir) if str(h).strip()}


def veri_satirlari(izgara, h: int, tc_sutun: int):
    for satir in izgara[h + 1:]:
        if tc_sutun < len(satir) and tc(satir[tc_sutun]):
            yield satir


def _hucre(satir, c):
    return satir[c] if c is not None and c < len(satir) else None


_YER_ETIKET = {
    "yerlestirme donemi": "donem", "program kodu": "program_kodu", "program adi": "program_adi",
    "universite adi": "universite", "fakulte/myo adi": "fakulte", "yerlestigi tercih sirasi": "tercih_sirasi",
    "puan turu": "puan_turu", "puan": "puan", "obp": "obp", "meteb durumu": "meteb", "kont. turu": "kont_turu",
    "ek puan durumu": "ek_puan",
}


def yerlestirme_satirlari(izgara):
    """yerlestirme tablosu için sözlükler (tc_kimlik, ad_soyad, donem, ...)."""
    h, tc_c = baslik_satiri(izgara)
    if h is None:
        return []
    et = _etiketler(izgara[h])
    harita = {}
    for c, e in et.items():
        if e in _YER_ETIKET:
            harita.setdefault(_YER_ETIKET[e], c)
        elif e.startswith("tubitak"):
            harita.setdefault("ek_puan_2", c)
    ad_c = next((c for c, e in et.items() if e == "ad soyad"), None)
    sayisal = {"tercih_sirasi": tam, "puan": sayi, "obp": sayi}
    cikti = []
    for s in veri_satirlari(izgara, h, tc_c):
        k = {"tc_kimlik": tc(s[tc_c]), "ad_soyad": metin(_hucre(s, ad_c))}
        for alan in ("donem", "program_kodu", "program_adi", "universite", "fakulte", "tercih_sirasi", "puan_turu",
                     "puan", "obp", "meteb", "kont_turu", "ek_puan", "ek_puan_2"):
            v = _hucre(s, harita.get(alan))
            k[alan] = sayisal[alan](v) if alan in sayisal else metin(v)
        cikti.append(k)
    return cikti


def puan_satirlari(izgara):
    """yks_puan tablosu için (tc_kimlik, ad_soyad, puan_turu, puan, basari_sirasi) sözlükleri (uzun biçim)."""
    h, tc_c = baslik_satiri(izgara)
    if h is None or h == 0:
        return []
    et = _etiketler(izgara[h])
    grup = sorted((c, str(izgara[h - 1][c]).strip()) for c in range(len(izgara[h - 1])) if str(izgara[h - 1][c]).strip())
    ad_c = next((c for c, e in et.items() if e == "ad soyad"), None)
    puan_c = [c for c, e in et.items() if e == "puan"]
    sira_c = [c for c, e in et.items() if e == "basari sirasi"]
    alanlar = []
    for i, (g, etiket) in enumerate(grup):
        son = grup[i + 1][0] if i + 1 < len(grup) else 10**6
        p = next((c for c in puan_c if g <= c < son), None)
        b = next((c for c in sira_c if g <= c < son), None)
        if p is not None:
            alanlar.append((etiket, p, b))
    cikti = []
    for s in veri_satirlari(izgara, h, tc_c):
        for etiket, p, b in alanlar:
            if sayi(_hucre(s, p)) is None and sayi(_hucre(s, b)) is None:
                continue
            cikti.append({"tc_kimlik": tc(s[tc_c]), "ad_soyad": metin(_hucre(s, ad_c)), "puan_turu": etiket,
                          "puan": sayi(_hucre(s, p)), "basari_sirasi": tam(_hucre(s, b))})
    return cikti


def dogru_yanlis_satirlari(izgara, varsayilan_sinav: str):
    """dogru_yanlis tablosu için (tc_kimlik, ad_soyad, sinav, test, dogru, yanlis, bos, ham) sözlükleri."""
    h, tc_c = baslik_satiri(izgara)
    if h is None or h < 2:
        return []
    et = _etiketler(izgara[h])
    ad_c = next((c for c, e in et.items() if e == "ad soyad"), None)
    testler = sorted((c, " ".join(str(izgara[h - 1][c]).split())) for c in range(len(izgara[h - 1])) if str(izgara[h - 1][c]).strip())
    bolumler = sorted((c, str(izgara[h - 2][c]).strip().upper()) for c in range(len(izgara[h - 2]))
                      if sade(izgara[h - 2][c]) in ("tyt", "ayt", "ydt"))  # AYT dosyasında bu satır test grubudur, sınav değil
    alanlar = []
    for i, (t, ad) in enumerate(testler):
        son = testler[i + 1][0] if i + 1 < len(testler) else 10**6
        sut = {e: next((c for c, x in et.items() if x == e and t <= c < son), None) for e in ("d", "y", "b", "ham")}
        if sut["d"] is None:
            continue
        sinav = next((b for c, b in reversed(bolumler) if c <= t), varsayilan_sinav)
        alanlar.append((sinav, ad, sut))
    cikti = []
    for s in veri_satirlari(izgara, h, tc_c):
        for sinav, ad, sut in alanlar:
            d, y, b, ham = (sayi(_hucre(s, sut[k])) for k in ("d", "y", "b", "ham"))
            if d is None and y is None:
                continue
            cikti.append({"tc_kimlik": tc(s[tc_c]), "ad_soyad": metin(_hucre(s, ad_c)), "sinav": sinav, "test": ad,
                          "dogru": d, "yanlis": y, "bos": b, "ham": ham})
    return cikti


# --- docx: genel istatistik --------------------------------------------------------------


def docx_tablolari(yol) -> list[list[list[str]]]:
    with zipfile.ZipFile(yol) as z:
        govde = ET.fromstring(z.read("word/document.xml")).find(f"{_W}body")
    tablolar = []
    for tbl in govde.iter(f"{_W}tbl"):
        tablolar.append([[" ".join("".join(t.text or "" for t in c.iter(f"{_W}t")).split()) for c in tr.findall(f"{_W}tc")]
                         for tr in tbl.findall(f"{_W}tr")])
    return tablolar


def genel_istatistik(tablolar) -> list[dict]:
    """'Öğretim Yılı' başlıklı tablolardaki yıl satırları (yıl, son sınıf, başvuran, kazanan, ... toplam)."""
    cikti, ogretim_yili = [], None
    for tablo in tablolar:
        for satir in tablo:
            if satir and sade(satir[0]) == "ogretim yili" and len(satir) > 1:
                m = re.match(r"(\d{4}(?:-\d{4})?)", satir[1])
                ogretim_yili = m[1] if m else None
            elif len(satir) >= 10 and re.fullmatch(r"20\d\d", satir[0]):
                v = [tam(x) for x in satir[1:10]]
                cikti.append({"yil": int(satir[0]), "ogretim_yili": ogretim_yili, "son_sinif": v[0], "basvuran": v[1],
                              "kazanan": v[2], "tercih_yapan": v[3], "lisans": v[4], "onlisans_sinavsiz": v[5],
                              "onlisans_sinavli": v[6], "aof": v[7], "toplam_yerlesen": v[8]})
    return cikti


# --- dosya/DB katmanı --------------------------------------------------------------------


def xls_izgara(yol) -> list[list]:
    import xlrd

    with open(os.devnull, "w") as log:
        sayfa = xlrd.open_workbook(str(yol), logfile=log).sheets()[0]
    return [sayfa.row_values(r) for r in range(sayfa.nrows)]


def dsn() -> str:
    return os.environ.get("OSYM_DSN") or (Path.home() / ".config/osym/baglanti").read_text(encoding="utf-8").strip()


def sema_uygula(c):
    c.execute((Path(__file__).with_name("sema.sql")).read_text(encoding="utf-8"))


def _ekle(c, tablo: str, satirlar: list[dict], sabit: dict):
    for k in satirlar:
        d = {**sabit, **k}
        c.execute(f"INSERT INTO {tablo} ({','.join(d)}) VALUES ({','.join(['%s'] * len(d))})", list(d.values()))


def dosya_yukle(c, yol: Path, kuru: bool = False) -> str:
    izgara = xls_izgara(yol)
    yil, rapor = baslik_bilgisi(izgara, yol.name)
    if yil is None:
        return "atlandı (başlık/yıl bulunamadı)"
    if not YIL_ARALIK[0] <= yil <= YIL_ARALIK[1]:
        return f"atlandı ({yil}: aralık dışı)"
    ham = yol.read_bytes()
    sha = hashlib.sha256(ham).hexdigest()
    if c.execute("SELECT 1 FROM yukleme WHERE sha256=%s", (sha,)).fetchone():
        return f"{yil} {rapor}: zaten yüklü (aynı içerik)"
    if rapor == "yerlestirme":
        satirlar = yerlestirme_satirlari(izgara)
    elif rapor in ("yerlestirme_puani", "ham_puan"):
        satirlar = puan_satirlari(izgara)
    else:
        satirlar = dogru_yanlis_satirlari(izgara, "AYT" if rapor.endswith("ayt") else "TYT")
    if kuru:
        return f"{yil} {rapor}: {len(satirlar)} satır (kuru)"
    zaman = datetime.datetime.fromtimestamp(yol.stat().st_mtime, datetime.timezone.utc)
    yid = c.execute(
        "INSERT INTO yukleme (yil,rapor,dosya,dosya_zamani,sha256,satir) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
        (yil, rapor, yol.name, zaman, sha, len(satirlar)),
    ).fetchone()[0]
    sabit = {"yukleme_id": yid, "yil": yil}
    if rapor == "yerlestirme":
        _ekle(c, "yerlestirme", satirlar, sabit)
    elif rapor in ("yerlestirme_puani", "ham_puan"):
        _ekle(c, "yks_puan", satirlar, {**sabit, "rapor": rapor})
    else:
        _ekle(c, "dogru_yanlis", satirlar, sabit)
    return f"{yil} {rapor}: {len(satirlar)} satır"


def birincil_isaretle(c):
    c.execute("UPDATE yukleme u SET birincil = (u.id = (SELECT id FROM yukleme x WHERE x.yil=u.yil AND x.rapor=u.rapor "
              "ORDER BY x.dosya_zamani DESC NULLS LAST, x.id DESC LIMIT 1))")


def docx_yukle(c, yol: Path) -> int:
    satirlar = genel_istatistik(docx_tablolari(yol))
    for k in satirlar:
        d = {**k, "kaynak": yol.name}
        c.execute(f"INSERT INTO genel_istatistik ({','.join(d)}) VALUES ({','.join(['%s'] * len(d))}) "
                  f"ON CONFLICT (yil) DO UPDATE SET " + ",".join(f"{a}=EXCLUDED.{a}" for a in d if a != "yil"), list(d.values()))
    return len(satirlar)


def mezun_guncelle(c) -> int:
    """mezun tablosunu ÖSYM tablolarından üretir; telefon alanlarına dokunmaz."""
    c.execute("""
        INSERT INTO mezun (tc_kimlik, ad_soyad, mezuniyet_yili, yerlesen_program, yerlesme_yili)
        SELECT k.tc_kimlik, k.ad_soyad, k.yil, y.program_adi || ' - ' || y.universite, y.yil
        FROM (SELECT DISTINCT ON (tc_kimlik) tc_kimlik, ad_soyad, yil FROM
                (SELECT tc_kimlik, ad_soyad, yil FROM yks_puan UNION ALL SELECT tc_kimlik, ad_soyad, yil FROM dogru_yanlis
                 UNION ALL SELECT tc_kimlik, ad_soyad, yil FROM yerlestirme) u
              ORDER BY tc_kimlik, yil) k
        LEFT JOIN (SELECT DISTINCT ON (tc_kimlik) * FROM yerlestirme_guncel ORDER BY tc_kimlik, yil DESC) y USING (tc_kimlik)
        ON CONFLICT (tc_kimlik) DO UPDATE SET ad_soyad = EXCLUDED.ad_soyad, mezuniyet_yili = EXCLUDED.mezuniyet_yili,
            yerlesen_program = EXCLUDED.yerlesen_program, yerlesme_yili = EXCLUDED.yerlesme_yili, guncelleme = now()""")
    return c.execute("SELECT count(*) FROM mezun").fetchone()[0]


def ozet_yukle(c, yol: Path) -> int:
    """'SON 5 YIL YERLESEN' tablosu: ilk satır yıllar, sonraki satırlar Mezun / Sınava Giren / Yerleşen / Oran."""
    import openpyxl

    satirlar = [r for r in openpyxl.load_workbook(yol, data_only=True).active.iter_rows(values_only=True) if any(x is not None for x in r)]
    yillar = {i: int(y) for i, y in enumerate(satirlar[0]) if isinstance(y, (int, float)) and 2000 <= y <= 2100}
    alan = {"mezun": "mezun", "sinava giren": "sinava_giren", "universiteye yerlesen": "yerlesen", "oran": "oran"}
    veri: dict[int, dict] = {y: {} for y in yillar.values()}
    for r in satirlar[1:]:
        ad = next((a for e, a in alan.items() if sade(r[0]).startswith(e)), None)
        if ad:
            for i, y in yillar.items():
                veri[y][ad] = r[i]
    for y, d in veri.items():
        d = {"yil": y, **d, "kaynak": yol.name}
        c.execute(f"INSERT INTO ozet_son5 ({','.join(d)}) VALUES ({','.join(['%s'] * len(d))}) ON CONFLICT (yil) DO UPDATE SET "
                  + ",".join(f"{a}=EXCLUDED.{a}" for a in d if a != "yil"), list(d.values()))
    return len(veri)


def main(argv=None) -> int:
    import psycopg

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sema", action="store_true")
    p.add_argument("--yukle", metavar="KLASÖR")
    p.add_argument("--docx", metavar="DOSYA")
    p.add_argument("--ozet", metavar="DOSYA")
    p.add_argument("--kuru", action="store_true")
    a = p.parse_args(argv)
    with psycopg.connect(dsn()) as c:
        if a.sema:
            sema_uygula(c)
            print("şema uygulandı")
        if a.yukle:
            for yol in sorted(Path(a.yukle).rglob("*.xls")):
                try:
                    print(f"{yol.name[:60]:60} {dosya_yukle(c, yol, a.kuru)}")
                except Exception as e:  # noqa: BLE001 — bozuk dosya tüm yüklemeyi durdurmasın
                    print(f"{yol.name[:60]:60} HATA {type(e).__name__}: {e}")
            if not a.kuru:
                birincil_isaretle(c)
                print(f"mezun: {mezun_guncelle(c)} kişi")
        if a.docx:
            print(f"genel_istatistik: {docx_yukle(c, Path(a.docx))} yıl")
        if a.ozet:
            print(f"ozet_son5: {ozet_yukle(c, Path(a.ozet))} yıl")
        if a.kuru:
            c.rollback()
    return 0


if __name__ == "__main__":
    sys.exit(main())
