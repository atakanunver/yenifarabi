#!/usr/bin/env python3
"""
tools/kitap_metin.py — Ders kitabı PDF'lerini METNE çevirir (offline, API yok)

Karar: sanal öğretmen yalnız düz metin kullanacak. Sayfaların Gemini'ye
görüntü olarak okutulması (eski `gorsel` yolu) kaldırıldı — hem kota harcıyor
hem de ders ortasında saniyeler sürüyordu (ölçüm: soğuk çağrı 20 sn'de zaman
aşımı, ısıtma 57,1 sn). Metin çıkarma tamamen yerel, sıfır API çağrısı.

Sayfa metni `PyMuPDF` (fitz) ile çıkarılır, `pdfplumber` ile DEĞİL — burada
kasıtlı. `pdfplumber` her sayfanın ayrıştırılmış nesnelerini (char/rect/görsel)
süreç boyunca önbellekte tutuyor; 300+ sayfalık, görsel ağırlıklı bir kitapta
(tarih-10.pdf, 161 MB) bu RAM'i 5+ GB'a çıkarıp bu makinede (7,1 GB) OOM'a
düşürdü — ölçüldü, `sayfa.close()` eklemek bile yetmedi hızlı kitaplıkta.
`fitz.get_text()` aynı kitabı sabit bellekle, saniyeler içinde bitiriyor.
`pdfplumber` diğer araçlarda (file_processor, ders_icerigi, kitap_index,
yks_metin) hâlâ kullanımda — yalnız burada, büyük kitap taramasında
değiştirildi.

Bedeli: MEB matematik/fizik kitaplarının sembol fontu bozuk kodlanmış. Bu
betik iki katmanlı davranır ve bu ayrım bilinçlidir:

  KATMAN 1 — TEK ANLAMLI, otomatik onarılır
      R"R  -> R→R        (matematik_9'da 28 kez)
      x!R  -> x ∈ R      (41 kez; a!R, b!R aynı)
      6x   -> ∀x         (33 kez; 6a, 6m, 6k aynı)

  KATMAN 2 — ÇOK ANLAMLI, ASLA TAHMİN EDİLMEZ, yalnızca sayılır
      #    ≤ mi ≥ mi ≠ mi belli değil ("90 # x # 130" ile "x # 0" farklı yön)
      $    · mi ≥ mi belli değil

Bir eşitsizliğin yönünü yanlış öğretmek, sembolü hiç göstermemekten kötüdür.
Katman 2 işaretleri sayfa başına sayılır; `ders_icerigi` bu sayıyı görüp modele
"bu sayfadaki semboller şüpheli, formülü sembol sembol okuma, sözle anlat"
uyarısını ekler.

GÖRSEL OCR YEDEĞİ — sayfa GÖVDESİNİN üzerine hiç yazmaz, yalnızca görsel
dikdörtgenleri hedefler. Haritalar, tablo-görselleri ve diyagramlar metin
katmanı taşımaz; `fitz.get_text()` onları görmez. Her sayfada `get_images()`
ile bulunan büyük görseller (<150×150 px ikon/logo elenir) tek tek kırpılıp
`tesseract` ile OCR'lanır, sonuç gövde metnine EKLENİR (üzerine yazılmaz) ve
"[SAYFADAKİ GÖRSEL/HARİTA METNİ — OCR ile okundu, hatalı olabilir]" etiketiyle
ayrılır. KASITLI olarak dar: aynı OCR'ı tüm SAYFAYI yeniden okuyacak şekilde
zaten METİN İÇEREN bir kitapta (tarih-10.pdf) denedik — sonuç fitz'in zaten
çıkardığından daha KÖTÜYDÜ (tablo çerçevelerini "eT3.", "ee ee ee" gibi
gürültüye çeviriyor). Bu yüzden gövde metni bir daha OCR'lanmaz, yalnızca
görsel alanlar hedeflenir. Aynı mekanizma taranmış (metin katmanı hiç olmayan)
bir sayfayı da ayrıca kod yazmadan kurtarır — öyle bir sayfada gövde tek büyük
bir görseldir. `tesseract`/`tesseract-ocr-tur` sistemde yoksa (apt paketi, pip
değil) sessizce atlanır — kitap yine dönüşür, o görseller atlanır.

Kullanım:
    python tools/kitap_metin.py kitaplar/ --json icerik/metin
    python tools/kitap_metin.py kitaplar/matematik_9.pdf --json icerik/metin
    python tools/kitap_metin.py kitaplar/ --json icerik/metin --ocr-yok

Varsayılan olarak hedefte zaten json'u bulunan bir kitap atlanır (--zorla ile
yeniden işlenir). Bu, betiği her açılışta bütün klasöre çağırmayı ucuz yapar:
yalnızca yeni eklenen PDF işlenir — bkz. ui.py `_icerik_hazirlik_kontrolu`.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import fcntl
except ImportError:      # Windows — kilitsiz devam (yalnız POSIX tahtalarda gerekli)
    fcntl = None

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

OCR_SAYFA_ZAMAN_ASIMI_SN = 120   # tek sayfa OCR'ı bu süreyi aşarsa vazgeç, kitabı bekletme

# ── Katman 1: tek anlamlı onarımlar ────────────────────────────────────────
# Her biri en az iki kitapta ya da onlarca kez doğrulandı.
ONARIMLAR = [
    (re.compile(r'R"R'),                 "R→R"),      # fonksiyon: f: R→R
    (re.compile(r'\b([a-zA-Z])!R\b'),    r"\1 ∈ R"),  # x!R  -> x ∈ R
    (re.compile(r'\b6([a-zA-Z])\b'),     r"∀\1"),     # 6x   -> ∀x
]

# ── Katman 2: çok anlamlı — sayılır, DEĞİŞTİRİLMEZ ─────────────────────────
SUPHELI = re.compile(r'[a-zA-Z0-9]\s?[#$]\s?[a-zA-Z0-9]')


def metni_onar(ham: str) -> tuple[str, int]:
    """Katman 1'i uygula, katman 2'yi say. (metin, şüpheli_sayısı)"""
    metin = ham or ""
    for desen, yerine in ONARIMLAR:
        metin = desen.sub(yerine, metin)
    return metin, len(SUPHELI.findall(metin))


GORSEL_MIN_BOYUT = 150     # px — bundan küçük görsel (ikon/logo/süsleme) atlanır
GORSEL_MIN_METIN = 20      # karakter — bundan kısa OCR çıktısı gürültü sayılır, atılır


def _ocr_araclari_var() -> bool:
    return shutil.which("tesseract") is not None


def _pixmap_ocr(pix, dil: str = "tur+eng") -> str:
    """Bir fitz pixmap'ı `tesseract` ile OCR'lar. Hata/zaman aşımında
    sessizce boş döner — çağıran zaten OCR'ı bir kurtarma denemesi olarak
    ele alıyor, kitabın tamamını bekletmez."""
    with tempfile.TemporaryDirectory(prefix="farabi_ocr_") as tmp_str:
        png = Path(tmp_str) / "sayfa.png"
        try:
            pix.save(str(png))
            r = subprocess.run(
                ["tesseract", str(png), "stdout", "-l", dil],
                capture_output=True, text=True, timeout=OCR_SAYFA_ZAMAN_ASIMI_SN,
            )
            return r.stdout.strip()
        except Exception:
            # fitz'in kendi hata sınıfları (FzErrorArgument vb.) dahil —
            # bozuk/aşırı ölçekli bir görsel tüm kitabın dönüşümünü
            # düşürmesin, o görsel atlanır.
            return ""


def _sayfa_gorsellerini_oku(sayfa) -> str:
    """
    Sayfadaki büyük görselleri (harita, tablo-görsel, diyagram, taranmış
    tam sayfa) tek tek kırpıp OCR'lar. `sayfa.get_text()`'in zaten doğru
    çıkardığı gövde metnini YENİDEN OKUMAZ — yalnız görsel dikdörtgenleri
    hedefler, böylece iyi metnin üzerine asla yazmaz (modül dokümanındaki
    tarih-10.pdf ölçümü: tam sayfa OCR var olan metni bozuyordu).

    Aynı mekanizma, taranmış (metin katmanı hiç olmayan) bir sayfayı da
    ayrıca ele almadan kurtarır: böyle bir sayfada gövde metni PDF'de tek
    büyük bir görseldir, döngü onu da yakalar.
    """
    parcalar = []
    gorulen_xref = set()
    for img in sayfa.get_images(full=True):
        xref = img[0]
        if xref in gorulen_xref:
            continue
        gorulen_xref.add(xref)
        try:
            dikdortgenler = sayfa.get_image_rects(xref)
        except Exception:
            continue
        for r in dikdortgenler:
            if r.width < GORSEL_MIN_BOYUT or r.height < GORSEL_MIN_BOYUT:
                continue
            try:
                pix = sayfa.get_pixmap(clip=r, dpi=300)
            except Exception:
                continue
            metin = _pixmap_ocr(pix)
            if len(metin) >= GORSEL_MIN_METIN:
                parcalar.append(metin)
    return "\n".join(parcalar)


def kitabi_cevir(pdf_yolu: Path, hedef_dizin: Path, ocr_aktif: bool = True) -> dict:
    import fitz  # PyMuPDF — bkz. modül dokümanı: pdfplumber yerine, OOM ölçümü

    sayfalar: dict[str, dict] = {}
    supheli_toplam = 0
    bos_sayfa = 0
    gorsel_ocr_sayfa = 0

    ocr_kullanilabilir = ocr_aktif and _ocr_araclari_var()
    if ocr_aktif and not ocr_kullanilabilir:
        print("    (Görsel OCR kapalı: tesseract sistemde bulunamadı — "
              "sudo apt install tesseract-ocr tesseract-ocr-tur)")

    with fitz.open(str(pdf_yolu)) as pdf:
        for i, sayfa in enumerate(pdf, start=1):
            try:
                ham = sayfa.get_text()
            except Exception as e:
                print(f"    s.{i}: okunamadı ({type(e).__name__})")
                ham = ""
            metin, supheli = metni_onar(ham)

            gorsel_metin = _sayfa_gorsellerini_oku(sayfa) if ocr_kullanilabilir else ""

            if not metin.strip() and not gorsel_metin:
                bos_sayfa += 1
                continue

            if gorsel_metin:
                metin = (metin.strip() + "\n\n[SAYFADAKİ GÖRSEL/HARİTA METNİ — OCR "
                          "ile okundu, hatalı olabilir, temkinli kullan]\n"
                          + gorsel_metin).strip()
                gorsel_ocr_sayfa += 1

            kayit = {"metin": metin, "supheli": supheli}
            if gorsel_metin:
                kayit["gorsel_ocr"] = True
            sayfalar[str(i)] = kayit
            supheli_toplam += supheli

    ozet = {
        "kitap":            pdf_yolu.name,
        "sayfa_sayisi":     len(sayfalar),
        "bos_sayfa":        bos_sayfa,
        "gorsel_ocr_sayfa": gorsel_ocr_sayfa,
        "supheli_sembol":   supheli_toplam,
        "sayfalar":         sayfalar,
    }
    hedef_dizin.mkdir(parents=True, exist_ok=True)
    hedef = hedef_dizin / f"{pdf_yolu.stem}.json"
    hedef.write_text(json.dumps(ozet, ensure_ascii=False), encoding="utf-8")

    boyut = hedef.stat().st_size / 1024
    ocr_notu = f" · {gorsel_ocr_sayfa} sayfada görsel OCR" if gorsel_ocr_sayfa else ""
    print(f"  {pdf_yolu.name:34} {len(sayfalar):4} sayfa · "
          f"{bos_sayfa:3} boş{ocr_notu} · {supheli_toplam:4} şüpheli sembol · "
          f"{boyut:7.0f} KB")
    if supheli_toplam:
        print(f"       ⚠ {supheli_toplam} yerde '#' ya da '$' var; yönü "
              f"belli olmadığı için DEĞİŞTİRİLMEDİ. Farabi bu sayfalarda "
              f"formülü sembol sembol okumayacak, sözle anlatacak.")
    return ozet


def main() -> int:
    ap = argparse.ArgumentParser(description="Ders kitabı PDF -> metin (API yok)")
    ap.add_argument("kaynak", help="PDF dosyası ya da klasör")
    ap.add_argument("--json", default="icerik/metin",
                    help="Hedef klasör (varsayılan: icerik/metin)")
    ap.add_argument("--zorla", action="store_true",
                    help="Zaten dönüştürülmüş (hedefte aynı adla json'u olan) "
                         "kitapları da yeniden işle. Varsayılan: atla — bu "
                         "betiğin her açılışta çağrılabilmesinin (yalnız yeni "
                         "kitabı işlemesi) dayanağı.")
    ap.add_argument("--ocr-yok", action="store_true",
                    help="Metinsiz sayfalar için OCR yedeğini kapat (yalnız "
                         "fitz/pdfplumber'ın bulduğu metinle yetin).")
    a = ap.parse_args()

    kaynak = Path(a.kaynak)
    hedef  = BASE_DIR / a.json if not Path(a.json).is_absolute() else Path(a.json)
    hedef.mkdir(parents=True, exist_ok=True)

    # Aynı hedefe iki dönüştürme süreci birden yazarsa (ör. uygulama iki kez
    # açılmış, ya da HUD'daki düğme ve açılış kontrolü çakışmış) json'lar
    # yarım yamalak üzerine yazılabilir ve bellek ikiye katlanır — ölçüldü:
    # dört eşzamanlı süreç 7,1 GB'lık makineyi OOM'a düşürdü. Hedef başına
    # tek yazar kilidi, ikinci süreç sessizce çıkar.
    _kilit_tut = None
    if fcntl is not None:
        kilit_dosyasi = open(hedef / ".kitap_metin.lock", "w")
        try:
            fcntl.flock(kilit_dosyasi, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _kilit_tut = kilit_dosyasi          # süreç bitene kadar açık tut
        except OSError:
            print(f"Bu hedef için başka bir dönüştürme süreci zaten çalışıyor "
                  f"({hedef}), çıkılıyor.")
            return 0

    if kaynak.is_dir():
        pdfler = sorted(kaynak.glob("*.pdf"))
    elif kaynak.exists():
        pdfler = [kaynak]
    else:
        print(f"Bulunamadı: {kaynak}")
        return 1

    if not pdfler:
        print(f"{kaynak} içinde PDF yok.")
        return 1

    if not a.zorla:
        atlanan = [p for p in pdfler if (hedef / f"{p.stem}.json").exists()]
        if atlanan:
            print(f"{len(atlanan)} kitap zaten dönüştürülmüş, atlanıyor "
                  f"(yeniden işlemek için --zorla):")
            for p in atlanan:
                print(f"  = {p.name}")
            pdfler = [p for p in pdfler if p not in atlanan]
        if not pdfler:
            print("Dönüştürülecek yeni kitap yok.")
            return 0

    print(f"{len(pdfler)} kitap metne çevriliyor (yerel, API çağrısı yok)…\n")
    toplam_supheli = 0
    for pdf in pdfler:
        try:
            ozet = kitabi_cevir(pdf, hedef, ocr_aktif=not a.ocr_yok)
            toplam_supheli += ozet["supheli_sembol"]
        except Exception as e:
            print(f"  ✖ {pdf.name}: {type(e).__name__}: {str(e)[:90]}")

    print(f"\nBitti → {hedef}")
    if toplam_supheli:
        print(f"Toplam {toplam_supheli} şüpheli sembol. Bunlar tahmin "
              f"edilmedi: bir eşitsizliğin yönünü yanlış öğretmek, sembolü "
              f"hiç göstermemekten kötüdür.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
