"""server/rag.py — Faz 1 RAG çekirdeği: pgvector arama + rerank + eşik + LLM.

benchmark/recall_test.py (retrieval/rerank) ve benchmark/katman_test.py'nin
(eşik + LLM katmanı — 2026-08-10'da ölçülen: C grubu tek başına hiçbir eşikle
ayrıştırılamıyordu, iki katman birlikte %94 doğru) DOĞRULANMIŞ mantığının
canlı servise taşınmış hali. Akış mimari.md §8 ile birebir: rerank → eşik
(ana savunma, LLM'e hiç gitmeyebilir) → LLM (orta savunma, katı prompt +
YETERSIZ_KAYNAK) → sayı kontrolü (ek savunma).

NOT — sistem promptu mimari.md §8'den BİREBİR kopya, benchmark/katman_test.py
ile de aynı. Üç yerde de elle senkron tutulmalı; paylaşılan tek bir prompt
dosyası yok (Faz 1'in ilerleyen bir adımı olabilir).

ESIK_RERANK = 0.5 — benchmark/katman_test.py'de ölçüldü: A/B grubu rerank
skorlarının tabanı (temiz soru setiyle) 0.71, grup C'nin 2/5'i 0.02-0.34
aralığında. 0.5 ikisi arasında güvenli bir boşlukta duruyor ama TEK kitapla
(biyoloji-9) ölçüldü — yeni bir kitap eklendiğinde bu değer yeniden
gözden geçirilmeli, kör kör başka kitaplara uygulanmamalı.

§8 adım 7 "SAYI KONTROLÜ" (2026-08-11 eklendi) — cevaptaki sayısal değerlerin
kaynak metinde geçip geçmediğini kontrol eder. CLAUDE.md'nin "RAG Kuralları"
notuyla aynı: "kelime örtüşme oranı kullanma (doğru parafrazı engeller)" —
bu yüzden kontrol yalnızca SAYILARI karşılaştırıyor, cümlenin geri kalanını
değil. Dar kapsamlı, ek bir savunma — ana savunma eşik+LLM katmanıdır (yukarı
bkz.), bunun yerine geçmez.

LOGLAMA (2026-08-11 eklendi, mimari.md §13 / benchmark/olcum_schema.sql) —
`metrik` HER sorguda yazılır (süre+durum+skor, içerik yok, sınırsız saklanır).
`soru_log` yalnızca CLAUDE.md'nin "Loglama" tablosundaki durumlarda yazılır:
düşük skorlu ok, yetersiz_kaynak, sayi_kontrolu_reddi, hata (iptal bu API'de
henüz üretilemiyor — iptal mekanizması yok). DUSUK_SKOR_ESIGI (0.65) ÖLÇÜLMEDİ,
ESIK_RERANK (0.5, ana savunma) ile A/B'nin ölçülen tabanı (0.71) arasında ilk
tahmin — Kural 10 gereği burada açıkça işaretleniyor.

Yapılmayan (bilinçli sınır, bu turda eklenmedi):
- Kazanım eşleştirme, tahta_id → ders_programi → kitap_id bağlam çözümü —
  şu an kitap_id doğrudan istekte veriliyor, Faz 1'in sonraki bir adımı.
  `sorgula()`'ya tahta_id/sinif/ders parametreleri BU YÜZDEN eklendi (loglama
  şimdiden doğru şemaya yazsın diye) ama çağıran taraf (main.py) şu an
  yalnızca sinif/ders'i kitap_id'den çözüp geçiyor, tahta_id hep None.
"""

import json
import re
import time
import urllib.request

EMBED_MODEL = "BAAI/bge-m3"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
TOP_K = 20
TOP_N = 4
ESIK_RERANK = 0.5
DUSUK_SKOR_ESIGI = 0.65

_SAYI_RE = re.compile(r"\d+(?:[.,]\d+)?")

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


def _sayilar_kaynakta_mi(cevap: str, kaynak_metin: str) -> bool:
    """Cevaptaki her sayının kaynak metinde birebir geçip geçmediğini kontrol
    eder. Kaynakta olmayan TEK bir sayı bile varsa False döner — mimari.md §8
    adım 7'nin "ek, dar kapsamlı" savunması, kelime örtüşmesi DEĞİL."""
    cevap_sayilari = _SAYI_RE.findall(cevap)
    if not cevap_sayilari:
        return True
    return all(sayi in kaynak_metin for sayi in cevap_sayilari)


