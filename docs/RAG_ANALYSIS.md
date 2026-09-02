# RAG_ANALYSIS — Farabi

> Taban: `dbd3fdd` + kirli ağaç (`server/rag.py` **değişik ve commit
> edilmemiş**). Ölçümler: canlı PostgreSQL (`farabi@127.0.0.1/farabi`,
> salt-okunur `SELECT`), `benchmark/reports/`, ve `metrik` tablosunun
> **gerçek üretim telemetrisi**.

---

## 1. Gerçek pipeline (koddan izlendi, tahmin yok)

```
KAYNAK PDF  (/mnt/farabi-data/farabi/kitaplar/)
   │
   ├─ client/tools/kitap_metin.py ──► icerik/metin/<kitap>.json   [ÇEVRİMDIŞI]
   │      PyMuPDF, sayfa sayfa metin
   │
   ├─ client/tools/tablo_cikar.py ──► tablo JSON                  [ÇEVRİMDIŞI]
   │      yalnızca biyoloji-9 için çalıştırılmış (§4)
   ▼
CHUNKING   benchmark/embed_kitap.py::sayfayi_boluml
   │   CHUNK_TOKEN=400, tokenizer tabanlı kayan pencere, örtüşme
   │   SAYFA SINIRI HİÇ AŞILMAZ  ← CLAUDE.md kuralı, kodda gerçekten uygulanıyor
   │   --haric-sayfalar ile kapak/ISBN/atlas ekleri dışlanıyor
   ▼
EMBEDDING  BAAI/bge-m3 → VECTOR(1024), normalize_embeddings=True
   ▼
VECTOR DB  PostgreSQL + pgvector
   │   chunk_egitim (8.726 satır, 19 kitap)   chunk_tablo (67 satır, 1 kitap)
   │   mesafe: <=> (kosinüs).  YAKLAŞIK İNDEKS YOK — kasıtlı (§7)
   ▼
RETRIEVAL  rag.py::_ilk_k_getir   TOP_K=20   WHERE kitap_id = %s
   │      + rag.py::_tablo_getir  TOP_K_TABLO=10  (TABLO_KAYNAGI=True)
   │      İKİ AYRI SORGU — birleşik UNION değil (gerekçe: rag.py:70-79)
   ▼
RERANK     BAAI/bge-reranker-v2-m3, birleşim üzerinde, TOP_N=4
   │      tablo adayları rerank görünümünde 1200 karaktere kırpılır
   │      metin adayları KIRPILMAZ  ← §5'in konusu
   ▼
EŞİK       ESIK_RERANK = 0.5   ← ANA SAVUNMA, altındaysa LLM'e HİÇ GİTMEZ
   ▼
LLM        Ollama qwen2.5:14b, temperature=0.2, katı sistem promptu
   │      "SADECE KAYNAK METİN'e dayan" + "YETERSIZ_KAYNAK" çıkışı + ≤3 cümle
   ▼
SAYI KONTROLÜ  _sayilar_kaynakta_mi — cevaptaki her sayı kaynakta geçmeli
   ▼
CEVAP      {status, answer, sources[{chunk_id, sayfa, tur}], latency_ms}
```

**Değerlendirme: bu pipeline iyi tasarlanmış.** Üç bağımsız halüsinasyon
kapısı (eşik → katı prompt → sayı kontrolü), her biri farklı bir arıza modunu
yakalıyor. `kitap_id` filtresi her sorguda zorunlu. Sayfa sınırı hiç
aşılmıyor, dolayısıyla `s. 84` kaynağı her zaman doğru. Kaynak gösterimi
yapısal (`sources[]`), metin ayrıştırmasına dayanmıyor.

---

## 2. Ölçülen envanter

| | Değer | Kaynak |
|---|---|---|
| İndekslenmiş kitap | **19** | `SELECT count(*) FROM kitap` |
| `chunk_egitim` | **8.726** | canlı DB |
| `chunk_tablo` | **67** (yalnız `kitap_id=1`) | canlı DB |
| `kazanim_kod` **dolu** chunk | **0** | `WHERE kazanim_kod IS NOT NULL` |
| Ortalama chunk uzunluğu | 1.187 karakter | canlı DB |
| p95 chunk uzunluğu | 1.777 karakter | canlı DB |
| `metrik` (üretim telemetrisi) | **354** istek, 2026-08-11 → 09-02 | canlı DB |
| `soru_log` | 94 satır | canlı DB |

