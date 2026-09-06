# Farabi

Sınıf akıllı tahtalarında çalışan sesli ders asistanı.
Detaylı mimari: `@docs/mimari.md`

> ⚠️ **KESİN MİMARİ KARARI (2026-09-05) — `docs/mimari.md` §0'a bak, her
> şeyden önce.** Client = yalnızca tahtadaki arayüz/etkileşim yüzeyi (ses
> oturumu dahil), server = beyin (RAG + **sistem promptu** + iş mantığı +
> sağlayıcı routing). Bu, aşağıdaki "Temel Kurallar"daki Kural 1'in
> ("client ince kalmalı") doğal uzantısıdır. İki somut göç PLANLANDI, henüz
> YAPILMADI:
> 1. `client/core/prompt.txt` server'a taşınacak, client onu oturum başında
>    HTTP ile çekecek.
> 2. **Dağıtım: GitHub tek doğru kaynak — UYGULANDI (2026-09-05).**
>    Tahtalar GitHub'dan (`github.com/atakanunver/yenifarabi`, PUBLIC)
>    **doğrudan** çeker, server ARADA DEĞİL (kullanıcı netleştirdi: "tahtalar
>    serverdan kodu github üzerinden çeksin rsync iptal"). `server/
>    farabi-kurulum.sh` rsync'ten git'e yeniden yazıldı: tahta `client/`'ı
>    sparse-checkout ile klonlar, `farabiguncelle.sh` artık `git fetch` +
>    `git reset --hard origin/master` (aynı isim, tamamen yeni mekanizma) —
>    repo public olduğu için SSH-anahtar adımları kaldırıldı. `farabi.local`
>    yalnızca KENDİ (`server/`) kodu için ayrıca GitHub'dan çeker, bu board
>    dağıtımından bağımsız bir akış. **Henüz gerçek tahtada test edilmedi**
>    (9-A şu an ağda erişilemez durumda) — bkz. `docs/mimari.md` §0 madde 2.
>
> **Çapraz değişiklik kuralı (yeni):** client+server bağlı değiştiğinde
> (biri diğerini gerektiriyorsa) ikisi BİRLİKTE ele alınır — Claude her iki
> tarafı da inceler ve ilgili test paketlerini (`server/tests/`,
> `client/tests/`) çalıştırır, sonra `farabi.local` deploy eder. **Son kabul
> testi her zaman Atakan tarafından fiziksel tahtada yapılır** — bu adım
> otomatikleştirilmez/atlanmaz.
>
> `client/core/prompt.txt`'in server'a taşınması hâlâ PLANLANDI, henüz
> YAPILMADI — bu dosyanın geri kalanındaki "client'ta prompt.txt var"
> anlatımı hâlâ koddaki gerçek durumdur; dağıtım kısmı ise artık YUKARIDAKİ
> yeni akışı yansıtır, "rsync ile senkron" ifadeleri geçmiş durumu anlatır.

**Donanım (server, hızlı referans):** 2× NVIDIA RTX 3060 12GB 
İkisi de tam kapasite committed: biri `ollama.service`'e, diğeri
`farabi-api.service` (embedding+reranker) — ayrıntı ve gerekçe için aşağıdaki
"Bilinçli sapma (2026-08-09)" notuna bkz. Yeni bir GPU işi (ör. vision model)
planlanırken bu iki kartın ZATEN dolu olduğu unutulmamalı.

## Komutlar

Client kodu `client/` altında — detaylı komutlar, kurallar, bilinen sorunlar
için `@client/CLAUDE.md` (BU CLIENT KLASÖRÜ TAHTALARA SSH ÜZERİNDEN GÖNDERİLECEK GÜNCELLEMELER BÖYLE YAPILACAK)

```bash
cd client
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
python main.py               # client çalıştır
venv/bin/python -m pytest tests/ -q   # test (pytest requirements.txt'te YOK, geliştirici makinesine elle kurulur)
python tools/dogrula.py       # içerik doğrulama kapısı
```

Server kodu `server/` altında — FastAPI Brain, bu makinede (`farabi.local`)
`farabi-api.service` olarak systemd altında çalışıyor
(`WorkingDirectory=/home/ata/farabi/server`,
`ExecStart=.../server/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000`).

```bash
cd server
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
venv/bin/uvicorn main:app --reload --port 8000   # geliştirmede elle çalıştır
venv/bin/python -m pytest tests/ -q              # test (pytest requirements.txt'te var)
venv/bin/python -m pytest tests/test_icerik.py -q          # tek dosya
venv/bin/python -m pytest "tests/test_icerik.py::TestKitapBul" -q  # tek sınıf

sudo systemctl status farabi-api.service          # üretim servisi durumu
sudo systemctl restart farabi-api.service         # kod değişikliğinden sonra üretime almak için
```

Benchmark kodu `benchmark/` altında — Faz 0a/R-4 retrieval ölçüm harness'ları,
pytest'e bağlı DEĞİL (`tests/` dizini yok), her script bağımsız çalıştırılan
bir CLI. `rag_test.py` üretimin gerçek `server/rag.py::RagMotoru`'sunu import
edip ölçer; `recall_test.py`/`katman_test.py` pipeline'ı kendi başına yeniden
uygular (bkz. `rag_test.py`'nin kendi docstring'i — üçünün NEDEN ayrı
tutulduğu orada açıklanıyor, aralarında fark varsa `rag_test.py` esas alınır).

```bash
cd benchmark
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
venv/bin/python rag_test.py          # üretim RAG koduna karşı ölçüm (soru seti argümanla verilir, script docstring'ine bkz.)
venv/bin/python recall_test.py       # Recall@4/rerank/eşik/MRR, üretimden bağımsız model
venv/bin/python katman_test.py       # iki katmanlı halüsinasyon savunması simülasyonu
```

Lint/formatter yapılandırısı — Farabi Python kodunda lint ve formatter aracı olarak Ruff kullanılır.

Ruff ortamı
Ruff, Farabi'nin çalışma/runtime ortamından ayrı olan geliştirme ortamında kuruludur:
.venv-tools/bin/ruff
Ruff çalıştırılırken öncelikle bu yol tercih edilir:
.venv-tools/bin/ruff check client server benchmark tahtayoklama
Ruff --fix veya format komutları çalıştıralabilir
ruff check . --fix
ruff format .
.venv-tools/bin/ruff karşılıkları.
Farabi'nin çalışan bir eğitim/yoklama sistemi olmasıdır. Otomatik kod değişiklikleri mevcut davranışı bozabilir.
Ruff çalışma prosedürü Kod değişikliğinden sonra:
Önce Ruff yalnızca kontrol amacıyla çalıştırılır:
.venv-tools/bin/ruff check client server benchmark tahtayoklama
Bulgular sınıflandırılır:
F8xx / gerçek Python hataları: Öncelikli olarak incelenir.
F401 / F841: Güvenli olup olmadığı kontrol edilerek temizlenebilir.
I001 / formatlama: Davranışı değiştirmediği doğrulandıktan sonra düzenlenebilir.
DTZ / timezone: Farabi'nin İstanbul/Türkiye saat mantığı kontrol edilmeden değiştirilmez.
PLR / SIM / PERF / RUF: Önce davranış etkisi değerlendirilir.
Bir Ruff bulgusu gerçek bir bug ise önce kodun çalışma mantığı incelenir, ardından minimum değişiklik yapılır.
Büyük ölçekli otomatik düzeltme yapılmaz.Özellikle korunacak davranışlar
Ruff temizliği sırasında aşağıdaki davranışlar bozulmamalıdır:
Yoklama sistemi
Ders/zil zamanlaması
İstanbul/Türkiye saat dilimi
Öğrenci ve sınıf verileri
Dashboard
SSH bağlantıları
Akıllı tahta ↔ server iletişimi
RAG sistemi
LLM bağlantıları
Farabi'nin ders akışı
Mevcut API endpointleri
Mevcut dosya ve veritabanı formatları
Ruff sonrası doğrulama
Kod değişikliğinden sonra mümkünse:
.venv-tools/bin/ruff check client server benchmark tahtayoklama
çalıştırılır.
Ardından ilgili testler veya mevcut çalışma kontrolleri gerçekleştirilir.
Ruff'un sıfır hata vermesi, çalışan davranışın korunmasından daha önemli değildir.
Farabi'de öncelik sırası:
Çalışan sistem > davranışın korunması > gerçek bugların düzeltilmesi > lint temizliği > stil/formatlamalma

farabi/sunucu server
├── CLAUDE.md          — bu dosya, günlük kurallar
├── docs/mimari.md     — detaylı mimari (server/veri/RAG tasarımı) dosya yoksa claude code agent en yüksek model fable5 ile oluşturur.(mimari önemli)
├── client/            — ÇALIŞAN kod, tahta istemcisi (aşağıya bkz.) — İNCE:
│                         kendi kitaplar/YKS/içerik deposu YOK (2026-08-14'te
│                         kaldırıldı), tüm ders_icerigi/pdf_sayfa/yks_sorulari/
│                         file_processor/bulut-LLM çağrıları HTTP ile server'a
│                         gidiyor; SES hâlâ tamamen Gemini Live'da, server'dan bağımsız
├── server/            — ÇALIŞAN Brain, artık yalnız RAG değil — FastAPI:
│                         RAG (pgvector+rerank+eşik+LLM), kitap içeriği/PDF
│                         render, YKS soru arama, bulut LLM proxy, dosya
│                         işleme (bkz. aşağıdaki "server/" bölümü ve mimari.md §9/§10)
└── benchmark/         — Faz 0a retrieval/eşik/katman testleri, 13 kitap pgvector'a indekslendi


**`client/` — PyQt6 tabanlı tahta istemcisi.**(vestel akıllı tahtalar üzerinde kurulu)
Detaylar `client/CLAUDE.md`'de (koddan doğrulanmış, güncellenmesi gerekebilir);
özet:

- `main.py` — `FarabiLive`: Gemini Live oturumu, araç çağrı dağıtımı, ders açılışı
- `ui.py` — `FarabiUI`/`MainWindow`: PyQt6 HUD; `main.py` bunu import eder, 
  bu tahtanın artık yerel kitap dizinleri yok, içerik hazırlama tek noktadan (server) yapılıyor. Aynı
  tarihte **kalem/silgi çizim katmanı** eklendi (`_CizilebilirGorsel`,
  `pdf_sayfa`/`yks_sorulari` görüntüsünün üzerine dokunmatik yazma/silme) —
  yalnızca buton ile açılır, sesli komutla DEĞİL (LLM'e tool olarak sunulmadı,
  yanlış tetikleme riski taşımasın diye); çizim geçicidir, kaydedilmez.
- `core/` — motor/altyapı: `ders_motoru.py` (ders akışı), `olaylar.py` (event bus),
  `program.py` (ders programı), `zil.py` (zil senkronizasyonu),
  `saglayicilar.py` (2026-08-14: artık sağlayıcı havuzu DEĞİL — ince bir HTTP
  proxy istemcisi, gerçek Groq/Mistral/DeepSeek/OpenRouter/NVIDIA havuzu
  `server/saglayicilar.py`'ye taşındı; `metin_uret`/`gorsel_uret` imzaları
  BİREBİR korunarak — bkz. `server/` bölümü), `anahtar.py` (yalnızca
  Gemini anahtar havuzu/rotasyon — client'ta kalan TEK bulut anahtarı türü),
  `transcript.py` (yalnızca metin, KVKK notlu), `tahta.py`, `modeller.py`, `logger.py`
- `actions/` — modelin çağırdığı araçlar, tek kaynak `kayit.py` (registry).
  Tümü (kitap_sorusu, ders_icerigi, pdf_sayfa, yks_sorulari, file_processor)
  artık server'a HTTP ile bağlı; sunucu ulaşılamazsa hepsi sessizce kısıtlayıcı
  bir metne düşer, ders hiçbir zaman bozulmaz (mimari.md §2).
  `kitap_sorusu.py` — kaynaklı, somut soru-cevabı `server/`'ın RAG motoruna
  yönlendirir; `ders_icerigi` (konu anlatımı için sayfa getirir, artık
  `server/icerik.py`'de eşleştirilir) ile karıştırılmamalı, ikisi farklı iş yapar.
  `pdf_sayfa.py` (2026-08-14'te server-çağıran hale getirildi) — render artık
  `server/icerik.py`'de (PyMuPDF client'tan kalktı); client yalnızca PNG indirip
  küçük, boyut sınırlı bir yerel önbelleğe (`icerik/onbellek/pdf_sayfa/`, en
  fazla 30 dosya) yazar.
  ekran görüntüsü alma zorunlu bir yetenek — 9-A'da `ekran_goruntusu_al.py`/
  `ekrandaki_soruyu_oku.py` olarak kurulu (2026-08-30, bkz. `client/CLAUDE.md`);
  eski `screen_processor.py` (webcam tabanlı) bu ikisinin YERİNE geçmedi, ayrı
  ve kaldırılmış bir modüldü — karıştırma. Diğer tahtalarda Farabi client hiç
  kurulu değil, bu yetenek de dolayısıyla oralarda yok; kurulum yapıldığında
  buraya da gitmesi gerekiyor.
- `tools/` — çevrimdışı içerik hazırlama script'leri (kitap/YKS PDF → JSON) hâlâ
  burada duruyor (kod olarak sil) ama **artık bu tahtada koşmuyor** —
  işledikleri `kitaplar/`/`YKS/`/`icerik/` dizinleri client'ta yok; aynı
  script'ler server'ın kendi `client/` kopyasında (rsync ile senkron), kanonik
  veri konumuna (`/mnt/farabi-data/farabi/`) symlink'lenmiş halde çalışıyor.
  `dogrula.py` (ücretsiz doğrulama kapısı), `mikrofon_test.py` client'ta anlamlı
  kalmaya devam ediyor.
- `tests/` — pytest, ağ/model çağrısı olsun. `test_saglayicilar.py` 2026-08-14'te
  HTTP-proxy davranışını test edecek şekilde yeniden yazıldı (eski
  sağlayıcı-zinciri testleri `server/tests/test_saglayicilar.py`'ye taşındı).
- `config/` — gerçek JSON'lar gitignore'lu, `.example.json` şablonları committed.
  2026-08-14: `api_keys.json`'server'a taşındı — client'ta yalnızca
  `gemini_api_keys`/`gemini_api_key`, `derslik`, `sunucu_url`, `ders_kipi`,
  `os_system` kaldı.
- `memory/`,derste geçen konuşmalar hatalar loglar tutulsun  
  `planlar/` — koda BAĞLI DEĞİL, ölü/arşiv (sil,yenidenbağlama— `client/CLAUDE.md`'de gerekçesi var)

> kitap/YKS PDF'i ve türetilmiş içerik tamamen server'a taşındı (bkz. aşağıdaki
> "server/" bölümü ve mimari.md §6). Client'ta yalnızca `icerik/onbellek/
> pdf_sayfa/` ve `icerik/onbellek/yks_sayfa/` kalır — o an gösterilen sayfanın
> geçici, boyut sınırlı (≤30 dosya) yerel önbelleği, kalıcı bir veri deposu
> değil.

**`server/`** — FastAPI Brain, artık yalnızca RAG değil, Farabi'nin ağır işinin
TAMAMI burada (Kural 1'in fiilen tamamlanmış hâli):

- `main.py`/`rag.py`/`db.py` — `/health`, `/ready`, `POST /api/egitim/question`,
  `GET /api/egitim/kitaplar`, `POST /api/egitim/ders_kaydi_yedek`. Ollama
  (qwen2.5:14b) + embedding/reranker GPU'lu çalışıyor, her biri kendi kartına
  sabit (bkz. "Bilinçli sapma", aşağıda).
- `icerik.py` (2026-08-14 eklendi) — `POST /api/egitim/ders_icerigi` (kitap
  sayfa metni, eşleştirme mantığı client'tan taşındı), `GET /api/egitim/
  pdf_sayfa` (PyMuPDF render, PNG döner).
- `yks.py` (2026-08-14 eklendi) — `POST /api/egitim/yks_sorusu`,
  `GET /api/egitim/yks_sayfa`. Sıralı-sunum oturumu `derslik` anahtarlı bir
  dict'te (`_OTURUMLAR`) tutulur — client'taki eski modül-seviyesi `_OTURUM`
  tek sürecin TÜM tahtalara hizmet etmesiyle artık güvenli değildi.
- `saglayicilar.py` (2026-08-14 eklendi) — client'ın eski `core/saglayicilar.py`
  sağlayıcı havuzunun BİREBİR taşınmış hâli (GOREV_ZINCIRLERI, soğuma mantığı
  değişmedi). Anahtarlar `server/config/api_keys.json`'da.
  ⚠️ **2026-09-02 — `gorsel` zinciri onarıldı.** Gerçek çağrılarla ölçüldü:
  eski zincirin İKİ basamağı da ölüydü (groq `llama-4-scout` → 404, model
  groq hesabının kataloğunda artık yok; nvidia `llama-3.2-90b-vision` →
  120 sn'de bile yanıt yok) ve `gorsel_uret` `evrensel_yedek=False` ile
  çağrıldığı için üçüncü basamak yoktu. Yani `ekrandaki_soruyu_oku` ve
  `file_processor`'ın görsel işi ~31 sn sonra hata dönüyordu. Loglar bu
  yolun 2026-08-14'ten beri hiç çağrılmadığını gösterdi — arıza gizliydi,
  ilk gerçek sınıf kullanımında patlayacaktı. Yeni zincir:
  `mistral/pixtral-12b-2409` → `mistral/mistral-medium-latest` →
  `nvidia/meta/llama-3.2-11b-vision-instruct`. Uçtan uca doğrulandı
  (`POST /api/egitim/dosya_isle`, gerçek kitap sayfası: 200 OK, 10,1 sn).
  Aynı turda `kitap_ozet` ve `soru_taslak` zincirlerindeki ölü
  `nvidia/meta/llama-3.3-70b-instruct` (410 Gone) da değiştirildi.
  **nvidia bu ağdan genel olarak güvenilmez** — metin modelleri 410/timeout
  veriyor, yalnızca 11b-vision çalışıyor (10,4 sn, ama Türkçe istemde
  İngilizce cevap eğilimli, o yüzden son çare).
  Durum tespiti ve ölçümlerin tamamı: kökteki `plan.md`.
- `proxy.py` (2026-08-14 eklendi) — `POST /api/egitim/metin_uret`,
  `POST /api/egitim/gorsel_uret`: `saglayicilar.py`'nin HTTP yüzü.
- `dosya.py` (2026-08-14 eklendi) — `POST /api/egitim/dosya_isle` (multipart
  upload; PDF/docx/xlsx/pptx/görsel işleme + AI özet/analiz),
  `GET /api/egitim/dosya_indir/{id}/{ad}` (üretilen dönüşüm dosyaları, 24 saat
  sonra silinir). **2026-08-25:** metin özetleme (`belge_ozet` görevi,
  `_ai_metin`) artık ÖNCE yerel Ollama'yı (`qwen2.5:14b`) dener, bulut
  (deepseek→mistral) yalnızca Ollama yanıt vermezse devreye girer — kullanıcı
  kararı: "PDF analizinde bulut token'ı harcanmasın". Görsel özetleme
  (`gorsel_uret`, `_ai_gorsel`) hâlâ yalnızca bulut — bu makinede yerel bir
  vision modeli yok; yerel vision modeli eklemek Kural 8 kapsamında ayrı bir
  onay gerektirir. **2026-09-02: zincirin KENDİSİ değişti** (eski
  groq→nvidia zinciri tamamen ölüydü, bkz. yukarıdaki `saglayicilar.py`
  notu) — artık mistral/pixtral birincil. Ayrıca aynı tarihte ölçüldü:
  GPU 0'da yük altında **7.041 MiB boş** var (CLAUDE.md'nin başındaki
  "iki kart da tam kapasite committed" notu GPU 1 için doğru, GPU 0 için
  değil) — yerel VLM tartışması bu ölçümle yapılmalı, varsayımla değil.
  Ayrıntı: `raganaliz.txt` (2026-08-25) ve kökteki `plan.md` (2026-09-02).
- `config/api_keys.json` (gitignore'lu) — bulut anahtarları (Gemini YOK, o
  client'ta kalıyor — ses oturumu mimari kısıtı, bkz. §14) + `board_keys`.
  ⚠️ **2026-09-02:** `.gitignore` kuralları TAM YOL idi
  (`server/config/api_keys.json`), yanında duran `apikeys.env` ve
  `api_keys_yeni 30.08.2026.txt` ignore kapsamı DIŞINDAYDI — bir
  `git add -A` anahtarları commit ederdi (Kural 9 ihlali, denetimde
  bulundu). Kurallar desen tabanlı yapıldı: `*.env`, `**/api_keys*`,
  `!**/api_keys.example.json`. Yeni anahtar dosyası bırakılırken bu
  desenlere uyduğu `git check-ignore` ile doğrulanmalı.

> ⚠️ **Kritik düzeltme (2026-08-14):** `farabi-api.service` önceden yalnızca
> `127.0.0.1:8000`'e bağlıydı — bu satırın eski hâli "client artık BAĞLI"
> diyordu ama bu YANLIŞTI, hiçbir gerçek tahta server'a ulaşamıyordu (bağlantı
> reddediliyordu). `--host 0.0.0.0` yapıldı, artık LAN'dan erişilebilir ve
> uçtan uca doğrulandı. VLAN/güvenlik duvarı henüz kurulmadığı için bu, Ollama
> ile aynı risk modelini paylaşıyor (okul güvenlik duvarı dış sınır koruması,
> bkz. §5 ve mimari.md §11). Aynı oturumda okul ağının SSL-inceleme sertifikası
> (MEB-CERT-TTVPN) server'da tanınmadığı için hem HuggingFace Hub kontrolleri
> (`HF_HUB_OFFLINE=1` ile atlandı, ~5dk→~12sn) hem de bulut LLM proxy çağrıları
> başarısız oluyordu — sertifika server'ın sistem güven deposuna VE her venv'in
> certifi paketine eklendi, artık gerçek Groq/Mistral/DeepSeek çağrıları çalışıyor.

> ⚠️ **9-A'da gerçek sınıf hatası (2026-08-30) — tahtadaki sayfa ile Farabi'nin
> okuduğu farklıydı.** İki AYRI kusur bulundu, ikisi de kanıtlı:
>
> 1. **Düzeltildi:** `icerik.py::_kitap_bul` (pdf_sayfa'nın kitap seçimi),
>    `_bolum_bul` (ders_icerigi'nin konu bazlı seçimi) ile SENKRON değildi.
>    9. sınıf matematik için İKİ kitap var (`matematik_9.pdf` cilt 1, temalar
>    1-3; `matematik_9_2.pdf` cilt 2, temalar 4-7) — `ders_icerigi` konuya
>    göre doğru cildi buluyordu ama `pdf_sayfa` her zaman listedeki İLK kitabı
>    (cilt 1) döndürüyordu, aynı sayfa numarası iki kitapta bambaşka içerik.
>    Fix: `ders_icerigi` artık hangi kitabı seçtiğini `_SON_KITAP` (derslik
>    anahtarlı, process-ömürlü dict) içine yazıyor, `pdf_sayfa` aynı derslik+
>    ders için varsa onu tercih ediyor. `derslik` kimliği auth'tan DEĞİL,
>    doğrudan client isteğinden geliyor (`yks.py`'nin `istek.derslik`
>    deseniyle aynı) — bkz. madde 2, auth henüz client'a bağlı değil. Client
>    tarafı: `actions/ders_icerigi.py`/`actions/pdf_sayfa.py` artık
>    `tahta.derslik()`'i isteğe ekliyor. Test: `server/tests/test_icerik.py::
>    TestKitapBul`. Uçtan uca canlıda doğrulandı (aynı derslik ile cilt 2,
>    derslik olmadan cilt 1 döndüğü curl ile karşılaştırıldı).
> 2. **DÜZELTİLDİ (2026-08-30, aynı gün, `6ab9328` commit'i içinde — bu not
>    "flagged, onay bekliyor" derken bayat kalmıştı, 2026-08-31'de koddan
>    doğrulanıp güncellendi).** Kök neden: öğretmen doğrudan sayfa numarası
>    söylediğinde ("Bizim 45. sayfa") Farabi `pdf_sayfa`yı ÇIPLAK çağırıyordu
>    (önce/sonra hiçbir `ders_icerigi` çağrısı yok) → `pdf_sayfa` yalnızca PNG
>    döndürüyordu, sayfa METNİ döndürmüyordu → Farabi ekranda ne olduğunu
>    bilmeden içerik uyduruyordu. Fix: `server/icerik.py`'a
>    `GET /api/egitim/pdf_sayfa_metni` eklendi (`SayfaMetniYanit`, `metin`
>    alanı); `client/actions/pdf_sayfa.py` artık sayfayı gösterdikten sonra bu
>    endpoint'i çağırıp modele "buna dayandır" diyerek gerçek sayfa metnini
>    veriyor. 9-A'da SSH ile doğrulandı (2026-08-31): repodaki kod ile 9-A'daki
>    kod checksum'ları birebir aynı, bu fix üründe canlı.

> ⚠️ **FAZ 1 (server auth) — rapor ile gerçek durum uyuşmuyor (2026-08-30
> doğrulandı).** `docs/FAZ1_IMPLEMENT_RAPORU.md` (commit edilmemiş,
> `server/auth.py`/`server/tests/test_auth.py` ile birlikte hâlâ `??`)
> "Client (10) dosya değiştirildi, `client` testleri 129/129 geçti" diyor —
> bu YANLIŞ. `git status client/` tertemiz (hiçbir client dosyası
> değişmemiş) ve gerçek `client/tests/test_board_auth.py` çalıştırıldığında
> 3/5 test `AttributeError: module 'core.tahta' has no attribute
> 'tahta_anahtari'` ile düşüyor — o fonksiyon hiç yazılmamış, hiçbir
> `actions/*.py` `X-Farabi-Board-Key` header'ı göndermiyor. Server tarafı
> (`auth.dogrula_tahta`, her router'a bağlı) gerçek ve çalışıyor, ama
> `server/config/api_keys.json`'da `board_keys` alanı da BOŞ. Rapor bunu
> düzeltmeden/silmeden burada not düşülüyor — rapor kendi hâlinde kalsın,
> gerçek durum buradan okunsun.
>
> **Operasyonel sonuç (2026-08-30'da böyleydi):** servis restart edilirse
> (auth kod olarak zaten her router'a bağlı) client hiç header göndermediği
> için TÜM tahtaların HER `/api/egitim/*` çağrısı 401 alırdı — bu bir
> icerik.py fix'ini devreye almak için restart gerekirken keşfedildi, restart'tan
> HEMEN ÖNCE. Geçici çözüm olarak `/etc/systemd/system/farabi-api.service.d/
> override.conf` içine `Environment="FARABI_AUTH_REQUIRED=0"` eklenmişti
> (auth.py'nin kendi tasarladığı acil rollback anahtarı).
>
> ⚠️ **ÇÖZÜLDÜ (2026-08-30, aynı gün ilerleyen saatlerde) — override
> kaldırıldı, auth artık üretimde ZORUNLU.** `core.tahta.auth_headers()`/
> `tahta_anahtari()` yazıldı ve `core/saglayicilar.py` + 6 `actions/*.py`
> dosyasındaki (`kitap_sorusu`, `pdf_sayfa`, `ders_icerigi`, `ders_hafizasi`,
> `yks_sorulari`, `file_processor`) + `main.py`'nin `ders_kaydi_yedek`
> çağrısındaki TÜM sunucu isteklerine eklendi (`client/tests/
> test_board_auth.py` 5/5). Yalnızca **9-A** için gerçek bir `board_keys`
> anahtarı üretilip hem `server/config/api_keys.json`'a hem 9-A'nın kendi
> `client/config/api_keys.json`'ına yazıldı, kod 9-A'ya senkronlandı
> (`farabiguncelle.sh` elle tetiklendi). `override.conf` silindi,
> `farabi-api.service` yeniden başlatıldı ve uçtan uca doğrulandı: header
> yoksa/yanlışsa 401, 9-A'nın gerçek anahtarıyla 200 — hem localhost'tan hem
> 9-A'nın kendisinden (LAN üzerinden, `sunucu_url()` ile) gerçek istekle
> test edildi.
>
> **Diğer 6 aktif "tahta" (9-B, 10-A, 11-A, 11-B, 12-A, 12-B) bu restart'tan
> ETKİLENMEDİ ve etkilenemezdi** — bu deploy sırasında keşfedildi: bu
> tahtalarda Farabi client hiç KURULU DEĞİL (yalnızca ayrı bir proje olan
> `tahtayoklama/` kurulu; kök `CLAUDE.md`'deki "Yoklama kurulu mu" tablosu
> yoklama projesinin kurulumunu gösteriyordu, Farabi client'ının değil —
> yalnızca 9-A'da ikisi birlikte, aynı venv'i paylaşarak kurulu). Bu 6 tahta
> için `board_keys`'e önceden birer anahtar yazıldı (placeholder, zararsız,
> şu an hiçbir client bunları hiç göndermiyor) — ileride `farabi-kurulum.sh`
> ile bu tahtalara gerçek Farabi client kurulduğunda hazır beklesinler diye.
> O kurulum yapılmadan bu tahtaların auth'la bir ilgisi yok.

## Temel Kurallar

1. Client ince kalmalı. Ağır iş (RAG, LLM, kitap/plan işleme) sunucuda.
2. **Farabi asla dersi bozmaz.** Herhangi bir servis çökerse tahta normal çalışmaya
   devam eder; tam ekran hata basılmaz. (`mimari.md` §2 — tasarım kısıtı)
3. Tek seferde tek modül değiştir.
4. Değiştirmeden önce ilgili dosyayı oku. Varsayma, koddan kanıt bul.
5. Mevcut davranışı bozma; geriye dönük uyumluluğu koru.
6. Büyük refactor için önce plan sun, onay bekle.
7. Testleri atlama, başarısız testi gizleme.
8. **Mimari dokümanda geçmeyen yeni teknoloji/servis/kütüphane eklemeden önce onay
   iste.** Özellikle: Docker, Redis, Qdrant, Elasticsearch, Celery, Kafka,
   Kubernetes, Prometheus/Grafana, bulut API'si, yeni LLM.
9. `.env` asla commit edilmez. API anahtarı koda yazılmaz.
10. Ölçmeden optimizasyon yapma.

## Şu An Yapılmayacaklar

- ⛔ **`/api/idari/*` — KALICI OLARAK İPTAL EDİLDİ (2026-08-31), "Faz 4" artık
  bir sonraki aşama değil, hiç yapılmayacak bir iş.** Endpoint yazılmayacak,
  idari tablo/chunk tasarımı gündemde değil. Şu an yalnızca ders içeriği
  (Faz 1) çalışıyor: sunucu `farabi.local`, client 9-A'da; testler bitmedi.
- ⛔ **Yerel STT/TTS (faster-whisper, Piper) — KALICI OLARAK İPTAL EDİLDİ
  (2026-08-11), Faz 0a'da "henüz gerekmez" değil.** Ses kalıcı olarak Gemini
  Live'da kalıyor —
> - **GPU yapılandırması** artık karara bağlandı: makinede 2x NVIDIA RTX 3060
>   var, `nvidia-driver-595-open` kuruldu (`nvidia-smi` ile doğrulandı, iki kart
>   da görünüyor). "Kaç kart aktif" sorusu **2026-08-12'de kapatıldı**: her
>   servis kendi kartına `CUDA_VISIBLE_DEVICES` ile sabitlendi —
>   `ollama.service` bir kartı (context 32768→8192'ye düşürüldü, tek 12GB
>   karta sığması için), `farabi-api.service` diğer kartı (embedding+reranker
>   birlikte) tek başına kullanıyor. `CUDA_DEVICE_ORDER=PCI_BUS_ID` her ikisine
>   de eklendi — bu olmadan CUDA'nın kendi kart numaralandırması
>   `nvidia-smi`'ninkiyle TERS çıkabiliyor (canlıda böyle bir çakışma
>   yaşandı: iki servis aynı fiziksel karta düştü, modelin bir kısmı CPU'ya
>   taştı — `CUDA_DEVICE_ORDER` eklenince düzeldi). Doğrulama: `ollama ps` →
>   `100% GPU`, `nvidia-smi` → iki kart ayrı, `POST /api/egitim/question` uçtan
>   uca test edildi.
> - **Ollama** kullanıcının açık isteğiyle kuruldu — amaç Faz 1'deki Brain'i
>   önceden kurmak DEĞİL, `benchmark/soru_taslak.py` gibi çevrimdışı içerik
>   araçlarının bulut sağlayıcı kotalarına (deepseek/mistral/nvidia kesintileri,
>   bkz. `core/saglayicilar.py`) bağımlılığını azaltmak. **2026-08-12'de
>   kapsamı genişledi:** artık yalnızca Farabi'ye özel değil — `OLLAMA_HOST`
>   ile okul LAN'ına açıldı (`0.0.0.0:11434`, okulun kendi güvenlik duvarı
>   dış sınırı koruyor), başka projelerin de kullanabileceği kalıcı, paylaşılan
>   bir yerel LLM servisi olarak düşünülüyor.
>
> **Üçüncü sapma (2026-08-14):** "Server iskeleti"nden çok daha ileri gidildi
> — kullanıcının açık isteğiyle ("çoğu şeyi server tarafına alalım, client'ta
> minimum dosya bulunsun") RAG dışındaki TÜM ağır iş (kitap/YKS PDF depolama,
> sayfa render, bulut LLM çağrıları, dosya işleme) da server'a taşındı; bkz.
> yukarıdaki "server/" ve "client/" bölümleri, mimari.md §6/§9/§10/§15. Bu,
> Faz 1→4 yol haritasının bir adımı değil, ona PARALEL yapılan bir
> konsolidasyon — roadmap'in kendisi değişmedi, yalnızca "client ince kalmalı"
> kuralı (Kural 1) artık neredeyse tam uygulanıyor. Aynı oturumda kritik bir
> üretim hatası da düzeltildi: server API'si LAN'a hiç açık değildi (bkz.
> "server/" bölümündeki düzeltme notu).

## Kurulum Biçimi

systemd servisleri. Docker kullanılmaz — okulda sistemi devralacak kişi
`systemctl status` ile durumu görebilmeli.

## Ağ Envanteri (tahtalar + sunucu, yapısal özet)

FARABI SUNUCU (Ubuntu 26.04 LTS, AMD Ryzen 9 3900X,AKILLI TAHTALAR BU SUNUCUYA BAĞLANIP DERS BILGILERI GIRIS CIKIS VE YOKLAMA BILGILERINI SENKRON YONETIYORLAR)
ata@farabi.local
OS: Ubuntu 26.04 resolute
Kernel: x86_64 Linux 7.0.0-29-generic
Shell: bash 5.3.9
Disk: 57G / 2.3T (3%)
CPU: AMD Ryzen 9 3900X 12-Core @ 24x 4.67382GHz
GPU: NVIDIA GeForce RTX 3060, NVIDIA GeForce RTX 3060
RAM: 13870MiB / 61899MiB

SSH BILGILERI
Host          : farabi.local  (192.168.23.252)
Kullanıcı adı : ata
Şifre         : 1
Sudo          : şifresiz (NOPASSWD) (veya aynı şifre)


Üç ayrı makine sınıfı var:

1. **Vestel akıllı tahtalar** (Pardus ETAP GNU/Linux, hostname hepsinde
   `etap`, ağ `192.168.23.0/24`, VLAN/güvenlik duvarı yok) — Farabi
   client'ının (`client/`) VE `tahtayoklama/`'nın (Farabi'den bağımsız,
   ayrı proje) koştuğu fiziksel donanım. 11 tahta (2026-08-24 itibarıyla):

   | Sınıf/Ad  | IP             | Yoklama kurulu mu |
   |-----------|----------------|--------------------|
   | 9-A       | 192.168.23.245 | evet (Farabi client venv'ini paylaşır) |
   | 9-B       | 192.168.23.242 | evet |
   | 10-A      | 192.168.23.233 | evet |
   | 11-A      | 192.168.23.228 | evet (2026-08-24'te kuruldu — önceki 11-A/236 ataması yanlıştı, düzeltildi) |
   | 11-B      | 192.168.23.239 | evet |
   | 12-A      | 192.168.23.231 | evet |
   | 12-B      | 192.168.23.240 | evet |
VESTEL AKILLI TAHTALAR (Pardus ETAP GNU/Linux 23) - 11 adet 7 si aktif sınıf olarak kullanılıyor (Intel i3-2330M,eski mobil işlemci)
--------------------------------------------------------------
Kullanıcı adı : etapadmin
Şifre         : etap+pardus!
Root'a geçiş  : sudo -S (aynı şifre)

Akıllı Tahta Öğretmen Kullanıcısı Şifreleri
Kullanıcı adı :ogretmen
Sifre         :ogretmen

IP              MAC Adresi           Ağ Arayüzü
192.168.23.231  00:09:df:83:ff:cc    enp3s0
192.168.23.233  00:09:df:8b:0c:c4    enp3s0
192.168.23.234  00:09:df:83:cd:c8    enp3s0
192.168.23.235  00:09:df:83:5c:45    enp3s0
192.168.23.236  00:09:df:83:f3:8b    enp3s0
192.168.23.239  00:09:df:83:5c:a9    enp3s0
192.168.23.240  00:09:df:8c:1a:e8    enp3s0f0
192.168.23.242  00:09:df:84:14:1e    enp3s0
192.168.23.244  00:09:df:8c:32:8a    enp3s0f0
192.168.23.245  00:09:df:83:55:d1    enp3s0
192.168.23.228  00:09:df:83:50:6e    11-A SINIFI OLARAK KURULdu

   Bağlanma: `server/tahta-ssh.sh <derslik>` (kullanıcı) ya da
   `--admin <derslik>` (etapadmin, sudo). MAC adresleri ve tam kimlik
   bilgileri `network.txt`'te.

2. **Kapıdaki yüz tanıma sistemi** (giriş yoklaması kiosk PC'si,
   `192.168.23.254`, Debian 12, düşük donanım) — bu repodaki hiçbir
   projeye henüz BAĞLI DEĞİL, yalnızca envanter/referans amaçlı not
   (2026-08-24 eklendi).

3. **Farabi sunucu** (bu makine, `farabi.local` / `192.168.23.252`,
   Ubuntu 26.04, 2× RTX 3060) — `server/`, `tahtayoklama/dashboard/`
   burada koşuyor, yukarıdaki tahtalara buradan SSH ile bağlanılıyor.

## RAG Kuralları (kritik)

- Cevap **sadece** retrieval sonucundan üretilir. Serbest üretim yok.
- Ana savunma: skor eşiğin altındaysa LLM'e hiç gitme → "Bu konu ders kitabında
  bulunmuyor."
- Arama **yalnızca kitap filtresiyle** çalışır (`kitap_id` WHERE koşulu) —
  ama **2026-09-02'den beri İKİ kaynaktan**: `chunk_egitim` top-20
  (`rag.py::_ilk_k_getir`) + `chunk_tablo` top-10 (`rag.py::_tablo_getir`),
  ikisi de aynı `kitap_id` filtresiyle, ayrı sorgularla. Rerank birleşim
  üzerinde çalışır, top-4 oradan seçilir; `ESIK_RERANK` (0,5) değişmedi.
  Ölçüldü (40 soruluk set, 2 kez): 35/40 → **38/40**, Grup A/C bozulmadı,
  medyan gecikme 5,2 → 5,7 sn. Ayrıntı `docs/mimari.md` §5. Geri dönüş tek
  satır: `rag.py::TABLO_KAYNAGI = False`. **`chunk_tablo` şu an yalnızca
  `biyoloji-9` için dolu** — yeni kitap eklendiğinde ölçüm tekrarlanmalı.

  ⚠️ **Daha eski düzeltme (2026-08-30, doc↔kod denetiminde bulundu), hâlâ
  geçerli:** bu satır o tarihten önceki sürümlerde "iki aşamalı: (1)
  kazanım + kitap filtresi, (2) sonuç yoksa yalnızca kitap" diyordu — bu hiç
  doğru olmamıştı, `chunk_egitim`'in `kazanim_kod` kolonu DB'de var ama kod
  tarafında hiçbir sorguda okunmuyor/filtrelenmiyor. Kazanım bazlı filtre
  fikri gerçek bir gelecek-fazı önerisi (`docs/mimari.md` §12, "RAG çıktı-
  doğrulama genişletmesi + kazanım filtresi") ama BUGÜN uygulanmış bir
  davranış değil — kod değiştirilmedi, yalnızca bu satır gerçeğe uyduruldu.
- Her cevapta kaynak: `9. Sınıf Biyoloji, s. 84`
- Chunk sayfa sınırını aşmaz.
- LLM sıcaklığı ≤ 0.2, cevap ≤ 3 cümle.
- Ek kontrol: cevapta kaynakta geçmeyen **sayı** varsa gösterme.
  Kelime örtüşme oranı kullanma (doğru parafrazı engeller).

## API Prensibi

**Brain karar verir, Client görüntüler.** Server ham LLM metni döndürmez;
`{status, answer, sources[], latency_ms, request_id}` yapısı döner (`audio_url`
2026-08-11'de kaldırıldı — ses Brain'de üretilmiyor, bkz. mimari.md §9/§14).
Client metni ayrıştırmaz, `status`'a göre davranır.

Client↔Server event listesi bağlayıcıdır — `mimari.md`  dokümanı güncelle.

## Veri Yerleşimi

  Brain sunucusuna zaten bağlı ikinci disk (`/mnt/farabi-data/farabi/`, 1.8TB)
  kullanılıyor (2026-08-14): `kitaplar/`, `yks/`, `icerik/{metin,ozet,
  yks_metin,eslemeler,onbellek,kitaplar.json}`. Gerçek NAS gelirse bu yol
  taşınır, kod bu ayrımdan habersiz (yalnızca `DATA_DIR` sabiti değişir).
- **PostgreSQL** → metadata, hash, sınıf, ders, kazanım, sayfa
- **pgvector** → chunk + embedding

Dosya içeriği DB'ye gömülmez.

## Veri İzolasyonu (kritik)

- `chunk_egitim` — tek chunk tablosu, kurulu olan bu ve olacak olan da bu.
  `chunk_idari` hiç oluşturulmadı ve oluşturulmayacak (`/api/idari/*` kalıcı
  iptal, "Şu An Yapılmayacaklar"a bkz.) — DB'de, kodda veya promptlarda idari
  içerikle ilgili hiçbir referans yok, karışacak bir şey yok.
- Tahta token'ı yalnızca `/api/egitim/*` çağırabilir.

## Gizlilik

> ⚠️ **Karar (2026-08-11): Öğrenci sesi kalıcı olarak Gemini Live'a (Google
> bulutu) gidiyor.** Bu, önceki sürümlerde "geçici, kabul edilmiş bir açık"
> olarak yazıyordu ve yerel STT/TTS hedef gösteriliyordu — o plan **iptal
> edildi**. Gerekçe: Gemini Live'ın gerçek-zamanlı ses akıcılığını (konuşma
> sırası, araya girme, doğal tonlama) yerel bir hatla eşleştirmek ayrı, büyük
> bir mühendislik işi; başka bir projede denenebilir, bu projenin kapsamında
> değil. Detay: `docs/mimari.md` §14.

- Fiziksel kamera/webcam donanımı yok, bu değişmedi (9-A'da `/dev/video*` yok,
  2026-08-30 doğrulandı) — ama bu, tahtanın KENDİ ekranının görüntüsünü alma
  yeteneğini kapsamaz. **2026-08-30 kararıyla ekran görüntüsü zorunlu bir
  yetenek**: `ekran_goruntusu_al`/`ekrandaki_soruyu_oku` yalnızca
  `QApplication.primaryScreen().grabWindow(0)` çağırır — tahtanın o an
  gösterdiği şeyi (pdf_sayfa/show_content) yakalar, kamera karesi/fiziksel
  sınıf/öğrenciler asla değil. Ayrıntı: `client/CLAUDE.md`, "Project layout"
  altında `RESOLVED 2026-08-30` notu.
- Ham ses diske yazılmaz — Gemini Live'ın kendi transkripsiyonu client'ta
  kalır, Brain'e yalnızca metin gider.
- Öğrenci kimliği tutulmaz. Anonim "öğrenci sordu".
- **Eğitim İÇERİĞİ (kitap metni, RAG cevabı) dış bulut AI servisine
  gönderilmez** — bu hedef karşılanıyor, Brain (Ollama, embedding, reranker,
  PostgreSQL/pgvector) tamamen yerel. **SES bu kuralın dışında, kalıcı olarak
  Gemini Live'a gidiyor** — yukarıdaki karar notuna bkz.

> **Kapandı (2026-08-14):** Yukarıda "hâlâ açık" denen konu artık farklı bir
> biçimde kapandı — client'ın metin/görsel görevleri (eskiden `core/
> saglayicilar.py`) hâlâ bulut sağlayıcılara (Groq/Mistral/DeepSeek/
> OpenRouter/NVIDIA NIM) gidiyor, bu DEĞİŞMEDİ; ama artık bu çağrılar
> client'tan değil server'dan yapılıyor (`server/saglayicilar.py` +
> `proxy.py`), anahtarlar client diskinde durmuyor. Yerel qwen'e taşıma hâlâ
> karara bağlanmadı (zincirlerde yalnızca son çare olarak duruyor) ama bu artık
> ayrı bir soru — bulut bağımlılığının KENDİSİ değil, anahtarların NEREDE
> durduğu sorunu çözüldü.
>
> **Kısmen genişledi (2026-08-25):** `belge_ozet` görevi (dosya/PDF metin
> özeti, `dosya.py`) için "yerel qwen'e taşıma" kararı verildi — artık bu
> görevde Ollama birincil, bulut yalnızca yedek. Diğer görevler
> (`gorsel`, `arama_sentez`, `video_ozet`, `sembol_duzelt`, `soru_taslak`,
> `kitap_ozet`) DEĞİŞMEDİ, hâlâ bulut öncelikli/yalnızca bulut. Ollama'ya
> giderken sistem mesajı olmadan dil karışması (Türkçe→Çince kayma)
> gözlendi ve düzeltildi — bkz. `server/saglayicilar.py` içindeki
> `_OLLAMA_VARSAYILAN_SISTEM`, ayrıntı `raganaliz.txt`'te.

## Loglama — iki tablo, karıştırma

- `metrik` → yalnızca süre + durum + skor. İçerik yok. Sınırsız saklanır.
- `soru_log` → soru/cevap metni **yalnızca** şu durumlarda: düşük skorlu `ok`,
  `yetersiz_kaynak`, `sayi_kontrolu_reddi`, `iptal`, `hata`.
  Başarılı+yüksek skorlu cevaplarda metin saklanmaz.
  derste konuşulan şeyler metin olarak tutulur loglamaya dahil edilir.

> ⚠️ **Karar (2026-08-18): "90 gün sonra silinir" kaldırıldı, bilinçli
> olarak.** Bu satır önceki sürümlerde burada duruyordu ama hiçbir zaman
> uygulanmamıştı (crontab'da, systemd timer'da ya da kodda buna karşılık
> gelen bir DELETE hiç yoktu — bir kod incelemesinde bulundu). Kullanıcı bu
> boşluğu bir hata olarak DEĞİL, olması gereken durum olarak onayladı:
> `soru_log` artık süre sınırı olmadan tutulur. Zaten kimlik tutulmuyor
> ("Anonim öğrenci sordu", bkz. Gizlilik bölümü) — süresiz saklamanın KVKK
> açısından ek bir kişisel-veri riski taşımadığı değerlendirmesiyle alınmış
> bir karar. İleride tekrar bir silme politikası istenirse bu not
> güncellenmeli, kod tarafında hâlâ hiçbir otomatik silme mekanizması yok.

### Log dosyalarını okuma ilkesi (karar: 2026-08-31)

**Log dosyaları önemli — hata/bug avında birincil kanıt, varsayımla debug
etme.**

- Ders transkriptleri (`client/logs/ders/*.txt` — tahtanın kendi diskinde,
  repoya committed değil, SSH gerekir: `server/tahta-ssh.sh <derslik> "cat
  ~/farabi/client/logs/ders/<dosya>.txt"`) derste gerçekten ne konuşulduğunu,
  hangi tool'un ne zaman çağrıldığını, modelin nerede yanlış yaptığını
  gösterir — bkz. yukarıdaki "9-A'da gerçek sınıf hatası" notu, tam olarak bu
  şekilde bulundu. Server'a yedeklenen kopyaları
  `server/yedekler/ders_kaydi/<derslik>/*.txt`'te (bu makinenin kendi diski,
  doğrudan okunabilir).
- `client/logs/farabi.log` (tanı/rotating log, tahtanın diskinde) ikincil
  kanıt — bağlantı/reconnect/hata izleri.
- **Server'da dosya bazlı log YOK** — `server/main.py` hiçbir yere
  `FileHandler` yazmıyor, çıktı yalnızca systemd journal'a gidiyor:
  `journalctl -u farabi-api.service`.
- **Bir log dosyası büyükse (kabaca >1000 satır ya da >200KB), önce
  boyutunu bildir; dosyanın TAMAMINI okumadan önce mutlaka sor.** Hedefli
  arama (`grep`, `tail`, belirli tarih/derslik aralığı) sormadan yapılabilir
  — onay yalnızca "dosyanın tamamını context'e çek" istendiğinde gerekir.

## Okuma

Şunları okuma: `*.pdf`, `data/`, `models/`, `*.onnx`, `venv/`, `__pycache__/`,
`client/config/api_keys.json*`, `server/config/api_keys.json*`,
`/mnt/farabi-data/farabi/` (kitap/YKS PDF'leri ve türetilmiş içerik — telifli/
büyük, 2026-08-14'te client'tan buraya taşındı; client'ta artık `kitaplar/`,
`YKS/`, `icerik/metin`/`ozet`/`yks_metin`/`eslemeler`/`kitaplar.json` YOK).
pdf içerikleri sayfa sayfa parcalayıp ekranda gösterebilirsin ders anında 
gemini live bunları okuyabilir.hatta gemini live tablo yorumlara görsel
vision görü yeteneği kazandırabilirsin.
