#!/usr/bin/env python3
"""
benchmark/recall_test.py — Faz 0a geçiş kriterleri harness'ı (docs/mimari.md §8,
"Faz 0a — geçiş kriterleri" / "Soru seti" bölümleri).

BU BETİK SORU SETİ ÜRETMEZ. 40+ soruluk gerçek soru seti (grup A/B/C) insan
işidir — mimari.md: "Soru seti — 3 grup, en az 40 soru ... insan işi, kod
değil". Bu betik yalnızca elindeki soru setini (JSON) alıp gerçek pgvector
verisi üzerinde Recall@4 / rerank / eşik / MRR metriklerini ölçer.

Soru seti formatı (JSON, liste):
[
  {"soru": "Mitozun sonucunda kaç hücre oluşur?", "dogru_sayfa": 84, "grup": "A"},
  {"soru": "Mitoz ile mayozun evrimsel avantajı nedir?", "dogru_sayfa": null, "grup": "C"}
]
  - "dogru_sayfa": null/yok  → grup C, "kitapta yok", doğru davranış YETERSİZ_KAYNAK.
  - "grup" opsiyonel ama varsa raporda ayrı kırılım verilir (mimari.md: "Her
    grup ayrı raporlanır").

Kullanım:
    venv/bin/python recall_test.py --sorular sorular.json --kitap-id 1
    venv/bin/python recall_test.py --sorular sorular.json --esik 0.35
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from sentence_transformers import SentenceTransformer, CrossEncoder

from ortak import baglan, kitap_idyi_coz

EMBED_MODEL = "BAAI/bge-m3"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"


def ilk_k_getir(conn, kitap_id: int, sorgu_vektor, k: int):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sayfa_no, metin, embedding <=> %s AS mesafe
            FROM chunk_egitim
            WHERE kitap_id = %s
            ORDER BY mesafe
            LIMIT %s
            """,
            (sorgu_vektor, kitap_id, k),
        )
        return cur.fetchall()  # [(sayfa_no, metin, mesafe), ...]


