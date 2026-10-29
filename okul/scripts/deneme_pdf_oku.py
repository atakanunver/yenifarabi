"""Deneme sonuç PDF'ini (okul net listesi + kurum soru analizi + öğrenci sayfaları) deneme_yukle.py JSON'una çevirir.

Kullanım (pdfplumber yalnız server venv'inde var, okul venv'ine EKLENMEZ):
    ../server/venv/bin/python -I scripts/deneme_pdf_oku.py <pdf> <cikti.json> --ad "<deneme adı>"
Her öğrencinin PDF sayfası <cikti.json>_sayfalar/ altına ayrılır ve JSON'da `pdf_yol` olarak yazılır (deneme_yukle.py yükler).
Öğrenci sayfalarındaki cevap dizisi: büyük harf = doğru, küçük harf = yanlış, boşluk = boş. Kurum analizindeki
A/B kitapçık eşlemesiyle soru -> kazanım bulunur; dizi kitapçık anahtarıyla uyuşmazsa o test için kazanım YAZILMAZ.
Öğrencinin kendi sıralaması (şube/kurum/ilçe/il/genel sıra + katılımcı sayısı + yüzdelik) `siralama` olarak alınır. Çıktı öğrenci verisi içerir: okul/veri/ altına (gitignore'lu) yaz.
"""

import json
import re
import sys

# Her testin (bölümün) ders aralıkları: A kitapçığı soru numarasına göre. Sıra: Türkçe, Sosyal, Matematik, Fen.
DERS_ARALIKLARI = [
    [("Türkçe", 1, 40)],
    [
        ("Tarih-1", 1, 5),
        ("Coğrafya-1", 6, 10),
        ("Felsefe", 11, 15),
        ("Din Kül. ve Ahl. Bil.", 16, 20),
        ("Felsefe (Seçmeli)", 21, 25),
    ],
    [("Matematik-1", 1, 30), ("Geometri", 31, 40)],
    [("Fizik", 1, 7), ("Kimya", 8, 14), ("Biyoloji", 15, 20)],
]

_ETIKET = re.compile(r"^A-(\d+)\nB-(\d+)$")
_SAYI = re.compile(r"^\d+$")
_NET = re.compile(r"^-?\d+(,\d+)?$")


def _ondalik(s: str) -> float:
    return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)


def cevap_durumlari(cevap: str, anahtar: str) -> list[str] | None:
    """Cevap dizisini d/y/b listesine çevirir; anahtarla çelişirse (güvenilmez) None."""
    if len(cevap) > len(anahtar):
        return None
    cevap = cevap.ljust(len(anahtar))
    sonuc = []
    for c, a in zip(cevap, anahtar):
        if c == " ":
            sonuc.append("b")
        elif c.isupper():
            if c != a:
                return None
            sonuc.append("d")
        else:
            if c.upper() == a:
                return None
            sonuc.append("y")
    return sonuc


def kurum_bolumleri(tablolar: list[list[list]]) -> list[list[dict]]:
    """Kurum soru analizi tablolarından bölümleri çıkarır (A numarası geri sarınca yeni bölüm)."""
    bolumler: list[list[dict]] = []
    onceki = 0
    for tablo in tablolar:
        for satir in tablo:
            m = _ETIKET.match(satir[0] or "") if satir and satir[0] else None
            if not m:
                continue
            a, b = int(m.group(1)), int(m.group(2))
            if a <= onceki or not bolumler:
                bolumler.append([])
            onceki = a
            bolumler[-1].append(
                {
                    "a": a,
                    "b": b,
                    "kazanim": " ".join((satir[1] or "").split()),
                    "dc": (satir[2] or "").strip(),
                }
            )
    return bolumler


def beklenen_anahtar(bolum: list[dict], kitapcik: str) -> str:
    """Kitapçıktaki soru sırasına göre doğru cevap dizisi."""
    alan = kitapcik.lower()
    sira = {s[alan]: s["dc"] for s in bolum}
    return "".join(sira.get(k, "?") for k in range(1, len(bolum) + 1))


def kazanim_ozeti(
    bolum: list[dict], kitapcik: str, durumlar: list[str], ders_araliklari: list[tuple]
) -> list[dict]:
    """Öğrencinin soru durumlarını (d/y/b) (ders, kazanım) başına toplar; ilk görülme sırası korunur."""
    alan = kitapcik.lower()
    soru_by_pozisyon = {s[alan]: s for s in bolum}
    toplam: dict[tuple, dict] = {}
    for poz, durum in enumerate(durumlar, start=1):
        s = soru_by_pozisyon.get(poz)
        if s is None:
            continue
        ders = next((ad for ad, bas, bit in ders_araliklari if bas <= s["a"] <= bit), "")
        k = toplam.setdefault(
            (ders, s["kazanim"]),
            {"ders": ders, "kazanim": s["kazanim"], "d": 0, "y": 0, "b": 0},
        )
        k[durum] += 1
    return list(toplam.values())


