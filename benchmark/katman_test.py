#!/usr/bin/env python3
"""
benchmark/katman_test.py — mimari.md §8'in İKİ katmanlı halüsinasyon
savunmasının tam simülasyonu: (1) eşik kontrolü [ANA savunma, adım 5] +
(2) LLM'in katı prompt'u [ORTA savunma, adım 6, "YETERSIZ_KAYNAK"].

NEDEN GEREKLİ — recall_test.py TEK BAŞINA yalnızca katman (1)'i ölçebiliyor,
ve ölçüldü: hiçbir tek eşik değeri (ne rerank-öncesi kosinüs ne rerank-sonrası
skor) grup C'yi (kitapta olmayan ama konuyla ilgili sorular) A/B'den
ayrıştıramıyor — aralıklar tamamen çakışıyor (2026-08-09/10 durum raporu).
Bu script katman (2)'yi ekleyip İKİSİNİ BİRLİKTE test ediyor: eşiğin altında
kalan adaylar LLM'e HİÇ gitmiyor (mimari.md §8 adım 5'in tam istediği gibi —
ana savunma ucuz ve LLM çağrısı olmadan çalışır), eşiği geçenler gerçek
retrieval sonucundaki chunk'larla LLM'e gidiyor; LLM'in kendi YETERSIZ_KAYNAK
kararı ikinci savunma katmanı olarak değerlendiriliyor.

ÖNKOŞUL: recall_test.py'nin ürettiği bir rapor (top_n_sayfalar VE
en_iyi_rerank_skoru alanlarını içermeli — ikisi de recall_test.py'de
--esik-rerank verilmeden de her zaman kaydedilir).

NOT — sistem promptu mimari.md §8'den BİREBİR kopyalandı. Sunucu (Faz 1)
kurulup paylaşılan tek bir prompt dosyası oluşana kadar bu iki yer elle
senkron tutulmalı; biri değişirse diğeri unutulmasın.

NOT — bu, Faz 0a'nın "FastAPI/WebSocket/Ollama/STT/TTS kurulmaz" kapsamının
dışına taşan bilinçli bir genişleme (CLAUDE.md'deki 2026-08-09 "Bilinçli
sapma" notuyla aynı ruhta): retrieval-only eşiğin tek başına C grubunu
geçiremediği ölçüldükten sonra, LLM katmanının gerçekten telafi edip
etmediğini görmeden Faz 0a'ya "geçti/geçmedi" denemez.

Kullanım:
    venv/bin/python katman_test.py --rapor reports/xxx.json --esik-rerank 0.15
"""

import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ortak import baglan, kitap_idyi_coz

SISTEM_SABLON = """Sen Farabi'sin, bir ders asistanısın.
SADECE aşağıdaki KAYNAK METİN'e dayanarak cevap ver.

KURALLAR:
- Kaynak metinde olmayan hiçbir bilgiyi ekleme.
- Genel bilginle tamamlama yapma.
- Cevap kaynak metinde yoksa sadece şunu yaz: YETERSIZ_KAYNAK
- En fazla 3 cümle.
- Lise öğrencisinin anlayacağı sadelikte yaz.
- Yorum, tahmin, örnek uydurma yok.

KAYNAK METİN:
{kaynak}"""


