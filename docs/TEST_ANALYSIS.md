# TEST_ANALYSIS — Farabi

> Taban: `dbd3fdd` + kirli ağaç.
> ```
> server/venv/bin/python -m pytest server/tests/ -q     → 65 passed in 3.56s
> cd client && venv/bin/python -m pytest tests/ -q      → 144 passed in 2.81s
> ```
> Coverage, **halihazırda diskte bulunan** `.coverage` dosyalarından okundu
> (`client/.coverage`, `server/.coverage`, ikisi de 2026-09-02 17:44-17:45).
> Üretim venv'ine **hiçbir paket kurulmadı** (Kural 8):
> `client/venv/bin/python -m coverage report --data-file=server/.coverage`

---

## 1. Taban (baseline)

| | Server | Client |
|---|---|---|
| Test sayısı | **65** | **144** |
| Sonuç | **hepsi geçti** | **hepsi geçti** (1 uyarı) |
| Süre | 3,56 sn | 2,81 sn |
| Coverage (toplam) | **%59** | **%35** |
| Test dosyası | 5 | 17 |

**Toplam 209 test, hepsi geçiyor, 6,4 saniyede.** Bu hızlı ve sağlıklı bir
geri bildirim döngüsü — refactoring için iyi bir zemin.

Not: iki toplam **karşılaştırılamaz**. Server'ın %59'u test dosyalarını da
sayıyor (%100 coverage'lı 508 satır test kodu). Kaynak-yalnız server
coverage'ı fiilen daha düşük.

---

## 2. En kritik bulgu

### T-01 — `server/rag.py` — halüsinasyon kapılarının tamamı, **%19 coverage, sıfır test dosyası**

| | |
|---|---|
| **AMAÇ** | Farabi'nin tek varoluş gerekçesi: uydurmadan, kaynaklı cevap |
| **MEVCUT DURUM** | `server/rag.py` — 120 statement, **97 miss = %19**. `server/tests/` altında **`test_rag.py` YOK.** |
| **KANIT** | `ls server/tests/` → `test_auth, test_ders_hafizasi, test_icerik, test_saglayicilar, test_yks` — hepsi bu. Coverage raporu: `server/rag.py 120 97 19%` |
| **RİSK** | CLAUDE.md'nin "RAG Kuralları (kritik)" bölümündeki **her savunma** bu dosyada ve hiçbiri birim testiyle korunmuyor: <br>• `ESIK_RERANK` kapısı (**ana savunma**, `rag.py:262`)<br>• `YETERSIZ_KAYNAK` tespiti — Türkçe `İ`/`I` normalizasyonu dahil (`rag.py:283`)<br>• `_sayilar_kaynakta_mi` — sayı kontrolü (`rag.py:112`)<br>• `metrik`/`soru_log` ayrımı — **gizlilik kuralı** (`rag.py:181-215`)<br>• `chunk_tablo` id'lerinin negatif yazılması (`rag.py:270`)<br><br>Bu mantık bugün **yalnızca** `benchmark/`'la doğrulanıyor: GPU + PostgreSQL + indekslenmiş kitap + ayrı venv gerektiren, dakikalar süren, **CI'da koşamayan** bir yol. Yani pratikte bir `rag.py` düzenlemesi **hiçbir otomatik kontrolden geçmiyor.**<br><br>⚠️ **Ve bu mantık gerçekten işe yarıyor — kaybedilecek bir şey var.** `RAG_BASELINE.md` §4.1, 354 gerçek üretim isteğiyle ölçüyor: `ok` cevaplarının ortalama rerank skoru **0,972**, `yetersiz_kaynak`'ınki **0,596** — eşik (0,5) ikisinin arasında, yani **üretimde gerçekten ayırt ediyor**. Sayı kontrolü 3 kez devreye girip uydurma yakalamış. Yani T-01 "belki bozuk bir kod test edilmiyor" değil, **"kanıtlanmış şekilde çalışan bir savunma korumasız duruyor"** demek. |
| **ÖNERİ** | `server/tests/test_rag.py` — **saf fonksiyonlar ve karar mantığı** için, GPU/DB'siz: <br>1. `_sayilar_kaynakta_mi` doğrudan test edilebilir (saf fonksiyon, bağımlılık yok) — 8-10 vaka: ondalık virgül/nokta, kaynakta olmayan sayı, sayısız cevap.<br>2. `RagMotoru`'yu sahte `embed_model`/`reranker`/`conn` ile kur (yapıcı **zaten enjeksiyonla** çalışıyor — `rag.py:117`), `sorgula()`'nın **statü makinesini** test et: eşik altı → `yetersiz_kaynak` (ve **LLM'e hiç gidilmediğini** doğrula), LLM `YETERSIZ_KAYNAK` dedi → `yetersiz_kaynak`, sayı uydurdu → `sayi_kontrolu_reddi`, mutlu yol → `ok` + `sources`.<br>3. `_logla` sözleşmesi: yüksek skorlu `ok`'ta `soru_log`'a **yazılmadığını** doğrula (gizlilik kuralı, sahte cursor ile).<br><br>`saglayicilar` ve `auth` testleri bu deseni **zaten** kullanıyor (`test_saglayicilar.py` 212 satır, sahte HTTP) — yani altyapı ve örnek mevcut. |
| **ÖNCELİK** | **P1 — bu belgedeki en önemli tek iş** |

