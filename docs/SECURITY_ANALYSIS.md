# SECURITY_ANALYSIS — Farabi

> Taban: `dbd3fdd` + kirli ağaç.
> Tarama: `.venv-tools/bin/bandit -r client server benchmark -f txt`
> **Hiçbir gizli değer okunmadı.** `api_keys.json` yalnızca *anahtar adları*
> ve *alan sayısı* için `json.load` edildi (CLAUDE.md "Okuma" kuralı).

---

## 1. Bandit özeti

| Önem | Adet |
|---|---|
| **High** | **0** |
| Medium | 3 |
| Low | 388 |

Taranan: 13.983 satır. Güven: 391/391 High.

**Low bulguların dağılımı — %74'ü gürültü:**

```
287  B101 assert_used          → pytest testleri. Yanlış pozitif.
 26  B110 try_except_pass      → GERÇEK, bkz. CODE_QUALITY Q-02b
 24  B603 subprocess_no_shell  → shell=False zaten DOĞRU kullanım
 21  B607 partial_path         → subprocess çağrıları
 12  B311 random               → kriptografik kullanım değil
 10  B404 subprocess import
  8  B112 try_except_continue
```

**Medium 3 bulgunun tamamı incelendi ve düşük riskli:**

| Konum | Bulgu | Değerlendirme |
|---|---|---|
| `server/rag.py:176` | B310 `urllib.urlopen` | URL **sabit kodlu** `http://127.0.0.1:11434/api/chat`. Kullanıcı girdisi şemayı etkileyemez. **Yanlış pozitif.** |
| `benchmark/katman_test.py:74` | B310 aynı | aynı, çevrimdışı betik. **Yanlış pozitif.** |
| `benchmark/embed_kitap.py:131` | B615 HF `revision` pinsiz | `HF_HUB_OFFLINE=1` ile fiilen nötr. Bkz. `DEPENDENCY_ANALYSIS.md` D-04. **Gerçek ama düşük.** |

**Sonuç: Bandit bu kod tabanında anlamlı bir açık bulmuyor.** Gerçek riskler
statik tarayıcının göremediği yerde — mimaride ve ağ konumlandırmasında.

---

## 2. Gerçek bulgular

### S-01 — Ollama `*:11434` üzerinde **kimlik doğrulaması olmadan** tüm ağa açık

| | |
|---|---|
| **AMAÇ** | Okulun GPU'sunun ve yerel LLM'inin kontrollü kullanımı |
| **MEVCUT DURUM** | `ss -tlnp` → `LISTEN *:11434`. Ollama'nın **hiçbir kimlik doğrulama katmanı yok** — protokolde de yok. Ağ: `192.168.23.0/24`, **VLAN yok, güvenlik duvarı yok** (CLAUDE.md). |
| **KANIT** | `ss -tlnp \| grep 11434` → `LISTEN 0 4096 *:11434 *:*` |
| **RİSK** | Okul LAN'ındaki **herhangi bir cihaz** (öğrenci telefonu dahil — aynı /24'te) `curl http://farabi.local:11434/api/chat` ile qwen2.5:14b'yi sınırsız kullanabilir. Etkiler: (a) GPU 1 doygunluğu → **ders sırasında RAG gecikmesi**, Kural 2'yi doğrudan tehdit eder; (b) `/api/delete` ile **model silme** — Ollama'nın yönetim uçları da aynı portta ve korumasız; (c) okul ağından çıkan uygunsuz içerik üretimi. |
| **HAFİFLETİCİ** | Bu **bilinçli bir karar** — CLAUDE.md 2026-08-12: *"OLLAMA_HOST ile okul LAN'ına açıldı, başka projelerin de kullanabileceği paylaşılan servis"*. Yani (a) ve (c) kabul edilmiş; **ama (b) — model silme — muhtemelen kabul edilmemiş.** |
| **ÖNERİ** | Paylaşım kararını bozmadan: `iptables`/`nft` ile 11434'ü yalnızca `/api/generate`, `/api/chat`, `/api/embeddings`'e izin verecek şekilde değil — bu L7, kolay değil — bunun yerine **Ollama'yı `127.0.0.1`'e geri al ve paylaşımı `server:8000` üzerinden auth'lu bir uçla ver**. Farabi'nin kendi trafiği zaten `127.0.0.1:11434`'e gidiyor (`rag.py:118`), yani **Farabi hiç etkilenmez**. |
| **ÖNCELİK** | **P1** |

### S-02 — Tahta anahtarı düz metin HTTP ile düz LAN'da taşınıyor

