#!/usr/bin/env python3
"""
benchmark/model_karsilastir.py — RAG'ın ÜRETİM MODELİ'ni (şu an qwen2.5:14b)
başka bir Ollama modeliyle (ör. Kaira-Turkish-Gemma-9B) GERÇEK `server/rag.py`
üzerinde, yan yana karşılaştırır.

NEDEN VAR (2026-09-08) — EBYS botu projesindeki bir Claude oturumu, aynı
Ollama'da (farabi.local, GPU1) qwen2.5:14b'nin ürettiği Çince/Japonca alfabe
sızıntısı sorununu çözmek için `hf.co/umutkkgz/Kaira-Turkish-Gemma-9B-T1-GGUF`
adlı Türkçe'ye özel bir modeli yükledi. Atakan bu modeli Farabi RAG'ın ÜRETİM
modeli olarak da kullanmayı düşünüyor. CLAUDE.md Kural 10 ("ölçmeden
optimizasyon yapma") ve mimari.md §15'teki emsal (qwen2.5:14b Faz 0a'da
grup C'de %94 doğrulukla ÖLÇÜLEREK seçildi) gereği, körlemesine geçiş
yapılmadı — bu betik o ölçümü sağlar.

`rag_test.py`'nin desenini birebir izler (aynı `_OlcumBaglantisi` — üretim
`metrik`/`soru_log` tablolarına YAZMAZ, embed+rerank CPU'da) ama onun aksine
LLM ADIMINI ATLAMAZ: karşılaştırdığımız tam olarak LLM'in davranışı. Farkı:
`RagMotoru.model` özniteliği modeller arasında değiştirilir, retrieval/rerank
AYNI kalır (ikisi de aynı embed+reranker'ı kullanır) — yani buradaki tüm fark
yalnızca son cevabı üreten modelden gelir.

BİLİNÇLİ TASARIM KARARLARI
───────────────────────────
1) Modeller arasında SORU SORU değil, TÜM SET BİTTİKTEN SONRA geçilir — her
   model geçişi Ollama'da GPU1'de bir swap'e (qwen ⇄ Kaira, ~10-20 sn) mal
   olur; soru başına swap etmek hem yavaş hem de EBYS botunun kendi
   `keep_alive` döngüsüyle gereksiz çakışır.

2) `_llm_cevap` SARMALANIR, DEĞİŞTİRİLMEZ — rag_test.py'nin `--llm-atla`
   modundaki `_sahte_llm` deseninden farklı olarak burada gerçek çağrı
   yapılır, yalnızca ham cevap + LLM süresi dışarıdan yakalanır (sorgula()
   bunları dışarı döndürmüyor, yalnızca _logla'ya iç akışta geçiyor).

3) `<think>...</think>` SIZINTISI AYRICA ÖLÇÜLÜR — Kaira düz promptta
   "thinking" tarzı çıktı üretiyor (format:"json" kullanılmadıkça). rag.py
   şu an bunu TEMİZLEMİYOR; hem son cevaba sızabilir (`cumle_asimi` ve
   `think_sizinti` alanlarıyla yakalanır) HEM DE `_sayilar_kaynakta_mi`
   kontrolü ham cevabın TAMAMINI (think bloğu dahil) taradığı için, model
   akıl yürütürken kaynakta olmayan bir sayıdan bahsederse gerçek cevap
   temiz olsa bile `sayi_kontrolu_reddi` YANLIŞ POZİTİF üretebilir. Bu
   betik bunu düzeltmiyor (o, migrasyonun kendisi) — yalnızca ölçüyor.

4) ZAMAN AŞIMI 30 sn'DE SABİT — `rag.py`'nin `_llm_cevap` varsayılanı,
   `sorgula()` onu override etmiyor. "Thinking" modelleri daha yavaş
   olabilir; bu betik zaman aşımını ARTIRMAZ (üretim davranışını taklit
   etmek için) — sık zaman aşımı da başlı başına bir bulgu, `hata_orani`
   alanında görünür.

Kullanım
────────
    benchmark/venv/bin/python model_karsilastir.py --kitap-id 1
    benchmark/venv/bin/python model_karsilastir.py --kitap-id 1 --limit 8
    benchmark/venv/bin/python model_karsilastir.py --kitap-id 1 \\
        --modeller "qwen2.5:14b,hf.co/umutkkgz/Kaira-Turkish-Gemma-9B-T1-GGUF:Q4_K_M"
"""

import argparse
import json
import re
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# server/ modülleri paket değil, düz modül — sys.path import'tan ÖNCE
# ayarlanmalı (server/tests/ ve rag_test.py ile aynı desen).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import rag
import rag_test
from ortak import baglan, kitap_idyi_coz

_CUMLE_RE = re.compile(r"[.!?]+(?:\s|$)")
_THINK_RE = re.compile(r"<think", re.IGNORECASE)

