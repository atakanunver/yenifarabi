# voice_node — Faz 1b ses düğümü

Pipecat (1.11.0) tabanlı, tahtayla websocket üzerinden konuşan, Brain'e
(`server/ses_cephe.py`, Faz 1a) OpenAI-uyumlu `/v1/chat/completions` ile
bağlanan ayrı bir servis. Plan: `docs/superpowers/plans/2026-09-26-ses-dugumu.md`.
Kod yorumları Türkçe.

## Kurulum ve komutlar

```bash
cd voice_node
export UV_SYSTEM_CERTS=true SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt UV_PROJECT_ENVIRONMENT=venv
uv sync --group dev                     # venv/ oluşturur (İSİM ÖNEMLİ — .gitignore **/venv/ kapsıyor)

# Test (gerçek model YOK, mock):
venv/bin/python -m pytest tests/ -q

# Geliştirmede elle çalıştırma (GPU0'ı koru — nvidia-smi ile önce boş yer kontrol et):
LD_LIBRARY_PATH="$(pwd)/venv/lib/python3.12/site-packages/nvidia/cublas/lib:$(pwd)/venv/lib/python3.12/site-packages/nvidia/cuda_nvrtc/lib" \
CUDA_VISIBLE_DEVICES=0 CUDA_DEVICE_ORDER=PCI_BUS_ID HF_HUB_OFFLINE=1 \
set -a; . config/ses_node.env; set +a
venv/bin/uvicorn app:app --host 127.0.0.1 --port 8030   # testte 127.0.0.1, üretimde 0.0.0.0

# Piper (ayrı proje/venv, GPL izolasyonu):
cd piper_servis && uv sync
venv/bin/python -m piper.http_server -m tr_TR-dfki-medium \
    --data-dir /mnt/farabi-data/farabi/ses/piper --host 127.0.0.1 --port 5050

# Ruff (repo kökünden):
cd /home/ata/farabi && .venv-tools/bin/ruff check voice_node
```

Modeller `/mnt/farabi-data/farabi/ses/` altında (repo dışı, `DATA_DIR`
deseni): `whisper/large-v3-turbo/` (deepdml, MIT), `piper/tr_TR-dfki-medium.onnx{,.json}`
(CC BY-NC-SA 4.0). `nvidia-cublas-cu12` + `nvidia-cuda-nvrtc-cu12` (ikincisi
plan listesinde AÇIKÇA geçmiyor ama ctranslate2'nin CUDA JIT derlemesi için
zorunlu transitive bağımlılık — cuDNN YOK, gerekmiyor: `ldconfig -p | grep
cudnn` boş, cuBLAS+nvrtc yeterli, 2026-09-26'da GPU0'da doğrulandı).

## Mimari — dosyalar