**⚠️ Doküman ayrışması (R-D1):** CLAUDE.md ve `docs/mimari.md` **"13 kitap
pgvector'a indekslendi"** diyor. Gerçek: **19**. Aşağıdaki tüm kapsam
değerlendirmeleri 19 üzerinden yapıldı.

---

## 3. Bulgular

### R-01 — Değerlendirme seti 19 kitabın **1'ini** kapsıyor; %80'i insan onayı almamış

| | |
|---|---|
| **AMAÇ** | RAG doğruluk iddialarının dayanağı |
| **MEVCUT DURUM** | `benchmark/sorular.json` = 40 soru, **hepsi biyoloji-9'dan** (`benchmark/metin/` içinde tek dosya: `biyoloji-9.json`). Onay durumu: **`onaylandi: true` → 8**, **`false` → 32**. |
| **KANIT** | `python3 -c "…Counter(x['onaylandi'] …)"` → `{False: 32, True: 8}`; grup dağılımı A=17, B=18, C=5 |
| **RİSK** | `docs/mimari.md` soru setini şöyle tanımlıyor: *"insan işi, kod değil"*. Set ise `benchmark/soru_taslak.py` ile **LLM tarafından taslaklanmış** ve **%80'i doğrulanmamış**. CLAUDE.md'deki her doğruluk rakamı (35/40, 38/40) bu setten geliyor. Yani: **Farabi'nin doğruluk iddiaları, kendisiyle aynı sınıftan bir modelin ürettiği ve insanın onaylamadığı sorulara dayanıyor.** Ayrıca ölçüm **19 kitabın 1'ini** kapsıyor — geri kalan 18 kitabın retrieval kalitesi hakkında **hiçbir veri yok**. |
| **ÖNERİ** | (a) Kalan 32 soruyu onayla/düzelt/at — bu **insan işi**, kod değil, ve öğretmen tam olarak bu işi yapabilecek kişi. (b) En az 2 kitap daha ekle (farklı biçim: `matematik_9` formül ağırlıklı, `tarih_10` düzyazı ağırlıklı) × 15 soru. (c) `ESIK_RERANK=0.5`'in **yalnızca biyoloji-9 ile kalibre edildiği** `rag.py:14-18`'de zaten yazılı — bu genişleme o uyarının gereğidir. |
| **ÖNCELİK** | **P1 — bu belgedeki en önemli RAG işi** |

### R-02 — Fizik-9'da bozuk PDF çıkarımı: tek chunk **21.814 karakter**

