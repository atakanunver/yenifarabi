# RAG_BASELINE — Farabi

> **Bu dosyanın amacı:** ileride "iyileştirdik" diyebilmek için bugünkü
> durumun **ölçülmüş** kaydı. §14: *"Baseline yoksa 'iyileşti' iddiasında
> bulunma."*

---

## 1. Taban damgası — KİRLİ AĞAÇ

```
git rev-parse HEAD  →  dbd3fdd7a0e4f4f7a5dd3b56a592716e0d192edc
```

**Bu taban `dbd3fdd` DEĞİL — `dbd3fdd` + commit edilmemiş çalışma ağacıdır.**
Ölçüm anında değişik olan dosyalar:

```
 M .gitignore                       M client/tests/test_arac_kaydi.py
 M CLAUDE.md                        M client/tests/test_transcript.py
 M client/CLAUDE.md                 M client/tools/dogrula.py
 M client/actions/kayit.py          M client/ui.py
 M client/core/prompt.txt           M docs/mimari.md
 M client/core/transcript.py        M server/main.py      ← RAG yolunda
 M client/main.py                   M server/rag.py       ← RAG ÇEKİRDEĞİ
                                    M server/saglayicilar.py
?? client/actions/yoklama_al.py     ?? plan.md
                                    (15 dosya, +583 / −69 satır)
```

⚠️ **`server/rag.py` ve `server/main.py` commit edilmemiş.** `chunk_tablo`
entegrasyonunun (`TABLO_KAYNAGI`, `_tablo_getir`, `RERANK_TABLO_KARAKTER`)
tamamı bu commit edilmemiş diff'in içinde. **Bu tabanı yeniden üretmenin tek
yolu bu çalışma ağacıdır** — `git checkout dbd3fdd` farklı bir sistem verir.

**İLK ÖNERİ:** ölçüme devam etmeden önce bu diff'i commit et. Aksi hâlde
buradaki hiçbir rakam kalıcı olarak yeniden üretilemez.

**Ortam:** Ubuntu 26.04, 2× RTX 3060, Python 3.14.4, `farabi-api.service`
**active**, `ollama.service` **active**, PostgreSQL `127.0.0.1:5432`.
GPU (boşta): GPU 0 → 6.867 MiB kullanımda / **5.045 MiB boş**;
GPU 1 → 9.951 MiB kullanımda / **1.961 MiB boş**.

---

## 2. Ölçülmüş taban — kod & test

| Metrik | Taban | Komut |
|---|---|---|
| Ruff bulgusu | **420** | `.venv-tools/bin/ruff check client server benchmark tahtayoklama --statistics` (ruff **0.16.5**, **yapılandırma dosyası yok**) |
| Ortalama karmaşıklık | **A (4,15)** / 768 blok | `radon cc client server benchmark -s -a` |
| D+ blok | **17** (D 15, E 1, F 1) | aynı |
| MI "A" olmayan dosya | **3** | `radon mi client server benchmark -s` |
| Bandit High / Medium | **0 / 3** | `bandit -r client server benchmark` |
| Server testleri | **65 passed** (3,56 sn) | `server/venv/bin/python -m pytest server/tests/ -q` |
| Client testleri | **144 passed** (2,81 sn) | `client/venv/bin/python -m pytest tests/ -q` |
| Server coverage | **%59** | `coverage report --data-file=server/.coverage` |
| Client coverage | **%35** | `coverage report --data-file=client/.coverage` |
| `server/rag.py` coverage | **%19** | aynı |

---

## 3. RAG retrieval tabanı — ⚠️ 3 HAFTA BAYAT

**Kaynak:** `benchmark/reports/20260811_071108.json` ve
`katmanli_20260811_071503.json` — `benchmark/reports/`'daki **en yeni** dosyalar.

Yapılandırma: `kitap_id=1` (biyoloji-9), `top_k=20`, `top_n=4`, `esik=0.55`,
`esik_rerank=0.5`, model `qwen2.5:14b`.

### 3.1 Retrieval / rerank (2026-08-11)

| Grup | n | Recall@4 | rerank top-1 doğru | MRR | ort. arama |
|---|---|---|---|---|---|
| A (kitapta net var) | 17 | **1,000** | 0,882 | 0,941 | 0,124 sn |
| B (dolaylı) | 18 | **0,833** | 0,778 | 0,816 | 0,146 sn |
| C (kitapta yok) | 5 | — | — | — | 0,148 sn |
| **TOPLAM** | **40** | **0,914** | **0,829** | **0,877** | — |

### 3.2 Katmanlı (eşik + LLM) doğru davranış (2026-08-11)

| Grup | n | Doğru tespit | Eşikle reddedilen | LLM'e giden |
|---|---|---|---|---|
| A | 17 | **1,00** | 0 | 17 |
| B | 18 | **0,889** | 0 | 18 |
| C | 5 | **1,00** | 2 | 3 |
| **TOPLAM** | **40** | **0,95 (38/40)** | 2 | 38 |

