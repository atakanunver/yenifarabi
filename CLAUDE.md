# Farabi

Sınıf akıllı tahtalarında çalışan sesli ders asistanı + aynı sunucuda koşan
okul operasyon servisleri (yoklama panosu, SMS).

- **Bu dosya = güncel durum + kurallar.** Tarihli olay anlatımları, kök neden
  hikâyeleri ve "neden böyle" gerekçeleri `DECISIONS.md`'de (2026-09-25'te
  buradan taşınanlar dosyanın sonundaki "Arşiv" bölümünde). Bir notun
  ayrıntısı için `grep "## <tarih>" DECISIONS.md`.
- Detaylı mimari: `@docs/mimari.md` §0–§14 (§15 yok). ⚠️ İçeriği
  **2026-09-13'te donmuş**, sonraki değişiklikleri yansıtmaz; çelişkide BU
  dosya esas. Dosya kaybolursa yeniden üretme: `git show
  3f26d71^:docs/mimari.md` ile geri al.
- Alt projelerin kendi `CLAUDE.md`'leri var: `client/`, `tahtayoklama/`,
  `smssistemi/`, `tahtaayar/`.

## Güncel durum (2026-09-25)

- **Farabi client:** 8 tahtada kurulu — 7 sınıf (9-A, 9-B, 10-A, 11-A, 11-B,
  12-A, 12-B) + `fenlab`. Tablo: aşağıda "Ağ Envanteri".
- **Tahtayoklama:** aynı 8 tahtada kurulu. Tahta tarafı
  `tahtayoklama/yoklama.py`; sunucu tarafı `tahtayoklama/dashboard/`.
- **Mikrofonsuz mod** şu an 8 tahtanın hepsinde açık (`api_keys.json::
  mikrofon`, bkz. DECISIONS.md 2026-09-25 "Gemini faturalandırma engeli").
- **`client/core/prompt.txt` hâlâ client'ta.** Server'a taşınması
  PLANLANDI, YAPILMADI (mimari.md §0).
- **IP değil hostname/MAC esas alınır.** DHCP kirası bozulunca IP değişiyor
  (12-A, 2026-09-22). Kanonik kayıt `server/tahtalar.json`. Bir tahtanın IP'si
  değişirse **üç yer** güncellenir: `server/tahtalar.json`, dashboard SQLite
  `tahtalar` tablosu (yoklama + uzaktan yönetim buradan okur), bu dosyadaki
  tablo.
- ⚠️ **Ders programı ve zil saatleri üç bağımsız kopya:**
  `mudur/ders_programi.json` (müdür yardımcısının kaynağı),
  `tahtayoklama/data/ders_programi.json` (dashboard'un kendi kopyası —
  `dashboard/ders_programi.py` docstring'i bilinçli bağımsız olduğunu
  söylüyor) ve her tahtanın `client/config/ders_programi.json`'ı. Biri
  değişince diğerleri OTOMATİK güncellenmez — `mudur/ders_programi_yukle.py`
  / `tahtayoklama/dashboard/scripts/ders_programi_yukle.py` ile senkron
  edilir. Aynı desen `zil.json` için de geçerli.

## Mimari: üç servis + tahta istemcisi

Hepsi bu makinede (`farabi.local`), **üç ayrı systemd birimi, üç ayrı venv**.
Kod paylaşmazlar, birini deploy etmek diğerini etkilemez; üretime almak =
ilgili servisi restart etmek. Servisler birleştirilmez; servisler arası bağ =
HTTP + HMAC.

| Servis | Dizin | Port | Ne yapar |
|---|---|---|---|
| `farabi-api` ("Brain") | `server/` | 8000 | RAG, kitap içeriği/PDF render, YKS, bulut LLM proxy, dosya işleme, tahta auth |
| `farabi-yoklama-dashboard` | `tahtayoklama/dashboard/` | 8010 | yoklama, roster, zil/ders programı, uzaktan yönetim (`/admin/uzaktan`) |
| `farabi-smssistemi` | `smssistemi/` | 8020 | toplu/kişisel SMS, rehber, Doğum Günleri, Yoklama SMS |
| `ollama` | — | 11434 | `qwen2.5:14b`, LAN'a açık, paylaşılan yerel LLM |