| | |
|---|---|
| **MEVCUT DURUM** | `ss -tlnp` → `0.0.0.0:8000`, TLS yok. Kimlik doğrulama **statik, paylaşılan, süresiz** bir sır: `X-Farabi-Board-Key`. |
| **KANIT** | `server/auth.py:98` `Header(alias="X-Farabi-Board-Key")`; `ss -tlnp` |
| **RİSK** | Aynı anahtarsız/VLAN'sız /24'te pasif dinleme ya da ARP zehirlemesi anahtarı verir. Anahtar ele geçirilirse: tüm `/api/egitim/*`, **`metin_uret` üzerinden okulun ödediği bulut API'leri** (S-03), ve `dosya_isle` yükleme yüzeyi açılır. Rotasyon mekanizması, süre sonu, iptal listesi **yok**. |
| **HAFİFLETİCİ** | Bugün **yalnızca 9-A** kurulu → saldırı yüzeyi bir cihaz. Sunucu okul dışına açık değil. |
| **ÖNERİ** | Bugün: bir şey yapma (risk/maliyet dengeli). **Diğer 6 tahtaya kurulum yapılmadan önce**: ya self-signed TLS + client'ta CA pinleme, ya da en azından anahtar rotasyon prosedürünü yaz. |
| **ÖNCELİK** | **P2 → kurulum genişlemeden önce P1** |

### S-03 — `metin_uret` sınırsız bir bulut LLM rölesi

| | |
|---|---|
| **MEVCUT DURUM** | `POST /api/egitim/metin_uret` kimliği doğrulanmış istemciden **200.000 karaktere kadar** rastgele istem alıp Groq/Mistral/DeepSeek/OpenRouter/NVIDIA'ya iletiyor. **Hız sınırı yok, tahta başına kota yok, günlük tavan yok, içerik kontrolü yok.** |
| **KANIT** | `server/proxy.py:29` `istem: str = Field(..., max_length=200_000)`; `proxy.py:44-53` — `saglayicilar.metin_uret` doğrudan çağrılıyor, arada hiçbir sınırlama yok. `grep -rn "rate\|limit\|kota" server/proxy.py` → yalnızca `max_length`. |
| **RİSK** | S-02 ile birleşince: çalınan bir tahta anahtarı = okulun **faturalı** API hesaplarına sınırsız erişim. Ayrıca bu, Farabi'nin "eğitim içeriği buluta gitmez" gizlilik duruşunda bir delik — röle **ne gönderildiğini denetlemiyor**. |
| **ÖNERİ** | Tahta başına basit bellek-içi jeton kovası (saatte N istek). Yeni bağımlılık gerekmez → Kural 8 tetiklenmez. |
| **ÖNCELİK** | **P2** |

### S-04 — `gorsel_uret`'te yükleme boyut sınırı **yok**

| | |
|---|---|
| **MEVCUT DURUM** | `dosya.py`'de `YUKLEME_LIMIT_MB = 60` var ve uygulanıyor. `proxy.py::gorsel_uret_endpoint` **aynı korumaya sahip değil** — `veri = await dosya.read()` boyut kontrolü olmadan **tüm dosyayı belleğe alıyor**. |
| **KANIT** | `server/proxy.py:56-70` (tam dosya okundu, hiçbir boyut kontrolü yok); `server/dosya.py:37` `YUKLEME_LIMIT_MB = 60` |
| **RİSK** | Kimliği doğrulanmış tek bir istek yeterince büyük bir yüklemeyle `farabi-api.service`'i belleğe boğabilir. Servis çökerse **tüm tahtaların içerik yolu düşer**. Kural 2 client tarafında korunuyor (sessizce kısıtlayıcı metne düşüyor) ama servis kesintisi yine de tüm RAG/içerik yeteneğini kaybettirir. |
| **ÖNERİ** | `dosya.py`'nin limitini `proxy.py`'ye uygula — **tek satırlık**, davranışı bozmayan, risksiz düzeltme. |
| **ÖNCELİK** | **P1** (etki/maliyet oranı en iyi güvenlik işi) |

### S-05 — Prompt injection: kitap metni doğrudan sistem promptuna gömülüyor

| | |
|---|---|
| **MEVCUT DURUM** | `rag.py::SISTEM_SABLON.format(kaynak=kaynak_metin)` — retrieval'dan gelen ham kitap metni **sistem** rolüne yerleştiriliyor. `pdf_sayfa_metni` de sayfa metnini Gemini Live'a "buna dayandır" diyerek veriyor. |
| **KANIT** | `server/rag.py:98-110`, `server/rag.py:296-300` |
| **RİSK** | **Düşük ve iyi sınırlanmış.** Kaynak, öğretmenin çevrimdışı indekslediği MEB ders kitapları — düşman girdisi değil. ⚠️ Ancak "korpus temiz" öncülü ölçümle **kısmen çürütüldü**: Fizik-9'da 13 chunk ~%99 oranında U+FFFD çöpü (`RAG_ANALYSIS.md` R-02). Bu **düşman** içerik değil (enjeksiyon riski yok, güvenlik değerlendirmesi DEĞİŞMEZ) — ama korpusun denetimsiz girdiğini gösteriyor; ileride kaynak çeşitlenirse bu öncül yeniden sınanmalı. Kullanıcı sorusu `user` rolünde, doğru ayrım. Halüsinasyon kapıları (eşik → katı prompt → sayı kontrolü) çıktı tarafını ayrıca koruyor. |
| **KALAN RİSK** | `dosya_isle` **öğretmenin yüklediği rastgele PDF/docx**'i işliyor ve çıktısı LLM'e gidiyor. Kötü niyetli bir PDF ("önceki talimatları yoksay…") modelin davranışını etkileyebilir. Etkisi sınırlı (çıktı yalnızca ekranda gösteriliyor, araç çağırma yetkisi yok). |
| **ÖNERİ** | Şimdilik **eylem gerekmez**, belgelendi. `dosya_isle` çıktısı ileride araç çağırmayı tetikleyecek hâle gelirse **yeniden değerlendirilmeli**. |
| **ÖNCELİK** | **P3** (izlenecek) |

