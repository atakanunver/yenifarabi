# FARABI VISUAL PULSE — DISCOVERY REPORT

> **2026-11-01 güncellemesi:** Sonraki salt-okunur canlı kontrol, Ollama'da yalnız `qwen3.8:27b` yüklü olduğunu ve `farabi:latest` ile aynı digest'i kullandığını doğruladı (49152 bağlam, yaklaşık 19 GB model VRAM). `gemma4:12b` diskte, yüklü değil. Aşağıdaki 31 Ekim erişim kısıtları o keşfin tarihsel sınırlarıdır; burada vision inference/başarım testi yapılmış sayılmaz.

Tarih: 2026-10-31. Kapsam: yalnız PHASE 0. Kaynak kökü: `/home/ata/farabi`.
Bu belge tasarımdır; burada önerilen bileşenler kurulmadı veya çalıştırılmadı.

**Kanıt sınırı:** Kaynak kodu, diskteki systemd birimleri/drop-in'ler, model manifest adları, `/proc/driver/nvidia` ve disk kapasitesi okundu. Yerel soket erişimi kısıtlı olduğundan systemd canlı durumu, Ollama HTTP/list/ps ve PostgreSQL katalog sorgusu doğrulanamadı. `nvidia-smi` sürücüyle iletişim kuramadı. Bu sonuç GPU arızası veya servislerin kapalı olduğu anlamına gelmez. Canlı veritabanı tablo/satır varlığı, modelin yüklenmiş olması ve GPU boş belleği aşağıda kesinleşmiş bilgi olarak sunulmaz. Üretim modülleri import edilmedi; import yan etkileri ve testlerin canlı veriye erişme riski nedeniyle uygulama/test suite çalıştırılmadı. Secret dosyalarının değerleri rapora veya çıktıya alınmadı.

**Git başlangıcı:** `okul/templates/yonetici/sms_detay.html`, `server/main.py`, `server/rag.py`, `server/tests/conftest.py`, `smssistemi/app.py`, `smssistemi/test_dogum_app.py`, `smssistemi/test_rehber_duzenle.py`, `tahtayoklama/dashboard/app.py` zaten değişikti. `docs/` altında mevcut izlenmeyen inceleme belgeleri ve `server/tests/test_kazanim_katmani.py` vardı. Bunlar kullanıcı çalışması kabul edildi. Dal değiştirilmedi, commit/deploy yapılmadı. Bu keşfin tek yazısı bu yeni belgedir.

## 1. Mevcut Farabi mimarisi

- `/home/ata/farabi/client/main.py::main`: PyQt yüzeyi oluşturur; daemon `threading.Thread` içinde `runner`, ardından `asyncio.run(FarabiLive.run())` çalışır. Ana thread Qt event loop'udur.
- `client/ui.py::FarabiUI`, `MainWindow`, `_RootShim`: QApplication, pencere, UI sinyalleri. `FarabiUI.__init__` pencereyi oluşturur/gösterir.
- `server/main.py::app`, `lifespan`: FastAPI, flat import düzeni; route modülleri `app.include_router` ile bağlanır. `/etc/systemd/system/farabi-api.service` diskte `User=ata`, çalışma dizini `server/`, `uvicorn main:app --host 0.0.0.0 --port 8000` tanımlar. Yüklü süreç durumu doğrulanamadı.
- Ses oturumu istemcide Gemini Live; kitap/dosya/LLM proxy işleri server HTTP uçlarında. Diğer okul servisleri ayrı uygulamalardır; Visual Pulse bunlara bağımlılık eklememeli.
- `server/icerik.py::DATA_DIR = /mnt/farabi-data/farabi` kanonik içerik konumudur. Geçici dosya ve ders kayıt depoları ayrıca vardır.
- `server/main.py::RAG_AKTIF = False`; `lifespan` embedding/reranker yüklemeyi atlar. `server/rag.py`, `embed_servisi/`, `benchmark/schema.sql` gibi eski retrieval parçaları diskte durur. Visual Pulse bunlara bağlanmayacak. Kodda kalan importlar, modülün halen kullanıldığı kanıtı değildir.
- Kaynak yorumları güncel kodla her zaman uyuşmuyor: örneğin client açıklamalarında plan hattı kaldırıldı denirken `main.py::_plan_kazanimini_getir` ve `server/kazanim.py` mevcut. Esas alınan yürütülebilir koddur.

## 2. Client tarafında yeniden kullanılabilecek kodlar

| Dosya / sembol | Kullanım ve sınır |
|---|---|
| `client/core/tahta.py::derslik`, `sinif_duzeyi`, `sunucu_url`, `auth_headers` | Kimlik/config ve mevcut HTTP header'ları. Kimliğin son otoritesi sunucu olacak. |
| `client/core/zil.py::cizelge`, `ders_durumu` | Ders etkinlik kapısı; yalnız `tur == 'ders'` kabul edilir. |
| `client/core/program.py::simdiki_ders`, `gunun_programi` | Ders bağlamı; eksik programda konu uydurulmaz. |
| `client/ui.py::MainWindow._ekran_goruntusu_yakala`, `_ekran_goruntusu_cek` | Yalnız GUI-thread yakalama ve sinyal deseni örneği. Doğrudan çağrılmayacak. |
| `client/ui.py::FarabiUI`, `MainWindow` sinyalleri | GUI-thread'e güvenli geçiş; kopyalanmış QImage worker'a aktarılır. |
| `client/core/logger.py::get_logger` | Mevcut dönen client logu; `FARABI_LOG_DIR` test izolasyonu korunur. |
| `client/core/saglayicilar.py::gorsel_uret` | `requests` multipart + auth biçimi örneği; AI proxy çağrısı yeniden kullanılmaz. |
| `client/core/olaylar.py::abone`, `yayinla` | Abone hatası izolasyonu örneği. Ses/ders olayları pilotun tek tetikleyicisi yapılmaz. |

Mevcut screenshot yolu PNG'yi diske yazar, pencere başlığı gizlilik filtresi uygular, Farabi öndeyse küçültür/geri getirir. Sessiz gözlemde bu davranışlar istenmiyor. Var olan aracı değiştirmeden ayrı RAM capture slot'u gerekir. Visual Pulse'ta başlık/uygulama filtresi geliştirilmeyecek veya bu yoldan miras alınmayacak. Yakalama gerçek ekranda görünen Farabi UI'sini de içerebilir; pasif modda pencereler taşınmaz.

`client/memory/` eski kullanıcı profil/config paketidir; yeni ayarlar buna bağlanmamalı. Güncel tahta ayarları `client/config/api_keys.json` üzerinden okunuyor.

## 3. Server tarafında yeniden kullanılabilecek kodlar

