# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Kapsam:** yalnızca `server/` — Farabi "Brain" (`farabi-api.service`,
FastAPI, port 8000). Mimari, kurallar, gizlilik ve RAG kuralları kök
`/home/ata/farabi/CLAUDE.md`'de; çelişkide kök kazanır. Tarihli gerekçeler
`DECISIONS.md`'de.

## Komutlar

```bash
venv/bin/uvicorn main:app --reload --port 8000             # geliştirmede elle
venv/bin/python -m pytest tests/ -q                        # testler, GPU/DB'ye dokunmaz
venv/bin/python -m pytest tests/test_icerik.py -q          # tek dosya
venv/bin/python -m pytest "tests/test_icerik.py::TestKitapBul" -q   # tek sınıf

sudo systemctl restart farabi-api.service   # üretime alma (bu dizin canlı üretim)
journalctl -u farabi-api.service            # tek log kaynağı — dosya log YOK
```

- Venv kurulumu: `pip install -r requirements.txt`; birebir üretim ortamı
  `requirements.lock.txt` (pytest bunun içinde). Yeni venv kurulursa okul
  ağının MEB-CERT-TTVPN sertifikası venv'in `certifi`'sine yeniden
  eklenmeli (kök CLAUDE.md, "Sunucu ortamı — tuzaklar").
- `tests/conftest.py` sahte embedding/reranker/psycopg2 bağlantısı verir
  (`RagMotoru` yapıcısı zaten enjeksiyonlu) — yeni test gerçek GPU/DB'ye
  gitmemeli, bu sahteleri kullan.
