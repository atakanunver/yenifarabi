#!/usr/bin/env python3
"""server/idari_yukle.py — mevzuat klasörünü chunk_idari'ye yükler (2026-10-03).

Kaynak: /mnt/farabi-data/farabi/mudur/ (ALT KLASÖRLER HARİÇ — "OKUL GÜVENLİĞİ
AYLIK RAPORLAR" kişisel veri içerebilir, bilinçli olarak dışarıda).
- PDF: PyMuPDF sayfa metni; < 50 karakterlik sayfa tesseract'a (tur+eng, 300 dpi)
- jpeg/jpg/png: tesseract, tek sayfa
- docx: python-docx paragraf + tablo hücreleri, tek "sayfa"
Parçalama benchmark/embed_kitap.py::sayfayi_boluml ile AYNI (400 token,
%15 örtüşme, sayfa sınırı aşılmaz). Hash aynıysa belge atlanır.

Kullanım (server/ dizininden):
    venv/bin/python idari_yukle.py --kuru     # yalnızca listele, DB'ye yazma
    venv/bin/python idari_yukle.py
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path

KLASOR = Path("/mnt/farabi-data/farabi/mudur")
UZANTILAR = {".pdf", ".docx", ".jpeg", ".jpg", ".png"}
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
}
# Yüklenmeyecek dosyalar (silinmez) — 2026-10-03 kullanıcı kararı: 657'nin
# 2015 baskısı eski; güncel olan 657DEVLET.pdf (Mevzuat Bilgi Sistemi).
HARIC_DOSYALAR = {"657_devlet_memurlari_kanunu.pdf"}


def belge_adi(yol: Path) -> str:
    if yol.name in BILINEN_ADLAR:
        return BILINEN_ADLAR[yol.name]
    kelimeler = re.split(r"[\s_\-]+", yol.stem)
    return " ".join(k[:1].upper() + k[1:] for k in kelimeler if k)


def belgeleri_listele(klasor: Path) -> list[Path]:
    return sorted(p for p in klasor.iterdir()
                  if p.is_file() and p.suffix.lower() in UZANTILAR
                  and p.name not in HARIC_DOSYALAR)


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
    return [(1, ocr(yol.read_bytes()), True)]


def sayfayi_boluml(metin: str, tokenizer, chunk_token: int, ortusme: int) -> list[str]:
    """benchmark/embed_kitap.py::sayfayi_boluml ile BİREBİR aynı (ayrı venv/dizin
    olduğu için kopya). Değişirse ikisi birlikte değişir."""
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
    return {".pdf": "pdf", ".docx": "docx"}.get(yol.suffix.lower(), "gorsel")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--klasor", type=Path, default=KLASOR)
    ap.add_argument("--kuru", action="store_true", help="DB'ye yazma, yalnızca listele")
    a = ap.parse_args()

    belgeler = belgeleri_listele(a.klasor)
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
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ADI)
    model = uzak_model.toplu_gomme_modeli(MODEL_ADI)
    ortusme = int(CHUNK_TOKEN * ORTUSME_ORANI)
    conn = psycopg2.connect(host="127.0.0.1", dbname="farabi", user="farabi")
    register_vector(conn)
    for yol, sayfalar in okunan:
        h = _hash(yol)
        with conn.cursor() as cur:
            cur.execute("SELECT id, hash FROM idari_belge WHERE dosya_yolu = %s", (str(yol),))
            var = cur.fetchone()
        if var and var[1] == h:
            print(f"atlandı (değişmemiş): {yol.name}")
            continue
        chunklar = [(s, p) for s, m, _ in sayfalar if m.strip()
                    for p in sayfayi_boluml(m, tokenizer, CHUNK_TOKEN, ortusme) if p.strip()]
        vektorler = model.encode([p for _, p in chunklar], normalize_embeddings=True,
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