- `server/auth.py::dogrula_tahta`, `TahtaKimligi`: kimlik doğrulama dependency'si ve sunucunun belirlediği derslik.
- `server/main.py` router kayıt düzeni: tek yeni isteğe bağlı router entegrasyonu; mevcut uçlar değiştirilmez.
- `server/proxy.py::gorsel_uret_endpoint`: `UploadFile`, multipart, parça parça byte sayımı örneği. Endpoint AI çağırdığı için Visual Pulse upload'u buraya yönlendirilmez. Buradaki 60 MB sınırı pilot için fazla; ayrı düşük limit önerilir.
- `server/dosya.py::dosya_isle`, `dosya_indir`, `_eski_gecici_temizle`: upload sayımı, TTL ve resolve/containment örnekleri. İşleyicileri AI çalıştırabilir; çağrılmayacak. Mevcut temizlik kodu ortak queue protokolü değildir.
- `server/kazanim.py::_yukle`, `_ders_adi`, `_hafta`, `kazanim_bul`: yayın JSON'u ve sunucuda ders bağlamı çözümü örneği. Kazanım analizi Phase 1'e alınmaz.
- `server/db.py::baslat`, `baglanti`: mevcut threaded PG pool. `baglanti.__enter__` her bağlantıda `register_vector` çağırır; sırf reuse için Visual Pulse'u bu RAG bağlantı katmanına zorlamamak gerekir.
- `server/saglayicilar.py::gorsel_uret`, `metin_uret`, `_config_oku`: mevcut secret okuma ve sağlayıcı çağrı düzeni. Serbest metin ve otomatik fallback zinciri gece provider sözleşmesinin aynısı değildir; confidence kontrolü dışında otomatik buluta düşmek için kullanılmaz.
- `soruhavuzu/uretici.py::uret`: Ollama `/api/chat`, JSON ve sınırlı retry örneği. Soru üreticisi çağrılmaz, payload/prompt kopyalanmaz.

Genel, kalıcı, bounded upload/event kuyruğu veya Visual Pulse retry/idempotency altyapısı tespit edilmedi. Mevcut HTTP çağrılarının timeout/hata yakalaması yeni kuyruk gereksinimini tek başına karşılamaz.

## 4. Ders/zil entegrasyonu

`tahtayoklama/dashboard/okul_ana_veri.py::baglan` PostgreSQL'e bağlanıp `search_path = okul_ana` ayarlar. `OKUL_ANA_DSN` veya `~/.config/okul-ana/baglanti` kullanılır; değerleri okunup gösterilmedi.

`okul_ana_goruntu.py::zil_json_uret` → `okul_ana.zil`, `ayar`, `ogretim_yili`; `program_json_uret` → `okul_ana.ders_programi`, `sinif`. `okul_ana_yayin.py::yayin_json` içerik değişince `.yeni` + `os.replace` ile `tahtayoklama/data/zil.json` ve `ders_programi.json` yayınlar. `server/config_dagit.sh` bu yayınları tahtalara dağıtan mevcut yoldur; çalıştırılmadı.

İstemci `config/zil.json` ve `config/ders_programi.json` okur. `zil.ders_durumu` dosya yok/bozuksa `yok`, hafta dışı günlerde `tatil` döner; normal programda dakika çözünürlüğü ve bitiş dakikasını kapsayan `<=` davranışı vardır. Visual Pulse mevcut fonksiyonu değiştirmeden bu sınırı test etmeli; ders bitişinde pending kare için açık politika uygulamalı.

Varsayılan `tahta.sade_mod()` açık; sesin ders motoru uyuyabilir. Gözlemci QApplication ömrüne bağlanmalı, FarabiLive oturumuna/başlat düğmesine/Gemini anahtarı hazır olmasına bağlanmamalı. Farabi uygulaması tamamen kapalıysa süreç içi gözlemci çalışmaz. Bağımsız ajan daha sonraki ayrı karardır.

TR takvimi `ZoneInfo('Europe/Istanbul')`; duration/debounce için monotonic saat kullanılmalı. Tarihi bozuk tahta tespiti gerekir: sunucu `received_at` ve capture zamanını ayrı tutar, aşırı sapmayı reddeder. Resmî tatil/özel gün kapsamı mevcut haftalık zil çizelgesinden garanti edilmez; belirsiz çizelgede capture kapalı önerilir.

## 5. HMAC/authentication

Tahta Brain API'sinde request HMAC imzası yoktur. `client/core/tahta.py::auth_headers` → `X-Farabi-Board-Key` ve sürüm header'ı; `server/auth.py::dogrula_tahta` → gitignored `server/config/api_keys.json::board_keys` ile `hmac.compare_digest`. Bu karşılaştırma mesaj imzalama veya replay koruması sağlamaz. Dashboard'da `auth.py`/`guvenlik.py` HMAC örnekleri vardır; bunlar Brain tahta protokolü yerine geçirilmez.

Yeni router `Depends(auth.dogrula_tahta)` sonucunu endpoint'e alır. Derslik path/body'den değil `TahtaKimligi.derslik` üzerinden seçilir. Gövdede derslik varsa yalnız eşitlik kontrolü için kullanılabilir; tercih hiç göndermemektir. `board_id` mevcut dataclass'ta `None`; yeni sayısal ID uydurulmaz.

`FARABI_AUTH_REQUIRED=0` durumunda mevcut dependency `None` dönebilir. Visual Pulse bunu anonim upload izni saymamalı; kimlik yoksa kendi ucunda fail-closed olmalı. Mevcut dependency davranışı değişmez. Kimlik başlığı/log secret'ı yazılmaz. Ayrı event ID + digest retry tekrarlarını önler; bu bir kriptografik request imzası değildir.

## 6. PostgreSQL

Canlı katalog sorgusu salt okunur `PGOPTIONS` ve 3 sn timeout ile denendi, bağlantı başarısız oldu (`psql: error:`). Aşağıdaki envanter **kaynak şema ve SQL referanslarından** çıkarılmıştır; canlı tabloların tam listesi/satır sayısı değildir.