- `lifespan` açılışta bir ısınma embed'i (reranker yüklüyse rerank'i de)
  çalıştırır (DB'ye yazmadan); restart'tan hemen sonra yavaş ilk yanıt
  beklenebilir.

## Yapı ve uç noktalar

**RAG (2026-10-03): bge-m3 CPU'da, reranker yok.** `main.py::RAG_AKTIF =
True`, `RERANK_YUKLE = False` — yalnızca `BAAI/bge-m3` (`EMBED_DEVICE =
"cpu"`) yüklenir. `/api/egitim/question` reranker'sız çalışamadığı için
`status="hata"` döner (DECISIONS.md 2026-10-03); Open WebUI yolu
(`webui.py` → `RagMotoru.ara`) yalnızca vektör aramasıdır. Her durumda
sonra `durum["hazir"] = True`. Aşağıdaki router'lar RAG modeli gerektirmez,
kendi dosya/DB/anahtar kontrollerini kendileri yapar.

| Dosya | Uçlar / görev |
|---|---|
| `main.py`, `rag.py`, `db.py` | `/health`, `/ready`, `GET /api/version`, `POST /api/egitim/question`, `GET /api/egitim/kitaplar`, `POST /api/egitim/ders_kaydi_yedek` |
| `icerik.py` | `POST /api/egitim/ders_icerigi`, `GET /api/egitim/pdf_sayfa` (PyMuPDF → PNG), `GET /api/egitim/pdf_sayfa_metni`. `DATA_DIR = /mnt/farabi-data/farabi` tek sabit |
| `yks.py` | `POST /api/egitim/yks_sorusu`, `GET /api/egitim/yks_sayfa` |
| `saglayicilar.py` + `proxy.py` | bulut sağlayıcı havuzu (`GOREV_ZINCIRLERI`) + `POST /api/egitim/metin_uret`, `/gorsel_uret` |
| `webui.py` | `POST /api/webui/ara` — Open WebUI filtresinin kaynak araması (LLM yok), `X-Farabi-WebUI-Key` (`config/api_keys.json::webui_key`), yalnızca `metrik`'e `webui_*` yazar |
| `idari_yukle.py` + `schema_idari.sql` | mevzuat → `idari_belge`/`chunk_idari` (`--kuru` önce; OCR tesseract). `HF_HUB_OFFLINE=1 venv/bin/python idari_yukle.py --kuru`, sonra `--kuru` olmadan; şema: `sudo -u postgres psql -d farabi -v ON_ERROR_STOP=1 < schema_idari.sql` (stdin; postgres `/home/ata`'yı okuyamaz). Tam yükleme CPU'yu doyurur → `taskset -c 6-11` |
| `ders_plani.py` | `POST /api/egitim/ders_plani` — 40 dk ders planı, önbellekli, kaynak dışı sayı uyarısı, görev zaman aşımı 120 sn, zincir deepseek > groq > cohere (Ollama bilerek yok). Client'a henüz bağlı değil |
| `ders_hafizasi.py` | `POST /api/egitim/ders_hafizasi` — `yedekler/ders_kaydi/<derslik>/` dosyalarından geçmiş ders hatırlama |
| `dosya.py` | `POST /api/egitim/dosya_isle`, `GET /api/egitim/dosya_indir/{id}/{ad}` (24 saatte silinir) |
| `client_durum.py` | `POST /api/client/heartbeat`, `GET /api/client/durum` (`tahta_durum` tablosu, şema `schema_tahta_durum.sql`) |
| `auth.py` | `dogrula_tahta` — `X-Farabi-Board-Key`; `config/api_keys.json::board_keys` her istekte okunur |
| `version.py` | server semver (şu an `0.2.0`), client'ınkiyle karşılaştırılır |
| `metin_araclari.py` | `icerik.py`/`yks.py`'nin paylaştığı `_norm`/`_kelimeler` normalizasyonu |

`/geogebra/` statik yolu **auth'suz** bağlanır (herkese açık GeoGebra
paketi, öğrenci verisi değil); dizin yoksa yol hiç bağlanmaz.

## Değişirken bozulmaması gerekenler

- **Derslik anahtarlı durum:** tek süreç tüm tahtalara hizmet ediyor.
  `icerik.py::_SON_KITAP` (ders_icerigi'nin seçtiği cilt — `pdf_sayfa` onu
  tercih eder; bozulursa tahtadaki sayfa ile Farabi'nin okuduğu ayrışır)
  ve `yks.py::_OTURUMLAR` `derslik` anahtarlıdır. Yeni oturum durumu da
  modül-seviyesi tekil değişken değil, `derslik` anahtarlı olmalı.
- **Yanıt şekli:** `{status, answer, sources[], latency_ms, request_id}`;
  client metni ayrıştırmaz, `status`'a göre davranır. `sources[].tur`
  (`"tablo"`) isteğe bağlı alan — eski client'lar yok sayar, öyle kalmalı.
- **Sağlayıcı anahtarları yalnızca `config/api_keys.json`'dan** okunur,
  kökteki `apikeys.env`'den değil (DECISIONS.md 2026-09-29). Yeni anahtar
  her iki dosyaya da yazılır; yeni anahtar dosyası bırakırken `git
  check-ignore` ile doğrula.
- `gorsel` zinciri: `mistral/pixtral-12b-2409` → `mistral/mistral-medium-latest`
  → `nvidia/meta/llama-3.2-11b-vision-instruct`. **NVIDIA bu ağdan
  güvenilmez** (410/timeout). openrouter anahtarı yok.
- Ollama (`qwen3.8:27b`, tek model): sistem mesajı olmayan isteklere
  `saglayicilar.py` Farabi promptunu (`ollama/farabi_sistem.txt`) ekler;
  prompt değişince `farabi-api` restart gerekir (modül açılışta okur).
  Düşünme her çağrıda kapalı olmalı: yerel API `"think": False`, `/v1`
  `reasoning_effort="none"`.
- `dosya.py` `belge_ozet`: önce yerel Ollama, bulut yedek — tahtadan
  yüklenen belgeler eğitim amaçlı, buluta gidebilir (resmî yazılar bu
  yoldan değil EBYS botundan geçer, o yalnızca yerel; DECISIONS.md
  2026-10-03). Görsel özet yalnızca bulut.

## Tahta işlem script'leri

Hepsi bu dizinden, `~/.ssh/id_ed25519_tahta` ile; hedef listesi
`tahtalar.json` (kanonik tahta kaydı — IP değişirse kök CLAUDE.md'deki
"üç yer" kuralı).

| Script | İş |
|---|---|
| `tahta-ssh.sh [--admin] <derslik> ["komut"]` | `ogretmen` (ya da `etapadmin`+sudo) olarak SSH |
| `farabi-kurulum.sh <derslik> <sunucu_url> <tahta_anahtari>` | client'ı GitHub'dan sparse-checkout ile kurar, `farabiguncelle.sh` (20:00 cron) + heartbeat cron'u yazar |
| `config_dagit.sh [--kuru] [tahta...]` | gitignore'lu ayarları dağıtır + hash ile doğrular: `../tahtayoklama/data/zil.json`, `../mudur/ders_programi.json`, `config/api_keys_tahta_ortak.json` (ortak alanlar birleştirilir) |
| `geogebra_dagit.sh` | GeoGebra çevrimdışı paketini tahtaların `client/icerik/geogebra/`'sine kopyalar |
| `geogebra_uygulama_kur.sh` | GeoGebra Klasik'i bağımsız masaüstü uygulaması olarak kurar (Farabi aracından ayrı) |
| `mikrofonsuz_dagit.sh` | 2026-09-25 tek seferlik mikrofonsuz mod dağıtımı (artık `config_dagit.sh` kapsıyor) |
| `proxy_kontrol.sh` | sunucunun internet çıkışını Müdür PC WifiHttpProxy üzerinden/doğrudan yapar (ayrı systemd drop-in) |

`yedekler/ders_kaydi/<derslik>/*.txt` — tahtalardan yedeklenen ders
transkriptleri; hata avında doğrudan okunabilir (büyükse kök CLAUDE.md'deki
log okuma ilkesi).
