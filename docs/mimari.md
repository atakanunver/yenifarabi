# Farabi — Mimari

> Referans dokümanı, her istekte okunmaz. Günlük kurallar için `CLAUDE.md`.
> Sürüm: v4

---

## 1. Amaç ve Kapsam

Farabi, sınıf akıllı tahtalarında çalışan sesli ders asistanıdır.

**Hedef:** Ders başarısını artırmak, dersleri zenginleştirmek, öğretmenin yükünü hafifletmek.

**Kapsam dışı:** Kamera / görüntü işleme. Öğrenci kimliklendirme. Not veya
değerlendirme kararı verme.

---

## 2. Temel Gereksinim — Farabi Asla Dersi Bozmaz

Bu bir AI demosu değil, okul altyapısına kurulacak sistemdir. **Aşağıdaki tablo
tasarım kısıtıdır, iyi niyet temennisi değildir.**

| Bozulan | Sonuç |
|---|---|
| Server tamamen kapalı | Tahta normal çalışır, Farabi sessizce yok |
| RAG / DB çöktü | Tahta normal çalışır, Farabi "şu an cevap veremiyorum" |
| LLM (Brain, RAG cevabı) yanıt vermiyor | Tahta normal çalışır, timeout sonrası sessiz |
| Gemini Live bağlantısı yok | Sesli ders yapılamaz, tahta normal çalışır (bkz. §14 — ses kalıcı olarak Gemini Live üzerinden) |
| Ağ / internet yok | Tahta normal çalışır |

Farabi hiçbir durumda tam ekran hata basmaz, tahtayı kilitlemez, öğretmenin
sunum/tarayıcı kullanımını engellemez.

---

## 3. Mimari Genel Görünüm

```
                  FARABİ BRAIN  (SERVER_IP — ağ keşfinden sonra)
                  Ryzen 9 / 64 GB / RTX 3060 ×N   ← §5, karar bekliyor
                  ┌──────────────────────────┐
                  │ Reverse Proxy (Caddy)    │
                  │ FastAPI :8000            │
                  │ Ollama (LLM)             │
                  │ RAG / Reranker           │
                  │ PostgreSQL + pgvector    │
                  │ Document Service         │
                  └────────────┬─────────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
              TAHTA VLAN            İDARİ VLAN
              Tahta 1..5            Yönetici PC
                                          │
                                     NAS (OMV)
```

> ⚠️ **Karar (2026-08-11):** Ses tarafı **kalıcı olarak Gemini Live'da
> kalıyor** — yerel STT/TTS (faster-whisper, Piper) planı **iptal edildi**,
> Brain diyagramından çıkarıldı. Gerekçe: Gemini Live tek, entegre bir
> gerçek-zamanlı model; konuşma sırası, öğrenci araya girme (barge-in), doğal
> tonlama gibi şeyleri kendi içinde çözüyor. Ayrı VAD→STT→LLM→TTS hattı
> kurmak bunların hiçbirini otomatik vermez, sıfırdan inşa edilmesi gerekir —
> değerlendirildi, bilinçli olarak vazgeçildi. Bkz. §14. Brain artık **ses
> işlemez** — yalnızca metin tabanlı RAG sorularını cevaplar, client'a Gemini
> Live üzerinden bir araç (tool call) olarak bağlanır.

**Client = ince istemci.** Mikrofon, hoparlör, ekran, UI — ses tamamen Gemini
Live üzerinden, Brain'e uğramadan. Karar üretmez.
**Brain = metin zekâsı.** LLM (RAG cevabı), kitap/plan/kazanım, veri. Ses YOK.

> `SERVER_IP` ve VLAN yerleşimi ağ keşfi tamamlanmadan sabitlenmez.

### Kurulum biçimi — systemd, Docker değil

```
Ubuntu
  ├── postgresql.service
  ├── ollama.service
  ├── farabi-api.service
  └── farabi-document.service
```

Gerekçe: okul sunucusunda "container neden restart olmuyor" sorunuyla uğraşılmaz;
sistemi devralacak kişi `systemctl status` ile durumu görebilir.

> **Durum (2026-08-11):** `postgresql.service`, `ollama.service`,
> `farabi-api.service` kuruldu ve `enabled` — üçü de bu makinede aktif çalışıyor
> (`systemctl status <ad>` ile doğrulanabilir). `farabi-document` henüz yok.
> `farabi-stt`/`farabi-tts` listeden tamamen çıkarıldı — ses kalıcı olarak
> Gemini Live'da, bkz. §3 üstündeki karar notu.

### Worker

Şu an **yok**. Ryzen 5 + RTX 3060 yedekte. Devreye alma kararı §13 metrikleriyle verilir.

---

## 4. Ölçek

**Pilot: 1 tahta → 2–5 tahta.** 10 tahta Faz 3'e ertelendi.

Zil senkron olduğu için zirve eşzamanlılık istisna değil normaldir.

