# API VE ENTEGRASYONLAR (API & INTEGRATIONS)

> ⚠️ **DOĞRULANMAMIŞ — LLM üretimi (2026-10-29 toplu belge seti).** 2026-11-11 kod kontrolünde bu setteki belgelerin
> var olmayan dosyalara (`smssistemi/netgsm.py`, `server/services/stt_service.py`, `okul/rotalar/notlar.py`,
> `tahtayoklama/ziller/zil.py`) ve projede olmayan teknolojilere (Netgsm, go2rtc, Whisper, Nginx, Flask, `/home/pi`)
> atıf yaptığı görüldü. Kaynak değildir; bir bulguya göre iş yapmadan önce kodda doğrula. Esas: kök `AGENTS.md`,
> `docs/mimari.md`, `docs/runbook.md`, `DECISIONS.md`.

> **Belge Sürümü:** 1.0.0  
> **Tarih:** 29 Ekim 2026  
> **Kapsam:** Farabi platformunun dışa açılan uç noktaları, servisler arası REST/WS API'leri ve 3. parti entegrasyonları

---

## 1. Temel Servis API Uç Noktaları

### 1.1. `server/` (Farabi Akıllı Asistan API - Port 8000)

| Metot | Uç Nokta (Path) | Kimlik Doğrulama | Açıklama |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/chat` | Bearer Token / API Key | Metin tabanlı sohbet; RAG destekli yanıt üretimi. |
| `POST` | `/api/v1/voice/stt` | İsteğe Bağlı | Yüklenen ses dosyasını (WAV/MP3) metne çevirir (Whisper). |
| `POST` | `/api/v1/voice/tts` | İsteğe Bağlı | Metni ses dosyasına sentezler (Edge-TTS / Piper). |
| `POST` | `/webrtc/offer` | Açık / LAN | WebRTC ses kanalı el sıkışması (SDP Offer/Answer). |
| `GET` | `/ws/telemetry` | WebSocket | Tahta durumu, CPU/RAM sıcaklık ve aktiflik telemetrisi. |
| `GET` | `/health` | Açık | Servis sağlık kontrolü (GPU, Ollama, Veritabanı durumu). |

### 1.2. `okul/` (Öğrenci & Yönetim Portalı - Port 9090)

| Metot | Uç Nokta (Path) | Kimlik Doğrulama | Açıklama |
| :--- | :--- | :--- | :--- |
| `POST` | `/giris` | Form (Kullanıcı/Şifre) | Oturum açma; `session` cookie oluşturur. |
| `POST` | `/cikis` | Session | Oturumu sonlandırır. |
| `GET` | `/ogrenci/notlar` | Session (`OGRENCI`) | Öğrencinin ders notlarını ve karne ortalamasını listeler. |
| `GET` | `/ogrenci/devamsizlik` | Session (`OGRENCI`) | Özürlü/özürsüz devamsızlık gün ve saat dökümü. |
| `GET` | `/ogretmen/dersler` | Session (`OGRETMEN`) | Öğretmenin sorumlu olduğu sınıflar ve dersler. |
| `POST` | `/ogretmen/not-girisi` | Session (`OGRETMEN`) | Sınıf bazlı sınav notlarının toplu kaydedilmesi. |
| `GET` | `/api/pano` | IP Kontrolü / Session | Koridor panoları için nöbetçi öğretmen, yemek ve duyuru JSON'u. |
| `GET` | `/cozum-gorsel/{soru_id}` | Session | Soru çözüm görselini döndürür (*Bkz: Güvenlik Denetimi*). |
| `POST` | `/sifre` | Session | Kullanıcı şifre değiştirme (*Bkz: Güvenlik Denetimi*). |

### 1.3. `tahtayoklama/` (Yoklama ve Akıllı Tahta Yönetimi - Port 80)

| Metot | Uç Nokta (Path) | Kimlik Doğrulama | Açıklama |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/yoklama/kaydet` | Tahta Token / IP | Sınıf akıllı tahtasından anlık yoklama bildirimini kaydeder. |
| `GET` | `/api/yoklama/bugun` | Basic Auth / Session | Günün tüm sınıflara ait yoklama durum dökümü. |
| `GET` | `/api/kamera/video/{oda_id}` | Session / Local | go2rtc / RTSP kamerasından anlık görüntü/video alır. |
| `GET` | `/admin/uzaktan/ekran-goruntusu/{tahta_adi}` | Session | Tahtanın ekran görüntüsünü SSH üzerinden alır (*Bkz: Güvenlik Denetimi*). |
| `POST` | `/admin/uzaktan/komut-calistir` | Session (`MUDUR`) | Seçili tahtalarda uzaktan komut yürütür. |

### 1.4. `smssistemi/` (Toplu SMS Gateway - Port 8020)

| Metot | Uç Nokta (Path) | Kimlik Doğrulama | Açıklama |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/sms/gonder` | Session / API Key | Tekil veya toplu SMS gönderim emri oluşturur. |
| `GET` | `/api/sms/taslaklar` | Session | Onay bekleyen SMS taslaklarını listeler. |
| `POST` | `/api/sms/taslak/{id}/onayla`| Session | Taslağı onaylayıp Netgsm kuyruğuna gönderir. |
| `GET` | `/api/sms/raporlar` | Session | Gönderilen SMS'lerin iletim (DLR) durum raporları. |

---

## 2. Üçüncü Parti Harici Entegrasyonlar

### 2.1. Netgsm SMS API
- **Protokol:** HTTP POST (XML veya JSON REST).
- **Rol:** Öğrenci devamsızlıkları, acil durum duyuruları, veli toplantısı ve doğum günü kutlama mesajlarının GSM operatörlerine iletimi.
- **Kritik Davranış:** Kredi/bakiye kontrolü, numara formatlama (`+905xxxxxxxxx`), Türkçe karakter desteği.

### 2.2. Google Gemini API (Generative Language)
- **Model:** `gemini-2.0-flash`, `gemini-2.5-flash`.
- **SDK:** `google-genai` / Python SDK.
- **Rol:** Yerel GPU'nun yoğun olduğu saatlerde veya karmaşık çok modlu (multimodal - görsel soru çözümü) analizlerde bulut yedeği olarak devreye girer.

### 2.3. go2rtc & RTSP Kameralar
- **Protokol:** RTSP, H.264/H.265 video stream, WebRTC bridge.
- **Kullanım:** Sınıflardaki yoklama teyidi ve okul koridor güvenliği.

### 2.4. Cloudflare Tunnel
- **Protokol:** `cloudflared` agent üzerinden tünelleme.
- **Rol:** Statik IP veya port açma (port forwarding) zorunluluğu olmadan `okul.farabi...` adresinin güvenli biçimde dış dünyaya açılması.
