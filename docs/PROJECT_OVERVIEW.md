# FARABİ PROJESİ GENEL BAKIŞ (PROJECT OVERVIEW)

> **2026-11-01 canlı model/port doğrulaması:** Yoklama Panosu **80**, Atos/AnythingLLM **8010**; Ollama istemci adı **`farabi`**, aynı digest ile **`qwen3.8:27b`**. Eski model çağrısı üretim modelini tahliye edebileceğinden kullanılmamalıdır.

> **Belge Sürümü:** 1.0.0  
> **Tarih:** 29 Ekim 2026  
> **Denetçi:** Kıdemli Sistem Mimarı & Kod Denetçisi  
> **Depo Yolu:** `/home/ata/farabi`  
> **Aktif Çalışma Dalı:** `atos-anythingllm-gemma`

---

## 1. Yönetici Özeti

**Farabi**, lise düzeyindeki bir eğitim kurumunun tüm dijital, operasyonel, donanımsal ve yapay zekâ ihtiyaçlarını entegre biçimde karşılamak üzere tasarlanmış, dağıtık ve çok bileşenli bir **Okul Otomasyon ve Akıllı Asistan Platformudur**.

Sistem; sınıflardaki Raspberry Pi / Orange Pi / Linux tabanlı akıllı tahtalar, merkezi yerel sunucu (2× NVIDIA RTX 3060 12 GB), RTSP güvenlik kameraları, dijital panolar, SMS bilgilendirme gateway'i ve öğrenci/öğretmen/yönetici web portallarından oluşmaktadır.

### Temel İstatistikler
- **Python Kod Tabanı:** 9 ana alt proje (`server`, `client`, `tahtayoklama`, `okul`, `smssistemi`, `soruhavuzu`, `kazanimtest`, `kelebek`, `osym`).
- **Toplam Test Sayısı:** 1.637 adet otomatik test (1.635 başarılı, 2 adet `smssistemi` HTTP 410 testi güncellenmeyi bekliyor).
- **Aktif Systemd Servisleri:** 8 adet servis daemon, 4 adet timer aktif çalışmaktadır.
- **Veri Saklama Katmanı:** PostgreSQL 16 (`okul_ana`, pgvector) + 6 farklı SQLite veritabanı + JSON/YAML yapılandırma dosyaları.
- **Yapay Zekâ Katmanı:** Yerel Ollama `farabi` takma adı (`qwen3.8:27b`, 49152 bağlam, süresiz yüklü) + tahtalarda Gemini Live. RAG ve embedding servisi kalıcı kapalıdır.

---

## 2. Alt Projelerin Görev ve Kapsam Envanteri

| Alt Proje / Dizin | Teknoloji & Çatılar | Port / Çalışma Modu | Sorumluluk / İşlevi |
| :--- | :--- | :--- | :--- |
| **`server/`** | FastAPI, Uvicorn, WebRTC (aiortc), WebSocket, ChromaDB | Port 8000 (Systemd: `farabi-api`) | Akıllı tahta asistanı arka yüzü: STT (Whisper), LLM yönlendirme (Ollama/Gemini), TTS (Edge/Piper), RAG, WebRTC ses kanalı, tahta durum telemetry. |
| **`client/`** | PyQt6, QWebEngine, WebRTC, PyAudio/SoundDevice | İstemci (Fiziksel Akıllı Tahtalar) | Akıllı tahta asistan arayüzü, wake-word dinleme, ekran karartma, ders programı/yoklama entegrasyonu. |
| **`tahtayoklama/`** | Flask / FastAPI, Jinja2, SQLite, Paramiko (SSH) | Port 80 (Systemd: `farabi-yoklama-dashboard`) | Sınıf akıllı tahtalarının anlık yoklama bildirimleri, ders zili yönetimi, uzaktan komut/SSH çalıştırma, kamera izleme. |
| **`okul/`** | FastAPI, SQLite, Jinja2, Tailwind, Chart.js | Port 9090 (Systemd: `farabi-okul`) | Öğrenci, veli, öğretmen ve idari portal. Notlar, ödevler, devamsızlık, analitikler, soru bankası, sudoku, pano yönetimi. |
| **`smssistemi/`** | FastAPI, SQLite, Netgsm API | Port 8020 (Systemd: `farabi-smssistemi`) | Toplu veli/öğrenci/personel SMS gönderimi, devamsızlık ve doğum günü şablonları, onay akışı. |
| **`soruhavuzu/`** | FastAPI, PostgreSQL (`okul_ana`), pgvector | Bağımsız / API Modülü | Müfredat kazanımlarına göre vektörel soru havuzu, TYT/AYT soru arama, soru üretim döngüleri. |
| **`kazanimtest/`** | FastAPI, SQLite, ReportLab (PDF) | Bağımsız Servis | MEB kazanım kavrama testleri derleme, öğrenciye özel test kitapçığı (PDF) üretimi. |
| **`kelebek/`** | FastAPI, Python Algoritmaları | Port 8050 (Systemd: `farabi-kelebek`) | Ortak sınavlarda kopya önleyici Kelebek Dağıtım Algoritması (öğrenci-sınıf optimizasyonu). |
| **`osym/`** | Python Kütüphanesi | Kütüphane / Modül | YKS/ÖSYM yerleştirme puan hesaplama, standart sapma ve net analizi. |
| **`kameralar/`** | Python, OpenCV, RTSP, go2rtc | Arka Plan Servisi (Systemd: `farabi-kameralar`) | Sınıf ve koridor RTSP kamera akışlarının proxy edilmesi ve yoklama/güvenlik snapshot üretimi. |
| **`tahtaayar/`** | Python CLI / GUI | Bakım Aracı | Akıllı tahtaların ağ ayarları, IP atamaları ve SSH provisioning otomasyonu. |
| **`mudur/`** | CLI / Python Betikleri | İdari Otomasyon | e-Okul / MEB Excel/CSV çıktılarının ayrıştırılması ve sisteme aktarımı. |