| Kaynak | Kaynak kodunda görülen yapı |
|---|---|
| `benchmark/schema.sql`, `faz1_schema.sql` | `farabi` için `kitap`, `chunk_egitim`, `ogretmen`, `kazanim(kod PK, sinif, ders, unite, metin)`, `sinif_kitap`, `yillik_plan`, `ders_programi`. Eski şema notu bazı tabloların boş bırakıldığını söylüyor; bugünkü doluluk bilinmiyor. |
| `benchmark/olcum_schema.sql`, `kazanim_test_schema.sql` | `metrik`, `soru_log`, `kazanim_test_soru`; Visual Pulse olay/analiz tablosu değildir. |
| `server/schema_*.sql` | `tahta_durum`, `yks_gosterim`, `atos_hafiza`, `idari_belge`, `chunk_idari`. Eski retrieval tabloları bağlanmayacak. |
| `soruhavuzu/sema.sql`, `vt.py` | Ayrı `soru_havuzu` DB: `kaynak_birim`, `soru`, `kazanim`, `soru_geri_bildirim`. `kazanim.id serial`, `sinif`, `ders`, `hafta`, nullable `kod`, `metin`, `durum`; UNIQUE `(sinif,ders,hafta,metin)`. |
| `okul_ana_veri.py`, `okul_ana_goruntu.py` | Okul ana şemasında `ogretim_yili`, `sinif`, `ders_programi`, `zil`, `ayar` ve diğer okul tabloları. DB seçimi DSN ile; kod fallback'i her ortamın canlı DB adı sayılmaz. |

`okul/db.py` ayrıca SQLite portal şeması barındırır; PostgreSQL envanteriyle karıştırılmamalı. Dashboard `okul_sql.py::kazanim_tablosu` dönüştürme yolundaki `kazanim`, JSON'dan geçici SQLite tablosudur; kalıcı PG kazanım kaynağı değildir.

## 7. GPU/Ollama

- `/proc/driver/nvidia/gpus/*/information` iki **NVIDIA GeForce RTX 3060**, device minor 0/1 gösterdi. Canlı VRAM toplamı/kullanımı ve utilization doğrulanamadı. Repo açıklamasındaki kapasite/boşluk ölçüm yerine kullanılamaz.
- Diskte `ollama.service`: `ollama serve`, `User=ollama`, `CUDA_DEVICE_ORDER=PCI_BUS_ID`.
- `ollama.service.d/override.conf`: `CUDA_VISIBLE_DEVICES=0,1`, `OLLAMA_KEEP_ALIVE=-1`, CUDA library ayarı. `zz-baglam.conf`: `OLLAMA_CONTEXT_LENGTH=49152`; temel unit'teki 8192 değerini dosya sırasıyla ezer. `zz-kvtest.conf`: flash attention açık, KV cache `q8_0`. Bunlar diskteki ayarlar; çalışan sürecin env'i doğrulanamadı.
- `farabi-embed.service`: `CUDA_VISIBLE_DEVICES=1`; proje notlarında bilinçli disabled. Canlı inactive/disabled durumu teyit edilemedi; açılması önerilmiyor.
- Manifest kökünde görülen dosyalar: `gemma4/12b`, `mistral-nemo/12b`, `cosmos-8b/latest`, `qwen3.8/27b`. Bu, repo notundaki “tek model” ifadesiyle aynı şey değil: eski manifestler diskte kalmış olabilir; blob bütünlüğü ve servis model listesi doğrulanmadı. `qwen3-vl:8b` manifesti bu standart kökte görülmedi; başka `OLLAMA_MODELS` konumu dışlanamaz.
- `soruhavuzu/uretici.py::MODEL = 'farabi'` (`qwen3.8:27b` takma adı), `think:false`, JSON yanıtı, `/api/chat`; mevcut tüketici kanıtı.
- `soruhavuzu/systemd/soru-havuzu-uret.timer`: 21:00 UTC = 00:00 TR; servis gece üretim çalıştırıyor. Aynı pencereyi paylaşmak GPU/LLM gecikmesi ve model eviction riski yaratır. Timer'ın canlı aktifliği burada doğrulanamadı.

Herhangi bir inference, preload, model indirme, GPU/env değişikliği yapılmadı.

## 8. Visual Pulse için eksik bileşenler

RAM ekran yakalama köprüsü; bounded compare/encode/upload worker'ı; saf değişim durum makinesi; statik/dinamik dedup; doğrulanan config/flag; ders başına kota; retry/idempotency; stream ve decode boyutu sınırlı yeni upload route'u; disk kotası ve atomik olay deposu; metrics; queue onarım/cleanup; pilot ölçüm araçları eksik. Gece vision/provider/classifier/observation bileşenleri sonraki fazlarda ayrıca gerekecek.

## 9. Önerilen client mimarisi

QApplication ömrüne bağlı optional controller. Flag varsayılan false; false iken timer, capture, worker ve ağ işi oluşturulmaz. Config hatası yalnız modülü kapatır. Bağımsız bir Qt event loop icat edilmez.

GUI QTimer ders kapısını kontrol eder; worker meşgulse tick atlanır. `primaryScreen().grabWindow(0)` yalnız GUI-thread'de; pixmap'ten ayrıştırılmış/kopyalanmış QImage worker'a aktarılır. QPixmap worker'da kullanılmaz. Grab süresi ayrıca ölçülür; capture tamamen UI dışına taşınabilir varsayımı yanlıştır. Pencere küçültülmez, xprop çağrılmaz, karşılaştırma kareleri diske yazılmaz.

Mevcut threading + Qt signal desenine uygun tek bounded worker: resize/grayscale/compare, state machine, WebP ve timeout'lu requests upload. Tek işi beklerken yeni capture biriktirmez; eski comparison işi yerine en güncel kare tutulur. Ağ bloklanırsa UI etkilenmez; worker'ın compare gecikmesi ölçülür. Pilot bunu yetersiz bulursa aynı bounded yapıda uploader ayrı thread'e ayrılabilir; başlangıçta gereksiz concurrency eklenmez.

Son gönderilen statik referans, önceki sample ve pending aday ayrı tutulur. Monotonic saat kullanılır; ders değişince durum/kota sıfırlanır. Sunucu kabulü gelmeden son ACK referansı ilerletilmez; yerel dedup pending upload'ları da kapsar. Upload limiti aşılırsa yeni kare durdurulur/ölçümlü drop edilir, kuyruk büyütülmez. QApplication.aboutToQuit ile timer durur, bounded kapanış yapılır; ağ bitmesini UI beklemez.

## 10. Önerilen server mimarisi

`server/visual_pulse.py` yeni APIRouter; `main.py` yalnız optional router kaydı. Receive → auth → validation → quota/disk reservation → WebP doğrulama → atomic persist → ACK. Gündüz OCR/VLM/text LLM/cloud çağrısı yok. API işlemi screenshot içeriğini loglamaz.

Disk işleri sync endpoint/threadpool veya açık offload ile yapılır; async event loop'ta ağır Pillow decode veya uzun filesystem taraması yapılmaz. FastAPI'nin başka endpoint'lerini etkileyen global hata handler/pool/GPU değişikliği yok. Feature disabled veya depo sağlıksızsa yalnız yeni endpoint kontrollü 503 verir.

## 11. Önerilen dosya yapısı