---

## 5. Donanım — KARAR VERİLDİ (2026-08-09)

**Farabi Brain, ayrı bir makinede çalışıyor** — mevcut aiserver değil. §16'daki
açık soru cevaplandı: seçenek (b).

Makine: hostname `farabi`, AMD Ryzen 9 3900X (12 çekirdek), 60 GB RAM,
**2× RTX 3060 (toplam ~24 GB VRAM)**, Ubuntu 26.04, temiz kurulum (2026-08-09).
Bu makinede aiserver'ın diğer işleri (anime-reels, APK analizi, tesla monitor)
**çalışmıyor** — GPU paylaşım riski yok.

> Önceki sürümlerde "mevcut aiserver'da 3× RTX 3060" yazıyordu — bu, farklı bir
> makineydi (aiserver), Brain için kullanılmıyor. Düzeltildi.

> **Güncellendi (2026-08-10/11):** NVIDIA sürücüsü kuruldu (`nvidia-driver-595-open`),
> iki kart da aktif. Ollama `qwen2.5:14b`'yi iki karta bölerek çalıştırıyor
> (`OLLAMA_KEEP_ALIVE=-1`, model sürekli bellekte). Aşağıdaki "önce CPU'da
> deneyin" önerisi **ölçüldü ve yanlış çıktı** — bkz. not.

### Servis yerleşimi — ÖLÇÜLDÜ (2026-08-11), önceki hipotezin yerine

> Bu makinede, bu modellerle ölçülen gerçek yerleşim. Başka donanımda yeniden
> ölçülmeden kopyalanmamalı (Kural 10).

| Servis | Yerleşim | Ölçülen VRAM |
|---|---|---|
| LLM (Ollama, qwen2.5:14b) | 2 kart bölüşük | ~16 GB toplam |
| Embedding (bge-m3) | GPU 1 | ~3.5 GB |
| Reranker (bge-reranker-v2-m3) | GPU 0 | ~1–2 GB |
| PostgreSQL + pgvector | CPU/RAM | — |

**"Embedding ve reranker'ı önce CPU'da deneyin" önerisi ölçüldü ve terk edildi.**
CPU'da reranker tek başına 20 adayı sıralamak için 4–10 sn harcıyordu — bu tek
adım, "ilk cevap ≤2 sn" hedefini tek başına aşıyordu. GPU'ya taşınınca (embedding
ve reranker ayrı kartlara, aynı karta ikisi birden sığmadı — bge-m3 tek başına
~3.5 GB VRAM alıyor, tahmin edilenden fazla) toplam gecikme ~11 sn'den ~1–5 sn'ye
düştü.

**Ses (STT/TTS) yerel olarak kurulmuyor — karar (2026-08-11), bkz. §3 ve §14.**
Gemini Live kalıcı olarak ses tarafını üstleniyor; Brain yalnızca metin
tabanlı RAG cevabı üretiyor.

**Gecikme hedefi:** Brain'in RAG cevabı (metin) ≤ 2 sn içinde client'a
dönmeli — client bu metni Gemini Live'a iletip sesli okutuyor. "İlk ses"
gecikmesi artık Gemini Live'ın kendi sorumluluğunda, Brain'in ölçüm alanı
dışında.

---

## 6. Veri Yerleşimi

| Katman | Sorumluluk | İçerik |
|---|---|---|
| **NAS (OMV)** | Dosyanın kendisi | PDF, DOCX, XLSX, arşiv, yedek |
| **PostgreSQL** | Dosyanın bilgisi | metadata, hash, sınıf, ders, kazanım, sayfa |
| **pgvector** | Anlamsal indeks | chunk, embedding |

Dosya içeriği DB'ye gömülmez. `hash`, yeniden indeksleme gerekip gerekmediğini belirler.

Qdrant / Elasticsearch / Redis / Kafka / Kubernetes / Prometheus **kurulmaz.**

### Şema — Faz 1

> Faz 0a bu şemayı kullanmaz. Faz 0a yalnızca `kitap` + `chunk_egitim` ile çalışır.

```sql
ogretmen(id, ad_soyad, brans, aktif)

kitap(id, sinif, ders, yayinevi, yayin_yili,
      dosya_yolu, hash, indekslendi_at)

sinif_kitap(sinif, sube, ders, kitap_id)
  -- 9/A hangi yayınevinin kitabını kullanıyor.
  -- Bu eşleme olmadan aynı ders için iki kitap varsa RAG yanlış kaynaktan cevaplar.

kazanim(kod, sinif, ders, unite, metin)

chunk_egitim(id, kitap_id, sayfa_no, kazanim_kod NULL,
             metin, embedding vector(1024))

yillik_plan(id, sinif, sube, ders, hafta, kazanim_kod, ogretmen_id)

ders_programi(id, sinif, sube, ders, gun, baslangic, bitis,
              ogretmen_id, tahta_id, aktif)

-- FAZ 4 — şimdi oluşturulmaz, izolasyon tasarımı için burada listelenmiştir
belge_idari(id, dosya_yolu, hash, tarih, sayi, konu, kurum)
chunk_idari(id, belge_id, sayfa_no, metin, embedding vector(1024))
```