_METRIK_ANAHTARLAR = (
    "ok_orani", "yetersiz_kaynak_orani", "sayi_kontrolu_reddi_orani",
    "hata_orani", "think_sizinti_orani", "cumle_asimi_orani",
    "medyan_llm_ms", "medyan_toplam_ms",
)


def _cumle_sayisi(metin: str) -> int:
    """Kaba bir sezgisel — ondalık sayılar ("3.14") yanlış bölünebilir, bu
    yalnızca teşhis amaçlı, üretim kapısı değil."""
    return len([p for p in _CUMLE_RE.split(metin) if p.strip()])


def _model_mevcut_mu(ollama_host: str, model_adi: str) -> bool:
    try:
        with urllib.request.urlopen(f"http://{ollama_host}/api/tags", timeout=5) as r:
            veri = json.load(r)
        return any(m.get("name") == model_adi for m in veri.get("models", []))
    except Exception:
        return True  # kontrol başarısızsa engelleme — asıl hata soru bazında görünür


def _olc_llm(motor, conn, kitap_id, sorular, model_adi):
    orijinal = rag.RagMotoru._llm_cevap
    son = {}

    def _sarmali(sistem, soru, timeout=30.0):
        t0 = time.perf_counter()
        ham = orijinal(motor, sistem, soru, timeout)
        son["ham"] = ham
        son["llm_ms"] = int((time.perf_counter() - t0) * 1000)
        return ham

    motor._llm_cevap = _sarmali
    motor.model = model_adi

    kayitlar = []
    for i, s in enumerate(sorular, 1):
        son.clear()
        t0 = time.perf_counter()
        sonuc = motor.sorgula(conn, kitap_id, s["soru"])
        toplam_ms = int((time.perf_counter() - t0) * 1000)
        ham = son.get("ham")  # None ise eşik LLM'e hiç gitmeden reddetti
        cevap = sonuc.get("answer") or ""

        kayitlar.append({
            "soru": s["soru"][:120],
            "grup": s.get("grup"),
            "durum": sonuc["status"],
            "ham_cevap": ham,
            "cevap": cevap,
            "think_sizinti": bool(ham and _THINK_RE.search(ham)),
            "cumle_sayisi": _cumle_sayisi(cevap) if cevap else None,
            "cumle_asimi": (_cumle_sayisi(cevap) > 3) if cevap else False,
            "llm_ms": son.get("llm_ms"),
            "toplam_ms": toplam_ms,
            "hata": sonuc.get("hata"),
        })
        print(f"  [{i}/{len(sorular)}] {sonuc['status']:<20} "
              f"think={'EVET' if kayitlar[-1]['think_sizinti'] else '-':<4} "
              f"llm_ms={son.get('llm_ms', '-')}", flush=True)
    return kayitlar


def _ozet_llm(kayitlar):
    def _grup(liste):
        n = len(liste)
        if not n:
            return None
        ok = [k for k in liste if k["durum"] == "ok"]
        llm_sureler = [k["llm_ms"] for k in liste if k["llm_ms"] is not None]
        toplam_sureler = [k["toplam_ms"] for k in liste]
        return {
            "n": n,
            "ok_orani": len(ok) / n,
            "yetersiz_kaynak_orani": sum(1 for k in liste if k["durum"] == "yetersiz_kaynak") / n,
            "sayi_kontrolu_reddi_orani": sum(1 for k in liste if k["durum"] == "sayi_kontrolu_reddi") / n,
            "hata_orani": sum(1 for k in liste if k["durum"] == "hata") / n,
            "think_sizinti_orani": sum(1 for k in liste if k["think_sizinti"]) / n,
            "cumle_asimi_orani": (sum(1 for k in ok if k["cumle_asimi"]) / len(ok)) if ok else None,
            "medyan_llm_ms": statistics.median(llm_sureler) if llm_sureler else None,
            "medyan_toplam_ms": statistics.median(toplam_sureler),
        }

    ozet = {}
    for g in sorted({k["grup"] for k in kayitlar if k["grup"]}):
        ozet[g] = _grup([k for k in kayitlar if k["grup"] == g])
    ozet["TOPLAM"] = _grup(kayitlar)
    return ozet