**Phase 1'de değiştirilecek dosyalar (henüz değiştirilmedi):**

- `client/ui.py`: ayrı RAM capture sinyali/slot'u ve optional lifecycle köprüsü; mevcut screenshot aracı korunur.
- `client/main.py::main`: controller başlatma ve kapanış bağlama; API key bekleyen runner'dan bağımsız.
- `client/config/api_keys.example.json`: `visual_pulse` varsayılan kapalı örnek alanı.
- `server/main.py`: yeni router kaydı; mevcut kullanıcı diff'i üzerine yalnız onaylı küçük değişiklik.
- `server/config/api_keys.example.json`: server pilot limitlerinin secretsiz örneği.

**Phase 1'de oluşturulacak dosyalar:**

- `client/core/visual_pulse.py`: config, controller/worker ve saf state machine; büyürse compare modülü ayrılır.
- `server/visual_pulse.py`: validation/API.
- `server/visual_pulse_store.py`: atomic queue, quota, idempotency, cleanup CLI.
- `client/tests/test_visual_pulse.py`, `client/tests/test_visual_pulse_ui.py`.
- `server/tests/test_visual_pulse.py`, `server/tests/test_visual_pulse_store.py`.
- `docs/VISUAL_PULSE_PILOT.md`: config, ölçüm ve rollback prosedürü.

**Sonraki faz adayları:** `server/visual_pulse_worker.py`, `server/visual_pulse_vision.py`, `server/visual_pulse_kazanim.py`, `server/schema_visual_pulse.sql`, `server/systemd/farabi-visual-pulse-*.{service,timer}`. Bunlar Phase 1 kapsamına alınmaz (AI worker). Cleanup için unit dosyaları ancak ayrı kurulum onayında devreye girer.

## 12. API tasarımı

Öneri: `POST /api/visual-pulse`, mevcut `/api/egitim/*` uçlarından ayrı optional router, aynı tahta auth dependency'si. Multipart: `metadata` JSON form alanı + `image` WebP dosyası. Base64 ağda kullanılmaz.

```json
{
  "schema_version": 1,
  "event_id": "a36bf512-49dc-4dc1-b69d-86e9f8560a2a",
  "captured_at": "2026-10-31T10:24:18+03:00",
  "lesson_no": 3,
  "event_type": "scene_change",
  "dynamic_content": false,
  "comparison_hash": "0123456789abcdef",
  "comparison_algorithm": "gray-diff-dhash-v1",
  "sequence": 7,
  "capture_width": 1600,
  "capture_height": 900
}
```

`phash` adı altında dHash saklanmaz; algorithm/version açık yazılır. Subject/board ID zorunlu client girdisi değil; server auth ve programdan zenginleştirir. Enum, timestamp timezone/sapma, ders no, UUID, sequence, alan uzunluğu ve metadata boyutu Pydantic ile doğrulanır; bilinmeyen alanlar reddedilir. MIME/uzantı yetmez: RIFF/WEBP formatı, gerçek decode, piksel limiti, tek kare (animasyon reddi), gerçek boyut uyumu doğrulanır. Decompression-bomb limiti uygulanır.

Önerilen cevaplar: 202 `{status:'queued',event_id,...}`; aynı ID/aynı digest retry → başarılı duplicate ACK; aynı ID/farklı içerik → 409; 401 kimlik; 413 byte limiti; 415 format; 422 metadata; 429 rate/ders kotası; 503 flag/depo/disk kapasitesi. Retry-After uygun hatalarda döner. Event ID capture sırasında bir kez üretilir, retry'da değişmez. Retry yalnız network/408/429/geçici 5xx; kalıcı 4xx tekrar edilmez. ACK yalnız kalıcı commit sonrası verilir.

Multipart parser endpoint öncesinde spool yapabilir: yalnız `await image.read` sayımı toplam request'i korumaz. Yeni path'e özel ASGI receive boyut sayımı ile Content-Length olmayan chunked gövde de sınırlandırılmalı; form alan/dosya sayısı sınırı gerekir. Mevcut endpoint limitleri değiştirilmez.

## 13. Queue tasarımı

Önerilen kök: config ile `/mnt/farabi-data/farabi/visual_pulse_queue`. Henüz oluşturulmadı.

```text
YYYY-MM-DD/<server-generated-board-token>/lesson_03/
  <server-generated-event-token>/
    image.webp
    event.json
```

Derslik yalnız auth'tan alınır, path segmenti sunucuda güvenli token'a çevrilir; raw client dosya adı/path kullanılmaz. Tarih TR normalize edilir ve kabul penceresi sınırlandırılır. Event token UUID veya board+event ID digest'idir; deterministik retry adresi sağlar. Timestamp, tür, sıra metadata'da bulunur. Çıplak timestamp+sequence reboot/retry çakışması yapabileceğinden tek başına dosya anahtarı değildir.

Aynı filesystem'de geçici event dizinine iki dosya yazılır; flush/fsync sonrası atomic rename ve parent fsync ile commit. ACK kaybında aynı ID yeniden bulunur. Eksik `.tmp` dizinleri tüketilmez. Atomik commit ile kota kontrolü arasında yarış olmaması için processler arası kilit/reservation gerekir; başlangıçta tek API worker varsayımına sessizce güvenilmez. Duplicate check kota sayımından önce yapılır. Sayaçlar restart'ta committed metadata'dan yeniden kurulabilir; her request tüm ağacı taramaz.

Pilot için PG/Redis/Celery gerekmiyor; immutable event sidecar'ları yeterli. Worker aşamasında lesson manifest ve atomik claim/lease ile `pending/processing/done/failed` tutulabilir. Analiz anahtarı lesson+ordered input digest+analysis_version; yeni geç olay gelirse yeni input revision oluşur. Eski completed revision tekrar çalıştırılmaz. Lease expiry/crash recovery ve retry sayacı gerekir; poison lesson diğerlerini durdurmaz.

**Önerilen başlangıç korumaları, ölçüm sonucu değişir:** 1 MiB image, 16 KiB metadata, 2 MiB toplam request, 4 MP decode, 30 event/ders, 10 GiB queue kotası, minimum 20 GiB veya %10 boş diskten yüksek olanı, client max 3 encoded pending event ve 3 MiB RAM retry kotası. Değerler hard-code değil config. Queue filesystem'i mount değilse kök diske yanlışlıkla yazılmasını engelleyen kontrol önerilir. 503/backoff ile capture geçici durdurulabilir; ana Farabi etkilenmez.

