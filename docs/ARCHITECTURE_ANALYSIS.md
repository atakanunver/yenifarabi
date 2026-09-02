# ARCHITECTURE_ANALYSIS — Farabi

> **Analiz turu:** 2026-09-02, yalnızca analiz (§21 — kod değiştirilmedi).
> **Taban (baseline):** `dbd3fdd` + **kirli çalışma ağacı** (15 dosya değişik,
> 2 dosya untracked). Ayrıntı: `RAG_BASELINE.md` §1.
> **Yöntem:** her iddia koddan/komut çıktısından doğrulandı. Doğrulanamayan
> her şey `UNKNOWN` olarak işaretlendi. CLAUDE.md bir *hipotez kaynağı* olarak
> kullanıldı, kanıt olarak değil.

---

## 0. Otomatik çıkarılan proje bağlamı (§2)

| Soru | Bulgu | Kanıt |
|---|---|---|
| Python dosya sayısı | **102** (venv/node_modules hariç) | `find . -name "*.py" -not -path "*/venv/*" … \| wc -l` |
| Dağılım | client 63, server 17, tahtayoklama 12, benchmark 10 | aynı komut, `awk -F/` |
| Toplam LOC (client+server) | client **12.411**, server **3.707** | `wc -l` |
| Ana framework | **FastAPI 0.118.0** (server), **PyQt6** (client) | `server/requirements.txt`, `client/requirements.txt` |
| Test framework | **pytest** (her iki venv'de kurulu) | `ls server/venv/bin`, `ls client/venv/bin` |
| Vector DB | **PostgreSQL + pgvector 0.5.0** (`chunk_egitim`, `chunk_tablo`) | `server/requirements.txt`, `server/rag.py:124-158` |
| Embedding modeli | **BAAI/bge-m3** | `server/rag.py:51` |
| Reranker | **BAAI/bge-reranker-v2-m3** | `server/rag.py:52` |
| Yerel LLM | **Ollama / qwen2.5:14b** | `server/rag.py:118` |
| Bulut LLM | Groq, Mistral, DeepSeek, OpenRouter, NVIDIA, Cerebras, Cohere, SambaNova | `server/config/api_keys.json` üst-seviye alan adları (değerler OKUNMADI) |
| Ses | **Gemini Live** (yalnız client) | `client/requirements.txt` → `google-genai` |
| CI/CD | **YOK** | `.github/` yok, `ls -a \| grep -Ei "tox\|Makefile\|github"` boş |
| Docker | **YOK — bilinçli karar** | CLAUDE.md "Kurulum Biçimi"; `docker-compose.yml` yok |
| `pyproject.toml` / `ruff.toml` | **YOK** | `find -maxdepth 2 -name pyproject.toml` boş |
| Lockfile | **YOK** (`package-lock.json` var ama Python'la ilgisiz) | — |
| Secrets yapısı | `server/config/api_keys.json` + `apikeys.env`, ikisi de gitignored | `git check-ignore -v` |

**Kritik bağlam bulgusu:** proje **derlenebilir bir paket değil** — ne
`pyproject.toml` ne `setup.cfg` var (`client/setup.py` 10 satırlık bir kabuk).
Bu, aşağıdaki üç sonucun ortak kökü: (a) ruff'un davranışı sürüm-bağımlı,
(b) import yolları `sys.path`/cwd'ye bağlı, (c) dağıtım `rsync` ile dosya
kopyalama.

---

## 1. Gerçek mimari diyagram (koddan üretildi)

```
┌─────────────────────── VESTEL AKILLI TAHTA (Pardus, 9-A) ────────────────────┐
│                                                                              │
│   main.py (2.123 sat.)  ── FarabiLive: Gemini Live oturumu + araç dağıtımı   │
│      │                                                                       │
│      ├── ui.py (2.680 sat.) ── PyQt6 HUD  ◄── main.py `from ui import`       │
│      ├── core/  ders_motoru, program, zil, olaylar, tahta, transcript,       │
│      │         anahtar (Gemini havuzu), saglayicilar (İNCE HTTP proxy)       │
│      ├── actions/ (22 araç) ── LLM'in çağırdığı tool'lar, registry: kayit.py │
│      └── tools/, memory/ ── ÇALIŞMIYOR (bkz. §4 "ölü ağırlık")              │
│                                                                              │
│   SES: mikrofon ──────────────────► Gemini Live (Google bulutu) ─────────────┼──►
└──────────────────────────────┬───────────────────────────────────────────────┘
                               │ HTTP + X-Farabi-Board-Key
                               │ (düz metin, TLS YOK, düz LAN 192.168.23.0/24)
                               ▼
┌─────────────────── FARABİ SUNUCU (farabi.local, 2× RTX 3060) ────────────────┐
│  uvicorn 0.0.0.0:8000  (farabi-api.service)                                   │
│                                                                              │
│   main.py ── kompozisyon kökü: model yükleme + 6 router                      │
│      │        /health, /ready  ← AUTH YOK (bilinçli, sağlık probu)           │
│      │        /api/egitim/question, /kitaplar, /ders_kaydi_yedek ← auth'lu   │
│      │                                                                       │
│      ├── auth.py ────── fail-closed, hmac.compare_digest, 7 board_key        │
│      ├── rag.py ─────── RAG çekirdeği (aşağıda ayrı diyagram)                │
│      ├── icerik.py ──── ders_icerigi, pdf_sayfa, pdf_sayfa_metni (PyMuPDF)   │
│      ├── yks.py ─────── yks_sorusu, yks_sayfa                                │
│      ├── dosya.py ───── dosya_isle (multipart), dosya_indir                  │
│      ├── proxy.py ───── metin_uret, gorsel_uret  → saglayicilar.py           │
│      ├── ders_hafizasi.py, client_durum.py                                   │
│      └── saglayicilar.py ── bulut sağlayıcı havuzu (GOREV_ZINCIRLERI)        │
│                                                                              │
│   GPU 0: farabi-api (bge-m3 + reranker)    GPU 1: ollama (qwen2.5:14b)       │
│   PostgreSQL+pgvector 127.0.0.1:5432 │ Ollama *:11434 (AUTH YOK, LAN'a açık) │
│   Veri: /mnt/farabi-data/farabi/ (1.8TB)                                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Bağımlılık yönü — ÖLÇÜLDÜ, İHLAL YOK

Server iç import grafiği (`grep -E "^import |^from " server/*.py`):

```
main ──► auth, db, rag, icerik, yks, proxy, dosya, ders_hafizasi, client_durum
icerik ──► auth, metin_araclari
yks ──► auth, db, icerik, metin_araclari
dosya ──► auth, saglayicilar
proxy ──► auth, saglayicilar
ders_hafizasi ──► auth, metin_araclari
client_durum ──► auth, db
```

**Sonuç: asiklik.** `main` tek kompozisyon kökü, `auth` ve `metin_araclari`
yaprak. Döngüsel bağımlılık **yok**. `rag.py` hiçbir router'ı import etmiyor —
saf bir motor, `main.py` tarafından enjekte ediliyor (`RagMotoru(embed_model,
reranker)`). Bu **iyi bir tasarım** ve korunmalı.

Client yön kontrolü: `core/` → `actions/` importu **yok** (grep boş), `ui.py` →
`main.py` importu **yok**, yalnızca `main.py:16 from ui import FarabiUI`.
Katman yönü doğru.

---

## 3. AMAÇ / MEVCUT DURUM / KANIT / RİSK / ÖNERİ / ÖNCELİK

### A-01 — `client/main.py` ve `client/ui.py` god-file

| | |
|---|---|
| **AMAÇ** | Tahta istemcisinin sürdürülebilir olması; Kural 1 "client ince kalmalı" |
| **MEVCUT DURUM** | `ui.py` 2.680 satır / MI **0,00**; `main.py` 2.123 satır / MI **0,70**. Projedeki tek iki "C" dereceli dosya. `FarabiLive._execute_tool` cyclomatic complexity **F (52)** — tüm repodaki tek F bloğu. |
| **KANIT** | `radon mi client server benchmark -s` → `client/ui.py - C (0.00)`, `client/main.py - C (0.70)`, üçüncü en kötü `server/dosya.py - B (14.67)`. `radon cc -s` → `client/main.py M 919:4 FarabiLive._execute_tool - F (52)`, `client/ui.py M 449:4 HudCanvas.paintEvent - E (37)`. Coverage: `main.py` 919 stmt / 640 miss = **%30**, `ui.py` 1609 stmt / 1347 miss = **%16**. |
| **RİSK** | Bu iki dosya ders anında çalışan tek süreçtir. `_execute_tool` 22 aracın tamamının dağıtım noktası — 52 dallanma, %30 kapsam. Kural 2 ("Farabi asla dersi bozmaz") tam olarak buradan ihlal edilir. |
| **ÖNERİ** | `_execute_tool`'u registry-tabanlı dağıtıma indirgemek (`kayit.py` zaten bir registry — dallanma oraya taşınabilir). `ui.py` için `HudCanvas`'ı ayrı modüle çıkarmak. **Önce characterization test** (§18). |
| **ÖNCELİK** | **P1** |

### A-02 — Kural 1 fiilen tamamlandı, ama client'ta ölü ağırlık kaldı

| | |
|---|---|
| **AMAÇ** | "Ağır iş sunucuda, client ince" |
| **MEVCUT DURUM** | Ağır iş gerçekten taşınmış (RAG/PDF/LLM/dosya hepsi server'da — §2 grafiği doğruluyor). Ama client hâlâ 12.411 satır ve bunun **~1.100 satırı hiç çalışmıyor**: `client/tools/` (7 dosya, coverage **%0**: kitap_metin 149, kitap_ozet 117, tablo_cikar 117, mikrofon_test 146, yks_metin 80, onbellek_isit 42, dogrula 90) + `client/memory/` (memory_manager 143 + config_manager 37, coverage **%0**, **hiçbir yerden import edilmiyor**). |
| **KANIT** | `coverage report --data-file=client/.coverage`; `grep -rn "memory_manager\|config_manager" client/ --include=*.py \| grep -v "^client/memory/"` → **boş**. `client/planlar/` kod değil, PDF/plan arşivi (`ls client/planlar`). |
| **RİSK** | Düşük çalışma-zamanı riski (kod çağrılmıyor), yüksek **bilişsel** risk: her rsync bunları 9-A'ya gönderiyor, her okuyan "bu ne işe yarıyor?" diye vakit kaybediyor. `client/memory/long_term.json` diskte duruyor ama kimse okumuyor — CLAUDE.md ise `memory/`'nin ders konuşmalarını tutmasını istiyor (§4 D-03). |
| **ÖNERİ** | `client/memory/` sil (gerçekten ölü). `client/tools/` **silme** — CLAUDE.md'ye göre server'ın client kopyasında koşuyor; onun yerine client'a gitmemesi için rsync `--exclude` ile ayır. |
| **ÖNCELİK** | **P2** |

### A-03 — Paylaşılan prompt/sabit yok: üç yerde elle senkron

| | |
|---|---|
| **AMAÇ** | RAG davranışının tek kaynaktan yönetilmesi |
| **MEVCUT DURUM** | `SISTEM_SABLON` (halüsinasyon kapısının kalbi) **üç yerde birebir kopya**: `server/rag.py:98`, `benchmark/katman_test.py`, `docs/mimari.md §8`. Kodun kendi docstring'i bunu itiraf ediyor: *"Üç yerde de elle senkron tutulmalı; paylaşılan tek bir prompt dosyası yok."* Aynı şey eşikler için de geçerli (`ESIK_RERANK` rag.py'de sabit, recall_test.py'de `--esik` argümanı). |
| **KANIT** | `server/rag.py:9-12` docstring; `sed -n '1,40p' server/rag.py` |
| **RİSK** | Benchmark'ın ölçtüğü prompt ile üretimin kullandığı prompt **sessizce ayrışabilir**. O an tüm RAG doğruluk iddiaları geçersiz olur ve bunu hiçbir test yakalamaz. |
| **ÖNERİ** | `server/prompt_rag.py` (tek sabit) → `rag.py` ve `benchmark/katman_test.py` ikisi de import etsin. Benchmark ayrı venv'de: `sys.path` eklemesi ya da küçük bir paylaşılan dosya. Düşük risk, yüksek getiri. |
| **ÖNCELİK** | **P1** |

### A-04 — `derslik` kimliği auth'tan değil, istek gövdesinden geliyor

| | |
|---|---|
| **AMAÇ** | Sınıflar arası durum izolasyonu |
| **MEVCUT DURUM** | `auth.dogrula_tahta` doğrulanmış bir `TahtaKimligi(derslik=...)` üretiyor **ama hiçbir endpoint onu kullanmıyor**. `icerik.py::_SON_KITAP` ve `yks.py::_OTURUMLAR` sözlükleri, istemcinin gövdede gönderdiği `derslik` alanıyla anahtarlanıyor. |
| **KANIT** | `server/auth.py:98-117` (`return TahtaKimligi(derslik=derslik)`); CLAUDE.md'nin kendi notu: *"`derslik` kimliği auth'tan DEĞİL, doğrudan client isteğinden geliyor"*. Router'lar `dependencies=[Depends(...)]` kullanıyor — dönen değeri **bağlamıyor**. |
| **RİSK** | 9-A'nın anahtarına sahip bir istemci `derslik="12-B"` göndererek 12-B'nin oturum durumunu okuyabilir/bozabilir. Bugün etkisi düşük (yalnızca 9-A kurulu) ama `farabi-kurulum.sh` diğer 6 tahtaya gittiği anda gerçek bir yetkilendirme açığı olur. |
| **ÖNERİ** | `kimlik: TahtaKimligi = Depends(auth.dogrula_tahta)` parametresini endpoint imzalarına ekleyip `istek.derslik` yerine `kimlik.derslik` kullanmak. Geriye dönük uyum için: auth kapalıyken (`FARABI_AUTH_REQUIRED=0`) gövdeye düş. |
| **ÖNCELİK** | **P2 bugün → diğer tahtalar kurulmadan ÖNCE P1** |

### A-05 — Sunucuda dosya-bazlı log yok; gözlemlenebilirlik tek yönlü

| | |
|---|---|
| **AMAÇ** | Üretim arızasını kanıtla teşhis edebilmek |
| **MEVCUT DURUM** | Server yalnızca journald'a yazıyor; yapılandırılmış metrik **veritabanında** (`metrik`, `soru_log` — `rag.py::_logla`). Bu iyi. Ama `metrik` tablosunu **okuyan hiçbir şey yok** — dashboard, rapor, sorgu betiği hiçbiri repoda mevcut değil. |
| **KANIT** | `grep -rn "FROM metrik" .` → yalnızca şema dosyası. CLAUDE.md: *"Server'da dosya bazlı log YOK"*. |
| **RİSK** | Ölçüm verisi toplanıyor ama hiç kullanılmıyor → Kural 10 ("ölçmeden optimizasyon yapma") pratikte uygulanamıyor, çünkü ölçümü okumanın yolu yok. `plan.md`'deki gecikme rakamları elle üretilmiş. |
| **ÖNERİ** | ~40 satırlık `server/tools/metrik_ozet.py`: son N günün p50/p95 gecikmesi, `sonuc` dağılımı, `yetersiz_kaynak` oranı. Yeni bağımlılık yok (Kural 8 tetiklenmez). |
| **ÖNCELİK** | **P2** |

### A-06 — Sunucuda hız sınırı / kota yok

| | |
|---|---|
| **AMAÇ** | Okulun ödediği bulut API kotasının ve GPU'nun korunması |
| **MEVCUT DURUM** | `POST /api/egitim/metin_uret` kimliği doğrulanmış her tahtadan **200.000 karaktere kadar** serbest istem kabul edip Groq/Mistral/DeepSeek'e iletiyor. Hız sınırı, tahta başına kota, günlük tavan **yok**. `gorsel_uret` ise **boyut sınırı bile yok** (`dosya_isle`'nin `YUKLEME_LIMIT_MB=60`'ı buraya uygulanmıyor). |
| **KANIT** | `server/proxy.py:29` `istem: str = Field(..., max_length=200_000)`; `proxy.py:55-70` `gorsel_uret_endpoint` — `await dosya.read()` öncesi hiçbir boyut kontrolü yok. `server/dosya.py:37` `YUKLEME_LIMIT_MB = 60` yalnızca `dosya.py`'de. |
| **RİSK** | Statik bir tahta anahtarı düz metin HTTP ile düz LAN üzerinde taşınıyor (§SECURITY S-02). Anahtar sızarsa fatura ve GPU doğrudan hedef. Ayrıca sınırsız `gorsel_uret` yüklemesi tek istekle belleği doldurabilir. |
| **ÖNERİ** | `gorsel_uret`'e `dosya.py`'nin limitini uygula (tek satır). `metin_uret`'e tahta başına basit bellek-içi jeton kovası — yeni bağımlılık gerekmez. |
| **ÖNCELİK** | **P2** (`gorsel_uret` boyut sınırı: **P1**, tek satır, risksiz) |

---

## 4. Doküman ↔ Kod ayrışması (bu turun ana katma değeri)

CLAUDE.md geçmişte defalarca gerçeğe aykırı çıktı (FAZ1 raporundaki 129/129,
"iki aşamalı kazanım filtresi", "90 gün sonra silinir", "iki kart da dolu").
Bu yüzden her iddia **hipotez** kabul edilip koda karşı sınandı:

| # | CLAUDE.md iddiası | Doğrulama | Sonuç |
|---|---|---|---|
| D-01 | `TABLO_KAYNAGI = False` ile tek satırda geri dönülür | `grep -n TABLO_KAYNAGI server/rag.py` → `87:TABLO_KAYNAGI = True`, `239: if TABLO_KAYNAGI:` | ✅ **DOĞRU** |
| D-02 | `kazanim_kod` hiçbir sorguda okunmuyor | `grep -rn "kazanim" server/ --include=*.py` → **hiç eşleşme yok** | ✅ **DOĞRU** — ve `bac8b91` commit'i "Kazanım katmanı (RAG)" başlığını taşımasına rağmen server'a tek satır dokunmamış; yalnızca `benchmark/` + DB tablosu. **Commit başlığı yanıltıcı.** |
| D-03 | auth üretimde zorunlu, `override.conf` silindi | `systemctl show farabi-api.service -p Environment` → `CUDA_VISIBLE_DEVICES=0 CUDA_DEVICE_ORDER=PCI_BUS_ID HF_HUB_OFFLINE=1` (`FARABI_AUTH_REQUIRED` **yok**) + `auth.py:71` varsayılan `"1"` | ✅ **DOĞRU** — auth zorunlu |
| D-04 | 7 tahta için `board_keys` yazıldı | anahtar **değerleri okunmadan** sayıldı: 7 giriş, `['9-A','9-B','10-A','11-A','11-B','12-A','12-B']` | ✅ **DOĞRU** |
| D-05 | `.gitignore` desen tabanlı, `apikeys.env` artık kapsamda | `git check-ignore -v apikeys.env` → `.gitignore:22:*.env`; `api_keys.json` → `.gitignore:23:**/api_keys*` | ✅ **DOĞRU** |
| D-06 | `client/actions/yoklama_al.py` `bac8b91`'de silindi (ölü kod) | `git show --stat bac8b91` silindiğini doğruluyor, ama dosya **yeniden yazılmış** ve `git status`'ta `??`. `kayit.py:537` `ad="yoklama_al"` ile **artık gerçekten kayıtlı** | ⚠️ **BAYAT** — silinmedi, geri geldi ve bu kez doğru şekilde kaydedildi. CLAUDE.md bunu bilmiyor. |
| D-07 | `memory/` ders konuşmalarını tutsun | `client/memory/` coverage **%0**, **hiçbir importer yok**. Konuşmalar aslında `core/transcript.py` + `client/logs/ders/*.txt`'te | ❌ **YANLIŞ/DİLEK** — CLAUDE.md bir *isteği* mevcut durum gibi yazıyor |
| D-08 | Ekran görüntüsü yalnız 9-A'da kurulu | `client/actions/ekran_goruntusu_al.py` + `ekrandaki_soruyu_oku.py` repoda var, coverage %11/%14 | ✅ kod mevcut; **tahta kurulumu bu turda doğrulanmadı** (SSH gerekir) → `UNKNOWN` |
| D-09 | GPU 0'da yük altında 7.041 MiB boş | bu turda ölçüm: GPU 0 → **5.045 MiB boş**, GPU 1 → **1.961 MiB boş** (`nvidia-smi`, boşta) | ⚠️ **SAYI BAYAT** — yön doğru (GPU 0'da yer var, GPU 1 dolu), miktar farklı. Yerel VLM tartışması **5 GB** üzerinden yapılmalı. |
| D-11 | "**13 kitap** pgvector'a indekslendi" | canlı DB: `SELECT count(*) FROM kitap` → **19**; `chunk_egitim` **8.726** satır | ❌ **YANLIŞ** — 19 kitap indeksli. Kapsam değerlendirmeleri 19 üzerinden yapılmalı (`RAG_ANALYSIS.md` R-D1) |
| D-12 | (örtük varsayım) korpus temiz/küratörlü | `chunk_egitim`'de **45 chunk > 3.122 karakter**, en uzunu **21.814** (Fizik-9); 13 chunk PyMuPDF `�` çöpü | ⚠️ **KISMEN YANLIŞ** — %98,3'ü temiz, ama Fizik-9'da ölçülmüş bir bozulma var (`RAG_ANALYSIS.md` R-02) |
| D-10 | `chunk_tablo` bağlanınca 35/40 → 38/40 | `plan.md:77-80` bu tabloyu içeriyor. Ama `benchmark/reports/katmanli_20260811_071503.json` **tablo eklenmeden önce zaten 38/40 (%95)** gösteriyor | ⚠️ **KARŞILAŞTIRILAMAZ** — iki rakam farklı harness'lardan (`katman_test.py` vs canlı API). Ayrıntı: `RAG_ANALYSIS.md` §6. |

---

## 5. Mimari puanı

**7 / 10.**

Artı (ölçülmüş): server bağımlılık grafiği asiklik ve `main` tek kompozisyon
kökü (§2); `rag.py` saf motor, enjeksiyonla test edilebilir; auth **her**
router'da tek satırla ve fail-closed (§SECURITY); path traversal savunması
`dosya_indir`'de gerçekten var; kod yorumları ölçüm ve gerekçe içeriyor
(`rag.py:64-86` — nadir görülen bir kalite).

Eksi (ölçülmüş): client'ta iki god-file MI 0,00 / 0,70 ve toplam LOC'un
%39'unu tutuyor (§A-01); RAG promptu üç yerde kopya (§A-03); kimlik doğrulama
sonucu kullanılmıyor (§A-04); `client/memory/` tamamen ölü (§A-02); paket
tanımı/lockfile yok (§0).

