"""soruhavuzu/maarif_11_mat_aktar.py — 11. Sınıf Maarif Matematik Soru Bankası'ndan
metin tabanlı soruları ayrıştırır ve soru_havuzu veritabanına aktarır.

Grafik, şekil ve tablo içeren sorular filtrelenir; yalnızca metinle çözülebilen,
temiz ve cevap anahtarı doğrulanmış sorular aktarılır.
"""

import json
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
import psycopg2

sys.path.insert(0, "/home/ata/farabi")
from soruhavuzu import sik  # noqa: I001



logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("maarif_11_mat")

PDF_PATH = Path("/mnt/farabi-data/farabi/kitaplar/11.SINIF MAARIF SORU BANKASI MATEMATİK.pdf")

# Grafik / tablo / şekil içeren soruları elemek için regex desenleri
FORBIDDEN_PATTERNS = [
    # Şekil / Geometri çizimi içeren sorular (Türkçe 'bir şekilde' zarfını hariç tutar)
    r"şekildeki\b",
    r"şekle\s+göre\b",
    r"şekilde\s+verilen\b",
    r"şekilde\s+gösterilen\b",
    r"şekilde\s+bir\b",
    r"yandaki\s+şekilde\b",
    r"aşağıdaki\s+şekilde\b",
    r"yukarıdaki\s+şekilde\b",
    r"şekil\s*[-–]?\s*[0-9]+",
    r"(?m)^\s*şekilde\b",
    # Grafik referansları
    r"aşağıdaki\s+grafik",
    r"yukarıdaki\s+grafik",
    r"yandaki\s+grafik",
    r"grafiğe\s+göre\b",
    r"grafikte\s+verilen\b",
    r"grafikteki\b",
    r"nokta\s+grafiğinde\b",
    r"çizgi\s+grafiğinde\b",
    r"sütun\s+grafiğinde\b",
    r"daire\s+grafiğinde\b",
    r"grafiği\s+verilmiştir\b",
    r"grafiği\s+aşağıdakilerden\s+hangisidir\b",
    r"saçılma\s+grafiğinde\b",
    # Tablo referansları
    r"aşağıdaki\s+tablo",
    r"yukarıdaki\s+tablo",
    r"yandaki\s+tablo",
    r"tabloya\s+göre\b",
    r"tabloda\s+verilen\b",
    r"tablodaki\b",
    r"tablo\s*[-–]?\s*[0-9]+",
    # Çizim, kroki, koordinat düzlemi
    r"görseldeki\b",
    r"görsele\s+göre\b",
    r"krokideki\b",
    r"çizimdeki\b",
    r"şemadaki\b",
    r"boyalı\s+bölge\b",
    r"taralı\s+bölge\b",
    r"boyalı\s+alan\b",
    r"taralı\s+alan\b",
    r"dik\s+koordinat\s+düzleminde.*?verilmiştir",
]



def ocr_area(page, rect, psm=6, dpi=200):
    pix = page.get_pixmap(clip=rect, dpi=dpi)
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        pix.save(tmp.name)
        res = subprocess.run(
            ["tesseract", tmp.name, "stdout", "-l", "tur", "--psm", str(psm)],
            capture_output=True,
            text=True,
            check=False,
        )

        return res.stdout


def parse_footer_answers(page):
    w, h = page.rect.width, page.rect.height
    txt = ocr_area(page, fitz.Rect(0.02 * w, 0.80 * h, 0.98 * w, h), psm=6)
    
    # Harf ve rakam karışıklıklarını düzelt
    txt = txt.replace("|", "1").replace("l.", "1.").replace("I.", "1.")
    txt = re.sub(r"\bG([A-Ea-e])", r"6\1", txt)
    txt = re.sub(r"\bT([A-Ea-e])", r"7\1", txt)
    txt = re.sub(r"\bS([A-Ea-e])", r"5\1", txt)
    txt = re.sub(r"\bB([A-Ea-e])", r"8\1", txt)
    
    # '1.c' -> '1.C', '1E' -> '1.E'
    matches = re.findall(r"(\d{1,2})\s*[\.:\-\s]?\s*([A-Ea-e])\b", txt)
    ans = {}
    for k, v in matches:
        num = int(k)
        let = v.upper()
        if 1 <= num <= 25:
            ans[num] = let
    return ans