- **Tek bilinçli DB paylaşımı istisnası:** smssistemi'nin `/yoklama-sms`'i
  dashboard'un `yoklama_pano.db`'sini **salt-okunur, doğrudan** okur (bkz.
  DECISIONS.md 2026-09-23). Dashboard ↔ smssistemi başka bağı yok: HMAC SSO
  köprüsü (`/dogum`, `/sms-git`).
- **Uzaktan yönetim** (`/admin/uzaktan`): ekran karart/kaldır, yoklama
  aç/kapat, duvar kağıdı, anlık ekran görüntüsü (`GET /admin/uzaktan/
  ekran-goruntusu/{tahta_adi}?ham=1`), çoklu tahta seçimi. Tahtaya doğrudan
  `ogretmen` olarak SSH (`~/.ssh/id_ed25519_tahta`), sudo gerektirmez.

**Client ↔ Server ayrımı (KESİN, mimari.md §0):** client = yalnızca tahtadaki
arayüz/etkileşim yüzeyi (Gemini Live ses oturumu dahil); server = beyin (RAG,
sistem promptu, iş mantığı, sağlayıcı routing). Ses kalıcı olarak Gemini
Live'da, client'ta (2026-08-11 kararı); client'taki tek bulut anahtarı Gemini.

**Tahtaya dağıtım:** GitHub tek doğru kaynak (`github.com/atakanunver/
yenifarabi`, PUBLIC). Tahtalar GitHub'dan **doğrudan** çeker, server arada
değil: `server/farabi-kurulum.sh` `client/`'ı sparse-checkout ile klonlar,
tahtadaki `farabiguncelle.sh` = `git fetch` + `git reset --hard
origin/master` (günlük cron), `farabi-heartbeat.sh` 15 dk'da bir `POST
/api/client/heartbeat`. İstisna: **9-A** tam klon yapısını korur
(`~/farabi/repo`, client `~/farabi/repo/client`'ta) — mekanizma aynı.
Gitignore'lu ayarlar (`zil.json`, `ders_programi.json`, `api_keys.json`'ın
ortak alanları: Gemini anahtarı, `mikrofon`, `sunucu_url`) git ile gitmez,
`server/config_dagit.sh [--kuru] [tahta...]` ile SSH'tan dağıtılır; ortak
değerlerin kaynağı `server/config/api_keys_tahta_ortak.json` (gitignore'lu).
`farabi.local` kendi `server/` kodunu ayrıca GitHub'dan çeker.

**Tahta auth:** her `/api/egitim/*` router'ı `auth.dogrula_tahta`'ya bağlı,
üretimde ZORUNLU. Client tüm isteklerde `core.tahta.auth_headers()` ile
`X-Farabi-Board-Key` gönderir. Anahtarlar `server/config/api_keys.json::
board_keys` ve her tahtanın `client/config/api_keys.json`'ında;
`auth._board_keys()` dosyayı her istekte okur (restart gerekmez). Acil geri
dönüş: servis override'ına `Environment="FARABI_AUTH_REQUIRED=0"`.

### `client/` — PyQt6 tahta istemcisi

Detay `client/CLAUDE.md`'de. Özet:

- `main.py` (`FarabiLive`: Gemini Live oturumu, araç dağıtımı, ders açılışı),
  `ui.py` (`FarabiUI`/`MainWindow` HUD; kalem/silgi çizim katmanı
  `_CizilebilirGorsel` — yalnızca butonla açılır, LLM tool'u DEĞİL, çizim
  kaydedilmez).
- `core/` — `ders_motoru.py`, `olaylar.py` (event bus), `program.py`,
  `zil.py`, `anahtar.py` (Gemini anahtar havuzu), `transcript.py`,
  `tahta.py`, `saglayicilar.py` (sağlayıcı havuzu DEĞİL — server'a ince HTTP
  proxy; `metin_uret`/`gorsel_uret` imzaları korunmuş).
- `actions/` — modelin çağırdığı araçlar, tek kaynak `kayit.py`. Server'a
  bağlı olanlar sunucu ulaşılamazsa sessizce kısıtlayıcı metne düşer, ders
  bozulmaz. `kitap_sorusu` (RAG ile kaynaklı soru-cevap) ≠ `ders_icerigi`
  (konu anlatımı için sayfa metni) — karıştırma. `pdf_sayfa` PNG'yi
  indirip ≤30 dosyalık önbelleğe yazar, sonra `pdf_sayfa_metni` ile sayfa
  metnini modele verir. `ekran_goruntusu_al`/`ekrandaki_soruyu_oku` yalnızca
  tahtanın kendi ekranını yakalar (webcam yok; eski `screen_processor.py`
  ayrı, kaldırılmış bir modüldü).
- `tools/` — çevrimdışı içerik hazırlama script'leri (kitap/YKS PDF → JSON);
  tahtada koşmaz, bu makinede `/mnt/farabi-data/farabi/` verisiyle çalışır.
  `dogrula.py` ve `mikrofon_test.py` hâlâ kullanılır.
- `config/` — gerçek JSON'lar gitignore'lu, `.example.json` şablonlar
  committed. Client'ta yalnızca `gemini_api_keys`, `derslik`, `sunucu_url`,
  `ders_kipi`, `os_system`, `mikrofon`, `tahta_anahtari` kalır.
- `planlar/` koda bağlı değil, arşiv. Client'ın kendi kitap/YKS deposu YOK;
  yalnızca `icerik/onbellek/{pdf_sayfa,yks_sayfa}/` geçici önbelleği.

### `server/` — FastAPI Brain

- `main.py`/`rag.py`/`db.py` — `/health`, `/ready`, `POST
  /api/egitim/question`, `GET /api/egitim/kitaplar`, `POST
  /api/egitim/ders_kaydi_yedek`.
- `icerik.py` — `POST /api/egitim/ders_icerigi`, `GET /api/egitim/pdf_sayfa`
  (PyMuPDF → PNG), `GET /api/egitim/pdf_sayfa_metni`. Aynı ders için birden
  fazla cilt olabilir (ör. `matematik_9.pdf` / `matematik_9_2.pdf`):
  `ders_icerigi`'nin seçtiği kitap `_SON_KITAP`'ta (derslik anahtarlı)
  tutulur, `pdf_sayfa` onu tercih eder — bu senkron bozulursa tahtadaki
  sayfa ile Farabi'nin okuduğu ayrışır.
- `yks.py` — `POST /api/egitim/yks_sorusu`, `GET /api/egitim/yks_sayfa`;
  sıralı sunum oturumu `derslik` anahtarlı `_OTURUMLAR`'da (tek süreç tüm
  tahtalara hizmet ediyor, modül-seviyesi global kullanma).
- `saglayicilar.py` + `proxy.py` — bulut sağlayıcı havuzu
  (Groq/Mistral/DeepSeek/OpenRouter/NVIDIA, `GOREV_ZINCIRLERI`) ve HTTP yüzü
  (`/api/egitim/metin_uret`, `/api/egitim/gorsel_uret`). `gorsel` zinciri:
  `mistral/pixtral-12b-2409` → `mistral/mistral-medium-latest` →
  `nvidia/meta/llama-3.2-11b-vision-instruct`. **NVIDIA bu ağdan güvenilmez**
  (metin modelleri 410/timeout). Ollama'ya giden çağrılarda sistem mesajı
  şart (`_OLLAMA_VARSAYILAN_SISTEM`, yoksa Türkçe→Çince kayma).
- `dosya.py` — `POST /api/egitim/dosya_isle`, `GET
  /api/egitim/dosya_indir/{id}/{ad}` (24 saatte silinir). `belge_ozet`
  (metin özeti) ÖNCE yerel Ollama, bulut yalnızca yedek; görsel özet yalnızca
  bulut (yerel vision modeli yok, eklemek Kural 8 onayı ister). Diğer
  görevler (`gorsel`, `arama_sentez`, `video_ozet`, `sembol_duzelt`,
  `soru_taslak`, `kitap_ozet`) bulut öncelikli.
- `config/api_keys.json` (gitignore'lu) — bulut anahtarları + `board_keys`.
  `.gitignore` desen tabanlı (`*.env`, `**/api_keys*`,
  `!**/api_keys.example.json`); yeni anahtar dosyası bırakırken `git
  check-ignore` ile doğrula.
- Tahta işlemleri script'leri: `tahta-ssh.sh [--admin] <derslik>`,
  `farabi-kurulum.sh`, `config_dagit.sh`.

### Sunucu ortamı — tuzaklar

- **GPU:** 2× RTX 3060 12GB, her servis kendi kartına sabit:
  `farabi-api` → `CUDA_VISIBLE_DEVICES=0` (embedding+reranker), `ollama` →
  `1` (context 8192'ye düşürüldü, tek karta sığsın diye). İkisinde de
  `CUDA_DEVICE_ORDER=PCI_BUS_ID` şart — yoksa CUDA numaralandırması
  `nvidia-smi`'ninkiyle ters çıkıp iki servis aynı karta düşebiliyor.
  2026-09-02 ölçümü: GPU 0'da yük altında ~7 GB boş, GPU 1 dolu. Yeni GPU işi
  planlanırken o an `nvidia-smi` ile yeniden ölç.
- **Okul ağı SSL-inceleme yapıyor (MEB-CERT-TTVPN).** Sertifika sistem güven
  deposuna VE her venv'in `certifi`'sine eklendi — yeni venv kurulursa
  certifi'ye tekrar eklenmeli, yoksa bulut çağrıları ve HF Hub kırılır.
  `HF_HUB_OFFLINE=1` bu yüzden açık. CDN'e bağlı her şey burada sessizce
  bozulabilir.
- `farabi-api` `--host 0.0.0.0` ile LAN'a açık (tahtalar başka türlü
  ulaşamaz); VLAN/güvenlik duvarı yok, dış sınırı okul güvenlik duvarı
  koruyor.
- Bu çalışma dizini (`/home/ata/farabi`) canlı üretim — servisler buradan
  koşuyor.

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

`server/` — `farabi-api.service`
(`WorkingDirectory=/home/ata/farabi/server`,
`ExecStart=.../server/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000`).

```bash
cd server
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
venv/bin/uvicorn main:app --reload --port 8000   # geliştirmede elle çalıştır
venv/bin/python -m pytest tests/ -q              # test (pytest requirements.lock.txt'te, venv'de kurulu)
venv/bin/python -m pytest tests/test_icerik.py -q          # tek dosya
venv/bin/python -m pytest "tests/test_icerik.py::TestKitapBul" -q  # tek sınıf

