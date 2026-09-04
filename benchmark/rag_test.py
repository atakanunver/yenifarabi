#!/usr/bin/env python3
"""
benchmark/rag_test.py — GERÇEK `server/rag.py` üzerinde ölçüm harness'ı.

NEDEN VAR (2026-09-02, docs/REFACTORING_PLAN.md R-4 sırasında bulundu):
`recall_test.py` ve `katman_test.py` `rag.py`'yi IMPORT ETMİYOR — ikisi de
pipeline'ı YENİDEN YAZIYOR (kendi `ilk_k_getir`'i, kendi eşiği, kendi
`SISTEM_SABLON` kopyası). Yani üretimin RAG davranışını değiştiren bir kod
düzenlemesi o iki harness'ta HİÇBİR fark üretmez; ölçtükleri şey sistemin
kendisi değil, sistemin bir MODELİ.

Bu, `docs/RAG_BASELINE.md` §3.3'teki açıklanamayan "38/40 vs 35/40" taban
farkının da en olası kaynağı: iki ayrı uygulama zamanla ayrışmış.

Bu betik farkı kapatır: `RagMotoru`'yu doğrudan kurar ve `sorgula()`'yı
çağırır — üretimde koşan KODUN TA KENDİSİNİ. Eski harness'lar silinmedi;
onlar retrieval/eşik parametrelerini rag.py'den BAĞIMSIZ taramak için hâlâ
işe yarıyor (ör. `--esik` süpürmesi).

İKİ ÖNEMLİ TASARIM KARARI
─────────────────────────
1) ÜRETİM TELEMETRİSİ KİRLETİLMEZ. `sorgula()` her çağrıda `metrik`e (ve
   koşullu olarak `soru_log`a) INSERT atıyor. 40 soruluk bir ölçüm koşusu
   bu tabloları benchmark verisiyle doldurur ve `docs/RAG_BASELINE.md`
   §4'ün dayandığı gerçek-kullanım istatistiğini bozardı. `_OlcumBaglantisi`
   SELECT'leri geçirir, INSERT'leri YUTAR.

2) MODELLER CPU'DA. `benchmark/venv` torch'u `2.13.0+cpu` — GPU'ya hiç
   dokunulmaz, `farabi-api.service` ve `ollama` etkilenmez, ders sırasında
   bile koşturulabilir. Bunun bedeli: buradaki GECİKME rakamları CPU
   rakamlarıdır, üretimi TEMSİL ETMEZ (üretim gecikmesi için `metrik`
   tablosu). Sıralama/doğruluk metrikleri ise geçerlidir — aynı ağırlıklar.

Kullanım
────────
    benchmark/venv/bin/python rag_test.py --sorular sorular.json --kitap-id 1
    benchmark/venv/bin/python rag_test.py --sorular sorular.json --kitap-id 1 --llm-atla
    benchmark/venv/bin/python rag_test.py --karsilastir onceki.json sonraki.json

`--llm-atla` LLM adımını sahteler: retrieval/rerank/eşik katmanını izole
eder, Ollama'ya hiç gitmez (hızlı ve deterministik). R-4 gibi YALNIZCA
rerank girdisini değiştiren bir değişiklik için doğru mod budur.
"""

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# server/ modülleri paket değil, düz modül — sys.path import'tan ÖNCE
# ayarlanmalı (server/tests/ ile aynı desen).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import rag
from ortak import baglan, kitap_idyi_coz


class _OlcumBaglantisi:
    """SELECT'leri gerçek bağlantıya geçirir, INSERT'leri yutar.

    Amaç: ölçüm koşusunun `metrik`/`soru_log` tablolarına yazmaması. Bu
    tablolar üretim telemetrisi (bkz. docs/RAG_BASELINE.md §4); benchmark
    satırları oraya karışırsa gerçek sınıf kullanımının istatistiği
    geri dönülemez şekilde bozulur."""

    def __init__(self, conn):
        self._conn = conn
        self.yutulan_insert = 0

    class _Imlec:
        def __init__(self, dis, gercek):
            self._dis, self._g = dis, gercek

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return self._g.__exit__(*a)

        def execute(self, sql, params=None):
            if sql.strip().upper().startswith("INSERT"):
                self._dis.yutulan_insert += 1
                return None
            return self._g.execute(sql, params)

        def fetchall(self):
            return self._g.fetchall()

    def cursor(self):
        return self._Imlec(self, self._conn.cursor().__enter__())

    def commit(self):
        pass                      # yazmıyoruz, commit edilecek bir şey yok

    def rollback(self):
        self._conn.rollback()