def temizle_metin(text):
    if not text:
        return ""
    text = text.strip()
    # Alt sayfa/logo kalıntılarını sil
    text = re.sub(r"\n+(?:ORİJİNAL.*|\d+|©|Tı|ki|WE|\<5).*$", "", text, flags=re.IGNORECASE)
    # Önceden gelen garip karakterler
    text = re.sub(r"^[;\-—\*\.\s]+", "", text)
    # Romen rakamı öncülleri (satır başı)
    text = re.sub(r"(?m)^[ilI\|]\.\s*", "I. ", text)
    text = re.sub(r"(?m)^[ilI\|]{2}\.\s*", "II. ", text)
    text = re.sub(r"(?m)^[ilI\|]{3}\.\s*", "III. ", text)
    text = re.sub(r"(?m)^[ilI\|][vV]\.\s*", "IV. ", text)
    
    # Şıklardaki Romen kombinasyonları
    text = re.sub(r"\b[Yy]alnız\s+[iılI\|]\b", "Yalnız I", text)
    text = re.sub(r"\b[Yy]alnız\s+[iılI\|]{2}\b", "Yalnız II", text)
    text = re.sub(r"\b[Yy]alnız\s+[iılI\|]{3}\b", "Yalnız III", text)
    
    # Romen kombinasyonları
    text = re.sub(r"\b[iılI\|]\s*ve\s*[ilI\|]\b", "I ve II", text, flags=re.IGNORECASE)
    text = re.sub(r"\bi\s*veli\b", "I ve II", text, flags=re.IGNORECASE)
    text = re.sub(r"\bivelli\b", "I ve III", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[iılI\|]\s*ve\s*[ilI\|]{3}\b", "I ve III", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[iılI\|]{2}\s*ve\s*[ilI\|]{3}\b", "II ve III", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[0-9]l\s*ve\s*l{2,3}\b", "II ve III", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[iılIİı\|]\s*,\s*[ilI\|]{1,2}\s*ve\s*[iılIİıh]{2,4}\b", "I, II ve III", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[iI],\s*[iI]{2}\s*ve\s*[iI]{3}\b", "I, II ve III", text, flags=re.IGNORECASE)
    
    # Satır sonundaki tek harfli marj / logo kalıntılarını temizle (örn. '... vardır? E' veya '... dir. z')
    text = re.sub(r"(?m)\s+[zgçşsüa-z]\s*$", "", text)
    # Çoklu boşlukları teke indir
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()



def is_graph_option(val):
    """Grafik eksenleri, tek harfli koordinatlar veya çizim parçalarını tespit eder."""
    lines = [l.strip() for l in val.splitlines() if l.strip()]
    if len(lines) >= 3:
        words = val.split()
        # Eğer çok satır var ama çok az kelime varsa (örn. koordinat ve sayılar)
        if len(words) < len(lines) * 2:
            return True
        # Yalnız 'x', 'y' veya eksen okları içeren satırlar
        if any(re.match(r"^[xy]\s*[\-—>]?$", l, re.IGNORECASE) for l in lines):
            return True
    return False


def is_valid_text_question(stem, opts):
    # Uzunluk kontrolü
    if len(stem) < 25:
        return False, "stem_too_short"
        
    # Şekil / grafik / tablo desenleri var mı?
    for pat in FORBIDDEN_PATTERNS:
        if re.search(pat, stem, re.IGNORECASE):
            return False, f"forbidden_pattern_{pat}"
            
    # Koordinat düzlemi, diyagram, açıölçer, birim çember çizimi var mı?
    if re.search(r"koordinat|diyagram|açıölçer|birim\s+çember|özdeş\s+kare", stem, re.IGNORECASE):
        return False, "visual_geometry_or_plot"
        
    # Seçeneklerin geçerliliği
    if len(opts) < 4:
        return False, "too_few_options"
        
    for val in opts.values():
        if not val or len(val) == 0:
            return False, "empty_option"

        if len(val) > 180:
            return False, "option_too_long"
        # Başka bir soru seçeneğin içine sızmış mı?
        if any(marker in val for marker in ["olduğuna göre", "kaçtır?", "hangisidir?", "değeri kaçtır"]):
            return False, "leaked_question_in_options"
        # Tablo matrisi şıkları mı?
        if any(w in val for w in ["Birebir olup", "Örten olup", "Pozitif değerli", "Negatif değerli", "Maksimum değeri"]):
            return False, "table_matrix_option"
        if is_graph_option(val):
            return False, "graph_option"
            
    # Soru gövdesinde kesik formül veya aşırı OCR bozulması var mı?
    if re.search(r"Ölçüsü\s+—\s+radyan", stem):
        return False, "broken_fraction_in_stem"
    if re.search(r"[~§_\\|\^]", stem):
        return False, "ocr_noise"
        
    return True, "ok"





def extract_questions_from_column(col_text, valid_qnums=None):
    # Eğer geçerli soru numaraları biliniyorsa sadece onları baz al
    if valid_qnums:
        nums_pat = "|".join(str(n) for n in sorted(valid_qnums))
        split_pat = r"\n(?=\s*(?:" + nums_pat + r")\.\s+(?!sınıf|dönem|bölüm|kat|adım|madde|yüzyıl|derece))"
    else:
        split_pat = r"\n(?=\s*\d{1,2}\.\s+(?!sınıf|dönem|bölüm|kat|adım|madde|yüzyıl|derece))"
        
    parts = re.split(split_pat, "\n" + col_text)
    questions = []
    
    for p in parts:
        p = p.strip()
        m = re.match(r"^(\d{1,2})\.\s+(.*)", p, re.DOTALL)
        if not m:
            continue
        qnum = int(m.group(1))
        if valid_qnums and qnum not in valid_qnums:
            continue
            
        body = m.group(2).strip()
        
        # Seçenekleri yakala: A) veya A. veya c) vb.
        opt_matches = list(re.finditer(r"\b([A-Ea-e])[\)\.]\s*", body))
        if len(opt_matches) < 4:
            continue
            
        stem = body[: opt_matches[0].start()].strip()
        stem = temizle_metin(stem)
        
        # Seçenekleri çıkar
        opts = {}
        for idx, om in enumerate(opt_matches):
            let = om.group(1).upper()
            start = om.end()
            end = opt_matches[idx + 1].start() if idx + 1 < len(opt_matches) else len(body)
            opt_val = body[start:end].strip()
            opt_val = temizle_metin(opt_val)
            opts[let] = opt_val
            
        questions.append((qnum, stem, opts))
    return questions



def reduce_to_4_choices(opts, correct_letter):
    """5 şıkkı (A-E) 4 şıkka indirger; doğru şıkkın korunmasını garanti eder."""
    if correct_letter not in opts:
        return None, None
        
    correct_text = opts[correct_letter].strip()
    if not correct_text:
        return None, None
        
    if correct_letter in ["A", "B", "C", "D"]:
        selected = [opts.get(k, "").strip() for k in ["A", "B", "C", "D"] if opts.get(k)]
        if len(selected) < 4 and "E" in opts:
            selected.append(opts["E"].strip())
    else:  # correct_letter == 'E'
        selected = [correct_text]
        for k in ["A", "B", "C", "D"]:
            v = opts.get(k, "").strip()
            if v and v != correct_text and len(selected) < 4:
                selected.append(v)
                
    if len(selected) < 4 or correct_text not in selected:
        return None, None
        
    selected = selected[:4]
    try:
        correct_idx = selected.index(correct_text)
    except ValueError:
        return None, None
        
    return selected, correct_idx


def process_test(doc, start_page, end_page, tema_adi, test_no):

    """Bir testteki (genellikle 2 sayfa) tüm saf metin sorularını çıkarır."""
    # 1. Cevap anahtarını bul (genellikle son sayfanın altında veya her sayfada)
    answers = {}
    for p in range(start_page, end_page + 1):
        ans_page = parse_footer_answers(doc[p - 1])
        answers.update(ans_page)
        
    log.info(f"Test {test_no} (Sayfa {start_page}-{end_page}): {len(answers)} cevap bulundu: {sorted(answers.items())}")
    
    test_questions = []
    valid_qnums = set(answers.keys()) if answers else None
    
    # 2. Her sayfadaki kolonları tara ve soruları çıkar
    for p in range(start_page, end_page + 1):
        page = doc[p - 1]
        w, h = page.rect.width, page.rect.height
        
        # Sol ve sağ kolon (alt sınırı footer'ın hemen üstüne çektik)
        left_text = ocr_area(page, fitz.Rect(0.04 * w, 0.08 * h, 0.50 * w, 0.885 * h), psm=6)
        right_text = ocr_area(page, fitz.Rect(0.50 * w, 0.08 * h, 0.96 * w, 0.885 * h), psm=6)
        
        col_qs = extract_questions_from_column(left_text, valid_qnums) + extract_questions_from_column(right_text, valid_qnums)

        
        for qnum, stem, opts in col_qs:
            # Cevap anahtarında bu soru var mı?
            if qnum not in answers:
                log.debug(f"Soru {qnum} cevap anahtarında yok, atlanıyor.")
                continue
                
            ok, reason = is_valid_text_question(stem, opts)
            if not ok:
                log.info(f"Soru {qnum} elendi: {reason}")
                continue
                
            correct_letter = answers[qnum]
            secenekler_4, dogru_idx = reduce_to_4_choices(opts, correct_letter)
            if not secenekler_4:
                log.info(f"Soru {qnum} 4 şıkka indirgenemedi (doğru: {correct_letter})")
                continue
                
            # Seçeneklerdeki satır sonlarını ve fazla boşlukları temizle
            secenekler_4 = [re.sub(r"\s+", " ", o).strip() for o in secenekler_4]
            dogru_metin = secenekler_4[dogru_idx]
            
            # Kanonik sıralama uygula
            kanonik_secenekler, yeni_dogru_idx = sik.kanonik_sira(stem, secenekler_4, dogru_idx)

            
            # Zorluk belirleme
            zorluk = ((qnum - 1) % 4) + 1
            kaynak_str = f"Orijinal 11. Sınıf Maarif Matematik: {tema_adi}, Test {test_no}, Soru {qnum}"
            
            q_data = {
                "sinif": 11,
                "ders": "matematik",
                "konu": tema_adi,
                "soru": stem,
                "secenekler": kanonik_secenekler,
                "dogru_index": yeni_dogru_idx,
                "kisa_cevap": dogru_metin,
                "zorluk": zorluk,
                "kaynak": kaynak_str,
                "birim_anahtar": f"kitap:maarif_mat_11:t{test_no}_p{start_page}",
                "birim_etiket": f"11. Sınıf Maarif Matematik: {tema_adi}, Test {test_no}",
            }
            test_questions.append(q_data)
            
    log.info(f"Test {test_no} sonucunda {len(test_questions)} geçerli metin sorusu çıkarıldı.")
    return test_questions


def sorulari_veritabanina_aktar(sorular, kuru=False):
    """Soru listesini PostgreSQL soru_havuzu veritabanına aktarır."""
    if not sorular:
        log.warning("Aktarılacak soru bulunamadı.")
        return {"aktarilan": 0, "atlanan": 0}
        
    conn = psycopg2.connect(host="127.0.0.1", dbname="soru_havuzu", user="farabi")
    
    # Mevcut soru metinlerini al (tekrar eklemeyi önlemek için)
    with conn.cursor() as cur:
        cur.execute("SELECT soru FROM soru WHERE sinif = 11 AND ders = 'matematik';")
        mevcut_sorular = {r[0].strip() for r in cur.fetchall()}
        
    aktarilan = 0
    atlanan = 0
    birim_cache = {}
    
    for s in sorular:
        soru_metin = s["soru"].strip()
        if soru_metin in mevcut_sorular:
            atlanan += 1
            continue
            
        b_key = s["birim_anahtar"]
        if not kuru:
            if b_key not in birim_cache:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin, durum, islendi_at)
                        VALUES ('kitap', %s, 'matematik', 11, %s, %s, 'islendi', now())
                        ON CONFLICT (anahtar) DO UPDATE SET durum = 'islendi'
                        RETURNING id;
                        """,
                        (b_key, s["birim_etiket"], f"Orijinal 11. Sınıf Maarif Matematik: {s['konu']}"),
                    )
                    birim_id = cur.fetchone()[0]
                    birim_cache[b_key] = birim_id
            else:
                birim_id = birim_cache[b_key]
                
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO soru (
                        birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler,
                        dogru_index, zorluk, kaynak, durum, denetim_notu, olusturma, denetim_at
                    ) VALUES (
                        %s, 'matematik', 11, %s, %s, %s, %s::jsonb,
                        %s, %s, %s, 'onayli', %s, now(), now()
                    );
                    """,
                    (
                        birim_id,
                        s["konu"],
                        s["soru"],
                        s["kisa_cevap"],
                        json.dumps(s["secenekler"], ensure_ascii=False),
                        s["dogru_index"],
                        s["zorluk"],
                        s["kaynak"],
                        "11. Sınıf Maarif Matematik Soru Bankası (Orijinal)",
                    ),
                )
        aktarilan += 1
        mevcut_sorular.add(soru_metin)
        
    if not kuru:
        conn.commit()
    conn.close()
    
    return {"toplam": len(sorular), "aktarilan": aktarilan, "atlanan": atlanan}


