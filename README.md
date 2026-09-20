# Farabi

Bir okulun akıllı tahta / idari altyapısı için yazılmış, birden fazla
bağımsız servisten oluşan bir monorepo. Merkezinde **Farabi** var: sınıf
akıllı tahtalarında çalışan, Gemini Live ile sesli etkileşim kuran bir ders
asistanı. Etrafında, aynı okulun ihtiyaçlarına göre büyümüş birkaç bağımsız
alt proje bulunuyor.

## Alt projeler

| Klasör | Ne işe yarar |
|---|---|
| [`server/`](server) | Farabi'nin "beyni" — FastAPI: RAG (ders kitabı soru-cevap, pgvector + rerank + LLM), PDF/sayfa içeriği, YKS soru bankası, bulut LLM proxy'si, dosya işleme. `farabi-api.service` olarak çalışır. |
| [`client/`](client) | Akıllı tahtalarda çalışan PyQt6 arayüzü — Gemini Live sesli oturumu, ders akışı, ekran görüntüsü/soru okuma. GitHub'dan doğrudan (sparse-checkout ile) çekilip tahtalara dağıtılır. |
| [`tahtayoklama/`](tahtayoklama) | Öğrenci yoklama sistemi — tahta tarafı + `dashboard/` (öğretmen/idare paneli, uzaktan tahta yönetimi, sistem durumu). Farabi'den bağımsız, ayrı bir systemd servisi. |
| [`smssistemi/`](smssistemi) | Okul idaresinin velilere toplu/kişiselleştirilmiş SMS göndermesi için web uygulaması — Huawei HiLink modem üzerinden, Ollama destekli mesaj düzeltme. |
| [`tahtaayar/`](tahtaayar) | Akıllı tahtaların işletim sistemi/oturum ayarlarını (güç, uyku, ekran karartma) referans duruma getiren ajansız script'ler. |
| [`mudur/`](mudur) | Müdür yardımcısının kullandığı araçlar (ör. ders programı kaynağı). |
| [`benchmark/`](benchmark) | RAG retrieval/eşik/katman ölçüm harness'ları — üretim koduna karşı veya bağımsız çalışır. |
| [`docs/`](docs) | Tasarım kararları ve uygulama planları. |

Her alt projenin kendi `CLAUDE.md` dosyası var (komutlar, mimari, bilinen
sorunlar) — o klasörde çalışırken önce onu oku.

## Mimari ilkesi

Farabi tarafında (`server/` + `client/`) tek kural şu: **client ince kalır,
ağır iş (RAG, LLM, iş mantığı) sunucuda çalışır.** Diğer alt projeler
(`tahtayoklama`, `smssistemi`) kasıtlı olarak Farabi'den bağımsızdır — kod
paylaşımı yok, her biri kendi veritabanını/kimlik doğrulamasını yönetir.

Detaylı mimari, geçmiş kararlar ve gerekçeleri için:
- [`CLAUDE.md`](CLAUDE.md) — güncel durum, kurallar, envanter
- [`DECISIONS.md`](DECISIONS.md) — kronolojik karar/bulgu kaydı

## Kurulum biçimi

Docker yok — her servis systemd altında ayrı bir birim olarak çalışır,
sistemi devralacak biri `systemctl status` ile duruma bakabilir.
