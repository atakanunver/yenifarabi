"""soruhavuzu/gorsel_sanatlar_aktar.py
9_sinif_gorsel_sanatlar_soru_bankasi.pdf dosyasındaki 18 soruyu ayrıştırır,
farabi.kazanim_test_soru ve soru_havuzu.soru tablolarına onaylı olarak ekler.
"""

import hashlib
import json
import logging
import re
import sys
from pathlib import Path

import fitz
import psycopg2

sys.path.insert(0, "/home/ata/farabi")
from soruhavuzu import dersler, sik

PDF_PATH = Path("/mnt/farabi-data/farabi/kazanim_test/9_sinif_gorsel_sanatlar_soru_bankasi.pdf")

ZORLUK_HARITASI = {
    # 1. Tema: Sanata Bakış
    1: 1, 2: 2, 3: 3, 4: 4,
    # 2. Tema: Çizgiden Boyuta
    5: 1, 6: 2, 7: 3, 8: 4, 9: 2, 10: 3,
    # 3. Tema: Zamanın İzinde Sanat
    11: 1, 12: 2, 13: 3, 14: 4,
    # 4. Tema: Sanat ve Teknoloji Evreni
    15: 1, 16: 2, 17: 3, 18: 4,
}

KISA_KONULAR = {
    1: "Sanata Bakış",
    2: "Sanata Bakış",
    3: "Sanata Bakış",
    4: "Sanata Bakış",
    5: "Çizgiden Boyuta",
    6: "Çizgiden Boyuta",
    7: "Çizgiden Boyuta",
    8: "Çizgiden Boyuta",
    9: "Çizgiden Boyuta",
    10: "Çizgiden Boyuta",
    11: "Zamanın İzinde Sanat",
    12: "Zamanın İzinde Sanat",
    13: "Zamanın İzinde Sanat",
    14: "Zamanın İzinde Sanat",
    15: "Sanat ve Teknoloji Evreni",
    16: "Sanat ve Teknoloji Evreni",
    17: "Sanat ve Teknoloji Evreni",
    18: "Sanat ve Teknoloji Evreni",
}

def parse_pdf():
    doc = fitz.open(PDF_PATH)
    # Sayfa 5: Cevap anahtarı
    p5_text = doc[4].get_text()
    lines = [l.strip() for l in p5_text.splitlines() if l.strip()]
    cevap_tablosu = {}
    for i in range(len(lines)):
        if lines[i].isdigit() and 1 <= int(lines[i]) <= 18:
            q_num = int(lines[i])
            if i + 3 < len(lines):
                cevap_tablosu[q_num] = {
                    "cevap": lines[i+1],
                    "konu": lines[i+2],
                    "kod": lines[i+3]
                }

    # Sayfa 1-4: Sorular
    pages_text = "\n".join(doc[i].get_text() for i in range(4))
    pattern = r"Soru\s+(\d+)\.\s*(.*?)(?=(?:Soru\s+\d+\.)|(?:CEVAP ANAHTARI)|$)"
    matches = list(re.finditer(pattern, pages_text, re.DOTALL))

    parsed = []
    pdf_bytes = PDF_PATH.read_bytes()
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()

    for m in matches:
        q_num = int(m.group(1))
        q_body = m.group(2).strip()
        first_opt = re.search(r"\bA\)\s*", q_body)
        if not first_opt:
            continue
        soru_metni = re.sub(r"\s+", " ", q_body[:first_opt.start()]).strip()
        opts_text = q_body[first_opt.start():]
        opt_matches = list(re.finditer(r"([A-E])\)\s*(.*?)(?=(?:[A-E]\))|$)", opts_text, re.DOTALL))
        secenekler = {om.group(1): re.sub(r"\s+", " ", om.group(2).strip()) for om in opt_matches}

        ans_info = cevap_tablosu.get(q_num, {})
        cevap_harfi = ans_info.get("cevap")
        konu = ans_info.get("konu", "Görsel Sanatlar")
        kazanim_kodu = ans_info.get("kod", "")

        parsed.append({
            "no": q_num,
            "soru": soru_metni,
            "secenekler": secenekler,
            "cevap": cevap_harfi,
            "konu": konu,
            "kisa_konu": KISA_KONULAR.get(q_num, "Görsel Sanatlar"),
            "kazanim_kodu": kazanim_kodu,
            "zorluk": ZORLUK_HARITASI.get(q_num, 2),
            "pdf_hash": pdf_hash,
        })

    return parsed


