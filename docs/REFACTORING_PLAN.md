# REFACTORING_PLAN — Farabi

> Taban: `RAG_BASELINE.md`. Her madde §22 formatında.
> **Bu turda hiçbir kod değiştirilmedi** (§21). Aşağıdakiler onay bekleyen
> öneri kalemleridir.
>
> Sıralama **Impact × Probability × Cost** (§15) — sayısal eşiklerle değil,
> Farabi'nin kritiklik sırasıyla: **çalışan sistem > davranışın korunması >
> gerçek bug > lint > stil**.

---

## Önerilen sıra (bağımlılıklar dahil)

```
R-00 (diff'i commit et)  ─── her şeyin önkoşulu
   ↓
R-1 test_rag.py ──┬──► R-4 metin kırpma      (test olmadan doğrulanamaz)
                  └──► R-6 prompt tekilleştir (test olmadan doğrulanamaz)
R-2 gorsel_uret limiti   (bağımsız, tek satır)
R-3 client lockfile      (bağımsız, kod değişikliği yok)
R-5 soru seti onayı      (bağımsız, insan işi)
```

---

## R-00 — Commit edilmemiş diff'i commit et

```
ID:                  R-00
Priority:            P0 (süreç — kod değil)
Category:            baseline / yeniden üretilebilirlik
File:                15 değişik + 2 untracked dosya
Symbol:              —
Problem:             chunk_tablo RAG entegrasyonunun TAMAMI (server/rag.py,
                     server/main.py) commit edilmemiş. plan.md ve
                     client/actions/yoklama_al.py untracked.
Evidence:            git status --short → M server/rag.py, M server/main.py …
                     git diff --stat → 15 dosya, +583/−69
Impact:              Bu belgedeki HİÇBİR ölçüm yeniden üretilemez.
                     `git checkout dbd3fdd` bambaşka bir sistem verir.
                     Ayrıca üretimde çalışan kodun git'te karşılığı yok —
                     bir geri alma gerekirse dayanak yok.
Risk:                Commit etmemenin riski, etmenin riskinden büyük.
Proposed change:     Mantıksal olarak ayır (§19 "bir commit = bir değişiklik"):
                       1. feat(rag): chunk_tablo retrieval'a bağlandı
                       2. fix(saglayicilar): ölü gorsel zinciri onarıldı
                       3. feat(client): yoklama_al aracı
                       4. docs: CLAUDE.md/mimari.md güncellemeleri + plan.md
Tests required:      Mevcut 209 test (hepsi zaten geçiyor)
Benchmark required:  Hayır
Estimated effort:    30 dk
Dependencies:        yok
Rollback strategy:   —
```

---

## R-1 — `server/tests/test_rag.py` yaz

```
ID:                  R-1
Priority:            P1
Category:            test / güvenlik ağı
File:                server/tests/test_rag.py (YENİ), server/tests/conftest.py (YENİ)
Symbol:              RagMotoru.sorgula, _sayilar_kaynakta_mi, _logla
Problem:             Farabi'nin halüsinasyon savunmasının TAMAMI rag.py'de ve
                     birim testi YOK. Coverage %19.
Evidence:            ls server/tests/ → test_rag.py yok
                     coverage report → server/rag.py 120 stmt, 97 miss, %19
Impact:              rag.py'ye yapılan HER değişiklik bugün otomatik kontrolsüz.
                     Korunmayan davranışlar: ESIK_RERANK kapısı (ana savunma),
                     YETERSIZ_KAYNAK tespiti (Türkçe İ/I normalizasyonu dahil),
                     sayı kontrolü, metrik/soru_log gizlilik ayrımı,
                     chunk_tablo id'lerinin negatif yazılması.
Risk:                Test YAZMANIN riski ~sıfır (üretim kodu değişmez).
                     Yazmamanın riski: R-4/R-6 güvenle yapılamaz.
Proposed change:     GPU'suz, DB'siz birim testleri:
                     1. _sayilar_kaynakta_mi — saf fonksiyon, 8-10 vaka
                        (ondalık nokta/virgül, kaynakta olmayan sayı,
                        sayısız cevap, kısmi eşleşme)
                     2. sorgula() statü makinesi — sahte embed_model/reranker/
                        conn ile (yapıcı ZATEN enjeksiyonlu, rag.py:117):
                        • skor < 0,5 → yetersiz_kaynak VE _llm_cevap HİÇ
                          çağrılmadı (ana savunmanın asıl iddiası)
                        • LLM "YETERSIZ_KAYNAK" → yetersiz_kaynak
                        • LLM uydurma sayı → sayi_kontrolu_reddi
                        • mutlu yol → ok + sources[] + sayfa numarası
                        • aday yok → yetersiz_kaynak
                        • embed/rerank/LLM istisnası → hata (+ metriğe yazıldı)
                     3. _logla sözleşmesi: yüksek skorlu ok'ta soru_log'a
                        YAZILMADIĞI (gizlilik kuralı), metrik'e HER ZAMAN
                        yazıldığı
                     Desen hazır: server/tests/test_saglayicilar.py (212 sat.)
                     ağa çıkmadan zincir mantığını test ediyor.
Tests required:      Bu maddenin kendisi
Benchmark required:  Hayır (kasıtlı — GPU/DB'siz koşabilmeli)
Estimated effort:    3-4 saat
Dependencies:        R-00
Rollback strategy:   Test dosyasını sil — üretim kodu hiç değişmedi
```

