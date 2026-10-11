# Faz 1b — Pipecat ses düğümü (`voice_node/`), tahtasız test

> ⛔ **KALICI OLARAK İPTAL (2026-09-28).** Yerel sese geçiş projesi donanım
> altyapısı yetersiz olduğu için iptal edildi; ses Gemini Live'da kalır. Bu
> dosya yalnızca arşivdir — uygulanmaz, canlıya alınmaz. Ayrıntı:
> `DECISIONS.md` 2026-09-28.

Dal: `yerel-ses-pipecat` · Plan: Opus · Uygulama: Sonnet (Kural 11)
Önceki faz: `2026-09-25-ses-cephe.md` (Brain `/v1/*`, commit `e04e279`).
Kaynak araştırması: pipecat-ai 1.11.0 wheel kaynağı üzerinden (2026-09-25);
aşağıdaki dosya:satır referansları o sürüme aittir — sürüm `==` ile pinli
kalmalı.

## Onaylı kararlar (2026-09-26)

| Konu | Karar |
|---|---|
| Taşıma | `FastAPIWebsocketTransport` + özel `FrameSerializer`: ikili mesaj = PCM16 mono (giriş 16 kHz, çıkış 24 kHz), metin mesajı = JSON kontrol. Tahtaya yeni paket YOK (9-A client venv'inde `websockets`, `sounddevice`, `numpy` var) |
| RTVI | `enable_rtvi=False` — RTVI dışı mesajları yutuyor (`processors/frameworks/rtvi/processor.py:288-294`) |
| Tur yönetimi | Bas-konuş. `ExternalUserTurnStrategies(enable_interruptions=False)` + `ExternalUserTurnStopStrategy(wait_for_transcript=True)`; aggregator'a `vad_analyzer=None`. Stratejiler AÇIKÇA verilir — verilmezse `LocalSmartTurnAnalyzerV3` sessizce devreye giriyor (`turns/user_turn_strategies.py:45-53`) |
| Silero | Yalnızca boş-basış filtresi: `ptt_bitir`'de segmentte konuşma yoksa STT'ye gönderme |
| RNNoise | Pilotta KAPALI (`RNNOISE=0`), `[rnnoise]` extra'sı kurulmaz; A/B ölçümü sonraki adım |
| STT | faster-whisper large-v3-turbo (`deepdml/faster-whisper-large-v3-turbo-ct2`, MIT), `int8_float16`, GPU0; yedek `Systran/faster-whisper-small` int8 CPU |
| TTS | Piper ayrı servis, `tr_TR-dfki-medium` (CC BY-NC-SA 4.0, ticari olmayan kullanım olarak kabul — DECISIONS.md 2026-09-25) |
| Metrikler | Pilotta yalnızca journal |
| Tahta kimliği | Tahta anahtarı websocket bağlantı başlığında (`X-Farabi-Board-Key`), ses düğümü doğrulamaz — Brain'e iletir (`dogrula_tahta`); ses düğümü websocket'i yalnızca `192.168.23.0/24` + `127.0.0.1` |

## Ön koşullar (KULLANICI adımları — kod başlamadan)

1. **Kural 8 onayı** — aşağıdaki "Yeni bileşenler" listesinin tamamı.
2. **Faz 1a canlıya alma** (ders dışı saat): `server/config/ses.env`
   (`FARABI_SES_TOKEN=<rastgele>`), `sudo systemctl edit farabi-api.service`
   → `EnvironmentFile=-/home/ata/farabi/server/config/ses.env`, metrik
   trafiği kontrolü, import ön-kontrolü, restart, `/health` + `/ready`.
   Gerekçe: ses düğümü testleri canlı Brain'e (8000) bağlanır; ayrı bir dev
   Brain GPU0'a embed+reranker'ın ikinci kopyasını (+4,5 GB) + Whisper'ı
   yükler, kart ~11/12 GB'a çıkar ve yük testi yapay OOM ölçer.
3. **Test tahta anahtarı:** `server/config/api_keys.json::board_keys`'e
   `"ses-test": "<rastgele>"` (auth dosyayı her istekte okur, restart
   gerekmez); aynı değer `voice_node/config/ses_node.env::TEST_TAHTA_ANAHTARI`.
   Ajan `api_keys.json`'ı OKUMAZ/YAZMAZ.
4. **WAV kayıtları:** `voice_node/tests/audio/` şablonundaki 10 Türkçe soru.

## Yeni bileşenler (Kural 8 onay listesi)

Servisler: `farabi-ses.service` (port 8030, LAN — websocket),
`farabi-piper.service` (127.0.0.1:5050).

Ses düğümü venv'i (`voice_node/venv`, uv, CPython 3.12 — `uv python install
3.12` python-build-standalone'u GitHub'dan indirir):
pipecat-ai[whisper,websocket] 1.11.0 (BSD-2) · faster-whisper 1.2.1 (MIT) ·
ctranslate2 4.8.2 (MIT) · onnxruntime 1.24.4 (MIT) · nvidia-cublas-cu12
12.8.5.5 (NVIDIA tescilli; ctranslate2 `libcublas.so.12` istiyor, sistemde
yok) · uvicorn 0.54.0 (BSD-3) · aiohttp (Apache-2) · geçişli: fastapi,
openai, huggingface-hub, tokenizers, av (FFmpeg LGPL), numba, nltk, soxr
(LGPL), resampy, soundfile (libsndfile LGPL), loudness, num2words (LGPL),
protobuf. `uv.lock` commit edilir.

Piper venv'i (`voice_node/piper_servis/venv`, ayrı uv projesi):
piper-tts[http] 1.8.0 (GPL-3.0-or-later, espeak-ng GPL) + flask (BSD-3).

Modeller (`/mnt/farabi-data/farabi/ses/` altında — `DATA_DIR` deseni,
ikinci disk): `whisper/large-v3-turbo/` (deepdml, MIT), `whisper/small/`
(Systran, MIT), `piper/tr_TR-dfki-medium.onnx{,.json}` (CC BY-NC-SA 4.0),
`nltk_data/tokenizers/punkt_tab` (Apache-2). Silero VAD pipecat wheel'inin
içinde.

İndirme ortamı: `UV_SYSTEM_CERTS=true`, `SSL_CERT_FILE=/etc/ssl/certs/
ca-certificates.crt` (MEB kökleri sistem deposunda). 2026-09-25 gözlemi:
PyPI/HF/GitHub proxy'siz erişilebiliyor.

## Dosya düzeni

```
voice_node/
  pyproject.toml, uv.lock, CLAUDE.md, README yok
  config/ses_node.env.example   # FARABI_SES_TOKEN, BRAIN_URL, PIPER_URL,
                                # WHISPER_MODEL_DIR, WHISPER_DEVICE, WHISPER_COMPUTE,
                                # SES_PORT, IZINLI_AGLAR, RNNOISE, TEST_TAHTA_ANAHTARI
  app.py            # FastAPI: GET /health, WS /ses; ağ kontrolü; başlıktan tahta anahtarı
  oturum.py         # tahta başına pipeline
  serializer.py     # PCM16 ikili + JSON kontrol (FrameSerializer; arayüz serializers/base_serializer.py)
  bas_konus.py      # PTT → VAD/Proposed çerçeveleri, kuyruk gecikmesi, Silero boş-basış filtresi
  araclar.py        # pdf_sayfa/yks_sorulari/pencere_kapat handler'ları + future köprüsü
  stt_paylasimli.py # WhisperSTTService alt sınıfı, süreç genelinde TEK WhisperModel
  piper_http.py     # piper import ETMEYEN ince TTSService (POST {base}/synthesize, WAV → resample)
  gozlemci.py       # MetricsFrame → journal (stt_ms, llm_ilk_icerik_ms, tts_ilk_ses_ms, uçtan uca)
  araclar_cli/wav_istemci.py  # test istemcisi: WAV'ı gerçek protokolle gönderir, cevabı .wav'a yazar
  tests/            # pytest, mock
  tests/audio/      # SORULAR.md şablonu (dosya adı → beklenen metin); WAV'lar kullanıcıdan
  piper_servis/pyproject.toml, uv.lock
deploy/ (ya da voice_node/systemd/)  farabi-ses.service, farabi-piper.service (metin; kurulum kullanıcı adımı)
```

## Pipeline (tahta oturumu başına)

`transport.input()` → `BasKonus` → `SttPaylasimli` → `user_aggregator` →
`OpenAILLMService` → `PiperHttpTTS` → `transport.output()` →
`assistant_aggregator`. `PipelineParams(enable_metrics=True,
enable_usage_metrics=True)`, `enable_rtvi=False`.

- **LLM:** oturum başına ayrı `OpenAILLMService(base_url=BRAIN_URL + "/v1",
  api_key=FARABI_SES_TOKEN, default_headers={"X-Farabi-Board-Key": <ws
  başlığından>}, settings=Settings(model="farabi-brain", extra={"metadata":
  {"kip": str, "ders": str, "derslik": str}}))` (`services/openai/
  base_llm.py:150-165, 276-287, 383`). Bağlama araç EKLENMEZ. Kip/ders
  değişince `LLMUpdateSettingsFrame`. Metadata değerleri STRING.
- **Tahta araçları:** `llm.register_function(ad, handler, timeout_secs=...)`
  üç araç için (zaman aşımları `client/actions/kayit.py` ile aynı: pdf_sayfa
  10, yks_sorulari 15, pencere_kapat 8). Handler: `OutputTransportMessage
  UrgentFrame({"tip":"arac_cagri","id","ad","arg"})` → oturumun
  `asyncio.Future`'ı → tahtanın `{"tip":"arac_sonuc","id","sonuc"}` mesajı →
  `params.result_callback({...})` — SÖZLÜK döndür. Zaman aşımında
  `{"hata":"tahta yanıt vermedi"}`. Handler'lar senkron kalır (asenkron
  araçlar "developer" rolü ekliyor, `llm_service.py:643-646`).
- **Bas-konuş:** `ptt_basla` → aşağı akışa `VADUserStartedSpeakingFrame` +
  `ProposedUserStartedSpeakingFrame`; `ptt_bitir` → sunucu ~200 ms bekler
  (kontrol mesajı ses kuyruğunu geçebiliyor: `transports/base_input.py:
  197-204` vs `websocket/fastapi.py:386`), sonra Stopped çerçeveleri. Tuş
  basılı değilken gelen ses düşürülür. Bot konuşurken giriş susturulur
  (`AlwaysUserMuteStrategy` + `FunctionCallUserMuteStrategy`).
- **STT:** `WhisperSTTService` her örnekte modeli yeniden yüklüyor
  (`services/whisper/stt.py:316, 349`) → alt sınıf `_load`'u ezer, süreç
  genelinde tek `WhisperModel(model_dir, device, compute_type,
  num_workers=2)`; açılışta ön-ısıtma (1 sn sessizlik çözümlenir).
  `model` = yerel dizin yolu (`download_root`/`local_files_only`
  iletilmiyor). `language=Language.TR`.
- **TTS:** `piper_http.py`, `PiperHttpTTSService.run_tts`'in eşdeğeri
  (`services/piper/tts.py:210-340`) ama `from piper import ...` YOK. URL
  `http://127.0.0.1:5050/synthesize`. Açılışta ön-ısıtma cümlesi.
- **Loglama:** `logger.remove(); logger.add(sys.stderr, level="INFO")` —
  DEBUG'da her transkript ve tüm LLM bağlamı journal'a düşüyor
  (`stt.py:452`, `base_llm.py:324`). Gizlilik.
- **Hata/düşme:** Brain erişilemez → oturum kısa sesli uyarı ("Şu an
  cevap veremiyorum.") ve devam; ses düğümü çökerse tahta tarafı (Faz 1c)
  butonu griye alır. Ses düğümü kendi başına Brain'i ya da GPU'yu
  beklerken bloke olmaz.

## systemd taslakları (kurulum kullanıcı adımı)

`farabi-ses.service`: `User=ata`, `WorkingDirectory=/home/ata/farabi/
voice_node`, `EnvironmentFile=/home/ata/farabi/voice_node/config/
ses_node.env`, `CUDA_VISIBLE_DEVICES=0`, `CUDA_DEVICE_ORDER=PCI_BUS_ID`,
`HF_HUB_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1`, `NLTK_DATA=/mnt/
farabi-data/farabi/ses/nltk_data`, `LOGURU_LEVEL=INFO`,
`LD_LIBRARY_PATH=<venv>/lib/python3.12/site-packages/nvidia/cublas/lib`,
`ExecStart=<venv>/bin/uvicorn app:app --host 0.0.0.0 --port 8030`,
`Nice=5`, `CPUQuota=600%`, `MemoryMax=6G`, `Restart=on-failure`,
`RestartSec=5`, `After=farabi-api.service farabi-piper.service`.
`farabi-piper.service`: `ExecStart=<piper venv>/bin/python -m
piper.http_server -m tr_TR-dfki-medium --data-dir /mnt/farabi-data/farabi/
ses/piper --host 127.0.0.1 --port 5050` (`--host` varsayılanı 0.0.0.0 ve
`POST /download` var — 127.0.0.1 ŞART), `OMP_NUM_THREADS=4`, `Nice=5`,
`Restart=on-failure`.

## Testler

1. **Mock (pytest, `voice_node/tests/`):** serializer (PCM ↔ frame, JSON
   kontrol); bas-konuş çerçeve sırası ve 200 ms gecikme; boş-basış filtresi;
   araç köprüsü (future çözülür / zaman aşımı); ağ kısıtı (LAN dışı red);
   sahte SSE Brain ile uçtan uca (sahte STT/TTS) — `tool_calls` → tahtaya
   JSON → sonuç → ikinci tur.
2. **WAV seti:** `tests/audio/SORULAR.md` (10 soru: 6 bilgi sorusu, 1 konu
   anlatımı, 1 sayfa açma, 1 çıkmış soru, 1 sohbet). `wav_istemci.py` ile
   her biri için: STT metni ve doğruluğu (kelime hata oranı), `stt_ms`,
   Brain ilk içerik, `tts_ilk_ses_ms`, uçtan uca — tablo.
3. **Yeni araç-seçimi seti:** Faz 1a'daki 20/20 aynı set üzerinde ayarla
   ölçüldüğü için iyimser — `server/tests/ses_degerlendirme.py`'ye
   dokunmadan, **daha önce görülmemiş** 20 istemlik ikinci set (persona
   değiştirilmeden) → kapı yine ≥ 19/20.
4. **YÜK TESTİ (kritik):** ses düğümü art arda 5 WAV işlerken aynı anda
   Brain'e `/v1` üzerinden 5 `kitap_sorusu` → Brain RAG süresinin (metrik
   `toplam_ms`) yüksüz tabana göre % artışı; `nvidia-smi` GPU0/GPU1 tepe
   (0,25 sn örnekleme); OOM var mı; `ollama ps` 100% GPU 8192 kalıyor mu.
   **Karar kuralı:** Brain yavaşlaması > %20 ya da OOM → STT CPU'ya (small
   int8) iner, test tekrarlanır.
5. **Model VRAM ölçümü:** large-v3-turbo int8_float16 yüklüyken GPU0 kullanımı.

## Bitiş raporu

Gecikme tablosu, VRAM/CPU tepe değerleri, Brain üzerindeki etki yüzdesi,
yeni araç-seçimi seti skoru, STT doğruluğu, açık kalanlar, kullanıcının
manuel kontrol listesi (servis kurulumu + WAV testi). DUR — Faz 1c'ye onaysız
geçilmez.

## Doğrulanmamış riskler (uygulamada ilk iş)

- Sürücü 595 / CUDA 13.2 ile ctranslate2'nin CUDA 12 cuBLAS'ı birlikte
  çalışıyor mu; cuDNN gerçekten gereksiz mi — ilk adım: yalnız STT'yi
  yükleyip 1 WAV çözümle.
- Piper'ın Flask geliştirme sunucusunun eşzamanlı yük davranışı.
- 9-A'nın ses çıkışı `auto_null` (Faz 1c'de).