TEST_LISTESI = [
    # Tema 1: İstatistiksel Araştırma Süreçleri
    (7, 8, "İstatistiksel Araştırma Süreçleri - Temel Kabul", 1),
    (9, 10, "İstatistiksel Araştırma Süreci", 2),
    (11, 12, "İki Nicel Değişkenli Veri Toplama Planı", 3),
    (13, 14, "Veri Toplama ve Örneklem Seçimi", 4),
    (15, 16, "Nicel Değişkenler ve İlişki Türleri", 5),
    (17, 18, "İstatistiksel Araştırma Yöntemleri", 6),
    (19, 20, "Saçılma Grafikleri ve Eğilim Çıkarımı", 7),
    (21, 22, "İstatistik Beceri Temelli Tema Testi", 8),
    (23, 24, "İstatistik Beceri Temelli Tema Testi", 9),
    (25, 26, "İstatistik Beceri Temelli Tema Testi", 10),
    (27, 28, "İstatistik Beceri Temelli Tema Testi", 11),
    (29, 30, "İstatistik Beceri Temelli Tema Testi", 12),
    (31, 32, "İstatistik Bağlam Temelli Tema Testi", 13),
    (33, 34, "İstatistik Bağlam Temelli Tema Testi", 14),

    # Tema 3: Trigonometri
    (126, 127, "Trigonometri - Temel Kabul", 301),
    (128, 128, "Birim Çember", 302),
    (129, 129, "Yönlü Açılar", 303),
    (130, 130, "Açı Ölçü Birimleri", 304),
    (131, 132, "Esas Ölçü", 305),
    (133, 133, "Esas Ölçü", 306),
    (134, 134, "Trigonometrik Referans Fonksiyonlar", 307),
    (135, 135, "Trigonometrik Referans Fonksiyonlar", 308),
    (136, 137, "Trigonometrik Özdeşlikler", 309),
    (138, 138, "Trigonometrik Özdeşlikler", 310),
    (139, 139, "Trigonometrik Özdeşlikler", 311),
    (140, 140, "Trigonometrik Özdeşlikler", 312),
    (141, 141, "Trigonometrik Özdeşlikler", 313),
    (142, 143, "Periyodik Fonksiyonlar", 314),
    (145, 147, "Trigonometrik Fonksiyonların Nitel Özellikleri", 316),
    (148, 149, "Trigonometrik Fonksiyonların Nitel Özellikleri", 317),
    (150, 151, "Trigonometrik Fonksiyonların Nitel Özellikleri", 318),
    (152, 153, "Trigonometrik Fonksiyonların Nitel Özellikleri", 319),
    (154, 155, "Trigonometrik Özdeşlikler 2", 320),
    (156, 156, "Trigonometrik Özdeşlikler 3", 321),
    (157, 157, "Trigonometrik Denklemler", 322),
    (158, 158, "Trigonometrik Denklemler", 323),
    (159, 159, "Trigonometrik Denklemler", 324),
    (160, 162, "Trigonometri Beceri Temelli", 325),
    (163, 165, "Trigonometri Beceri Temelli", 326),
    (182, 183, "Trigonometri Bağlam Temelli", 327),

    # Tema 4: Üstel ve Logaritmik Fonksiyonlar
    (186, 187, "Üstel Fonksiyon - Temel Kabul", 401),
    (188, 189, "Üstel Referans Fonksiyonu", 402),
    (190, 191, "Üstel Fonksiyonların Nitel Özellikleri", 403),
    (192, 193, "Üstel Fonksiyonların Nitel Özellikleri", 404),
    (194, 195, "Üstel Fonksiyonların Nitel Özellikleri", 405),
    (196, 197, "Üstel Fonksiyonların Nitel Özellikleri", 406),
    (199, 202, "Üstel Fonksiyon Beceri Temelli", 407),
    (203, 205, "Logaritmik Referans Fonksiyonu", 408),
    (206, 208, "Logaritmik Referans Fonksiyonu", 409),
    (209, 211, "Logaritmik Referans Fonksiyonu", 410),
    (212, 213, "Logaritmik Referans Fonksiyonu", 411),
    (214, 215, "Logaritma İşlem Özellikleri", 412),
    (216, 217, "Logaritma İşlem Özellikleri", 413),
    (218, 218, "Logaritma İşlem Özellikleri", 414),
    (219, 220, "Üstel ve Logaritmik Denklemler", 415),
    (221, 222, "Logaritmik Eşitsizlikler", 416),
    (223, 224, "Logaritma Bilgi Temelli", 417),
    (225, 226, "Logaritma Bilgi Temelli", 418),
    (227, 229, "Logaritma Beceri Temelli", 419),
    (230, 232, "Logaritma Beceri Temelli", 420),
    (233, 235, "Logaritma Bağlam Temelli", 421),

    # Tema 5: Fonksiyonlar
    (238, 239, "Fonksiyonlar - Temel Kabul", 501),
    (240, 241, "Bileşke Fonksiyonun Tanım Kümesi", 502),
    (242, 243, "Bileşke Fonksiyonun Cebirsel Temsili", 503),
    (244, 245, "Bileşke Fonksiyonun Cebirsel Temsili", 504),
    (246, 247, "Bileşke Fonksiyonda Değer Bulma", 505),
    (248, 249, "Bileşke Fonksiyonda Değer Bulma", 506),
    (250, 251, "Bileşke Fonksiyonda Değer Bulma", 507),
    (252, 253, "Bileşke Fonksiyonun Görüntü Kümesi", 508),
    (254, 255, "Bileşke Fonksiyon Günlük Yaşam Problemleri", 509),
    (256, 257, "Bileşke Fonksiyonun Nitel Özellikleri", 510),
    (258, 260, "Bileşke Fonksiyon Beceri Temelli", 511),
    (268, 269, "Bileşke Fonksiyon Bağlam Temelli", 512),
    (270, 271, "Fonksiyonlarda Dört İşlem", 513),
    (272, 273, "Fonksiyonlarda Dört İşlem", 514),
    (274, 275, "Fonksiyonlarda Dört İşlem", 515),
    (276, 277, "Fonksiyonlarda Dört İşlem", 516),
    (278, 279, "Fonksiyonlarda Dört İşlem Problemleri", 517),
    (280, 282, "Fonksiyonlar Beceri Temelli", 518),
    (283, 285, "Fonksiyonlar Beceri Temelli", 519),
    (286, 288, "Fonksiyonlar Bağlam Temelli", 520),
]