| | |
|---|---|
| **MEVCUT DURUM** | `CHUNK_TOKEN=400` yapılandırılmış olmasına rağmen 45 chunk 3.122 karakteri, 10 tanesi 6.000 karakteri aşıyor. En uzunu **21.814 karakter** (`chunk_egitim.id=7710`, Fizik-9 s.169). |
| **KÖK NEDEN (bulundu)** | O chunk **yalnızca 184 boşlukla ayrılmış kelime** içeriyor. İçeriği incelendi: bir "Çalışma Yaprağı" sayfasının boş cevap satırları, PyMuPDF tarafından **U+FFFD (`�`) değiştirme karakteri** dizileri olarak çıkarılmış. Tokenizer bu dizileri az sayıda token sayıyor → 400 token sınırı **karakter olarak patlıyor**. |
| **KANIT** | `SELECT left(metin,300) …` → başlıktan sonra kesintisiz `�` bloğu. `array_length(regexp_split_to_array(metin,'\s+'),1)` → **184**. Yaygınlık taraması: `metin LIKE '%'\|\|chr(65533)\|\|'%'` → **yalnızca Fizik-9, 13 chunk / 782 (%1,7)**. Diğer 18 kitap **temiz**. |
| **RİSK** | Üç katmanlı: <br>1. **Gecikme yükseltme.** `rag.py:81-86` bu mekanizmayı zaten ölçmüş ve belgelemiş: 4.571 karakterlik bir tablo chunk'ı rerank'i 893 ms → 3.321 ms'ye çıkardı, çünkü *"BATCH EN UZUN DİZİYE PADLENİYOR"*. Yazar bu yüzden **tablo** adaylarını 1.200 karaktere kırptı — ama **metin adayları kırpılmıyor**. 21.814 karakterlik bir aday top-20'ye girerse aynı ceza, 4,8 kat büyüğüyle uygulanır.<br>2. **Boşa giden retrieval slotu.** Top-20'nin bir slotu neredeyse tamamen gürültü olan bir chunk'a gidiyor.<br>3. **Anlamsız embedding.** Baskın olarak `�` içeren bir vektör, sayfanın gerçek içeriğini temsil etmiyor — o sayfa **fiilen aranamaz**. |
| **DOĞRULAMA** | Üretim telemetrisi tutarlı: `rerank_ms` p99 = **5.220 ms**, max **5.426 ms**, 5 sn'yi aşan **8 istek**. |
| **ÖNERİ** | İki ayrı iş, karıştırılmamalı: <br>**(a) Anlık, ucuz, güvenli:** metin adaylarına da rerank-görünümü kırpması uygula — tablo tarafında **zaten kanıtlanmış** desen (`RERANK_TABLO_KARAKTER`). LLM'e giden kaynak metin **aynen kalır** (Kural 5). Kuyruk gecikmesini sınırlar.<br>**(b) Asıl düzeltme:** `embed_kitap.py`'ye `�` oranı kalite kapısı ekle (ör. >%30 ise chunk'ı atla) ve **yalnızca Fizik-9'u** yeniden indeksle. §20 gereği yeniden indeksleme **onay ister**. |
| **ÖNCELİK** | **(a) P1** (tek satır sınıfı, ölçülmüş mekanizma) / **(b) P2, ONAY GEREKTİRİR** |

### R-03 — `kazanim_kod` kolonu var, indeksi var, **tamamen boş ve hiç okunmuyor**

| | |
|---|---|
| **KANIT** | `SELECT count(*) … WHERE kazanim_kod IS NOT NULL` → **0** (8.726 satırın hepsi NULL). `grep -rn "kazanim" server/ --include=*.py` → **hiç eşleşme yok**. `benchmark/schema.sql` hem kolonu hem `idx_chunk_egitim_kazanim_kod` indeksini oluşturuyor. |
| **DEĞERLENDİRME** | CLAUDE.md bunu **doğru** anlatıyor (2026-08-30'da düzeltilmiş): kazanım filtresi bir gelecek-faz önerisi, bugünkü davranış değil. Bu turda ek olarak doğrulanan: kolon yalnızca okunmuyor, **hiç yazılmamış da**. |
| **AYRIŞMA (R-D2)** | `bac8b91` commit'inin başlığı **"Kazanım katmanı (RAG)"** — ama commit `server/`'a **tek satır dokunmuyor**. Yaptığı: `benchmark/`'a 208 MEB kazanımı ve 1.476 alıştırma sorusu yüklemek. Bunlar **ayrı tablolarda** (`kazanim`, `kazanim_test_soru`), `chunk_egitim.kazanim_kod` ile **bağlantısız**. Commit başlığı RAG'ın değiştiğini ima ediyor; değişmedi. |
| **RİSK** | Düşük (kullanılmayan kolon zararsız). Ama boş bir kolon üzerindeki indeks ve yanıltıcı commit başlığı, sonraki okuyucuyu "kazanım filtresi çalışıyor" sanmaya iter — CLAUDE.md'nin geçmişte tam olarak düştüğü tuzak. |
| **ÖNERİ** | Kod değişikliği **yok**. `docs/mimari.md` §12.1'in "tasarım, uygulanmadı" olduğu net kalsın. |
| **ÖNCELİK** | **P3 (belgeleme)** |

### R-04 — `chunk_tablo` 19 kitabın 1'inde dolu, ama kapı 19 kitapta da açık

| | |
|---|---|
| **MEVCUT DURUM** | `TABLO_KAYNAGI=True` **her** sorguda `_tablo_getir`'i çağırıyor. `chunk_tablo` yalnızca `kitap_id=1` için dolu (67 satır). Diğer 18 kitap için sorgu **her istekte** çalışıp boş dönüyor. |
| **KANIT** | `SELECT kitap_id, count(*) FROM chunk_tablo GROUP BY 1` → yalnızca `1 \| 67` |
| **RİSK** | İşlevsel risk **yok** — boş sonuç zararsız ve `rag.py:241-247` bunu ayrı `try/except` ile sarmalamış (iyi tasarım). Maliyet: 18 kitap için istek başına bir gereksiz indekssiz tarama. Ölçülen `retrieval_ms` ortalaması **23 ms** olduğundan bu **ihmal edilebilir** — Kural 10 gereği optimize **edilmemeli**. |
| **ASIL RİSK** | CLAUDE.md doğru uyarıyor: *"yeni kitap eklendiğinde ölçüm tekrarlanmalı"*. `TOP_K_TABLO=10` ve kırpma sınırı **tek kitapla** kalibre edildi. |
| **ÖNCELİK** | **P3** (izlenecek, eylem yok) |

### R-05 — Sistem promptu üç yerde kopya (bkz. `ARCHITECTURE_ANALYSIS.md` A-03)

`SISTEM_SABLON` `rag.py:98`, `benchmark/katman_test.py` ve `mimari.md §8`'de
**birebir üçlenmiş**. Kodun kendi docstring'i itiraf ediyor. Benchmark'ın
ölçtüğü prompt ile üretimin kullandığı prompt sessizce ayrışabilir ve bunu
**hiçbir test yakalamaz** (`test_rag.py` de yok — `TEST_ANALYSIS.md` T-01).
**P1**

### R-06 — Yaklaşık indeks yok: **doğru karar**, ölçümle destekleniyor

`benchmark/schema.sql`: *"HNSW/IVFFlat kasıtlı olarak eklenmedi — yaklaşık
indeks recall ölçümünü bozar. Kural 10: ölçmeden optimizasyon yapma."*

Üretim telemetrisi bu kararı **doğruluyor**: `retrieval_ms` ortalaması
**23 ms** (8.726 chunk üzerinde tam kosinüs taraması). Toplam gecikmenin
(p50 6.148 ms) **%0,4'ü**. Darboğaz retrieval değil — **LLM (ort. 5.271 ms)**
ve **rerank (ort. 1.761 ms)**.

**Sonuç: pgvector'a dokunulmamalı, indeks eklenmemeli, DB migrasyonu
önerilmemeli.** (§11'in "DB'yi gereksiz yere değiştirme" kuralı burada
ölçümle karşılandı.)

---

## 4. §12'nin sorusuna cevap

> *"Farabi öğrencinin sorusundan doğru MEB kazanımını ve doğru kaynak
> içeriğini bulabiliyor mu?"*

**Doğru kaynak içeriği: EVET — ama yalnızca 19 kitabın 1'i için kanıtlı.**
Biyoloji-9'da Recall@4 = **%91,4**, katmanlı doğru-tespit = **%95**
(`RAG_BASELINE.md` §3). Diğer 18 kitap: **UNKNOWN, hiç ölçülmedi.**

**Doğru MEB kazanımı: HAYIR — böyle bir yetenek yok.** `kazanim_kod`
tamamen boş, hiçbir sorguda okunmuyor (R-03). Kazanım verisi (208 kazanım)
`benchmark/`'ta ayrı bir tabloda duruyor ve RAG'a **bağlı değil**. Retrieval
`kitap_id` + anlamsal benzerlikle çalışıyor; kazanım eşleştirmesi bir
tasarım önerisi (`mimari.md` §12.1), uygulanmış bir davranış değil.

---

## 5. Puan

**RAG: 7 / 10.**

Artı (ölçülmüş): üç bağımsız halüsinasyon kapısı ve hepsi kodda gerçekten
uygulanmış; sayfa sınırı hiç aşılmıyor → kaynak gösterimi her zaman doğru;
`kitap_id` filtresi zorunlu; retrieval 23 ms (indeks kararı ölçümle doğru);
`chunk_tablo` entegrasyonu örnek bir mühendislik işi — gerekçesi, ölçümü ve
tek satırlık geri dönüşü (`TABLO_KAYNAGI`) kodda yazılı; üretim telemetrisi
(`metrik`) gerçekten toplanıyor.

Eksi (ölçülmüş): değerlendirme seti 19 kitabın 1'ini kapsıyor ve %80'i
insan onayı almamış (R-01) — bu tek başına puanı 8+'tan aşağı çekiyor;
Fizik-9'da 21.814 karakterlik bozuk chunk'lar ve metin adaylarında kırpma
yokluğu (R-02); prompt üç yerde kopya (R-05); RAG çekirdeğinin birim testi
yok (T-01).