def secmeli_ayikla(dersler: dict) -> set[str]:
    """Öğrencinin seçmediği Din / Felsefe (Seçmeli) dersi (hiç cevap yok) listeden düşer; ikisi de boşsa yalnız seçmeli."""
    din, sec = "Din Kül. ve Ahl. Bil.", "Felsefe (Seçmeli)"
    bos = {ad: ad in dersler and dersler[ad]["d"] == 0 and dersler[ad]["y"] == 0 for ad in (din, sec)}
    if bos[sec]:
        return {sec}
    if bos[din]:
        return {din}
    return set()


def ogrenci_basligi(metin: str) -> dict | None:
    """Öğrenci sayfası başlığı: şube, okul no, ad, toplam net."""
    m = re.search(r"^(\d{1,2}-\S+) - (\d+)\s*$", metin, re.MULTILINE)
    if not m:
        return None
    n = re.search(
        r"^(.+?) \d+ \d+ \d+ \d+ (-?[\d.,]+) Sizin yeriniz", metin[m.end() :], re.MULTILINE
    )
    if not n:
        return None
    return {
        "sinif": m.group(1),
        "okul_no": int(m.group(2)),
        "ad_soyad": n.group(1).strip(),
        "toplam_net": _ondalik(n.group(2)),
    }


def ders_satiri(satir: list) -> tuple[str, dict] | None:
    """[ders, soru, doğru, yanlış, boş, net, %başarı] satırı; başka satırlar için None."""
    dolu = [(c or "").strip() for c in satir if (c or "").strip()]
    if len(dolu) != 7 or dolu[0].startswith("Cevap"):
        return None
    ad, soru, d, y, b, net, _yuzde = dolu
    if not (_SAYI.match(soru) and _SAYI.match(d) and _SAYI.match(y) and _SAYI.match(b)
            and _NET.match(net)):
        return None
    return ad, {"d": int(d), "y": int(y), "b": int(b), "net": _ondalik(net)}


def _anahtar_cevaplar(satirlar: list[list]) -> list[tuple[str, str, str]]:
    """Sayfadaki (kitapçık, anahtar, cevap) üçlüleri, sayfadaki sırayla."""
    sonuc = []
    for i, satir in enumerate(satirlar):
        hucreler = [(c or "") for c in satir]
        if not any(c.strip() == "Cevap Anahtarı" for c in hucreler):
            continue
        sonraki = next(
            (
                r
                for r in satirlar[i + 1 : i + 4]
                if any((c or "").strip() == "Cevaplarınız" for c in r)
            ),
            None,
        )
        if sonraki is None:
            continue
        harfli = [c.strip() for c in hucreler if re.fullmatch(r"[A-E]{10,}", c.strip())]
        kit = [c.strip() for c in hucreler if c.strip() in ("A", "B")]
        cevaplar = [
            c for c in (c or "" for c in sonraki) if c.strip() and c.strip() != "Cevaplarınız"
        ]
        if harfli and kit and cevaplar:
            sonuc.append((kit[0], harfli[0], max(cevaplar, key=len)))
    return sonuc


def siralama(metin: str) -> dict | None:
    """Öğrenci sayfasındaki 'Şube Kurum İlçe İl Genel' sıra, katılımcı sayısı ve yüzdelik (yalnız öğrencinin kendi yeri)."""
    s = re.search(r"Öğrenci Sıra No ((?:\d+ ){4}\d+)\s*% ([\d,]+)", metin)
    k = re.search(r"Sınava Katılan Öğrenci Sayısı ((?:\d+ ){4}\d+)", metin)
    if not s or not k:
        return None
    sira, kisi = [int(x) for x in s.group(1).split()], [int(x) for x in k.group(1).split()]
    return {
        ad: [sira[i], kisi[i]] for i, ad in enumerate(("sube", "kurum", "ilce", "il", "genel"))
    } | {"yuzdelik": _ondalik(s.group(2))}