def main() -> int:
    ap = argparse.ArgumentParser(description="Faz 0a Recall@4 / rerank / eşik harness'ı")
    ap.add_argument("--sorular", required=True, help="Soru seti JSON dosyası")
    ap.add_argument("--kitap-id", type=int, default=None)
    ap.add_argument("--top-k", type=int, default=20, help="pgvector'dan çekilecek aday sayısı")
    ap.add_argument("--top-n", type=int, default=4, help="rerank sonrası nihai küme (Recall@N)")
    ap.add_argument("--esik", type=float, default=None,
                    help="Kosinüs benzerlik eşiği (0-1), rerank ÖNCESİ top-1 adaya "
                         "uygulanır. Verilmezse bu eşik metriği hesaplanmaz.")
    ap.add_argument("--esik-rerank", type=float, default=None,
                    help="Rerank SONRASI top-1 cross-encoder skoruna uygulanan eşik "
                         "(ham logit, 0-1 değil). mimari.md §8'in gerçek sırasıyla "
                         "uyumlu — eşik kontrolü adım 5, rerank'tan (adım 4) SONRA. "
                         "Verilmezse bu eşik metriği hesaplanmaz.")
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-name", default="farabi")
    ap.add_argument("--db-user", default="farabi")
    ap.add_argument("--rapor", default=None, help="Sonucu JSON olarak yaz (varsayılan: reports/<zaman>.json)")
    a = ap.parse_args()

    sorular = json.loads(Path(a.sorular).read_text(encoding="utf-8"))
    if not sorular:
        raise SystemExit("Soru seti boş.")

    conn = baglan(a.db_host, a.db_name, a.db_user)
    kitap_id = kitap_idyi_coz(conn, a.kitap_id)
    print(f"kitap_id={kitap_id} üzerinde {len(sorular)} soru test ediliyor…")

    print(f"Modeller yükleniyor: {EMBED_MODEL} (embed), {RERANK_MODEL} (rerank), CPU…")
    embed_model = SentenceTransformer(EMBED_MODEL, device="cpu")
    reranker = CrossEncoder(RERANK_MODEL, device="cpu")

    sonuclar = []
    for soru in sorular:
        metin = soru["soru"]
        dogru_sayfa = soru.get("dogru_sayfa")
        grup = soru.get("grup", "?")

        t0 = time.perf_counter()
        vektor = embed_model.encode(metin, normalize_embeddings=True)
        adaylar = ilk_k_getir(conn, kitap_id, vektor, a.top_k)
        t_arama = time.perf_counter() - t0

        if not adaylar:
            sonuclar.append({"soru": metin, "grup": grup, "dogru_sayfa": dogru_sayfa,
                              "hata": "aday yok"})
            continue

        en_iyi_benzerlik = 1 - adaylar[0][2]  # ilk aday, rerank'sız kosinüs benzerlik

        t1 = time.perf_counter()
        ciftler = [(metin, c[1]) for c in adaylar]
        skorlar = reranker.predict(ciftler)
        siralanmis = sorted(zip(adaylar, skorlar), key=lambda x: x[1], reverse=True)
        t_rerank = time.perf_counter() - t1

        siralanmis_sayfalar = [s[0][0] for s in siralanmis]
        top_n_sayfalar = siralanmis_sayfalar[:a.top_n]

        rank = siralanmis_sayfalar.index(dogru_sayfa) + 1 if dogru_sayfa in siralanmis_sayfalar else 0

        en_iyi_rerank_skoru = float(siralanmis[0][1])  # rerank SONRASI top-1 skoru (ham logit)

        kayit = {
            "soru": metin,
            "grup": grup,
            "dogru_sayfa": dogru_sayfa,
            "top_n_sayfalar": top_n_sayfalar,
            "en_iyi_benzerlik": round(en_iyi_benzerlik, 4),
            "en_iyi_rerank_skoru": round(en_iyi_rerank_skoru, 4),
            "sure_arama_sn": round(t_arama, 3),
            "sure_rerank_sn": round(t_rerank, 3),
        }

        if dogru_sayfa is not None:
            kayit["recall_at_n"] = dogru_sayfa in top_n_sayfalar
            kayit["rerank_top1_dogru"] = top_n_sayfalar[0] == dogru_sayfa if top_n_sayfalar else False
            kayit["mrr"] = 1 / rank if rank else 0.0
        else:
            kayit["recall_at_n"] = None
            kayit["rerank_top1_dogru"] = None
            kayit["mrr"] = None

        beklenen_yetersiz = dogru_sayfa is None
        if a.esik is not None:
            tahmin_yetersiz = en_iyi_benzerlik < a.esik
            kayit["esik_dogru_tespit"] = tahmin_yetersiz == beklenen_yetersiz
        if a.esik_rerank is not None:
            tahmin_yetersiz_rerank = en_iyi_rerank_skoru < a.esik_rerank
            kayit["esik_rerank_dogru_tespit"] = tahmin_yetersiz_rerank == beklenen_yetersiz

        sonuclar.append(kayit)
        print(f"  [{grup}] benzerlik={en_iyi_benzerlik:.3f} "
              f"recall@{a.top_n}={kayit['recall_at_n']} · {metin[:60]}")

    # ── Raporlama — mimari.md: "Her grup ayrı raporlanır" ──────────────────
    def ozet(liste, anahtar):
        degerler = [s[anahtar] for s in liste if s.get(anahtar) is not None]
        return sum(degerler) / len(degerler) if degerler else None

    gruplar = sorted(set(s["grup"] for s in sonuclar))
    print("\n=== SONUÇ (grup bazında) ===")
    genel_ozet = {}
    for g in gruplar + ["TOPLAM"]:
        alt = sonuclar if g == "TOPLAM" else [s for s in sonuclar if s["grup"] == g]
        if not alt:
            continue
        recall = ozet(alt, "recall_at_n")
        top1 = ozet(alt, "rerank_top1_dogru")
        mrr = ozet(alt, "mrr")
        esik_dogru = ozet(alt, "esik_dogru_tespit")
        esik_rerank_dogru = ozet(alt, "esik_rerank_dogru_tespit")
        sure = ozet(alt, "sure_arama_sn")
        genel_ozet[g] = {
            "n": len(alt),
            f"recall_at_{a.top_n}": recall,
            "rerank_top1_dogru_oran": top1,
            "mrr": mrr,
            "esik_dogru_tespit_oran": esik_dogru,
            "esik_rerank_dogru_tespit_oran": esik_rerank_dogru,
            "ortalama_arama_sn": sure,
        }
        print(f"[{g}] n={len(alt)} "
              f"recall@{a.top_n}={recall if recall is None else f'{recall:.0%}'} "
              f"rerank_top1={top1 if top1 is None else f'{top1:.0%}'} "
              f"mrr={mrr if mrr is None else f'{mrr:.2f}'} "
              f"eşik_doğru={esik_dogru if esik_dogru is None else f'{esik_dogru:.0%}'} "
              f"eşik_rerank_doğru={esik_rerank_dogru if esik_rerank_dogru is None else f'{esik_rerank_dogru:.0%}'} "
              f"ort_arama={sure:.3f}sn" if sure is not None else "")

    if a.esik is None:
        print("\n(--esik verilmedi: rerank-öncesi YETERSİZ_KAYNAK eşik doğruluğu ölçülmedi.)")
    if a.esik_rerank is None:
        print("(--esik-rerank verilmedi: rerank-sonrası YETERSİZ_KAYNAK eşik doğruluğu ölçülmedi.)")

    rapor = {
        "zaman": datetime.now(timezone.utc).isoformat(),
        "kitap_id": kitap_id,
        "top_k": a.top_k,
        "top_n": a.top_n,
        "esik": a.esik,
        "esik_rerank": a.esik_rerank,
        "ozet": genel_ozet,
        "detay": sonuclar,
    }
    hedef = Path(a.rapor) if a.rapor else Path(__file__).parent / "reports" / f"{datetime.now():%Y%m%d_%H%M%S}.json"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(rapor, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRapor yazıldı: {hedef}")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
