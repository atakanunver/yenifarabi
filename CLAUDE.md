# Farabi

Sınıf akıllı tahtalarında çalışan sesli ders asistanı.
Detaylı mimari: `@docs/mimari.md` (sadece gerektiğinde oku)

**Donanım (server, hızlı referans):** 2× NVIDIA RTX 3060 12GB (3 DEĞİL —
dışarıdan gelen bir varsayımda 3 kart sanılmıştı, düzeltme burada kayıtlı).
İkisi de tam kapasite committed: biri `ollama.service`'e, diğeri
`farabi-api.service` (embedding+reranker) — ayrıntı ve gerekçe için aşağıdaki
"Bilinçli sapma (2026-08-09)" notuna bkz. Yeni bir GPU işi (ör. vision model)
planlanırken bu iki kartın ZATEN dolu olduğu unutulmamalı.

## Komutlar

Client kodu `client/` altında — detaylı komutlar, kurallar, bilinen sorunlar
için `@client/CLAUDE.md` oku (çalışırken client/ dizinindeysen zaten otomatik
yüklenir).

```bash
cd client
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
python main.py               # client çalıştır
venv/bin/python -m pytest tests/ -q   # test (pytest requirements.txt'te YOK, geliştirici makinesine elle kurulur)
python tools/dogrula.py       # içerik doğrulama kapısı
```

Lint/formatter yapılandırılmamış — `ruff` kurulu değil, komut yok.

## Yapı

(2026-08-14 itibarıyla koddan doğrulandı — server-taşıma sonrası.)

```
farabi/
├── CLAUDE.md          — bu dosya, günlük kurallar
├── docs/mimari.md     — detaylı mimari (server/veri/RAG tasarımı)
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
```

**`client/` — PyQt6 tabanlı tahta istemcisi.**
Detaylar `client/CLAUDE.md`'de (koddan doğrulanmış, güncellenmesi gerekebilir);
özet:

- `main.py` — `FarabiLive`: Gemini Live oturumu, araç çağrı dağıtımı, ders açılışı
- `ui.py` — `FarabiUI`/`MainWindow`: PyQt6 HUD; `main.py` bunu import eder, tersi
  olmaz. 2026-08-14: yerel içerik-hazırlama düğmeleri (KİTAPLARI/YKS SORULARINI
  METNE DÖNÜŞTÜR, ŞÜPHELİ SEMBOL TEMİZLE, KİTAP ÖZETİ ÇIKAR) ve açılışta
  `kitaplar/`/`YKS/` tarayan otomatik dönüştürme kaldırıldı — bu tahtanın artık
  o dizinleri yok, içerik hazırlama tek noktadan (server) yapılıyor. Aynı
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
  Kamera/ekran yakalama (`screen_processor.py`) 2026-08-09'da tamamen
  kaldırıldı — kullanılmıyor, `Gizlilik` kuralına aykırıydı.
- `tools/` — çevrimdışı içerik hazırlama script'leri (kitap/YKS PDF → JSON) hâlâ
  burada duruyor (kod olarak silinmedi) ama **artık bu tahtada koşmuyor** —
  işledikleri `kitaplar/`/`YKS/`/`icerik/` dizinleri client'ta yok; aynı
  script'ler server'ın kendi `client/` kopyasında (rsync ile senkron), kanonik
  veri konumuna (`/mnt/farabi-data/farabi/`) symlink'lenmiş halde çalışıyor.
  `dogrula.py` (ücretsiz doğrulama kapısı), `mikrofon_test.py` client'ta anlamlı
  kalmaya devam ediyor.
- `tests/` — pytest, ağ/model çağrısı yok. `test_saglayicilar.py` 2026-08-14'te
  HTTP-proxy davranışını test edecek şekilde yeniden yazıldı (eski
  sağlayıcı-zinciri testleri `server/tests/test_saglayicilar.py`'ye taşındı).
- `config/` — gerçek JSON'lar gitignore'lu, `.example.json` şablonları committed.
  2026-08-14: `api_keys.json`'dan 5 bulut anahtarı (groq/mistral/deepseek/
  openrouter/nvidia) SİLİNDİ, server'a taşındı — client'ta yalnızca
  `gemini_api_keys`/`gemini_api_key`, `derslik`, `sunucu_url`, `ders_kipi`,
  `os_system` kaldı.
