# Farabi Web Mimarisi + Performans Audit (2026-09-25)

> Yalnızca keşif ve ölçüm yapıldı; bu belge yazılırken hiçbir kod, servis ya da
> config değiştirilmedi. Bütün sayılar farabi.local üzerinde 2026-09-25
> 03:40–04:00 UTC arasında ölçüldü veya mevcut log/DB kayıtlarından okundu.
> Sunucu saati **UTC**; okul saati = UTC+3 (İstanbul).
> Kimlik bilgileri bilerek bu belgeye yazılmadı (repo PUBLIC).

## 1. Mimari özeti

```
                        LAN 192.168.16.0/21 (okul)
 Vestel tahtalar ──HTTP──► farabi-api :8000 ──► PostgreSQL :5432 (pgvector)
 (client/, 7 sınıf)            │  embedding + rerank (GPU0, bge-m3 / bge-reranker-v2-m3)
                               └─► Ollama :11434 (GPU1, qwen2.5:14b) ◄── smssistemi (mesaj düzelt)
                                                                     ◄── Müdür PC (ebys)
                                                                     ◄── Open WebUI :80
 Tarayıcı (Müdür PC, Müdür Yrd) ─► yoklama-dashboard :8010 ──SSH──► tahtalar (yoklama tarama)
                                   └─ /sistem-durumu (salt izleme)
                                ─► smssistemi :8020 ──HTTP proxy (Müdür PC :8080)──► Huawei modem 192.168.8.1
 Dış makineler: zil 192.168.23.230:8090 (ses_dashboard), debian 192.168.23.251:5002 (Chatterbox TTS)
```