TTL: başarıyla işlenen raw görüntü için örnek 72 saat; işlenmemiş pilot veri için ayrı örnek 7 gün üst sınırı. Phase 1'de analiz yok diye sınırsız birikim olmaz. Kota dolunca sessiz eski-veri silmek yerine yeni kabul durur. Cleanup etkin lease'i silmez, güvenli kök containment ve lock kullanır; TTL nedeniyle silinen pending olay sayısını metrikte kaydeder. Retry'ı eski veriyi yeniden canlandırmaktan koruyan küçük tombstone/dedup metadata'sı retry ufkundan uzun tutulur.

## 14. Change detection algoritması

Başlangıç seçimi: **320×180 grayscale mutlak fark + değişen piksel oranı; küçük dHash yardımcı sinyali**. NumPy/Pillow client bağımlılıklarında zaten var. Gerçek test yapılmadığından en düşük CPU veya yeterli doğruluk kanıtlanmış değildir; Phase 1 ölçümünün hipotezidir.

- Piksel başına küçük renk değişimini eleyen eşik; sonra anlamlı değişen piksel oranı ve normalize mean absolute difference hesaplanır. İnt16 fark alınır, uint8 taşması önlenir.
- Hem önceki sample'a (hareket/stabilite) hem son event referansına (anlamlı yenilik) bakılır. Küçük kalem izleri sample başına eşiği geçmese bile referansa göre biriken fark olay doğurabilir.
- 64-bit dHash ucuz bir ek dedup sinyalidir; yalnız hash aynı diye küçük metin değişimi atılmaz. Benzer PDF sayfasının aynı hash'e düşmesi mümkündür.
- Histogram tek başına sayfa metni/yerleşim değişimini kaçırabilir; ana karar değildir.
- DCT pHash ek hesap/bağımlılık gerektirebilir; SSIM pencere hesapları daha maliyetlidir. İkisi benchmark karşılaştırma adayıdır; başlangıç runtime bağımlılığı değildir. OpenCV/scikit-image/imagehash kurma önerisi yok.

Değişim başlar → pending aday; stabilite süresi boyunca anlamlı hareket kesilirse son kararlı kare kabul edilir. Minimum event aralığı ve son referansla dedup uygulanır. Sürekli çizim sırasında maksimum bekleme veya ders bitişi politikası config olmalı; ısrarla stabilite beklerken bütün dersi kaybetmemeli. Uzun çizim timeout'u video gibi etiketlemek zorunda değildir; dinamik ayrımı aşağıdaki ayrı sinyalle yapılır.

## 15. Dynamic/video detection

Sliding window içinde yüksek değişim görülen sample oranı + değişen alan kapsamı + aralıksız süre. Küçük bölgesel el yazısı ile ekran genelindeki hareket aynı sayılmamalı; düşük çözünürlük tile kapsaması yardımcı olabilir. Heuristic gerçek “video tanıma” iddiası taşımaz; slayt animasyonu/scroll da dinamik olabilir.

`STATIC → CHANGING → DYNAMIC → STABILIZING` durumları; giriş/çıkış hysteresis ile yapılır. Dynamic'e girince bir başlangıç örneği, sonra yalnız sample interval dolunca tek örnek; çıkışta kararlı son frame. Girişte saklanan başlangıç adayı için en çok bir ilave buffer; video frame geçmişi tutulmaz. Başlangıç/son örnekleri de minimum aralık, ders kotası ve dedup kapsamındadır. Son frame başlangıçla aynıysa tekrar gönderilmez.

Örnek ayar hipotezi: 2 sn comparison, 10 sn window, yüksek hareket örnek oranı ≥0.8, 120 sn sampling, 4 sn stabilization, 20 sn minimum event interval. 40 dk kesintisiz videoda yaklaşık 20 ara örnek + sınır kareleri olabilir; bu 5–15 hedefini aşabilir. Dolayısıyla 180–300 sn dynamic sampling pilotta ayrıca karşılaştırılmalı; quota sert üst sınırdır. Bütün eşikler config ve algorithm version ile saklanır.

## 16. Performans tahmini

Ölçüm yapılmadı; aşağıdakiler hesap ve pilot bütçe önerisidir.

320×180 uint8 gray buffer 57.600 byte; 3 buffer ~169 KiB. 1920×1080 RGBA bir frame ~7.9 MiB; 2–3 kopya ~16–24 MiB; Qt/Pillow dönüştürme geçicileri eklenir. Tam çözünürlük history tutulmaz. 2 sn interval 40 dakikada ~1200 karşılaştırma yapar ama sadece anlamlı event upload edilir. Resize/grab kaynak çözünürlüğü ve cihaz sürücüsüne bağlıdır.

Başlangıç pilot bütçesi: ortalama CPU artışı tek çekirdeğin %5'inin altında, RSS artışı ≤50 MiB, ek GUI capture işi p95 <30 ms hedefi; bunlar garanti değil kabul önerisidir. Büyük ekran/yaşlı i3 üzerinde grab tek başına aşabilir; interval artırma, scale/kopya azaltma veya pilotu kapatma seçenekleri ölçümle seçilir. Farabi açık/kapalı baseline ve kullanıcı girdisi gecikmesi birlikte ölçülür.

## 17. Tahmini veri miktarı

Varsayım: 30 tahta × 8 ders/gün; event 80–100 **KB decimal**, 5–15 event/ders. Boyut benchmark sonucu değildir.

| Ölçek | 5 event × 80 KB | 15 event × 100 KB |
|---|---:|---:|
| Tahta/ders | 0.40 MB | 1.50 MB |
| Tahta/gün | 3.2 MB | 12 MB |
| 30 tahta/gün | 96 MB | 360 MB |
| 7 gün raw | 0.672 GB | 2.52 GB |

40 tahta için günlük 128–480 MB. 30 tahta, 30 event/ders kota ve 100 KB ortalama → 720 MB/gün; hard 1 MiB payload limitinde aynı kota ~7.03 GiB/gün olabilir. Disk kotası ortalamaya göre güvenlik sağlamaz; ayrıca global cap gerekir. Metadata, geçici yazı, storyboard, retry trafiği ve filesystem overhead dahil değil. 30 eşzamanlı 100 KB event ~3 MB burst; jitter ve sınırlı retry gerekir.

`df -h` keşif anında veri mount'u 1.8 T toplam, 84 G kullanılan, ~1.7 T boş; kök/home volume 462 G toplam, 327 G boş gösterdi. Bunlar anlık kapasitedir, kalıcı kabul bütçesi değildir.

## 18. Night Vision tasarımı

Phase 2; Phase 1'de worker/inference yok. API'den ayrı CLI/process, `Europe/Istanbul` 00:00–06:00 kapısı; her ders ve her AI çağrısından önce zaman kontrolü. Süre sonunu aşacak çağrı için kalan zamana bağlı timeout; bütçe biterse tekrar işlenebilir pending checkpoint. Yalnız timer'a güvenilmez.

