# FARABİ — PDF / VISION / GRAFİK / TABLO ANALİZİ
## Durum tespiti + mimari öneri (ONAY BEKLİYOR — kod yazılmadı)

> Tarih: 2026-09-02 · Makine: farabi.local · Yöntem: koddan okuma + canlı ölçüm
> **Bu turda hiçbir kod değiştirilmedi, model kurulmadı, servis/systemd/GPU
> eşlemesi/requirements/DB'ye dokunulmadı.** Aşağıdaki her sayı ya bu makinede
> ölçüldü ya da kaynağı belirtildi; ölçülmeyenler açıkça `TAHMİN` olarak
> işaretlendi.
>
> Test tabanı (değişiklik öncesi referans): `server` **65/65**, `client`
> **144/144** geçiyor.

---

# UYGULAMA GÜNLÜĞÜ — 2026-09-02 (onay sonrası)

> Aşağıdaki §0–§K **durum tespiti raporudur ve olduğu gibi bırakılmıştır**
> (o anki gerçeği gösteriyor). Onaydan sonra fiilen yapılanlar burada.

## ✅ Anahtar entegrasyonu
`apikeys.env` → `server/config/api_keys.json`. Yedek scratchpad'e alındı,
dosya izni (600) korundu. **Yalnızca `groq_api_key` değişti** — diğer 6
anahtar zaten günceldi; `openrouter_api_key` ve `board_keys` env'de olmadığı
için DOKUNULMADI. Raporun §0'daki hipotezi doğrulandı: anahtarlar yenilenmiş
ama kuruluma alınmamıştı.

`apikeys.env`'deki `GEMINI_API_KEY` **server'a yazılmadı** — Gemini mimari
gereği yalnızca client'ta (9-A'nın kendi `config/api_keys.json`'ı, ses
oturumu). Bilerek dokunulmadı: hatalı bir Gemini anahtarı ses oturumunu
tamamen keser, bu da binadaki en görünür arıza olur. İstenirse ayrıca
yapılır. `CLOUDFLARE_API_TOKEN` / `VERCEL_API_TOKEN` Farabi'de hiç
kullanılmıyor.

## ✅ Güvenlik — `.gitignore` genişletildi
Eski kurallar TAM YOL idi (`server/config/api_keys.json`), yanındaki
`apikeys.env` ve `api_keys_yeni ….txt` ignore kapsamı DIŞINDAYDI. Artık
desen tabanlı: `*.env`, `**/api_keys*`, `!**/api_keys.example.json`.
Doğrulandı: üç sır dosyası da ignored, iki `.example.json` şablonu hâlâ
takipte.

## ✅ FAZ 0 — `gorsel` zinciri onarıldı (`server/saglayicilar.py`)

