"""soruhavuzu/kalan_aktar.py — Henüz taranmamış 46 kazanım testini ayrıştırır,
farabi.kazanim_test_soru ve soru_havuzu.soru tablolarına dahil eder.
"""

import hashlib
import json
import logging
import re
import sys
from pathlib import Path

import fitz
import psycopg2

sys.path.insert(0, "/home/ata/farabi/benchmark")
import kazanim_test_parse as ktp
from soruhavuzu import dersler, sik

ca_dir = Path("/mnt/farabi-data/farabi/kazanim_test")


def parse_cevap_anahtari(p: Path) -> dict[int, dict[int, str]]:
    doc = fitz.open(p)
    text = "\n".join(page.get_text() for page in doc)
    tests = {}
    current_test = None
    for line in text.splitlines():
        line = line.strip()
        m_test = re.match(r"^Test\s+(\d+)", line, re.IGNORECASE)
        if m_test:
            current_test = int(m_test.group(1))
            tests.setdefault(current_test, {})
            continue
        m_ans = re.match(r"^(\d+)\.\s*([A-E])\b", line)
        if m_ans and current_test is not None:
            tests[current_test][int(m_ans.group(1))] = m_ans.group(2)
    return tests


def dosya_test_no(dosya_adi: str) -> int | None:
    if dosya_adi.startswith("mat_"):
        m = re.match(r"^mat_(\d+)", dosya_adi)
        if m:
            return int(m.group(1))
    m = re.match(r"^(?:12sinif_[a-z]+_(?:test_)?|)(\d+)", dosya_adi.lower())
    if m:
        return int(m.group(1))
    return None