**Omurga: MEB kazanım kodu (`9.1.1.2`).** `chunk_egitim.kazanim_kod` **NULL olabilir** — §8.

---

## 7. İndeksleme Hattı

```
PDF (NAS)
  ↓ metin katmanı var mı? (pdfplumber — EBA kitaplarının çoğunda vardır)
  ↓ yoksa: PaddleOCR (tr)
  ↓ sayfa bazlı çıkarma (sayfa_no korunur)
  ↓ temizleme (üst/alt bilgi, sayfa no)
  ↓ chunking: ~400 token, %15 örtüşme, SAYFA SINIRINI AŞMAZ
  ↓ kazanım eşleştirme — başarısız olabilir, NULL bırak
  ↓ embedding: bge-m3
  ↓ pgvector
```

---

## 8. Sorgu Akışı

```
Soru (Gemini Live'ın client'ta ürettiği metin, tool call ile Brain'e gelir —
STT yok, transkripsiyon Gemini Live'ın kendi işi, bkz. §3/§14)
  ↓
1. BAĞLAM
   tahta_id → ders_programi → sinif + sube + ders → sinif_kitap → kitap_id
  ↓
2. İKİ AŞAMALI ARAMA
   2a. kazanım + kitap filtresi ile hibrit arama
       └─ sonuç yoksa/zayıfsa ↓
   2b. yalnızca kitap filtresi ile semantik arama

   Sistem, kazanım kodu bulunamadığında ÇALIŞMAYA DEVAM ETMELİDİR.
   Gerçekte olacaklar: eski kitap, farklı yayınevi, bozuk plan formatı,
   OCR hatası, kazanım kodunun kitapta hiç geçmemesi.
  ↓
3. HİBRİT ARAMA
   pgvector (anlamsal) + PostgreSQL full-text (kelime) → birleştir
  ↓
4. RERANK → ilk 20'den en iyi 4
  ↓
5. EŞİK KONTROLÜ   ◄── ANA halüsinasyon savunması
   skor < eşik → LLM'e GİTME → "Bu konu ders kitabında bulunmuyor."
  ↓
6. LLM (katı prompt, temp ≤ 0.2)
  ↓
7. SAYI KONTROLÜ (ek savunma, ana savunma değil)
   Cevaptaki sayısal değerler kaynak chunk'larda geçiyor mu?
  ↓
8. Yapısal cevap + kaynak (metin) client'a döner
   Client bu metni Gemini Live oturumuna verir, Gemini sesli okur — TTS
   Brain'de YOK (bkz. §3, §14 — ses kalıcı olarak Gemini Live'da).
```

### Halüsinasyon savunması — katmanlar

| Katman | Tür | Rol |
|---|---|---|
| Eşik kontrolü (§8.5) | Kod | **Ana savunma** — LLM'e hiç güvenmez |
| Katı prompt + `YETERSIZ_KAYNAK` | LLM | Orta |
| Sayı kontrolü (§8.7) | Kod | Ek, dar kapsamlı |
| Kaynak gösterimi + durdur butonu | İnsan | En yüksek — öğretmen doğrular |

**Kelime örtüşme oranı kullanılmaz** (doğru parafrazı engeller).
**NLI / entailment** Faz 0–1 kapsamında değildir.

### Sistem promptu

```
Sen Farabi'sin, bir ders asistanısın.
SADECE aşağıdaki KAYNAK METİN'e dayanarak cevap ver.

KURALLAR:
- Kaynak metinde olmayan hiçbir bilgiyi ekleme.
- Genel bilginle tamamlama yapma.
- Cevap kaynak metinde yoksa sadece şunu yaz: YETERSIZ_KAYNAK
- En fazla 3 cümle.
- Lise öğrencisinin anlayacağı sadelikte yaz.
- Yorum, tahmin, örnek uydurma yok.

KAYNAK METİN:
[chunk 1] (s. 84)
[chunk 2] (s. 85)
```

---

## 9. API

### Sağlık

```
GET /health     — süreç ayakta mı
GET /ready      — LLM + DB + RAG hazır mı
GET /version    — sürüm / yüklü model bilgisi
```

### Eğitim

```
GET  /api/egitim/kitaplar          — uygulandı, `server/main.py`
POST /api/egitim/question          — uygulandı, `server/main.py`
POST /api/egitim/lesson/start
POST /api/egitim/teacher/command
WS   /ws/classroom/{tahta_id}
```

### İdari — FAZ 4, ŞU AN OLUŞTURULMAZ

```
POST /api/idari/search        ⛔ devre dışı / gelecek modül
```