def sayfa_ogrencisi(metin: str, tablolar: list, bolumler: list[list[dict]]) -> dict | None:
    """Tek öğrenci sayfasından JSON öğrenci kaydı."""
    baslik = ogrenci_basligi(metin)
    if baslik is None:
        return None
    satirlar = [r for t in tablolar for r in t]
    dersler = {}
    mat_toplam = None
    for r in satirlar:
        d = ders_satiri(r)
        if d and d[0] == "TYT Matematik":
            mat_toplam = d[1]
        elif d and d[0] == "TYT Türkçe":  # Türkçe'nin ayrı alt satırı yok; TYT Sosyal/Matematik/Fen toplam satırları atlanır
            dersler["Türkçe"] = d[1]
        elif d and not d[0].startswith("TYT"):
            dersler[d[0]] = d[1]
    # Matematiği tamamen boş bırakanın sayfasında alt satırlar yoktur; yalnız TYT Matematik toplamı (40 soru) vardır.
    if mat_toplam and mat_toplam["d"] == 0 and mat_toplam["y"] == 0 and not {"Matematik-1", "Geometri"} & dersler.keys():
        dersler["Matematik-1"] = {"d": 0, "y": 0, "b": 30, "net": 0.0}
        dersler["Geometri"] = {"d": 0, "y": 0, "b": 10, "net": 0.0}
    for ad in secmeli_ayikla(dersler):
        del dersler[ad]
    kazanimlar = []
    ciftler = _anahtar_cevaplar(satirlar)
    if len(bolumler) == len(DERS_ARALIKLARI):
        # Çift hangi teste ait: anahtarı bölümün kitapçık anahtarıyla birebir aynı olan.
        for kit, anahtar, cevap in ciftler:
            for bolum, aralik in zip(bolumler, DERS_ARALIKLARI):
                if anahtar != beklenen_anahtar(bolum, kit):
                    continue
                durum = cevap_durumlari(cevap, anahtar)
                if durum is not None:
                    kazanimlar.extend(kazanim_ozeti(bolum, kit, durum, aralik))
                break
        kazanimlar = [k for k in kazanimlar if k["ders"] in dersler]
    veri = {
        "toplam_net": baslik["toplam_net"],
        "dersler": {ad: v["net"] for ad, v in dersler.items()},
        "ders_dyb": {ad: [v["d"], v["y"], v["b"]] for ad, v in dersler.items()},
        "kazanimlar": kazanimlar,
    }
    if (sr := siralama(metin)) is not None:
        veri["siralama"] = sr
    return {
        "okul_no": baslik["okul_no"],
        "ad_soyad": baslik["ad_soyad"],
        "sinif": baslik["sinif"],
        "girdi": 1,
        "veri": veri,
        "analiz": "",
        "tavsiye": "",
    }


def sayfayi_ayir(kaynak: str, sayfa_no: int, hedef: str) -> None:
    """Kaynak PDF'in tek sayfasını (0 tabanlı) hedefe kaydeder; sayfa olduğu gibi (sıralamalar dahil) kalır."""
    import pymupdf

    with pymupdf.open(kaynak) as src, pymupdf.open() as out:
        out.insert_pdf(src, from_page=sayfa_no, to_page=sayfa_no)
        out.save(hedef)


def oku(yol: str, ad: str, pdf_klasoru: str) -> dict:
    import os

    import pdfplumber

    kurum_tablolari: list = []
    sayfalar = []
    with pdfplumber.open(yol) as pdf:
        for no, sayfa in enumerate(pdf.pages):
            metin = sayfa.extract_text() or ""
            if "KURUM SORU ANALİZİ" in metin:
                kurum_tablolari.extend(sayfa.extract_tables())
            elif "Sizin yeriniz" in metin:
                sayfalar.append((no, metin, sayfa.extract_tables()))
    bolumler = kurum_bolumleri(kurum_tablolari)
    ogrenciler = []
    atlanan = 0
    os.makedirs(pdf_klasoru, exist_ok=True)
    for no, metin, tablolar in sayfalar:
        s = sayfa_ogrencisi(metin, tablolar, bolumler)
        if s is None or "mezun" in s["sinif"].lower():
            atlanan += 1
            continue
        s["pdf_yol"] = os.path.abspath(os.path.join(pdf_klasoru, f"sayfa_{no + 1}.pdf"))
        sayfayi_ayir(yol, no, s["pdf_yol"])
        ogrenciler.append(s)
    kazanimli = sum(1 for s in ogrenciler if s["veri"]["kazanimlar"])
    print(
        f"bölüm={[len(b) for b in bolumler]} öğrenci={len(ogrenciler)} atlanan={atlanan}"
        f" kazanımı çıkan={kazanimli}",
        file=sys.stderr,
    )
    return {"ad": ad, "ogrenciler": ogrenciler}


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[2] != "--ad":
        print(__doc__)
        return 2
    belge = oku(argv[0], argv[3], argv[1] + "_sayfalar")
    with open(argv[1], "w", encoding="utf-8") as f:
        json.dump(belge, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
