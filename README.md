# Farabi

Bir okulun akıllı tahta / idari altyapısı için yazılmış, birden fazla
bağımsız servisten oluşan bir monorepo. Merkezinde **Farabi** var: sınıf
akıllı tahtalarında çalışan, Gemini Live ile sesli etkileşim kuran bir ders
asistanı. Etrafında, aynı okulun ihtiyaçlarına göre büyümüş birkaç bağımsız
alt proje bulunuyor.

## Alt projeler

| Klasör | Ne işe yarar |
|---|---|
| [`server/`](server) | Farabi'nin "beyni" — FastAPI: RAG (ders kitabı soru-cevap, pgvector + rerank + LLM), PDF/sayfa içeriği, YKS soru bankası, bulut LLM proxy'si, dosya işleme, ders planı üretimi, tahta kimlik doğrulama. `farabi-api.service` olarak çalışır (:8000). |
| [`client/`](client) | Akıllı tahtalarda çalışan PyQt6 arayüzü — Gemini Live sesli oturumu, ders akışı, ekran görüntüsü/soru okuma. Ağır işlerin hepsi `server/`'da; tahtalar GitHub'dan doğrudan (sparse-checkout ile) çeker. Şu an 8 tahtada kurulu. |
| [`tahtayoklama/`](tahtayoklama) | Öğrenci yoklama sistemi — tahta tarafı + `dashboard/` (öğretmen/idare paneli, canlı uzaktan tahta yönetimi, anlık ekran görüntüsü/önizleme balon pencere, uzaktan yönetim denetim kaydı, sistem durumu). Farabi'den bağımsız, ayrı bir systemd servisi (:8010). |
| [`smssistemi/`](smssistemi) | Okul idaresinin veli/öğrenci/personele toplu/kişiselleştirilmiş SMS göndermesi ve otomatik doğum günü tebrikleri, yoklama SMS'i ve 09:00 ilk ders devamsızlık otomasyonu için web uygulaması — Huawei HiLink modem (Müdür PC köprüsü üzerinden), mesaj düzeltmede yerel Ollama. `farabi-smssistemi.service` (:8020). |
| [`tahtaayar/`](tahtaayar) | Akıllı tahtaların işletim sistemi/oturum ayarlarını (güç, uyku, ekran karartma) referans duruma getiren ajansız script'ler. |
| [`mudur/`](mudur) | Müdür yardımcısının kullandığı araçlar (ders programı kaynağı, sınıf Excel/PDF listeleri). |
| [`dogum/`](dogum) | Eski Telegram doğum günü botu — UYKUDA (servis/cron kaydı yok); yerini smssistemi'nin Doğum Günleri modülü aldı. |
| [`benchmark/`](benchmark) | RAG retrieval/eşik/katman ölçüm harness'ları — üretim koduna karşı veya bağımsız çalışır. |
| [`docs/`](docs) | Tasarım kararları ve uygulama planları. |

Her alt projenin kendi `CLAUDE.md` dosyası var (komutlar, mimari, bilinen
sorunlar) — o klasörde çalışırken önce onu oku.

## Mimari ilkesi

Farabi tarafında (`server/` + `client/`) tek kural şu: **client ince kalır,
ağır iş (RAG, LLM, iş mantığı) sunucuda çalışır.** Diğer alt projeler
(`tahtayoklama`, `smssistemi`) kasıtlı olarak Farabi'den bağımsızdır — kod
paylaşımı yok, her biri kendi veritabanını/kimlik doğrulamasını yönetir.
Tek bilinçli istisna: smssistemi'nin Yoklama SMS sayfası dashboard'un
SQLite veritabanını salt-okunur okur.

Detaylı mimari, geçmiş kararlar ve gerekçeleri için:
- [`CLAUDE.md`](CLAUDE.md) — güncel durum, kurallar, envanter
- [`DECISIONS.md`](DECISIONS.md) — kronolojik karar/bulgu kaydı

## Kurulum biçimi

Docker yok — her servis systemd altında ayrı bir birim ve ayrı venv olarak
çalışır (`farabi-api`, `farabi-yoklama-dashboard`, `farabi-smssistemi`,
`ollama`), sistemi devralacak biri `systemctl status` ile duruma bakabilir.
Servisler birbirine yalnızca HTTP + HMAC ile bağlanır, birleştirilmez.