class RagMotoru:
    def __init__(self, embed_model, reranker, ollama_host: str = "127.0.0.1:11434",
                 model: str = "qwen2.5:14b"):
        self.embed_model = embed_model
        self.reranker = reranker
        self.ollama_host = ollama_host
        self.model = model

    def _ilk_k_getir(self, conn, kitap_id: int, vektor, k: int):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, sayfa_no, metin, embedding <=> %s AS mesafe
                FROM chunk_egitim
                WHERE kitap_id = %s
                ORDER BY mesafe
                LIMIT %s
                """,
                (vektor, kitap_id, k),
            )
            return cur.fetchall()  # [(id, sayfa_no, metin, mesafe), ...]

    def _llm_cevap(self, sistem: str, soru: str, timeout: float = 30.0) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": sistem},
                {"role": "user", "content": soru},
            ],
        }
        req = urllib.request.Request(
            f"http://{self.ollama_host}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
        return d["message"]["content"]

    def _logla(self, conn, *, tahta_id, sinif, ders, soru, sonuc, ham_cevap,
               toplam_ms, retrieval_ms, rerank_ms, llm_ms, en_iyi_skor,
               chunk_idler, skorlar) -> None:
        """metrik HER ZAMAN yazılır (içerik yok). soru_log yalnızca
        CLAUDE.md'nin "Loglama" tablosundaki durumlarda — mimari.md §13."""
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO metrik
                        (tahta_id, retrieval_ms, rerank_ms, llm_toplam_ms,
                         toplam_ms, sonuc, en_yuksek_skor)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tahta_id, retrieval_ms, rerank_ms, llm_ms, toplam_ms,
                     sonuc, en_iyi_skor),
                )

            dusuk_skorlu_ok = sonuc == "ok" and en_iyi_skor is not None and en_iyi_skor < DUSUK_SKOR_ESIGI
            metin_saklanmali = sonuc != "ok" or dusuk_skorlu_ok
            if metin_saklanmali:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO soru_log
                            (tahta_id, sinif, ders, soru_metni, donen_chunk_idler,
                             skorlar, cevap_metni, sonuc)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (tahta_id, sinif, ders, soru, chunk_idler or None,
                         skorlar or None, ham_cevap, sonuc),
                    )
            conn.commit()
        except Exception:
            # Loglama dersi bozmaz (mimari.md §2) — hata olursa yut, cevabı etkileme.
            conn.rollback()

    def sorgula(self, conn, kitap_id: int, soru: str, *,
                sinif: int | None = None, ders: str | None = None,
                tahta_id: int | None = None) -> dict:
        """Dönen dict: status, answer, sources ([{chunk_id, sayfa}]), latency_ms."""
        t0 = time.perf_counter()

        vektor = self.embed_model.encode(soru, normalize_embeddings=True)
        adaylar = self._ilk_k_getir(conn, kitap_id, vektor, TOP_K)
        retrieval_ms = int((time.perf_counter() - t0) * 1000)

        if not adaylar:
            toplam_ms = int((time.perf_counter() - t0) * 1000)
            self._logla(conn, tahta_id=tahta_id, sinif=sinif, ders=ders, soru=soru,
                        sonuc="yetersiz_kaynak", ham_cevap=None, toplam_ms=toplam_ms,
                        retrieval_ms=retrieval_ms, rerank_ms=None, llm_ms=None,
                        en_iyi_skor=None, chunk_idler=[], skorlar=[])
            return {"status": "yetersiz_kaynak", "answer": None, "sources": [], "latency_ms": toplam_ms}

        t1 = time.perf_counter()
        ciftler = [(soru, c[2]) for c in adaylar]
        skorlar_ham = self.reranker.predict(ciftler)
        siralanmis = sorted(zip(adaylar, skorlar_ham), key=lambda x: x[1], reverse=True)
        rerank_ms = int((time.perf_counter() - t1) * 1000)
        top_n = siralanmis[:TOP_N]
        en_iyi_skor = float(top_n[0][1])
        chunk_idler = [int(c[0]) for c, _ in top_n]
        skor_listesi = [round(float(s), 4) for _, s in top_n]

        # ── ANA savunma (mimari.md §8 adım 5) — eşiğin altındaysa LLM'e hiç gitme ──
        if en_iyi_skor < ESIK_RERANK:
            toplam_ms = int((time.perf_counter() - t0) * 1000)
            self._logla(conn, tahta_id=tahta_id, sinif=sinif, ders=ders, soru=soru,
                        sonuc="yetersiz_kaynak", ham_cevap=None, toplam_ms=toplam_ms,
                        retrieval_ms=retrieval_ms, rerank_ms=rerank_ms, llm_ms=None,
                        en_iyi_skor=en_iyi_skor, chunk_idler=chunk_idler, skorlar=skor_listesi)
            return {"status": "yetersiz_kaynak", "answer": None, "sources": [], "latency_ms": toplam_ms}

        kaynaklar = [{"chunk_id": c[0], "sayfa": c[1]} for c, _ in top_n]
        kaynak_metin = "\n\n".join(f"[chunk] (s. {c[1]}) {c[2]}" for c, _ in top_n)
        sistem = SISTEM_SABLON.format(kaynak=kaynak_metin)

        # ── ORTA savunma (mimari.md §8 adım 6) — katı prompt + YETERSIZ_KAYNAK ──
        t2 = time.perf_counter()
        try:
            cevap = self._llm_cevap(sistem, soru)
        except Exception as e:
            llm_ms = int((time.perf_counter() - t2) * 1000)
            toplam_ms = int((time.perf_counter() - t0) * 1000)
            self._logla(conn, tahta_id=tahta_id, sinif=sinif, ders=ders, soru=soru,
                        sonuc="hata", ham_cevap=f"{type(e).__name__}: {e}", toplam_ms=toplam_ms,
                        retrieval_ms=retrieval_ms, rerank_ms=rerank_ms, llm_ms=llm_ms,
                        en_iyi_skor=en_iyi_skor, chunk_idler=chunk_idler, skorlar=skor_listesi)
            return {"status": "hata", "answer": None, "sources": [], "latency_ms": toplam_ms,
                    "hata": f"{type(e).__name__}: {e}"}
        llm_ms = int((time.perf_counter() - t2) * 1000)

        yetersiz = "YETERSIZ_KAYNAK" in cevap.upper().replace("İ", "I")
        if yetersiz:
            toplam_ms = int((time.perf_counter() - t0) * 1000)
            self._logla(conn, tahta_id=tahta_id, sinif=sinif, ders=ders, soru=soru,
                        sonuc="yetersiz_kaynak", ham_cevap=cevap, toplam_ms=toplam_ms,
                        retrieval_ms=retrieval_ms, rerank_ms=rerank_ms, llm_ms=llm_ms,
                        en_iyi_skor=en_iyi_skor, chunk_idler=chunk_idler, skorlar=skor_listesi)
            return {"status": "yetersiz_kaynak", "answer": None, "sources": [], "latency_ms": toplam_ms}

        # ── EK savunma (mimari.md §8 adım 7) — cevaptaki sayılar kaynakta yoksa reddet ──
        if not _sayilar_kaynakta_mi(cevap, kaynak_metin):
            toplam_ms = int((time.perf_counter() - t0) * 1000)
            self._logla(conn, tahta_id=tahta_id, sinif=sinif, ders=ders, soru=soru,
                        sonuc="sayi_kontrolu_reddi", ham_cevap=cevap, toplam_ms=toplam_ms,
                        retrieval_ms=retrieval_ms, rerank_ms=rerank_ms, llm_ms=llm_ms,
                        en_iyi_skor=en_iyi_skor, chunk_idler=chunk_idler, skorlar=skor_listesi)
            return {"status": "sayi_kontrolu_reddi", "answer": None, "sources": [], "latency_ms": toplam_ms}

        toplam_ms = int((time.perf_counter() - t0) * 1000)
        self._logla(conn, tahta_id=tahta_id, sinif=sinif, ders=ders, soru=soru,
                    sonuc="ok", ham_cevap=cevap, toplam_ms=toplam_ms,
                    retrieval_ms=retrieval_ms, rerank_ms=rerank_ms, llm_ms=llm_ms,
                    en_iyi_skor=en_iyi_skor, chunk_idler=chunk_idler, skorlar=skor_listesi)
        return {"status": "ok", "answer": cevap.strip(), "sources": kaynaklar, "latency_ms": toplam_ms}