def sha256_dosya(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for blok in iter(lambda: f.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def kalan_pdfleri_yukle():
    anahtarlar = {
        "biyoloji": parse_cevap_anahtari(ca_dir / "12sinif_biyoloji_biyo_ca_mayis_1.pdf"),
        "cografya": parse_cevap_anahtari(ca_dir / "12sinif_cografya_cog_ca_mayis.pdf"),
        "fizik": parse_cevap_anahtari(ca_dir / "12sinif_fizik_fiz_ca_mayis_1.pdf"),
        "ingilizce": parse_cevap_anahtari(ca_dir / "12sinif_ingilizce_ing_ca_mayis.pdf"),
        "kimya": parse_cevap_anahtari(ca_dir / "12sinif_kimya_kim_ca_mayis.pdf"),
        "matematik": parse_cevap_anahtari(ca_dir / "12sinif_matematik_mat_ca_mayis.pdf"),
        "tarih": parse_cevap_anahtari(ca_dir / "12sinif_tarih_tar_ca_mayis.pdf"),
        "din": parse_cevap_anahtari(ca_dir / "dkab_ca_mayis.pdf"),
        "edebiyat": parse_cevap_anahtari(ca_dir / "12.edebiyat.41_Cevap_Anahtari.pdf"),
    }

    farabi = psycopg2.connect(host="127.0.0.1", dbname="farabi", user="farabi")
    havuz = psycopg2.connect(host="127.0.0.1", dbname="soru_havuzu", user="farabi")

    with farabi.cursor() as cur:
        cur.execute("SELECT DISTINCT kaynak_dosya FROM kazanim_test_soru;")
        db_files = {r[0] for r in cur.fetchall()}

    all_files = sorted(ca_dir.glob("*.pdf"))
    kalan = [
        p
        for p in all_files
        if p.name not in db_files
        and not (
            "_ca_" in p.name.lower()
            or "cevap_anahtar" in p.name.lower()
            or p.name.startswith("20258269")
        )
    ]

    print(f"[kalan_aktar] İşlenecek {len(kalan)} PDF dosyası tespit edildi.")

    kts_eklenen = 0
    havuz_eklenen = 0
    birim_cache = {}

    for p in kalan:
        dosya_adi = p.name
        f_hash = sha256_dosya(p)
        sinif, ders_anahtar = dersler.dosyadan_cozumle(dosya_adi)
        test_no = dosya_test_no(dosya_adi) or 1
        sinif = sinif or 12
        ders_adi_str = ders_anahtar.capitalize() if ders_anahtar else "Genel"

        doc = fitz.open(p)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()

        sorular = ktp.sorulari_ayir(text)
        if not sorular:
            continue

        for q in sorular:
            sno = q["soru_no"]
            smetin = q["soru_metni"]
            secenekler = q["secenekler"] or {}

            # Cevap anahtarından cevap bul
            cevap = None
            if ders_anahtar in anahtarlar and test_no in anahtarlar[ders_anahtar]:
                cevap = anahtarlar[ders_anahtar][test_no].get(sno)

            # 1. farabi.kazanim_test_soru tablosuna ekle
            with farabi.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO kazanim_test_soru (
                        kaynak_dosya, kaynak_hash, sinif, ders, konu,
                        test_no, soru_no, soru_metni, secenekler, cevap
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT DO NOTHING RETURNING id;
                    """,
                    (
                        dosya_adi,
                        f_hash,
                        sinif,
                        ders_adi_str,
                        f"{ders_adi_str} Test {test_no}",
                        test_no,
                        sno,
                        smetin,
                        json.dumps(secenekler, ensure_ascii=False),
                        cevap,
                    ),
                )
                r = cur.fetchone()
                if r:
                    kts_eklenen += 1

            # 2. Eğer cevabı varsa ve şıkları geçerliyse soru_havuzu'na da ekle
            if cevap and isinstance(secenekler, dict) and cevap in secenekler:
                dogru_metin = secenekler[cevap].strip()
                if not dogru_metin:
                    continue

                if cevap in ["A", "B", "C", "D"]:
                    secim = [secenekler.get(k, "").strip() for k in ["A", "B", "C", "D"] if secenekler.get(k)]
                    if len(secim) < 4 and "E" in secenekler:
                        secim.append(secenekler["E"].strip())
                else:
                    secim = [dogru_metin]
                    for k in ["A", "B", "C", "D"]:
                        val = secenekler.get(k, "").strip()
                        if val and val != dogru_metin and len(secim) < 4:
                            secim.append(val)

                if len(secim) < 4 or dogru_metin not in secim:
                    continue

                secim = secim[:4]
                try:
                    d_idx = secim.index(dogru_metin)
                except ValueError:
                    continue

                kanonik_secim, yeni_d_idx = sik.kanonik_sira(smetin, secim, d_idx)
                zorluk = ((sno - 1) % 4) + 1
                kaynak_str = f"MEB Kazanım Testi: {dosya_adi} (Test {test_no}, Soru {sno})"
                birim_anahtar = f"kazanim:{dosya_adi}:{test_no}"

                if birim_anahtar not in birim_cache:
                    with havuz.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin, durum, islendi_at)
                            VALUES (%s, %s, %s, %s, %s, %s, 'islendi', now())
                            ON CONFLICT (anahtar) DO UPDATE SET durum = 'islendi'
                            RETURNING id;
                            """,
                            (
                                "kazanim",
                                birim_anahtar,
                                ders_anahtar,
                                sinif,
                                f"Kazanım Testi: {ders_adi_str} {sinif}, Test {test_no}",
                                f"{ders_adi_str} {sinif}. Sınıf MEB ÖDSGM Kazanım Kavrama Testi ({dosya_adi})",
                            ),
                        )
                        birim_id = cur.fetchone()[0]
                        birim_cache[birim_anahtar] = birim_id
                else:
                    birim_id = birim_cache[birim_anahtar]

                with havuz.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO soru (
                            birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler,
                            dogru_index, zorluk, kaynak, durum, denetim_notu, olusturma, denetim_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s::jsonb,
                            %s, %s, %s, 'onayli', %s, now(), now()
                        ) ON CONFLICT DO NOTHING RETURNING id;
                        """,
                        (
                            birim_id,
                            ders_anahtar,
                            sinif,
                            f"{ders_adi_str} Test {test_no}",
                            smetin,
                            dogru_metin,
                            json.dumps(kanonik_secim, ensure_ascii=False),
                            yeni_d_idx,
                            zorluk,
                            kaynak_str,
                            "MEB ÖDSGM Resmi Kazanım Kavrama Testi (Cevap Anahtarlı)",
                        ),
                    )
                    sr = cur.fetchone()
                    if sr:
                        havuz_eklenen += 1

    farabi.commit()
    havuz.commit()
    farabi.close()
    havuz.close()

    print(f"[kalan_aktar] farabi.kazanim_test_soru'ya {kts_eklenen} yeni soru eklendi.")
    print(f"[kalan_aktar] soru_havuzu.soru'ya {havuz_eklenen} onaylı MEB sorusu eklendi.")


if __name__ == "__main__":
    kalan_pdfleri_yukle()