Ders bazında chronological manifest; PASS A numaralı/time etiketli contact sheet ile bağlam. PASS B seçilen orijinal karelerle OCR/formül/el yazısı/detay. Contact sheet küçük yazı analizinin tek girdisi olamaz. Sheet boyutu, kare sayısı, orijinal seçimi ve token/image limitleri benchmark'ta karşılaştırılır. Tek-pass multi-image da kontrol koludur; contact sheet otomatik üstün sayılmaz.

Atomic lease, girdi digest'i, attempt limiti, deadline, per-lesson hata izolasyonu. Model/provider/prompt/analysis version saklanır; DB commit başarılı olmadan `done` olmaz. Raw TTL analiz çıktısını silmez. OCR metni soru havuzuna aktarılmaz; kalıcı minimum metadata ve gözlenen içerik dili korunur. “Öğretmen X yaptı” çıkarımı yapılmaz; sample aralıklarından kesin faaliyet süresi üretilemez.

## 19. Local Vision modeli

`qwen3-vl:8b` yalnız başlangıç adayıdır; burada model adının registry doğrulaması/inference benchmark'ı yapılmadı. Standart manifest yolunda görülmedi; otomatik indirilmez. Mevcut kodun `farabi` takma adıyla `qwen3.8:27b` kullanması, onun Visual Pulse için OCR/formül/Türkçe başarısını kanıtlamaz.

İki RTX 3060 donanımı dosyadan doğrulandı; kullanılabilir VRAM belirsiz olduğundan modelin belirli context ve çoklu görselle sığacağı garanti edilmez. Önce salt okunur canlı `nvidia-smi`, `ollama list/ps`, etkin systemd env doğrulaması; sonra onaylı küçük benchmark. `VISION_PROVIDER`, `VISION_MODEL`, timeout/image budget config'ten gelir; mevcut Ollama context/GPU dağılımı değiştirilmez. Eksik model açık durum raporu üretir ve worker işi bekletir.

GPU planı: soru havuzu üreticisini durdurmadan önce mevcut gerçek tüketim ölçülmeli; farklı gece alt penceresi veya ortak erişim bütçesi kararlaştırılmalı. Yeni bir kilit yalnız Visual Pulse'ta olursa mevcut üreticiyi koordine etmiş sayılmaz. Bu keşif hiçbir GPU/env değişikliği önerisini uygulanmış kabul etmez.

## 20. Cloud escalation tasarımı

Phase 3; ilk pilotta cloud tamamen kapalı. Küçük `VisionProvider.analyze_lesson(input, deadline) -> validated result` sözleşmesi; `OllamaVisionProvider` ve config'ten seçilen `CloudVisionProvider` adaptörü. Ortak schema, hata sınıfları ve sürüm alanları. Provider anahtarı mevcut gitignored server config/env mekanizmasından; istemciye veya loga aktarılmaz.

Sistem confidence'ı: schema completeness, unknown oranı, OCR alanının kullanılabilirliği, A/B konu tutarlılığı, seçilmiş tekrar sonuçlarının tutarlılığı ve benchmark kalibrasyonu. Modelin self-confidence'ı tek kabul kriteri değildir; sinyaller kesin doğruluk kanıtı sayılmaz. Eşikler validation setinde kalibre edilir.

Düşük skor/invalid JSON/okunamayan el yazısı/formül → bütçe ve enabled flag uygunsa ikinci görüş. En çok sınırlı local repair/retry; geçersiz JSON sınırsız döngüye girmez. Cloud timeout/invalid yanıtında sonucu uydurmak yerine unresolved/review durumu. Local ve cloud çıktıları/provenance ayrı korunur; cloud her durumda doğru kabul edilmez. Günlük request/byte/maliyet bütçesi ve escalation oranı ölçülür. Mevcut provider havuzunun gizli otomatik fallback'i bu karar kapısını atlamamalı.

## 21. RAG'siz kazanım eşleştirme

Tercih adayı `soru_havuzu.kazanim`: satır ID'si ve ders/sınıf SQL filtreleri zaten var. `soruhavuzu/kazanimlar.py::oku`, haftalık `tahtayoklama/data/kazanimlar.json` satırlarını bu şekle dönüştürüyor; `vt.py::kazanim_upsert` unique anahtarı koruyor. `kod` nullable, aynı kazanım farklı haftalarda tekrarlanabilir. Kaynak/ID/curriculum sürümü açık tutulmalı; DB canlı doluluğu doğrulanmadan kesin seçim yapılmamalı.

Parametreli SQL örneği (yalnız sonraki faz tasarımı):

```sql
SELECT id, kod, metin, hafta
FROM kazanim
WHERE sinif = %s AND ders = %s AND durum = 'aktif'
ORDER BY hafta, id;
```

Ders adı canonical sözlüğü ve sınıf doğrulanır; konu bilinmiyorsa zorla eşleşme yapılmaz. SQL ile yalnız ilgili ders/sınıf adayları local text LLM'e verilir. Liste bağlama sığmazsa kontrollü SQL grupları içinde sınıflandırılır ve yalnız aday ID'lerle son seçim yapılır; embedding/chunk retrieval kullanılmaz. En fazla 3 match; boş match geçerli.

Pydantic ID tipini, confidence 0–1 aralığını, maksimum 3 ve benzersizliği doğrular. Dönen her ID SQL allowed-ID kümesinde ve aynı ders/sınıf bağlamında olmalı; yabancı ID reddedilir. Tekrarlanan haftalar canonical ID/snapshot politikasına göre birleştirilir. `soruhavuzu/siniflandir.py` embedding kullandığından pipeline olarak reuse edilmez. Mevcut soru üretim/sınıflandırma tablosuna screenshot sorusu yazılmaz.

## 22. Database değişiklik önerisi

Phase 1 **migration gerektirmez**; queue metadata dosyada. Phase 2–5 öncesi gerçek katalog, izinler, büyüklük ve mevcut uygun gözlem tablosu tekrar kontrol edilmeli.

Gerekirse `farabi` içinde tek yeni `lesson_observations` kalıcı tablo: ID; derslik/tarih/ders no; input_digest/revision; structured JSONB; analysis confidence; provider/model; prompt_version/analysis_version; created_at/updated_at; durum. UNIQUE derslik+tarih+ders_no+input_digest+analysis_version. Aynı revision idempotent upsert. Farklı revision geçmişi korunur; latest seçimi açık olur.