def aktar():
    sorular = parse_pdf()
    print(f"PDF'ten {len(sorular)} soru ayrıştırıldı.")

    farabi_conn = psycopg2.connect(host="127.0.0.1", dbname="farabi", user="farabi")
    havuz_conn = psycopg2.connect(host="127.0.0.1", dbname="soru_havuzu", user="farabi")

    # 1. farabi.kazanim_test_soru tablosundaki bozuk 9095'i temizle ve temiz 18 soruyu ekle
    with farabi_conn.cursor() as cur:
        cur.execute("DELETE FROM kazanim_test_soru WHERE kaynak_dosya = '9_sinif_gorsel_sanatlar_soru_bankasi.pdf';")
        print(f"farabi.kazanim_test_soru: Eski kayıtlar temizlendi ({cur.rowcount} satır silindi).")

        for s in sorular:
            cur.execute("""
                INSERT INTO kazanim_test_soru
                (kaynak_dosya, kaynak_hash, sinif, ders, konu, test_no, soru_no, soru_metni, secenekler, cevap)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                "9_sinif_gorsel_sanatlar_soru_bankasi.pdf",
                s["pdf_hash"],
                9,
                "Görsel Sanatlar",
                s["konu"],
                1,
                s["no"],
                s["soru"],
                json.dumps(s["secenekler"], ensure_ascii=False),
                s["cevap"]
            ))
        farabi_conn.commit()
        print(f"farabi.kazanim_test_soru: {len(sorular)} soru başarıyla kaydedildi.")

    # 2. soru_havuzu'na kaynak_birim ekle
    with havuz_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin, durum, islendi_at)
            VALUES ('kazanim', 'kazanim:9_sinif_gorsel_sanatlar_soru_bankasi.pdf:1', 'gorsel_sanatlar', 9,
                    '9. Sınıf Görsel Sanatlar Soru Bankası', 'MEB 9. Sınıf Görsel Sanatlar Dersi Soru Bankası',
                    'islendi', now())
            ON CONFLICT (anahtar) DO UPDATE SET durum = 'islendi'
            RETURNING id;
        """)
        birim_id = cur.fetchone()[0]

        # Eski varsa temizle
        cur.execute("DELETE FROM soru WHERE kaynak LIKE 'MEB Kazanım Testi: 9_sinif_gorsel_sanatlar_soru_bankasi.pdf%';")
        print(f"soru_havuzu.soru: Eski kayıtlar temizlendi ({cur.rowcount} satır silindi).")

        # 9, 10, 11, 12. sınıfların tamamı için ekle (tüm lise seviyelerinde oynanabilsin)
        toplam_eklenen = 0
        for sinif_duzeyi in [9, 10, 11, 12]:
            for s in sorular:
                dogru_metin = s["secenekler"][s["cevap"]]
                if s["cevap"] in ["A", "B", "C", "D"]:
                    secim = [s["secenekler"][k] for k in ["A", "B", "C", "D"]]
                else:
                    secim = [dogru_metin, s["secenekler"]["A"], s["secenekler"]["B"], s["secenekler"]["C"]]
                
                dogru_idx = secim.index(dogru_metin)
                kanonik_secenekler, yeni_dogru_idx = sik.kanonik_sira(s["soru"], secim, dogru_idx)

                kaynak_str = f"MEB Kazanım Testi: 9_sinif_gorsel_sanatlar_soru_bankasi.pdf (Test 1, Soru {s['no']})"

                cur.execute("""
                    INSERT INTO soru
                    (birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler, dogru_index, zorluk, kaynak, durum, olusturma, denetim_at, kullanim_sayisi)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'onayli', now(), now(), 0);
                """, (
                    birim_id,
                    "gorsel_sanatlar",
                    sinif_duzeyi,
                    s["kisa_konu"],
                    s["soru"],
                    dogru_metin,
                    json.dumps(kanonik_secenekler, ensure_ascii=False),
                    yeni_dogru_idx,
                    s["zorluk"],
                    kaynak_str,
                ))
                toplam_eklenen += 1

        havuz_conn.commit()
        print(f"soru_havuzu.soru: 9, 10, 11, 12. sınıflar için toplam {toplam_eklenen} soru başarıyla eklendi.")

    farabi_conn.close()
    havuz_conn.close()


if __name__ == "__main__":
    aktar()