Üç Farabi servisi birbirinden bağımsız: ayrı venv, ayrı systemd birimi, kod paylaşımı yok
(tek istisna: smssistemi `yoklama_pano.db`'yi salt-okunur okur).

## 2. Servisler ve portlar

| Servis | Birim / makine | Port | Kaynak kod | Mevcut health |
|---|---|---|---|---|
| Farabi RAG API ("Brain") | `farabi-api.service` | 8000 | `server/main.py`, `rag.py`, `db.py` | `GET /health`, `GET /ready` (auth yok) |
| Yoklama Panosu + Sistem Durumu | `farabi-yoklama-dashboard.service` | 8010 | `tahtayoklama/dashboard/app.py`, `sistem_durumu.py` | `GET /api/sistem-durumu` (oturum gerekli) |
| SMS Sistemi | `farabi-smssistemi.service` | 8020 | `smssistemi/app.py`, `sms_gonderici.py`, `otomasyon.py` | yok (`/api/otomasyon/durum` otomasyona özel) |
| Ollama | `ollama.service` (+ `override.conf`, `proxy.conf`) | 11434 (0.0.0.0) | — | `/api/version`, `/api/ps`, `/api/tags` |
| PostgreSQL 18 + pgvector 0.8.1 | `postgresql@18-main` | 5432 (yalnız 127.0.0.1) | — | bağlantı |
| Open WebUI | `open-webui.service` (`/opt/open-webui`) | 80 | — | `/` 200 |
| chrony | `chrony.service` | — | — | `systemctl is-active` |
| Zil (dış makine) | `ses_dashboard.service` @ zil | 8090 | uzak: `/home/atakan/ses` | yok; `/` → 401 (Basic Auth) = HTTP ayakta |
| TTS (dış makine) | `chatterbox-tts.service` @ debian | 5002 | uzak: `/opt/chatterbox-tts/tts_server.py` | `GET /saglik` → `{"durum":"ok"}` (yalnızca bu) |
| SMS gateway (dış) | WifiHttpProxy @ Müdür PC | 8080 | — | yok; `/` → 407 = proxy ayakta |

Dashboard (8010) ek uçları: `/api/ajan/*` (`GET tahtalar|sistem|yoklama`, `POST eylem|yeniden-baslat`) —
makine API'si, yalnızca 127.0.0.1 + `X-Farabi-Ajan-Key`; Open WebUI "Farabi Yönetim" aracı kullanır
(`tahtayoklama/CLAUDE.md` §5.2).

Diğer dinleyen portlar: 22 (ssh), 53 (resolved), 9749 (codebase-memory, geliştirme aracı).
Reverse proxy (nginx/caddy) **yok** — servisler doğrudan uvicorn ile 0.0.0.0'a açılıyor.

Portlar koddan/unit'lerden doğrulandı: `ExecStart ... --port 8000/8010/8020`,
`OLLAMA_HOST=0.0.0.0:11434`, `ss -ltnp`.

## 3. Loglama yapısı

- Üç Farabi servisi: stdout → systemd journal (`journalctl -u <birim>`), uvicorn access log dahil.
- RAG: her istek `metrik` tablosuna (retrieval/rerank/llm/toplam ms, sonuç, skor) yazılıyor;
  şüpheli cevaplar `soru_log`'a. → **RAG performans verisi zaten var**, yeni ölçüm altyapısı gerekmez.
- PostgreSQL: `/var/log/postgresql/postgresql-18-main.log` (logrotate'li).
- Sistem geçmişi: **sysstat (sar) kurulu ve 10 dk'da bir topluyor** (`/var/log/sysstat/saDD`).
- `pg_stat_statements` kurulu DEĞİL.

## 4. Mevcut health mekanizmaları (yeniden kullanılacaklar)

- `tahtayoklama/dashboard/sistem_durumu.py::durum_topla()` — `sensors -j`, `nvidia-smi`,
  `/proc/meminfo`, `shutil.disk_usage`, `os.getloadavg`, `systemctl is-active` (6 servis),
  Ollama `/api/tags`. Tamamı async/subprocess, sudo yok, psutil yok. Ölçülen süre: **~51 ms** (ilk çağrı 167 ms).
- `templates/sistem_durumu.html` zaten tam sayfa reload yapmıyor: **15 sn'de bir
  `fetch('/api/sistem-durumu')` → JSON → DOM güncelleme**.
- `static/kenar.js` her dashboard sayfasında aynı endpoint'i **30 sn'de bir** çağırıyor (mini rozet).
  Son 1 saatte Müdür PC'den 118 istek. → Endpoint ağırlaştırılmamalı; yeni prob'lar
  arka plan toplayıcı + önbellekle yapılmalı, mevcut JSON anahtarları korunmalı (kenar.js okuyor).
- `server/main.py` `/health`, `/ready`; TTS `/saglik`; Ollama `/api/ps` (yüklü model, VRAM, context).

## 5. Ölçümler

### Sistem (sar, son 8 gün + anlık)
- CPU: ortalama **%99.8 idle** (24 çekirdek), en yüksek load-1 **0.72**. iowait ≈ 0. PSI cpu/io = 0.
- RAM: 60 GiB'in %6–9'u kullanımda, swap 0.
- Disk: `/` %15 (462G), `/mnt/farabi-data` %1.
- GPU0 (farabi-api): 4.5 GB / 12 GB. GPU1 (Ollama): model yüklüyken 9.9 GB / 12 GB.
- Servis bazlı (cgroup): farabi-api 1.6 GB RAM / 3 günde 374 sn CPU; open-webui 785 MB; ollama 372 MB (+VRAM);
  dashboard 47 MB; smssistemi 60 MB; postgres 105 MB. Hepsi düşük.

**Sonuç: Farabi sunucusu donanım olarak zorlanmıyor.** Yavaşlık hissi CPU/RAM/disk kaynaklı değil.

### RAG (gerçek `metrik` tablosu, 376 kayıt, `sonuc='ok'` n=281)

| Aşama | p50 | p90 | Not |
|---|---|---|---|
| Embedding + vektör arama (`retrieval_ms`) | 17 ms | 23 ms | Tek sütun; ayrı ölçüm: embedding ~12 ms, vektör arama ~5 ms (sıcak), 28 ms (soğuk, EXPLAIN ANALYZE) |
| Rerank | **1291 ms** | **3491 ms** | 20–30 aday, fp32 |
| LLM (Ollama) | 4587 ms | 7231 ms | |
| Toplam | 6242 ms | 10222 ms | |

Günlük medyan toplam: 08-25 5.7 s → 09-02 6.7 s → 09-15 3.5 s → 09-20 5.4 s. **Zamanla kötüleşme yok.**
Bağlam oluşturma (context) ayrı ölçülmüyor; kod incelemesine göre string birleştirme, ms altı.

### Ollama
- Sürüm 0.32.6, tek model `qwen2.5:14b` Q4_K_M. `size_vram == size` (10.28 GB) → **tamamen GPU'da,
  CPU fallback yok** (log: `offloaded 49/49 layers to GPU`).
- Soğuk yükleme **3.5 s**, sıcak istek 2.5–2.8 s, **34.5 token/s**. `OLLAMA_KEEP_ALIVE=-1`.
- `n_ctx=8192`, **`n_slots=1`** → eşzamanlı istekler kuyruklanıyor. 30 günde 750 chat/generate isteğinin
  67'si başka bir istek bitmeden başlamış (çoğu 09-02/09-08 benchmark günleri).
- 7 kez `truncating input prompt limit=4098` uyarısı — RAG'den değil: istekler IP'siz (yerel CLI/araç)
  ve 1 tanesi Müdür PC'den (ebys). Bu istemciler `num_ctx=4096` gönderiyor, 9–11 bin token'lık prompt kırpılıyor.
- Ollama 09-23 18:47'de 3 kez yeniden başlatılmış (proxy aç/kapat ile uyumlu) → model VRAM'dan düşmüş,
  sonraki ilk istek 3.5 s soğuk yükleme ödüyor.

### PostgreSQL / pgvector
- DB 102 MB, `chunk_egitim` 11 968 satır. Cache hit %99.72. Aktif bağlantı 2 (max 100).
- **Vektör index'i yok**, sorgu `kitap_id` btree + kitap başına ~800 satır exact sıralama: 28 ms soğuk / 5 ms sıcak.
  Bu ölçekte ANN (HNSW/IVFFlat) index'i gerekmez ve filtreli aramada recall'u düşürür → değişiklik önerilmiyor.
- Log'da 7 günde 1 ERROR (manuel sorgu, `tahta_adi` kolonu yok). Slow query yok.

### Uzak servisler (TCP connect / HTTP toplam)
- TTS `.251:5002/saglik` 200, 0.4 / 2.5 ms. Makine: GTX 1060 6GB, 4373 MiB kullanımda
  (wiki ~5.9 GB diyor — fark çözülmedi, not düşülüyor), RAM 3.8 GB'ın 2.2 GB'ı, swap 462 MB.
- Zil `.230:8090` 401, 2.3 ms. SMS proxy `.243:8080` 407, 3.6 ms.
- Farabi'den debian'a SSH anahtarı YOK (yalnızca parola) → dashboard uzak CPU/GPU'yu okuyamaz.

### Loglar (7 gün)
farabi-api / dashboard / smssistemi / open-webui / postgres / chrony: 0 error/timeout/traceback.
Ollama: 13 uyarı — hepsi `ollama.com` model-recommendations erişilemiyor (zararsız).
Kernel: OOM / Xid / I/O hatası yok.

## 6. Bulgular (önem sırası)

### HIGH-1 — smssistemi (8020): senkron SMS gönderimi event loop'u donduruyor
- **Kanıt:** `otomasyon.py:333` `otomasyon_arkaplan_dongusu` (async) → `otomasyon_calistir` → `sms_gonderici.toplu_gonder`
  (`time.sleep(bekleme_sn)` her SMS arası + `_baglan` 8 deneme × 1 s). Aynı yol `app.py:685 otomasyon_manuel_calistir`
  (async def) içinden de doğrudan çağrılıyor.
- **Etki:** 09:00 otomasyonu çalışırken (N veli × ≥2 s) 8020 servisinin TAMAMI (tüm sayfalar, durdur butonu dahil) yanıt vermez.
- **Çözüm:** `await asyncio.to_thread(...)`; sqlite bağlantısı thread içinde açılmalı (`check_same_thread`).
- **Dosyalar:** `smssistemi/otomasyon.py`, `smssistemi/app.py`. **Risk:** düşük–orta (SMS gönderim yolu; kuru-çalıştırma ile test edilir).

### HIGH-2 — Rerank RAG'in ikinci büyük maliyeti, fp16 ile ~3× hızlanıyor
- **Kanıt:** üretim p50 1291 ms / p90 3491 ms. Gerçek `soru_log` sorularıyla (39 soru-kitap çifti, tablo adayları dahil)
  fp32 p50 1298 ms → **fp16 p50 405 ms**; maks skor farkı 0.0015, top-4 kümesi 39/39 aynı, top-1 38/39,
  0.5 / 0.65 eşik kararı değişen **0**.
- **Etki:** her RAG sorusunda ~0.9 s kazanç (p90'da daha fazla).
- **Çözüm:** `server/main.py` lifespan'da `reranker.model.half()` (tek satır). Önce `benchmark/rag_test.py` ile doğrulama.
- **Risk:** düşük–orta (retrieval kalitesi; ölçüm eşik kararını değiştirmediğini gösteriyor). Not: TTS'teki fp16 kalite
  sorunu otoregresif üretimle ilgiliydi; cross-encoder skorlaması farklı ve ölçüldü.

### MEDIUM-1 — smssistemi `api_mesaj_duzelt` async içinde bloklayan HTTP
- **Kanıt:** `app.py:237` async def → `ollama_mesaj_duzelt` → `urllib.request.urlopen(timeout=30)`.
- **Etki:** her "Ollama ile düzelt" tıklamasında 8020 ~2.5–30 s donuyor.
- **Çözüm:** `await asyncio.to_thread(ollama_mesaj_duzelt, taslak)`. **Risk:** düşük.

### MEDIUM-2 — farabi-api `SimpleConnectionPool` thread-safe değil, havuz 5
- **Kanıt:** `server/db.py` `psycopg2.pool.SimpleConnectionPool(1, 5)`; endpoint'ler `def` → FastAPI threadpool'unda
  paralel çalışıyor. RAG bağlantıyı LLM çağrısı boyunca (~5 s) tutuyor.
- **Etki:** bugün yük çok düşük, gözlenmiş hata yok. 5'ten fazla eşzamanlı istekte `PoolError` (500);
  eşzamanlı getconn'da yarış riski.
- **Çözüm:** `ThreadedConnectionPool` (aynı API). **Risk:** düşük.

### MEDIUM-3 — Ollama tek slot, çok istemci
- **Kanıt:** `n_slots=1`; RAG, smssistemi, ebys (Müdür PC), Open WebUI aynı modeli paylaşıyor; 67/750 istek kuyruğa girmiş.
- **Etki:** uzun bir Open WebUI / ebys isteği sınıftaki RAG sorusunu bekletir.
- **Çözüm (öneri):** `OLLAMA_NUM_PARALLEL=2` (VRAM: 9.9 GB + ~1.5 GB KV; 12 GB kartta sığar ama ölçülmeli).
  Servis restart'ı gerektirir → ders saati dışında, onayla. **Risk:** orta.

### MEDIUM-4 — Ollama restart'ları modeli VRAM'dan düşürüyor
- **Kanıt:** 09-23'te 3 restart (proxy toggle), sonrasında `/api/ps` boş; ilk istek 3.5 s soğuk yükleme.
- **Çözüm (öneri):** restart sonrası bir ısıtma isteği (ör. `ExecStartPost` ile `keep_alive=-1` boş generate) — ayrı karar.

### LOW
- `server/db.py`: `register_vector(conn)` her `getconn`'da tekrar çağrılıyor (her istekte ek bir katalog sorgusu). Önemsiz.
- 7 kırpılmış prompt (`num_ctx=4096` gönderen istemciler) — cevap kalitesi sorunu, Farabi RAG değil.
- `pg_stat_statements` yok → slow-query görünürlüğü sınırlı. Açmak PostgreSQL restart'ı ister (yalnız rapor).
- Proxy kimlik bilgisi düz metin olarak `server/proxy_kontrol.sh` (untracked) ve `smssistemi/config/modem.json` içinde —
  public repoya commit edilmemeli.
- TTS `/saglik` yalnızca `ok` dönüyor; CPU/RAM/GPU için ya `/saglik`'e `nvidia-smi` + `/proc/meminfo` eklenmeli
  (TTS kodunda değişiklik) ya da zil-timesync desenindeki gibi `command=` kısıtlı bir SSH anahtarı kurulmalı.
  Dashboard'a parola gömülmemeli.

### Değişiklik önerilmeyenler (bilinçli)
- farabi-api'deki `def` endpoint'ler bloklamıyor (threadpool).
- pgvector'e ANN index eklemek — gerekmez, zararlı olabilir.
- Dashboard frontend zaten JSON polling yapıyor; tam sayfa reload yok.
- Yoklama poller'ı (`app.py` `_polling_dongusu`) yalnızca ders penceresinde SSH yapıyor, async subprocess + timeout'lu.
- Zil ve TTS makineleri ayrı; Farabi'nin yavaşlığına etkileri yok.

## 7. Dashboard planı (UYGULANDI 2026-09-25 — bkz. §8)

1. `sistem_durumu.py`'ye **arka plan toplayıcı** (dashboard lifespan'da tek asyncio task, 15 s aralık) +
   son sonuç önbelleği → `/api/sistem-durumu` ve kenar.js önbellekten okur, ek yük getirmez.
2. Mevcut JSON anahtarları korunur, yeni anahtarlar eklenir:
   - servis başına: PID (`systemctl show MainPID`), port, CPU %, RAM (`/proc/<pid>` veya cgroup `MemoryCurrent`),
     uptime (`ActiveEnterTimestamp`), HTTP health + ms → **PROCESS / HTTP** ayrı gösterim.
   - AI: Ollama `/api/ps` (yüklü model, VRAM, context, GPU/CPU oranı), `/api/version` latency.
   - DB: salt-okunur `pg_stat_database`/`pg_stat_activity` (aktif bağlantı, >5 s süren sorgu, cache hit, DB boyutu,
     pgvector `extversion`). Dashboard venv'inde psycopg2 yok → `psql` CLI ile (pgpass mevcut) veya bağımlılık eklemek — karar gerekiyor.
   - RAG: `metrik` tablosundan son 30 dk / 24 saat p50-p90 (retrieval / rerank / LLM / toplam) — dürüst etiketleme,
     embedding ve vektör arama ayrı sütun olmadığı için birleşik gösterilir.
   - Network: TTS `/saglik`, zil `:8090` (401=UP), SMS proxy `:8080` (TCP, 60 s önbellek, **modem'e asla bağlanmadan**).
   - Disk I/O: `/proc/diskstats` farkı.
3. Son 30 dk trend: bellekte ring buffer (120 nokta × 15 s), yeni tablo/DB yok. Frontend'de basit inline SVG sparkline.
4. Tüm zamanlar İstanbul saatiyle gösterilir.
5. Salt izleme: yeni endpoint yalnızca GET, komut/restart yok.

## 8. Uygulanan değişiklikler (2026-09-25, kullanıcı onayıyla)

| Değişiklik | Dosyalar | Doğrulama |
|---|---|---|
| ThreadedConnectionPool | `server/db.py` | server testleri 108/108; restart; 3 eşzamanlı `/api/egitim/question` → 3×200 |
| SMS event loop donması (otomasyon + manuel + mesaj düzelt → `asyncio.to_thread`, çalışma kilidi) | `smssistemi/otomasyon.py`, `smssistemi/app.py`, `smssistemi/templates/otomasyon.html`, `smssistemi/test_otomasyon_app.py` | pytest 106/106 (+2 yeni: loop bloklanmıyor, kilit çift gönderimi önlüyor); restart; 8020 200 |
| Sistem Durumu → Farabi Health | `tahtayoklama/dashboard/sistem_durumu.py`, `app.py`, `templates/sistem_durumu.html`, `static/pano.css`, `test_sistem_durumu.py` | unittest 18/18 (+9 yeni); restart (ders saati öncesi); API 200, ~1.3 ms; oturumsuz 401; gerçek veriyle ekran görüntüsü kontrolü |

| SMS otomasyonu 0 SMS gönderiyordu (`durdur_bayragi=None`) | `smssistemi/otomasyon.py`, `smssistemi/test_otomasyon.py` | pytest 107/107; yeni test düzeltmesiz FAIL / düzeltmeyle PASS; otomasyon KAPALI bırakıldı |
| Sağlık yoklamaları 60 sn (log gürültüsü), başarısız yoklama her turda yeniden | `tahtayoklama/dashboard/sistem_durumu.py`, `templates/sistem_durumu.html` | unittest 18/18; ruff temiz; canlı API tüm bölümler ok |

Uygulanmayanlar: proxy düğmesi (iptal), rerank fp16 (onay bekliyor), `OLLAMA_NUM_PARALLEL`, `pg_stat_statements`, TTS uzak metrikleri.