Geçici `visual_pulse_events` tablosu zorunlu değil; event ledger disk sidecar'ları yeterliyse eklenmez. Operasyonel sorgu/transaction ihtiyacı kanıtlanırsa ayrı migration tasarlanır. Cross-database kazanım ID'sine PostgreSQL FK kurulamaz: `source_database/source_table/source_id` ve aday metin/kod/sürüm snapshot'ı ya JSONB match içinde ya gerekirse ayrı ilişki tablosunda saklanır. Başka DB'nin ID'sini `farabi.kazanim.kod` sanmak hatadır.

Migration planı: canlı katalog salt okunur teyit → DDL/indeks/rol ve geri dönüş metni review → staging doğrulama → ayrı açık onay → bakım penceresinde yalnız additive migration. Mevcut tablolara trigger veya soru havuzu yazımı yok. Bu keşifte SQL dosyası bile uygulanmadı.

## 23. Systemd önerisi

Mevcut standarda uygun ayrı `Type=oneshot`/restart edilebilir CLI, `User=ata`, `WorkingDirectory=/home/ata/farabi/server`, mevcut venv, düşük Nice/CPUWeight/IOWeight; API'ye `Requires=` bağımlılığı eklenmez. İleride `farabi-visual-pulse-worker.service/.timer`; timezone açık `OnCalendar=... Europe/Istanbul`. Gece kaçırıldı diye gündüz inference başlatılmamalı: `Persistent=false` ve worker içi pencere kapısı önerilir.

Cleanup AI'sız ayrı `farabi-visual-pulse-cleanup.service/.timer` veya onaylı operasyon CLI'si; kota kontrolü cleanup zamanlayıcısından bağımsız çalışır. Pilotun TTL'si için cleanup çalıştırma yöntemi etkinleştirme öncesi seçilmeli. Unit dosyasını hazırlamak enable/start yetkisi değildir. `farabi-idari-yukle` ve iptal edilmiş kazanım timer'ları açılmaz. Soru havuzu timer'ı değiştirilmez. Etkin unit/env doğrulaması erişim kısıtı nedeniyle açık kalmıştır.

## 24. Riskler (önem sırasıyla)

1. **Üretim/UI bozulması:** GUI-thread capture maliyeti, yanlış thread'de Qt, ses oturumuna yanlış bağlama. Çözüm bounded optional bridge, fail-safe startup, eski cihaz pilotu, flag kapatma.
2. **Disk/RAM ve API kaynak tüketimi:** multipart parser spool, decompression bomb, sınırsız retry, quota yarışları. Çözüm request giriş limiti, decoded pixel limiti, rezervasyon/kilit, global cap, mount ve free-space kontrolü.
3. **Yanlış ders/kimlik:** client'tan path/board kabulü, bozuk saat, stale program, tatil kapsamı. Çözüm auth kimliği, TR normalization, saat sapması, schedule validation ve capture-off.
4. **Gece GPU çakışması:** soru üretici + mevcut sürekli resident model; canlı VRAM bilinmiyor. Çözüm önce ölçüm ve açık workload planı, otomatik model indirmeme.
5. **Veri kaybı/çift olay:** ACK kaybı, reboot, partial write, quota sonrası duplicate reddi. Çözüm stable event ID, atomic event directory, recovery, digest/conflict kontrolü, dedup tombstone.
6. **Algoritmik yanılgı:** saat imleci/animasyon false event, benzer sayfa missed event, yazıyı video sayma. Çözüm iki referans, alan oranı, hysteresis, etiketli replay veri seti, ölçümlü eşik.
7. **Yanlış analitik kesinlik:** model confidence yanılgısı, küçük yazı, “öğretmen yaptı” iddiası. Çözüm benchmark, provenance, unknown ve gözlenen ekran dili.
8. **Kaynak/schema karışıklığı:** üç kazanım yapısı, eski RAG bağlantısı, cross-DB ID. Çözüm açık SQL repository, allowed-ID doğrulaması ve sürüm snapshot'ı.
9. **Dağıtım gerçeği:** Farabi kapalıyken süreç içi gözlemci yok; sunucudaki client dosyaları gerçek tahta donanımını temsil etmez. Çözüm süreç ömrü kararı ve gerçek tahtada ölçüm.

## 25. Phase 1 implementasyon planı

1. Bu discovery ve aşağıdaki pilot kararları onaylanır; mevcut kullanıcı diff'i yeniden kontrol edilir.
2. `client/core/visual_pulse.py`: doğrulanan typed config + saf state machine, yapay/replay kareleriyle test. Flag false zero-activity.
3. Aynı modülde bounded worker, WebP codec kontrolü, RAM retry/kota ve metrics; karşılaştırma algoritması kendi sürümüyle.
4. `client/ui.py` RAM signal/slot'u; `client/main.py::main` optional QApplication lifecycle bağlantısı. Önce false flag ile mevcut UI smoke testi.
5. `server/visual_pulse_store.py`: güvenli path/atomic commit/idempotency/quota/mount/disk/free-space/TTL cleanup. Tamamı temp kökte test.
6. `server/visual_pulse.py`: Pydantic/multipart/auth, yeni path'e özel toplam body sınırı, decoded image sınırı, durum kodları. AI modüllerine çağrı yok.
7. `server/main.py` router kaydı ve example config alanları; API mevcut route regression testleri. Kullanıcı değişiklikleriyle minimal entegrasyon.
8. `docs/VISUAL_PULSE_PILOT.md`: açma/kapama, config matrisi, ölçüm/cleanup, kabul ve rollback prosedürü. Test/build üretim restart'ı sayılmaz; gerçek deploy ayrı işlem.
9. Onaylı dağıtımla tek tahtada kapalı flag kontrolü, sonra sınırlı ders pilotu. Gerçek WebP çözünürlük/quality/okunabilirlik karşılaştırması. Sonuçlara göre 3 farklı donanım sınıfına genişletme; ardından 30+ tahta.
10. Pilot metrik raporu ve kabul kararı. Vision/OCR/cloud/dashboard/kazanım işine geçilmez.

Önerilen config mevcut JSON düzeninde `visual_pulse` alanı; enable için `VISUAL_PULSE_ENABLED` env override düşünülebilir. Sadece schema/example hazırlanır; gerçek config bu fazda değiştirilmez. Gerekli alanlar: enabled, comparison_interval/resolution, pixel_noise_threshold, change_threshold, stabilization_seconds, minimum_event_interval, dynamic_detection_window/ratio/area_threshold/sample_interval, max_events_per_lesson, capture_width/height, webp_quality, server_endpoint (aynı server origin), queue_retry_policy (attempt/backoff/jitter/deadline/max bytes), image/pixel/body/queue/free-disk/TTL limitleri. Config bounded range'lerle doğrulanır; key header'ını farklı host'a gönderen endpoint/redirect kabul edilmez.