---

## R-2 — `gorsel_uret`'e yükleme boyut sınırı

```
ID:                  R-2
Priority:            P1
Category:            güvenlik / dayanıklılık
File:                server/proxy.py
Symbol:              gorsel_uret_endpoint
Problem:             await dosya.read() boyut kontrolü olmadan tüm dosyayı
                     belleğe alıyor. dosya.py'de YUKLEME_LIMIT_MB=60 var ve
                     uygulanıyor; proxy.py'de YOK.
Evidence:            server/proxy.py:56-70 (tam okundu, hiçbir kontrol yok)
                     server/dosya.py:37 YUKLEME_LIMIT_MB = 60
Impact:              Kimliği doğrulanmış tek bir büyük yükleme
                     farabi-api.service'i belleğe boğabilir → TÜM tahtaların
                     içerik/RAG yolu düşer.
Risk:                Çok düşük. Yeni bir sınır ekliyor, mevcut geçerli
                     kullanımı etkilemiyor (ekran görüntüleri « 60 MB).
Proposed change:     dosya.py'nin limitini proxy.py'de yeniden kullan;
                     aşılırsa UretimYanit(status="hata", …) — 500 DEĞİL,
                     böylece client'ın Kural 2 düşüş yolu normal çalışır.
Tests required:      server/tests/test_proxy.py (YENİ): limit üstü → status
                     "hata"; limit altı → sağlayıcı çağrıldı
Benchmark required:  Hayır
Estimated effort:    45 dk
Dependencies:        R-00
Rollback strategy:   Tek fonksiyonluk değişiklik, git revert
```

---

## R-3 — Client bağımlılık lockfile'ı

```
ID:                  R-3
Priority:            P1
Category:            dağıtım / yeniden üretilebilirlik
File:                client/requirements.lock.txt (YENİ)
Symbol:              —
Problem:             client/requirements.txt'te 13 paketin 13'ü de PİNSİZ.
Evidence:            grep -cE '^[a-zA-Z].*==' client/requirements.txt → 0
                     Kurulu gerçek sürümler: DEPENDENCY_ANALYSIS.md D-01
Impact:              Yeni bir tahtaya kurulum, 9-A'dakinden FARKLI sürümler
                     kurar. google-genai (Gemini Live = SESİN TAMAMI) hızlı
                     gelişen bir SDK — kırıcı bir sürüm sınıfta sessiz ses
                     arızası demek. Ayrıca "hangi tahtada" hatası ayırt
                     edilemez hâle gelir.
Risk:                SIFIR — kod değişikliği yok, mevcut kurulumlara
                     dokunulmuyor. Yalnızca yeni bir dosya.
Proposed change:     client/venv/bin/pip freeze > client/requirements.lock.txt
                     Kurulum betiği lock'u kullansın; requirements.txt
                     okunabilir üst-seviye liste olarak KALSIN (yorumları
                     değerli).
                     Aynısı server/ ve benchmark/ için: P2 (D-02, D-03).
Tests required:      Yok (kod değişmiyor)
Benchmark required:  Hayır
Estimated effort:    20 dk
Dependencies:        yok
Rollback strategy:   Dosyayı sil
```

---

## R-4 — Rerank görünümünde metin adaylarını da kırp