sudo systemctl status farabi-api.service          # üretim servisi durumu
sudo systemctl restart farabi-api.service         # kod değişikliğinden sonra üretime almak için
journalctl -u farabi-api.service                  # server logu (dosya log YOK, yalnızca journal)
```

`benchmark/` — Faz 0a/R-4 retrieval ölçüm harness'ları, pytest'e bağlı
DEĞİL, her script bağımsız CLI. `rag_test.py` üretimin gerçek
`server/rag.py::RagMotoru`'sunu import eder; `recall_test.py`/
`katman_test.py` pipeline'ı kendi başına yeniden uygular (neden ayrı
oldukları `rag_test.py` docstring'inde; fark varsa `rag_test.py` esas).

```bash
cd benchmark
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
venv/bin/python rag_test.py          # üretim RAG koduna karşı ölçüm (soru seti argümanla verilir, script docstring'ine bkz.)
venv/bin/python recall_test.py       # Recall@4/rerank/eşik/MRR, üretimden bağımsız model
venv/bin/python katman_test.py       # iki katmanlı halüsinasyon savunması simülasyonu
```

`tahtayoklama/dashboard/` — ⚠️ **pytest DEĞİL, `unittest`** (venv'de pytest
yok, çağırmak "No module named pytest" verir). Yeni testte var olan
`unittest.TestCase` desenini sürdür.

```bash
cd tahtayoklama/dashboard
venv/bin/uvicorn app:app --reload --port 8010          # geliştirmede elle
venv/bin/python -m unittest discover -p 'test_*.py'    # tüm testler
venv/bin/python -m unittest test_uzaktan_ekran -v      # tek dosya (modül adı, .py YOK)
venv/bin/python -m unittest test_uzaktan_ekran.TestUzaktanEkran.test_route_gecersiz_tahta

