"""soruhavuzu/katki.py — öğretmen katkısı turu (soru-katki.timer, 2 dakikada bir; LLM yok).

1) okul `GET /api/soru-katki` → öğretmen kararları ('askida' LLM şıklı sorular → 'onayli'/'red') uygulanır.
2) Cevap anahtarlı çoktan seçmeli PDF'ler: sorular numaradan, şıklar A) B) C) D) (E) işaretlerinden ayrılır,
   her soru kırpılıp görseli `soru_gorsel`'e yazılır, anahtarla eşlenir ve tek transaction'da 'onayli' girer.
   Soru sayısı anahtarla tutmazsa ya da bir sorunun şıkları bulunamazsa hiçbir soru yazılmaz; neden okula döner.
Çalıştırma (kökten): server/venv/bin/python -m soruhavuzu.katki
"""
import hashlib
import io
import json
import re
import urllib.request
from collections import Counter

import psycopg2
import pymupdf
from PIL import Image
from psycopg2.extras import Json

from soruhavuzu import okul_bildirim

TABAN = "http://127.0.0.1:9090"
GORSEL_YER = "Soruyu görselden inceleyiniz."  # tahta arenası bu metinli soruları göstermez
SORU_BAS = re.compile(r"^\s*(\d{1,3})\s*[.)]\s*(.*)$")
ANAHTAR_BASLIK = re.compile(r"CEVAP\s+ANAHTARI", re.I)
CIFT = re.compile(r"(\d{1,3})\s*[-.):]?\s*([A-E])(?![A-Za-zçğıöşüÇĞİÖŞÜ])")
# Görsele bağlı soru: "şekildeki/grafiğe göre" vb. ("bu şekilde kullanılmıştır" gibi zarflar sayılmaz).
GORSEL_ATIF = re.compile(
    r"şekil(?:deki|lerdeki|de gösteril|de veril|e göre|lere göre|\s*[\dIVX]+)|grafi[kğ]|tablo|görsel(?:de|e göre)|resim(?:de|deki)|harita|diyagram",
    re.I,
)
SAYFA_GEC = re.compile(r"(Diğer|Sonraki) sayfaya geçiniz\.?", re.I)
SIK = re.compile(r"(?:(?<=\s)|^)([A-E])\s*[).]\s*")


class KatkiHatasi(ValueError):
    pass


