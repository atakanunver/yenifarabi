# DEPENDENCY_ANALYSIS — Farabi

> Taban: `dbd3fdd` + kirli ağaç. Tüm sürümler `pip list` ile **kurulu**
> ortamlardan okundu, `requirements.txt`'ten değil.

---

## 1. Ortamlar

| venv | Python | Rol |
|---|---|---|
| `server/venv` | 3.14.4 | **ÜRETİM** — `farabi-api.service` bunu çalıştırır |
| `client/venv` | 3.14.4 | Tahta istemcisi (9-A'da kurulu) |
| `benchmark/venv` | 3.14.4 | Çevrimdışı ölçüm/indeksleme |
| `.venv-tools` | 3.14.4 | Geliştirme araçları (ruff, radon, bandit, vulture, pydeps) |

Dört ayrı venv, dört ayrı bağımlılık kümesi, **tek bir lockfile yok**.

---

## 2. En kritik bulgu: client'ta sıfır sürüm sabitleme

### D-01 — `client/requirements.txt` 13 paketin **13'ü de pinsiz**

| | |
|---|---|
| **AMAÇ** | Bir tahtaya kurulan Farabi ile 9-A'da çalışan Farabi'nin aynı olması |
| **MEVCUT DURUM** | `grep -cE '^[a-zA-Z].*==' client/requirements.txt` → **0**. Server'da 8/18 pinli, client'ta **0/13**. |
| **KANIT** | Aşağıdaki tablo: beyan edilen (sürümsüz) vs 9-A'nın venv'inde fiilen kurulu olan |
| | |

| Paket | requirements.txt | client/venv'de kurulu |
|---|---|---|
| PyQt6 | *(pinsiz)* | 6.11.0 |
| sounddevice | *(pinsiz)* | 0.5.5 |
| google-genai | *(pinsiz)* | **2.17.0** |
| numpy | *(pinsiz)* | 2.5.2 |
| pillow | *(pinsiz)* | 12.3.0 |
| requests | *(pinsiz)* | 2.34.2 |
| psutil | *(pinsiz)* | 7.2.2 |
| beautifulsoup4 | *(pinsiz)* | 4.15.0 |
| lxml | *(pinsiz)* | 6.1.1 |
| ddgs | *(pinsiz)* | 9.14.4 |
| PyPDF2 | *(pinsiz)* | 3.0.1 |
| pdfplumber | *(pinsiz)* | 0.11.10 |
| youtube-transcript-api | *(pinsiz)* | 1.2.4 |

| | |
|---|---|
| **RİSK** | **Yüksek ve somut.** `farabi-kurulum.sh` bugün 9-B'ye çalıştırılırsa `pip install -r requirements.txt` PyPI'nin **o günkü** sürümlerini kurar. `google-genai` Farabi'nin SES yolunun tamamıdır (Gemini Live) ve hızlı gelişen bir SDK'dır — kırıcı bir sürüm, sınıfta *sessiz* bir ses arızası demektir. Kural 2 ("Farabi asla dersi bozmaz") burada dağıtım katmanından ihlal edilir. Ayrıca 9-A ile yeni tahtalar arasında **yeniden üretilemeyen** bir fark doğar; bir hatanın "hangi tahtada" olduğunu ayırt etmek imkânsızlaşır. |
| **ÖNERİ** | `client/venv/bin/pip freeze > client/requirements.lock.txt` üret ve **kurulum betiği bunu kullansın**; `requirements.txt` okunabilir üst-seviye liste olarak kalsın (yorumları değerli). Kod değişikliği sıfır, davranış değişikliği sıfır. |
| **ÖNCELİK** | **P1** |

### D-02 — `server/requirements.txt` yarı pinli (8/18)

Pinli: `fastapi`, `uvicorn`, `pydantic`, `psycopg2-binary`, `pgvector`,
`sentence-transformers`, `transformers`, `torch`.
**Pinsiz:** `PyMuPDF`, `pdfplumber`, `openai`, `python-multipart`,
`python-docx`, `python-pptx`, `pandas`, `openpyxl`, `Pillow`, `PyPDF2`.

Dosya bu ayrımı **bilerek** yapmış (kendi yorumu: *"client requirements.txt
ile aynı sürüm disiplini yok, en güncel kararlı"*). Gerekçe savunulabilir —
retrieval modellerinin sabitlenmesi doğruluk için kritikti. Ama:

- Fiilen kurulu olanlar: `pandas 3.0.5`, `openai 3.0.0`, `pymupdf 1.28.2`,
  `Pillow 12.3.0` — **hepsi büyük major sürümler**. `pandas 3.x` ve
  `openai 3.x` her ikisi de yakın geçmişte kırıcı değişiklikler getiren
  hatlar. `server/dosya.py` coverage'ı **%8** (§TEST) — bu paketleri kullanan
  kod pratikte test edilmiyor.
- **RİSK:** üretim venv'i bugün çalışıyor; ama servis yeniden kurulursa ya da
  `pip install --upgrade` çalıştırılırsa `dosya.py` sessizce bozulabilir ve
  bunu yakalayacak test yok.
- **ÖNERİ:** `server/venv/bin/pip freeze > server/requirements.lock.txt`.
  Mevcut `requirements.txt`'e **dokunma** (Kural 5). **P2**

### D-03 — `benchmark/` için `requirements.txt` yok

`ls benchmark/requirements.txt` → yok. `benchmark/venv` elle kurulmuş; içinde
`sentence-transformers`, `torch`, `psycopg2`, `pgvector` olduğu
`recall_test.py`/`ortak.py` importlarından **çıkarılabiliyor** ama beyan
edilmiş değil.

**RİSK:** Benchmark, RAG doğruluk iddialarının **tek kanıt kaynağı**. Bu venv
bozulursa/kaybolursa hiçbir iddia yeniden üretilemez. `recall_test.py`
`bge-m3` + `bge-reranker-v2-m3` yükler — bunlar server'ın kullandıklarıyla
**aynı olmak zorunda**, aksi hâlde ölçüm üretimi temsil etmez. Bugün
`sentence-transformers` server'da 5.7.0'a pinli, benchmark'ta **UNKNOWN**.

**ÖNERİ:** `benchmark/requirements.txt` yaz, server'ın model-ilgili pinlerini
birebir kopyala. **P1** — ölçümün geçerliliği buna bağlı.

### D-04 — Model artefaktları sürümlenmemiş

`bandit` bulgusu **B615** (`benchmark/embed_kitap.py:131`):
`AutoTokenizer.from_pretrained(MODEL_ADI)` — `revision` pinlenmemiş.
Aynı desen `server/main.py`'de de model yüklerken geçerli.

Bugün `HF_HUB_OFFLINE=1` (servis env'inde doğrulandı) bunu **fiilen
nötrleştiriyor** — model diskten okunuyor, ağdan çekilmiyor. Yani şu an
gerçek risk düşük. Ama `HF_HUB_OFFLINE` kaldırılırsa ya da yeni bir makineye
kurulum yapılırsa `bge-m3`'ün **farklı bir revizyonu** inebilir ve tüm
embedding uzayı kayar — indekslenmiş 13 kitabın vektörleri geçersizleşir.

**ÖNERİ:** model adlarının yanına `revision=` sabiti; ya da en azından şu an
diskteki snapshot hash'ini `docs/`'a not düş. **P2**

---

## 3. Sistem-seviyesi bağımlılıklar (kod dışı)

| Bağımlılık | Durum | Kanıt |
|---|---|---|
| `farabi-api.service` | active | `systemctl is-active` |
| `ollama.service` | active | `systemctl is-active` |
| PostgreSQL | `127.0.0.1:5432` dinliyor | `ss -tlnp` |
| Ollama | `*:11434` dinliyor — **tüm arayüzler** | `ss -tlnp` |
| API | `0.0.0.0:8000` dinliyor | `ss -tlnp` |
| MEB SSL sertifikası | her venv'in certifi'sine elle eklenmiş | CLAUDE.md; bu turda doğrulanmadı → **UNKNOWN** |

**Kırılganlık:** MEB sertifikası her venv'in `certifi` paketine **elle**
eklenmiş. `pip install --upgrade certifi` bunu **sessizce geri alır** ve tüm
bulut LLM çağrıları ölür. Hiçbir yerde otomasyonu ya da kontrolü yok.
**ÖNERİ:** `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` ortam değişkeni ile sistem
güven deposunu göster — certifi'ye dokunma. **P2**

---

## 4. Dış servis bağımlılık haritası

```
client ──► Gemini Live (Google)          ── SES, kalıcı karar, alternatifsiz
client ──► server:8000                   ── içerik/RAG/dosya, DÜŞERSE ders bozulmaz (Kural 2) ✅
server ──► Ollama 11434 (yerel)          ── RAG LLM + belge_ozet birincil
server ──► PostgreSQL (yerel)            ── DÜŞERSE RAG tamamen durur
server ──► Groq/Mistral/DeepSeek/…       ── gorsel, arama_sentez, soru_taslak…
```

**Tek arıza noktaları:** PostgreSQL (yedeği yok, RAG'ın tamamı ona bağlı) ve
Gemini Live (ses, mimari olarak alternatifsiz — bilinçli karar).

**Bulut sağlayıcı kırılganlığı ÖLÇÜLMÜŞ ve gerçek:** CLAUDE.md 2026-09-02'de
`gorsel` zincirinin **her iki basamağının da ölü** olduğunu (groq 404, nvidia
timeout) ve bunun 2026-08-14'ten beri fark edilmediğini kaydediyor. Yani
sağlayıcı zincirleri **sessizce çürüyor** ve bunu yakalayan hiçbir otomatik
kontrol yok.

**ÖNERİ (D-05):** Haftalık bir "zincir canlılık" betiği — her `GOREV_ZINCIRLERI`
görevine küçük bir istek atıp hangi basamağın yanıt verdiğini raporlasın.
Yeni bağımlılık gerekmez (systemd timer, Kural 8 uyumlu). **P1** — bu tam
olarak zaten bir kez sınıfta patlamak üzere olan arıza sınıfı.

---

## 5. Puan

**Bağımlılık yönetimi: 4 / 10.**

Eksi: client 0/13 pinli (D-01); lockfile hiç yok; benchmark'ın bağımlılıkları
beyan edilmemiş (D-03) — bu, doğruluk iddialarının yeniden üretilebilirliğini
kırıyor; certifi el düzenlemesi kırılgan; sağlayıcı zincirlerinin çürümesini
yakalayan otomatik kontrol yok (D-05).

Artı: iç bağımlılık grafiği asiklik (`ARCHITECTURE_ANALYSIS.md` §2); Docker'sız
systemd tercihi devralınabilirlik için bilinçli ve tutarlı; retrieval-kritik
paketler (`torch`, `transformers`, `sentence-transformers`) **pinli** —
doğruluğun bağlı olduğu yer doğru şekilde sabitlenmiş.