def _llm_cevap(ollama_host: str, model: str, sistem: str, soru: str, timeout: float) -> str:
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0.2},
        "messages": [
            {"role": "system", "content": sistem},
            {"role": "user", "content": soru},
        ],
    }
    req = urllib.request.Request(
        f"http://{ollama_host}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    return d["message"]["content"]


def _yetersiz_mi(cevap: str) -> bool:
    return "YETERSIZ_KAYNAK" in cevap.upper().replace("İ", "I")


def main() -> int:
    ap = argparse.ArgumentParser(description="İki katmanlı (eşik + LLM) halüsinasyon savunması testi")
    ap.add_argument("--rapor", required=True, help="recall_test.py çıktısı JSON (en_iyi_rerank_skoru içermeli)")
    ap.add_argument("--esik-rerank", type=float, required=True,
                     help="Bu skorun ALTINDAKİ adaylar LLM'e HİÇ gitmez (ana savunma, mimari.md §8 adım 5)")
    ap.add_argument("--kitap-id", type=int, default=None)
    ap.add_argument("--ollama-host", default="127.0.0.1:11434")
    ap.add_argument("--model", default="qwen2.5:14b")
    ap.add_argument("--llm-timeout", type=float, default=60.0)
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-name", default="farabi")
    ap.add_argument("--db-user", default="farabi")
    ap.add_argument("--rapor-cikti", default=None)
    a = ap.parse_args()

    kaynak_rapor = json.loads(Path(a.rapor).read_text(encoding="utf-8"))
    detay = kaynak_rapor["detay"]
    eksik = [s["soru"] for s in detay if "en_iyi_rerank_skoru" not in s]
    if eksik:
        raise SystemExit(
            f"{len(eksik)} soruda en_iyi_rerank_skoru yok — bu rapor eski bir "
            f"recall_test.py sürümüyle üretilmiş olabilir. Önce recall_test.py'yi "
            f"yeniden çalıştırın."
        )

    conn = baglan(a.db_host, a.db_name, a.db_user)
    kitap_id = a.kitap_id or kaynak_rapor.get("kitap_id") or kitap_idyi_coz(conn, None)
    print(f"kitap_id={kitap_id}, esik_rerank={a.esik_rerank}, model={a.model} — {len(detay)} soru üzerinde katmanlı test…")

    sonuclar = []
    for s in detay:
        beklenen_yetersiz = s["dogru_sayfa"] is None
        kayit = {
            "soru": s["soru"],
            "grup": s["grup"],
            "dogru_sayfa": s["dogru_sayfa"],
            "en_iyi_rerank_skoru": s["en_iyi_rerank_skoru"],
        }

        if s["en_iyi_rerank_skoru"] < a.esik_rerank:
            # ANA savunma tek başına yetiyor — LLM'e hiç gidilmedi.
            kayit["katman"] = "esik"
            karar_yetersiz = True
        else:
            sayfalar = sorted(set(s["top_n_sayfalar"]))
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT sayfa_no, metin FROM chunk_egitim WHERE kitap_id = %s AND sayfa_no = ANY(%s)",
                    (kitap_id, sayfalar),
                )
                chunklar = cur.fetchall()
            kaynak_metin = "\n\n".join(f"[chunk] (s. {sn}) {m}" for sn, m in chunklar)
            sistem = SISTEM_SABLON.format(kaynak=kaynak_metin)

            t0 = time.perf_counter()
            try:
                cevap = _llm_cevap(a.ollama_host, a.model, sistem, s["soru"], a.llm_timeout)
            except Exception as e:
                kayit["hata"] = f"{type(e).__name__}: {e}"
                sonuclar.append(kayit)
                print(f"  ⚠ [{s['grup']}] LLM hatası, atlanıyor: {e}")
                continue
            kayit["sure_llm_sn"] = round(time.perf_counter() - t0, 2)
            kayit["llm_cevap"] = cevap
            kayit["katman"] = "llm"
            karar_yetersiz = _yetersiz_mi(cevap)

        kayit["karar_yetersiz"] = karar_yetersiz
        kayit["katmanli_dogru"] = karar_yetersiz == beklenen_yetersiz
        sonuclar.append(kayit)
        print(f"  [{s['grup']}] katman={kayit['katman']:5} doğru={kayit['katmanli_dogru']} · {s['soru'][:55]}")

    # ── Raporlama — grup bazında, recall_test.py ile aynı ilke ─────────────
    def ozet(liste, anahtar):
        degerler = [s[anahtar] for s in liste if s.get(anahtar) is not None]
        return sum(degerler) / len(degerler) if degerler else None

    gruplar = sorted(set(s["grup"] for s in sonuclar))
    print("\n=== KATMANLI SONUÇ (eşik + LLM birlikte) ===")
    genel_ozet = {}
    for g in gruplar + ["TOPLAM"]:
        alt = sonuclar if g == "TOPLAM" else [s for s in sonuclar if s["grup"] == g]
        if not alt:
            continue
        katmanli_dogru = ozet(alt, "katmanli_dogru")
        esik_ile_bitenler = sum(1 for s in alt if s.get("katman") == "esik")
        genel_ozet[g] = {
            "n": len(alt),
            "katmanli_dogru_tespit_oran": katmanli_dogru,
            "esik_ile_reddedilen": esik_ile_bitenler,
            "llm_ile_karar_verilen": len(alt) - esik_ile_bitenler,
        }
        print(f"[{g}] n={len(alt)} "
              f"katmanlı_doğru={katmanli_dogru if katmanli_dogru is None else f'{katmanli_dogru:.0%}'} "
              f"(eşikte durdu: {esik_ile_bitenler}, LLM'e gitti: {len(alt) - esik_ile_bitenler})")

    rapor = {
        "zaman": datetime.now(timezone.utc).isoformat(),
        "kaynak_rapor": str(a.rapor),
        "kitap_id": kitap_id,
        "esik_rerank": a.esik_rerank,
        "model": a.model,
        "ozet": genel_ozet,
        "detay": sonuclar,
    }
    hedef = Path(a.rapor_cikti) if a.rapor_cikti else Path(__file__).parent / "reports" / f"katmanli_{datetime.now():%Y%m%d_%H%M%S}.json"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(rapor, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRapor yazıldı: {hedef}")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
