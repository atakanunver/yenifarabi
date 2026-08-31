"""
benchmark/ogretim_program_parse.py — /mnt/farabi-data/farabi/ogretim_program/
altındaki MEB "Türkiye Yüzyılı Maarif Modeli" ders öğretim programı
PDF'lerinden kazanım (öğrenme çıktısı) kod+metin çiftlerini çıkaran saf
ayrıştırma mantığı. DB/dosya I/O YOK (kazanim_test_parse.py'nin deseniyle
tutarlı) — `ogretim_program_yukle.py` bu modülü import eder.

PDF YAPISI (2026-08-31, fizik.pdf'te pdfplumber/PyMuPDF ile doğrulandı,
9-12. sınıfların TAMAMI, diğer 16 dosyanın YALNIZCA bir kısmı örneklendi):

- Her sayfanın üstünde "<DERS ADI> DERSİ ÖĞRETİM PROGRAMI" satırı tekrarlıyor
  — ders adını buradan alıyoruz, dosya adından DEĞİL (dosya adları tutarsız:
  "fizik.pdf" vs "fizikdöp.pdf" gibi aynı ders için birden fazla dosya var).
- Sınıf düzeyi tek başına bir satırda geçiyor: "12. SINIF" (metinde ünite
  başlığından ÖNCE ya da SONRA görünebiliyor, sıra dosyaya göre değişiyor —
  bu yüzden metin boyunca DURUM olarak takip ediliyor, konumla değil).
- Ünite başlığı: "N. ÜNİTE: AD" — kendi satırında.
- Her ünitenin "ÖĞRENME ÇIKTILARI VE SÜREÇ BİLEŞENLERİ" bölümünde kazanım
  kodu+başlığı: "FİZ.12.1.1. Torkun matematiksel modeline yönelik tümeva-
  rımsal akıl yürütebilme" biçiminde. İLK kazanım kodu genelde "VE SÜREÇ
  BİLEŞENLERİ" etiketiyle AYNI satırda geliyor (satır BAŞINDA değil) —
  bu yüzden kod deseni satırın HERHANGİ bir yerinde aranıyor (^ ile değil).
  Sonraki kodlar kendi satırlarında.
- Başlıktan sonra "a) ... b) ... c) ..." harfli süreç bileşenleri geliyor —
  bu sürüm bunları BİLİNÇLİ OLARAK atlıyor (yalnızca kod+başlık cümlesi
  alınıyor), ayrıntı için "ÖĞRENME-ÖĞRETME YAŞANTILARI" bölümüne kadar uzayan
  çok daha büyük bir pedagojik anlatı var — kazanım REFERANS metni için
  başlık cümlesi yeterli, tamamı ayrı ve çok daha büyük bir iş.
"""

import re

_DERS_ADI = re.compile(r"^([A-ZÇĞİİÖŞÜ .]+) DERSİ (?:\(.*?\)\s*)?ÖĞRETİM PROGRAMI$")
_SINIF_SATIRI = re.compile(r"^(\d{1,2})\.\s*SINIF$")
_UNITE_SATIRI = re.compile(r"^(\d{1,2})\.\s*ÜNİTE:\s*(.+)$")
_KOD_DESENI = re.compile(r"([A-ZÇĞİİÖŞÜ]{2,6}(?:\.\d{1,2}){3})\.\s+(.*)$")
_MADDE_SATIRI = re.compile(r"^[a-zçğıiöşü]\)\s")


def _turkce_title(s: str) -> str:
    """str.title() Türkçe İ/I'yı bozar ('FİZİK' -> 'Fi̇zi̇k', birleşik nokta
    karakteriyle). Türkçe büyük/küçük harf eşlemesini elle yapar."""
    kucuk_ozel = {"İ": "i", "I": "ı"}
    buyuk_ozel = {"i": "İ", "ı": "I"}
    kucuk = "".join(kucuk_ozel.get(c, c.lower()) for c in s)
    kelimeler = []
    for kelime in kucuk.split(" "):
        if not kelime:
            continue
        if "." in kelime.rstrip("."):
            # "t.c." gibi kısaltmalar — tamamı büyük kalır
            kelimeler.append(kelime.upper())
            continue
        ilk = buyuk_ozel.get(kelime[0], kelime[0].upper())
        kelimeler.append(ilk + kelime[1:])
    return " ".join(kelimeler)