---

## 3. Diğer test boşlukları

### T-02 — Testi hiç olmayan server modülleri

| Modül | Satır | Coverage | Test dosyası |
|---|---|---|---|
| `server/dosya.py` | 567 | **%8** | **yok** |
| `server/rag.py` | 344 | **%19** | **yok** (T-01) |
| `server/proxy.py` | 71 | %70 | **yok** (dolaylı) |
| `server/db.py` | 37 | %56 | **yok** |
| `server/client_durum.py` | 70 | %70 | **yok** |
| `server/main.py` | 259 | %66 | **yok** |

`dosya.py` **%8** — repodaki en düşük anlamlı coverage. 416 statement'ın
382'si hiç çalıştırılmamış. Ve bu dosya `pandas 3.0.5` / `openai 3.0.0` /
`PyMuPDF` gibi **pinsiz** major-sürüm paketlere dayanıyor
(`DEPENDENCY_ANALYSIS.md` D-02). Yani: en kırılgan bağımlılık kümesi, en az
test edilen kodda. **P2**

### T-03 — Client: iki god-file'ın kapsamı düşük

| Dosya | Statement | Miss | Coverage |
|---|---|---|---|
| `client/ui.py` | 1.609 | 1.347 | **%16** |
| `client/main.py` | 919 | 640 | **%30** |

`main.py`'nin test edilmemiş %70'i `_execute_tool`'un F(52) dallanmasını
içeriyor (`CODE_QUALITY_ANALYSIS.md` Q-01). PyQt6 arayüzünü test etmek
pahalıdır ve `ui.py` için düşük coverage **savunulabilir**; ama `main.py`'nin
araç dağıtımı arayüz değil, **saf mantık** ve test edilebilir. **P2**

### T-04 — `actions/` katmanı: 22 aracın çoğu %11-%22 arası

```
site_goster %11   ekran_goruntusu_al %11   pencere_kapat %12   web_search %13
eba %14   youtube_video %14   file_processor %15   ekrandaki_soruyu_oku %14
web_ac %20   dosya_ac %21   uygulama_ac %21   yks_sorulari %22   yoklama_al %28
```

İyi durumdakiler: `ders_hafizasi` %100, `kayit.py` %87, `kitap_sorusu` %51,
`pdf_sayfa` %46.

Bunlar LLM'in çağırdığı araçlar; her biri Kural 2 gereği **hata durumunda
sessizce kısıtlayıcı bir metne düşmek zorunda**. O düşüş yolları büyük ölçüde
test edilmemiş. **P2**

### T-05 — `client/actions/yoklama_al.py` — yeni, izlenmiyor, testsiz

`git status` → `?? client/actions/yoklama_al.py`. `kayit.py:537`'de
**kayıtlı** ve dolayısıyla LLM tarafından çağrılabilir. Coverage **%28**.
Yoklama, CLAUDE.md'nin "özellikle korunacak davranışlar" listesinde.