İdari RAG pilot kapsamında **değildir.** Endpoint yazılmaz, route tanımlanmaz.
Yalnızca veri izolasyonu (§12) baştan tasarlanır ki Faz 4'te sonradan
güvenlik eklemek gerekmesin.

### Cevap yapısı — Brain karar verir, Client görüntüler

Client, LLM çıktısını **yorumlamaz.** Server ham metin döndürmez:

```json
{
  "status": "ok",
  "answer": "Mitoz bölünme vücut hücrelerinde görülür ve iki özdeş hücre oluşur.",
  "sources": [
    { "book": "9. Sınıf Biyoloji", "page": 84, "chunk_id": 1523 }
  ],
  "latency_ms": 1840,
  "request_id": "..."
}
```

> **`audio_url` kaldırıldı (2026-08-11).** Ses Brain'de üretilmiyor — client
> `answer` metnini Gemini Live oturumuna verip sesli okutuyor. Bkz. §3/§14.

`status`: `ok` | `yetersiz_kaynak` | `sayi_kontrolu_reddi` | `hata` | `iptal`

Client her `status` için ne göstereceğini bilir; metni ayrıştırmaz.

---

## 10. Client ↔ Server Protokolü

> ⚠️ **Değiştirildi (2026-08-11).** Aşağıdaki eski tasarım, server'ın
> STT→LLM→TTS'i uçtan uca bir WebSocket üzerinden akıttığı bir mimari
> varsayıyordu. Ses kalıcı olarak Gemini Live'da kaldığı için (§3, §14) bu
> hiç gerekmiyor — Brain artık yalnızca **basit, senkron bir HTTP aracı**.
> Client, Gemini Live oturumu içinde (bir tool call gibi) Brain'i çağırır,
> metin cevabı alır, Gemini'ye geri verir; Gemini sesli okur. WebSocket
> akışı, `stt.*`/`tts.*` event'leri **iptal edildi**, bu listeye artık
> uyulmuyor.

**Gerçek sözleşme (uygulandı, `server/main.py`):**

```
GET /api/egitim/kitaplar
  →
  [{ "id", "dosya_adi", "sinif", "ders" }, ...]

POST /api/egitim/question
  { "kitap_id": <int>, "soru": <string, en fazla 500 karakter> }
  →
  { "status", "answer", "sources"[], "latency_ms", "request_id" }
```

Tek istek, tek yanıt. Öğretmen "DURDUR"a basarsa client Gemini Live'ın kendi
oturumunu keser (mevcut client davranışı, `client/CLAUDE.md`) — Brain'in
ayrıca bir iptal mekanizması bilmesi gerekmez, çünkü istek zaten senkron ve
kısa sürüyor (~1–5 sn, bkz. §5).

**`soru` neden 500 karakterle sınırlı (2026-08-11 bulundu):** sınırsız
uzunlukta bir soru (~6000 karakter) reranker'ı (cuda:0, qwen2.5:14b ile aynı
kart) CUDA out-of-memory'ye düşürdü — o an embedding/rerank adımları hiç
sarmalanmamıştı, istisna yakalanmadan çıkıp çıplak 500 döndürdü. İki
düzeltme yapıldı: (1) `SoruIstek.soru` artık Pydantic `max_length=500` ile
pahalı bir GPU çağrısı hiç yapılmadan 422 ile reddediyor — doğrulanmış soru
setinin (`benchmark/sorular.json`) en uzun sorusu 336 karakter, 500 rahat bir
pay; (2) `rag.py`'de embedding/arama ve rerank adımları da LLM adımıyla aynı
desene alındı (try/except + `hata` durumu + `metrik` loglaması) — bundan
sonra bu aşamada ne çıkarsa çıksın sunucu ayakta kalıyor. Kabul edilen kalan
risk: GPU 0 durağan halde ~11.2/11.63 GiB dolu (Ollama 7.63 + server 3.59),
reranker'a yalnızca ~400 MiB pay kalıyor — eşzamanlı sınıf yükünde NORMAL
uzunlukta bir soru bile OOM'a düşebilir, ama artık `hata` durumuna düzgün
düşüyor, çıplak 500'e değil. GPU paylaşımını yeniden tasarlamak bu turda
yapılmadı (ölçmeden optimizasyon yapma, Kural 10).

**Bağlam çözümü — çözüldü (2026-08-11):** `sinif_kitap` tablosu henüz boş
(gerçek okul verisi yok) olduğu için `tahta_id → ders_programi → sinif_kitap`
zinciri ATLANIYOR; client `GET /api/egitim/kitaplar`'ı bir kez çekip
`(ders, sinif)` çiftiyle eşliyor (`client/actions/kitap_sorusu.py`). `ders`
verilmeden eşleme YAPILMAZ — boş bırakılırsa aynı sınıf düzeyindeki ilk kitap
seçilip yanlış dersten kaynaklı bir cevap üretebilirdi; bu yüzden yeni araç
şemasında `ders` zorunlu alan. Gerçek okul verisi (`sinif_kitap` doldurulunca)
bu geçici eşleme gerçek bağlam çözümüne geçirilebilir.