```
ID:                  R-4
Priority:            P1
Category:            performans / veri kalitesi
File:                server/rag.py
Symbol:              sorgula (aday listesi kurulumu), RERANK_TABLO_KARAKTER
Problem:             Tablo adayları rerank görünümünde 1200 karaktere
                     kırpılıyor; METİN adayları kırpılmıyor. CrossEncoder
                     batch'i EN UZUN DİZİYE padliyor → tek uzun aday tüm
                     partinin maliyetini yükseltiyor.
Evidence:            rag.py:81-86 mekanizmayı ZATEN ölçmüş ve belgelemiş:
                       4.571 karakterlik tablo chunk'ı → rerank 893→3.321 ms
                     Üretim telemetrisi: rerank_ms p99 = 5.220 ms, max 5.426,
                       5 sn üstü 8 istek
                     KİTAP BAZLI chunk uzunluk dağılımı (canlı DB) — sabiti
                     BU belirler, korpus geneli p95 DEĞİL. Mekanizma bir
                     SORGU-BAŞI kuyruk özelliği: batch, O SORGUNUN top-20'sinin
                     EN UZUN üyesine padleniyor.
                       kitap  ders              p99     max    >2000  >4000
                        19    Fizik-9          9.112  21.814     13     10
                        17    Coğrafya-9       3.938   4.673     39      4
                        18    Din Kültürü-9    3.606   4.212     59      2
                        14    Türk Dili-10     2.844   4.163     19      1
                         8    Fizik-10         2.461   3.801      7      0
                    →    1    BİYOLOJİ-9       2.392   3.122     12      0
                       (kalan 13 kitap: max < 3.000, >4000 hepsi 0)
Impact:              Ders anı gecikmesinin kuyruğu. Uçtan uca p95 zaten
                     11.599 ms — sınıf için yüksek.
                     ⚠️ KAPSAM SINIRI: R-4 YALNIZCA gecikme kuyruğunu
                     düzeltir. Fizik-9'un 13 bozuk chunk'ı ~%99 oranında
                     `�` karakteri — herhangi bir kapakla kırpıldığında da
                     ÇÖPLÜĞÜNÜ KORUR, embedding'i anlamsız kalır, o sayfa
                     ARANAMAZ olmaya devam eder. Aranabilirliği getiren
                     düzeltme R-12'dir (kalite kapısı + yeniden indeksleme).
                     R-4 kapatılırken "Fizik-9 s.169 düzeldi" SANILMAMALI.
Risk:                DÜŞÜK ama SIFIR DEĞİL. Kırpma yalnızca rerank'in GÖRDÜĞÜ
                     metne uygulanır; LLM'e giden kaynak metin AYNEN kalır
                     (Kural 5). Yine de sıralamayı teorik olarak
                     değiştirebilir → benchmark ZORUNLU.
Proposed change:     RERANK_METIN_KARAKTER = 4000, tablo tarafındaki desenle
                     birebir aynı.
                     SABİTİN GEREKÇESİ — kabul testinin koştuğu kitapta
                     NO-OP olmalı: biyoloji-9'un >4000 chunk sayısı SIFIR,
                     max'ı 3.122. Yani 4.000'lik kapak Recall@4=0,914'ün
                     ölçüldüğü kitaba HİÇ DOKUNMAZ; buna rağmen 21.814'lük
                     aykırı değeri 5,5 kat kırpar.
                     ⚠️ 2000 SEÇİLMEMELİ: biyoloji-9'un 12 chunk'ı 2.000'i
                     aşıyor (p99=2.392) — yani 2000, kırpmayı tam da kabul
                     testinin koştuğu kitaba uygular ve gate'i kendi kendine
                     kirletir. (İlk taslakta korpus geneli p95=1.777'den
                     türetilmişti; o rakam sorgu-başı padding mekanizması
                     için YANLIŞ tabandı.)
                     Etki: 8.726 chunk'ın 17'si (%0,19), hepsi ölçülmemiş
                     5 kitapta.
Tests required:      R-1'in test_rag.py'si + kırpmanın yalnızca rerank
                     girdisine uygulandığını, kaynak metnin tam kaldığını
                     doğrulayan bir test
Benchmark required:  EVET — ZORUNLU. recall_test.py + katman_test.py,
                     ÖNCE/SONRA. Recall@4 (0,914) ve katmanlı doğru tespit
                     (0,95) BOZULMAMALI.
Estimated effort:    1 saat + benchmark
Dependencies:        R-00, R-1.  İLGİLİ: R-12 (asıl veri düzeltmesi —
                     R-4 onun yerine GEÇMEZ, bkz. Impact)
Rollback strategy:   Sabiti None yap (tek satır) — kırpma devre dışı
```

---

## R-5 — Değerlendirme setini onayla ve genişlet