- `memory/`, `planlar/` — koda BAĞLI DEĞİL, ölü/arşiv (silme, ama yeniden
  bağlama da — `client/CLAUDE.md`'de gerekçesi var)

> ⚠️ **`kitaplar/`, `YKS/`, `icerik/metin`/`ozet`/`yks_metin`/`eslemeler`/
> `kitaplar.json` client'ta ARTIK YOK (2026-08-14, server-taşıma).** Önceki
> sürümlerde burada "PDF bırakma dizinleri" olarak listeleniyordu — 1.1GB+
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
- `proxy.py` (2026-08-14 eklendi) — `POST /api/egitim/metin_uret`,
  `POST /api/egitim/gorsel_uret`: `saglayicilar.py`'nin HTTP yüzü.
- `dosya.py` (2026-08-14 eklendi) — `POST /api/egitim/dosya_isle` (multipart
  upload; PDF/docx/xlsx/pptx/görsel işleme + AI özet/analiz),
  `GET /api/egitim/dosya_indir/{id}/{ad}` (üretilen dönüşüm dosyaları, 24 saat
  sonra silinir).
- `config/api_keys.json` (gitignore'lu) — 5 bulut anahtarı (Gemini YOK, o
  client'ta kalıyor — ses oturumu mimari kısıtı, bkz. §14).

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

- ⛔ Server iskeleti — Faz 0a benchmark geçmeden başlanmaz
- ⛔ `/api/idari/*` — Faz 4, endpoint yazılmaz
- ⛔ **Yerel STT/TTS (faster-whisper, Piper) — KALICI OLARAK İPTAL EDİLDİ
  (2026-08-11), Faz 0a'da "henüz gerekmez" değil.** Ses kalıcı olarak Gemini
  Live'da kalıyor — bkz. `docs/mimari.md` §14. Başka bir projede denenebilir,
  bu projenin kapsamında değil.

> ⚠️ **Bilinçli sapma (2026-08-09):** Aşağıdaki iki madde bu listede "yapılmayacak"
> olarak dururken, kullanıcının açık onayıyla Faz 0a sırasında öne çekildi —
> geriye dönük olarak yasaklanmadılar, kararlar burada kayıt altına alınıyor:
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
> **İkinci sapma (2026-08-10/11):** Yukarıdaki maddenin "server iskeleti yok"
> kısmı artık geçerli değil — kullanıcının açık kararıyla `server/` iskeleti
> Faz 0a kapısı tam kapanmadan (B grubu sorusu o an 12/15) kuruldu. Gerekçe ve
> detaylar `docs/mimari.md` §15'te ("Neden server iskeleti bekliyor" altındaki
> not). Kısa özet: eşik+LLM katmanı birlikte grup C'de %94 doğru çıkmıştı,
> yöntemin çalıştığına dair yeterli kanıt vardı. `/api/idari/*` hâlâ
> yazılmadı, hâlâ Faz 4'e kadar yazılmayacak — bu kısıt değişmedi.
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

## RAG Kuralları (kritik)

- Cevap **sadece** retrieval sonucundan üretilir. Serbest üretim yok.
- Ana savunma: skor eşiğin altındaysa LLM'e hiç gitme → "Bu konu ders kitabında
  bulunmuyor."
- Arama iki aşamalı: (1) kazanım + kitap filtresi, (2) sonuç yoksa yalnızca kitap.
  Kazanım kodu bulunamadığında sistem çalışmaya devam eder.
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

Client↔Server event listesi bağlayıcıdır — `mimari.md` §10. Protokolü genişletmeden
önce dokümanı güncelle.

## Veri Yerleşimi

- **NAS** → dosyanın kendisi. Ayrı bir NAS (OMV) henüz kurulmadı — bunun yerine
  Brain sunucusuna zaten bağlı ikinci disk (`/mnt/farabi-data/farabi/`, 1.8TB)
  kullanılıyor (2026-08-14): `kitaplar/`, `yks/`, `icerik/{metin,ozet,
  yks_metin,eslemeler,onbellek,kitaplar.json}`. Gerçek NAS gelirse bu yol
  taşınır, kod bu ayrımdan habersiz (yalnızca `DATA_DIR` sabiti değişir).
- **PostgreSQL** → metadata, hash, sınıf, ders, kazanım, sayfa
- **pgvector** → chunk + embedding

Dosya içeriği DB'ye gömülmez.

## Veri İzolasyonu (kritik)

- `chunk_egitim` ve `chunk_idari` **ayrı tablolar**.
- Tahta token'ı yalnızca `/api/egitim/*` çağırabilir.
- `farabi_client` DB kullanıcısının `chunk_idari` üzerinde yetkisi yok.

İdari tablolar Faz 4'e kadar boş kalır, izolasyon baştan kurulur.

## Gizlilik

> ⚠️ **Karar (2026-08-11): Öğrenci sesi kalıcı olarak Gemini Live'a (Google
> bulutu) gidiyor.** Bu, önceki sürümlerde "geçici, kabul edilmiş bir açık"
> olarak yazıyordu ve yerel STT/TTS hedef gösteriliyordu — o plan **iptal
> edildi**. Gerekçe: Gemini Live'ın gerçek-zamanlı ses akıcılığını (konuşma
> sırası, araya girme, doğal tonlama) yerel bir hatla eşleştirmek ayrı, büyük
> bir mühendislik işi; başka bir projede denenebilir, bu projenin kapsamında
> değil. Detay: `docs/mimari.md` §14.

- Kamera yok.
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

## Loglama — iki tablo, karıştırma

- `metrik` → yalnızca süre + durum + skor. İçerik yok. Sınırsız saklanır.
- `soru_log` → soru/cevap metni **yalnızca** şu durumlarda: düşük skorlu `ok`,
  `yetersiz_kaynak`, `sayi_kontrolu_reddi`, `iptal`, `hata`.
  Başarılı+yüksek skorlu cevaplarda metin saklanmaz.

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

## Okuma

Şunları okuma: `*.pdf`, `data/`, `models/`, `*.onnx`, `venv/`, `__pycache__/`,
`client/logs/`, `client/config/api_keys.json*`, `server/config/api_keys.json*`,
`/mnt/farabi-data/farabi/` (kitap/YKS PDF'leri ve türetilmiş içerik — telifli/
büyük, 2026-08-14'te client'tan buraya taşındı; client'ta artık `kitaplar/`,
`YKS/`, `icerik/metin`/`ozet`/`yks_metin`/`eslemeler`/`kitaplar.json` YOK).