| Dosya | İş |
|---|---|
| `app.py` | FastAPI: `GET /health`, `WS /ses`; LAN/localhost IP kontrolü (`IZINLI_AGLAR`), tahta anahtarı başlıktan okunur (doğrulanmaz, Brain'e iletilir), Whisper ön-ısıtma (lifespan) |
| `oturum.py` | Tahta başına pipeline: `transport.input() -> BasKonus -> SttPaylasimli -> user_aggregator -> OpenAILLMService -> PiperHttpTTS -> transport.output() -> assistant_aggregator` |
| `serializer.py` | `FrameSerializer`: ikili = PCM16 mono (giriş 16 kHz, çıkış 24 kHz), metin = JSON kontrol paketi |
| `bas_konus.py` | PTT kontrolcüsü — **plan sapması aşağıda** |
| `stt_paylasimli.py` | `WhisperSTTService._load` ezilir — süreç genelinde TEK `WhisperModel` (VRAM tasarrufu, çoklu tahta) |
| `piper_http.py` | İnce Piper HTTP istemcisi — `piper` paketi HİÇ import edilmez (GPL izolasyonu) |
| `araclar.py` | `pdf_sayfa`/`yks_sorulari`/`pencere_kapat` için `register_function` köprüsü (future <-> tahta JSON) |
| `gozlemci.py` | `BaseObserver`: `MetricsFrame`/`TranscriptionFrame` -> journal (İÇERİK YOK, yalnızca süre/uzunluk) + test için board'a `transkript`/`metrik` mesajı |
| `araclar_cli/wav_istemci.py` | Test istemcisi — WAV gönderir, cevabı `.wav`'a yazar, zamanlama JSON'ı basar |

## Tel protokolü (websocket `/ses`)

Bağlantı: `ws://<host>:8030/ses?kip=<ogretmenli|ogretmensiz|talimat>&ders=<ops>`,
başlık `X-Farabi-Board-Key: <tahta anahtarı>` (ses düğümü DOĞRULAMAZ, Brain'e
`default_headers` ile iletir — `auth.dogrula_tahta` orada çalışır).

İkili mesaj = ham PCM16 mono (giriş 16 kHz mikrofon; çıkış 24 kHz Piper).

Metin mesajı = tek satır JSON. Tahta -> düğüm:
```
{"tip": "ptt_basla"}
{"tip": "ptt_bitir"}
{"tip": "arac_sonuc", "id": "<call_id>", "sonuc": {...}}
{"tip": "baglam", "kip": "...", "ders": "..."}   # kip/ders güncelleme
```
Düğüm -> tahta:
```
{"tip": "arac_cagri", "id": "...", "ad": "pdf_sayfa|yks_sorulari|pencere_kapat", "arg": {...}}
{"tip": "transkript", "metin": "..."}            # yalnızca test/gözlem, üretim istemcisi yok sayabilir
{"tip": "metrik", "asama": "stt|llm_ilk_icerik|tts_ilk_ses", "ms": 123}
{"tip": "hata", "mesaj": "..."}
```
Bilinmeyen `tip` HER İKİ yönde de sessizce yok sayılır (ileri uyumluluk).

## Plan sapmaları (raporda da işaretli)

1. **Bas-konuş: buffer-then-decide, canlı akış DEĞİL.** Plan taslağı
   `ptt_basla` anında `VADUserStartedSpeakingFrame`/`Proposed...` yollayıp
   sesi CANLI akıtmayı ima ediyordu. Kaynak incelemesi
   (`turns/user_stop/external_user_turn_stop_strategy.py`,
   `services/stt_service.py::SegmentedSTTService`) şunu gösterdi:
   `ExternalUserTurnStopStrategy(wait_for_transcript=True)` bir
   `TranscriptionFrame` gelmeden turu KAPATMAZ — boş basışta (STT'ye ses
   gitmezse) transkript hiç gelmez, tur SONSUZA kadar açık kalır. Çözüm:
   `BasKonus` basılı tutulan TÜM sesi kendi tamponunda toplar, `ptt_bitir`de
   (serializer'ın ~200ms geciktirdiği kontrol mesajı) Silero VAD ile TEK
   seferlik bir kontrol yapar — konuşma yoksa hiçbir şey pipeline'a
   girmez (tur hiç açılmaz, kilitlenme riski yok); varsa VAD/Proposed
   Started + TEK büyük ses çerçevesi + VAD/Proposed Stopped tek seferde
   pushlanır (gecikme maliyeti yok, segmented STT zaten yalnızca Stop
   anında çalışıyordu). Bkz. `bas_konus.py` docstring'i.
2. **`PipelineWorker(enable_rtvi=False)` ŞART, varsayılan `True`.**
   Test sırasında keşfedildi: varsayılan `PipelineWorker`, pipeline'ın EN
   BAŞINA kendi `RTVIProcessor`'ını ekleyip bizim JSON kontrol
   mesajlarımızı ("ptt_basla" vb.) "Ignoring not RTVI message" diyerek
   YUTUYORDU. Plan zaten `enable_rtvi=False` istiyordu ama parametrenin
   NEREYE verileceği (transport değil, `PipelineWorker`) ilk yazımda
   atlanmıştı — `oturum.py`'de düzeltildi, e2e testiyle doğrulandı.
3. **Araç zaman aşımı çifte korumalı.** `register_function(timeout_secs=...)`
   pipecat'in KENDİ zaman aşımı mekanizması; `araclar.py` bunun ÜZERİNE
   kendi `asyncio.wait_for`'ını (plan değeri - 0.5 sn) ekliyor, böylece
   Türkçe "tahta yanıt vermedi" mesajı HER ZAMAN pipecat'in kendi (farklı
   biçimli) zaman aşımından ÖNCE üretiliyor — yarış riski yok.

## Bilinen sınırlar / açık işler

- `wav_istemci.py`'nin `arac_cagri` cevapları SİMÜLE — gerçek tahta
  davranışını (Faz 1c, PyQt istemci) yansıtmaz.
- RNNoise pilotta kapalı (`RNNOISE=0`), A/B ölçümü sonraki adım.
- Ses metriklerinin (`stt_ms` vb.) `metrik` DB tablosuna nasıl yazılacağı
  (dashboard sayımını bozmadan) HENÜZ KARARLAŞTIRILMADI — pilotta yalnızca
  journal + test-amaçlı `{"tip":"metrik"}` board mesajı.