def _istek(yol: str, veri: dict | None = None, zaman_asimi: int = 60) -> bytes:
    istek = urllib.request.Request(
        TABAN + yol,
        data=None if veri is None else json.dumps(veri).encode("utf-8"),
        headers={"X-Soru-Anahtar": okul_bildirim.anahtar(), "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as r:
        return r.read()


def _satirlar(belge) -> list[dict]:
    """Okuma sırasında satırlar: sayfa, sütun (iki sütunlu sayfada sol önce), y. Üst/alt bilgi (çoğu sayfada
    tekrar eden kenar satırı), kenardaki yalnız sayıdan oluşan satırlar (sayfa no) ve iri puntolu satırlar
    (filigran, kapak başlığı) atılır."""
    ham = []
    for pno, sayfa in enumerate(belge):
        orta = sayfa.rect.width / 2
        bas = len(ham)
        for blok in sayfa.get_text("dict")["blocks"]:
            for satir in blok.get("lines", []):
                metin = SAYFA_GEC.sub("", "".join(s["text"] for s in satir["spans"])).strip()
                if metin:
                    x0, y0, x1, y1 = satir["bbox"]
                    ham.append({"sayfa": pno, "sutun": int(x0 >= orta - 5), "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                                "metin": metin, "orta": orta, "boyut": max(s["size"] for s in satir["spans"]),
                                "kenar": y0 < sayfa.rect.height * 0.08 or y1 > sayfa.rect.height * 0.92})
        iki = sum(s["sutun"] for s in ham[bas:]) >= 5
        for s in ham[bas:]:
            s["iki_sutun"] = iki
    sayfa_sayisi = Counter(m for m, _ in {(re.sub(r"\d+", "#", s["metin"]), s["sayfa"]) for s in ham})
    esik = max(3, len(belge) // 2 + 1)
    boyutlar = sorted(s["boyut"] for s in ham) or [0]
    iri = boyutlar[len(boyutlar) // 2] * 2.5
    temiz = [s for s in ham if s["boyut"] < iri and not (s["kenar"] and re.fullmatch(r"\d{1,3}", s["metin"]))
             and not (s["kenar"] and len(belge) >= 3 and sayfa_sayisi[re.sub(r"\d+", "#", s["metin"])] >= esik)]
    temiz.sort(key=lambda s: (s["sayfa"], s["sutun"], s["y0"]))
    # Aynı hizadaki satırlar (yan yana dizilmiş şıklar) soldan sağa: y0 farkı ≤3 pt olanlar tek sıra.
    sira, cikti = [], []
    for s in temiz:
        if sira and (s["sayfa"], s["sutun"]) == (sira[0]["sayfa"], sira[0]["sutun"]) and s["y0"] - sira[0]["y0"] <= 3:
            sira.append(s)
        else:
            cikti += sorted(sira, key=lambda x: x["x0"])
            sira = [s]
    return cikti + sorted(sira, key=lambda x: x["x0"])


def anahtar_bul(satirlar: list[dict]) -> tuple[list[dict], str]:
    """'CEVAP ANAHTARI' başlığından sonrası soru metnine karışmaz; oradaki 1-A … çiftleri anahtar olur."""
    for i, s in enumerate(satirlar):
        if ANAHTAR_BASLIK.search(s["metin"]):
            ciftler = CIFT.findall(" ".join(x["metin"] for x in satirlar[i:]))
            sirali = {}
            for n, h in ciftler:
                sirali.setdefault(int(n), h)
            nolar = sorted(sirali)
            anahtar = "".join(sirali[n] for n in nolar) if nolar == list(range(1, len(nolar) + 1)) else ""
            return satirlar[:i], anahtar
    return satirlar, ""


def _siklar(metin: str) -> tuple[str, list[str]] | None:
    """Metindeki son A…D(E) şık zinciri → (kök, şıklar). Zincir yoksa None."""
    isaret = [(m.group(1), m.start(), m.end()) for m in SIK.finditer(metin)]
    for i in range(len(isaret) - 1, -1, -1):
        if isaret[i][0] != "A":
            continue
        zincir, beklenen = [isaret[i]], "B"
        for h, b, e in isaret[i + 1:]:
            if h == beklenen:
                zincir.append((h, b, e))
                beklenen = chr(ord(beklenen) + 1)
        if len(zincir) >= 4:
            zincir = zincir[:5]
            siklar = [metin[zincir[j][2]:(zincir[j + 1][1] if j + 1 < len(zincir) else len(metin))].strip()
                      for j in range(len(zincir))]
            return metin[: zincir[0][1]].strip(), siklar
    return None


def sorulari_ayir(satirlar: list[dict]) -> list[dict]:
    sorular, beklenen = [], 1
    for s in satirlar:
        m = SORU_BAS.match(s["metin"])
        if m and int(m.group(1)) == beklenen:
            sorular.append({"no": beklenen, "satirlar": [s]})
            beklenen += 1
        elif sorular:
            sorular[-1]["satirlar"].append(s)
    for q in sorular:
        ilk = SORU_BAS.match(q["satirlar"][0]["metin"]).group(2)
        q["metin"] = "\n".join([ilk] + [x["metin"] for x in q["satirlar"][1:]]).strip()
        sonuc = _siklar(q["metin"])
        if sonuc is None:
            raise KatkiHatasi(f"{q['no']}. sorunun A) B) C) D) şıkları bulunamadı.")
        q["kok"], q["siklar"] = sonuc
    return sorular


def gorsel(belge, satirlar: list[dict]) -> bytes:
    """Sorunun satırlarını (sayfa/sütun parçaları alt alta) sütun genişliğinde kırpar → PNG."""
    parcalar = {}
    for s in satirlar:
        parcalar.setdefault((s["sayfa"], s["sutun"]), []).append(s)
    resimler = []
    for (pno, sutun), ss in sorted(parcalar.items()):
        sayfa = belge[pno]
        x0, x1 = (ss[0]["orta"], sayfa.rect.width) if sutun else (0, ss[0]["orta"] if ss[0]["iki_sutun"] else sayfa.rect.width)
        alan = pymupdf.Rect(x0, max(0, min(x["y0"] for x in ss) - 4), x1, min(sayfa.rect.height, max(x["y1"] for x in ss) + 6))
        pix = sayfa.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=alan, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        kutu = img.convert("L").point(lambda v: 255 if v < 235 else 0).getbbox()
        resimler.append(img.crop((max(0, kutu[0] - 12), 0, min(img.width, kutu[2] + 12), img.height)) if kutu else img)
    gen = max(r.width for r in resimler)
    birlesik = Image.new("RGB", (gen, sum(r.height for r in resimler) + 16 * (len(resimler) - 1)), "white")
    y = 0
    for r in resimler:
        birlesik.paste(r, (0, y))
        y += r.height + 16
    cikti = io.BytesIO()
    birlesik.save(cikti, "PNG", optimize=True)
    return cikti.getvalue()


def hazirla(pdf: bytes, cevap: str) -> list[dict]:
    """PDF + anahtar ('ACBD…' ya da '' → PDF içinde aranır) → havuza yazılacak sorular. Tutarsızlıkta KatkiHatasi."""
    try:
        belge = pymupdf.open(stream=pdf, filetype="pdf")
    except Exception as e:
        raise KatkiHatasi("PDF açılamadı.") from e
    satirlar = _satirlar(belge)
    if sum(len(s["metin"]) for s in satirlar) < 100:
        raise KatkiHatasi("PDF'te seçilebilir metin yok (taranmış olabilir).")
    satirlar, pdf_anahtar = anahtar_bul(satirlar)
    cevap = cevap or pdf_anahtar
    if not cevap:
        raise KatkiHatasi("Cevap anahtarı yok: formdaki kutuya yazın ya da PDF'in sonuna 'CEVAP ANAHTARI' ekleyin.")
    sorular = sorulari_ayir(satirlar)
    if not sorular:
        raise KatkiHatasi("Numaralı soru bulunamadı (1. 2. 3. … biçiminde olmalı).")
    if len(sorular) != len(cevap):
        raise KatkiHatasi(f"PDF'te {len(sorular)} soru bulundu, cevap anahtarında {len(cevap)} cevap var.")
    cikti = []
    for q, harf in zip(sorular, cevap):
        dogru = ord(harf) - ord("A")
        if dogru >= len(q["siklar"]):
            raise KatkiHatasi(f"{q['no']}. sorunun cevabı {harf}, ama sorunun {len(q['siklar'])} şıkkı var.")
        kok = re.sub(r"\s+", " ", q["kok"])
        siklar = [re.sub(r"\s+", " ", x) for x in q["siklar"]]
        # Şekle/tabloya bağlı ya da şıkları resim olan soru yalnız görselden çözülür (tahtada gösterilmez).
        # Kesir/üs gibi alt alta dizilmiş matematik: harfsiz kısa satırlar metne bozuk çıkar → yalnız görsel.
        matematik = any(len(x["metin"]) <= 4 and not re.search(r"[^\W\d_]", x["metin"]) for x in q["satirlar"][1:])
        yalniz_gorsel = (len(kok) < 10 or GORSEL_ATIF.search(kok) or matematik or not all(siklar)
                         or len(set(siklar)) != len(siklar))
        cikti.append({
            "no": q["no"],
            "soru": GORSEL_YER if yalniz_gorsel else kok,
            "secenekler": [f"{'ABCDE'[i]} seçeneği" for i in range(len(siklar))] if yalniz_gorsel else siklar,
            "dogru_index": dogru,
            "kisa_cevap": (harf if yalniz_gorsel else siklar[dogru])[:80],
            "ham": q["metin"],
            "sayfa": q["satirlar"][0]["sayfa"] + 1,
            "gorsel": gorsel(belge, q["satirlar"]),
        })
    return cikti


def yaz(conn, katki: dict, sha: str, sorular: list[dict]) -> int:
    """Tek transaction; bu PDF daha önce eklendiyse KatkiHatasi (çift kayıt yok)."""
    etiket = f"{katki['baslik'][:80]} (öğretmen katkısı)"
    with conn, conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("katki:" + sha,))
        cur.execute("SELECT 1 FROM kaynak_birim WHERE anahtar LIKE %s LIMIT 1", (f"katki:{sha}:%",))
        if cur.fetchone():
            raise KatkiHatasi("Bu PDF daha önce havuza eklenmiş.")
        for s in sorular:
            cur.execute(
                "INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin, durum, islendi_at)"
                " VALUES ('kitap', %s, %s, %s, %s, %s, 'islendi', now()) RETURNING id",
                (f"katki:{sha}:{s['no']}", katki["ders"], katki["sinif"], f"{etiket}, {s['no']}. soru", s["ham"]),
            )
            bid = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO soru (birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler, dogru_index, zorluk,"
                " kaynak, durum, denetim_notu, denetim_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,2,%s,'onayli',%s,now())"
                " RETURNING id",
                (bid, katki["ders"], katki["sinif"], katki["baslik"][:80], s["soru"], s["kisa_cevap"],
                 Json(s["secenekler"]), s["dogru_index"], f"{etiket}, {s['no']}. soru", "öğretmen cevap anahtarı"),
            )
            cur.execute(
                "INSERT INTO soru_gorsel (soru_id, icerik, mime, kaynak_sha256, kaynak_sayfa) VALUES (%s,%s,'image/png',%s,%s)",
                (cur.fetchone()[0], psycopg2.Binary(s["gorsel"]), sha, s["sayfa"]),
            )
    return len(sorular)


def kararlari_uygula(conn, kararlar: list[dict]) -> int:
    """Yalnız 'ogretmen-acik:' kaynaklı 'askida' sorular değişir; diğer id'ler sessizce geçilir."""
    n = 0
    with conn, conn.cursor() as cur:
        for k in kararlar:
            cur.execute(
                "UPDATE soru SET durum = %s, denetim_notu = %s, denetim_at = now() WHERE id = %s AND durum = 'askida'"
                " AND birim_id IN (SELECT id FROM kaynak_birim WHERE anahtar LIKE 'ogretmen-acik:%%')",
                ("onayli" if k["karar"] == "onay" else "red", f"öğretmen {k['karar']}", int(k["soru_id"])),
            )
            n += cur.rowcount
    return n


def calistir(conn) -> dict:
    if not okul_bildirim.anahtar():
        return {"atlandi": "anahtar yok"}
    try:
        v = json.loads(_istek("/api/soru-katki"))
    except Exception as e:
        return {"atlandi": f"okul okunamadı: {type(e).__name__}"}
    ozet = {"karar": 0, "katki": []}
    if v["kararlar"]:
        ozet["karar"] = kararlari_uygula(conn, v["kararlar"])
        _istek("/api/soru-katki/kararlar", {"uygulandi": [k["soru_id"] for k in v["kararlar"]]})
    for k in v["katkilar"]:
        _istek(f"/api/soru-katki/{k['id']}/sonuc", {"durum": "isleniyor"})
        try:
            pdf = _istek(f"/api/soru-katki/{k['id']}/pdf", zaman_asimi=120)
            n = yaz(conn, k, hashlib.sha256(pdf).hexdigest(), hazirla(pdf, k["cevap"]))
            sonuc = {"durum": "bitti", "eklenen": n, "not": ""}
        except KatkiHatasi as e:
            sonuc = {"durum": "hata", "eklenen": 0, "not": str(e)}
        except Exception as e:  # beklenmeyen: ayrıntı loga, öğretmene genel metin
            conn.rollback()
            print(f"[katki] #{k['id']} {type(e).__name__}: {e}", flush=True)
            sonuc = {"durum": "hata", "eklenen": 0, "not": "PDF işlenemedi; yöneticiye bildirildi."}
        _istek(f"/api/soru-katki/{k['id']}/sonuc", sonuc)
        ozet["katki"].append({"id": k["id"], **sonuc})
    return ozet


def main():
    from soruhavuzu import vt

    conn = vt.baglan()
    try:
        print(f"[katki] {calistir(conn)}", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