Yeni bağımlılık başlangıçta beklenmiyor: client PyQt6/NumPy/Pillow/requests, server FastAPI/Pydantic/python-multipart/Pillow mevcut requirements'ta. WebP desteği gerçek tahtadaki codec build'inde runtime probe ile doğrulanmalı; yoksa modül kapalı/hata durumu, otomatik kurulum veya sessiz PNG fallback yok. Sonraki worker için httpx/SDK availability ayrı doğrulanır; paket kurma önerisi onaydan önce gereksinim değildir.

## 26. Test planı

- **Saf state machine:** aynı kare → 0 tekrar; küçük imleç/saat değişimi → eşik altı; benzer metinli PDF sayfa değişimi → event; küçük kalem izlerinin birikimi → tek stable event; sürekli çizim → debounce; video/scroll → bounded dynamic sampling; static'e dönüş → tek final; ders sınırı ve minimum interval; duplicate/reference ve retry ACK yarışı.
- **GUI:** GUI-thread grab ve copied QImage; minimize/raise yok; busy iken frame birikmez; feature false iken timer/network/capture yok; capture null/exception → ana UI açık; quit hızlı. Primary/multi-monitor ve X11/Wayland davranışı gerçek tahtada doğrulanır.
- **API/store:** auth yok/yanlış/None; sahte derslik/path traversal; MIME sahte, bozuk/animasyonlu WebP, pixel bomb; büyük/chunked body/çok form alanı; invalid metadata/timestamp; duplicate aynı digest ACK ve farklı digest 409; eşzamanlı quota; disk low/mount yok/permission hatası → graceful 503; partial write/restart recovery; cleanup lease/idempotency.
- **Ağ:** sunucu yok/timeout/ACK kaybı/429/503; bounded retry, jitter, expired event; reconnect'te upload fırtınası yok; ana Farabi ses/UI çalışır.
- **Regresyon:** mevcut `client/tests/test_ekran_yakalama_ui.py`, `test_board_auth.py`, `server/tests/test_auth.py` ve ilgili API testleri izole koşullarda. Bu keşifte test çalıştırılmadı.
- **Gerçek ders pilotu:** baseline ve flag açık CPU/RSS/UI input gecikmesi, grab/compare/encode p50/p95, WebP byte/okunabilirlik; PDF/kalem/video/sunum/website karışımı 40 dk dersler. False-positive/false-negative için insanın etiketlediği ekran değişim günlüğü; öğretmen faaliyet değerlendirmesi değil.
- **Ölçek:** 30 ve 40 sentetik auth'lı client, aynı zil anında burst; temporary store ile request latency, disk reservation ve API diğer uçlarının gecikmesi. Üretime yük testi keşif kapsamında yapılmaz.

Metrikler: screens_compared, changes_detected, events_after_debounce, static_events, dynamic_events, images_uploaded, bytes_uploaded, upload_failures, retry_count, dropped_events/reason, queue_size (count+bytes), quota_rejections, low_disk_rejections, grab/compare/encode süreleri. Derslik+tarih+ders bazında sayaç; screenshot/base64/key loglanmaz. Vision_processing_seconds/failures, local_success, cloud_escalations, kazanim_match_success sonraki fazlarda; Phase 1'de çağrı sayıları sıfır kalmalı.

Phase 2 benchmark: PDF/MEB/soru bankası/Türkçe metin/matematik/fizik/kimya/biyoloji/grafik/tablo/formül/el yazısı/çizim/video/sunum; küçük etiketli gerçek Farabi kümesi, ayar ve değerlendirme örnekleri ayrılır. Subject/topic doğruluğu, Türkçe OCR, formül/el yazısı, question detection, concepts, JSON geçerliliği, süre ve peak VRAM ölçülür. Phase 3'te aynı seçilmiş örneklerde local/cloud karşılaştırılır; escalation oranı/maliyeti gerçek ölçümden raporlanır.

## 27. Karar verilmesi gereken noktalar

**Phase 1 başlamadan onaylanacaklar:**

1. Süreç içi gözlemci: Farabi UI açıkken, ses hiç başlatılmasa da çalışsın; uygulama kapalıyken izleme bu pilotun dışında kalsın.
2. Tek tahta pilotu ve ölçüm bütçeleri; başlangıç algoritması gray diff + dHash, ayarların replay/gerçek dersle belirlenmesi.
3. `POST /api/visual-pulse`, multipart, mevcut board-key auth, auth None ise fail-closed; kimliğin server'dan gelmesi.
4. Filesystem queue ile DB'siz Phase 1; önerilen kök, kota/disk/payload limitleri; RAM-only client retry nedeniyle process kapanınca pending kayıp kabulü.
5. Ham veri TTL ve pending TTL, cleanup çalıştırma yöntemi; pilotun başarı/başarısızlık ve rollback eşikleri.
6. Önerilen dosya bazlı minimal entegrasyon ve default-off flag. Aktifleştirme/deploy/restart bu discovery'nin parçası değildir.

**Daha sonraki fazlardan önce:** canlı PG katalog ve kazanım kaynağı seçimi; gerçek GPU/VRAM/Ollama model doğrulaması; soru havuzuyla gece pencere paylaşımı; model kurulumuna ayrı karar; provider ve cloud bütçesi; benchmark confidence eşikleri; kalıcı observation şeması/migration ve unit kurulumu. Bunlar Phase 1'i AI kapsamına genişletmez.

## A–U discovery kapsam dizini

| İstenen başlık | Karşılığı |
|---|---|
| A. Mevcut Farabi mimarisi | §1 |
| B. Client mimarisi | §2, §9 |
| C. Server/API mimarisi | §3, §10 |
| D. Authentication/HMAC | §5 |
| E. Ders/zil sistemi | §4 |
| F. PostgreSQL yapısı | §6 |
| G. Kazanım verisinin mevcut yapısı | §6, §21 |
| H. Ollama/GPU yapısı | §7 |
| I. Yeniden kullanılabilecek kodlar | §2–3 |
| J. Yeni gereken bileşenler | §8 |
| K. Değiştirilecek dosyalar | §11 |
| L. Oluşturulacak dosyalar | §11 |
| M. Dependency ihtiyacı | §25 |
| N. Database etkisi | §22 |
| O. API tasarımı | §12 |
| P. Client performans riskleri | §16, §24 |
| Q. Server/disk/network riskleri | §13, §17, §24 |
| R. Vision mimarisi | §18–19 |
| S. Local/cloud provider mimarisi | §20 |
| T. Kazanım eşleştirme mimarisi | §21 |
| U. Phase 1 uygulama planı | §25–26 |

PHASE 0 COMPLETE

No production code modified.
No services restarted.
No database changes made.
No packages installed.
No models downloaded.

WAITING FOR APPROVAL TO START PHASE 1.