sudo systemctl restart farabi-yoklama-dashboard.service
```

`smssistemi/` — pytest, düz `test_*.py` dosyaları (tüm komutlar
`smssistemi/CLAUDE.md`'de).

```bash
cd smssistemi
venv/bin/python -m pytest -q
sudo systemctl restart farabi-smssistemi.service
```

Tahtaya komut / log okuma:

```bash
server/tahta-ssh.sh <derslik> "<komut>"          # ogretmen olarak
server/tahta-ssh.sh --admin <derslik> "<komut>"  # etapadmin (sudo)
server/config_dagit.sh --kuru                    # gitignore'lu ayar dağıtımı, önce kuru çalıştır
```

### Lint: Ruff

Lint ve formatter aracı Ruff; runtime'dan ayrı geliştirme ortamında:
`.venv-tools/bin/ruff`. `--fix` / `format` çalıştırılabilir
(`.venv-tools/bin/ruff check . --fix`, `.venv-tools/bin/ruff format .`) ama
Farabi çalışan bir eğitim/yoklama sistemi, otomatik değişiklikler davranışı
bozabilir.

```bash
.venv-tools/bin/ruff check client server benchmark tahtayoklama tahtaayar smssistemi
.venv-tools/bin/ruff check smssistemi/app.py      # yalnızca dokunduğun dosya
```

⚠️ **Sıfır hata beklenmiyor — 2026-09-22 taban çizgisi 480 bulgu**
(`smssistemi` hariç 448, `smssistemi` 32). Değişiklikten önce ve sonra
çalıştırıp **farkı** oku ya da yalnızca dokunduğun dosyayı ver. Birikmiş
yığını topluca temizlemek Kural 6 kapsamında ayrı iş. `mudur/` ve `dogum/`
bilinçli olarak kapsam dışı.

Prosedür — kod değişikliğinden sonra önce yalnızca kontrol, bulgular
sınıflandırılır:
- F8xx / gerçek Python hataları: öncelikli incelenir.
- F401 / F841: güvenli olduğu kontrol edilerek temizlenebilir.
- I001 / formatlama: davranışı değiştirmediği doğrulandıktan sonra.
- DTZ / timezone: İstanbul/Türkiye saat mantığı kontrol edilmeden değiştirilmez.
- PLR / SIM / PERF / RUF: önce davranış etkisi değerlendirilir.

Bulgu gerçek bir bug ise önce çalışma mantığı incelenir, sonra minimum
değişiklik. Büyük ölçekli otomatik düzeltme yapılmaz. Ruff temizliğinde
bozulmaması gerekenler: yoklama sistemi, ders/zil zamanlaması,
İstanbul/Türkiye saat dilimi, öğrenci ve sınıf verileri, dashboard, SSH
bağlantıları, tahta ↔ server iletişimi, RAG, LLM bağlantıları, ders akışı,
mevcut API endpoint'leri, mevcut dosya ve veritabanı formatları. Sonrasında
Ruff tekrar + ilgili testler/çalışma kontrolleri.

**Öncelik sırası:** Çalışan sistem > davranışın korunması > gerçek bugların
düzeltilmesi > lint temizliği > stil/formatlama.

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
11. **Bug fix / özellik işlerinde plan Opus, uygulama Sonnet ile yapılır.**
    Önce Opus modeliyle (ör. `Agent` tool, `model: opus`, `subagent_type:
    Plan`) sorunun kök nedenini ve değişecek dosya/mantığı netleştiren yazılı
    bir plan çıkarılır, kullanıcıya sunulur; onaydan sonra kodu Sonnet yazar.
    Küçük/aşikâr tek satırlık düzeltmeler için (typo, config değeri gibi) bu
    adım zorunlu değil — orantısız olur.
12. **Çapraz değişiklik:** client+server bağlı değiştiğinde (biri diğerini
    gerektiriyorsa) ikisi BİRLİKTE ele alınır — her iki taraf incelenir,
    ilgili test paketleri (`server/tests/`, `client/tests/`) çalıştırılır,
    sonra `farabi.local` deploy edilir. **Son kabul testi her zaman Atakan
    tarafından fiziksel tahtada yapılır** — otomatikleştirilmez/atlanmaz.

**Kurulum biçimi:** systemd servisleri. Docker kullanılmaz — okulda sistemi
devralacak kişi `systemctl status` ile durumu görebilmeli.

## Şu An Yapılmayacaklar

- ⛔ **`/api/idari/*` — KALICI OLARAK İPTAL (2026-08-31).** Endpoint
  yazılmayacak, idari tablo/chunk (`chunk_idari`) tasarımı gündemde değil.
- ⛔ **Yerel STT/TTS (faster-whisper, Piper) — KALICI OLARAK İPTAL
  (2026-08-11).** Ses kalıcı olarak Gemini Live'da (mimari.md §14).

## Ağ Envanteri

Kimlik bilgileri (şifreler) ve tüm MAC adresleri **yalnızca
`network.txt`'te** (gitignore'lu). Bu dosya public GitHub'a gidiyor —
buraya şifre yazılmaz.

Üç ayrı makine sınıfı var:

1. **Vestel akıllı tahtalar** (Pardus ETAP GNU/Linux, hostname
   `vestel<düzey><şube>` deseninde — ör. `vestel9a`, ağ `192.168.23.0/24`,
   VLAN/güvenlik duvarı yok). **Sayım:** ağda 11 fiziksel tahta; **8'inde**
   Farabi client kurulu (aşağıdaki tablo = `config_dagit.sh`'in varsayılan
   hedef listesi), 8'in **7'si** sınıf, 8.'si `fenlab`. Kalan 3 tahta
   (`.234`, `.235`, `.236`) `server/tahtalar.json`'da `tahta-NNN` geçici
   adıyla kayıtlı, sınıfı atanmamış, client kurulu değil. Kurulum tarihleri
   ve ayrıntıları DECISIONS.md'de.

   | Sınıf/Ad | IP             | Hostname  | Yoklama | Farabi client |
   |----------|----------------|-----------|---------|---------------|
   | 9-A      | 192.168.23.245 | vestel9a  | evet (Farabi client venv'ini paylaşır) | evet (pilot; tam klon yapısı `~/farabi/repo`) |
   | 9-B      | 192.168.23.239 | vestel9b  | evet | evet |
   | 10-A     | 192.168.23.242 | vestel10a | evet | evet |
   | 11-A     | 192.168.23.228 | vestel11a | evet | evet |
   | 11-B     | 192.168.23.233 | vestel11b | evet | evet |
   | 12-A     | 192.168.23.226 | vestel12a | evet | evet |
   | 12-B     | 192.168.23.240 | vestel12b | evet | evet |
   | fenlab   | 192.168.23.244 | fenlab    | evet (7 sınıfın rosterı birden; dashboard'da sınıf atanmamış) | evet |

   ⚠️ **fenlab'ın `derslik` değeri `"fenlab"`** — Farabi sınıf düzeyini
   `derslik`ten çıkarıyor (`10-A` → 10. sınıf); `"fenlab"` bir düzeye
   çözülemez, bu yüzden kitap ararken öğretmene sınıfı soracak. Tek bir
   düzeye sabitlenecekse `derslik` değiştirilmeli.

   Donanım: Pardus ETAP 23, Intel i3-2330M (eski mobil işlemci).
   Bağlanma: `server/tahta-ssh.sh <derslik>` (`ogretmen`) ya da
   `--admin <derslik>` (`etapadmin`, sudo). NOPASSWD sudo tahtadan tahtaya
   değişiyor — önce `sudo -n true` ile dene. MAC adresleri ve kimlik
   bilgileri `network.txt`'te (ikincil referans; çelişkide
   `server/tahtalar.json` esas).

2. **Kapıdaki yüz tanıma sistemi** (giriş yoklaması kiosk PC'si,
   `192.168.23.254`, Debian 12) — bu repodaki hiçbir projeye BAĞLI DEĞİL,
   yalnızca envanter notu.

3. **Farabi sunucu** (bu makine, `ata@farabi.local` / `192.168.23.252`,
   Ubuntu 26.04, Ryzen 9 3900X, 2× RTX 3060, 64 GB RAM, sudo NOPASSWD) —
   üç servis burada, tahtalara buradan SSH ile bağlanılıyor.

## RAG Kuralları (kritik)

- Cevap **sadece** retrieval sonucundan üretilir. Serbest üretim yok.
- Ana savunma: skor eşiğin altındaysa LLM'e hiç gitme → "Bu konu ders kitabında
  bulunmuyor."
- Arama **yalnızca kitap filtresiyle** (`kitap_id` WHERE koşulu), **iki
  kaynaktan**: `chunk_egitim` top-20 (`rag.py::_ilk_k_getir`) +
  `chunk_tablo` top-10 (`rag.py::_tablo_getir`), ayrı sorgular. Rerank
  birleşim üzerinde, top-4 seçilir; `ESIK_RERANK` = 0,5. Geri dönüş tek
  satır: `rag.py::TABLO_KAYNAGI = False`. **`chunk_tablo` şu an yalnızca
  `biyoloji-9` için dolu** — yeni kitap eklendiğinde ölçüm (40 soruluk set,
  şu an 38/40) tekrarlanmalı. Ayrıntı `docs/mimari.md` §5.
- **Kazanım filtresi YOK:** `chunk_egitim.kazanim_kod` kolonu DB'de var ama
  hiçbir sorguda okunmuyor. Kazanım bazlı filtre yalnızca gelecek-fazı
  önerisi (mimari.md §12).
- Her cevapta kaynak: `9. Sınıf Biyoloji, s. 84`
- Chunk sayfa sınırını aşmaz.
- LLM sıcaklığı ≤ 0.2, cevap ≤ 3 cümle.
- Ek kontrol: cevapta kaynakta geçmeyen **sayı** varsa gösterme.
  Kelime örtüşme oranı kullanma (doğru parafrazı engeller).

## API Prensibi

**Brain karar verir, Client görüntüler.** Server ham LLM metni döndürmez;
`{status, answer, sources[], latency_ms, request_id}` yapısı döner
(`audio_url` yok — ses Brain'de üretilmiyor). Client metni ayrıştırmaz,
`status`'a göre davranır.

Client↔Server event listesi bağlayıcıdır — değişirse `mimari.md`'yi güncelle.

## Veri Yerleşimi ve İzolasyon

- Dosyalar ikinci diskte: `/mnt/farabi-data/farabi/` (1.8TB) — `kitaplar/`,
  `yks/`, `icerik/{metin,ozet,yks_metin,eslemeler,onbellek,kitaplar.json}`.
  Kod bu yoldan yalnızca `DATA_DIR` sabitiyle haberdar (NAS gelirse tek sabit
  değişir).
- **PostgreSQL** → metadata, hash, sınıf, ders, kazanım, sayfa.
  **pgvector** → chunk + embedding. Dosya içeriği DB'ye gömülmez.
- `chunk_egitim` tek chunk tablosu; `chunk_idari` yok ve olmayacak.
- Tahta token'ı yalnızca `/api/egitim/*` çağırabilir.

## Gizlilik

- **Öğrenci sesi kalıcı olarak Gemini Live'a (Google bulutu) gidiyor** —
  bilinçli karar (2026-08-11, mimari.md §14).
- Fiziksel kamera/webcam yok. Ekran görüntüsü zorunlu bir yetenek ama
  yalnızca `QApplication.primaryScreen().grabWindow(0)` — tahtanın o an
  gösterdiği şey, asla kamera/sınıf/öğrenci. Ayrıntı `client/CLAUDE.md`.
- Ham ses diske yazılmaz — Gemini Live'ın transkripsiyonu client'ta kalır,
  Brain'e yalnızca metin gider.
- Öğrenci kimliği tutulmaz. Anonim "öğrenci sordu".
- **Eğitim İÇERİĞİ (kitap metni, RAG cevabı) dış bulut AI servisine
  gönderilmez** — Brain (Ollama, embedding, reranker, PostgreSQL/pgvector)
  tamamen yerel. Ses bu kuralın dışında. Metin/görsel yardımcı görevler
  (bkz. `server/saglayicilar.py`) bulut sağlayıcılara server üzerinden
  gider; anahtarlar client diskinde durmaz.

## Loglama — iki tablo, karıştırma

- `metrik` → yalnızca süre + durum + skor. İçerik yok. Sınırsız saklanır.
- `soru_log` → soru/cevap metni **yalnızca** şu durumlarda: düşük skorlu `ok`,
  `yetersiz_kaynak`, `sayi_kontrolu_reddi`, `iptal`, `hata`.
  Başarılı+yüksek skorlu cevaplarda metin saklanmaz.
  derste konuşulan şeyler metin olarak tutulur loglamaya dahil edilir.
- `soru_log` **süre sınırı olmadan** tutulur (bilinçli karar, 2026-08-18);
  otomatik silme mekanizması yok ve olmamalı, aksi istenmedikçe.

### Log dosyalarını okuma ilkesi

**Log dosyaları hata/bug avında birincil kanıt — varsayımla debug etme.**

- Ders transkriptleri (`client/logs/ders/*.txt` — tahtanın kendi diskinde,
  SSH gerekir: `server/tahta-ssh.sh <derslik> "cat
  ~/farabi/client/logs/ders/<dosya>.txt"`) derste ne konuşulduğunu, hangi
  tool'un ne zaman çağrıldığını, modelin nerede yanlış yaptığını gösterir.
  Server'a yedeklenen kopyalar `server/yedekler/ders_kaydi/<derslik>/*.txt`
  (doğrudan okunabilir).
- `client/logs/farabi.log` (tahtanın diskinde, rotating) ikincil kanıt —
  bağlantı/reconnect/hata izleri.
- **Server'da dosya bazlı log YOK** — yalnızca `journalctl -u
  farabi-api.service`.
- **Bir log dosyası büyükse (kabaca >1000 satır ya da >200KB), önce
  boyutunu bildir; dosyanın TAMAMINI okumadan önce mutlaka sor.** Hedefli
  arama (`grep`, `tail`, belirli tarih/derslik aralığı) sormadan yapılabilir.

## Okuma

Şunları okuma: `*.pdf`, `data/`, `models/`, `*.onnx`, `venv/`, `__pycache__/`,
`client/config/api_keys.json*`, `server/config/api_keys.json*`,
`/mnt/farabi-data/farabi/` (kitap/YKS PDF'leri ve türetilmiş içerik — telifli/
büyük).
pdf içerikleri sayfa sayfa parcalayıp ekranda gösterebilirsin ders anında 
gemini live bunları okuyabilir.hatta gemini live tablo yorumlara görsel
vision görü yeteneği kazandırabilirsin.

## Diğer dizinler

- `mudur/` — müdür yardımcısının kaynak dosyaları (ders programı, SINIF/
  Excel+PDF). Servis değil; `smssistemi/scripts/sinif_bilgi_ice_aktar.py`
  buradan okur.
- `dogum/` — eski tek dosyalık **Telegram** doğum günü botu. UYKUDA
  (crontab/systemd'de kayıtlı değil, son çalışma 2026-09-20); smssistemi'nin
  Doğum Günleri modülü yerini aldı, kasıtlı mı bilinmiyor.
- `tahtaayar/` — tahtaların OS/oturum ayarlarını (güç düğmesi, uyku, ekran
  karartma) referans duruma getiren ajansız script'ler.
- `docs/superpowers/{specs,plans}/` — superpowers becerilerinin ürettiği
  belgeler buraya yazılır (`<TARİH>-<konu>-design.md`, `<TARİH>-<konu>.md`).

## Araçlar / Eklentiler

- **superpowers** — beceriler kendiliğinden tetiklenir. ⚠️ TDD/worktree
  akışı Kural 11'i (plan Opus → uygulama Sonnet) ve Kural 6'yı GEÇERSİZ
  KILMAZ; çakışırsa bu dosya kazanır.
- **context7** (MCP, `.mcp.json`, anahtarsız düşük kota) — FastAPI/PyQt6
  gibi dış kütüphane API'si için. Farabi'nin KENDİ kodu için değil, onun için
  kodu oku (Kural 4).
- **frontend-design** — kurallar `tahtayoklama/CLAUDE.md`'de.

## Frontend / Dashboard Tasarım Standartları

`tahtayoklama/dashboard/` web arayüzüne (templates + `static/`) dokunmadan
önce `tahtayoklama/CLAUDE.md` → "Frontend / Dashboard Tasarım
Standartları" bölümünü oku. Özet: tasarım sistemi (`pano.css` token'ları,
üç tema, satır içi ikon sprite) dondurulmuş; CDN/yeni kütüphane yok
(Kural 8).
