"""soruhavuzu/kaynaklar.py — kaynak birimlerini (soru üretilecek metin parçaları) kataloglar.

Kitaplar: farabi DB'sindeki chunk_egitim, ardışık sayfalar ~grup_karakter'e kadar birleştirilir.
PDF'ler (kazanım testi / YKS): sayfa başına bir birim (PyMuPDF metni)."""

from collections.abc import Iterator
from pathlib import Path

import fitz

from soruhavuzu import dersler, vt

PDF_AZAMI_KARAKTER = 6000


def kitap_gruplari(farabi_conn, grup_karakter: int = 1800) -> Iterator[dict]:
    with farabi_conn.cursor() as cur:
        cur.execute(
            "SELECT k.id, k.sinif, k.ders, c.sayfa_no, c.metin FROM chunk_egitim c "
            "JOIN kitap k ON k.id = c.kitap_id ORDER BY k.id, c.sayfa_no, c.id"
        )
        satirlar = cur.fetchall()
    grup = None
    for kid, sinif, ders, sayfa, metin in satirlar:
        if grup and (
            grup["kid"] != kid or len(grup["metin"]) + len(metin) > grup_karakter
        ):
            yield _bitir(grup)
            grup = None
        if grup is None:
            grup = {
                "kid": kid,
                "sinif": sinif,
                "ders_ad": ders,
                "ilk": sayfa,
                "son": sayfa,
                "metin": "",
            }
        grup["son"] = sayfa
        grup["metin"] += ("\n" if grup["metin"] else "") + metin
    if grup:
        yield _bitir(grup)


def _bitir(g: dict) -> dict:
    return {
        "tur": "kitap",
        "anahtar": f"kitap:{g['kid']}:{g['ilk']}-{g['son']}",
        "ders": dersler.ders_anahtari(g["ders_ad"]),
        "sinif": g["sinif"],
        "etiket": f"{g['ders_ad']} {g['sinif']}, s. {g['ilk']}",
        "metin": g["metin"],
    }


def pdf_gruplari(yol: Path, tur: str) -> Iterator[dict]:
    sinif, ders = dersler.dosyadan_cozumle(yol.name)
    if tur == "yks":
        sinif, ders = 12, None  # YKS: ders soru başına modelden gelir
    onek = "Kazanım Testi" if tur == "kazanim" else "YKS"
    with fitz.open(yol) as belge:
        for i, sayfa in enumerate(belge, start=1):
            metin = sayfa.get_text().strip()
            if len(metin) < 200:
                continue
            yield {
                "tur": tur,
                "anahtar": f"{tur}:{yol.name}:{i}",
                "ders": ders,
                "sinif": sinif,
                "etiket": f"{onek}: {yol.stem}, s. {i}",
                "metin": metin[:PDF_AZAMI_KARAKTER],
            }


def katalogla(
    havuz_conn, farabi_conn, kazanim_dizin: Path, yks_dizin: Path
) -> dict[str, int]:
    sayac = {"kitap": 0, "kazanim": 0, "yks": 0, "atlanan_pdf": 0, "cozulemeyen": []}
    gruplar = list(kitap_gruplari(farabi_conn))
    for tur, dizin in (("kazanim", kazanim_dizin), ("yks", yks_dizin)):
        for yol in sorted(dizin.glob("*.pdf")):
            try:
                gruplar.extend(pdf_gruplari(yol, tur))
            except Exception as e:  # noqa: BLE001 — bozuk PDF kataloğu durdurmasın
                print(f"[katalog] {yol.name} okunamadı: {type(e).__name__}: {e}")
                sayac["atlanan_pdf"] += 1
    for g in gruplar:
        if g["sinif"] is None or (g["tur"] != "yks" and g["ders"] is None):
            ad = g["anahtar"].split(":")[1]
            if ad not in sayac["cozulemeyen"]:
                sayac["cozulemeyen"].append(ad)
            continue
        if vt.birim_ekle(
            havuz_conn,
            g["tur"],
            g["anahtar"],
            g["ders"],
            g["sinif"],
            g["etiket"],
            g["metin"],
        ):
            sayac[g["tur"]] += 1
    return sayac
