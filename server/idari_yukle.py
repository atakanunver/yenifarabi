#!/usr/bin/env python3
"""server/idari_yukle.py — mevzuat klasörünü chunk_idari'ye yükler (2026-10-03).

Kaynak: /mnt/farabi-data/farabi/mudur/ (ALT KLASÖRLER HARİÇ — "OKUL GÜVENLİĞİ
AYLIK RAPORLAR" kişisel veri içerebilir, bilinçli olarak dışarıda).
- PDF: PyMuPDF sayfa metni; < 50 karakterlik sayfa tesseract'a (tur+eng, 300 dpi)
- jpeg/jpg/png: tesseract, tek sayfa
- docx: python-docx paragraf + tablo hücreleri, tek "sayfa"
- xlsx: openpyxl, her çalışma sayfası bir "sayfa", satırlar " | " ile (2026-10-05)
İdari kayıtlar yalnızca İdare grubunun "hepsi"/"idari" kapsamından aranır (webui.py).
Parçalama benchmark/embed_kitap.py::sayfayi_boluml ile AYNI (400 token,
%15 örtüşme, sayfa sınırı aşılmaz). Hash aynıysa belge atlanır.

Kullanım (server/ dizininden):
    venv/bin/python idari_yukle.py --kuru     # yalnızca listele, DB'ye yazma
    venv/bin/python idari_yukle.py
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
from pathlib import Path

KLASOR = Path("/mnt/farabi-data/farabi/mudur")
UZANTILAR = {".pdf", ".docx", ".jpeg", ".jpg", ".png", ".xlsx"}
OCR_ESIK_KARAKTER = 50
CHUNK_TOKEN = 400
ORTUSME_ORANI = 0.15
MODEL_ADI = "BAAI/bge-m3"

BILINEN_ADLAR = {
    "Ortaöğretim Kurumları Yönetmeliği (22.02.2025).pdf": "Ortaöğretim Kurumları Yönetmeliği (22.02.2025)",
    "resmi yazışma kuralları.pdf": "Resmî Yazışma Kuralları",
    "türkiye yüzyılı maarif modeli.pdf": "Türkiye Yüzyılı Maarif Modeli",
    "yazıı ve uygulamalı sınavlar yönergesi.pdf": "Yazılı ve Uygulamalı Sınavlar Yönergesi",
    "zümre yönerge 23-24.pdf": "Zümre Öğretmenler Kurulu Yönergesi (2023-24)",
    "iokbs 2024.pdf": "İOKBS 2024 Kılavuzu",
    "dyk.pdf": "Destekleme ve Yetiştirme Kursları (DYK) Yönergesi",
    "ekders saatlerine ilişkin karar.pdf": "Ek Ders Saatlerine İlişkin Karar",
    "e okul kullanım rehberi.pdf": "e-Okul Kullanım Rehberi",
    "kılık-kıyafet yönetmeliği.pdf": "Kılık-Kıyafet Yönetmeliği",
    "OKUL KIYAFETLERİ YÖNETMELİĞİ.docx": "Okul Kıyafetleri Yönetmeliği",
    "sınıf reh. görevleri yönetmelik.docx": "Sınıf Rehber Öğretmeni Görevleri",
    "egzersiz yönetmeliği.pdf": "Egzersiz Yönetmeliği",
    "su verimliliği yönetmeliği.pdf": "Su Verimliliği Yönetmeliği",
    "Ders Giriş Çıkış Saatleri Çizelgesi.pdf": "Ders Giriş-Çıkış Saatleri Çizelgesi",
    "NORM BRANS SAAT.jpeg": "Norm Branş Saatleri",
    "açık lise geçiş 2023.jpeg": "Açık Liseye Geçiş (2023)",
    "08142336_25145204_sosyal_etkinlikler_yonetmeligi.pdf": "Sosyal Etkinlikler Yönetmeliği",
    "11220411_millegitimbakanligiokulailebirligiyonetmeligi.pdf": "Okul-Aile Birliği Yönetmeliği",
    "657DEVLET.pdf": "657 Sayılı Devlet Memurları Kanunu",
    # 2026-10-05: Open WebUI sohbetinden (İdare) aktarılan çizelgeler
    "anadolu nöbet.pdf": "Nöbet Çizelgesi (Anadolu Lisesi)",
    "anadolu öğrt.pdf": "Öğretmen Ders Programları (Anadolu Lisesi)",
    "anadolu sınıf.pdf": "Sınıf Ders Programları (Anadolu Lisesi)",
    "çarşaflisteöğretmenler.pdf": "Çarşaf Liste — Öğretmenler",
    "çarşaflistesınıflar.pdf": "Çarşaf Liste — Sınıflar",
    "bilgi fomu detay20262027.docx": "Öğrenci Bilgi Formu Detay (2026-27)",
    "personel bilgi2026.xlsx": "Personel Bilgi Listesi (2026)",
    "Lise_Yıllık_RPDH_Planı.xlsx": "Lise Yıllık Rehberlik (RPDH) Planı",
}
# Yüklenmeyecek dosyalar (silinmez) — 2026-10-03 kullanıcı kararı: 657'nin
# 2015 baskısı eski; güncel olan 657DEVLET.pdf (Mevzuat Bilgi Sistemi).
HARIC_DOSYALAR = {"657_devlet_memurlari_kanunu.pdf"}
# Kişisel veri içeren idari dosyalar toplu indekslemede hariç tutulur.
KISISEL_VERI_DOSYALARI = {
    "bilgi fomu detay20262027.docx",
    "personel bilgi2026.xlsx",
}


def belge_adi(yol: Path) -> str:
    if yol.name in BILINEN_ADLAR:
        return BILINEN_ADLAR[yol.name]
    kelimeler = re.split(r"[\s_\-]+", yol.stem)
    return " ".join(k[:1].upper() + k[1:] for k in kelimeler if k)


def belgeleri_listele(klasor: Path, haric: set[str] | None = None) -> list[Path]:
    yasak = HARIC_DOSYALAR if haric is None else (HARIC_DOSYALAR | set(haric))
    return sorted(p for p in klasor.iterdir()
                  if p.is_file() and p.suffix.lower() in UZANTILAR
                  and p.name not in yasak)


def ocr_png(goruntu: bytes) -> str:
    """tesseract CLI — stdin'den görüntü, stdout'a metin. Yerel; buluta gitmez."""
    r = subprocess.run(["tesseract", "stdin", "stdout", "-l", "tur+eng", "--dpi", "300"],
                       input=goruntu, capture_output=True, timeout=120, check=False)
    return r.stdout.decode("utf-8", errors="replace").strip()


def sayfa_metinleri(yol: Path, ocr=ocr_png) -> list[tuple[int, str, bool]]:
    uz = yol.suffix.lower()
    if uz == ".pdf":
        import fitz
        sonuc = []
        with fitz.open(yol) as d:
            for i, sayfa in enumerate(d, start=1):
                metin = sayfa.get_text().strip()
                if len(metin) >= OCR_ESIK_KARAKTER:
                    sonuc.append((i, metin, False))
                else:
                    png = sayfa.get_pixmap(dpi=300).tobytes("png")
                    sonuc.append((i, ocr(png), True))
        return sonuc
    if uz == ".docx":
        import docx
        belge = docx.Document(str(yol))
        parcalar = [p.text for p in belge.paragraphs if p.text.strip()]
        for tablo in belge.tables:
            for satir in tablo.rows:
                hucreler = [h.text.strip() for h in satir.cells if h.text.strip()]
                if hucreler:
                    parcalar.append(" | ".join(hucreler))
        return [(1, "\n".join(parcalar), False)]
    if uz == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(yol, read_only=True, data_only=True)
        sonuc = []
        for i, ws in enumerate(wb.worksheets, start=1):
            satirlar = [" | ".join(str(h).strip() for h in r if h is not None and str(h).strip())
                        for r in ws.iter_rows(values_only=True)]
            metin = "\n".join(s for s in satirlar if s)
            sonuc.append((i, f"{ws.title}\n{metin}" if metin else "", False))
        wb.close()
        return sonuc
    return [(1, ocr(yol.read_bytes()), True)]


def temizle_metin(m: str) -> str:
    m = m.replace("\x00", "")
    m = m.replace("\xad", "")
    m = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", m)
    m = m.replace("\x08", "").replace("\ufffd", "")
    m = re.sub(r"[\r\t]", " ", m)
    m = re.sub(r" +", " ", m)
    return m.strip()


MADDE_RE = re.compile(
    r'(?:^|\n)\s*'
    r'(?P<tam_baslik>'
    r'(?:(?P<konu>[^\n:]{2,60}):\s*)?'
    r'(?P<madde>(?:Ek\s+|Geçici\s+)?(?:Madde|MADDE)\s+\d+[a-zçğıöşüA-ZÇĞİÖŞÜ0-9\/\-]*)'
    r'[^\n–\-]*(?:[–\-][^\n]*)?'
    r')',
    re.IGNORECASE
)


def _parcala_kati(metin: str, limit: int = 1200) -> list[str]:
    """Herhangi bir metni en fazla limit karakterlik parçalara böler,
    asla limiti aşmaz. Cümle (. ) veya satır (\n) sınırlarını tercih eder."""
    if len(metin) <= limit:
        return [metin] if metin.strip() else []
    parcalar = []
    kalan = metin
    while len(kalan) > limit:
        kesim = kalan[:limit]
        nokta = max(kesim.rfind("\n\n"), kesim.rfind("\n"), kesim.rfind(". "), kesim.rfind("; "))
        if nokta < limit // 3:
            nokta = kesim.rfind(" ")
        if nokta < limit // 3:
            nokta = limit
        parca = kalan[:nokta].strip()
        if parca:
            parcalar.append(parca)
        kalan = kalan[nokta:].strip()
    if kalan:
        parcalar.append(kalan)
    return parcalar


def belge_parcala(sayfalar: list[tuple[int, str, bool]], belge_ad: str, max_chars: int = 1300) -> list[tuple[int, str]]:
    """Mevzuat belgelerini madde sınırlarına, fıkralara ve paragraflara göre böler.
    Her parçanın başına [Belge Adı - Madde X: Konu] bağlam başlığını ekler.
    Hiçbir parçanın max_chars sınırını aşmamasını garanti eder."""
    chunks = []
    aktif_madde = None

    for sayfa_no, ham_metin, _ in sayfalar:
        metin = temizle_metin(ham_metin)
        if not metin:
            continue

        matches = list(MADDE_RE.finditer(metin))
        if not matches:
            prefix = f"[{belge_ad} - {aktif_madde} (Devamı)]\n" if aktif_madde else f"[{belge_ad}]\n"
            limit = max_chars - len(prefix)
            for sub in _parcala_kati(metin, limit):
                chunks.append((sayfa_no, f"{prefix}{sub}"))
            continue

        if matches[0].start() > 30:
            giris = metin[:matches[0].start()].strip()
            if giris:
                prefix = f"[{belge_ad} - {aktif_madde} (Devamı)]\n" if aktif_madde else f"[{belge_ad}]\n"
                limit = max_chars - len(prefix)
                for sub in _parcala_kati(giris, limit):
                    chunks.append((sayfa_no, f"{prefix}{sub}"))

        for i, m in enumerate(matches):
            baslangic = m.start()
            bitis = matches[i + 1].start() if i + 1 < len(matches) else len(metin)
            madde_metni = metin[baslangic:bitis].strip()
            baslik = m.group("tam_baslik").strip().replace("\n", " ")
            baslik_kisa = re.sub(r"\s+", " ", baslik)[:100]
            aktif_madde = baslik_kisa
            prefix = f"[{belge_ad} - {baslik_kisa}]\n"
            limit = max_chars - len(prefix)

            if len(madde_metni) <= limit:
                chunks.append((sayfa_no, f"{prefix}{madde_metni}"))
            else:
                for sub in _parcala_kati(madde_metni, limit):
                    chunks.append((sayfa_no, f"{prefix}{sub}"))

    return [(s, c.strip()) for s, c in chunks if c.strip()]


def sayfayi_boluml(metin: str, tokenizer, chunk_token: int, ortusme: int) -> list[str]:
    """Geriye dönük uyumluluk için korundu."""
    ids = tokenizer.encode(metin, add_special_tokens=False)
    if not ids:
        return []
    if len(ids) <= chunk_token:
        return [metin]
    adim = chunk_token - ortusme
    parcalar = []
    i = 0
    while i < len(ids):
        pencere = ids[i:i + chunk_token]
        parcalar.append(tokenizer.decode(pencere))
        if i + chunk_token >= len(ids):
            break
        i += adim
    return parcalar


def _hash(yol: Path) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def _tur(yol: Path) -> str:
    return {".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx"}.get(yol.suffix.lower(), "gorsel")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--klasor", type=Path, default=KLASOR)
    ap.add_argument("--db-name", default=os.environ.get("FARABI_DB_NAME", "farabi"))
    ap.add_argument("--zorla", action="store_true", help="Hash aynı olsa bile yeniden indeksle")
    ap.add_argument("--kuru", action="store_true", help="DB'ye yazma, yalnızca listele")
    ap.add_argument("--haric", nargs="*", default=list(KISISEL_VERI_DOSYALARI),
                    help="Hariç tutulacak dosya adları")
    ap.add_argument("--dosya", type=Path, nargs="+",
                    help="yalnızca bu dosyaları işle (belge_arsiv.py — Atos belge kayıt aracı)")
    a = ap.parse_args()

    haric_kume = set(a.haric) | HARIC_DOSYALAR
    belgeler = [p for p in a.dosya if p.is_file() and p.name not in haric_kume] if a.dosya else belgeleri_listele(a.klasor, haric=haric_kume)
    okunan = []
    for yol in belgeler:
        sayfalar = sayfa_metinleri(yol)
        ocrli = sum(1 for _, _, o in sayfalar if o)
        bos = [s for s, m, _ in sayfalar if not m.strip()]
        print(f"{belge_adi(yol)} | {len(sayfalar)} sayfa | OCR {ocrli} | boş {bos or '-'}")
        okunan.append((yol, sayfalar))
    if a.kuru:
        return 0

    import psycopg2
    from pgvector.psycopg2 import register_vector
    import uzak_model  # 2026-10-04: gömme bilgehan GPU'sunda

    model = uzak_model.toplu_gomme_modeli(MODEL_ADI)
    conn = psycopg2.connect(host="127.0.0.1", dbname=a.db_name, user="farabi")
    register_vector(conn)
    for yol, sayfalar in okunan:
        h = _hash(yol)
        with conn.cursor() as cur:
            cur.execute("SELECT id, hash FROM idari_belge WHERE dosya_yolu = %s", (str(yol),))
            var = cur.fetchone()
        if var and var[1] == h and not a.zorla:
            print(f"atlandı (değişmemiş): {yol.name}")
            continue

        chunklar = belge_parcala(sayfalar, belge_adi(yol))
        if not chunklar:
            continue
        metinler = [p for _, p in chunklar]
        vektorler = model.encode(metinler, normalize_embeddings=True,
                                 batch_size=16, show_progress_bar=False)
        with conn.cursor() as cur:
            if var:
                cur.execute("DELETE FROM idari_belge WHERE id = %s", (var[0],))
            cur.execute(
                "INSERT INTO idari_belge (ad, dosya_yolu, hash, tur) VALUES (%s, %s, %s, %s) RETURNING id",
                (belge_adi(yol), str(yol), h, _tur(yol)),
            )
            belge_id = cur.fetchone()[0]
            cur.executemany(
                "INSERT INTO chunk_idari (belge_id, sayfa_no, metin, embedding) VALUES (%s, %s, %s, %s)",
                [(belge_id, s, p, v) for (s, p), v in zip(chunklar, vektorler)],
            )
        conn.commit()
        print(f"yüklendi: {belge_adi(yol)} — {len(chunklar)} parça")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
