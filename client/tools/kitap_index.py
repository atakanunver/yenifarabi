#!/usr/bin/env python3
"""
tools/kitap_index.py — MEB ders kitabı PDF'ini ünite/tema haritasına çevirir.

Kullanım:
    python tools/kitap_index.py <kitap.pdf> [--json cikti.json]

Neden gerekli:
Farabi'ye 200-400 sayfalık kitabın tamamını vermek hem pahalı hem zararlıdır
(uzun bağlam, öğretim kurallarına dikkati seyreltir). Bunun yerine o günkü
kazanıma karşılık gelen ÜNİTE/TEMA verilir. Bu betik, hangi sayfaların hangi
üniteye ait olduğunu koşan sayfa başlıklarından otomatik çıkarır.

Maarif Modeli notu: yeni kitaplar "Ünite" yerine "Tema" diyor (örn. matematik
9-10). Betik ikisini de tanır.

ÖNEMLİ — çıkarma yöntemi seçimi:
Betik her ünite için metin çıkarma kalitesini de ölçer. Matematik/fizik gibi
sembol yoğun kitaplarda PDF'in font kodlaması bozuk olduğu için metin çıkarma
notasyonu bozar (→ yerine ", ∈ yerine !, ∀ yerine 6, · yerine $). Bu tespit
edilirse ünite "gorsel" olarak işaretlenir: o ünite Farabi'ye METİN olarak
değil, PDF sayfaları olarak verilmelidir (Gemini'nin kendi belge okuması
notasyonu doğru çözer).

Sayfa metni `PyMuPDF` (fitz) ile çıkarılır, `pdfplumber` ile DEĞİL — bu betik
02.08.2026'da `pdfplumber`'dan taşındı: 161 MB'lık `tarih-10.pdf`'i indekslerken
ölçülen 3 art arda süreç ~4,6 GB RAM'e çıkıp bu makineyi (7,1 GB) neredeyse
takasa düşürdü. Kök neden `tools/kitap_metin.py`'nin modül dokümanındakiyle
AYNI: `pdfplumber` her sayfanın ayrıştırılmış nesnelerini süreç boyunca
önbellekte tutuyor. Bu betik yalnız düz metin (`extract_text`) okuyor —
`kitap_metin.py`'yi kurtaran `fitz.get_text()` burada da tam karşılığı.
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF gerekli:  pip install PyMuPDF")

try:
    import fcntl
except ImportError:      # Windows — kilitsiz devam (yalnız POSIX tahtalarda gerekli)
    fcntl = None


# "1.Ünite", "2. Tema", "3. TEMA:" hepsini yakalar
# Maarif Modeli kitaplarında tema adı başlığın İÇİNDE gelir:
#   "1. Tema / Sayılar"  ·  "1. TEMA: GEOMETRİK ŞEKİLLER"
# Eski kitaplarda ise ayrı sayfada: "2.Ünite" + "İslam'da İnanç Esasları"
BOLUM_RE = re.compile(
    r"^(\d+)\s*\.\s*(Ünite|Tema)\b\s*[:/]?\s*(.*)$", re.IGNORECASE)

# Bozuk sembol font imzaları: matematiksel ifade içinde olmaması gereken karakterler
BOZUK_KALIPLAR = [
    (re.compile(r"[A-Z]\"[A-Z]"),       "→ yerine \""),   # R"R  = R→R
    (re.compile(r"\s![A-Z]"),           "∈ yerine !"),    #  !R  = ∈R
    (re.compile(r"\b6[a-z],"),          "∀ yerine 6"),    # 6c,  = ∀c,
    (re.compile(r"[a-z]\$[a-z]"),       "· yerine $"),    # a$c  = a·c
]


def bozukluk_puani(metin: str) -> tuple[int, list[str]]:
    """Sembol font bozukluğunun kaç kez göründüğünü ve türlerini döndürür."""
    toplam, turler = 0, []
    for kalip, ad in BOZUK_KALIPLAR:
        n = len(kalip.findall(metin))
        if n:
            toplam += n
            turler.append(f"{ad} ({n})")
    return toplam, turler


def indexle(pdf_yolu: Path) -> dict:
    bolumler: dict[int, dict] = {}
    son_no = None
    sayfa_sayisi = 0

    with fitz.open(str(pdf_yolu)) as pdf:
        sayfa_sayisi = pdf.page_count
        for i, sayfa in enumerate(pdf, start=1):
            try:
                # sort=True ŞART: bu betik ünite/tema başlığını sayfanın
                # İLK SATIRINDAN okuyor (baslik = ilk satır). fitz'in
                # varsayılan (sort=False) blok sırası PDF'in dahili nesne
                # sırasını izliyor — birçok kitapta sayfa numarası (üstbilgi/
                # kenar boşluğu) başlıktan ÖNCE geliyor, bu yüzden "1. Tema"
                # hiç ilk satır olmuyordu. Ölçüldü (02.08.2026): sort=False
                # ile 12 kitaptan yalnızca 3'ünde bölüm tespit ediliyordu
                # (biyoloji-9 dahil SIFIR); sort=True (üstten alta, soldan
                # sağa konum sıralaması) ile 9 kitapta iyileşme, HİÇBİR
                # kitapta gerileme yok — pdfplumber'ın eski (doğru çalışan)
                # okuma sırasına en yakın seçenek bu.
                metin = (sayfa.get_text(sort=True) or "").strip()
            except Exception:
                metin = ""
            baslik = metin.split("\n")[0].strip() if metin else ""

            m = BOLUM_RE.match(baslik)
            if m:
                son_no = int(m.group(1))
                tur = m.group(2).title()
                icerik_ad = m.group(3).strip(" :/-")
            if son_no is None:
                continue                      # ön kapak, künye, İstiklal Marşı vb.

            b = bolumler.setdefault(son_no, {
                "no": son_no, "tur": "Ünite", "ad": "",
                "ilk_sayfa": i, "son_sayfa": i,
                "karakter": 0, "bozuk": 0, "bozukluk_turleri": {},
                "_basliklar": {},
            })
            if m:
                b["tur"] = tur
                if icerik_ad:            # "1. Tema / Sayılar" -> "Sayılar"
                    b["_basliklar"][icerik_ad] = b["_basliklar"].get(icerik_ad, 0) + 10
            # Ünite adı: aralıktaki en sık koşan başlık (aşağıda seçilir).
            # Bölüm ilk sayfası dekoratif fontla basıldığı için ("AAllllaahh")
            # ilk gördüğümüzü almak yanlış sonuç veriyor.
            if baslik and not BOLUM_RE.match(baslik):
                b["_basliklar"][baslik] = b["_basliklar"].get(baslik, 0) + 1

            b["son_sayfa"] = i
            b["karakter"] += len(metin)
            puan, turler = bozukluk_puani(metin)
            b["bozuk"] += puan
            for t in turler:
                tur_ad = t.split(" (")[0]
                b["bozukluk_turleri"][tur_ad] = b["bozukluk_turleri"].get(tur_ad, 0) + 1

    for b in bolumler.values():
        # En sık koşan başlık = ünite adı. Tekrar eden harfli (dekoratif font)
        # başlıkları ele: "AAllllaahh" gibi.
        adaylar = [(n, ad) for ad, n in b.pop("_basliklar", {}).items()
                   if not re.search(r"(.)\1(.)\2", ad)]
        b["ad"] = max(adaylar)[1] if adaylar else b.get("ad", "")
        b["sayfa_sayisi"] = b["son_sayfa"] - b["ilk_sayfa"] + 1
        b["tahmini_token"] = b["karakter"] // 4
        b["bozukluk_turleri"] = [f"{k} ×{v}" for k, v in sorted(b["bozukluk_turleri"].items())]
        # Kalibrasyon (din9 / mat9 / mat10 ölçümü): düzyazı kitapta bu
        # kalıplar SIFIR kez görülüyor, matematikte 78-125 kez. Yani sinyal
        # ikili — oran eşiği değil, varlık kontrolü doğru olan.
        # 3'lük taban, rastlantısal eşleşmeye karşı emniyet payı.
        b["yontem"] = "gorsel" if b["bozuk"] >= 3 else "metin"

    return {
        "dosya": pdf_yolu.name,
        "sayfa_sayisi": sayfa_sayisi,
        "bolumler": [bolumler[k] for k in sorted(bolumler)],
    }


DERS_RE = re.compile(r"^(.*?)[-_]?(\d{1,2})(?:[-_](\d))?$")


def kitap_kimligi(ad: str) -> dict:
    """
    Dosya adından ders/sınıf/cilt çıkar.
      matematik_9.pdf        -> matematik, 9, cilt 1
      matematik_9_2.pdf      -> matematik, 9, cilt 2
      din-kulturu-...-9.pdf  -> din kulturu ..., 9, cilt 1
    """
    kok = ad[:-4] if ad.lower().endswith(".pdf") else ad
    m = DERS_RE.match(kok)
    if not m:
        return {"ders": kok.replace("-", " ").replace("_", " ").strip(), "sinif": None, "cilt": 1}
    ders, sinif, cilt = m.groups()
    return {
        "ders": ders.replace("-", " ").replace("_", " ").strip().lower(),
        "sinif": int(sinif),
        "cilt": int(cilt) if cilt else 1,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="MEB ders kitabını ünite/tema haritasına çevirir.")
    ap.add_argument("pdf", type=Path, help="PDF dosyası ya da kitaplar klasörü")
    ap.add_argument("--json", type=Path, help="Haritayı JSON olarak kaydet")
    a = ap.parse_args()

    if not a.pdf.exists():
        sys.exit(f"Bulunamadı: {a.pdf}")

    # Aynı çıktıya iki süreç birden yazmasın — ui.py'nin açılış kontrolü
    # (_kitaplar_json_guncelle) her MainWindow kurulduğunda bu betiği tetikler;
    # kilitsizken art arda tetiklenen birden çok süreç aynı kitaplar/ klasörünü
    # paralel taramış ve ölçülen 4,6 GB RAM ile makineyi takasa düşürmüştü —
    # tools/kitap_metin.py'deki aynı gerekçeyle aynı kilit deseni.
    _kilit_tut = None
    if a.json and fcntl is not None:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        kilit_dosyasi = open(a.json.parent / f".{a.json.stem}.lock", "w")
        try:
            fcntl.flock(kilit_dosyasi, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _kilit_tut = kilit_dosyasi          # süreç bitene kadar açık tut
        except OSError:
            sys.exit(f"Bu hedef için başka bir indeksleme süreci zaten çalışıyor "
                     f"({a.json}), çıkılıyor.")

    # Klasör verildiyse tüm PDF'leri indeksleyip toplu harita üret
    if a.pdf.is_dir():
        kitaplar = []
        for pdf in sorted(a.pdf.glob("*.pdf")):
            print(f"  … {pdf.name}")
            try:
                d = indexle(pdf)
            except Exception as e:
                print(f"    ✖ {e}")
                continue
            d.update(kitap_kimligi(pdf.name))
            d["yol"] = str(pdf)
            kitaplar.append(d)
            for b in d["bolumler"]:
                isaret = "⚠" if b["yontem"] == "gorsel" else " "
                print(f"    {isaret}{b['no']}. {b['tur']:<5} s.{b['ilk_sayfa']:3d}-{b['son_sayfa']:3d}  {b['ad'][:38]}")
        toplu = {"kitaplar": kitaplar}
        if a.json:
            a.json.parent.mkdir(parents=True, exist_ok=True)
            a.json.write_text(json.dumps(toplu, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"\n{len(kitaplar)} kitap indekslendi → {a.json}")
        else:
            print(f"\n{len(kitaplar)} kitap indekslendi (kaydetmek için --json verin)")
        return

    sonuc = indexle(a.pdf)
    print(f"\n{sonuc['dosya']} — {sonuc['sayfa_sayisi']} sayfa, "
          f"{len(sonuc['bolumler'])} bölüm\n")
    print(f"{'':2} {'sayfa':>11}  {'token':>7}  {'yöntem':7}  ad")
    print("-" * 78)
    for b in sonuc["bolumler"]:
        isaret = "⚠" if b["yontem"] == "gorsel" else " "
        print(f"{isaret}{b['no']}. {b['tur']:<5} "
              f"{b['ilk_sayfa']:3d}-{b['son_sayfa']:3d}  "
              f"{b['tahmini_token']:7d}  {b['yontem']:7}  {b['ad'][:34]}")

    gorsel = [b for b in sonuc["bolumler"] if b["yontem"] == "gorsel"]
    if gorsel:
        print(f"\n⚠  {len(gorsel)} bölümde sembol font bozukluğu var — "
              f"bunlar Farabi'ye PDF sayfası olarak verilmeli, metin olarak DEĞİL.")
        for b in gorsel:
            print(f"   {b['no']}. {b['tur']}: {', '.join(b['bozukluk_turleri'])}")

    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(sonuc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nKaydedildi: {a.json}")


if __name__ == "__main__":
    main()