---

## 3. Donanım ve Altyapı Mimarisi

- **Merkezi Sunucu:**
  - **İşlemci / Bellek:** Çok çekirdekli Linux Host, 64 GB+ RAM.
  - **GPU:** 2× NVIDIA GeForce RTX 3060 12 GB — Ollama `qwen3.8:27b`, istemci adı `farabi`; toplam yaklaşık 19 GB VRAM, 49152 bağlam. `gemma4:12b` diskte bulunur, üretimde kullanılmaz. RAG ve embedding servisi kalıcı kapalıdır.
  - **İşletim Sistemi:** Linux (Ubuntu 24.04 LTS tabanlı, systemd tabanlı servis yönetimi).
- **Ağ ve Uç Cihazlar:**
  - Kurum içi VLAN / LAN ağı (`192.168.1.0/24` ve `10.x.x.x` alt ağları).
  - 30+ Akıllı Tahta (Raspberry Pi 4 / Orange Pi 5 veya x86 mini PC).
  - Cloudflare Tunnel entegrasyonu (dış erişim: `okul.farabi...`, `sms.farabi...`).

---

## 4. Giriş Noktaları (Entry Points)

| Servis | Giriş Dosyası | Başlatma Komutu / Systemd Servisi |
| :--- | :--- | :--- |
| **Farabi API** | `server/main.py` | `systemctl start farabi-api` (`uvicorn server.main:app --host 0.0.0.0 --port 8000`) |
| **Okul Portalı** | `okul/app.py` | `systemctl start farabi-okul` (`uvicorn okul.app:app --host 0.0.0.0 --port 9090`) |
| **Yoklama Dashboard** | `tahtayoklama/dashboard/app.py` | `systemctl start farabi-yoklama-dashboard` (systemd `port80.conf` drop-in → port 80) |
| **SMS Sistemi** | `smssistemi/app.py` | `systemctl start farabi-smssistemi` (`uvicorn smssistemi.app:app --host 0.0.0.0 --port 8020`) |
| **Atos / AnythingLLM** | `/opt/anythingllm` | `pm2-anythingllm.service`, port **8010** |
| **Kelebek Sistemi** | `kelebek/app.py` | `systemctl start farabi-kelebek` (`uvicorn kelebek.app:app --host 0.0.0.0 --port 8050`) |
| **Kamera Servisi** | `kameralar/` | `systemctl start farabi-kameralar` |
| **Tahta İstemcisi** | `client/main.py` | Tahta üzerinde autostart (`python -m client.main`) |

---

## 5. Güvenlik, Gizlilik ve Kısıtlamalar

1. **Hassas Bilgiler:** Proje; öğrencilere, velilere ve personele ait kişisel verileri (KVKK) içermektedir. `.env`, API anahtarları, şifre hashleri ve kimlik bilgileri git reposu dışında veya korumalı tutulmaktadır.
2. **Kritik Süreçler:** Okul saatleri içinde yoklama, ders zili ve akıllı tahta servisleri kesintisiz çalışmalıdır. Yapılacak tüm güncellemeler geriye dönük uyumlu ve minimal riskli olmalıdır.