def _konsol_ozet(sonuclar):
    modeller = list(sonuclar)
    print(f"\n{'='*78}\nKARŞILAŞTIRMA — TOPLAM\n{'='*78}")
    baslik = f"  {'metrik':<28}" + "".join(f"{m[:20]:>22}" for m in modeller)
    print(baslik)
    for anahtar in _METRIK_ANAHTARLAR:
        satir = f"  {anahtar:<28}"
        for m in modeller:
            v = sonuclar[m]["ozet"]["TOPLAM"].get(anahtar)
            satir += f"{v:>22.3f}" if isinstance(v, float) else f"{str(v):>22}"
        print(satir)

    if "C" in sonuclar[modeller[0]]["ozet"]:
        print(f"\n{'='*78}\nGRUP C (kitapta yok — YETERSIZ_KAYNAK doğru davranıştır)\n{'='*78}")
        print(baslik)
        for anahtar in _METRIK_ANAHTARLAR:
            satir = f"  {anahtar:<28}"
            for m in modeller:
                v = sonuclar[m]["ozet"].get("C", {}).get(anahtar) if sonuclar[m]["ozet"].get("C") else None
                satir += f"{v:>22.3f}" if isinstance(v, float) else f"{str(v):>22}"
            print(satir)

    print(f"\n{'='*78}\nÖRNEK CEVAPLAR (grup C tamamı + ilk 2 A/B)\n{'='*78}")
    ilk_model = sonuclar[modeller[0]]["kayitlar"]
    ornek_idx = [i for i, k in enumerate(ilk_model) if k["grup"] == "C"]
    ornek_idx += [i for i, k in enumerate(ilk_model) if k["grup"] != "C"][:2]
    for i in ornek_idx:
        print(f"\n  SORU: {ilk_model[i]['soru']}")
        for m in modeller:
            k = sonuclar[m]["kayitlar"][i]
            cevap = (k["cevap"] or f"[{k['durum']}]")[:200]
            print(f"    {m[:24]:<26} {cevap}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sorular", default=str(Path(__file__).parent / "sorular.json"))
    ap.add_argument("--kitap-id", type=int, default=None)
    ap.add_argument("--modeller", default="qwen2.5:14b,hf.co/umutkkgz/Kaira-Turkish-Gemma-9B-T1-GGUF:Q4_K_M",
                    help="Virgülle ayrılmış Ollama model adları (ollama list'teki NAME ile birebir)")
    ap.add_argument("--limit", type=int, default=None, help="Yalnızca ilk N soru (hızlı deneme)")
    ap.add_argument("--rapor-cikti")
    ap.add_argument("--etiket", default="")
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-name", default="farabi")
    ap.add_argument("--db-user", default="farabi")
    ap.add_argument("--ollama-host", default="127.0.0.1:11434")
    a = ap.parse_args()

    modeller = [m.strip() for m in a.modeller.split(",") if m.strip()]
    if len(modeller) < 2:
        ap.error("--modeller en az 2 model içermeli (karşılaştırma için)")

    sorular = json.loads(Path(a.sorular).read_text(encoding="utf-8"))
    if a.limit:
        sorular = sorular[:a.limit]

    for m in modeller:
        if not _model_mevcut_mu(a.ollama_host, m):
            print(f"UYARI: '{m}' ollama list'te görünmüyor — 'ollama pull {m}' gerekebilir.")

    gercek = baglan(a.db_host, a.db_name, a.db_user)
    kitap_id = kitap_idyi_coz(gercek, a.kitap_id)
    conn = rag_test._OlcumBaglantisi(gercek)

    print(f"Embed+rerank CPU'ya yükleniyor ({rag.EMBED_MODEL} + {rag.RERANK_MODEL})…")
    from sentence_transformers import CrossEncoder, SentenceTransformer
    t0 = time.perf_counter()
    motor = rag.RagMotoru(SentenceTransformer(rag.EMBED_MODEL, device="cpu"),
                          CrossEncoder(rag.RERANK_MODEL, device="cpu"),
                          ollama_host=a.ollama_host)
    print(f"  yüklendi ({time.perf_counter()-t0:.1f} sn)")

    print(f"\nkitap_id={kitap_id}, {len(sorular)} soru, {len(modeller)} model: {modeller}")
    print("UYARI: model geçişleri GPU1'de gerçek Ollama swap'i tetikler "
          "(EBYS botunun paylaştığı kart) — her model TÜM soru seti bitene kadar sabit tutulur.\n")

    sonuclar = {}
    for model_adi in modeller:
        print(f"\n{'='*70}\nMODEL: {model_adi}\n{'='*70}")
        kayitlar = _olc_llm(motor, conn, kitap_id, sorular, model_adi)
        sonuclar[model_adi] = {"ozet": _ozet_llm(kayitlar), "kayitlar": kayitlar}

    rapor = {
        "zaman": datetime.now(timezone.utc).isoformat(),
        "etiket": a.etiket,
        "harness": "model_karsilastir.py (GERÇEK server/rag.py, yalnızca LLM modeli değişiyor)",
        "kitap_id": kitap_id,
        "soru_sayisi": len(sorular),
        "yutulan_insert": conn.yutulan_insert,
        "modeller": sonuclar,
    }
    hedef = Path(a.rapor_cikti) if a.rapor_cikti else (
        Path(__file__).parent / "reports" / f"model_karsilastir_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(rapor, ensure_ascii=False, indent=2), encoding="utf-8")

    _konsol_ozet(sonuclar)
    print(f"\nRapor: {hedef}")
    print(f"Üretim tablolarına yazılmadı (yutulan INSERT: {conn.yutulan_insert})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
