# Farabi 2.0 — Yerel Ses Hattı (Tasarım)

> Tarih: 2026-10-07 · Dal: `v2-yerel-ses` (`~/farabi-v2`) · Durum: onaylandı, uygulama planı bekliyor

## Amaç

Pilot sınıfta (9-A) tahta istemcisini Gemini Live olmadan, sesi okul ağının dışına çıkarmadan
çalıştırmak. İlk sürümde çalışması gerekenler:

- kitaptan soru cevaplama (mevcut RAG)
- ders anlatma (mevcut ders motoru)
- ekrandaki soruyu okuma
- sesli komutlarla tahta kontrolü (mevcut araçlar)

Gemini Live kodu (v1) silinmez; yedek olarak kalır (tag `v1.0-gemini-live`, dal `v1-gemini-live`).
Diğer 7 sınıf master'da kalır.

## Önceki kararla ilişki

Proje `CLAUDE.md` → "Şu An Yapılmayacaklar": yerel STT/TTS 2026-09-28'de donanım yetersizliği nedeniyle "kalıcı iptal" edilmişti. **2026-10-07'de kullanıcı kararıyla Farabi 2.0 için yeniden açıldı**; değişen koşul: Bilgehan (RTX 3060) ayrı ses donanımı olarak ağa katıldı ve Chatterbox hızlı yolu ölçüldü (RTF 0,45). Kural 8 gereği yeni bileşenler (faster-whisper, Chatterbox Multilingual) kullanıcı onayıyla eklenir. Bu karar yalnızca `v2-yerel-ses` dalı ve pilot sınıf için geçerli; master `CLAUDE.md` iptal notu pilot sonucu belli olunca güncellenir. Gizlilik bölümündeki "öğrenci sesi Gemini Live'a gidiyor" ifadesi yerel modda geçerli olmaz.

## Kararlar

| Konu | Karar |
|---|---|
| Dinleme biçimi | **Bas-konuş** (tahtada düğme). Uyandırma kelimesi ikinci aşama. |
| Gizlilik | Ses (STT/LLM/TTS) yerel. **Görsel okuma bulutta kalır** (mevcut `gorsel` zinciri: pixtral → mistral-medium → nvidia). |
| Döngünün yeri | **Tahtada** (Yaklaşım 1). Araçlar zaten tahtada çalışıyor (`FarabiLive._execute_tool`, `client/main.py`). |
| Ses | Chatterbox Multilingual, referans `nisan_kumru_2.wav`, exaggeration 0.7 / cfg_weight 0.3 / temperature 0.75, hızlı T3 yolu (`hizli_t3.py`). |
| LLM | Farabi Ollama `qwen3.8:27b`, `/api/chat` akışlı, `tools` ile, `think: false`. |
| Ses servisi kapalıysa | **Gemini'ye düşülmez.** Tahtada tam ekran OLMAYAN bir uyarı ("Ses servisi kapalı (Bilgehan)"), Farabi oturumu başlamaz, log; tahta normal kullanılmaya devam eder (Kural 2). |
| Riskli araçlar | Yoklama, dersi bitir, video aç → önce onay sorusu ("Yoklama alayım mı hocam?"). |
| Sunucu sürümü | Farabi sunucusunun `VERSION` ana sürümü **değiştirilmez** (master tahtaları HTTP 426 almasın). |

## Ölçülmüş dayanaklar (2026-10-07)

- Qwen sohbet: ilk token ~0,5 sn (araçsız), araçlarla ~1,5 sn (≈5.500 token araç tanımı, önek önbelleği tutmuyor); araç kararı ~3,5 sn (Ollama araç çağrısını akıtmıyor).
- Araç seçimi (16 araç, 36 cümle): 34/36; "selamlaşmada araç çağırma" kuralı şart (kuralsız: "Günaydın çocuklar" → uydurma `ders_icerigi`).
- Chatterbox (Bilgehan RTX 3060, CPU AMD FX-6100): orijinal 23,8 tok/s, RTF 1,23 → hızlı T3 (statik KV + CUDA graph) 89 tok/s, RTF 0,45. Darboğaz CPU'nun kernel başlatma yüküydü (GPU ort. %36).
- Boğulma kuyruğu referanstan bağımsız (derya eski 9/16, temizlenmiş 8/16) → model davranışı; hızlı yoldaki long_tail EOS koruması ve trim/kuyruk temizliği gerekli.

