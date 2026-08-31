#!/usr/bin/env python3
"""
benchmark/kazanim_test_yukle.py — /mnt/farabi-data/farabi/kazanim_test/
altındaki MEB ÖDSGM kazanım testi PDF'lerini `kazanim_test_soru` tablosuna
yükler (şema: kazanim_test_schema.sql). Saf ayrıştırma mantığı
kazanim_test_parse.py'de; bu betik yalnızca dosya/DB/embedding I/O yapar
(embed_kitap.py'nin deseniyle tutarlı: aynı model, aynı CPU embed, aynı
psycopg2 execute_values batch yazımı).

Kapsam ve BİLİNÇLİ olarak DIŞARIDA bırakılanlar (2026-08-31):
- Yalnızca *_Cevap_Anahtari*.pdf DIŞINDAKİ dosyalar işlenir — cevap
  anahtarları ayrı bir betik gerektiriyor (bkz. kazanim_test_parse.py'nin
  cevap_anahtari_ayir'ı), o betik henüz yazılmadı çünkü dosya adından
  (ör. "01_Cembersel_Hareket-1.pdf" → "Test 1") güvenilir bir eşleştirme
  hâlâ doğrulanmadı — bazı dosyalarda "01_" öneki muhtemelen Test N sırasını
  kodluyor, bazılarında (12sinif_fizik_N.pdf gibi farklı adlandırılan bir
  ikinci seri) bu doğrulanmadı. `cevap` kolonu bu yüzden şimdilik NULL
  kalıyor — yanlış eşleşen bir cevap anahtarı, hiç cevap olmamasından
  daha kötü.
- `test_no` de aynı sebeple hesaplanmıyor, NULL kalıyor.
- Dosya adından/başlıktan sinif+ders çıkarılamayan ya da hiç soru
  ayrıştırılamayan dosyalar ATLANIR ve raporda ayrıca listelenir —
  sessizce çöp satır yazılmaz.
- **Kalite kapısı:** soru_no dizisi 1'den başlayıp aralıksız/tekrarsız
  artmayan dosyalar da atlanır — çok testli birleşik PDF'ler (ör.
  `*_ca_mayis*.pdf`) ve kimyada alt madde numaralarının ("1)", "2)") soru
  başlangıcıyla karışması bu dosyalarda soru sınırlarını bozuyor.
  2026-08-31'de ölçüldü: 207 dosyanın 173'ü bu testi geçti, 1903 soru,
  SIFIR eksik şıklı soru. Geri kalan ~30 dosya (fizik/kimya/matematik/
  edebiyat "mayıs" birleşik setleri + kimyanın çoğu) daha akıllı bir
  test-sınırı tespiti gerektiriyor, ayrı bir iş.

İlk gerçek çalıştırma (2026-08-31, --db-user farabi): 1476 yeni soru
yazıldı (Fizik 427, Matematik 385, Türk Dili ve Edebiyatı 360, Kimya 188,
DKAB 116 — hepsi 12. sınıf), 427 satır "zaten vardı" dedi — bunlar gerçek
kod hatası değil, klasördeki birebir aynı içerikli kopya dosyalar (ör.
"12sinif_matematik_7.pdf" ve "12sinif_matematik_7 (1).pdf") aynı
kaynak_hash+soru_no'yu üretti, UNIQUE kısıtı doğru şekilde ikinciyi attı.

Kullanım:
    venv/bin/python kazanim_test_yukle.py
    venv/bin/python kazanim_test_yukle.py --dry-run   # DB'ye yazmadan raporla
"""

import argparse
import hashlib
import os
from pathlib import Path

# Okul ağının SSL-inceleme sertifikası (MEB-CERT-TTVPN) bu makinenin
# certifi'sinde tanınmıyor, HuggingFace Hub'ın kendi güncellik kontrolü bu
# yüzden her config dosyası için 5 kez yeniden dener sonra yerel önbelleğe
# düşer (bkz. root CLAUDE.md'nin "Kritik düzeltme (2026-08-14)" notu — aynı
# kök neden, server tarafında zaten HF_HUB_OFFLINE=1 ile atlanıyor).
# bge-m3 embed_kitap.py'den beri zaten önbellekte, offline'a zarasız geçilir.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import fitz
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

from kazanim_test_parse import baslik_bilgisi_cikar, konu_cikar, sorulari_ayir

KAYNAK_DIZIN = Path("/mnt/farabi-data/farabi/kazanim_test")
MODEL_ADI = "BAAI/bge-m3"