def ders_adi_cikar(tam_metin: str) -> str | None:
    """Her sayfada tekrarlanan '<DERS> DERSİ ÖĞRETİM PROGRAMI' başlığından
    ders adını çıkarır (Title Case). Dosya adından DEĞİL — bkz. modül
    docstring'i, aynı ders için birden fazla tutarsız dosya adı var."""
    for satir in tam_metin.splitlines():
        m = _DERS_ADI.match(satir.strip())
        if m:
            return _turkce_title(m.group(1).strip())
    return None


def kazanimlari_ayir(tam_metin: str) -> list[dict]:
    """Tüm PDF metnini (sayfalar birleştirilmiş) kazanım listesine ayırır.
    Her öge: {"kod": str, "sinif": int|None, "unite": str|None, "metin": str}.
    Süreç bileşenleri (a/b/c maddeleri) dahil edilmez — yalnızca kod+başlık."""
    sinif: int | None = None
    unite: str | None = None
    sonuc: list[dict] = []
    guncel: dict | None = None  # üzerinde toplanan kazanım

    def bitir():
        if guncel is not None and guncel["metin"].strip():
            guncel["metin"] = guncel["metin"].strip()
            sonuc.append(guncel)

    for satir in tam_metin.splitlines():
        satir = satir.strip()
        if not satir:
            continue

        m_sinif = _SINIF_SATIRI.match(satir)
        if m_sinif:
            bitir()
            guncel = None
            sinif = int(m_sinif.group(1))
            continue

        m_unite = _UNITE_SATIRI.match(satir)
        if m_unite:
            bitir()
            guncel = None
            unite = m_unite.group(2).strip()
            continue

        if _MADDE_SATIRI.match(satir):
            # süreç bileşeni (a/b/c) başladı — kazanım başlığı burada BİTER
            # (bilinçli olarak atlanır, bkz. docstring), sonrasındaki dev
            # pedagojik anlatıya (ÖĞRENME-ÖĞRETME YAŞANTILARI vb.) hiç girilmez
            bitir()
            guncel = None
            continue

        m_kod = _KOD_DESENI.search(satir)
        if m_kod:
            bitir()
            guncel = {
                "kod": m_kod.group(1),
                "sinif": sinif,
                "unite": unite,
                "metin": m_kod.group(2).strip(),
            }
            continue

        if guncel is not None:
            # başlık birden fazla satıra sarkmış olabilir — "a)" gelene kadar ekle
            guncel["metin"] += " " + satir

    bitir()

    # Filtre 1: "N. SINIF" satırından ÖNCE (içindekiler/kapak sayfaları)
    # bulunan hayalet eşleşmeler — sinif'i olmayan bir kazanım kullanılamaz.
    sonuc = [k for k in sonuc if k["sinif"] is not None]

    # Filtre 2: kod deseni ("XX.N.N.N") yalnızca öğrenme çıktısı kodlarını
    # değil, aynı belgedeki "KB.2.16.1" (kavramsal beceri) gibi başka
    # kodlama şemalarını da yakalıyor — 2026-08-31'de fizik.pdf'te bulundu.
    # Öğrenme çıktısı kodları belge başına TEK bir önekle gelir (ör. "FİZ")
    # ve sayıca ezici çoğunluktadır; en sık geçen önek dışındakiler atılır.
    if sonuc:
        onekler = [k["kod"].split(".", 1)[0] for k in sonuc]
        baskin_onek = max(set(onekler), key=onekler.count)
        sonuc = [k for k in sonuc if k["kod"].split(".", 1)[0] == baskin_onek]

    return sonuc