Yeni anahtarla yapılan ölçüm, raporun §0'ını bir noktada **düzeltti**:
groq anahtarı artık geçerli (metin çağrısı 0,8 sn'de OK) **ama
`llama-4-scout` modeli groq hesabının kataloğunda ARTIK YOK** (`models.list`:
groq'ta hiçbir görsel modeli kalmamış). Yani anahtar yenilense de o basamak
asla çalışmayacaktı.

| Görev | Önce | Sonra |
|---|---|---|
| `gorsel` | groq/llama-4-scout **(404)** → nvidia/llama-3.2-90b-vision **(timeout)** | `mistral/pixtral-12b-2409` → `mistral/mistral-medium-latest` → `nvidia/meta/llama-3.2-11b-vision-instruct` |
| `kitap_ozet` | nvidia/llama-3.3-70b **(410 Gone)** → deepseek → ollama | `groq/openai/gpt-oss-120b` → deepseek → ollama |
| `soru_taslak` | deepseek → mistral → nvidia/llama-3.3-70b **(410)** → ollama | deepseek → mistral → `groq/openai/gpt-oss-120b` → ollama |

Üçüncü görsel basamağı bilerek **başka bir sağlayıcıda**: ilk ikisi aynı
mistral anahtarını paylaşıyor, tek bir 429/402 ikisini birden soğutur.

**Uçtan uca doğrulama** (`ekrandaki_soruyu_oku`'nun birebir yolu — gerçek
`POST /api/egitim/dosya_isle`, `action=ocr`, board auth, 281 KB PNG):
`HTTP 200, 10,1 sn, status=ok`, doğru Türkçe tablo çıktısı. Journal'da
"sıradaki sağlayıcıya geçiliyor" satırı YOK → 1. basamak (pixtral) ilk
denemede başardı. **Önceki hâl: ~31 sn sonra hata.**

## ✅ FAZ 1 — `chunk_tablo` RAG'a bağlandı (`server/rag.py`, `server/main.py`)

Tasarım: `chunk_egitim` top-20 ve `chunk_tablo` top-10 **ayrı** çekilir,
rerank BİRLEŞİM üzerinde çalışır, top-4 oradan seçilir. Tek birleşik sorgu
KULLANILMADI — tablo satırları metin adaylarını havuzdan iterdi.
`ESIK_RERANK=0.5` değiştirilmedi. Tablo sorgusu ayrı `try/except` içinde:
patlarsa metin yolu hiç etkilenmez.

**Ölçüm — 40 soruluk doğrulanmış set, canlı API, her yapılandırma 2 kez
koşuldu (sonuçlar birebir tekrarlandı, gürültü değil):**

| Yapılandırma | A | B | C | TOPLAM | medyan gecikme | rerank_ms |
|---|---|---|---|---|---|---|
| Bayrak KAPALI (taban) | 17/17 | 13/18 | 5/5 | 35/40 **%88** | 5,2 sn | 893 |
| `TOP_K_TABLO=5` | 17/17 | 14/18 | 5/5 | 36/40 %90 | 6,7 sn | 2167 |
| `TOP_K_TABLO=10`, kırpmasız | 17/17 | 15/18 | 5/5 | 37/40 %92 | 7,9 sn | 3321 |
| **`TOP_K_TABLO=10` + rerank kırpma 1200** | 17/17 | **16/18** | 5/5 | **38/40 %95** | **5,7 sn** | 1439 |

**Grup A ve C hiç bozulmadı** (%100 / %100) — yani ne yalnızca-metin
recall'ı düştü, ne de "kitapta yok" savunması zayıfladı. Kazanç tamamen
Grup B'de (çoklu-sayfa sentez): 13/18 → 16/18. Düzelen sorular tam olarak
`raganaliz.txt`'in 2026-08-25'te "bilinen zayıf nokta" diye işaretlediği
sorulardı (ateş karıncaları s.155-156; bakteri/arke/ökaryot s.51-53).

**Yan bulgu — ölçüm sırasında çıktı, ayrıca değerli:** tablo eklenince
rerank 893 → 3321 ms'ye fırladı (aday başına ~240 ms; metin adaylarında
~45 ms). Sebep: `CrossEncoder`'a `max_length` verilmemiş
(`server/main.py:60`), model 8192 token'a kadar kabul ediyor ve **batch en
uzun diziye padleniyor** — tek bir 4571 karakterlik tablo TÜM partinin
maliyetini yükseltiyor. Rerank görünümü 1200 karaktere kırpılınca hem
gecikme tabana yaklaştı (5,7 sn) hem de doğruluk ARTTI (37→38). LLM'e giden
kaynak metin TAM kalır, metin adayları hiç kırpılmaz.

**Geri dönüş:** `server/rag.py`'de `TABLO_KAYNAGI = False` → sistem taban
davranışına döner. Bu yol ölçüm sırasında fiilen kullanıldı ve çalıştığı
doğrulandı (35/40 tabanı iki kez yeniden üretildi).

**Testler:** `server` 65/65, `client` 144/144 — değişiklik öncesi ve
sonrası aynı. Ruff: dokunulan üç dosyada yeni bulgu yok (rag.py'de +1
BLE001, dosyada zaten 5 tane olan bilinçli "dersi bozma" deseninin aynısı).

**Bilerek ERTELENDİ (yapılmadı, gizlenmedi):** raporun §E'sinde tablo
kaynağının `9. Sınıf Biyoloji, s. 84 (tablo)` diye gösterilmesi öneriliyordu.
Server tarafı hazır (`sources[].tur` alanı eklendi, geriye dönük uyumlu) ama
`client/actions/kitap_sorusu.py:126-127` kaynağı hâlâ yalnızca `page`+`book`
ile kuruyor — yani sınıfta tablodan gelen bir cevap metinden gelenle AYNI
gösteriliyor. Kaynak YANLIŞ değil (sayfa numarası doğru), yalnızca daha az
belirgin. Yapılmadı çünkü client değişikliği 9-A'ya `farabiguncelle.sh` ile
senkron gerektiriyor ve bu turun onayı server tarafıydı. Tek satırlık iş.

**Ayrıca aday (yapılmadı):** rerank kırpması şu an YALNIZCA tablo adaylarına
uygulanıyor. Aynı padding etkisi metin tarafında da var (`chunk_egitim`
ort. 1249, en fazla 3122 karakter) — oraya da uygulamak muhtemel bir ek
kazanç, ama mevcut davranışı değiştireceği için AYRI bir değişiklik ve kendi
40-soruluk turunu gerektirir (Kural 5). **Bilinen sınır:** 1200 karakteri
aşan büyük bir tablonun sonraki satırları retrieval'ı etkilemez.

**Not — sonraki adım:** `chunk_tablo` şu an yalnızca `biyoloji-9` için dolu
(67 tablo). Diğer 18 kitap için `tools/tablo_cikar.py` + `benchmark/
embed_tablo.py` koşturulmalı (offline, GPU/API yok). Bu ölçüm bir kitapla
yapıldı; her yeni kitap sonrası tekrar edilmeli.

## ✅ YEREL VLM BENCHMARK — ilk ölçümler (Qwen2.5-VL-3B, GPU 0)

**Yöntem — üretime hiç dokunulmadı:** `systemd`, `ollama.service`, GPU
eşlemesi, `server/venv`, `requirements.txt` DEĞİŞMEDİ. Geçici, izole bir
ollama örneği (`port 11435`, `CUDA_VISIBLE_DEVICES=0`, AYRI model dizini
`/home/ata/vlm-benchmark/models`) foreground süreç olarak çalıştırıldı.

**Engel bulundu:** `ollama pull qwen3-vl / qwen2.5vl / llava / moondream`
hepsi **başarısız** — `registry.ollama.ai` manifest'i 200 dönüyor ama BLOB
indirmesi **503** veriyor (okul ağı model CDN'ini engelliyor; MEB
sertifikaları sistem trust store'unda kurulu, bu bir sertifika sorunu
DEĞİL). Hugging Face çalışıyor (4,4 MB/s ölçüldü) — model
`hf.co/ggml-org/Qwen2.5-VL-3B-Instruct-GGUF:Q4_K_M` üzerinden çekildi.
**Bu, ileride yerel model kurulacaksa kalıcı bir kısıt: ollama registry
yerine HF yolu kullanılmalı.**

### Ölçüm — gerçek ders kitabı sayfaları, bulut testleriyle AYNI sayfa/istem

| Ölçüt | Sonuç |
|---|---|
| **VRAM (model payı)** | **4.610 MiB** — 2,8 GB'lık dosyaya rağmen; 1106×1560 sayfa görüntüsü çok sayıda görsel token üretiyor |
| GPU 0 tepe (farabi-api dahil) | **11.477 / 12.288 MiB → yalnızca 811 MiB boş** |
| Gecikme | ilk çağrı 80,3 sn (model yükleme dahil), sonra **13,3 / 8,3 / 7,1 sn** |
| Tablo | okunabilir ama Türkçesi bozuk ("yammaması", "Yıkanabilir gazlar") |
| **Grafik** | ❌ **soruyu ıskaladı** — sayfada HEM bir tablo HEM x-t/v-t/a-t grafikleri var (sayfa metniyle doğrulandı; 172 vektör çizim, 0 raster). 3B tabloyu **doğru** okudu ama sorulan grafikleri hiç görmedi. pixtral ve mistral-medium ikisi de grafiği bulup eksen/birim/değer verdi. Yani hata "uydurma" değil, **vektör çizilmiş grafiği algılayamama** — ki bu kitaplıkta 1.107 sayfa tam olarak bu türden |
| Matematik | ✓ iyi, LaTeX korunmuş — buluta yakın |
| **Şekil/diyagram** | ❌ **KENDİ İÇİNDE ÇELİŞKİLİ** — "Kara yosunu: Tohumlu bitkidir" deyip aynı cevapta onu "Tohumsuz Bitkiler" listesine koydu |

### Ara sonuç (ölçüme dayalı, tahmin değil)

1. **Co-residency (GPU 0'da farabi-api ile birlikte) ölçümle ELENDİ.**
   3B model tek başına 4,6 GB alıyor ve GPU 0'da 811 MiB bırakıyor. Ayrıca
   §G'deki "7.041 MiB boş" rakamı **düzeltilmeli**: o taze-yükleme
   anındaki değerdi; gerçek bir çalışma gününden sonra PyTorch'un önbellek
   ayırıcısı bloğu bırakmıyor, farabi-api 6.858 MiB tutuyor → **gerçek boş
   alan 5.430 MiB**. 7B bir VLM (~8-9 GB beklenir) buraya HİÇ sığmaz.
2. **Kalite, ders için yeterli değil — iki AYRI kusur:**
   - *Vektör grafikleri algılayamıyor.* `fizik-10` s.60'ta sayfadaki
     x-t/v-t/a-t grafiklerini hiç görmedi (aynı sayfadaki tabloyu doğru
     okuduğu hâlde). Bu kitaplıkta **1.107 sayfa** vektör-yoğun (§D.3) —
     yani tam da bu sayfa sınıfı.
   - *Gerçek halüsinasyon.* `biyoloji-9` s.57'de "Kara yosunu: Tohumlu
     bitkidir" dedi; sayfa metni bunun TERSİNİ yazıyor ("kara yosunları
     ... gibi çiçeksiz bitkilerde tohum oluşmaz") ve model aynı cevabın
     devamında kara yosununu "Tohumsuz Bitkiler" listesine koydu —
     kendisiyle çelişti. Bulut modelleri aynı sayfada doğru sınıflandırdı.
     Bu, projenin en temel kuralının ("uydurma yok") tam karşıtı.
3. **Hız avantajı da yok:** ısınmış hâlde 7–13 sn, bulut pixtral 8–9 sn.

### Henüz ölçülmedi (dürüst sınır)

**Qwen2.5-VL-7B** indirildi/indiriliyor ama **GPU'da ölçülemedi**: 5.430 MiB
boş alana sığmıyor, ölçmek için `farabi-api.service`'in durdurulması
gerekiyor — bu ölçüm ders saatleri içinde YAPILMADI (Kural 2). Güvenli
pencere: öğle arası (12:10–13:30) ya da 15:50 sonrası. 7B'nin **kalitesi**
ayrıca CPU'da (GPU riski sıfır) ölçülebilir; hız anlamsız olur ama
"grafik/şekil sorusunu doğru cevaplıyor mu" sorusu cevaplanır.

---

# 0. ÖNCE BUNU OKU — MEVCUT VISION YOLU KIRIK (ve henüz kimse fark etmedi)

İstenen iş "mevcut multimodal katmanı geliştirmek"ti. Ölçüm sırasında çıkan
gerçek şu: **var olan tek görsel yolu (`gorsel` görev zinciri) bugün tamamen
kırık** — yani `ekrandaki_soruyu_oku` ve `file_processor`'ın görsel/OCR işi
9-A'da bugün çağrılsa çalışmaz. Loglar (bkz. §0.1) bu yolun 2026-08-14'ten
beri hiç çağrılmadığını gösteriyor: arıza **gizli**, ilk gerçek kullanımda
patlayacak. Üzerine bir multimodal katman koymadan önce altındaki bu
basamağın onarılması gerekiyor.

Zincir (`server/saglayicilar.py::GOREV_ZINCIRLERI["gorsel"]`) iki basamak,
ikisi de düştü (gerçek çağrılarla ölçüldü, 2026-09-02):

| Basamak | Sonuç | Ölçülen |
|---|---|---|
| `groq / meta-llama/llama-4-scout-17b-16e-instruct` | **401 Invalid API Key** | 0,5 sn'de düşüyor; `models.list` bile 401 |
| `nvidia / meta/llama-3.2-90b-vision-instruct` | **zaman aşımı** | 30 sn'de, 60 sn'de ve 120 sn'de de yanıt yok |

Ve `gorsel_uret()` bilerek `evrensel_yedek=False` ile çağrılıyor
(`saglayicilar.py:206`) — yani **üçüncü bir basamak yok**, zincir bitince
`RuntimeError` fırlıyor.

**Sınıfta görünen hâli:** öğretmen "Farabi, ekrandaki soruyu oku" dediğinde
araç ~31 saniye sessiz kalıyor (groq'un 0,5 sn'si + nvidia'nın 30 sn'lik
timeout'u), sonra `dosya.py` `"AI görsel analizi başarısız: …"` döndürüyor
(`server/dosya.py:122`). Araç
zaman aşımı 45 sn olduğu için (`kayit.py`, `ekrandaki_soruyu_oku`)
Farabi'nin kendi "sınıfa teknik sorun anlatma" koruması bile devreye
girmiyor — araç 31. saniyede *başarıyla* bir hata metni döndürmüş oluyor.

Anahtarların kendisi hakkında iki ayrı bulgu (değer okunmadı/basılmadı):

- **nvidia anahtarı GEÇERLİ.** `meta/llama-3.3-70b-instruct` çağrısı 401
  değil **410 Gone — "end of life"** döndürdü; bu kimliği doğrulanmış bir
  cevap. Yani sorun anahtar değil, model. Ama bunun ikinci bir sonucu var:
  **`kitap_ozet` zincirinin 1. basamağı da ölü** (410) — sessizce
  deepseek'e düşüyor, kimse fark etmemiş.
- **groq anahtarı geçersiz (401).** Bu bir tahmin değil, ölçüm. Muhtemel
  sebep — doğrulanmadı: `git status`'ta duran
  `server/config/api_keys_yeni 30.08.2026.txt` dosyası, anahtarların
  yenilenip `api_keys.json`'a **taşınmamış** olabileceğini düşündürüyor.
  Tek satırlık kontrol sizde: bu dosyadaki groq anahtarı ile
  `api_keys.json`'daki aynı mı?

Çalışan alternatif zaten elinizde (gerçek ders kitabı sayfalarıyla ölçüldü):

| Sağlayıcı/model | Görsel destekliyor mu | Ölçülen süre | Türkçe kalite |
|---|---|---|---|
| `mistral / pixtral-12b-2409` | **evet** | 5,4 – 7,4 sn | iyi (tablo/şekil/LaTeX) |
| `mistral / mistral-medium-latest` | **evet** (zaten zincirlerde metin olarak var) | 3,0 – 8,1 sn | iyi |
| `openrouter` ücretsiz VLM slug'ları | **hayır** — 404, "unavailable for free" | — | — |

### 0.1 Loglar ne diyor (journal + ders transkriptleri, incelendi)

Arıza ne zamandan beri var ve sınıfta tetiklendi mi — varsayım yerine log:

- **`journalctl -u farabi-api.service`** (kapsam: 2026-08-11 → bugün, tam
  geçmiş): `POST /api/egitim/dosya_isle` **hayatı boyunca 2 kez** çağrılmış
  (ikisi de 2026-08-14, ikisi de 200 OK), o tarihten sonra **hiç**.
  `gorsel` zincirine ait tek bir başarısızlık satırı yok — `saglayicilar`
  logger'ı journal'a düşüyor (deepseek 402'leri orada görünüyor), yani
  susmuyor: **bu yol üretimde hiç denenmemiş.**
- **9-A ders transkriptleri** (SSH ile, 15 dosya, 2026-08-23 → 2026-09-01):
  `ekrandaki_soruyu_oku` / `ekran_goruntusu_al` / "görsel analizi" geçen
  **tek bir satır yok**. `client/logs/farabi.log` bu iki aracın
  2026-08-30'dan beri modele düzenli **sunulduğunu** doğruluyor (her
  oturumda "Araçlar: 18 bildirim").

> **Doğru okuma:** bu, derse bugün zarar veren bir arıza DEĞİL —
> **henüz tetiklenmemiş, gizli (latent) bir arıza.** Araçlar 2026-08-30'dan
> beri modele açık; öğretmen ilk kez "ekrandaki soruyu oku" dediğinde sınıf
> 31 saniye sessiz kalacak. FAZ 0'ın aciliyeti buradan geliyor: ucuz, bugün
> ölçüldü, ve ilk gerçek kullanımdan ÖNCE yapılırsa hiç yaşanmamış olur.

> ⚠️ Ayrıca **güvenlik**: `server/config/api_keys_yeni 30.08.2026.txt` hem
> **untracked hem de `.gitignore` KAPSAMINDA DEĞİL** (`git check-ignore` ile
> doğrulandı). Bugün atılacak bir `git add -A`, API anahtarlarını repoya
> commit eder — CLAUDE.md Kural 9 ihlali. Bu rapordan bağımsız, ayrıca
> ele alınmalı.

---

# A. MEVCUT PDF PIPELINE (koddan doğrulandı)

İki ayrı yol var, ikisi de **yalnızca metin**; hiçbiri görsel modele gitmiyor.

### A.1 Konu bazlı yol — `ders_icerigi`

```
Gemini Live tool call: ders_icerigi(ders, sinif, konu/tema, sayfa_adedi)
   ↓  client/actions/ders_icerigi.py  (HTTP + X-Farabi-Board-Key)
POST /api/egitim/ders_icerigi         (server/icerik.py)
   ↓  _bolum_bul()   → önce elle eşleme (icerik/eslemeler/*.json),
   │                    sonra kelime-örtüşme skoru ≥ 0,5
   ↓  _ilgili_sayfalar() → konu kelimelerinin sayfa metnindeki frekansı;
   │                        seçim icerik/onbellek/_sayfa_secimi.json'a cache'lenir
   ↓  _metin_cikar() → icerik/metin/<kitap>.json (önceden çıkarılmış düz metin);
   │                    yoksa canlı pdfplumber
   ↓  MAX_KARAKTER = 6000'e kırp + başlık/kaynak/uyarı satırları ekle
   ↓  _SON_KITAP[derslik][ders] = seçilen kitap  ← pdf_sayfa bunu kullanacak
{status, metin, baslik} → client → FunctionResponse(text) → Gemini Live
```

### A.2 Sayfa numarası yolu — `pdf_sayfa` (İKİ ayrı çağrı)

```
pdf_sayfa(sayfa, ders, sinif)
   ↓ (1) GET /api/egitim/pdf_sayfa        → PyMuPDF render, ZOOM=2.0, PNG
   │      _pdf_sayfa_kitap_coz(): _SON_KITAP tercihi + _kitap_bul fallback
   │      cache: /mnt/farabi-data/farabi/icerik/onbellek/pdf_sayfa/<kitap>_s<n>.png
   │      → client 30 dosyalık yerel LRU'ya yazar → player.show_image() → EKRAN
   ↓ (2) GET /api/egitim/pdf_sayfa_metni  → aynı kitap+sayfanın GERÇEK METNİ
          kalite kapısı: U+FFFD oranı > %2 ise "bulunamadi"
   → metin varsa: "SAYFA METNİ (… buna dayandır)" olarak modele eklenir
   → metin yoksa: "içeriği UYDURMA" uyarısı eklenir
```

### A.3 Soru-cevap yolu — `kitap_sorusu` → RAG

```
POST /api/egitim/question (kitap_id, soru ≤ 500 karakter)
   ↓ bge-m3 embed → pgvector top-20 (WHERE kitap_id = …) → bge-reranker-v2-m3
   ↓ top-4 → EŞİK 0,5 (altındaysa LLM'e HİÇ gitme)
   ↓ Ollama qwen2.5:14b, temp 0.2, ≤3 cümle
   ↓ _sayilar_kaynakta_mi(): cevaptaki her sayı kaynak metinde birebir yoksa REDDET
{status, answer, sources[], latency_ms, request_id}
```
**Ölçülen uçtan uca RAG gecikmesi (4 gerçek sorgu, canlı serviste):
5,4 / 5,6 / 8,0 / 5,6 sn.** Yani ders içi "normal" gecikme zaten ~6 sn.

### A.4 Çevrimdışı içerik hattı (ayrı, ders anında koşmaz)

```
kitap_metin.py  → icerik/metin/<kitap>.json        (düz sayfa metni)
kitap_index.py  → bölüm/tema indeksi + bölüm başına yontem = "metin" | "gorsel"
tablo_cikar.py  → pdfplumber find_tables + kalite filtresi → icerik/tablolar/*.json
embed_kitap.py  → bge-m3 → chunk_egitim   (8.726 satır, 19 kitap)
embed_tablo.py  → bge-m3 → chunk_tablo    (67 satır, YALNIZCA biyoloji-9)
```

---

# B. MEVCUT EKRAN GÖRME PIPELINE

```
ekrandaki_soruyu_oku(talimat)                     [kayit.py, zaman_asimi=45 sn]
   ↓ player._win._screenshot_sig.emit(ctx)         (GUI thread'e geç, 5 sn bekle)
   ↓ ui.py::_ekran_goruntusu_yakala
        QApplication.primaryScreen().grabWindow(0) ← TÜM MASAÜSTÜ, kamera değil
        → logs/ekran/ekran_<zaman>.png             (son N dosya tutulur)
   ↓ actions/file_processor.py: multipart upload (timeout 60 sn)
POST /api/egitim/dosya_isle  action="ocr"
   ↓ server/dosya.py::_process_image → PIL → JPEG q85
   ↓ _ai_gorsel() → saglayicilar.gorsel_uret("gorsel", …)
   ↓ ✗ ZİNCİR KIRIK (bkz. §0) — ~31 sn sonra RuntimeError
```

`ekran_goruntusu_al` ise yalnızca PNG'i ders loguna yazar, hiçbir modele
göndermez.

**Bu yolun içerik kalitesi, PDF yoluna göre yapısal olarak daha düşük:**
- Ekran görüntüsü **tüm masaüstünü** alıyor — Farabi HUD'u, içerik paneli
  çerçevesi, kalem/silgi çizim katmanı, ne varsa hepsi karede.
- Tahta ekranının çözünürlüğü sabit; PDF ise istenen zoom'da render
  edilebiliyor. Ölçüm: `ZOOM=2.0` → 1106×1560 px, render 120–180 ms;
  `zoom=1.5` → 830×1170 px, 60–102 ms.
- Ekran görüntüsünde **sayfa numarası/kitap kimliği kaybolur** → kaynak
  gösterimi (`9. Sınıf Biyoloji, s. 84`) üretilemez.

→ **§11'in sorusuna cevap: PDF sayfası her koşulda ekran görüntüsünden daha
güvenilir kaynaktır.** Ekran görüntüsü yalnızca "PDF olmayan bir şey
gösteriliyor" durumunda (elle açılmış dosya, tahtaya yazılmış çözüm,
yapıştırılmış görsel) doğru araçtır.

---

# C. MEVCUT GEMINI LIVE PIPELINE

```
mikrofon → out_queue → session.send_realtime_input(media=…)   [SES, sürekli]
Gemini Live (models/gemini-2.5-flash-native-audio-preview-12-2025)
   ↓ response.tool_call
   ↓ _araclari_calistir()  ← alım döngüsünün DIŞINDA (55 sn'lik bir çağrının
   │                          dersi dondurduğu gerçek olaydan sonra ayrıldı)
   ↓ types.FunctionResponse(id, name, response={"result": <STRING>})
   ↓ session.send_tool_response(...)
Gemini Live sesli anlatır
```

**Kritik, koddan doğrulanmış kısıt:** araç sonucu Live oturumuna **yalnızca
düz metin** olarak dönüyor. `main.py`'de görüntü/`inline_data`/`Blob`
gönderen tek bir satır yok. Yani "Gemini Live sayfayı görsün" bugün
**yok olan bir yetenek**, kablolanması gereken bir şey değil — yeni bir
yetenek. (CLAUDE.md'nin sonundaki "gemini live'a vision kazandırabilirsin"
notu bir fikir, uygulama değil.)

İki ek bulgu:
- `client/core/vision_prompt.txt` **ölü dosya** — repoda hiçbir Python
  dosyası referans vermiyor (grep ile doğrulandı). Türkçe, pedagojik olarak
  iyi yazılmış bir görsel promptu; kullanılmıyor.
- `server/dosya.py`'deki görsel promptları **İngilizce** sabitler
  ("Extract all text visible in this image…"). Pratikte
  `ekrandaki_soruyu_oku` Türkçe bir `instruction` geçtiği için üzerine
  yazılıyor, ama `file_processor` doğrudan çağrıldığında İngilizce prompt
  kullanılıyor.

---

# D. EKSİKLER

**D.0 — Üretimde kırık (yeni özellik değil, ONARIM):**
1. `gorsel` zinciri tamamen ölü (groq 401 + nvidia timeout, üçüncü basamak yok).
2. `kitap_ozet` zincirinin 1. basamağı ölü (nvidia 410, end-of-life model adı).
3. `api_keys_yeni 30.08.2026.txt` gitignore kapsamında değil.

**D.1 — Yazılmış ama HİÇ KULLANILMAYAN yapılar (bedava kazanç):**
4. **`chunk_tablo` hiçbir sorguda okunmuyor.** 67 gerçek tablo embed edilmiş
   (biyoloji-9), `rag.py::_ilk_k_getir` yalnızca `chunk_egitim`'e bakıyor.
   grep sonucu: tabloyu SELECT eden tek satır yok.
5. **`bolum["yontem"] = "gorsel"` sinyali hiç dallanmıyor.**
   `kitap_index.py` bozuk-metin sayısına göre bölümü "görsel" işaretliyor,
   `icerik.py::_esleme_bolumu` bunu dict'e koyuyor — ve hiçbir yerde
   `if yontem == "gorsel"` yok. Hazır bir yönlendirme sinyali boşa gidiyor.
6. `chunk_egitim.kazanim_kod` kolonu dolu değil/okunmuyor (zaten belgeli).
7. `client/core/vision_prompt.txt` ölü.

**D.2 — Gerçekten yeni yetenek gerektirenler:**
8. Sayfa tipi sınıflandırması yok (TEXT/TABLE/GRAPH/DIAGRAM/FORMULA/IMAGE/MIXED).
9. Grafik/şekil/diyagram anlama yok — hiçbir yol görsel modele gitmiyor.
10. Matematiksel ifade çıkarımı yok; `fizik_9.pdf`'te 273 sayfanın **150'si**
    U+FFFD ile kirli (ölçüldü — diğer 18 kitapta toplam 4 sayfa).
11. Vision sonucu için önbellek yok, kaynak (`s. 84`) taşıma yolu yok.
12. Pedagojik katman (kazanım ilişkisi, sorulacak soru, olası öğrenci hatası) yok.

**D.3 — Ölçülen içerik profili (19 kitap, 5.045 sayfa):**

| Ölçüt | Sayfa | Oran |
|---|---:|---:|
| Toplam | 5.045 | %100 |
| **Hiç metni olmayan (taranmış olabilir)** | **11** | **%0,2** |
| Metni < 200 karakter | 112 | %2,2 |
| ≥1 gömülü raster görsel | 2.704 | %54 |
| ≥3 gömülü görsel | 1.129 | %22 |
| >150 vektör çizim (grafik/şema göstergesi) | 1.107 | %22 |
| **Vision adayı (birleşim)** | **3.223** | **%64** |
| Yalnızca metin (vision gereksiz) | 1.822 | %36 |
| U+FFFD içeren | 154 (150'si `fizik_9.pdf`) | %3 |

> **Bu tablonun en önemli satırı: taranmış PDF pratikte YOK (11 sayfa).**
> Yani problem OCR değil — kitaplar dijital doğumlu. Problem **yapı
> anlama**: tablo, grafik, şekil, formül. Bu, model seçimini de değiştirir:
> "OCR modeli" (olmOCR gibi) bu kitaplığın asıl derdine yanlış cevaptır.

---

# E. ÖNERİLEN VISION MİMARİSİ

Öneri **4 fazlı ve her fazı tek başına durdurulabilir**. Faz 0 ve 1 yeni
model/GPU/altyapı GEREKTİRMEZ.

### FAZ 0 — Onarım (yeni yetenek yok, yalnızca kırığı düzelt)
- `gorsel` zincirine çalışan basamaklar: `mistral/pixtral-12b-2409` (ölçüldü)
  ve `mistral/mistral-medium-latest` (ölçüldü). groq/nvidia listede kalsın
  (anahtar yenilenirse kendiliğinden dönerler; `_sogumada_mi` zaten koruyor).
- `kitap_ozet` zincirinin ölü nvidia model adını güncelle veya sırayı çevir.
- `gorsel_uret` timeout'u: 30 sn tek bir görsel çağrı için dar; iki basamağın
  toplamı zaten araç zaman aşımına yaklaşıyor.
- Anahtar dosyasını `.gitignore`'a al.

### FAZ 1 — Vision'sız kazanımlar (`chunk_tablo`'yu bağla)
Başarı kriterlerinizden **#2 ("bu tabloyu özetle") ve #3 ("tablodaki en
yüksek değer")** için görsel model şart değil: 67 tablo zaten yapısal JSON
olarak embed edilmiş durumda.
- `rag.py`'ye ikinci bir retrieval kaynağı: `chunk_tablo` (aynı `kitap_id`
  filtresi, aynı reranker, aynı eşik). Kaynak biçimi `9. Sınıf Biyoloji,
  s. 84 (tablo)`.
- `tablo_cikar.py` + `embed_tablo.py` kalan 18 kitap için çalıştırılır
  (offline, GPU yok, API yok).
- `bolum["yontem"] == "gorsel"` sinyali `ders_icerigi`'nin cevabına bir
  ipucu olarak eklenir ("bu bölüm ağırlıklı görsel — sayfayı `pdf_sayfa`
  ile göster").

### FAZ 2 — Sayfa tipi sınıflandırıcı (yerel, ucuz, modelsiz)
`fitz`/`pdfplumber` metriklerinden (metin uzunluğu, raster görsel sayısı,
vektör çizim sayısı, `find_tables` sonucu, formül sembolü yoğunluğu) sayfa
başına bir tip etiketi: `TEXT | TABLE | GRAPH | DIAGRAM | FORMULA | IMAGE |
MIXED`. Bu, §7'nin istediği ayrım ve §4'ün "akıllı routing"i — ve
%36'lık yalnızca-metin sayfayı vision'dan tamamen muaf tutar.
Ölçüm zaten yapıldı: bu sınıflandırma 5.045 sayfa için ~7 dakikada koşuyor,
GPU kullanmıyor.

### FAZ 3 — Çevrimdışı vision ön-işleme (asıl iş)
Yalnızca FAZ 2'nin `TABLE/GRAPH/DIAGRAM/FORMULA/MIXED` işaretlediği
sayfalar için, ders dışında:

```
sayfa → render (zoom 1,5; 830×1170; ~120 KB JPEG)
      → VLM  → YAPISAL JSON (§7'deki şema)
      → doğrulama kapısı (aşağı bkz.)
      → chunk_gorsel tablosu (yeni) + bge-m3 embedding → pgvector
```
Ders anında GPU/bulut yükü **sıfır** olur; retrieval zaten var olan
pgvector yolundan gelir.

### FAZ 4 — Ders anı (yalnızca cache-miss için)
```
"Farabi, bu grafiği yorumla"
  → o an ekranda ne var?  (_SON_KITAP + son pdf_sayfa çağrısı zaten biliniyor)
  → PDF sayfası ise: ÖNCE chunk_gorsel'den oku (cache hit → ~ms)
  → yoksa: canlı VLM çağrısı (ölçülen 5,4–7,4 sn) + sonucu kalıcı yaz
  → PDF DEĞİLSE: ancak o zaman ekran görüntüsü
  → RAG kaynaklarıyla birleştir → Gemini Live sesli anlatır
```

### E.1 — HALÜSİNASYON KAPISI (§8'in gereği) ve ÇÖZÜLMESİ GEREKEN ÇELİŞKİ

`rag.py::_sayilar_kaynakta_mi` cevaptaki **her sayının** `kaynak_metin`de
birebir geçmesini şart koşuyor. Vision'dan gelen sayılar görüntüden gelir,
`chunk_egitim` metninde geçmez.

> **Bu haliyle §8 ("kaynakta olmayan sayı üretme") ile §7 ("grafikteki veri
> noktalarını çıkar") birbirini kilitler:** vision JSON'u RAG kaynağı
> yapılırsa, tablo/grafik cevaplarının neredeyse hepsi
> `sayi_kontrolu_reddi` alır.

Önerilen çözüm — kuralı gevşetmeden kapsamını düzelt:
1. Vision JSON'unun **yalnızca içerik alanları** (`title`, `headers`,
   `rows`, `important_values`) kaynak metne katılsın; sayı kontrolü
   `chunk_egitim ∪ chunk_gorsel(içerik alanları)` üzerinden çalışsın.
   Kural aynen kalır: "cevaptaki sayı, gösterilen kaynakta geçmeli."
   > ⚠️ **`confidence`, `page`, `graph_type` ve her tür iç metadata bu
   > kümeye ASLA girmemeli.** `_sayilar_kaynakta_mi` düz alt-dize
   > karşılaştırması yapıyor (`sayi in kaynak_metin`) — `"confidence":
   > 0.91` gibi bir alan kaynak dizesine karışırsa `0`, `9`, `1`, `91`
   > rakamları serbest kalır ve **yalnızca metin tabanlı cevapların**
   > sayı savunması da sessizce zayıflar. Bu, gözden kaçarsa FAZ 3'ün en
   > sinsi yan etkisi olur.
2. Vision'ın kendi çıktısı **ayrıca** kapıdan geçsin: VLM'e "sayfada
   görünmeyen hiçbir sayıyı yazma" denir + üretilen JSON'daki sayılar,
   aynı sayfanın `icerik/metin` metniyle karşılaştırılır; eşleşmeyen sayı
   `confidence`'ı düşürür ve `important_values`'tan çıkarılır.
3. `interpretation` alanı **asla** kaynak sayı üretemez — yalnızca
   `rows`/`important_values`'ta zaten bulunan değerlere atıf yapabilir.
4. Kitapta açıklama yoksa §9'daki kontrollü cümle: *"Grafikteki düşüş şu
   sayfadaki verilerden görülüyor; kitabımız bu düşüşün nedenini
   açıklamıyor."* — bu, mevcut `YETERSIZ_KAYNAK` deseninin görsel karşılığı.

### E.2 — Pedagojik katman (§14)
Kazanım ilişkisi/soru önerisi **vision çıktısının içinde üretilmemeli**
(orada uydurma riski en yüksek). Doğru yer: `kazanim` tablosu (208 kayıt)
ve `kazanim_test_soru` (1.476 kayıt) zaten dolu — sayfa→kazanım eşleşmesi
bir **retrieval** işi, bir üretim işi değil. Bu, mimari.md §12.1'in
"Hedef → Kanıt → Araç" tasarımının doğal devamı ve ayrı bir onay konusu.

---

# F. MODEL KARŞILAŞTIRMASI

> **Okuma uyarısı:** ilk iki satır **bu makinede, gerçek ders kitabı
> sayfalarıyla ÖLÇÜLDÜ**. Alt blok **kurulmadı, ölçülmedi** — üretici
> beyanına dayanan tahminlerdir ve kurulmadan doğrulanamaz. İkisini aynı
> kefeye koymayın.

## F.1 Bulut — ÖLÇÜLDÜ (2026-09-02, biyoloji-9 / fizik-10 / matematik_9 sayfaları)

| MODEL | VRAM | QUANT | GPU | LATENCY | OCR | TABLO | GRAFİK | MATEMATİK | TÜRKÇE | TOPLAM |
|---|---|---|---|---|---|---|---|---|---|---|
| `mistral/pixtral-12b-2409` | 0 | — | yok | **5,4–7,4 sn** (ölçüldü) | iyi | **iyi** — güvenlik sembolleri tablosunu başlık+satır olarak çıkardı | **iyi** — x-t grafiğinde eksen+birim+değer okudu | **iyi** — küme gösterimini LaTeX ile verdi | akıcı, kaymadı | **Bugün kullanılabilir en iyi seçenek** |
| `mistral/mistral-medium-latest` | 0 | — | yok | **3,0–8,1 sn** (ölçüldü) | iyi | iyi | iyi (yorum katıyor) | iyi | akıcı | Yedek; zaten `belge_ozet`/`sembol_duzelt` zincirlerinde var |
| `groq/llama-4-scout-17b-vision` | 0 | — | yok | — | — | — | — | — | — | **401 — anahtar geçersiz** |
| `nvidia/llama-3.2-90b-vision` | 0 | — | yok | **>120 sn, yanıt yok** | — | — | — | — | — | **Fiilen ölü** |
| `openrouter` ücretsiz VLM'ler | 0 | — | yok | — | — | — | — | — | — | **404 — ücretsiz sürüm kaldırılmış** |

> **Düzeltme (aynı gün, sayfa metniyle karşılaştırılarak):** bu satır
> önce "`mistral-medium` sayfada yazmayan bir yön yorumu ('batı yönünde')
> ekledi" diyordu — **yanlış alarmdı.** `fizik-10.pdf` s.60'ın metni
> okunduğunda o ifade birebir sayfada geçiyor ("(2t-3t) s aralığında batı
> yönünde düzgün hızlanan"). Ölçülen üç bulut modelinde de kaynakta
> olmayan bir bilgi tespit EDİLMEDİ. E.1'deki doğrulama kapısı yine de
> zorunlu — ama gerekçesi gözlenmiş bir halüsinasyon değil, `_sayilar_
> kaynakta_mi` ile vision sayılarının yapısal çelişkisi (bkz. E.1).

## F.2 Yerel — `TAHMİN, KURULMADI, ÖLÇÜLMEDİ`

Bu satırlardaki VRAM/latency değerleri **bu makinede doğrulanmadı**. Karar
verilebilmesi için ayrı, onaylı bir benchmark turu gerekir (bkz. §J/§K).
Belirleyici kısıt ölçüldü ve aşağıdaki her satırı bağlar:

> **GPU 0'da yük altında ölçülen boş VRAM: 7.041 MiB. GPU 1'de: 2.337 MiB.**

| MODEL | VRAM (tahmin) | QUANT | GPU | LATENCY | OCR | TABLO | GRAFİK | MATEMATİK | TÜRKÇE | TOPLAM DEĞERLENDİRME |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3-VL (7B sınıfı) | ~5–7 GB | 4-bit | yalnızca GPU 0 | ölçülmedi | ? | ? | ? | ? | ? | GPU 0'a **sığabilir ama pay bırakmaz**; reranker ile aynı kartta OOM riski gerçek (rag.py'de kayıtlı geçmiş OOM) |
| Qwen3-VL (daha büyük) | >12 GB | 4-bit | **sığmaz** | — | — | — | — | — | — | **Eleniyor** — tek kart 12 GB, iki kart 24 GB gibi davranmaz (§6) |
| olmOCR-2-7B | ~5–7 GB | 4-bit | yalnızca GPU 0 | ölçülmedi | çok iyi (iddia) | orta | zayıf | orta | ? | **Yanlış araç**: bu kitaplıkta taranmış sayfa 11 tane (%0,2). OCR'ye ihtiyaç yok |
| Ollama VLM (qwen2.5-vl / minicpm-v / granite-vision) | 4–8 GB | Ollama quant | **GPU 1'de yer YOK** | ölçülmedi | ? | ? | ? | ? | ? | GPU 1'de 2.337 MiB boş; `OLLAMA_KEEP_ALIVE=-1` qwen2.5:14b'yi kalıcı tutuyor. Yükleme, RAG LLM'ini kartından atar |

**Ara sonuç:** ders anındaki canlı yol için bulut (pixtral) bugün hem
ölçülmüş hem bedava GPU maliyetli. Yerel VLM'in asıl anlamlı olduğu yer
**FAZ 3'ün gece koşan toplu ön-işlemesi** — orada gecikme önemli değil,
gizlilik ve token maliyeti önemli. Karar için önce ölçüm gerekir.

---

# G. GPU YERLEŞİMİ (ölçüldü, 2026-09-02)

```
GPU 0  (farabi-api.service, CUDA_VISIBLE_DEVICES=0, CUDA_DEVICE_ORDER=PCI_BUS_ID)
   BAAI/bge-m3 (embedding) + BAAI/bge-reranker-v2-m3
   boşta:        4.491 MiB / 12.288 MiB
   YÜK ALTINDA:  5.247 MiB  ← 4 gerçek RAG sorgusu boyunca örneklendi
   BOŞ (tepe anında): 7.041 MiB

GPU 1  (ollama.service, CUDA_VISIBLE_DEVICES=1, OLLAMA_CONTEXT_LENGTH=8192)
   qwen2.5:14b  —  9.951 MiB, "Forever" (OLLAMA_KEEP_ALIVE=-1), %100 GPU
   BOŞ: 2.337 MiB
```

> CLAUDE.md "iki kart da tam kapasite committed, boş VRAM yok" diyor.
> **Ölçüm bunu kısmen düzeltiyor:** GPU 1 gerçekten dolu, ama GPU 0'da yük
> altında bile ~7 GB boş. Yine de bu "kullanılabilir" demek değil —
> reranker aynı kartta ve `rag.py` bu kartta yaşanmış bir CUDA OOM'u
> kayıt altına almış durumda.

§6'daki seçeneklerin ölçüme göre değerlendirmesi (**hiçbiri uygulanmadı**):

| Seçenek | Ölçüme göre durum |
|---|---|
| **A)** VLM'i GPU 0'daki mevcut servise gömmek | Aritmetik olarak mümkün (7 GB), ama ders sırasında RAG ile aynı kartta OOM riski. **Önerilmiyor** |
| **B)** CPU/çevrimdışı ön-işleme | 60 GB RAM, 46 GB boş — CPU'da VLM çok yavaş ama gece koşan toplu iş için elenemez |
| **C)** VLM yalnızca PDF hazırlama aşamasında | **En düşük riskli**: ders anında GPU'ya hiç dokunmaz. FAZ 3 tam olarak bu |
| **D)** Gerektiğinde yükle/boşalt | Ders ortasında 5–7 GB model yüklemek = uzun sessizlik. **Önerilmiyor** |
| **E)** Mevcut GPU görevlerini yeniden düzenlemek | Ollama LAN'da paylaşılan servis; taşımak Farabi dışı projeleri etkiler. Ayrı onay konusu |