def sha256_dosya(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for blok in iter(lambda: f.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def pdf_metni(yol: Path) -> tuple[str, str]:
    """(ilk_sayfa_metni, tam_metin) — sayfalar \\n ile birleştirilir."""
    doc = fitz.open(yol)
    sayfalar = [sayfa.get_text() for sayfa in doc]
    doc.close()
    ilk = sayfalar[0] if sayfalar else ""
    tam = "\n".join(sayfalar)
    return ilk, tam


def main() -> int:
    ap = argparse.ArgumentParser(description="kazanim_test/ PDF'lerini kazanim_test_soru'ya yükle")
    ap.add_argument("--dry-run", action="store_true", help="DB'ye yazma, yalnızca raporla")
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-name", default="farabi")
    ap.add_argument("--db-user", default="farabi")
    ap.add_argument("--batch", type=int, default=32)
    a = ap.parse_args()

    dosyalar = sorted(
        p for p in KAYNAK_DIZIN.glob("*.pdf")
        if "cevap" not in p.name.lower() and "anahtar" not in p.name.lower()
    )
    print(f"{len(dosyalar)} soru PDF'i bulundu (cevap anahtarları hariç).")

    conn = None
    if not a.dry_run:
        conn = psycopg2.connect(host=a.db_host, dbname=a.db_name, user=a.db_user)
        register_vector(conn)

    atlanan: list[tuple[str, str]] = []  # (dosya, sebep)
    tum_sorular: list[dict] = []  # DB'ye yazılacak satırlar (embedding hariç)

    for yol in dosyalar:
        try:
            ilk_sayfa, tam_metin = pdf_metni(yol)
        except Exception as e:
            atlanan.append((yol.name, f"PDF açılamadı: {e}"))
            continue

        sinif, ders = baslik_bilgisi_cikar(ilk_sayfa)
        if not ders:
            atlanan.append((yol.name, "başlıktan ders çıkarılamadı"))
            continue

        konu = konu_cikar(ilk_sayfa)
        sorular = sorulari_ayir(tam_metin)
        if not sorular:
            atlanan.append((yol.name, "hiç soru ayrıştırılamadı"))
            continue

        # Kalite kapısı (2026-08-31): bazı dosyalarda (çok testli birleşik
        # PDF'ler; kimyada "1)"/"2)" gibi alt madde numaralarının soru
        # başlangıcıyla karışması) soru_no dizisi 1'den başlayıp aralıksız
        # artmıyor — bu, aynı (kaynak_hash, soru_no) çiftinin birden fazla
        # kez üretildiği, dolayısıyla UNIQUE kısıtının çoğunu SESSİZCE
        # düşüreceği anlamına gelir. Böyle dosyalar şimdilik atlanıyor;
        # yanlış/eksik soru yazmaktan iyidir. Ölçüldü: 207 dosyanın 173'ü
        # bu testi geçiyor, geçenlerde SIFIR eksik şıklı soru var.
        no_dizisi = [s["soru_no"] for s in sorular]
        beklenen = list(range(no_dizisi[0], no_dizisi[0] + len(no_dizisi)))
        if no_dizisi != beklenen:
            atlanan.append((yol.name, "soru_no sırasız/tekrarlı (birden fazla test ya da yanlış bölünme)"))
            continue

        dosya_hash = sha256_dosya(yol)
        for s in sorular:
            tum_sorular.append({
                "kaynak_dosya": yol.name,
                "kaynak_hash": dosya_hash,
                "sinif": sinif,
                "ders": ders,
                "konu": konu,
                "test_no": None,
                "soru_no": s["soru_no"],
                "soru_metni": s["soru_metni"],
                "secenekler": s["secenekler"],
            })

    print(f"{len(dosyalar) - len(atlanan)} dosya ayrıştırıldı, {len(atlanan)} dosya atlandı, "
          f"{len(tum_sorular)} soru bulundu.")
    if atlanan:
        print("Atlanan dosyalar:")
        for ad, sebep in atlanan:
            print(f"  - {ad}: {sebep}")

    if a.dry_run or not tum_sorular:
        print("--dry-run: DB'ye yazılmadı." if a.dry_run else "Yazılacak soru yok.")
        return 0

    print(f"Tokenizer + model yükleniyor ({MODEL_ADI}, CPU)…")
    model = SentenceTransformer(MODEL_ADI, device="cpu")

    import json as _json

    yazilan = 0
    atlanan_conflict = 0
    try:
        with conn.cursor() as cur:
            for i in range(0, len(tum_sorular), a.batch):
                grup = tum_sorular[i:i + a.batch]
                metinler = [s["soru_metni"] for s in grup]
                gomme = model.encode(metinler, normalize_embeddings=True, show_progress_bar=False)
                for s, vektor in zip(grup, gomme):
                    cur.execute(
                        """
                        INSERT INTO kazanim_test_soru
                            (kaynak_dosya, kaynak_hash, sinif, ders, konu, test_no,
                             soru_no, soru_metni, secenekler, cevap, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s)
                        ON CONFLICT (kaynak_hash, soru_no) DO NOTHING
                        """,
                        (
                            s["kaynak_dosya"], s["kaynak_hash"], s["sinif"], s["ders"],
                            s["konu"], s["test_no"], s["soru_no"], s["soru_metni"],
                            _json.dumps(s["secenekler"], ensure_ascii=False) if s["secenekler"] else None,
                            vektor,
                        ),
                    )
                    if cur.rowcount:
                        yazilan += 1
                    else:
                        atlanan_conflict += 1
                conn.commit()
                print(f"  {min(i + a.batch, len(tum_sorular))}/{len(tum_sorular)} işlendi", end="\r")
        print(f"\nBitti. {yazilan} yeni soru yazıldı, {atlanan_conflict} zaten vardı (hash+soru_no eşleşti).")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