Kod **okundu** ve savunma açısından iyi durumda: dosya varlığı kontrolü,
`subprocess.Popen` non-blocking, `shell=False`, geniş `try/except` ile
kullanıcıya Türkçe hata mesajı, çıktı okunmuyor. **Gerçek bir kusur
bulunmadı** — eksik olan yalnızca test ve git takibi.

**ÖNERİ:** commit et + `tests/test_yoklama_al.py` (3 vaka: script yok →
kibar mesaj; `Popen` patlıyor → kibar mesaj; mutlu yol → `Popen` doğru
argümanlarla çağrıldı). **P2**

### T-06 — `server/tests/conftest.py` yok

Client'ta `tests/conftest.py` **örnek alınacak kalitede** — gerçek
`logs/farabi.log` ve ders transkriptlerinin test gürültüsüyle kirlenmesini
ortam değişkenleriyle önlüyor ve **nedenini** açıklıyor.

Server'da karşılığı yok. Bugün sorun değil (server testleri DB'ye
dokunmuyor) ama T-01'deki `test_rag.py` yazılırken sahte `conn`/model
fixture'ları için doğal yer burası olacak. **P2 (T-01'in parçası)**

### T-07 — Test seviyeleri ayrılmamış

§18'in istediği `UNIT → INTEGRATION → RAG → API → E2E` ayrımı yok: tek düz
`tests/` dizini, marker yok, `pytest.ini`/`pyproject` yok (Q-00).

Bugün pratik sorun yaratmıyor (209 test 6,4 sn'de koşuyor). Ama `test_rag.py`
gelince "GPU'suz koşabilenler" ile "gerçek DB isteyenler" ayrımı gerekecek.
**ÖNERİ:** Q-00'ın `pyproject.toml`'una `markers = ["gpu", "db"]` ekle.
**P3**

### T-08 — RAG değerlendirmesi CI'da koşamaz

`benchmark/recall_test.py` + `katman_test.py` gerçek bir değerlendirme
harness'ı (§13 anlamında iyi tasarlanmış) ama: GPU, PostgreSQL, indekslenmiş
kitap ve ayrı bir venv gerektiriyor; `benchmark/requirements.txt` **yok**
(D-03); en son rapor **2026-08-11** tarihli — yani `chunk_tablo`
değişikliğinden **öncesi**. Ayrıntı: `RAG_BASELINE.md`. **P1**

---

## 4. İyi yapılmış şeyler

- **209 test 6,4 saniyede geçiyor** — refactoring için güçlü zemin.
- `client/tests/conftest.py` gerçek log dosyalarını koruyor **ve nedenini
  belgeliyor**.
- `server/tests/test_auth.py` 346 satır, `auth.py`'yi **%98** kapsıyor —
  güvenlik-kritik kodun hakkı verilmiş, T-01'in olması gereken hâlinin örneği.
- `test_saglayicilar.py` (212 sat.) ağa çıkmadan sağlayıcı zinciri mantığını
  test ediyor — `test_rag.py` için doğrudan kopyalanabilir desen.
- `client/core/ders_motoru.py` **%88**, `program.py` **%94**, `logger.py`
  **%95** — ders akışının çekirdeği gerçekten korunuyor.
- Testlerde gerçek ağ/DB çağrısı yalnızca 2 client dosyasında geçiyor ve
  oralarda da sahtelenmiş.

---

## 5. Puan

**Test: 5 / 10.**

Artı: 209/209 geçiyor, hızlı; `auth` %98, `ders_motoru` %88, `program` %94 —
kritik yolların bir kısmı gerçekten korunuyor; conftest disiplini örnek.

Eksi: **RAG çekirdeğinin test dosyası yok ve coverage %19** (T-01) — projenin
en kritik mantığı otomatik korumasız; `dosya.py` %8 (T-02); 6 server modülünün
testi yok; `ui.py` %16 / `main.py` %30 (T-03); RAG değerlendirmesi CI'da
koşamıyor ve son raporu **3 hafta bayat** (T-08).

Puanı 5'te tutan tek sebep T-01: kapsamın nerede eksik olduğu, ne kadar eksik
olduğundan daha önemli.
