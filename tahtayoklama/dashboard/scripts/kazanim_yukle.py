#!/usr/bin/env python3
"""dashboard/scripts/kazanim_yukle.py — yıllık planlardan (YILLIK PLANLAR
2026_2027) her (sınıf düzeyi, ders) için HAFTALIK kazanımı çıkarıp
tahtayoklama/data/kazanimlar.json'u üretir. Pano/tahta, ders adının altına
"bu haftanın kazanımı" tek satırını bu dosyadan basar.

Çalıştırma — DİKKAT: dashboard venv'i DEĞİL, server venv'i
----------------------------------------------------------
python-docx / openpyxl / pdfplumber dashboard'un venv'inde YOK (pip install
yapılmaz); server venv'inde var:

    /home/ata/farabi/server/venv/bin/python -I \\
        tahtayoklama/dashboard/scripts/kazanim_yukle.py \\
        [--plan-dir DİZİN] [--cikti YOL]

Varsayılan plan dizini /mnt/farabi-data/farabi/YILLIK PLANLAR 2026_2027,
varsayılan çıktı tahtayoklama/data/kazanimlar.json. İdempotenttir (aynı
girdi → bayt bayt aynı çıktı, zaman damgası yok). Yalnızca çıktı dosyasını
yazar (geçici dosya + os.replace); servis yeniden başlatmaz, hiçbir şey
buluta göndermez.

Çıktı şeması
------------
    {"_kaynak": "...", "_uretim_araci": "...",
     "haftalar":   {"1": "2026-09-14", ...},       # plan hafta no -> o haftanın PAZARTESİ'si
     "kazanimlar": {"9": {"matematik": {"1": "9.1.1. ..."}}}}

Takvim (haftalar) planların KENDİ tarihli hafta etiketlerinden ("4. Hafta:
5-9 Ekim", "4.HAFTA(05-11)" ...) çıkarılır; ara tatil/yarıyıl tatili
yüzünden hafta numaraları takvimde ardışık değildir. Planlar arası
anlaşmazlıkta çoğunluk kazanır, anlaşmazlık raporda yazılır. Satırlar,
etiketindeki tarih takvimde varsa o tarihin haftasına, yoksa etiketteki hafta
numarasına yazılır (ÇAĞDAŞ planında yalnızca tarih var).

Dosya -> (düzey, ders) eşlemesi AÇIK bir tablodur (ESLEME / ATLANAN); tabloda
olmayan dosya raporda "eşlenmemiş" olarak listelenir. Kazanım sütunu
başlığa göre bulunur (ÖĞRENME ÇIKTILARI / KAZANIM / LEARNING OUTCOMES ...,
"KAZANIM AÇIKLAMASI" hariç). Haftada birden çok kazanım varsa İLKİ alınır;
boşluklar tek boşluğa indirilir, en çok 200 karakter (kelime sınırında
kesilip "…" eklenir). Kazanımsız hafta (tatil, sınav, boş) anahtar olarak
YER ALMAZ — içerik uydurulmaz.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
TAHTAYOKLAMA_DIR = DASHBOARD_DIR.parent
VARSAYILAN_PLAN_DIZINI = Path("/mnt/farabi-data/farabi/YILLIK PLANLAR 2026_2027")
VARSAYILAN_CIKTI = TAHTAYOKLAMA_DIR / "data" / "kazanimlar.json"
URETIM_ARACI = "tahtayoklama/dashboard/scripts/kazanim_yukle.py"

OKUL_YILI_BASLANGICI = date(2026, 9, 14)  # 1. hafta Pazartesi
MAKS_UZUNLUK = 200
MIN_OY = 3  # bir takvim haftasını kabul etmek için en az plan sayısı
YOK_ALT_DIZIN = "ders programı"  # taranmaz

# --- Zaman çizelgesindeki ders adları: düzey -> dersler (TAM ve küçük harf) ---
GEREKLI = {
    9: ["almanca", "beden eğitimi", "biyoloji", "coğrafya",
        "din kültürü ve ahlak bilgisi", "fizik", "görsel sanatlar",
        "ingilizce", "kimya", "matematik",
        "sağlık bilgisi ve trafik kültürü", "tarih",
        "türk dili ve edebiyatı"],
    10: ["beden eğitimi", "biyoloji", "coğrafya",
         "din kültürü ve ahlak bilgisi", "felsefe", "fizik",
         "görsel sanatlar", "ingilizce", "kimya", "matematik",
         "ortak türk tarihi", "peygamberimizin hayatı", "tarih",
         "türk dili ve edebiyatı"],
    11: ["beden eğitimi", "bilişim teknolojileri ve yazılım", "biyoloji",
         "coğrafya", "din kültürü ve ahlak bilgisi", "felsefe", "fizik",
         "görsel sanatlar", "ingilizce", "kimya", "matematik",
         "matematik uygulamaları", "psikoloji", "tarih",
         "türk dili ve edebiyatı"],
    12: ["almanca", "beden eğitimi", "bilişim teknolojileri ve yazılım",
         "biyoloji", "coğrafya", "din kültürü ve ahlak bilgisi", "fizik",
         "ingilizce", "inkılap tarihi ve atatürkçülük", "kimya",
         "matematik", "türk dili ve edebiyatı",
         "çağdaş türk ve dünya tarihi"],
}

DKAB = "din kültürü ve ahlak bilgisi"
EDEB = "türk dili ve edebiyatı"
SAGLIK = "sağlık bilgisi ve trafik kültürü"
INKILAP = "inkılap tarihi ve atatürkçülük"
CAGDAS = "çağdaş türk ve dünya tarihi"

# (göreli yol, düzey, ders, sayfa [xlsx: sayfa adı; kelime-PDF: "s1-2" aralığı; None = tümü], not)
ESLEME = [
    ("almanca/9-sinif-almanca-mit-deutsch-a11-yillik-plan-ogretmenevrak-1788857208.docx", 9, "almanca", None, ""),
    ("almanca/12-sinif-almanca-deutsch-a12-yillik-plan-ogretmenevrak-1788857282.docx", 12, "almanca", None, ""),
    ("beden eğitimi 10 eksik/9-sinif-temel-spor-egitimi yıllık plan.docx", 9, "beden eğitimi", None,
     "9. sınıfta 'Beden Eğitimi' yerine 'Temel Spor Eğitimi' planı var (varsayım)"),
    ("beden eğitimi 10 eksik/11-sinif-beden-egitimi-ve-spor yıllık plan.docx", 11, "beden eğitimi", None, ""),
    ("beden eğitimi 10 eksik/12-sinif-beden-egitimi-ve-spor yıllık plan.docx", 12, "beden eğitimi", None,
     "iki 12. sınıf planından standart adlı olan seçildi"),
    ("biyoloji-sağlık/9-sinif-biyoloji-maarif-m-al-yillik-plan.docx", 9, "biyoloji", None, ""),
    ("biyoloji-sağlık/10-sinif-biyoloji-maarif-m-al-yillik-plan.docx", 10, "biyoloji", None, ""),
    ("biyoloji-sağlık/11-sinif-biyoloji-maarif-m-al-yillik-plan-.docx", 11, "biyoloji", None, ""),
    ("biyoloji-sağlık/12-sinif-biyoloji-al-ayse-merve-karakoc-yillik-plan-.docx", 12, "biyoloji", None, ""),
    ("biyoloji-sağlık/9-sinif-saglik-bilg-ve-trafik-kult-maarif-m-yillik-plan.docx", 9, SAGLIK, None, ""),
    ("coğrafya/9-sinif-cografya-maarif-m-al-yillik-plan-ogretmenevrak-1789111222.docx", 9, "coğrafya", None, ""),
    ("coğrafya/10-sinif-cografya-maarif-m-al-yillik-plan-ogretmenevrak-1789111198.docx", 10, "coğrafya", None, ""),
    ("coğrafya/11-sinif-cografya-maarif-m-al-4-saatlik-yillik-plan-ogretmenevrak-1789111163.docx", 11, "coğrafya", None, ""),
    ("coğrafya/12-sinif-cografya-al-4-saatlik-ozlem-arslan-yillik-plan-ogretmenevrak-1789111245.docx", 12, "coğrafya", None, ""),
    ("din kültürü/2026-2027dkab9_TYMM  (1).xlsx", 9, DKAB, None, ""),
    ("din kültürü/2026-2027dkab10_TYMM (1).xlsx", 10, DKAB, None, ""),
    ("din kültürü/2026-2027dkab11_TYMM 1.xlsx", 11, DKAB, None, ""),
    ("din kültürü/2026-2027dkab12 (1).xlsx", 12, DKAB, None, ""),
    ("din kültürü/2026-2027peygamberimizinhayati10_TYMM (2).xlsx", 10, "peygamberimizin hayatı", None, ""),
    ("edebiyat/9.SINIFLAR TDE YILLIK PLANI.docx", 9, EDEB, None, ""),
    ("edebiyat/10.sınıflar edebiyat.pdf", 10, EDEB, None, "2026-10-06: .doc yerine PDF konuldu"),
    ("edebiyat/11.SINIFLAR TDE YILLIK PLANI 2026 - 2027 (1).docx", 11, EDEB, None, ""),
    ("edebiyat/12.SINIFLAR TDE YILLIK PLANI.pdf", 12, EDEB, None, "2026-10-06: .doc yerine PDF konuldu"),
    ("fizik/9.sınıf fizik yıllık plan.docx", 9, "fizik", None, ""),
    ("fizik/10.sınıf fizik yıllık plan.docx", 10, "fizik", None, ""),
    ("fizik/11.sınıf fizik yıllık plan.docx", 11, "fizik", None, ""),
    ("görsel sanatlar/9-sinif-gorsel-sanatlar-maarif-m-yillik-plan-ogretmenevrak-1789636609.docx", 9, "görsel sanatlar", None, ""),
    ("görsel sanatlar/10-sinif-gorsel-sanatlar-maarif-m-yillik-plan-ogretmenevrak-1789636695.docx", 10, "görsel sanatlar", None, ""),
    ("görsel sanatlar/11-sinif-gorsel-sanatlar-cigdem-ince-yillik-plan-ogretmenevrak-1789636733.docx", 11, "görsel sanatlar", None,
     "iki 11. sınıf planı da kişi adlı; ogretmenevrak kaynaklı olan seçildi"),
    ("ingilizce/9.-Sinif-Ingilizce-Yillik-Plan-2026-2027-by-ingilizceciyiz.com_-1.docx", 9, "ingilizce", None, ""),
    ("ingilizce/10. SINIF İNGİLİZCE.docx", 10, "ingilizce", None, ""),
    ("ingilizce/26-27 11.sınıf yıllık plan.docx", 11, "ingilizce", None, ""),
    ("ingilizce/26-27 12. sınıf yıllık plan.docx", 12, "ingilizce", None, ""),
    ("kimya/9-sinif-kimya-maarif-m-al-yillik-plan-ogretmenevrak-1788776684.docx", 9, "kimya", None, ""),
    ("kimya/10-sinif-kimya-maarif-m-al-yillik-plan-ogretmenevrak-1788776742.docx", 10, "kimya", None, ""),
    ("kimya/11-sinif-kimya-maarif-m-al-yillik-plan-ogretmenevrak-1788776778.docx", 11, "kimya", None, ""),
    ("kimya/12-sinif-kimya-al-emine-bingol-yillik-plan-ogretmenevrak-1788776813.docx", 12, "kimya", None, ""),
    ("matematik/9-12.xlsx", 9, "matematik", "9. SINIF", ""),
    ("matematik/9-12.xlsx", 12, "matematik", "12. SINIF", ""),
    ("matematik/2026-2027 10. sınıf yıllık plan matematik.pdf", 10, "matematik", None, ""),
    ("matematik/2026-2027 11. sınıf yıllık plan matematik.pdf", 11, "matematik", None, ""),
    ("tarih/2026-2027ŞEHİT MURAT USTAOĞLU _9_Sinif_Tarih_Yillik_Plani.docx", 9, "tarih", None, ""),
    ("tarih/2026-2027_ŞEHİT MURAT USTAOĞLU_10_Sinif_Tarih_Yillik_Plani.docx", 10, "tarih", None, ""),
    ("tarih/2026-2027_11_Sinif_Tarih_Yillik_Plani_Farklilastirma_Eklenmis (1).docx", 11, "tarih", None, ""),
    ("tarih/2026-2027_ŞEHİT MURAT USTAOĞLUi_12_Sinif_TC_Inkilap_Tarihi_).docx", 12, INKILAP, None, ""),
    ("tarih/ÇAĞDAŞ .docx", 12, CAGDAS, None, ""),
    ("tarih/ortak-turk-tarihi-unitelendirilmis-yillik-plan.docx", 10, "ortak türk tarihi", None,
     "seçmeli ders; kazanım sütunu 'KAZANIMLAR VE AÇIKLAMALARI'"),
    # Tek PDF'te iki plan: s1-2 = 12. sınıf, s3-4 = 11. sınıf. Çizgisiz tablo
    # (pdfplumber tablo bulamıyor) → kelime konumlarından okunur
    # (pdf_kelime_tablolari). Kendi hafta numaraları 07 Eylül'den başlar ve
    # tatilleri saymaz; satırlar TARİH ARALIĞINA göre ortak takvime yerleşir.
    ("bilisim/2026-2027 Programlamaya Giriş ve Algoritmalar Yıllık Planları (12-11 sınıf atakan ünver).pdf", 12, "bilişim teknolojileri ve yazılım", "s1-2",
     "Programlamaya Giriş ve Algoritmalar planı (2026-10-06 eklendi)"),
    ("bilisim/2026-2027 Programlamaya Giriş ve Algoritmalar Yıllık Planları (12-11 sınıf atakan ünver).pdf", 11, "bilişim teknolojileri ve yazılım", "s3-4",
     "Programlamaya Giriş ve Algoritmalar planı (2026-10-06 eklendi)"),
]

# Edebiyat 10/12 PDF'leri (2026-10-06, .doc yerine): birleşik hücreli, başlık ile
# veri sütun numaraları kayık tablolar → hücreler KONUMLA (bbox) eşlenir
# (pdf_tde_tablolari). Hafta numaraları okul takvimiyle birebir (35/34 tarihli
# haftada kontrol edildi), satırlar hafta numarasıyla yerleşir.
TDE_PDF = {"edebiyat/10.sınıflar edebiyat.pdf", "edebiyat/12.SINIFLAR TDE YILLIK PLANI.pdf"}
# 12. sınıf planı eski programda: kazanımlar TDE kodlu değil (A.2.1., B.1., C.1. 2.)
KOD_ZORUNLU_HARIC = {(12, "türk dili ve edebiyatı")}

# Çizgisiz tablolu PDF'ler: sütunlar başlık kelimelerinin x konumundan çıkarılır.
KELIME_PDF = {"bilisim/2026-2027 Programlamaya Giriş ve Algoritmalar Yıllık Planları (12-11 sınıf atakan ünver).pdf"}

# Bir haftada tutulacak en fazla ayrı kazanım (tahtada 2 satır gösterilir).
MAKS_KAZANIM_SAYISI = 3

# Yeni kazanım içermeyen, önceki kazanımın devam açıklamalarından oluşan
# haftalar (2026-10-06 bağımsız denetimiyle kaynaktan doğrulandı; kullanıcı
# kararı: önceki kazanım gösterilsin). Plan değişirse yeniden denetlenmeli.
DEVAM_HAFTALARI = {(10, "ortak türk tarihi"): (18, 31)}

# Kazanım + açıklamanın aynı hücrede olduğu planlar: ilk cümlede kes.
CUMLE_KES = {(10, "ortak türk tarihi")}

# Zaman çizelgesinde karşılığı olmayan / yinelenen dosyalar (neden ile).
ATLANAN = {
    "beden eğitimi 10 eksik/12. sınıf beden eğitimi.docx": "12. sınıf beden eğitimi yinelenen plan (standart adlı olan kullanıldı)",
    "görsel sanatlar/11 görsel sanatlar feride.docx": "11. sınıf görsel sanatlar yinelenen plan (cigdem-ince kullanıldı)",
    "edebiyat/11.SINIFLAR TDE YILLIK PLANI SEÇMELİ.docx": "SEÇMELİ varyant",
    "edebiyat/12.SINIFLAR TDE YILLIK PLANI SEÇMELİ.docx": "SEÇMELİ varyant",
    "fizik/hedef-temelli-egitim-fizik-1.docx": "hedef-temelli seçmeli varyant",
    "kimya/hedef-temelli-egitim-kimya-ii-12-plan 2.docx": "hedef-temelli seçmeli varyant",
    "tarih/hedef-temelli-bir saatlik.docx": "hedef-temelli seçmeli varyant",
    "tarih/SEÇMELİ TARİH.docx": "SEÇMELİ varyant",
    "din kültürü/2026-2027temeldinibilgiler_ortaoogretim1_TYMM (2).xlsx": "temel dini bilgiler seçmeli (çizelgede yok)",
}

# Okunamayan biçimler: kütüphane yok, sistem paketi kurulmaz.
DESTEKLENMEYEN_UZANTILAR = {
    ".doc": "eski .doc: antiword/libreoffice/textract/olefile bu venv'de yok "
            "(olefile yalnızca /opt/open-webui/venv'de; başka servisin venv'i, kullanılmadı)",
}

# --- Metin yardımcıları -------------------------------------------------------

_KATLA = str.maketrans({
    "İ": "I", "ı": "I", "Ş": "S", "ş": "S", "Ğ": "G", "ğ": "G", "Ü": "U",
    "ü": "U", "Ö": "O", "ö": "O", "Ç": "C", "ç": "C", "â": "A", "Â": "A",
    "î": "I", "û": "U", " ": " ",
})


def katla(metin: str) -> str:
    """ASCII'ye katlanmış BÜYÜK harf ('Ekim' -> 'EKIM'); Türkçe i/İ tuzağına
    karşı .lower() KULLANILMAZ."""
    return metin.translate(_KATLA).upper()


AYLAR = {
    "OCAK": 1, "SUBAT": 2, "MART": 3, "NISAN": 4, "MAYIS": 5, "HAZIRAN": 6,
    "TEMMUZ": 7, "AGUSTOS": 8, "EYLUL": 9, "EKIM": 10, "KASIM": 11, "ARALIK": 12,
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5, "JUNE": 6, "JULY": 7,
    "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}
_AY_RE = r"[A-Z]{3,}"
TARIH_ARALIK_RE = re.compile(
    rf"(?<!\d)(\d{{1,2}})\s*({_AY_RE})?\s*[-–—]\s*(\d{{1,2}})(?!\d)\s*({_AY_RE})?"
)
HAFTA_RE = [
    re.compile(r"(?<!\d)(\d{1,2})\s*\.?\s*HAFTA"),
    re.compile(r"(?<!\d)(\d{1,2})\s*\.?\s*WEEK"),
    re.compile(r"WEEK\s*(\d{1,2})(?!\d)"),
    re.compile(r"^\s*(\d{1,2})\.\s*$"),  # edebiyat: yalnız "12."
]


# Kısaltılmış Türkçe ay adları ("28 Eyl - 02 Eki", "30 Kas - 04 Ara" —
# bilişim planı, 2026-10-06): ilk 3 harf Türkçe aylar arasında tekil.
_TR_AY_KISA = {ad[:3]: no for ad, no in list(AYLAR.items())[:12]}


def ay_no(belirteç: str | None) -> int | None:
    if not belirteç:
        return None
    return AYLAR.get(belirteç) or _TR_AY_KISA.get(belirteç[:3])


def hafta_no_bul(hucre_metinleri: list[str]) -> int | None:
    for metin in hucre_metinleri:
        k = katla(metin)
        for re_ in HAFTA_RE:
            m = re_.search(k)
            if m:
                return int(m.group(1))
    return None


def ay_ipucu(hucre_metinleri: list[str]) -> int | None:
    """'EYLÜL' / 'EYLÜL-EKİM' gibi yalnız ay adı içeren hücreden ilk ay."""
    for metin in hucre_metinleri:
        belirtecler = re.split(r"[\s\-–/]+", katla(metin).strip())
        belirtecler = [b for b in belirtecler if b]
        if belirtecler and all(b in AYLAR for b in belirtecler):
            return AYLAR[belirtecler[0]]
    return None


def pazartesi_bul(hucre_metinleri: list[str]) -> tuple[date | None, str | None]:
    """Etiketteki tarih aralığının BAŞLANGIÇ günü -> (tarih, sorun).
    Pazartesi değilse tarih None, sorun açıklaması döner."""
    metin = " ".join(katla(m) for m in hucre_metinleri)
    # "28 Ara 2026 - 01 Oca 2027": aradaki yıl aralık kalıbını bozar; yıl
    # zaten aydan çıkarılıyor (aşağıda), o yüzden atılır.
    metin = re.sub(r"(?<!\d)20\d{2}(?!\d)", " ", metin)
    ipucu = ay_ipucu(hucre_metinleri)
    for m in TARIH_ARALIK_RE.finditer(metin):
        g1, a1, g2, a2 = int(m.group(1)), ay_no(m.group(2)), int(m.group(3)), ay_no(m.group(4))
        if a1 is not None:
            ay = a1
        elif a2 is not None:
            ay = a2 if g2 >= g1 else (a2 - 1 or 12)
        elif ipucu is not None:
            ay = ipucu
        else:
            continue
        yil = 2026 if ay >= 8 else 2027
        try:
            gun = date(yil, ay, g1)
        except ValueError:
            continue
        if gun.weekday() != 0:
            return None, f"{gun.isoformat()} Pazartesi değil"
        return gun, None
    return None, None


def temizle(metin: str) -> str:
    return re.sub(r"\s+", " ", metin.replace(" ", " ")).strip()


def kisalt(metin: str, sinir: int = MAKS_UZUNLUK) -> str:
    if len(metin) <= sinir:
        return metin
    kesik = metin[:sinir]
    bosluk = kesik.rfind(" ")
    if bosluk > sinir // 2:
        kesik = kesik[:bosluk]
    return kesik.rstrip(" ,;:-–") + "…"


# Kazanım kodu: BİY.9.1.2. / 9.1.1. / E10.1.L1. / ENG.9.1.L1 / TDE2.1. / GS.10.3.1 / 1.1.
_KOD = (
    r"(?:[A-ZÇĞİÖŞÜ]{1,5}\.?)?E?\d{1,2}(?:\.\d{1,2}){1,4}\.?"
    r"|[A-Z]{1,4}\.?\d{1,2}\.\d{1,2}\.[A-Z]\d{1,2}\.?"
)
_KOD_SONRASI = r"(?=\s|[A-ZÇĞİÖŞÜ][a-zçğıöşü])"  # "E11.3.L1.Students" gibi bitişik yazımlar
KOD_RE = re.compile(rf"(?<![\w.])(?:{_KOD}){_KOD_SONRASI}")
KOD_BASTA_RE = re.compile(rf"^(?:{_KOD})(?=[A-ZÇĞİÖŞÜ][a-zçğıöşü])")
# İngilizce/Almanca beceri etiketleri (ilk kazanımın başına/sonuna sızar).
BECERI_ETIKETI = (
    r"Listening|Speaking|Reading|Writing|Pronunciation|Spoken Interaction|Spoken Production|"
    r"HÖREN|SPRECHEN|LESEN|SCHREIBEN|SPRACHMITTLUNG"
)
_BECERI_SON_RE = re.compile(rf"\s+(?:{BECERI_ETIKETI})\s*$", re.IGNORECASE)
_BECERI_BAS_RE = re.compile(rf"^(?:{BECERI_ETIKETI})\s+(?=[A-Z]{{1,5}}\.?\d|Students)", re.IGNORECASE)
_BECERI_ORTA_RE = re.compile(rf"\s(?:{BECERI_ETIKETI})\s+(?=Students|[A-Z]{{1,5}}\.?\d)")
_CUMLE_SONU_RE = re.compile(r"(?<=[a-zçğıöşü])\.\s+(?=[A-ZÇĞİÖŞÜ])")


def ilk_kazanim(ham: str, cumle_kes: bool = False) -> str:
    """Hücredeki İLK kazanım. Kural sırası: ilk paragraf (kısa etiket satırıysa
    sonraki satırla birleşir); paragrafta kod yoksa ama ilk 100 karakterde bir
    kod varsa oradan başla (edebiyat 'Edebiyat Atölyesi / Yazma TDE4.1.',
    ingilizce 'Listening E10.1.L1.'); sonraki kodda kes; beceri etiketini
    ayıkla. cumle_kes: kazanım ile açıklaması aynı hücrede (ortak türk
    tarihi) — kodun ilk cümlesinde kes."""
    duz = temizle(ham)
    satirlar = [temizle(x) for x in ham.split("\n")]
    satirlar = [x for x in satirlar if x]
    if not satirlar:
        return ""
    metin = satirlar[0]
    if not KOD_RE.match(metin + " "):
        km = KOD_RE.search(duz)
        if km and km.start() < 100:
            metin = duz[km.start():]
        elif len(satirlar) > 1 and len(metin) < 12:  # yalnız etiket satırı (HÖREN)
            metin = temizle(metin + " " + satirlar[1])
    um = re.match(r"^\d{1,2}\.\s*ÜNİTE\b.*?(\d{1,2}\.\s?\d{1,2}\.\s)", metin)
    if um:  # "5. ÜNİTE: ... 5. 1. Moğol ..." -> "5.1. Moğol ..."
        metin = re.sub(r"^(\d{1,2})\.\s(\d{1,2}\.)", r"\1.\2", metin[um.start(1):])
    metin = _BECERI_BAS_RE.sub("", metin)
    kodlar = list(KOD_RE.finditer(metin + " "))
    if len(kodlar) >= 2 and kodlar[0].start() == 0:
        metin = metin[:kodlar[1].start()]
    elif len(kodlar) >= 3:
        metin = metin[:kodlar[2].start()]
    orta = _BECERI_ORTA_RE.search(metin)  # kodsuz planlarda (ingilizce 11)
    if orta:
        metin = metin[:orta.start()]
    if cumle_kes:
        m = _CUMLE_SONU_RE.search(metin)
        if m:
            metin = metin[:m.start() + 1]
    metin = _BECERI_SON_RE.sub("", metin.strip())
    metin = re.sub(r"\s+[a-zçğıöşü]\.$", "", metin)  # kesilen "a." alt madde işareti
    km = KOD_BASTA_RE.match(metin)
    if km:  # "9.1.1.Gerçek" -> "9.1.1. Gerçek"
        metin = metin[:km.end()] + " " + metin[km.end():]
    return kisalt(temizle(metin))


_YER_TUTUCU_RE = re.compile(
    r"^(\*|sdb\d|\d{1,2}\.\s*hafta|destekleme|zenginleştirme|köprü kurma|sınav haftası|sosyal etkinlik|social activit|mid-term|ara tatil|yarıyıl|tatil)", re.IGNORECASE)
_KAZANIM_GIBI_RE = re.compile(
    r"^(?:[A-ZÇĞİÖŞÜ]{1,5}\.?)?E?\d{1,2}(?:\.\d{1,2}){1,4}|^[A-Z]{2,4}\.?\d|^\d{1,2}\.\s|^Students\b|^(?:HÖREN|SPRECHEN)\b")


def yer_tutucu_mu(metin: str) -> bool:
    """Kazanım olmayan hücre içeriği: '*Okul Temelli Planlama', 'SINAV HAFTASI',
    '……….', tek harfli alt madde ('c.')."""
    harfler = re.sub(r"[^A-Za-zÇĞİÖŞÜçğıöşü]", "", metin)
    return len(harfler) < 6 or bool(_YER_TUTUCU_RE.match(metin.strip()))


# Edebiyat planlarında kazanım sütunu açıklama/uyarı satırlarıyla da dolu:
# yalnızca TDE kodlu hücreler kazanım sayılır.
KOD_ZORUNLU = {EDEB: re.compile(r"^TDE\d")}


def plan_filtrele(adaylar: list[tuple[int, str]], zorunlu: re.Pattern | None = None) -> list[tuple[int, str]]:
    """Yer tutucuları at. Planın kazanımlarının çoğu kod/numara ile başlıyorsa
    (>=%70), kodsuz hücreler (açıklama/uyarı metni) de kazanım sayılmaz."""
    adaylar = [(h, m) for h, m in adaylar if not yer_tutucu_mu(m)]
    if zorunlu is not None:
        return [(h, m) for h, m in adaylar if zorunlu.match(m)]
    if adaylar:
        kodlu = sum(1 for _h, m in adaylar if _KAZANIM_GIBI_RE.match(m))
        if kodlu / len(adaylar) >= 0.7:
            adaylar = [(h, m) for h, m in adaylar if _KAZANIM_GIBI_RE.match(m)]
    return adaylar


# --- Tablo okuyucular: her satır = [(metin, kimlik), ...] -----------------------


def docx_tablolari(yol: Path):
    import docx  # server venv

    belge = docx.Document(str(yol))
    for tablo in belge.tables:
        satirlar = []
        for satir in tablo.rows:
            try:
                hucreler = satir.cells
            except Exception:  # noqa: BLE001, S112 — bozuk grid satırı
                continue
            satirlar.append([(h.text, h._tc) for h in hucreler])
        yield "docx-tablo", satirlar


def xlsx_tablolari(yol: Path, sayfa_adi: str | None):
    import openpyxl

    kitap = openpyxl.load_workbook(str(yol), data_only=True)
    for ws in kitap.worksheets:
        if sayfa_adi and ws.title != sayfa_adi:
            continue
        izgara = [[(("" if v is None else str(v)), ("h", r, c))
                   for c, v in enumerate(satir)]
                  for r, satir in enumerate(ws.iter_rows(values_only=True))]
        for aralik in ws.merged_cells.ranges:  # birleşik hücre: değer + kimlik tekrarı
            r0, c0 = aralik.min_row - 1, aralik.min_col - 1
            if r0 >= len(izgara) or c0 >= len(izgara[r0]):
                continue
            metin = izgara[r0][c0][0]
            for r in range(aralik.min_row - 1, min(aralik.max_row, len(izgara))):
                for c in range(aralik.min_col - 1, min(aralik.max_col, len(izgara[r]))):
                    izgara[r][c] = (metin, ("m", ws.title, r0, c0))
        yield f"xlsx:{ws.title}", izgara


def pdf_tablolari(yol: Path):
    import pdfplumber

    with pdfplumber.open(str(yol)) as pdf:
        for no, sayfa in enumerate(pdf.pages, 1):
            for t_no, tablo in enumerate(sayfa.extract_tables(), 1):
                satirlar = [[((c or "").replace("\n", " "), ("p", no, t_no, r, i))
                             for i, c in enumerate(satir)]
                            for r, satir in enumerate(tablo)]
                yield f"pdf-s{no}-t{t_no}", satirlar


def pdf_kelime_tablolari(yol: Path, sayfa_araligi: str | None):
    """Çizgisiz PDF tablosu: başlık satırındaki ("Hft ... Kazanımlar ...")
    kelimelerin x0'ı sütun başlangıcı; sol sütundaki sayılar satır
    başlangıcı. Hücre metni dikey ortalı taşabildiği için satır bandı komşu
    satır numaralarının ORTA NOKTALARIYLA sınırlanır. Tarih sütununu
    pazartesi_bul okusun diye ilk 3 hücre: hafta no, tarih aralığı, saat."""
    import logging

    import pdfplumber

    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    bas, son = 1, 10_000
    if sayfa_araligi:
        a, b = sayfa_araligi.lstrip("s").split("-")
        bas, son = int(a), int(b)
    with pdfplumber.open(str(yol)) as pdf:
        for no, sayfa in enumerate(pdf.pages, 1):
            if not bas <= no <= son:
                continue
            kelimeler = sayfa.extract_words()
            baslik = next((k for k in kelimeler if k["text"] == "Hft"), None)
            if baslik is None:
                continue
            ust = baslik["top"]
            sutun_x = sorted(k["x0"] for k in kelimeler
                             if abs(k["top"] - ust) < 3 and k["text"] in
                             ("Hft", "Tarih", "Sa.", "Öğrenme", "Kazanımlar", "Yöntem", "Belirli"))
            if len(sutun_x) < 5:
                continue
            basliklar = ["Hft", "Tarih Aralığı", "Sa.", "Öğrenme Alanı / Konu",
                         "Kazanımlar ve İşleniş İçeriği", "Yöntem / Araç-Gereç",
                         "Belirli Günler / Açıklamalar"][: len(sutun_x)]
            # Tam genişlik tatil bandı ("09 - 13 Kasım 2026 • 1. DÖNEM ARA
            # TATİLİ ...") = Hft sütununda numarası OLMAYAN ve "•" içeren
            # satır; komşu haftanın hücresine karışmasın diye atılır. Numaralı
            # bir haftanın satırında "•" geçse bile o satır korunur.
            numara_ust = [k["top"] for k in kelimeler
                          if k["x0"] < sutun_x[1] - 2 and k["text"].isdigit()]
            bant_ust = [k["top"] for k in kelimeler if k["text"] == "•"
                        and all(abs(k["top"] - t) > 2 for t in numara_ust)]
            kelimeler = [k for k in kelimeler if all(abs(k["top"] - t) > 2 for t in bant_ust)]
            satir_basi = sorted(k["top"] for k in kelimeler
                                if k["x0"] < sutun_x[1] - 2 and k["text"].isdigit()
                                and k["top"] > ust + 5)
            if not satir_basi:
                continue
            sinirlar = [ust + 8]
            sinirlar += [(a + b) / 2 for a, b in zip(satir_basi, satir_basi[1:])]
            sinirlar.append(satir_basi[-1] + (satir_basi[-1] - sinirlar[-1]))
            satirlar = [[(m, ("k", no, 0, 0, i)) for i, m in enumerate(basliklar)]]
            for r in range(len(satir_basi)):
                hucreler = [[] for _ in sutun_x]
                for k in kelimeler:
                    if sinirlar[r] <= k["top"] < sinirlar[r + 1]:
                        i = max(j for j, x in enumerate(sutun_x) if k["x0"] >= x - 3) if k["x0"] >= sutun_x[0] - 3 else 0
                        hucreler[i].append(k)
                metin = [" ".join(w["text"] for w in sorted(h, key=lambda w: (round(w["top"]), w["x0"])))
                         for h in hucreler]
                # SIRAYLA EŞLEME (kullanıcı kararı 2026-10-06): bu planların
                # tarihleri okul takviminden kayık (7 Eylül başlangıç, farklı
                # ara tatiller) ama hafta numaraları tatilleri saymayan
                # öğretim haftası sırası → plan haftası N = okul haftası N.
                # Tarih hücresi boşaltılır ki takvim oylamasına girmesin ve
                # satır "tarihsiz etiket" yolundan N'e yerleşsin.
                metin[0] = f"{metin[0]}. HAFTA"
                metin[-1] = f"{metin[-1]} ({metin[1]})"
                metin[1] = ""
                satirlar.append([(m, ("k", no, 0, r + 1, i)) for i, m in enumerate(metin)])
            yield f"pdfk-s{no}", satirlar


_TDE_KOD = re.compile(r"TDE\d+\.\d+\.?|(?<!\w)[ABC]\.\s?\d{1,2}(?:\.\s?\d{1,2})?\.?")
_TDE_HAFTA = re.compile(r"^(\d{1,2})\.$")
# Alttaki tablo başlığından sızan BÜYÜK HARF parça ("… ÖĞRENME Ç",
# "… YAZMA / SÖZLÜ İLETİŞİM BECERİLERİ KAZANIMLARI") — oradan kesilir.
_BASLIK_SIZINTISI = re.compile(r"\s[A-ZÇĞİÖŞÜ]{4,}\s+[A-ZÇĞİÖŞÜ/].*$")


def _tde_ilk_kodlu(metin: str | None) -> str | None:
    """Hücredeki İLK anlamlı kodlu kazanım: koddan bir sonraki koda kadar; kodun
    ardından en az 3 kelime yoksa (ör. "C.1.2 -C.1.17 kazanımları" aralık
    başlığı) sonraki koda geçilir. Kod yoksa None."""
    if not metin:
        return None
    kodlar = list(_TDE_KOD.finditer(metin))
    for i, m in enumerate(kodlar):
        son = kodlar[i + 1].start() if i + 1 < len(kodlar) else len(metin)
        parca = _BASLIK_SIZINTISI.sub("", " ".join(metin[m.start():son].split()))
        if len(parca[m.end() - m.start():].split()) >= 3:
            return parca
    return None


def pdf_tde_tablolari(yol: Path):
    """Edebiyat 10/12 PDF'leri. Kazanım sütunu = "öğrenme çıktısı"/"kazanım"
    başlıklı hücrelerin EN DARI; veri satırında ona x'te en çok örtüşen hücre
    alınır. O konumda hücre yoksa (birleşik hücre devamı) aynı tablodaki
    önceki haftanın kazanımı sürer."""
    import logging

    import pdfplumber

    logging.getLogger("pdfminer").setLevel(logging.ERROR)

    def metin_al(sayfa, kutu):
        return " ".join((sayfa.crop(kutu).extract_text() or "").split()) if kutu else None

    def ortusme(a, b):
        return max(0.0, min(a[2], b[2]) - max(a[0], b[0]))

    with pdfplumber.open(str(yol)) as pdf:
        for no, sayfa in enumerate(pdf.pages, 1):
            for t_no, tablo in enumerate(sayfa.find_tables(), 1):
                hucreler = [[(k, metin_al(sayfa, k)) for k in r.cells] for r in tablo.rows]
                basliklar = [(k, m) for r in hucreler for k, m in r if k and m and len(m) < 120
                             and any(x in katla(m) for x in ("OGRENME CIKTI", "KAZANIM"))
                             and "KONU" not in katla(m)]
                if not basliklar:
                    continue
                kutu = min(basliklar, key=lambda km: km[0][2] - km[0][0])[0]
                satirlar = [[("HAFTA", None), ("", None), ("", None), ("KAZANIM", None)]]
                onceki = None

                def kutudaki(r):
                    aday = max(((k, m) for k, m in r if k), key=lambda km: ortusme(km[0], kutu),
                               default=(None, None))
                    return (None, None) if aday[0] is None or ortusme(aday[0], kutu) < 5 else aday

                def hafta_no(r):
                    hm = _TDE_HAFTA.match(next((m for _k, m in r if m), "") or "")
                    return hm.group(1) if hm else None

                for i, r in enumerate(hucreler):
                    no_h = hafta_no(r)
                    if no_h is None:
                        continue
                    kk, km = kutudaki(r)
                    # Haftanın alt satırları (ilk sütunu boş, sonraki haftaya ya da
                    # tablo başlığına kadar): sarılan metin ve etiketin altındaki
                    # kodlu kazanım buradadır → kazanım sütunundaki metinler birleşir.
                    parcalar = [km] if kk is not None else []
                    for r2 in hucreler[i + 1:]:
                        if hafta_no(r2) is not None or (r2 and r2[0][1]):
                            break
                        parcalar.append(kutudaki(r2)[1])
                    birlesik = " ".join(x for x in parcalar if x)
                    kazanim = _tde_ilk_kodlu(birlesik)
                    if kazanim is not None:
                        # "Önceki" yalnızca KODLU kazanım bulununca güncellenir:
                        # alt satırlardaki kodsuz metin (açıklama) belleği silmesin.
                        onceki = birlesik
                    elif kk is None:
                        # Kazanım sütununda hücre yok = dikey birleşik hücre devamı.
                        kazanim = _tde_ilk_kodlu(onceki)
                    kazanim = kazanim or ""
                    satirlar.append([(f"{no_h}. HAFTA", ("t", no, t_no)), ("", None),
                                     ("", None), (kazanim, ("t", no, t_no))])
                yield f"pdft-s{no}-t{t_no}", satirlar


# --- Tablodan (hafta, kazanım) satırları ---------------------------------------


def baslik_kazanim_mi(metin: str) -> bool:
    if len(metin) > 100:  # başlık kısa olur; uzun hücre içerik metnidir
        return False
    k = katla(metin)
    if "KANIT" in k or "SUREC BILESEN" in k and "OGRENME CIKTI" not in k:
        return False
    if "ACIKLAMA" in k and "KAZANIMLAR VE" not in k:
        return False
    return any(a in k for a in ("OGRENME CIKTI", "KAZANIM", "LEARNING OUTCOMES", "LANGUAGE TASKS"))


def tablo_satirlari(satirlar, ofset_bellek: dict):
    """Yield (hafta_no|None, pazartesi|None, kazanim_ham, tarih_sorunu|None,
    etiketsiz_mi). ofset_bellek: başlıksız tablolar için hafta->kazanım sütun farkı."""
    kolon = None
    onceki_hafta = None  # (hafta_no, pazartesi) — etiketsiz devam satırları için
    baslik_goruldu = False
    for satir in satirlar:
        metinler = [h[0] for h in satir]
        # Başlık satırı: kazanım başlığı içeren ve tarih/hafta içermeyen satır
        sol_ilk = metinler[:3]
        hafta = hafta_no_bul(sol_ilk)
        tarih, sorun = pazartesi_bul(sol_ilk)
        adaylar = [i for i, m in enumerate(metinler) if baslik_kazanim_mi(m)]
        if adaylar and hafta is None and tarih is None and len(satir) >= 4:
            kolon = adaylar[0]
            baslik_goruldu = True
            onceki_hafta = None
            continue
        if hafta is None and tarih is None:
            # devam satırı (etiketsiz) ya da tatil bandı
            if any("TATIL" in katla(m) for m in sol_ilk + metinler[3:5]):
                onceki_hafta = None
                continue
            k = kolon
            if k is None and not baslik_goruldu:
                k = None
            if k is None or k >= len(satir):
                continue
            ham = satir[k][0]
            if temizle(ham):
                if onceki_hafta:
                    yield onceki_hafta[0], onceki_hafta[1], ham, None, False
                else:
                    yield None, None, ham, None, True
            continue
        k = kolon
        if k is None:  # başlıksız tablo (PDF devam sayfaları)
            w_idx = next((i for i, m in enumerate(metinler[:3]) if hafta_no_bul([m]) is not None), None)
            ofs = ofset_bellek.get("ofset")
            if w_idx is None or ofs is None:
                continue
            k = w_idx + ofs
        elif "ofset" not in ofset_bellek:
            w_idx = next((i for i, m in enumerate(metinler[:3]) if hafta_no_bul([m]) is not None), None)
            if w_idx is not None:
                ofset_bellek["ofset"] = k - w_idx
        if k >= len(satir):
            continue
        onceki_hafta = (hafta, tarih)
        yield hafta, tarih, satir[k][0], sorun, False


def dosyayi_oku(yol: Path, sayfa: str | None):
    """-> (satir listesi [(hafta, pazartesi, ham, sorun, etiketsiz)], uyarilar)"""
    uzanti = yol.suffix.lower()
    if uzanti == ".docx":
        tablolar = docx_tablolari(yol)
    elif uzanti == ".xlsx":
        tablolar = xlsx_tablolari(yol, sayfa)
    elif uzanti == ".pdf" and any(str(yol).endswith(k) for k in TDE_PDF):
        tablolar = pdf_tde_tablolari(yol)
    elif uzanti == ".pdf" and any(str(yol).endswith(k) for k in KELIME_PDF):
        tablolar = pdf_kelime_tablolari(yol, sayfa)
    elif uzanti == ".pdf":
        tablolar = pdf_tablolari(yol)
    else:
        raise ValueError(f"desteklenmeyen uzantı: {uzanti}")
    sonuc = []
    ofset = {}
    for _etiket, satirlar in tablolar:
        sonuc.extend(tablo_satirlari(satirlar, ofset))
    if uzanti == ".pdf":
        sonuc = pdf_kesik_hucreleri_onar(sonuc)
    return sonuc


def pdf_kesik_hucreleri_onar(satirlar):
    """PDF'te sayfa sonuna denk gelen satırın kazanım hücresi kesik gelir
    ("... f (x) ="); aynı metinle başlayan DAHA UZUN bir hücre (aynı kazanımın
    başka haftadaki tam hâli) varsa kesik olan onunla değiştirilir."""
    metinler = sorted({r[2] for r in satirlar}, key=len, reverse=True)
    yeni = []
    for r in satirlar:
        uzun = next((m for m in metinler if len(m) > len(r[2]) and r[2].strip() and m.startswith(r[2])), r[2])
        yeni.append((r[0], r[1], uzun, r[3], r[4]))
    return yeni


# --- Ana akış ------------------------------------------------------------------


def calisma(plan_dizini: Path, cikti: Path) -> int:
    if not plan_dizini.is_dir():
        print(f"HATA: plan dizini yok: {plan_dizini}", file=sys.stderr)
        return 2

    mevcut = {str(p.relative_to(plan_dizini)) for p in plan_dizini.rglob("*")
              if p.is_file() and YOK_ALT_DIZIN not in p.relative_to(plan_dizini).parts}
    eslenen_yollar = {e[0] for e in ESLEME}
    eslenmemis = sorted(mevcut - eslenen_yollar - set(ATLANAN))
    kayip_dosya = sorted(eslenen_yollar - mevcut)

    okunan = {}  # (düzey, ders) -> satırlar
    destek_yok = []
    notlar = []
    for yol_s, duzey, ders, sayfa, not_ in ESLEME:
        if yol_s not in mevcut:
            continue
        yol = plan_dizini / yol_s
        if yol.suffix.lower() in DESTEKLENMEYEN_UZANTILAR:
            destek_yok.append((duzey, ders, yol_s, DESTEKLENMEYEN_UZANTILAR[yol.suffix.lower()]))
            continue
        try:
            okunan[(duzey, ders, yol_s)] = dosyayi_oku(yol, sayfa)
        except Exception as hata:  # noqa: BLE001 — tek dosya diğerlerini durdurmasın
            destek_yok.append((duzey, ders, yol_s, f"okunamadı: {hata!r}"))
        if not_:
            notlar.append(f"{duzey}/{ders}: {not_}")

    # 1) Takvim: dosya başına (hafta -> pazartesi) oyları
    oylar = defaultdict(Counter)
    kaynaklar = defaultdict(lambda: defaultdict(set))
    tarih_sorunlari = []
    for (duzey, ders, yol_s), satirlar in okunan.items():
        gorulen = set()
        for hafta, pzt, _ham, sorun, _e in satirlar:
            if sorun:
                tarih_sorunlari.append(f"{duzey}/{ders} hafta {hafta}: {sorun}")
            if hafta is not None and pzt is not None and (hafta, pzt) not in gorulen:
                gorulen.add((hafta, pzt))
                oylar[hafta][pzt] += 1
                kaynaklar[hafta][pzt].add(f"{duzey}/{ders}")
    takvim = {}
    anlasmazlik = []
    elenen_haftalar = []
    for hafta in sorted(oylar):
        sirali = sorted(oylar[hafta].items(), key=lambda kv: (-kv[1], kv[0]))
        kazanan, oy = sirali[0]
        if oy < MIN_OY:  # yalnızca 1-2 plan söylüyor: takvim haftası sayılmaz
            elenen_haftalar.append(f"hafta {hafta}: {kazanan.isoformat()} x{oy} ({', '.join(sorted(kaynaklar[hafta][kazanan]))})")
            continue
        takvim[hafta] = kazanan
        if len(sirali) > 1:
            for p, n in sirali[1:]:
                anlasmazlik.append((tuple(sorted(kaynaklar[hafta][p])), hafta, kazanan, p, oy, n))
    ters = {}
    for h, p in takvim.items():
        ters.setdefault(p, h)

    # Dosya içi tutarlılık: etiket->tarih eşlemesi ve etiketi takvimle çelişen dosyalar
    dosya_esleme = {}
    kaymis = set()
    for anahtar, satirlar in okunan.items():
        em = {}
        for hafta, pzt, *_ in satirlar:
            if hafta is not None and pzt is not None:
                em.setdefault(hafta, pzt)
                if pzt in ters and ters[pzt] != hafta:
                    kaymis.add(anahtar)
        dosya_esleme[anahtar] = em

    # 2) Kazanımlar
    sonuc = defaultdict(lambda: defaultdict(dict))  # düzey -> ders -> hafta -> metin
    celiskiler = []
    etiketsiz = Counter()
    for (duzey, ders, yol_s), satirlar in okunan.items():
        hedef = sonuc[duzey][ders]
        adaylar = []
        for hafta, pzt, ham, _sorun, etiketsiz_mi in satirlar:
            if etiketsiz_mi:
                etiketsiz[(duzey, ders)] += 1
                continue
            hafta_son = hafta
            if pzt is None and hafta is not None:
                # Tarihsiz satır: etiket numarası yalnızca dosya takvimle tutarlıysa
                # güvenilir; kaymış dosyada kendi eşlemesinden, yoksa atlanır.
                kendi = dosya_esleme[(duzey, ders, yol_s)].get(hafta)
                if kendi is not None and kendi in ters:
                    hafta_son = ters[kendi]
                elif (duzey, ders, yol_s) in kaymis:
                    celiskiler.append(f"{duzey}/{ders}: tarihsiz etiket hafta {hafta} (kaymış numaralama) tatil sayıldı, atlandı")
                    continue
            if pzt is not None:
                if pzt in ters:
                    if hafta is not None and ters[pzt] != hafta:
                        celiskiler.append(f"{duzey}/{ders}: etiket hafta {hafta} ama tarih {pzt} = hafta {ters[pzt]} (tarih esas alındı)")
                    hafta_son = ters[pzt]
                else:  # takvimde olmayan tarih = tatil haftası; kazanım yazılmaz
                    celiskiler.append(f"{duzey}/{ders}: {pzt} (etiket hafta {hafta}) takvimde yok -> tatil sayıldı, atlandı")
                    continue
            if hafta_son is None:
                continue
            metin = ilk_kazanim(ham, (duzey, ders) in CUMLE_KES)
            if metin:
                adaylar.append((hafta_son, metin))
        # Aynı haftada birden fazla AYRI kazanım (ör. matematik: 2 saat 9.1.1 +
        # 4 saat 9.1.2) hepsi tutulur, plandaki sırayla, "\n" ile ayrılır —
        # öğretmen deftere eksik yazmasın (kullanıcı kararı 2026-10-06: tahtada
        # iki satır). Eski yoklama.py "\n"'i boşluğa çevirip tek satır gösterir.
        hafta_listesi = defaultdict(list)
        zorunlu = None if (duzey, ders) in KOD_ZORUNLU_HARIC else KOD_ZORUNLU.get(ders)
        for hafta_son, metin in plan_filtrele(adaylar, zorunlu):
            if metin not in hafta_listesi[hafta_son]:
                hafta_listesi[hafta_son].append(metin)
        for hafta_son, liste in hafta_listesi.items():
            hedef.setdefault(hafta_son, "\n".join(liste[:MAKS_KAZANIM_SAYISI]))
        # Devam haftaları: yeni kazanım yok, önceki kazanımın açıklamaları var
        # (denetimle tek tek doğrulandı) → önceki haftanın kazanımı gösterilir.
        for h in DEVAM_HAFTALARI.get((duzey, ders), ()):
            if h not in hedef and h - 1 in hedef:
                hedef[h] = hedef[h - 1]

    cikti_json = {
        "_kaynak": f"{plan_dizini.name} ({len(okunan)} plan dosyası/sayfası okundu)",
        "_uretim_araci": URETIM_ARACI,
        "haftalar": {str(h): p.isoformat() for h, p in sorted(takvim.items())},
        "kazanimlar": {
            str(d): {ders: {str(h): m for h, m in sorted(hf.items())}
                     for ders, hf in sorted(sonuc[d].items()) if hf}
            for d in sorted(sonuc)
        },
    }
    cikti.parent.mkdir(parents=True, exist_ok=True)
    gecici = cikti.with_name(cikti.name + ".tmp")
    gecici.write_text(json.dumps(cikti_json, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(gecici, cikti)

    # --- Rapor ---
    print(f"Çıktı: {cikti}")
    print("\n== KAPSAM (gerekli düzey/ders -> bulundu/yok) ==")
    destek_yok_map = {(d, s): n for d, s, _y, n in destek_yok}
    eslenen_ders = {(e[1], e[2]) for e in ESLEME}
    for duzey, dersler in GEREKLI.items():
        for ders in dersler:
            hf = sonuc.get(duzey, {}).get(ders, {})
            if hf:
                print(f"  {duzey:>2} {ders:<34} ✓ {len(hf)} hafta")
            elif (duzey, ders) in destek_yok_map:
                print(f"  {duzey:>2} {ders:<34} ✗ {destek_yok_map[(duzey, ders)]}")
            elif (duzey, ders) in eslenen_ders:
                print(f"  {duzey:>2} {ders:<34} ✗ plan okundu ama kazanım çıkmadı")
            else:
                print(f"  {duzey:>2} {ders:<34} ✗ plan dosyası yok")
    fazla = [(d, s) for d in sonuc for s in sonuc[d] if sonuc[d][s] and s not in GEREKLI.get(d, [])]
    if fazla:
        print("  (çizelge dışı bulunanlar:", fazla, ")")

    print("\n== TAKVİM ==")
    print(f"  {len(takvim)} hafta; 1. hafta = {takvim.get(1)} (beklenen {OKUL_YILI_BASLANGICI})")
    onceki = None
    for h, p in sorted(takvim.items()):
        if onceki and (p - onceki[1]).days != 7:
            print(f"  tatil/boşluk: hafta {onceki[0]} ({onceki[1]}) -> hafta {h} ({p}): {(p - onceki[1]).days // 7 - 1} hafta atlandı")
        onceki = (h, p)
    eksik = [h for h in range(1, max(takvim) + 1) if h not in takvim] if takvim else []
    print(f"  takvimde etiketi olmayan hafta no: {eksik or 'yok'}")
    print(f"  planlar arası anlaşmazlık: {len(anlasmazlik)} hafta-oyu")
    gruplar = defaultdict(list)
    for kaynak, hafta, kazanan, p, oy, n in anlasmazlik:
        gruplar[kaynak].append((hafta, kazanan, p, oy))
    for kaynak, liste in gruplar.items():
        haftalar_ = [h for h, *_ in liste]
        ornek = liste[0]
        print(f"   - {', '.join(kaynak)}: {len(liste)} haftada çoğunluktan ayrı "
              f"(hafta {min(haftalar_)}-{max(haftalar_)}; örn. hafta {ornek[0]}: çoğunluk {ornek[1]} x{ornek[3]}, "
              f"bu plan {ornek[2]}) — tatil haftalarını da numaralıyor")
    for e in elenen_haftalar:
        print("  takvimden elenen (az oy):", e)
    for s in sorted(set(tarih_sorunlari))[:20]:
        print("  tarih sorunu:", s)
    if celiskiler:
        print(f"\n== HAFTA/TARİH ÇELİŞKİLERİ ({len(celiskiler)}) ==")
        ozet = Counter(c.split(":")[0] + " | " + ("etiket!=tarih (tarih esas)" if "tarih esas" in c else "tatil/takvim dışı satır atlandı")
                       for c in set(celiskiler))
        for anahtar, n in sorted(ozet.items()):
            print(f"  {anahtar}: {n}")
    if etiketsiz:
        print("\n== HAFTA ETİKETİ OKUNAMAYAN KAZANIMLI SATIRLAR (atlandı) ==")
        for (d, s), n in sorted(etiketsiz.items()):
            print(f"  {d}/{s}: {n} satır")
    if destek_yok:
        print("\n== DESTEKLENMEYEN / OKUNAMAYAN ==")
        for d, s, y, n in destek_yok:
            print(f"  {d}/{s}  {y}: {n}")
    print("\n== ATLANAN DOSYALAR ==")
    for y, n in sorted(ATLANAN.items()):
        print(f"  {y}: {n}")
    for n in notlar:
        print("  not:", n)
    if eslenmemis:
        print("\n== EŞLENMEMİŞ DOSYALAR (tabloda yok!) ==")
        for y in eslenmemis:
            print("  ", y)
    if kayip_dosya:
        print("\n== ESLEME'de olup dizinde bulunmayan ==")
        for y in kayip_dosya:
            print("  ", y)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Yıllık planlardan haftalık kazanım JSON'u üretir.")
    ap.add_argument("--plan-dir", type=Path, default=VARSAYILAN_PLAN_DIZINI)
    ap.add_argument("--cikti", type=Path, default=VARSAYILAN_CIKTI)
    args = ap.parse_args()
    return calisma(args.plan_dir, args.cikti)


if __name__ == "__main__":
    sys.exit(main())