```
ID:                  R-5
Priority:            P1
Category:            RAG değerlendirme / kanıt
File:                benchmark/sorular.json
Symbol:              —
Problem:             40 sorunun 32'si onaylandi:false (LLM taslağı, insan
                     doğrulaması yok) ve set 19 kitabın 1'ini kapsıyor.
Evidence:            Counter(onaylandi) → {False: 32, True: 8}
                     benchmark/metin/ → yalnızca biyoloji-9.json
                     SELECT count(*) FROM kitap → 19
                     docs/mimari.md: soru seti "insan işi, kod değil"
Impact:              CLAUDE.md'deki HER doğruluk rakamı bu sete dayanıyor.
                     Bugün Farabi'nin doğruluğu, kendisiyle aynı sınıftan bir
                     modelin ürettiği ve insanın onaylamadığı sorularla
                     ölçülüyor. ESIK_RERANK=0,5 de bu tek kitapla kalibre
                     edildi (rag.py:14-18 bunu açıkça uyarıyor).
Risk:                Yok (veri işi, kod değişmiyor).
Proposed change:     (a) 32 soruyu onayla / düzelt / at → onaylandi:true
                     (b) 2 kitap daha × ~15 soru — biçim çeşitliliği için:
                         matematik_9 (formül ağırlıklı),
                         tarih_10 (düzyazı ağırlıklı)
                     (c) Genişletilmiş setle ESIK_RERANK'i YENİDEN kalibre et
Tests required:      —
Benchmark required:  EVET — genişletilmiş setle yeni taban
Estimated effort:    Öğretmen zamanı; (a) ~2 saat, (b) ~3 saat
Dependencies:        yok (bağımsız başlatılabilir)
Rollback strategy:   sorular.json.bak zaten mevcut
```

---

## R-6 — `SISTEM_SABLON`'u tekilleştir

```
ID:                  R-6
Priority:            P1
Category:            mimari / doğruluk garantisi
File:                server/rag.py, benchmark/katman_test.py
Symbol:              SISTEM_SABLON
Problem:             RAG sistem promptu ÜÇ yerde birebir kopya: rag.py:98,
                     benchmark/katman_test.py, docs/mimari.md §8.
Evidence:            server/rag.py:9-12 docstring bunu itiraf ediyor:
                       "Üç yerde de elle senkron tutulmalı; paylaşılan tek
                        bir prompt dosyası yok."
Impact:              Benchmark'ın ölçtüğü prompt ile üretimin kullandığı
                     prompt SESSİZCE ayrışabilir. O an tüm doğruluk iddiaları
                     geçersizleşir ve hiçbir test bunu yakalamaz.
                     RAG_BASELINE.md §3.3'teki açıklanamayan 38 vs 35 taban
                     farkının OLASI bir sebebi de bu.
Risk:                DÜŞÜK ama sıfır değil — prompt metni bit-bit aynı
                     kalmalı. Tek bir boşluk farkı LLM davranışını değiştirir.
Proposed change:     server/prompt_rag.py (tek sabit).
                     rag.py import etsin; katman_test.py sys.path ile aynı
                     sabiti okusun. mimari.md §8 metni tekrarlamak yerine
                     dosyaya İŞARET etsin.
Tests required:      R-1'in test_rag.py'si + prompt'un beklenen metinle
                     birebir eşleştiğini doğrulayan bir test (ayrışma
                     alarmı)
Benchmark required:  EVET — prompt bit-bit aynıysa sonuç değişmemeli;
                     bunu KANITLA (değişmezlik testi)
Estimated effort:    1,5 saat
Dependencies:        R-00, R-1
Rollback strategy:   git revert (saf taşıma)
```

---

## R-7 — `tahtayoklama/pdf_disari_aktar.py` F821

```
ID:                  R-7
Priority:            P1
Category:            gerçek bug
File:                tahtayoklama/pdf_disari_aktar.py:155
Symbol:              _sube_harfi
Problem:             Tanımlanmamış isim çağrılıyor → NameError.
Evidence:            ruff --select F821 → "Undefined name `_sube_harfi`"
                     grep -rn "_sube_harfi" tahtayoklama/ → yalnızca 2 sonuç:
                       satır 27 (DOCSTRING içinde) ve satır 155 (ÇAĞRI).
                       Fonksiyon HİÇBİR YERDE tanımlı değil.
Impact:              SINIRLI ama gerçek: satır 155 HATA YOLUNDA — PDF'ten
                     hiç öğrenci ayrıştırılamadığında çalışır. Yani
                     kullanıcı yardımcı bir hata mesajı yerine ham bir
                     NameError alır. Tam da en çok yardıma ihtiyaç duyduğu
                     anda. Çevrimdışı yönetim betiği, ders anında koşmuyor —
                     bu yüzden P0 değil.
Risk:                Çok düşük.
Proposed change:     Ya `_sube_harfi`'yi yaz (docstring'e göre: sınıf adının
                     son karakteri), ya da f-string'den çıkar. Docstring bir
                     davranış tarif ediyor — hangisinin DOĞRU olduğu
                     kullanıcıya sorulmalı.
Tests required:      tahtayoklama/ test altyapısı bu turda incelenmedi →
                     en azından elle: bilerek eşleşmeyen bir --sinif ile
                     çalıştır, kibar mesajın çıktığını gör
Benchmark required:  Hayır
Estimated effort:    30 dk
Dependencies:        yok
Rollback strategy:   git revert
```

