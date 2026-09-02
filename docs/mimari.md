# FARABİ — MİMARİ

> Bu doküman 2026-08-30'da sıfırdan yazıldı (önceki `mimari.md` ve
> `docs/` altındaki diğer analiz raporları kullanıcı isteğiyle silindi —
> "temiz başlangıç"). Aşağıdaki her madde bu tarihte gerçek kod okunarak
> ve/veya canlı sistemde doğrulanarak yazıldı; varsayım değil.

## 1. Ne — kısaca

Farabi, sınıf akıllı tahtalarında (Vestel, Pardus ETAP GNU/Linux) çalışan,
Gemini Live ile sesli etkileşen bir ders asistanı. Öğretmenin yerine geçmez,
onun ikinci yardımcısıdır — ders akışının kontrolü her zaman öğretmende
kalır (`core/ders_motoru.py`'nin kendi invaryantı: "öğretmen her zaman
kazanır").

## 2. Süreç topolojisi

İki bağımsız Python süreci, HTTP üzerinden konuşur — broker/WebSocket yok:

```
┌─────────────────────┐         HTTP (server/ 5 router)        ┌──────────────────────────┐
│  client/  (tahta)    │ ───────────────────────────────────▶  │  server/  (farabi.local)  │
│  PyQt6 + Gemini Live  │ ◀───────────────────────────────────  │  FastAPI + PostgreSQL     │
└──────────┬───────────┘                                        └────────────┬─────────────┘
           │ ses (WebSocket, Google)                                         │
           ▼                                                                  ▼
   Gemini Live API                                          Ollama · pgvector · bulut sağlayıcılar
   (gemini-2.5-flash-native-audio)                           (Groq/Mistral/DeepSeek/OpenRouter/NVIDIA)
```

Ses (öğrenci/öğretmen konuşması, Farabi'nin sesi) **yalnızca** client ↔
Gemini Live arasında akar — server bunu hiç görmez, hiç saklamaz (ham ses
diske hiç yazılmaz). Server yalnızca metin/görüntü işi yapar.

## 3. Donanım (server, farabi.local)

2× NVIDIA RTX 3060 12GB, **ikisi de tam kapasite committed**:
- Kart 1 → `ollama.service` (qwen2.5:14b, context 8192)
- Kart 2 → `farabi-api.service` (embedding `BAAI/bge-m3` + reranker
  `BAAI/bge-reranker-v2-m3`, birlikte)

Yeni bir GPU işi (vision model, vb.) planlanırken bu iki kartın ZATEN dolu
olduğu unutulmamalı — boş VRAM yok. Bu yüzden görsel/OCR/tablo işleri
(bkz. §8) bilerek yerel GPU değil, mevcut bulut sağlayıcı zincirini
kullanır.

## 4. `server/` — FastAPI Brain

`server/main.py` her router'ı topluyor:

| Dosya | Uçlar | İş |
|---|---|---|
| `main.py`/`rag.py`/`db.py` | `/health`, `/ready`, `POST /api/egitim/question`, `GET /api/egitim/kitaplar`, `POST /api/egitim/ders_kaydi_yedek` | RAG (§5), DB havuzu |
| `icerik.py` | `POST /api/egitim/ders_icerigi`, `GET /api/egitim/pdf_sayfa`, `GET /api/egitim/pdf_sayfa_metni` | Kitap sayfa metni, PDF render, sayfa-metni grounding (§9) |
| `yks.py` | `POST /api/egitim/yks_sorusu`, `GET /api/egitim/yks_sayfa` | Geçmiş YKS sorusu arama, derslik-anahtarlı oturum (`_OTURUMLAR`) |
| `saglayicilar.py`/`proxy.py` | `POST /api/egitim/metin_uret`, `POST /api/egitim/gorsel_uret` | Bulut LLM/vision havuzu (§7), client'a HTTP yüzü |
| `dosya.py` | `POST /api/egitim/dosya_isle`, `GET /api/egitim/dosya_indir/{id}/{ad}` | Dosya/görsel işleme (OCR dahil) |
| `ders_hafizasi.py` | `POST /api/egitim/ders_hafizasi` | Geçmiş ders kaydı arama (bu tahtanın kendi yedekleri) |
| `client_durum.py` | `POST /api/client/heartbeat`, `GET /api/client/durum` | Filo görünürlüğü (§10) |
| `auth.py` | (dependency, tüm router'lara bağlı) | Tahta kimlik doğrulama — **kod hazır, YÜRÜRLÜKTE DEĞİL** (§11) |

Config: `server/config/api_keys.json` (gitignored) — 5 bulut sağlayıcı
anahtarı + `board_keys` (auth için, şu an boş). Gemini anahtarı BURADA YOK —
ses client'ta kalıyor, mimari kısıtı (§6).

## 5. RAG (`server/rag.py`)

```
soru → embed (bge-m3) → İKİ AYRI pgvector sorgusu (ikisinde de kitap_id filtresi):
          chunk_egitim top-20  +  chunk_tablo top-10        ← 2026-09-02, FAZ 1
     → rerank (bge-reranker-v2-m3) BİRLEŞİM üzerinde
          (tablo adayları rerank'e 1200 karaktere KIRPILARAK girer; LLM'e giden
           kaynak metin TAM kalır — bkz. aşağıdaki ölçüm notu)
     → top-4 → EŞİK (ESIK_RERANK=0.5, altındaysa LLM'e gitme) → Ollama qwen2.5:14b (temp=0.2)
     → sayı-doğrulama (cevaptaki her sayı kaynak metinde var mı) → {status, answer, sources[]}
```

**FAZ 1 (2026-09-02) — `chunk_tablo` retrieval'a bağlandı.** Önceki sürümde
bu satır "yalnızca `chunk_egitim`" diyordu, o zaman doğruydu. Tasarım kararı:
tek `UNION` sorgusu DEĞİL, iki ayrı top-K — birleşik sorguda tablo satırları
metin adaylarını havuzdan iterdi ve yalnızca-metin recall'ı düşerdi.
`ESIK_RERANK` değiştirilmedi, tablo da aynı kapıdan geçer. `chunk_tablo`
sorgusu ayrı `try/except` içinde: patlarsa metin yolu hiç etkilenmez (§2).
Geri dönüş: `rag.py::TABLO_KAYNAGI = False` (tek satır, DB'ye dokunmadan).

Ölçüm (40 soruluk doğrulanmış set, canlı API, her yapılandırma 2 kez):

| Yapılandırma | A | B | C | TOPLAM | medyan | rerank_ms |
|---|---|---|---|---|---|---|
| kapalı (taban) | 17/17 | 13/18 | 5/5 | 35/40 %88 | 5,2 sn | 893 |
| k=10, kırpmasız | 17/17 | 15/18 | 5/5 | 37/40 %92 | 7,9 sn | 3321 |
| **k=10 + kırpma 1200** | 17/17 | **16/18** | 5/5 | **38/40 %95** | **5,7 sn** | 1439 |

Grup A/C hiç bozulmadı; kazanç tamamen Grup B'de (çoklu-sayfa sentez, bu
mimarinin bilinen zayıf noktası). **Yan bulgu:** `CrossEncoder` `max_length`
verilmeden yükleniyor (`main.py`) ve batch en uzun diziye padleniyor — tek
uzun bir tablo (4571 krk) tüm partinin maliyetini yükseltiyordu. Kırpma hem
gecikmeyi tabana yaklaştırdı hem doğruluğu artırdı. Aynı etki `chunk_egitim`
için de geçerli (ort. 1249, en fazla 3122 krk) — oraya da uygulamak muhtemel
bir kazanç ama AYRI bir değişiklik, kendi 40-soruluk turunu gerektirir.
**Bilinen sınır:** 1200 karakteri aşan büyük bir tablonun sonraki satırları
retrieval'ı etkilemez.

**Kapsam notu:** `chunk_tablo` şu an yalnızca `biyoloji-9` için dolu (67
tablo). Diğer 18 kitap için `tools/tablo_cikar.py` + `benchmark/
embed_tablo.py` koşturulmadı — koşturulduğunda bu ölçüm TEKRARLANMALI.

Üç katmanlı halüsinasyon savunması: eşik + LLM sıcaklığı + sayı-kontrolü.
Cevap ≤3 cümle, her cevapta kaynak (`9. Sınıf Biyoloji, s. 84`). Chunk sayfa
sınırını aşmaz. `kazanim_kod` kolonu DB'de var ama **hiçbir kod tarafından
doldurulmuyor/okunmuyor** — kazanım bazlı filtreleme henüz yok, yalnızca
`kitap_id` filtresi çalışıyor.

Test kapsamı: **`rag.py`'nin otomatik testi yok** — yalnızca
`benchmark/katman_test.py` (elle çalıştırılan ölçüm scripti) dolaylı
doğrulama sağlıyor.

## 6. `client/` — tahta istemcisi

PyQt6 tabanlı, Vestel akıllı tahtalarda çalışıyor. İnce: kendi kitap/YKS/
içerik deposu yok, ağır iş server'a HTTP ile gidiyor. **Ses tamamen
istisna** — Gemini Live client'ta, server'dan bağımsız (kalıcı mimari
kararı, 2026-08-11: yerel STT/TTS iptal edildi, "başka bir projede
denenebilir, bu projenin kapsamında değil").

- `main.py` — `FarabiLive`: Live oturumu (`google-genai` SDK, `client.aio.
  live.connect()`), tool dispatch, ders akışı enjeksiyonu, reconnect/backoff.
- `ui.py` — `FarabiUI`/`MainWindow`: PyQt6 HUD, `player` olarak action'lara
  geçirilir (`FarabiUI._win` gerçek `MainWindow`).
- `core/ders_motoru.py` — ders akışını KOD yürütür (11 adım: BEKLIYOR →
  YOKLAMA → ... → BITTI), `enjekte=True` varsayılan. Öğretmen `duraklat()`/
  `mudahale()` ile her zaman motoru geçersiz kılar.
- `actions/kayit.py` — TOOL REGISTRY, tek kaynak. Şu an **18 araç**
  kayıtlı (bkz. §8).

## 7. Model routing (gerçek durum)

- **Canlı ses**: `models/gemini-2.5-flash-native-audio-preview-12-2025`
  (`core/modeller.py`, tek sabit, routing yok).
- **RAG LLM**: Ollama `qwen2.5:14b` (yerel, `server/rag.py`).
- **Metin/görsel görevleri** (`server/saglayicilar.py::GOREV_ZINCIRLERI`,
  statik görev→sağlayıcı zincirleri, dinamik router YOK):

  | Görev | Zincir |
  |---|---|
  | `gorsel` | **2026-09-02'de tamamen yenilendi** (eski zincirin İKİ basamağı da ölüydü: groq'ta model artık yok = 404, nvidia 90b-vision zaman aşımı): mistral `pixtral-12b-2409` → mistral `mistral-medium-latest` → nvidia `llama-3.2-11b-vision-instruct`. Evrensel yedek hâlâ YOK (`evrensel_yedek=False`), ama artık üç gerçek basamak var; üçüncüsü bilerek başka sağlayıcıda (ilk ikisi aynı mistral anahtarını paylaşıyor) |
  | `arama_sentez` | deepseek → (evrensel: openrouter/free) |
  | `belge_ozet` | **ollama (yerel, 2026-08-25'ten beri birincil)** → deepseek → mistral |
  | `video_ozet` | deepseek → groq |
  | `kitap_ozet` | **groq `openai/gpt-oss-120b`** → deepseek → ollama (2026-09-02: eski 1. basamak `nvidia/meta/llama-3.3-70b-instruct` "410 Gone — end of life" veriyordu, zincir sessizce deepseek'e düşüyordu) |
  | `sembol_duzelt` | deepseek → mistral → cohere |
  | `soru_taslak` | deepseek → mistral → **groq `openai/gpt-oss-120b`** → ollama (aynı ölü nvidia modeli buradan da çıkarıldı, 2026-09-02) |

  Kota/hata devri: quota-şekilli hata → 4 saat soğuma, diğer her hata →
  sıradaki sağlayıcıya (soğumasız).

## 8. Tool registry — 18 araç (`actions/kayit.py`)

`ders_icerigi`, `kitap_sorusu`, `pdf_sayfa`, `yks_sorulari`, `ders_hafizasi`,
`site_goster`, `file_processor`, `web_search`, `youtube_video`, `eba`,
`ekran_goruntusu_al`, `ekrandaki_soruyu_oku` (KIP_HEPSI+talimat) ·
`web_ac`, `uygulama_ac`, `dosya_ac`, `pencere_kapat`, `talimat_modundan_cik`
(yalnızca KIP_TALIMAT) · `shutdown_farabi`.

`izin`/`maliyet` alanları metadata — **çalışma zamanında uygulanmıyor**,
yalnızca `kip` filtresi gerçek bir yetki sınırı (öğretmen talimat modunda
`ders_icerigi`/`web_search` gibi normal ders araçları hiç sunulmaz).

**`ekran_goruntusu_al`/`ekrandaki_soruyu_oku` — 2026-08-30, kullanıcı
kararıyla eklendi.** Kamera/webcam DEĞİL — bu tahtada kamera donanımı hiç
yok (`/dev/video*` yok, doğrulandı). `QApplication.primaryScreen().
grabWindow(0)` ile yalnızca tahtanın KENDİ o anki ekran görüntüsünü alır
(ör. `pdf_sayfa`'nın açtığı sayfa) — fiziksel sınıfı/öğrencileri hiç
görmez. Bu, önceden (2026-08-09) kaldırılmış `screen_processor.py`
(webcam tabanlı) ile AYNI ŞEY DEĞİL; o kaldırılmış kalıyor.

## 9. Bilinen, düzeltilmiş sınıf hataları (2026-08-30, 9-A canlı testi)

1. **Kitap-sayfa uyuşmazlığı (matematik_9 cilt 1/cilt 2).** `pdf_sayfa`
   her zaman listedeki ilk kitabı döndürüyordu, `ders_icerigi` konuya göre
   doğru cildi seçiyordu — aynı sayfa numarası iki farklı içerik. Fix:
   `_SON_KITAP` (derslik-anahtarlı), client `derslik`'i her iki isteğe de
   ekliyor.
2. **`pdf_sayfa` sayfa metni olmadan gösteriyordu.** Öğretmen doğrudan
   sayfa numarası söylediğinde (`ders_icerigi` çağrılmadan) Farabi ekranda
   ne yazdığını bilmeden içerik uyduruyordu. Fix: `GET /api/egitim/
   pdf_sayfa_metni` — aynı kitap seçimiyle gerçek sayfa metnini döner,
   yoksa modele açık "uydurma" uyarısı gider. Ayrıca bir kitapta (yalnızca
   `fizik_9.pdf`, %55 sayfa) gömülü font bozukluğu nedeniyle metin U+FFFD
   ile kirli çıkıyor — kalite kapısı (>%2 U+FFFD ise "bulunamadı") ekli.
3. **DUR düğmesi konuşma sırasında gerçekten kesmiyordu.** `_sesi_sustur()`
   yalnızca yerel ses kuyruğunu boşaltıyor, Gemini'nin sunucu tarafında
   ÜRETMEKTE OLDUĞU yanıtı iptal edemiyordu (SDK'da cancel metodu yok) —
   uzun bir yanıt akarken yeni parçalar kuyruğu hemen dolduruyordu. Fix:
   `talimat_modundan_cik`'in kullandığı "bağlantıyı zorla kes + yeniden
   bağlan" deseni (`_DurZorlama` istisnası, `run()`'ın backoff'suz anında
   reconnect dalı) — yalnızca `self._is_speaking` iken tetiklenir.
4. **YKS soru eşleşmesi ders sınırlamıyor.** `ders` ipucu yalnızca skor
   önyargısı, dosya/konu filtresi değil — karma sınav kaynaklarında
   (AYT_EA gibi) yanlış-ders soru gelebiliyor. **Henüz düzeltilmedi.**
5. **Model bazen "yaptım" diyip tool çağırmadan devam ediyor** (ör. "aynı
   soruyu tekrar göster" dendiğinde araç çağrılmadan "tekrar gösteriyorum"
   demek). **Henüz düzeltilmedi**, prompt-dürüstlük sınıfı bir sorun.

## 10. Senkronizasyon — server-merkezli, pull yönü

**2026-08-30'da tersine çevrildi** (9-A pilot dönemi bitti): `client/` kodu
artık SERVER'da (`/home/ata/farabi/client/`) düzenlenir, tek doğruluk
kaynağı budur. Her tahta `~/.local/bin/farabiguncelle.sh` ile sunucudan
ÇEKER (rsync, `--delete`, tam simetrik exclude listesi — `venv/`, `logs/`,
`icerik/`, `config/api_keys.json` her iki tarafta da korunur). Yeni
tahtalar için canonical kurulum `server/farabi-kurulum.sh` (git'te).

`server/client_durum.py::heartbeat` (2026-08-18'de yazılmış, ilk gerçek
çağıranı 2026-08-30'da kuruldu) — her tahta 15 dakikada bir `derslik` +
son çekilen commit hash'i + hostname/IP bildirir, `GET /api/client/durum`
ile görünür.

**Açık boşluk:** eski push akışında sunucuda otomatik `git commit` vardı;
pull'a geçince bunun eşdeğeri yok — server'daki `client/` değişiklikleri
artık ELLE commit edilmeli.

**Gerçek filo durumu:** yalnızca **9-A** üzerinde Farabi kurulu ve
çalışıyor. `tahtalar.json`'da listelenen diğer 6 "aktif sınıf" tahtasında
`~/farabi/client/` dizini bile yok — Farabi hiç kurulmamış.

## 11. Auth — üründe ZORUNLU (2026-08-30'da tamamlandı, bu satır önceden bayattı)

Bu bölüm önceden "kod hazır, yürürlükte DEĞİL" diyordu — o an doğruydu ama
aynı gün (2026-08-30) durum değişti ve satır hiç güncellenmedi; 2026-08-31'de
doğrudan doğrulanarak (401 testi) düzeltildi.

`server/auth.py` (`dogrula_tahta`, tüm router'lara `Depends()` ile bağlı)
`X-Farabi-Board-Key` header'ını `board_keys`'e karşı doğruluyor, ve artık:
- `core/tahta.py::auth_headers()`/`tahta_anahtari()` yazıldı; `main.py` +
  6 `actions/*.py` dosyası + `core/saglayicilar.py` bu header'ı GERÇEKTEN
  gönderiyor (`client/tests/test_board_auth.py` 5/5).
- **9-A** için gerçek bir `board_keys` anahtarı üretildi, hem
  `server/config/api_keys.json`'a hem 9-A'nın kendi
  `client/config/api_keys.json`'ına yazıldı. Diğer 6 kayıtlı tahta
  (9-B/10-A/11-A/11-B/12-A/12-B) için placeholder anahtar var ama Farabi
  client onlarda hiç kurulu değil, henüz kullanılmıyor.
- `/etc/systemd/system/farabi-api.service.d/override.conf`
  (`FARABI_AUTH_REQUIRED=0`, acil rollback anahtarı) **kaldırıldı**,
  `farabi-api.service` yeniden başlatıldı.

**2026-08-31'de canlıda doğrulandı:** header'sız istek → 401
(`POST /api/egitim/ders_kaydi_yedek` ile test edildi), 9-A'nın gerçek
anahtarıyla → 200. `FARABI_AUTH_REQUIRED` varsayılanı zaten güvenli tarafta
(env değişkeni hiç verilmezse auth AÇIK kalır, `server/auth.py`) — acil
kapatma yalnızca env değişkenini elle `0` yaparak mümkün, şu an hiçbir yerde
öyle bir ayar yok.

## 12. Veri katmanı (PostgreSQL + pgvector)

| Tablo | Amaç |
|---|---|
| `kitap` | kitap metadata (sinif, ders, dosya_yolu, hash) |
| `chunk_egitim` | RAG'ın kullandığı metin chunk'ları + embedding (1024-dim) |
| `chunk_tablo` | **2026-08-30 eklendi, 2026-09-02'de RAG'A BAĞLANDI** (§5) — tablo verisi (§13), `chunk_egitim`'den AYRI tablo ama artık aynı sorguda ikinci kaynak. Şu an yalnızca `biyoloji-9` dolu (67 tablo) |
| `metrik` | yalnızca süre+durum+skor, içerik yok, süresiz saklanır |
| `soru_log` | düşük-skorlu/reddedilen soru-cevap metni, süresiz (2026-08-18'de bilinçli karar) |
| `tahta_durum` | heartbeat (derslik, commit_hash, son_heartbeat) |
| `yks_gosterim` | YKS soru gösterim geçmişi (tekrar göstermemek için) |
| `kazanim` | **2026-08-31 eklendi** — MEB öğretim programı kazanım kod+metni (kod, sinif, ders, unite, metin), `kod` UNIQUE. Henüz yalnızca Fizik/DKAB/İnkılap dolu — bkz. §12.1 |
| `kazanim_test_soru` | **2026-08-31 eklendi** — MEB ÖDSGM kazanım testi soruları + embedding, `chunk_egitim`'den AYRI, henüz RAG'a bağlı değil — bkz. §12.1 |

### 12.1 Kazanım katmanı — Hedef → Kanıt → Araç tasarımı (2026-08-31)

Kullanıcının belirlediği tasarım ilkesi, `core/prompt.txt`'e de eklendi
(aynı gün) — üç tablo bu üç rolü karşılıyor, birbirinin yerine geçmiyor:

1. **Hedef** (`kazanim`) — öğrencinin edineceği beceri/kazanım, MEB öğretim
   programından (`/mnt/farabi-data/farabi/ogretim_program/`). Ders anlatımının
   ÇERÇEVESİ budur, içerik değildir.
2. **Kanıt** (`kazanim_test_soru`) — bu kazanımın edinildiğini gösterecek
   değerlendirme sorusu, MEB ÖDSGM kazanım testlerinden
   (`/mnt/farabi-data/farabi/kazanim_test/`).
3. **Araç** (`chunk_egitim`, ders kitabı) — Hedef'e ulaşmak ve Kanıt'ı
   çözebilecek yetkinliği kazandırmak için kullanılan içerik/etkinlik
   havuzu — kendi başına amaç değil.

`chunk_egitim.kazanim_kod` kolonu bu üç tabloyu birbirine bağlamak için
DB'de zaten var ama kod tarafında hâlâ hiçbir sorguda okunmuyor/
filtrelenmiyor (RAG Kuralları, kök `CLAUDE.md`) — bu üçlü tasarım
`kazanim_kod` filtresini gerçek bir sonraki adım yapıyor, ama `server/rag.py`
sorgu mantığını değiştirmek hâlâ ayrı bir onay gerektiriyor (Kural 6).
Şu an yalnızca veri katmanı (kazanim + kazanim_test_soru dolduruldu) hazır,
bağlama mantığı yazılmadı.

## 13. Tablo çıkarma pipeline'ı (FAZ 1, 2026-08-30)

Kullanıcı isteği: ders kitaplarındaki tabloları (hücre/sütun ilişkisi
korunarak) RAG'a bağlamak. **`chunk_tablo`'nun retrieval'a dahil edilmesi
(eski "FAZ 3") 2026-09-02'de YAPILDI ve ölçüldü — bkz. §5.** Grafik/şekil
anlama (eski "FAZ 2") hâlâ yapılmadı; onun mimari önerisi ve ölçümleri
kökteki `plan.md`'de (2026-09-02 durum tespiti raporu). Çıkarma hattı
bilinçli olarak küçük/güvenli tutuldu:

```
client/tools/tablo_cikar.py  → pdfplumber.find_tables() + kalite filtresi
                                (≥2 satır, ≥2 sütun, ≥%50 dolu hücre —
                                aksi hâlde kapak sayfası gibi sahte tespitler)
                              → icerik/tablolar/<kitap>.json
benchmark/embed_tablo.py     → bge-m3 (CPU) ile embed → chunk_tablo (pgvector)
```

Pilot: `biyoloji-9.pdf`, 67 gerçek tablo çıkarıldı ve embed edildi. GPU/
Docker gerektirmiyor — kullanıcının kendi kararı: "elimizde bir sürü API
var, multimodal için kullanabiliriz" — grafik/şekil FAZ 2'de mevcut bulut
`gorsel_uret()` zinciri (§7) yeniden kullanılacak, yeni model kurulmayacak.

## 14. Kısıtlar (bilinçli, tekrar açılmadan önce sorulmalı)

- **Öğrenci kimliği/profili tutulmaz** — tek mikrofon, "anonim öğrenci",
  diarization yok. `memory/` paketi kod olarak duruyor ama çalışma zamanına
  BAĞLI DEĞİL.
- **Eğitim içeriği (kitap metni, RAG cevabı) dış buluta gönderilmez** —
  embedding/LLM tamamen yerel (Ollama, bge-m3, pgvector). Ses bunun TEK
  istisnası.
- **Systemd, Docker değil.**
- **Öğretmen her zaman kazanır** — `ders_motoru.py`'nin temel invaryantı.
- **Ölçmeden optimizasyon yapma.**