## Bileşenler

### Bilgehan: `farabi2-ses` servisi

(Ad bilinçli olarak eski, iptal edilmiş `farabi-ses` biriminden farklı.)

Tek süreç, `CUDA_DEVICE_ORDER=PCI_BUS_ID`, `CUDA_VISIBLE_DEVICES=1` (RTX 3060). `farabi-embed` (GPU0, :8040) ile Debian .251'e dokunulmaz. systemd birimi ile açılır.

- `POST /stt` — 16 kHz mono WAV → `{"metin": "...", "sure_ms": ...}`. faster-whisper `large-v3-turbo`, int8, `language="tr"`.
- `POST /tts` — `{"metin": "..."}` → 24 kHz mono 16-bit PCM WAV. Referans koşulları açılışta bir kez hazırlanır. Kalıp cümleler açılışta üretilip bellekte tutulur; metin birebir eşleşirse önbellekten döner. Çıkışta trim + `kuyruk.py` boğulma temizliği.
- `GET /saglik` — model durumları, VRAM, sayaçlar (istek, önbellek isabeti, boğulma kesilen).

STT ve TTS ayrı kilitlerle sıralanır (aynı model eşzamanlı çağrılmaz).

### Tahta istemcisi (`client/`)

- `core/yerel_oturum.py` (yeni) — `YerelOturum`: konuşma geçmişi, Qwen akışlı çağrısı, araç listesi `actions/kayit.bildirimler(kip)`'ten OpenAI şemasına çevrilir (dönüşüm `benchmark/v2_arac_testi.py`'deki mantıktan alınır), cümle bölücü, TTS kuyruğu → mevcut ses çalma kuyruğu, araç çağrısında mevcut `_execute_tool`.
- `core/ses_istemci.py` (yeni) — `/stt`, `/tts`, `/saglik` HTTP çağrıları ve zaman aşımları.
- `core/metin_duzelt.py` (yeni) — seslendirme öncesi biçimlendirme temizliği (yıldız, liste, başlık) ve Türkçe sıra sayısı düzeltmesi ("12. sınıf" → "on ikinci sınıf"); Chatterbox'un kendi düzeltmesinin üstüne.
- `main.py` — ayar bayrağı `ses_modu: gemini | yerel` (varsayılan `gemini`). `yerel` ise Gemini bağlantısı yerine `YerelOturum`.
- `ui.py` — bas-konuş düğmesi; mevcut DUR düğmesi yerel modda da çalışır.
- Talimat — v1 sistem talimatı + üç kural: konuşma diliyle 2-3 cümle; liste/biçimlendirme yok; selamlaşma ve sohbette araç çağırma yok.

Değişmeyenler: 20 aracın kodu, ders motoru, talimat kipi, RAG/kitap sunucusu, görsel okuma zinciri.

## Konuşma turu

1. **Bas** — kayıt başlar (16 kHz). Farabi konuşuyorsa önce susturulur.
2. **Bırak** — kayıt `/stt`'ye. 0,4 sn'den kısa kayıt ve boş metin yok sayılır. Metin `core/transcript.py` dökümüne yazılır.
3. **Qwen** — sistem talimatı + son N tur + o kipin araçları, akışlı.
4. **Metin** — cümle bölücü `. ? !` ile keser → `metin_duzelt` → `/tts` → ses kuyruğu. Sonraki cümleler ilki çalınırken üretilir.
5. **Araç çağrısı** — önce uygun kalıp cümle anında çalınır; araç `_execute_tool` ile (v1 zaman aşımlarıyla) çalışır; sonuç Qwen'e verilir; 4'e dönülür. Turda en fazla 3 araç.
6. **Tur sonu** — geçmiş güncellenir; ders motoru ve boşta gözcüsü bilgilendirilir.

**DUR** — Qwen akışı iptal, bekleyen TTS istekleri atılır, ses kuyruğu boşaltılır (`_sesi_sustur`); yarım cevap geçmişe "kesildi" notuyla yazılır.

## Hata durumları

