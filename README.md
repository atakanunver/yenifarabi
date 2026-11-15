# Farabi

Bir okulun akıllı tahta / idari altyapısı için yazılmış, birden fazla
bağımsız servisten oluşan bir monorepo. Merkezinde **Farabi** var: sınıf
akıllı tahtalarında çalışan, Gemini Live ile sesli etkileşim kuran bir ders
asistanı. Etrafında, aynı okulun ihtiyaçlarına göre büyümüş birkaç bağımsız
alt proje bulunuyor.

## Alt projeler (bu depoda)

| Klasör | Ne işe yarar | Servis / port |
|---|---|---|
| [`server/`](server) | Farabi'nin "beyni" — FastAPI: kitap/PDF sayfa içeriği, YKS soru bankası, bulut LLM proxy'si, dosya işleme, ders planı üretimi, tahta kimlik doğrulama, ders görsel arşivi. Ders kitabı vektör araması (RAG) 2026-10-31'de kalıcı olarak kapatıldı. | `farabi-api` :8000 |
| [`client/`](client) | Akıllı tahtalarda çalışan ince PyQt6 arayüzü — tek ses yolu Gemini Live, ders akışı, ekran görüntüsü/soru okuma. Ağır işler `server/`'da; tahtalar kodu GitHub'dan doğrudan (sparse-checkout ile) çeker. | tahtada uygulama |
| [`tahtayoklama/`](tahtayoklama) | Tahtadaki dokunmatik yoklama arayüzü + `dashboard/` yönetim paneli: yoklama, canlı uzaktan tahta yönetimi, ekran önizleme, servisler, sistem durumu, kameralar, acil durum. Farabi'den bağımsız. | `farabi-yoklama-dashboard` :80 |
| [`smssistemi/`](smssistemi) | Veli/öğrenci/personele toplu ve kişiselleştirilmiş SMS, doğum günü tebrikleri, yoklama ve devamsızlık SMS otomasyonu (Huawei HiLink modem). | `farabi-smssistemi` :8020 |
| [`okul/`](okul) | Dijital okul portalı (ŞMUAL) — öğrenci/veli/öğretmen/yönetici rolleri, duyuru, ödev/test, devamsızlık, anket, Bilgi Arenası, kişisel gelişim, sohbet odası, Web Push; mobil PWA. Dışarıya Cloudflare Tunnel ile açılır. | `farabi-okul` :9090 |
| [`arenasinif/`](arenasinif) | Sınıf Arenası: tahtada oynanan yarışma oyunları (Düello, HexaFetih); tamamen yerel çalışır. | `sinif-arena` :8030 |
| [`anythingllm/`](anythingllm) | **Atos** (AnythingLLM) kurulum betiği ve özel ajan yetenekleri (okul verisi SQL sorgusu, tablo dosyası, onaylı SMS). Uygulamanın kendisi depoda değildir. | `pm2-anythingllm` :8010 |
| [`soruhavuzu/`](soruhavuzu) | Oyunlar ve okul portalı için hazır soru + orijinal görsel arşivi (PostgreSQL). Otomatik LLM soru üretimi 2026-11-07'de kapatıldı; öğretmen katkısı zamanlayıcıyla alınır. | zamanlayıcı |
| [`osym/`](osym) | ÖSYM/YKS sonuç raporu yükleyici ve analiz (PostgreSQL). | elle |
| [`tahtaayar/`](tahtaayar) | Tahtaların işletim sistemi/oturum ayarlarını (güç, uyku, ekran karartma) referans duruma getiren betikler. | elle |
| [`kiosk/`](kiosk) | Giriş kiosku dijital pano yönetim paneli (`okul_panel.py`). | kiosk makinesinde |
| [`mudur/`](mudur) | Müdür yardımcısının yardımcı betikleri. Ders programının tek kaynağı artık okul veritabanıdır; buradaki ders programı dosyaları eskidir. | — |
| [`kazanimtest/`](kazanimtest) | Haftanın kazanımı testi (Google Form). **Kalıcı olarak kapatıldı** (2026-10-24); kod ve veriler duruyor. | — |
| [`benchmark/`](benchmark) | Eski RAG ölçüm araçları ve kitap/tablo yükleyicileri. Bazı betikler üretim veritabanına yazar. | elle |
| [`docs/`](docs) | Mimari, runbook, tasarım ve uygulama planları. 2026-10-29 tarihli toplu belge seti doğrulanmamış LLM üretimidir; kaynak sayılmaz. | — |
| [`_arsiv/`](_arsiv) | Eski Open WebUI araçları ve teması, eski doğum günü botu, eski planlar. Yalnız okuma. | — |

## Ayrı depolar ve izlenmeyen dizinler

Aynı sunucuda bu klasörün altında çalışan ama bu depoda izlenmeyen projeler:

| Dizin | Ne işe yarar | Servis / port |
|---|---|---|
| `kelebek/` | Ortak sınav salon dağıtımı | `farabi-kelebek` :8050 |
| `kameralar/` | Güvenlik kamerası ızgarası (RTSP → mediamtx WebRTC) ve hareket algılama | `farabi-kameralar`, `farabi-hareket` :8889 |
| `tahtaatlasfarabi/` | Farabi Atlas: yerel harita/küre laboratuvarı ve beş sınıf oyunu (ayrı public depo `atakanunver/farabi-atlas`) | `farabi-atlas` :8099 |
| `okul3d/` | Okul binasının 3D dijital ikizi (ayrı özel depo) | `farabi-okul3d` :8095, :8096 |
| `progmatik/` | Ders programı planlayıcı, OR-Tools CP-SAT (ayrı özel depo) | `progmatik` :8060 |
| `tahtamasaustuduzeni/` | Tahta masaüstü kısayollarının gece bakımı | cron |

## Mimari ilkesi

Farabi tarafında (`server/` + `client/`) tek kural şu: **client ince kalır,
ağır iş (LLM, içerik, iş mantığı) sunucuda çalışır.** Ses tek yoldan, tahtada
tutulan Gemini Live oturumuyla gider. Diğer alt projeler kasıtlı olarak
Farabi'den bağımsızdır — kod paylaşımı yok, her biri kendi veritabanını ve
kimlik doğrulamasını yönetir. Tek bilinçli istisna: smssistemi'nin Yoklama SMS
sayfası dashboard'un SQLite veritabanını salt-okunur okur.

Yerel LLM: Ollama'da tek model `qwen3.8:27b`; istemciler modeli `farabi`
takma adıyla ister, model değişince kod değişmez.

Ayrıntı için:
- [`AGENTS.md`](AGENTS.md) — güncel durum, kurallar, servis tablosu (`CLAUDE.md` ve `GEMINI.md` buna sembolik bağdır)
- [`DECISIONS.md`](DECISIONS.md) — kronolojik karar/bulgu kaydı
- Her alt projenin kendi `AGENTS.md` dosyası (komutlar, mimari, bilinen sorunlar) — o klasörde çalışırken önce onu oku.

## Kurulum biçimi

Docker yok — her servis systemd altında ayrı bir birim ve ayrı venv olarak
çalışır (`farabi-api`, `farabi-yoklama-dashboard`, `farabi-smssistemi`,
`farabi-okul`, `sinif-arena`, `ollama` ve yukarıdaki ayrı depoların
birimleri); Atos PM2 ile (`pm2-anythingllm`) çalışır. Sistemi devralacak biri
`systemctl status` ile duruma bakabilir. Servisler birbirine yalnızca HTTP +
HMAC/paylaşılan anahtar ile bağlanır, birleştirilmez.