### 3.3 ⚠️ İki "38/40" aynı şey DEĞİL — karşılaştırma tuzağı

CLAUDE.md: *"`chunk_tablo` bağlanınca 35/40 → **38/40**"*.
Yukarıdaki 2026-08-11 raporu, `chunk_tablo` **hiç bağlı değilken de**
**38/40 (%95)** gösteriyor.

Çelişki değil — **iki farklı harness**:

| | `katmanli_20260811` | `plan.md:77-80` (2026-09-02) |
|---|---|---|
| Yol | `benchmark/katman_test.py` (çevrimdışı) | canlı `POST /api/egitim/question` |
| Taban | **38/40** | **35/40** |
| `chunk_tablo` | yok | var → **38/40** |

Aynı 40 soru, aynı kitap, ama **aynı taban değil** (38 vs 35). Sebep
araştırılmadı; muhtemel etkenler: canlı yolun `ESIK_RERANK=0,5`'i (benchmark
`esik=0,55` kullanıyor), farklı sıcaklık/prompt yolu, ya da `SISTEM_SABLON`
kopyalarının ayrışması (`RAG_ANALYSIS.md` R-05).

> **BAĞLAYICI KURAL:** `35/40 → 38/40` **yalnızca kendi içinde** geçerli bir
> karşılaştırmadır (aynı gün, aynı harness, iki kez üretildiği `plan.md:99`'da
> yazılı). Bu rakamlar `benchmark/reports/`'takilerle **KARŞILAŞTIRILAMAZ**.
> Gelecekteki her ölçüm **hangi harness'la** üretildiğini yazmalıdır.

### 3.4 Kapsam tavanı (dürüst sınır)

- Değerlendirme seti **19 kitabın 1'ini** kapsıyor (biyoloji-9).
- 40 sorunun **8'i** insan onaylı (`onaylandi: true`), **32'si değil**.
- `chunk_tablo` yalnızca `kitap_id=1` için dolu (67 satır).
- `ESIK_RERANK=0,5` **tek kitapla** kalibre edildi (`rag.py:14-18`).
- **Diğer 18 kitap için retrieval kalitesi: UNKNOWN.**

### 3.5 Bu turda canlı yeniden ölçüm YAPILMADI — gerekçe