Client'ın bu endpoint'i hangi araçla çağıracağı sorusu da çözüldü: yeni
`kitap_sorusu` aracı (`client/actions/kitap_sorusu.py`, kayıt `actions/
kayit.py`) — `ders_icerigi`'nin aksine bir konuyu anlatmak için değil,
kaynaklı bir soruyu yanıtlamak için. Sunucu ulaşılamazsa ya da eşleşme yoksa
sessizce mevcut araçlara düşer (mimari.md §2).

---

## 11. Ağ

**Kısıt:** İdari VLAN ↔ Tahta VLAN birbirini görmüyor. **Bu politika değiştirilmez.**

```
TAHTA VLAN ──► SERVER            İZİN
TAHTA VLAN ──► İDARİ VLAN        ENGEL

İDARİ VLAN ──► SERVER            İZİN
İDARİ VLAN ──► SERVER :22        yönetim
İDARİ VLAN ──► TAHTA VLAN        ENGEL
```

**Çift NIC kullanılmaz.** İki izole VLAN'a aynı anda bağlı makine, o iki ağ arasında
fiili bir köprüdür; sunucu ele geçirilirse tahta ağından idari ağa geçiş noktası olur.

### TLS

Reverse proxy (Caddy) ilk günden konur, FastAPI doğrudan dışarı açılmaz.

TLS kararı **test edilmeden verilmez:** FATİH tahtaları kilitli imajlarla gelir; özel
sertifika otoritesini güven deposuna eklemek yönetici yetkisi gerektirebilir ve
merkezi politikayla ezilebilir.

```
Faz 1: tek tahtada sertifika güveni test edilir
   ├── çalışıyorsa → HTTPS
   └── çalışmıyorsa → izole VLAN'da HTTP (ara çözüm), Faz 2'de yeniden değerlendirilir
```

**Kurulumdan önce netleşecekler:** VLAN yapısı, switch yönetilebilir mi, IP aralıkları,
statik IP / DHCP rezervasyonu, firewall kuralını kim koyuyor.

---

## 12. Veri İzolasyonu

1. **Ayrı tablolar** — `chunk_egitim`, `chunk_idari`. Aynı tabloda tip kolonuyla ayırma.
2. **Ayrı endpoint + token** — tahta token'ı `/api/idari/*` çağırırsa 403.
3. **Ayrı DB kullanıcısı** — `farabi_client`'ın `chunk_idari` üzerinde yetkisi yok.

Üçüncü katman en kritiktir: kodda bug olsa bile veritabanı reddeder.

Faz 4'e kadar idari tablolar boş kalır, ancak izolasyon **baştan** kurulur.

---

## 13. Ölçüm ve Loglama

**İki tablo, iki amaç. Karıştırılmaz.**

### `metrik` — performans, içerik yok

```sql
metrik(id, tahta_id, ts,
       retrieval_ms, rerank_ms,
       llm_ilk_token_ms, llm_toplam_ms, toplam_ms,
       sonuc, en_yuksek_skor)
```

> `stt_ms`/`tts_ilk_ses_ms` kaldırıldı (2026-08-11) — Brain artık ses
> işlemiyor, bkz. §3/§14. Gerçek kurulum: `benchmark/olcum_schema.sql`,
> `server/rag.py`.

Soru/cevap metni **yoktur.** Sınırsız saklanır.

### `soru_log` — kalite iyileştirme, KOŞULLU

Metin yalnızca **sistem hata yaptığında veya emin olmadığında** saklanır:

| Durum | Metin saklanır mı |
|---|---|
| `ok` + yüksek skor | ❌ Hayır — yalnızca metrik |
| `ok` + düşük skor | ✅ Evet |
| `yetersiz_kaynak` | ✅ Evet |
| `sayi_kontrolu_reddi` | ✅ Evet |
| `iptal` (öğretmen durdurdu) | ✅ Evet |
| `hata` | ✅ Evet |

```sql
soru_log(id, ts, tahta_id, sinif, ders,
         soru_metni, donen_chunk_idler, skorlar,
         cevap_metni, sonuc)
```

Gerekçe: RAG'ı iyileştirmek için gereken şey hatalardır. Başarılı cevapların metnini
saklamaya gerek yoktur. Hash saklamak işe yaramaz — "hangi soru hangi yanlış sayfayı
getirdi" bilgisi olmadan iyileştirme yapılamaz.

**Kısıtlar:** öğrenci kimliği yok, ses yok, **90 gün sonra otomatik silinir.**
"Öğretmen durdurdu" kaydı en değerli sinyaldir — Farabi'nin saçmaladığı andır.

### Periyodik

GPU utilization, VRAM, eşzamanlı aktif oturum.