**Önerilen yerleşim (onaylanırsa):** GPU eşlemesi **DEĞİŞMEZ**. FAZ 0/1/2
GPU'ya hiç dokunmaz. FAZ 3 için ayrı, kısa ömürlü bir gece süreci
GPU 0'ı kullanır (servisle aynı anda değil) — ya da bulut. FAZ 4 canlı
yol bulut kullanır.

---

# H. DERS SIRASINDAKİ LATENCY TAHMİNİ

Referans: mevcut RAG **5,4–8,0 sn** (ölçüldü), `pdf_sayfa` render
**120–180 ms** (ölçüldü).

| Yol | Bileşenler | Toplam |
|---|---|---|
| FAZ 1 — tablo RAG (vision yok) | embed + pgvector + rerank + LLM | **~6 sn** (mevcut RAG ile aynı, ölçüldü) |
| FAZ 3/4 — **cache HIT** (sayfa gece işlenmiş) | pgvector select + rerank + LLM | **~6 sn** |
| FAZ 4 — **cache MISS**, bulut VLM | render 0,12 sn + JPEG 0,05 + ağ + VLM 5,4–7,4 sn + RAG 6 sn | **~12–14 sn** |
| Bugünkü `ekrandaki_soruyu_oku` (kırık) | groq 0,5 + nvidia timeout 30 | **~31 sn, sonuç yok** (ölçüldü) |