JSON_PATH = Path("/home/ata/farabi/soruhavuzu/maarif_11_mat_sorular.json")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="11. Sınıf Maarif Matematik metin sorularını aktar")
    parser.add_argument("--kuru", action="store_true", help="DB'ye yazmadan sadece ayrıştır ve raporla")
    parser.add_argument("--test", type=int, help="Yalnızca belirtilen test numarasını çalıştır")
    parser.add_argument("--dosyadan", action="store_true", help="OCR yapmadan mevcut JSON dosyasından yükle")
    args = parser.parse_args()
    
    if args.dosyadan:
        if not JSON_PATH.exists():
            log.error(f"JSON dosyası bulunamadı: {JSON_PATH}")
            sys.exit(1)
        tum_sorular = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        log.info(f"{JSON_PATH} dosyasından {len(tum_sorular)} soru yüklendi.")
    else:
        if not PDF_PATH.exists():
            log.error(f"PDF dosyası bulunamadı: {PDF_PATH}")
            sys.exit(1)
            
        doc = fitz.open(PDF_PATH)
        log.info(f"PDF açıldı, toplam sayfa sayısı: {len(doc)}")
        
        hedef_testler = TEST_LISTESI
        if args.test:
            hedef_testler = [t for t in TEST_LISTESI if t[3] == args.test]
            if not hedef_testler:
                log.error(f"Test {args.test} tanımlı listede bulunamadı!")
                sys.exit(1)
                
        tum_sorular = []
        for start_p, end_p, tema_adi, test_no in hedef_testler:
            qs = process_test(doc, start_p, end_p, tema_adi, test_no)
            tum_sorular.extend(qs)
            
        log.info(f"Toplam {len(tum_sorular)} geçerli metin sorusu derlendi.")
        
        # Test filtresi yoksa JSON'a kaydet
        if not args.test:
            JSON_PATH.write_text(json.dumps(tum_sorular, ensure_ascii=False, indent=2), encoding="utf-8")
            log.info(f"Çıkarılan {len(tum_sorular)} soru {JSON_PATH} dosyasına kaydedildi.")
            
    # Dağılım ve örnekleri göster
    if tum_sorular:
        print("\n=== ÖRNEK SORULAR ===")
        for i, s in enumerate(tum_sorular[:3]):
            print(f"\n[Örnek {i+1}] Konu: {s['konu']} | Zorluk: {s['zorluk']}")
            print(f"Soru: {s['soru']}")
            print(f"Seçenekler: {s['secenekler']}")
            print(f"Doğru Cevap: {s['kisa_cevap']} (Index: {s['dogru_index']})")
            print(f"Kaynak: {s['kaynak']}")
            
    sonuc = sorulari_veritabanina_aktar(tum_sorular, kuru=args.kuru)
    print("\n=== İŞLEM SONUCU ===")
    print(f"Toplam çıkarılan soru: {sonuc['toplam']}")
    print(f"Aktarılan (yeni) soru: {sonuc['aktarilan']}")
    print(f"Atlanan (mevcut) soru: {sonuc['atlanan']}")
    if args.kuru:
        print("(--kuru modunda çalıştırıldı, DB'ye yazılmadı)")


if __name__ == "__main__":
    main()