def _sahte_llm(sistem, soru, timeout=30.0):
    """`--llm-atla` modu: eşiği geçen her soruya sabit, sayısız bir cevap.
    Sayısız olması önemli — sayı kontrolü (§8 adım 7) yanlışlıkla
    tetiklenip retrieval ölçümünü bulandırmasın."""
    return "Kaynak metne dayanan kisa bir cevap."


def _olc(motor, conn, kitap_id, sorular, llm_atla):
    kayitlar = []
    for i, s in enumerate(sorular, 1):
        t0 = time.perf_counter()
        sonuc = motor.sorgula(conn, kitap_id, s["soru"])
        gecen = int((time.perf_counter() - t0) * 1000)

        sayfalar = [k["sayfa"] for k in sonuc["sources"]]
        dogru = s.get("dogru_sayfa")
        # GRUP C AYRIMI: `dogru_sayfa: null` = "bu soru kitaptan
        # cevaplanamaz" demektir; doğru davranış YETERSIZ_KAYNAK'tır, bir
        # sayfa getirmek DEĞİL. Bu soruların `kaynak_sayfa` alanı yalnızca
        # "konusu buraya yakın" notudur — YER GERÇEĞİ DEĞİL. İlk sürüm onu
        # yer gerçeği sanıp grup C için anlamsız bir Recall@4 üretiyordu.
        # Recall yalnızca dogru_sayfa'sı OLAN sorular için tanımlıdır.
        kabul = set(s.get("kaynak_sayfa") or [dogru]) if dogru is not None else set()

        kayitlar.append({
            "soru": s["soru"][:120],
            "grup": s.get("grup"),
            "dogru_sayfa": dogru,
            "status": sonuc["status"],
            "sayfalar": sayfalar,
            # Birebir diff için: hangi chunk'lar, hangi sırayla, hangi skorla.
            # R-4'ün "biyoloji-9'da NO-OP" iddiası tam olarak buradan
            # kanıtlanır — iki koşunun bu alanları AYNI olmalı.
            "chunk_idler": [k["chunk_id"] for k in sonuc["sources"]],
            "turler": [k["tur"] for k in sonuc["sources"]],
            "recall_at_4": (bool(kabul & set(sayfalar)) if kabul else None),
            "top1_dogru": (sayfalar[0] in kabul if (kabul and sayfalar) else None),
            "toplam_ms": gecen,
        })
        print(f"  [{i}/{len(sorular)}] {sonuc['status']:<20} s={sayfalar}", flush=True)
    return kayitlar


def _ozet(kayitlar):
    def _grup(k_liste):
        n = len(k_liste)
        if not n:
            return None
        r = [k["recall_at_4"] for k in k_liste if k["recall_at_4"] is not None]
        t = [k["top1_dogru"] for k in k_liste if k["top1_dogru"] is not None]
        sureler = [k["toplam_ms"] for k in k_liste]
        return {
            "n": n,
            "recall_at_4": (sum(r) / len(r)) if r else None,
            "top1_dogru_oran": (sum(t) / len(t)) if t else None,
            # Grup C ("kitapta yok") için doğru davranış: yetersiz_kaynak
            "yetersiz_kaynak_orani": sum(
                1 for k in k_liste if k["status"] == "yetersiz_kaynak") / n,
            "medyan_ms": statistics.median(sureler),
        }

    ozet = {}
    for g in sorted({k["grup"] for k in kayitlar if k["grup"]}):
        ozet[g] = _grup([k for k in kayitlar if k["grup"] == g])
    ozet["TOPLAM"] = _grup(kayitlar)
    return ozet


