# Farabi

Sınıf akıllı tahtalarında çalışan sesli ders asistanı.
Detaylı mimari: `@docs/mimari.md` (sadece gerektiğinde oku)

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

(2026-08-11 itibarıyla koddan doğrulandı.)

```
farabi/
├── CLAUDE.md          — bu dosya, günlük kurallar
├── docs/mimari.md     — detaylı mimari (server/veri/RAG tasarımı)
├── client/            — ÇALIŞAN kod, tahta istemcisi (aşağıya bkz.), server'a BAĞLI DEĞİL
├── server/            — ÇALIŞAN prototip (bkz. aşağıdaki "Bilinçli sapma") — FastAPI,
│                         pgvector arama + rerank + eşik + LLM, /api/egitim/question
└── benchmark/         — Faz 0a retrieval/eşik/katman testleri, 13 kitap pgvector'a indekslendi
```

**`client/` — PyQt6 tabanlı tahta istemcisi, sunucusuz çalışıyor.**
Detaylar `client/CLAUDE.md`'de (82K, koddan doğrulanmış); özet:

- `main.py` — `FarabiLive`: Gemini Live oturumu, araç çağrı dağıtımı, ders açılışı
- `ui.py` — `FarabiUI`/`MainWindow`: PyQt6 HUD; `main.py` bunu import eder, tersi olmaz
- `core/` — motor/altyapı: `ders_motoru.py` (ders akışı), `olaylar.py` (event bus),
  `program.py` (ders programı), `zil.py` (zil senkronizasyonu),
  `saglayicilar.py` (Gemini DIŞI 6 sağlayıcılı metin/görsel havuzu — STT/TTS
  adaptörü DEĞİL, ses tamamen Gemini Live içinde), `anahtar.py` (yalnızca
  Gemini anahtar havuzu/rotasyon), `transcript.py` (yalnızca metin, KVKK notlu),
  `tahta.py`, `modeller.py`, `logger.py`
- `actions/` — modelin çağırdığı araçlar, tek kaynak `kayit.py` (registry).
  Kamera/ekran yakalama (`screen_processor.py`) 2026-08-09'da tamamen
  kaldırıldı — kullanılmıyor, `Gizlilik` kuralına aykırıydı.
- `tools/` — çevrimdışı içerik hazırlama (kitap/YKS PDF → JSON), `dogrula.py`
  (ücretsiz doğrulama kapısı), `mikrofon_test.py`
- `tests/` — pytest, ağ/model çağrısı yok
- `config/` — gerçek JSON'lar gitignore'lu, `.example.json` şablonları committed
- `memory/`, `planlar/` — koda BAĞLI DEĞİL, ölü/arşiv (silme, ama yeniden
  bağlama da — `client/CLAUDE.md`'de gerekçesi var)
- `kitaplar/`, `YKS/` — PDF bırakma dizinleri, gitignore'lu

**`server/`** — FastAPI prototip, Faz 0a kapısı tam kapanmadan erken başlatıldı
(bkz. "Bilinçli sapma", aşağıda). `main.py`/`rag.py`/`db.py` — `/health`,
`/ready`, `POST /api/egitim/question`. Ollama (qwen2.5:14b) + embedding/reranker
GPU'lu çalışıyor. Client'a hiç bağlı değil.

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
>   da görünüyor). "Kaç kart aktif" sorusu bu noktada AÇIK — yalnızca sürücü
>   kuruldu, GPU'ları hangi servisin/kaç tanesinin kullanacağı ayrı bir karar.
> - **Ollama** kullanıcının açık isteğiyle kuruldu — amaç Faz 1'deki Brain'i
>   önceden kurmak DEĞİL, `benchmark/soru_taslak.py` gibi çevrimdışı içerik
>   araçlarının bulut sağlayıcı kotalarına (deepseek/mistral/nvidia kesintileri,
>   bkz. `core/saglayicilar.py`) bağımlılığını azaltmak.
>
> **İkinci sapma (2026-08-10/11):** Yukarıdaki maddenin "server iskeleti yok"
> kısmı artık geçerli değil — kullanıcının açık kararıyla `server/` iskeleti
> Faz 0a kapısı tam kapanmadan (B grubu sorusu o an 12/15) kuruldu. Gerekçe ve
> detaylar `docs/mimari.md` §15'te ("Neden server iskeleti bekliyor" altındaki
> not). Kısa özet: eşik+LLM katmanı birlikte grup C'de %94 doğru çıkmıştı,
> yöntemin çalıştığına dair yeterli kanıt vardı. `/api/idari/*` hâlâ
> yazılmadı, hâlâ Faz 4'e kadar yazılmayacak — bu kısıt değişmedi.

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
`{status, answer, sources[], audio_url, latency_ms}` yapısı döner.
Client metni ayrıştırmaz, `status`'a göre davranır.

Client↔Server event listesi bağlayıcıdır — `mimari.md` §10. Protokolü genişletmeden
önce dokümanı güncelle.

## Veri Yerleşimi

- **NAS** → dosyanın kendisi
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

> **Ayrı, hâlâ açık bir konu:** `client/`'ın metin/görsel görevleri
> (`core/saglayicilar.py` — Groq/Mistral/DeepSeek/OpenRouter/NVIDIA NIM) hâlâ
> bulut sağlayıcılara gidiyor. Bu, SES kararından bağımsız — istenirse ileride
> yerel qwen'e taşınabilir (zaten `soru_taslak`/`kitap_ozet` zincirlerinde son
> çare olarak ekli), ama bugün karara bağlanmadı.

## Loglama — iki tablo, karıştırma

- `metrik` → yalnızca süre + durum + skor. İçerik yok. Sınırsız saklanır.
- `soru_log` → soru/cevap metni **yalnızca** şu durumlarda: düşük skorlu `ok`,
  `yetersiz_kaynak`, `sayi_kontrolu_reddi`, `iptal`, `hata`.
  Başarılı+yüksek skorlu cevaplarda metin saklanmaz. 90 gün sonra silinir.

## Okuma

Şunları okuma: `*.pdf`, `kitaplar/`, `YKS/`, `data/`, `models/`, `*.onnx`,
`venv/`, `__pycache__/`, `client/icerik/` (üretilen önbellek, `eslemeler/`
hariç), `client/logs/`, `client/config/api_keys.json*`