### S-06 — Öğrenci sesi Google bulutuna gidiyor (KVKK)

Kalıcı ve **açıkça onaylanmış** bir karar (CLAUDE.md "Gizlilik", `mimari.md`
§14). Bir açık değil, bir **kabul edilmiş takas**. Burada yalnızca eksiksizlik
için kaydediliyor.

Doğrulanmış hafifleticiler: ham ses diske yazılmıyor; Brain'e yalnızca metin
gidiyor; öğrenci kimliği tutulmuyor; fiziksel kamera yok
(`ekran_goruntusu_al` yalnızca `grabWindow(0)` çağırıyor —
`client/actions/ekran_goruntusu_al.py`, 40 satır, okundu).

**`soru_log` süresiz saklanıyor** — silme mekanizması kodda **yok**
(`grep -rn "DELETE FROM soru_log"` → boş). Bu da CLAUDE.md 2026-08-18'de
bilinçli olarak onaylanmış. **Eylem yok.**

---

## 3. Doğru yapılmış şeyler (denetlendi, sorun bulunmadı)

| Kontrol | Sonuç | Kanıt |
|---|---|---|
| SQL injection | **Temiz** — 10 `execute()` çağrısının tamamı parametreli | `grep "execute(" server/*.py \| grep -E '%\|f"\|format\|\+' \| grep -v "%s"` → **boş** |
| Path traversal (`dosya_indir`) | **Savunuluyor** — hem karakter süzgeci hem `is_relative_to` containment | `server/dosya.py:557-567` |
| Auth kapsamı | **Eksiksiz** — 6 router'ın **6'sı da** `APIRouter(dependencies=[Depends(auth.dogrula_tahta)])`; `main.py`'nin 3 `/api/egitim/*` ucu ayrı ayrı bağlı; auth'suz olan yalnızca `/health` ve `/ready` (doğru) | her router dosyasında `grep "APIRouter("` |
| Zamanlama saldırısı | **Savunuluyor** — `hmac.compare_digest` | `server/auth.py:113` |
| Fail-closed | **Doğru** — `FARABI_AUTH_REQUIRED` varsayılanı `"1"`; config okunamazsa boş sözlük → **hiçbir anahtar geçerli olmaz** | `server/auth.py:71, 75-88` |
| Sır sızıntısı (log) | **Temiz** — anahtarın kendisi hiçbir log satırına yazılmıyor, yalnızca başarı/başarısızlık + `derslik` | `server/auth.py:105-117` |
| Sır sızıntısı (git) | **Temiz** — `git check-ignore -v` → `apikeys.env` (`*.env`), `api_keys.json` (`**/api_keys*`); `api_keys_yeni 30.08.2026.txt` de aynı desende | `git check-ignore -v` |
| Sabit kodlu sır | **Bulunmadı** — bandit 0 High, `api_keys.json` tek kaynak | bandit |

---

## 4. Puan

**Güvenlik: 6 / 10.**

Artı (denetlendi): bandit'te **0 High**; SQL injection yok; path traversal
savunuluyor; auth eksiksiz, fail-closed ve sabit-zamanlı; sır yönetimi git
tarafında temiz ve desen tabanlı.

Eksi (ölçülmüş): Ollama tüm ağa kimlik doğrulamasız açık, **model silme
dahil** (S-01); tahta anahtarı düz metin HTTP'de, rotasyonsuz (S-02);
`metin_uret` kotasız bulut rölesi (S-03); `gorsel_uret`'te boyut sınırı yok
(S-04); hiçbir uçta hız sınırı yok.

Puanın 6'da tutulmasının nedeni: bulguların çoğu **ağ konumlandırması**, kod
kusuru değil — ve saldırı yüzeyi bugün tek bir kurulu tahtayla sınırlı.
Kurulum 7 tahtaya genişlerse **aynı kod aynı puanı hak etmez**; S-01/S-02/S-04
o genişlemenin önkoşulu sayılmalı.
