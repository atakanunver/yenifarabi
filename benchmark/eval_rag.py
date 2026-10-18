#!/usr/bin/env python3
"""benchmark/eval_rag.py — 2026-10-05 RAG Denetim ve Ölçüm Betiği.

/api/webui/ara mantığını farabi_agy veritabanı üzerinde koşturur,
Recall@1, Recall@4, Recall@15, rerank skoru dağılımı, "zayif" oranı ve süreleri ölçer.
"""

import json
import statistics
import sys
import time
from pathlib import Path

# server/ modüllerini ekle
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import db
from rag import RagMotoru
import uzak_model
import webui

EVAL_DOSYASI = Path(__file__).resolve().parent / "eval_set_20261005.json"


def main():
    db_name = "farabi_agy"
    db.baslat("127.0.0.1", db_name, "farabi")

    url, key = uzak_model.ayar_oku()
    if not url:
        raise SystemExit("Uzak model ayarları bulunamadı!")

    print(f"Uzak gömme ve rerank bağlanıyor: {url}...")
    embed_model, reranker = uzak_model.olustur(url, key)
    motor = RagMotoru(embed_model, reranker)
    webui.MOTOR = motor

    sorular = json.loads(EVAL_DOSYASI.read_text(encoding="utf-8"))
    print(f"{len(sorular)} soru üzerinde değerlendirme başlatılıyor ({db_name})...\n")

    sonuclar = []
    r1_sayisi = 0
    r4_sayisi = 0
    r15_sayisi = 0
    ok_sayisi = 0
    zayif_sayisi = 0
    hata_sayisi = 0
    top1_skorlar = []
    toplam_sureler = []

    for s in sorular:
        istek = webui.AraIstek(kapsam=s["kapsam"], soru=s["soru"], sinif=s.get("sinif"))
        t0 = time.perf_counter()
        yanit = webui.ara(istek)
        sure = int((time.perf_counter() - t0) * 1000)

        parcalar = yanit.get("parcalar", [])
        durum = yanit.get("durum")
        if durum == "ok":
            ok_sayisi += 1
        elif durum == "zayif":
            zayif_sayisi += 1
        else:
            hata_sayisi += 1

        top1_skor = parcalar[0]["skor"] if parcalar else 0.0
        if top1_skor > 0:
            top1_skorlar.append(top1_skor)
        toplam_sureler.append(sure)

        # Doğruluk kontrolü: beklenen içerik / kaynak / sayfa geldi mi?
        # Adaylarda hedef arama:
        bulundu_sira = None
        for idx, p in enumerate(parcalar, start=1):
            metin = p["metin"]
            kaynak = p["kaynak"]
            # Beklenen sayfa veya anahtar kelime eşleşmesi
            if s["kw"].lower() in metin.lower() or (s["beklenen_sayfa"] and f"s. {s['beklenen_sayfa']}" in kaynak):
                bulundu_sira = idx
                break

        if bulundu_sira == 1:
            r1_sayisi += 1
            r4_sayisi += 1
            r15_sayisi += 1
        elif bulundu_sira and bulundu_sira <= 4:
            r4_sayisi += 1
            r15_sayisi += 1
        elif bulundu_sira:
            r15_sayisi += 1

        sonuclar.append({
            "id": s["id"],
            "soru": s["soru"],
            "kapsam": s["kapsam"],
            "tur": s["tur"],
            "durum": durum,
            "top1_skor": top1_skor,
            "bulundu_sira": bulundu_sira,
            "sure_ms": sure,
            "parca_sayisi": len(parcalar),
            "ilk_kaynak": parcalar[0]["kaynak"] if parcalar else None
        })

        sira_str = f"Sıra: {bulundu_sira}" if bulundu_sira else "KAÇTI"
        print(f"[{s['id']:2d}] {s['tur']:6} | {durum:5} | Top-1: {top1_skor:.4f} | {sira_str:8} | {sure:4d}ms | {s['soru'][:55]}...")

    n = len(sorular)
    rapor = {
        "toplam_soru": n,
        "ok_orani": round(ok_sayisi / n, 4),
        "zayif_orani": round(zayif_sayisi / n, 4),
        "hata_orani": round(hata_sayisi / n, 4),
        "recall_1": round(r1_sayisi / n, 4),
        "recall_4": round(r4_sayisi / n, 4),
        "recall_15": round(r15_sayisi / n, 4),
        "ortalama_skor": round(statistics.mean(top1_skorlar), 4) if top1_skorlar else 0.0,
        "medyan_skor": round(statistics.median(top1_skorlar), 4) if top1_skorlar else 0.0,
        "min_skor": round(min(top1_skorlar), 4) if top1_skorlar else 0.0,
        "max_skor": round(max(top1_skorlar), 4) if top1_skorlar else 0.0,
        "ortalama_sure_ms": round(statistics.mean(toplam_sureler), 1),
        "medyan_sure_ms": round(statistics.median(toplam_sureler), 1),
        "detaylar": sonuclar
    }

    print("\n" + "=" * 50)
    print("ÖLÇÜM SONUÇLARI:")
    print(f"Toplam Soru:     {n}")
    print(f"Durum:           OK: {ok_sayisi} (%{rapor['ok_orani']*100:.1f}) | Zayıf: {zayif_sayisi} (%{rapor['zayif_orani']*100:.1f})")
    print(f"Recall@1:        {r1_sayisi} / {n} (%{rapor['recall_1']*100:.1f})")
    print(f"Recall@4:        {r4_sayisi} / {n} (%{rapor['recall_4']*100:.1f})")
    print(f"Recall@15:       {r15_sayisi} / {n} (%{rapor['recall_15']*100:.1f})")
    print(f"Top-1 Skor Dağ.: Ort={rapor['ortalama_skor']:.4f}, Medyan={rapor['medyan_skor']:.4f}, Min={rapor['min_skor']:.4f}, Max={rapor['max_skor']:.4f}")
    print(f"Gecikme (ms):    Ort={rapor['ortalama_sure_ms']}ms, Medyan={rapor['medyan_sure_ms']}ms")
    print("=" * 50)

    cikti_yolu = Path(__file__).resolve().parent / "reports" / f"taban_olcum_{int(time.time())}.json"
    cikti_yolu.write_text(json.dumps(rapor, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRapor kaydedildi: {cikti_yolu}")
    db.kapat()


if __name__ == "__main__":
    main()