def _karsilastir(a_yolu, b_yolu) -> int:
    a = json.loads(Path(a_yolu).read_text(encoding="utf-8"))
    b = json.loads(Path(b_yolu).read_text(encoding="utf-8"))
    ka, kb = a["kayitlar"], b["kayitlar"]
    if len(ka) != len(kb):
        print(f"HATA: soru sayıları farklı ({len(ka)} vs {len(kb)})")
        return 2

    farkli = []
    for x, y in zip(ka, kb):
        if x["chunk_idler"] != y["chunk_idler"] or x["status"] != y["status"]:
            farkli.append((x, y))

    print(f"\n{'='*66}\nKARŞILAŞTIRMA  {Path(a_yolu).name}  →  {Path(b_yolu).name}\n{'='*66}")
    for anahtar in ("recall_at_4", "top1_dogru_oran", "yetersiz_kaynak_orani", "medyan_ms"):
        va = a["ozet"]["TOPLAM"].get(anahtar)
        vb = b["ozet"]["TOPLAM"].get(anahtar)
        if va is None or vb is None:
            continue
        ok = "=" if abs(va - vb) < 1e-9 else ("↑" if vb > va else "↓")
        print(f"  {anahtar:<24} {va:>10.4f}  {ok}  {vb:<10.4f}")

    print(f"\n  Sıralaması/statüsü DEĞİŞEN soru: {len(farkli)} / {len(ka)}")
    for x, y in farkli[:10]:
        print(f"    - {x['soru'][:60]}")
        print(f"        önce : {x['status']:<18} {x['chunk_idler']}")
        print(f"        sonra: {y['status']:<18} {y['chunk_idler']}")
    if not farkli:
        print("    (hiçbiri — değişiklik bu kitapta BİREBİR NO-OP)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sorular")
    ap.add_argument("--kitap-id", type=int, default=None)
    ap.add_argument("--llm-atla", action="store_true",
                    help="LLM adımını sahtele — retrieval/rerank/eşiği izole eder")
    ap.add_argument("--rapor-cikti")
    ap.add_argument("--etiket", default="", help="rapora yazılacak serbest not")
    ap.add_argument("--karsilastir", nargs=2, metavar=("ONCE", "SONRA"))
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-name", default="farabi")
    ap.add_argument("--db-user", default="farabi")
    a = ap.parse_args()

    if a.karsilastir:
        return _karsilastir(*a.karsilastir)
    if not a.sorular:
        ap.error("--sorular gerekli (ya da --karsilastir)")

    sorular = json.loads(Path(a.sorular).read_text(encoding="utf-8"))
    gercek = baglan(a.db_host, a.db_name, a.db_user)
    kitap_id = kitap_idyi_coz(gercek, a.kitap_id)
    conn = _OlcumBaglantisi(gercek)

    print(f"Modeller CPU'ya yükleniyor ({rag.EMBED_MODEL} + {rag.RERANK_MODEL})…")
    from sentence_transformers import CrossEncoder, SentenceTransformer
    t0 = time.perf_counter()
    motor = rag.RagMotoru(SentenceTransformer(rag.EMBED_MODEL, device="cpu"),
                          CrossEncoder(rag.RERANK_MODEL, device="cpu"))
    print(f"  yüklendi ({time.perf_counter()-t0:.1f} sn)")

    if a.llm_atla:
        motor._llm_cevap = _sahte_llm
        print("  LLM ADIMI SAHTELENDİ (--llm-atla)")

    print(f"kitap_id={kitap_id}, {len(sorular)} soru, TABLO_KAYNAGI={rag.TABLO_KAYNAGI}, "
          f"ESIK_RERANK={rag.ESIK_RERANK}")
    kayitlar = _olc(motor, conn, kitap_id, sorular, a.llm_atla)

    rapor = {
        "zaman": datetime.now(timezone.utc).isoformat(),
        "etiket": a.etiket,
        "harness": "rag_test.py (GERÇEK server/rag.py)",
        "kitap_id": kitap_id,
        "llm_atlandi": a.llm_atla,
        "yutulan_insert": conn.yutulan_insert,
        "rag_ayarlari": {
            "TOP_K": rag.TOP_K, "TOP_N": rag.TOP_N,
            "ESIK_RERANK": rag.ESIK_RERANK,
            "TABLO_KAYNAGI": rag.TABLO_KAYNAGI,
            "TOP_K_TABLO": rag.TOP_K_TABLO,
            "RERANK_TABLO_KARAKTER": rag.RERANK_TABLO_KARAKTER,
            "RERANK_METIN_KARAKTER": getattr(rag, "RERANK_METIN_KARAKTER", None),
        },
        "ozet": _ozet(kayitlar),
        "kayitlar": kayitlar,
    }
    hedef = Path(a.rapor_cikti) if a.rapor_cikti else (
        Path(__file__).parent / "reports" / f"ragtest_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(rapor, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    for g, o in rapor["ozet"].items():
        if o:
            r = f"{o['recall_at_4']:.3f}" if o["recall_at_4"] is not None else "  — "
            print(f"  {g:<8} n={o['n']:<3} Recall@4={r}  "
                  f"yetersiz={o['yetersiz_kaynak_orani']:.2f}  medyan={o['medyan_ms']:.0f} ms")
    print(f"\nRapor: {hedef}")
    print(f"Üretim tablolarına yazılmadı (yutulan INSERT: {conn.yutulan_insert})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
