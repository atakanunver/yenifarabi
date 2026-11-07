#!/usr/bin/env python3
"""Öğretmenin gönderdiği açık uçlu (çözümlü) soru PDF'ini çoktan seçmeli havuz sorusuna çevirir.

Adımlar (kökten, server venv'i):
  ayristir  PDF → manifest.json (soru + çözüm metni; 1..N eksiksiz değilse durur, LLM yok)
  donustur  manifest'teki her soruyu yerel `farabi` modeliyle 4 şıklı soruya çevirir (kaldığı yerden sürer)
  aktar     dönüştürülenleri havuza 'askida' yazar (--uygula olmadan yalnız kontrol); öğretmen onaylayınca 'onayli' olur

Şıklar LLM'den gelir: kurala göre oyunlara açılmadan önce öğretmen onayı şart, bu yüzden 'uretildi' değil
'askida' yazılır (AGY denetimi `uretildi` seçer, bu satırlara dokunmaz).
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

import httpx
import pymupdf

from soruhavuzu import sik, uretici

GURULTU = re.compile(
    r"kubilaykurnaz|biolimpiyat|^\s*Sayfa \d+\s*$|SINIF BİYOLOJİ|Esaslıdır|Kılavuzu|Filigran|"
    r"^\s*\d{1,3}\s*$|^\s*Öğrenci Cevabı|^\s*SORULAR\s*$|İki Sütun",
    re.I,
)
SORU = re.compile(r"^\s*SORU\s+(\d{1,3})\s*:?\s*(.*)$", re.I)
COZUM = re.compile(r"^\s*SORU\s+(\d{1,3})\s+ÇÖZÜMÜ\s*:?\s*(.*)$", re.I)
BOLUM = re.compile(r"^\s*(?:\d+\.\s*(?:ÜNİTE|BÖLÜM)\s*:\s*)?(\d+\.\d+)\.?\s+(\S.*)$", re.I)
ARA_BASLIK = re.compile(r"ÇÖZÜM(LER)?\b|CEVAP ANAHTARI")  # yalnız büyük harfli bölüm başlıkları
ETIKET = re.compile(r"^\s*(Bağlam|Soru|Açıklama)\s*:\s*", re.I)


def _satirlar(belge) -> list[str]:
    """Sayfa sayfa, sütun sırasıyla (sol sütun önce) gürültüsüz satırlar."""
    cikti = []
    for sayfa in belge:
        orta = sayfa.rect.width / 2
        bloklar = [b for b in sayfa.get_text("blocks") if b[6] == 0]
        bloklar.sort(key=lambda b: (b[0] >= orta - 10, b[1]))
        for b in bloklar:
            for s in b[4].splitlines():
                if s.strip() and not GURULTU.search(s):
                    cikti.append(s.strip())
    return cikti


def ayristir(pdf: Path) -> dict:
    belge = pymupdf.open(pdf)
    sorular, cozumler, bolum = {}, {}, ""
    hedef, no = None, None
    for s in _satirlar(belge):
        if m := COZUM.match(s):
            hedef, no = cozumler, int(m.group(1))
            hedef[no] = [m.group(2)] if m.group(2) else []
            continue
        if (m := SORU.match(s)) and not s.lower().startswith("soru:"):
            hedef, no = sorular, int(m.group(1))
            hedef[no] = {"konu": bolum, "metin": [m.group(2)] if m.group(2) else []}
            continue
        if ARA_BASLIK.search(s) and len(s) < 140:
            hedef = None
            continue
        if (m := BOLUM.match(s)) and len(s) < 140:
            bolum = re.sub(r"\s*\(SORULAR.*$|\s*—\s*ÇÖZÜMLER.*$", "", f"{m.group(1)} {m.group(2)}", flags=re.I).strip()
            hedef = None  # başlık soruya/çözüme karışmasın
            continue
        if hedef is sorular and no in sorular:
            sorular[no]["metin"].append(s)
        elif hedef is cozumler and no in cozumler:
            cozumler[no].append(s)
    n = len(sorular)
    if not n or sorted(sorular) != list(range(1, n + 1)) or sorted(cozumler) != list(range(1, n + 1)):
        raise ValueError(f"{pdf.name}: soru {len(sorular)}, çözüm {len(cozumler)}; 1..N eksiksiz değil")

    def temiz(parcalar):
        return re.sub(r"\s+", " ", " ".join(ETIKET.sub("", p) for p in parcalar)).strip()

    kayit = []
    for i in range(1, n + 1):
        soru, cozum = temiz(sorular[i]["metin"]), temiz(cozumler[i])
        if len(soru) < 30 or len(cozum) < 15:
            raise ValueError(f"{pdf.name}: {i}. soru ya da çözüm boş/çok kısa")
        kayit.append({"no": i, "konu": sorular[i]["konu"], "acik_soru": soru, "cozum": cozum})
    return {"pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "sorular": kayit}


SISTEM = (
    "Sen MEB lise biyoloji/fen öğretmenisin. Sana bir öğretmenin hazırladığı açık uçlu bağlam temelli soru ve "
    "onun çözümü verilecek. Bunu oyunlarda kullanılacak TEK bir 4 şıklı çoktan seçmeli soruya çevir.\n"
    "Kurallar:\n"
    "1. Bağlamı (senaryoyu) koru, kısaltabilirsin; soru kökünü tek bir şeyi soran çoktan seçmeli köke çevir.\n"
    "2. Doğru şık YALNIZCA verilen çözümden çıkmalı; çözümde olmayan bilgiyi doğru cevap yapma.\n"
    "3. Üç çeldirici öğrencilerin tipik kavram yanılgılarına dayansın; biri bile doğru olmasın.\n"
    "4. Şıklar kısa, benzer uzunlukta ve birbirinden farklı olsun; 'hepsi', 'hiçbiri', 'A ve B' kullanma.\n"
    "5. 'şekildeki', 'grafiğe göre', 'tabloya göre', 'görseldeki' gibi atıf yapma.\n"
    "6. Tek doğru cevaplı soruya çevrilemiyorsa uygun=false döndür.\n"
    'Yalnızca JSON: {"uygun": true, "soru": "...", "secenekler": ["...","...","...","..."], '
    '"dogru_index": 0, "kisa_cevap": "1-6 kelime", "zorluk": 1}'
)


def donustur_bir(k: dict, sinif: int, ders: str, ollama_url="http://127.0.0.1:11434") -> dict:
    govde = {
        "model": uretici.MODEL,
        "messages": [
            {"role": "system", "content": SISTEM},
            {"role": "user", "content": f"Sınıf: {sinif}\nDers: {ders}\nKonu: {k['konu']}\n\n"
                                        f"AÇIK UÇLU SORU:\n{k['acik_soru']}\n\nÇÖZÜM:\n{k['cozum']}"},
        ],
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.3, "num_predict": 1024},
    }
    with httpx.Client(timeout=240, trust_env=False) as c:
        r = c.post(f"{ollama_url}/api/chat", json=govde)
        if r.status_code == 500:
            r = c.post(f"{ollama_url}/api/chat", json=govde)
        r.raise_for_status()
    try:
        v = json.loads(r.json().get("message", {}).get("content", ""))
    except json.JSONDecodeError:
        return {"durum": "bozuk"}
    if not isinstance(v, dict) or not v.get("uygun"):
        return {"durum": "uygun_degil"}
    s = {"soru": v.get("soru"), "secenekler": v.get("secenekler"), "dogru_index": v.get("dogru_index"),
         "kisa_cevap": v.get("kisa_cevap"), "zorluk": v.get("zorluk")}
    if not uretici._gecerli(s) or len(s["secenekler"]) != 4:
        return {"durum": "gecersiz"}
    s["secenekler"] = [x.strip() for x in s["secenekler"]]
    s["dogru_index"], s["zorluk"] = int(s["dogru_index"]), int(s["zorluk"])
    s["kisa_cevap"] = s["kisa_cevap"].strip().lstrip(":;-–. ").strip()
    return {"durum": "tamam", **s}


def aktar(conn, manifest: dict) -> tuple[int, int, int]:
    """Tek transaction; aynı anahtar zaten varsa atlanır (tekrar çalıştırmak güvenli)."""
    m, sha = manifest, manifest["pdf_sha256"]
    eklenen = var = atlanan = 0
    with conn, conn.cursor() as cur:
        for k in m["sorular"]:
            d = k.get("mc") or {}
            if d.get("durum") != "tamam":
                atlanan += 1
                continue
            anahtar = f"ogretmen-acik:{sha}:{k['no']}"
            etiket = f"{m['kaynak']}, {m['sinif']}. sınıf {k['no']}. soru"
            cur.execute(
                "INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin, durum, islendi_at)"
                " VALUES ('kitap', %s, %s, %s, %s, %s, 'islendi', now()) ON CONFLICT (anahtar) DO NOTHING RETURNING id",
                (anahtar, m["ders"], m["sinif"], etiket, f"{k['acik_soru']}\n\nÇözüm: {k['cozum']}"),
            )
            satir = cur.fetchone()
            if not satir:
                var += 1
                continue
            secenekler, dogru = sik.kanonik_sira(d["soru"], d["secenekler"], d["dogru_index"])
            cur.execute(
                "INSERT INTO soru (birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler, dogru_index, zorluk,"
                " kaynak, durum, denetim_notu) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'askida',%s)",
                (satir[0], m["ders"], m["sinif"], k["konu"] or m["ders"], d["soru"], d["kisa_cevap"],
                 json.dumps(secenekler, ensure_ascii=False), dogru, d["zorluk"], etiket,
                 "öğretmen onayı bekliyor (şıklar LLM ile üretildi)"),
            )
            eklenen += 1
    return eklenen, var, atlanan


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    alt = p.add_subparsers(dest="komut", required=True)
    a = alt.add_parser("ayristir")
    a.add_argument("pdf", type=Path)
    a.add_argument("--manifest", type=Path, required=True)
    a.add_argument("--sinif", type=int, required=True, choices=(9, 10, 11, 12))
    a.add_argument("--ders", required=True, choices=sorted(uretici.DERSLER))
    a.add_argument("--kaynak", required=True, help="Kaynak etiketi, örn. 'Kubilay Kurnaz 100 soru'")
    d = alt.add_parser("donustur")
    d.add_argument("--manifest", type=Path, required=True)
    t = alt.add_parser("aktar")
    t.add_argument("--manifest", type=Path, required=True)
    t.add_argument("--uygula", action="store_true")
    args = p.parse_args()

    if args.komut == "ayristir":
        if args.manifest.exists():
            p.error("manifest zaten var (donustur ilerlemesi silinmesin)")
        m = {**ayristir(args.pdf), "sinif": args.sinif, "ders": args.ders, "kaynak": args.kaynak}
        args.manifest.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(m['sorular'])} soru + çözüm ayrıştırıldı → {args.manifest}")
        return
    m = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.komut == "donustur":
        for k in m["sorular"]:
            if (k.get("mc") or {}).get("durum") == "tamam":
                continue
            try:
                k["mc"] = donustur_bir(k, m["sinif"], m["ders"])
            except httpx.HTTPError as e:
                k["mc"] = {"durum": "hata", "not": f"{type(e).__name__}"}
            args.manifest.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[{k['no']}] {k['mc']['durum']}", flush=True)
        say = {}
        for k in m["sorular"]:
            say[k["mc"]["durum"]] = say.get(k["mc"]["durum"], 0) + 1
        print("özet:", say)
        return
    hazir = sum((k.get("mc") or {}).get("durum") == "tamam" for k in m["sorular"])
    if not args.uygula:
        print(f"{hazir}/{len(m['sorular'])} soru aktarıma hazır; veritabanına yazılmadı.")
        return
    from soruhavuzu import vt
    conn = vt.baglan()
    try:
        print("eklenen={} mevcut={} atlanan={}".format(*aktar(conn, m)))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