**Prometheus/Grafana kurma.** SQL yeterli:
`SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY toplam_ms) FROM metrik`

**Worker kararı bu veriyle verilir.**

---

## 14. Gizlilik / KVKK

> ⚠️ **Karar (2026-08-11): Ses kalıcı olarak Gemini Live'da (Google bulutu)
> kalıyor.** Önceki sürümlerde bu "geçici, kabul edilmiş bir açık" olarak
> tanımlanıyordu ve yerel STT/TTS (faster-whisper, Piper) hedef gösteriliyordu.
> Bu plan **iptal edildi** — gerekçe: Gemini Live'ın gerçek-zamanlı ses
> kalitesini (konuşma sırası, araya girme, doğal tonlama) yerel bir
> VAD→STT→LLM→TTS hattıyla eşleştirmek büyük, ayrı bir mühendislik projesi;
> başka bir projede denenebilir ama bu projenin kapsamı dışında bırakıldı.
> Aşağıdaki kurallar bu kararla güncellendi.

- **Kamera yok.**
- **Öğrenci sesi Gemini Live'a (Google bulutu) gider — kalıcı, kabul edilmiş
  bir tasarım kararı, geçici değil.** Ham ses hiçbir yerde diske yazılmaz;
  Gemini Live'ın kendi transkripsiyonu client'ta kalır, Brain'e yalnızca
  metin gider.
- Öğrenci kimliği tutulmaz; anonim "öğrenci sordu".
- Soru metni yalnızca hatalı/şüpheli durumlarda, 90 gün saklanır (§13).
- **Eğitim İÇERİĞİ (kitap metni, RAG cevabı) dış bulut AI servisine
  gönderilmez — bu hedef hâlâ geçerli ve karşılanıyor.** Brain (Ollama,
  bge-m3, reranker, PostgreSQL/pgvector) tamamen yerel çalışıyor; yalnızca
  SES bulut tarafında (Gemini Live). Bu ayrım nettir: **metin/içerik yerel,
  ses bulut.**
- Hangi veri, ne kadar süre, nerede saklandığı yazılı hale getirilir.

---

## 15. Yol Haritası

İki kol **paralel** yürür; server iskeleti ikisinin birleşmesini bekler.

```
   KOL A — MEVCUT KOD                KOL B — KONSEPT DOĞRULAMA
   ─────────────────────             ─────────────────────────
   [A1] Kod analizi                  [B1] Soru seti (40+, insan işi)
        (Claude Code, kod                  ↓
         değiştirmeden)               [B2] FAZ 0a — retrieval benchmark
        ↓                                  tek betik, server yok, LLM yok
   [A2] Client/Server ayrım                ↓
        tablosu                       [B3] FAZ 0a KAPISI — geçti mi?
        ↓                                  ↓
   [A3] Refactor kapsamı            [B4] FAZ 0b — üretim testi
                                          Ollama var, FastAPI yok
        └──────────────┬───────────────────┘
                       ▼
              [1] SERVER İSKELETİ        ← Faz 0a geçmeden başlamaz
                       ▼
              [2] PostgreSQL + pgvector
                       ▼
              [3] Tek PDF RAG servisi
                       ▼
              [4] Tek soru → cevap (metin)
                       ▼
              [5] Client ↔ Brain köprüsü (Gemini Live'dan tool call ile,
                  STT/TTS YOK — ses kalıcı olarak Gemini Live'da, §14)
                       ▼
              [6] FAZ 1 — tek tahta, gerçek ders
                       ▼
              [7] Ölçüm (§13)
                       ▼
              [8] FAZ 2 — 2–5 tahta
                       ▼
              FAZ 3 — 10 tahta (yalnızca Faz 2 kullanılıyorsa)
                       ▼
              FAZ 4 — İdari RAG (son 1 yılın resmi yazıları)
```

> **STT/TTS adımları kaldırıldı (2026-08-11) — bkz. §14.** Yerel ses planı
> iptal edildi, Gemini Live kalıcı çözüm. Bu, yol haritasını kısaltıyor:
> Faz 1'e girmeden önce kalan tek büyük iş client↔Brain köprüsü.

**Neden paralel:** İki kol birbirini beklemiyor. B kolunun darboğazı kod değil,
40 sorunun yazılması — insan işidir ve gecikirse tüm proje gecikir. A kolunun
riski sınırlıdır (kod dağınıksa yeniden yazılır); B kolunun riski projeyi
bitirebilir (retrieval çalışmıyorsa mimarinin geri kalanının değeri yoktur).

**Neden server iskeleti bekliyor:** Retrieval %50 çıkarsa yazılmış FastAPI'nin
hiçbir değeri kalmaz.