| Durum | Davranış |
|---|---|
| Ders başında `/saglik` yanıt vermiyor | Tam ekran olmayan uyarı "Ses servisi kapalı (Bilgehan)", oturum başlamaz, log; tahta normal çalışır. Gemini'ye düşülmez. |
| Ders ortasında `/stt` hata / 5 sn zaman aşımı | Kalıp cümle "Sizi duyamadım hocam, tekrar söyler misiniz?"; TTS de kapalıysa ekranda mesaj. |
| `/tts` hatası | Cevap metni dökümde gösterilir; 3 ardışık hatada `/saglik` yeniden denetlenir. |
| Qwen meşgul | İlk token için 8 sn sınır; beklerken kalıp cümle; aşılırsa "Şu an yoğunum, birazdan tekrar sorar mısınız?". |
| Araç hatası | v1 `speak_error` deseni: hata araç sonucu olarak Qwen'e verilir, Qwen açıklar. |
| Riskli araç | Onay sorusu; öğretmen tekrar basıp "evet" demeden çalıştırılmaz. |

Kalıp cümleler (~25): bekleme ("Hemen bakıyorum", "Kitaba bakıyorum", "Ekrana bakıyorum"), onay ("Tamam", "Hemen açıyorum"), hata ("Sizi duyamadım", "Şu an yoğunum", "Ses servisi kapalı"), riskli araç onay soruları.

## Test

**Birim (istemci, `client/tests`, pytest; GPU/ağ yok)** — `farabi.local`'da `client/venv` yok; testler 9-A tahtasında koşulur (`server/tahta-ssh.sh 9-A "cd ~/farabi/repo/client && venv/bin/python -m pytest tests/ -q"`), 9-A `v2-yerel-ses` dalına geçtikten sonra.
- `metin_duzelt`: sıra sayıları, yıl + ek ("1923'te"), yüzde, biçimlendirme temizliği — tablo tabanlı.
- Cümle bölücü: kısaltmalar ("Dr.", "vb."), ondalık ("3.5"), `?`/`!`, parça parça gelen akış.
- `YerelOturum` (sahte Qwen/STT/TTS): sohbet turu, araçlı tur, 3 araç sınırı, DUR iptali, zaman aşımları, riskli araç onayı, servis kapalı hatası.
- Mevcut istemci testleri `ses_modu: gemini` iken aynen geçer.
- Son kabul testi fiziksel tahtada kullanıcı tarafından yapılır (Kural 12).

**Servis (Bilgehan)**
- `/stt`: önceden kaydedilmiş 20 Türkçe tahta cümlesi — kelime hata oranı ve süre.
- `/tts`: RTF < 0,6; kalıp cümle önbelleği < 50 ms; boğulma sayacı.
- VRAM: Chatterbox + Whisper yüklüyken GPU1 < 11,5 GB; GPU0 değişmemiş.
- `systemctl restart` sonrası kendiliğinden ayağa kalkma.

**Uçtan uca (Farabi'den, sınıftan önce)** — 36 cümlelik araç testi ses yoluyla (kayıt → STT → Qwen → araç → TTS). Hedefler:
- sohbet: düğme bırakıldıktan sonra ilk ses ≤ 3 sn
- araçlı tur: kalıp cümle ≤ 1 sn, gerçek cevap ≤ 7 sn
- araç seçme doğruluğu ≥ %90

## Pilot (9-A)

1. 9-A tahtası `v2-yerel-ses` dalına, ayarda `ses_modu: yerel`; diğer 7 sınıf master'da.
2. İlk gün öğretmen eşliğinde 1 ders; log'lardan tur gecikmesi, araç seçimi, hatalar toplanır.
3. Geri dönüş: `ses_modu: gemini` veya tahtayı master'a döndürmek.
4. 1 hafta sorunsuzsa uyandırma kelimesi aşaması.

## Kapsam dışı

Uyandırma kelimesi; sesle söz kesme ve yankı engelleme; yerel görsel model; 8 sınıf için merkezi ses kapısı (GPU kuyruğu); hızlı T3 yolunun Debian .251'e taşınması.

## Bilinen riskler

- Bilgehan VRAM'i dar (~10,5 / 12 GB tahmini) — kurulumda ölçülecek; sığmazsa Whisper `medium` int8.
- Bilgehan RAM 9,2 GB (kullanılabilir ~5 GB) — iki model birlikte yüklenince izlenecek.
- Qwen paylaşımlı (RAG, Open WebUI, soru üretimi/denetimi) — yoğun saatlerde gecikme artar.
- Tek 3060 aynı anda en fazla ~2 sınıfa ses üretebilir; pilot tek sınıf.
- Hızlı T3 yolunun ses kalitesi dinleyerek doğrulanmadı (`benchmark/reports/v2_chatterbox/hizli/`).