1. ~~GPU baskısı~~ — **bu gerekçe 2026-09-02'de ÇÜRÜTÜLDÜ.** `benchmark/venv`
   `torch 2.13.0+cpu` kullanıyor (server'da `2.13.0`, CUDA). Yani
   `recall_test.py` modelleri **CPU'ya** yüklüyor, GPU'ya HİÇ dokunmuyor —
   ders sırasında bile GPU açısından güvenli. Kalan maliyet CPU/RAM.
   (Aynı bulgunun ikinci sonucu: rapordaki `ortalama_arama_sn` 0,12-0,15 sn
   bir **CPU** rakamı, üretimi temsil etmiyor — üretim gecikmesi için §4.)
2. Canlı API yolu (`POST /api/egitim/question`) auth zorunlu; tahta anahtarı
   `server/config/api_keys.json`'da ve **CLAUDE.md o dosyayı okumayı
   yasaklıyor**.

> **Beklemede — iki komut, ders saatleri dışında:**
> ```
> # (1) 2026-08-11 tabanını bugünkü kodla yeniden üret
> benchmark/venv/bin/python recall_test.py --sorular sorular.json --kitap-id 1
> # (2) §3.3'teki 38-vs-35 farkını AYIRT ET:
> #     benchmark esik=0,55 kullandı, üretim ESIK_RERANK=0,5 kullanıyor.
> #     Aynı seti üretimin eşiğiyle koş — fark kapanıyorsa sebep eşik,
> #     kapanmıyorsa şüpheli SISTEM_SABLON ayrışması (R-6).
> benchmark/venv/bin/python recall_test.py --sorular sorular.json --kitap-id 1 --esik 0.5
> ```
> R-01 (soru seti onayı) öncesinde yapılırsa daha da değerli.

---

## 4. Üretim telemetrisi — BU TURDA ÖLÇÜLDÜ (yeni)

`metrik` tablosu, **354 gerçek istek**, 2026-08-11 → 2026-09-02.
Bu, `benchmark/`'tan bağımsız ve **daha güncel** bir kanıt kaynağı.

### 4.1 Sonuç dağılımı ve uçtan uca gecikme

| `sonuc` | n | % | ort. ms | p50 | **p95** | max | ort. skor |
|---|---|---|---|---|---|---|---|
| `ok` | 266 | **%75,1** | 7.056 | 6.454 | **11.599** | 19.622 | 0,972 |
| `yetersiz_kaynak` | 81 | **%22,9** | 3.638 | 3.431 | 6.990 | 26.882 | 0,596 |
| `hata` | 4 | %1,1 | 431 | 424 | 870 | 874 | 1,000 |
| `sayi_kontrolu_reddi` | 3 | %0,8 | 8.198 | 7.981 | 8.869 | 8.968 | 0,996 |

**Okunuşu:**
- **`ok` cevaplarının ortalama rerank skoru 0,972**, `yetersiz_kaynak`'ınki
  **0,596**. Eşik (0,5) iki dağılımın arasında duruyor → **ESIK_RERANK
  üretimde gerçekten ayırt edici**, yalnızca benchmark'ta değil. Bu, tabanın
  en güçlü tek bulgusu.
- **Sayı kontrolü 3 kez devreye girdi** (%0,8) — üçüncü savunma katmanı
  teorik değil, gerçekten çalışıyor ve gerçekten uydurma yakaladı.
- `hata` yalnızca 4 (%1,1) ve hepsi **hızlı** (ort. 431 ms) → erken
  başarısızlık, ders akışını uzun süre bekletmiyor.

### 4.2 Aşama bazlı gecikme (`sonuc='ok'`)

| Aşama | ortalama | p95 |
|---|---|---|
| retrieval | **23 ms** | — |
| rerank | **1.761 ms** | 3.813 ms |
| LLM (Ollama) | **5.271 ms** | 9.296 ms |

**Darboğaz net: LLM (%75) ve rerank (%25). Retrieval %0,4.**
→ pgvector indeksi/DB migrasyonu **gereksiz** (`RAG_ANALYSIS.md` R-06).

### 4.3 Günlük eğilim — `chunk_tablo` etkisi üretimde doğrulandı

| Gün | n | rerank p50 | toplam p50 |
|---|---|---|---|
| 2026-08-11 | 14 | 858 ms | 3.047 ms |
| 2026-08-13 | 9 | 841 ms | 856 ms |
| 2026-08-25 | 42 | 882 ms | 4.973 ms |
| **2026-09-02** | **284** | **1.432 ms** | **6.148 ms** |

`chunk_tablo` devreye girdiği gün rerank p50 **~880 ms → 1.432 ms** (+%63).
Bu, `plan.md`'nin bağımsız olarak ölçtüğü **893 ms → 1.439 ms** rakamıyla
**neredeyse birebir örtüşüyor** → iki bağımsız ölçüm birbirini doğruluyor.

**Kuyruk:** `rerank_ms` p99 = 5.220 ms, max 5.426 ms, 5 sn'yi aşan 8 istek —
`RAG_ANALYSIS.md` R-02'deki (kırpılmamış uzun metin adayları) mekanizmayla
tutarlı.

---

## 5. Hedefler — taban → hedef

§23: hedefler tabana göre belirlenir, mutlak sayılara körü körüne değil.

| Metrik | Taban | Hedef | Nasıl |
|---|---|---|---|
| İnsan onaylı soru | **8 / 40** | **40 / 40** | R-01, insan işi |
| Değerlendirilen kitap | **1 / 19** | **3 / 19** | R-01 |
| `server/rag.py` coverage | ~~%19~~ → **%96** | ~~≥%70~~ ✅ **AŞILDI** (2026-09-02, `3e93347`) | T-01 tamamlandı |
| Testi olmayan server modülü | ~~6~~ → **4** | ~~≤4~~ ✅ **KARŞILANDI** (`rag`, `proxy` testlendi; kalan: `dosya`, `db`, `client_durum`, `main`) | T-01/R-2 tamamlandı |
| `rerank_ms` p99 | **5.220 ms** | **< 4.000 ms** | R-02(a), metin kırpma |
| Bozuk (`�`) chunk | **13** (Fizik-9) | **0** | R-02(b), **onay gerekir** |
| Ruff bulgusu | **420** | önce **sabitle** (Q-00) | yapılandırma yoksa hedef anlamsız |
| Client pinli bağımlılık | ~~0/13~~ → **13/13** | ✅ **KARŞILANDI** (`bd99d29`, `requirements.lock.txt`) | D-01 tamamlandı |
| Bandit High | **0** | **0** (koru) | — |
| Test geçme | ~~209~~ → **248 / 248** | koru | server 65→104, client 144 |

### Bozulmaması gereken metrikler (§23 takas kuralı)

Aşağıdakiler **her** refactoring'den sonra yeniden ölçülmeli; kötüleşirse
değişiklik geri alınmalı:

- **Recall@4 = 0,914** ve **katmanlı doğru tespit = 0,95** (biyoloji-9)
- **`ok` oranı %75,1** ve **`ok` ortalama skoru 0,972**
- **uçtan uca p95 = 11.599 ms**
- **209/209 test geçiyor**
- **Bandit High = 0**

> **Ders anı gecikmesi bir doğruluk metriği kadar önemlidir.** p95 = 11,6 sn
> bir sınıf ortamı için hâlihazırda yüksek; doğruluğu artıran hiçbir
> değişiklik bunu daha da büyütmemeli.