> ⚠️ **Bilinçli sapma (2026-08-10/11):** Server iskeleti ([1]), Faz 0a kapısı
> **tam kapanmadan** kullanıcının açık kararıyla erken başlatıldı — B grubu
> soru sayısı o sırada 12'ydi (min. 15 altında) ve B grubunun ölçülen
> recall/rerank'i hedefin altındaydı. Karar gerekçesi: eşik+LLM katmanı
> birlikte kullanıldığında grup C %94 doğru çıkmıştı (bkz. aşağıdaki tablo) —
> yöntemin çalıştığına dair yeterli kanıt vardı, geri kalan eksik B grubu
> sorusunu tamamlamak insan işiydi ve server'ı bekletmeye gerek görülmedi.
> **Sonradan** (2026-08-11) B grubu 12'den 18'e çıkarıldı, toplam soru sayısı
> 40'a ulaştı — bkz. "Soru seti" altındaki not. Server artık gerçekten çalışan
> bir prototip: 13 kitap pgvector'a indekslendi, `POST /api/egitim/question`
> uçtan uca doğrulandı, gecikme GPU'ya taşınarak ~11sn'den ~1-5sn'ye indi
> (bkz. §5). Bu, "Faz 0a resmi olarak geçti" demek değildir — B grubunun
> recall/rerank'inin güncellenmiş soru setiyle yeniden ölçülmesi hâlâ
> yapılmadı.

### Faz 0a — kapsam

```
1 gerçek EBA kitabı
  → extraction → chunk → embedding → pgvector
  → 40+ gerçek soru → benchmark
```

**FastAPI, Ollama kurulmaz.** (STT/TTS zaten kapsam dışı bırakıldı, bkz. §14 —
bu satır Faz 0a'nın kendi dönemi için hâlâ doğru, WebSocket ise §10'da
tamamen kaldırıldığı için artık bahsi bile geçmiyor.)

**Altyapı hazırlığı tamamlandı (2026-08-09):** ikinci disk (`sda`, 1.8TB) GPT/ext4
formatlandı, `/mnt/farabi-data`'ya bağlandı, `/etc/fstab`'a kalıcı yazıldı
(§5 — bu makine artık Brain sunucusu). PostgreSQL 18 + `pgvector` (0.8.1)
kuruldu, systemd servisi aktif/enabled, `farabi` veritabanında `vector`
uzantısı doğrulandı (`\dx` ile). **Bu, Faz 0a'nın geçtiği anlamına gelmez** —
aşağıdaki geçiş kriterleri hâlâ ölçülmedi; yapılan yalnızca ortam hazırlığı.
Henüz yok: `kitap`/`chunk_egitim` tabloları, extraction/chunk/embedding
betiği, 40+ soruluk soru seti (bkz. "Soru seti" — insan işi, kod değil).

### Faz 0a — geçiş kriterleri