**Sonuç:** cache-miss'te canlı vision ~12–14 sn — sınıf için uzun. Bu
yüzden §12'nin cache'i ve §13'ün çevrimdışı ön-işlemesi *isteğe bağlı bir
optimizasyon değil, tasarımın kendisi*. Hedef: canlı VLM çağrısı **istisna**
olsun.

Önbellek anahtarı (§12'nin istediği): `kitap_id + sayfa_no + model_adı +
sayfa_görüntüsü_hash` → JSON. `pdf_sayfa` render önbelleği zaten aynı
mantıkla diskte duruyor, aynı deseni izler.

---

# I. ÇEVRİMDIŞI ÖN-İŞLEME (ölçülen büyüklük)

- Toplam **5.045 sayfa**, vision adayı **3.223 sayfa (%64)**.
- **Yalnızca-metin 1.822 sayfa (%36) hiç VLM görmez** — FAZ 2
  sınıflandırıcısının doğrudan kazancı.
- Render maliyeti ihmal edilebilir: 3.223 × ~0,12 sn ≈ **6,5 dakika** (ölçüldü).
- Bulut VLM ile seri: 3.223 × ~6,5 sn ≈ **5,8 saat**. 4 paralel istekle
  ≈ **1,5 saat** — *ancak Mistral'in eşzamanlılık/rate limitleri ölçülmedi.*
- Yerel VLM ile: **ölçülemez** (model kurulu değil).

**Önerilen sıra (tablo pilotuyla aynı desen):** önce tek kitap.
`biyoloji-9.pdf` → 125 vision adayı sayfa ≈ **~14 dakika bulutta**. Çıktı
elle gözden geçirilir, `confidence` dağılımı ve halüsinasyon oranı ölçülür,
ancak ondan sonra 19 kitaba açılır.

Sayfa bazlı dağılım (vision adayı oranı, ölçüldü) — bütçe planlaması için,
%%'ye göre sıralı:

| Kitap | Sayfa | Vision adayı | Oran |
|---|---:|---:|---:|
| tarih-10 | 319 | 318 | %100 |
| cografya-9 | 245 | 212 | %87 |
| cografya-10 | 241 | 201 | %83 |
| tarih-9 | 264 | 220 | %83 |
| waymark-9 (İngilizce) | 188 | 154 | %82 |
| biyoloji-10 | 199 | 135 | %68 |
| inkilap-12 | 287 | 189 | %66 |
| biyoloji-9 | 191 | 125 | %65 |
| fizik-10 | 353 | 220 | %62 |
| fizik_9 | 273 | 170 | %62 |
| kimya_9 | 287 | 171 | %60 |
| matematik-10 | 417 | 230 | %55 |
| din-kulturu-9 | 191 | 104 | %54 |
| matematik_9_2 | 238 | 129 | %54 |
| felsefe-10 | 217 | 115 | %53 |
| turk-dili-ve-edebiyati-10_2 | 319 | 167 | %52 |
| kimya-10 | 293 | 148 | %51 |
| matematik_9 | 205 | 102 | %50 |
| turk_dili_ve_edebiyati_9 | 318 | 113 | %36 |
| **TOPLAM** | **5.045** | **3.223** | **%64** |

`tarih-10.pdf` (319 sayfanın 318'i) ve `cografya-9.pdf` (%87) en pahalı
kitaplar; `turk_dili_ve_edebiyati_9.pdf` (%36) en ucuzu. FAZ 3 bütçesi
kitap kitap açılabilir.

---

# J. DEĞİŞTİRİLECEK DOSYALAR

**Hiçbiri henüz değiştirilmedi.** Onay verilirse önerilen sıra:

### FAZ 0 — onarım
| Dosya | Değişiklik | Risk |
|---|---|---|
| `server/saglayicilar.py` | `gorsel` zincirine `mistral/pixtral-12b-2409` + `mistral/mistral-medium-latest`; `kitap_ozet`'teki ölü nvidia model adı | **Düşük** — zincir sırası eklemesi, mevcut testler (`server/tests/test_saglayicilar.py`) zincir davranışını zaten kilitliyor |
| `server/saglayicilar.py` | görsel çağrılar için timeout gözden geçirme | Düşük |
| `.gitignore` | `server/config/api_keys*` deseni | **Sıfır** |
| `server/config/api_keys.json` | groq anahtarını yenile *(sizin kararınız — dosyayı okumadım)* | Düşük |

### FAZ 1 — chunk_tablo'yu bağla
| Dosya | Değişiklik | Risk |
|---|---|---|
| `server/rag.py` | `_ilk_k_getir`'e ikinci kaynak (`chunk_tablo`), aynı eşik/rerank | **ORTA — RAG çekirdeği.** Kural 6 kapsamında ayrı onay; `benchmark/katman_test.py` + 40 soruluk set ile önce/sonra ölçüm şart |
| `server/main.py` | `sources[]`'a tablo kaynağı biçimi | Düşük |
| (çalıştırma) `tablo_cikar.py` + `embed_tablo.py` | 18 kitap için koştur | Düşük — yalnızca yeni satır ekler, `chunk_egitim`'e dokunmaz |

### FAZ 2 — sınıflandırıcı
| Dosya | Değişiklik | Risk |
|---|---|---|
| `client/tools/sayfa_tipi.py` *(yeni)* | çevrimdışı sınıflandırıcı, GPU/API yok | Düşük — çalışan hiçbir yola dokunmaz |
| `server/icerik.py` | `yontem`/sayfa tipi ipucunu cevaba ekleme | Düşük |

### FAZ 3/4 — vision katmanı
| Dosya | Değişiklik | Risk |
|---|---|---|
| `benchmark/vision_isle.py` *(yeni)* | offline VLM → JSON → doğrulama | Düşük (offline) |
| `chunk_gorsel` tablosu *(yeni migration)* | `chunk_tablo` şemasının birebir kardeşi | **ORTA** — DB migration, ayrı onay |
| `server/gorsel.py` *(yeni router)* | cache-first sayfa analizi ucu | Orta |
| `client/actions/pdf_sayfa.py` | sayfa analizi varsa metne ekle (mevcut `pdf_sayfa_metni` deseniyle aynı) | Orta — canlı ders yolu |
| `client/actions/kayit.py` | gerekiyorsa yeni araç girdisi | Düşük |
| `server/rag.py` | E.1: sayı kontrolünün kaynak kümesi | **YÜKSEK** — halüsinasyon savunması. Ayrı onay + ölçüm |

**Hiçbir mevcut endpoint imzası değişmiyor**; tüm eklemeler yeni uç ya da
mevcut yanıtın metin alanına ek. Board auth her yeni router'a
`APIRouter(dependencies=[Depends(auth.dogrula_tahta)])` deseniyle aynen bağlanır.

---

# K. GERİ DÖNÜŞ PLANI

Her faz tek başına geri alınabilir; hiçbiri diğerine bağımlı değil.

| Faz | Geri dönüş | Süre |
|---|---|---|
| FAZ 0 | `GOREV_ZINCIRLERI` sözlüğünde satır sil → `git revert` | saniyeler |
| FAZ 1 | `rag.py`'de ikinci kaynağı bir bayrakla kapat (`TABLO_KAYNAGI = False`); DB'de `DELETE FROM chunk_tablo` gerekmez — okunmazsa zararsız | dakika |
| FAZ 2 | Yeni dosya; silmek yeterli, çalışan yola bağlı değil | anında |
| FAZ 3 | `chunk_gorsel` okunmazsa sistem FAZ 1 davranışına döner; tablo DROP edilmeden kalabilir | dakika |
| FAZ 4 | `pdf_sayfa.py`'deki ek çağrı `try/except` içinde ve **sessizce atlanabilir** olmalı — `pdf_sayfa_metni`'nin bugünkü deseniyle birebir aynı | anında |

**Değişmeyecek invaryantlar (her fazda korunur):**
- Vision servisi çökerse ders akışı bozulmaz — her yeni çağrı `try/except`
  içinde, başarısızlıkta mevcut davranışa düşer (Kural 2).
- GPU eşlemesi, systemd birimleri, Ollama yapılandırması **değişmez**.
- Gemini Live ses mimarisi, yoklama, zil/ders programı **değişmez**.
- Mevcut endpoint sözleşmeleri geriye dönük uyumlu kalır.
- Her fazdan sonra: `server/tests` (65) + `client/tests` (144) + RAG
  40 soruluk seti (`benchmark/`) — başarısız test gizlenmez.

---

# ONAY BEKLENEN KARARLAR

1. **FAZ 0 onarımı şimdi yapılsın mı?** Vision zinciri kırık ama henüz
   tetiklenmemiş (§0.1) — bu bir yeni özellik değil, ilk gerçek kullanımdan
   önce kapatılması gereken gizli bir arıza. Tek dosya, düşük risk.
2. **groq anahtarı**: `api_keys_yeni 30.08.2026.txt` içindeki anahtar
   güncel mi? (Dosyayı okumadım — do-not-read listesinde.)
3. **FAZ 1** (`chunk_tablo`'yu RAG'a bağlama) — RAG çekirdeğine dokunuyor,
   Kural 6 gereği ayrı onay.
4. **Yerel VLM benchmark'ı için izin**: hiçbir model kurulmadan
   karşılaştırma yapılamıyor. İstenirse, servisleri hiç değiştirmeden,
   kısa ömürlü tek bir süreçte GPU 0'da ölçüm turu önerilebilir — ama bu
   da ayrı bir onay.
5. **Bulut mu, yerel mi? — 5. MADDE, AYRINTILI**

   Bu madde bir *ilke* tartışması değil, bir *ölçek* tartışması. İkisini
   ayırmak önemli, çünkü karıştırıldığında zaten verilmiş bir kararı
   yeniden açmış oluruz.

   **Bugün ne oluyor (ve bu zaten onaylı):** bir sayfa görüntüsü buluta
   ancak öğretmen istediğinde, tek tek gidiyor. `ekrandaki_soruyu_oku`
   bunu bugün yapıyor, `mimari.md` §13 sizin kararınızı kayda geçirmiş:
   *"elimizde bir sürü API var, multimodal için kullanabiliriz."* FAZ 0
   (bugün onarılan) ve FAZ 4 (ders anındaki tek sayfa) bu davranışın
   aynısı — **yeni bir karar gerektirmiyorlar.**

   **FAZ 3 neden farklı:** orada kimse istemeden, bir gecede
   **3.223 sayfa** — yani kitaplığın neredeyse tamamı — toplu hâlde
   üçüncü bir tarafa yükleniyor. "Öğretmen bir sayfa sordu" ile "19
   kitabın tamamı bir sağlayıcının sunucusundan geçti" arasındaki fark
   nicel değil, nitel.

   **Risk NE DEĞİL:** KVKK/öğrenci mahremiyeti değil. Bunlar MEB'in
   kamuya açık ders kitapları; içlerinde öğrenci verisi, ses, isim yok.
   Farabi zaten öğrenci kimliği tutmuyor.

   **Risk NE:** iki somut soru —
   1. *Saklama/eğitim:* sağlayıcı (Mistral) gönderilen görüntüleri
      saklıyor mu, model eğitiminde kullanıyor mu? Ücretsiz/düşük katman
      sözleşmelerde bu genellikle AÇIK olur, ücretli katmanlarda kapalı.
      Bu, sözleşmeden okunacak bir şey — tahmin edilecek değil.
   2. *Telif duruşu:* okulun elindeki telifli PDF'lerin **tamamını**
      dışarıya toplu göndermek sizin/okulun kabul edebileceği bir şey mi?
      Tek sayfa "kullanım", tüm kitaplık "aktarım" gibi görünür.

   **Karar bu ikisinde:** cevabınız "sorun değil" ise FAZ 3 bulutla
   yapılır, yerel VLM'e hiç gerek kalmaz (ve bugünkü ölçüme göre yerel
   3B zaten yeterince iyi değil — bkz. yukarıdaki benchmark). Cevabınız
   "sorun" ise **yerel VLM'in TEK gerçek gerekçesi budur** — ders
   anındaki hız ya da kalite değil, toplu gönderimden kaçınmak.

   **Üçüncü bir yol da var:** FAZ 3'ü hiç yapmamak. O zaman vision
   yalnızca ders anında, öğretmen sorduğunda, tek sayfa çalışır
   (~12–14 sn, önbellekle ikinci kez ~6 sn) — bugünkü onaylı davranışın
   aynısı, sadece grafik/tablo anlayarak. Kitaplığın tamamı hiçbir yere
   gitmez. Ölçek sorunu ortadan kalkar, karşılığında ders anında bir
   kerelik gecikme kabul edilir.

---

## Ölçümler nasıl tekrarlanır

Bu rapordaki canlı RAG ölçümü (`5,4–8,0 sn`, GPU tepe `5.247 MiB`) gerçek
`POST /api/egitim/question` çağrılarıyla yapıldı; auth zorunlu olduğu için
istek başlığı `server/config/api_keys.json`'daki `board_keys["9-A"]`
değerinden **programatik olarak** okundu — anahtar hiçbir yere basılmadı,
loglanmadı, bu rapora girmedi. Bulut sağlayıcı ölçümleri
`server/saglayicilar.py`'nin kendi `_anahtar()` fonksiyonu üzerinden aynı
şekilde yapıldı. Ölçüm scriptleri scratchpad'de, repoya yazılmadı.