---

## P2 — planlı refactoring

| ID | Öncelik | Konu | Kaynak |
|---|---|---|---|
| R-8 | P2 | `pyproject.toml` + `[tool.ruff]` — 420 rakamını sabitle; diğer tüm lint işlerinin önkoşulu | Q-00 |
| R-9 | P2 | `FarabiLive._execute_tool` F(52) → `kayit.py` registry dağıtımı. **Önce characterization test** | Q-01 |
| R-10 | P2 | `derslik`'i `istek` yerine `auth.TahtaKimligi`'nden al. **Diğer tahtalara kurulumdan ÖNCE P1** | A-04 |
| R-11 | P2 | `metin_uret`'e tahta başına jeton kovası (yeni bağımlılık yok) | S-03 |
| R-12 | P2 | Fizik-9'un 13 bozuk chunk'ı: `embed_kitap.py`'ye `�` kalite kapısı + yeniden indeksle. **§20 ONAY GEREKTİRİR** | R-02(b) |
| R-13 | P2 | `client/memory/` sil (%0 coverage, sıfır importer). Önce `long_term.json`'a bak | Q-05 |
| R-14 | P2 | Sağlayıcı zinciri canlılık kontrolü (systemd timer) — `gorsel` zinciri 3 hafta ölü kaldı ve kimse fark etmedi | D-05 |
| R-15 | P2 | `server/tools/metrik_ozet.py` — toplanan telemetri okunabilir olsun | A-05 |
| R-16 | P2 | `benchmark/requirements.txt` — ölçümün yeniden üretilebilirliği | D-03 |
| R-17 | P2 | `yoklama_al.py` commit + test | T-05 |
| R-18 | P2 | Ollama'yı `127.0.0.1`'e al, paylaşımı auth'lu uç üzerinden ver. **Paylaşım kararı kullanıcıya ait — önce sor** | S-01 |
| R-19 | P2, ONAY | `mypy`/`pyright` `.venv-tools`'a (üretim venv'ine DEĞİL) — Kural 8 | Q-07 |
| R-20 | P2 | 26 adet `except: pass` — tek tek, `saglayicilar.py`/`proxy.py` önce | Q-02b |

## P3 — backlog

| ID | Konu | Not |
|---|---|---|
| R-21 | 29 `DTZ` timezone bulgusu | **DOKUNMA** — zil/program/yoklama korunacak davranışlar listesinde |
| R-22 | 35 `RUF100` çürük `noqa` | R-8 ile birlikte |
| R-23 | `client/ui.py` `HudCanvas` ayrı modüle | E(37), ama arayüz testi pahalı |
| R-24 | `test_ders_hafizasi.py:121` `pytest.raises(Exception)` gevşek | B017 |
| R-25 | CLAUDE.md/mimari.md "13 kitap" → **19 kitap** | R-D1 |
| R-26 | CLAUDE.md'ye `yoklama_al` geri geldi notu | D-06 |
| R-27 | CLAUDE.md GPU rakamı 7.041 MiB → **5.045 MiB** | D-09 |

---

## Yapılmayacaklar (bilinçli)

- **pgvector → başka bir vektör DB.** Retrieval ölçülen toplam gecikmenin
  **%0,4'ü** (23 ms). §11 gereği darboğaz kanıtlanmadan migrasyon önerilmez.
- **HNSW/IVFFlat indeksi.** Aynı gerekçe + `schema.sql` yaklaşık indeksin
  recall ölçümünü bozacağını yazıyor.
- **Toplu `ruff --fix` / `ruff format`.** CLAUDE.md: *"Büyük ölçekli otomatik
  düzeltme yapılmaz."*
- **183 `BLE001`'in toplu düzeltmesi.** Çoğu Kural 2'nin ("Farabi asla dersi
  bozmaz") fiilî uygulaması. Yalnızca 26 sessiz `except: pass` ele alınacak.
- **Yeni servis/kütüphane** (Redis, Docker, Celery…). Kural 8 — hiçbir öneri
  bunları gerektirmiyor.