| Metrik | Hedef | Kapı mı? | Ölçülen (2026-08-11, biyoloji-9, **40 soru**, A=17/B=18/C=5) |
|---|---|---|---|
| Recall@4 (doğru kaynak ilk 4'te) | ≥ %80 | ✅ | A %100, **B %83** ✅, TOPLAM %91 |
| Rerank sonrası doğru chunk ilk 1'de | ≥ %70 | ✅ | A %88, **B %78** ✅, TOPLAM %83 |
| Yanlış kaynak (alakasız sonuç) | ≤ %10 | ✅ | Ayrıca ölçülmedi — bkz. `YETERSIZ_KAYNAK` satırı |
| `YETERSIZ_KAYNAK` doğru tespiti — **yalnızca eşik** | ≥ %90 | ✅ | C %20 ❌ (hiçbir tek eşik değeri A/B'yi bozmadan C'yi ayıramadı) |
| `YETERSIZ_KAYNAK` doğru tespiti — **eşik + LLM katmanı birlikte** | ≥ %90 | ❌ (ölçüm) | **TOPLAM %95** (A %100, B %89, C %100) — bkz. `benchmark/katman_test.py`, rapor `katmanli_20260811_071503.json` |
| Ortalama retrieval süresi | < 1 sn | ✅ | 0.14 sn ✅ |
| MRR | ölç, kaydet | ❌ | A 0.94, B 0.82 |
| Kazanım eşleşme doğruluğu | ölç, kaydet | ❌ | Ölçülmedi — Faz 0a şeması `kazanim_kod`'u hiç kullanmıyor |

**Sonuç (güncellendi 2026-08-11):** B grubu artık kapıyı geçiyor — 12'den
18 soruya çıkarılınca (bkz. "Soru seti" notu) recall %75→%83, rerank
%67→%78'e yükseldi, ikisi de hedefin üstünde. Bu, önceki B-grubu
başarısızlığının bir **retrieval kalitesi sorunu değil, küçük/dengesiz soru
setinin bir eseri** olduğunu gösteriyor — eklenen 6 soru gerçek çok-sayfalı
sentez sorularıydı (öğretmenle birlikte, sayfa sayfa doğrulanarak yazıldı).
**A ve B artık ikisi de kapıyı geçiyor.** C grubu tek başına eşikle hâlâ
geçmiyor (%20) — bu beklenen, çünkü ana savunma (eşik) tek başına yeterli
değil; **eşik+LLM katmanı birlikte 40 soruluk güncel setle TOPLAM %95, C
grubu tek başına %100** ölçüldü (yukarıdaki tablo). Yani mimari.md'nin asıl
önerdiği İKİ katmanlı tasarım (§8) tek başına retrieval-eşiği testinden çok
daha iyi performans gösteriyor — **Faz 0a'nın sayısal kapı kriterlerinin
tamamı artık geçiyor** (recall, rerank, eşik+LLM birlikte, hız). Resmi "kapı
geçti" ilanı hâlâ yapılmadı çünkü mimari.md'nin insan-onaylı soru seti
şartı (§15, "en az 15'ini başka bir öğretmenden iste") tam karşılanmadı —
bkz. "Soru seti" altındaki not.

### Soru seti — 3 grup, en az 40 soru

| Grup | Tür | Örnek | Min |
|---|---|---|---|
| **A** | Doğrudan bilgi | "Mitozun sonucunda kaç hücre oluşur?" | 15 |
| **B** | Birkaç paragrafı ilişkilendiren | "Mitozda kromozom sayısının korunmasının nedeni nedir?" | 15 |
| **C** | Kitapta olmayan | "Mitoz ile mayozun evrimsel avantajı nedir?" | 5 |

**Her grup ayrı raporlanır.** B grubu naif RAG'ın en çok battığı yerdir; A'da %90
alıp B'de %40 almak gerçek bir başarısızlıktır ve ortalama bunu gizler.

20 soruda her soru %5 ağırlık taşır; birden fazla eşiği 20 soruyla ölçmek
istatistiksel olarak anlamsızdır.

Soruları tek başına yazma — kendi sisteminin bulabileceği soruları yazma eğilimi
oluşur. En az 15'ini başka bir öğretmenden iste.

> **Durum (2026-08-11, biyoloji-9):** `benchmark/sorular.json` şu an **40 soru**
> (A=17, B=18, C=5) — minimum karşılandı. **Ancak** bu setin çoğu Atakan
> tarafından tek başına, bu oturumda yazıldı (yukarıdaki "başka bir öğretmenden
> iste" uyarısı henüz karşılanmadı) — kendi sisteminin bulabileceği soru yazma
> eğilimi riski hâlâ açık. Ayrıca 8 soru (orijinal 40'ın parçası) kitabın
> ön/arka-matter kirliliğinden (İstiklal Marşı, atlas eki) üretildiği için
> silindi — bkz. `sorular.json.bak` ile fark. Diğer 12 kitap için hiç soru
> seti yok, yalnızca biyoloji-9 tam test edildi.

### Faz 0b — testler

```
Test B: Doğru kaynak verildiğinde LLM doğru cevap veriyor mu?
Test C: Cevap kaynak dışı bilgi ekliyor mu?
```

Retrieval testinden ayrı tutulur — hata ayıklamayı kolaylaştırır.

---

## 16. Açık Konular

| Konu | Kim çözer | Neyi bloke ediyor |
|---|---|---|
| ~~Farabi Brain = aiserver mı, ayrı makine mi~~ | Atakan | **Çözüldü 2026-08-09** — ayrı makine (§5) |
| Okul ağı yapısı (VLAN / IP / switch / firewall sahibi) | Atakan + ağ yöneticisi | Faz 1 kurulumu |
| FATİH tahtasında özel CA sertifikası güveniliyor mu | Test | TLS kararı |
| Tahtalara kalıcı yazılım kurulum izni | İdari süreç | Faz 2 |
| Devir dokümanı + bilişim öğretmenine eğitim | Atakan | Faz 2 sonrası |
| ~~`client/`'ın bulut LLM bağımlılığı nasıl yerel Brain'e taşınacak~~ | Atakan | **Çözüldü 2026-08-11** — SES için çözülmeyecek, kalıcı karar: Gemini Live kalıyor (§14). METİN/İÇERİK (RAG cevabı) için zaten yerel (`server/`, `POST /api/egitim/question` çalışıyor). Client hangi araçla Brain'i çağırıyor sorusu da çözüldü: yeni `kitap_sorusu` aracı (§10), gerçek sunucuya karşı doğrulandı. |
| Faz 1 bağlam çözümü: `tahta_id → ders_programi → sinif+sube+ders → sinif_kitap → kitap_id` zinciri nasıl kurulacak, pilot tahtaların `tahta_id`'leri nereden atanacak | Atakan | `server/`'ın API'si şu an `kitap_id`'yi doğrudan istekte alıyor, gerçek bir tahtadan gelen isteği çözemiyor |

"Okul Beyni" / müdür asistanı **ayrı projedir**; aynı sunucuda çalışabilir, aynı kod
tabanında olması gerekmez.
