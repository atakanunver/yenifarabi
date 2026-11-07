# OPERASYON VE DAĞITIM REHBERİ (DEPLOYMENT & OPERATIONS)

> **2026-11-01 canlı model/port doğrulaması:** Yoklama Panosu **80**, Atos/AnythingLLM **8010**; Ollama istemci adı **`farabi`**, aynı digest ile **`qwen3.8:27b`**. Eski model çağrısı üretim modelini tahliye edebileceğinden kullanılmamalıdır.

> **Belge Sürümü:** 1.0.0  
> **Tarih:** 29 Ekim 2026  
> **Kapsam:** Üretim ortamı servisleri, systemd birimleri, zamanlayıcılar, portlar, yedekleme ve felaket kurtarma

---

## 1. Üretim Ortamı Servis ve Süreç Durumu

Sistem genelinde Linux `systemd` ve `pm2` tarafından yönetilen aktif servislerin durumu:

| Servis Adı (Systemd Unit) | Port / Görev | Durum (Active State) | Açıklama |
| :--- | :--- | :---: | :--- |
| **`farabi-api.service`** | Port 8000 |  `active (running)` | Farabi AI Asistan, STT/TTS ve WebRTC arka yüzü. |
| **`farabi-yoklama-dashboard.service`** | Port 80 |  `active (running)` | Yoklama dashboard ve zil yönetim paneli; ana unit 8010, `port80.conf` drop-in etkin portu **80** yapar. |
| **`farabi-okul.service`** | Port 9090 |  `active (running)` | Öğrenci, veli ve yönetim web portalı. |
| **`farabi-smssistemi.service`** | Port 8020 |  `active (running)` | SMS dağıtım gateway servisi. |
| **`farabi-kelebek.service`** | Port 8050 |  `active (running)` | Kelebek sınav dağıtım motoru. |
| **`farabi-kameralar.service`** | Port 8554 |  `active (running)` | RTSP kamera akış ve proxy servisi (go2rtc). |
| **`farabi-embed.service`** | 127.0.0.1:8040 | `inactive (dead)` | RAG ve embedding kalıcı kapalı; 2026-11-01 systemd durumu doğrulandı. |
| **`ollama.service`** | Port 11434 |  `active (running)` | Yerel LLM: `farabi` takma adı = `qwen3.8:27b`, 49152 bağlam, süresiz yüklü; `gemma4:12b` diskte kullanılmıyor. |
| **`pm2-anythingllm`** | Port 8010 |  `active (running)` | Doküman sohbet arayüzü (PM2 yönetimli). |

---

## 2. Zamanlanmış Görevler (Systemd Timers)

| Zamanlayıcı Adı (Timer) | Tetiklenme Sıklığı | Durum | İşlevi |
| :--- | :--- | :---: | :--- |
| **`soru-havuzu-uret.timer`** | Her gün 02:00 |  `active` | Vektörel soru havuzu periyodik soru zenginleştirme. |
| **`farabi-tahta-karart-haftaici.timer`** | Hafta içi 17:30 |  `active` | Akıllı tahtaların otomatik ekran karartılması. |
| **`farabi-tahta-karart-haftasonu.timer`**| Hafta sonu 14:00 |  `active` | Hafta sonu nöbetçi ekran karartma. |
| **`farabi-idari-yukle.timer`** | - | ⏹️ `inactive` | e-Okul otomatik idari yükleme (Devre dışı - manuel kontrol). |
| **`farabi-okul-odev-uyari.timer`** | - | ⏹️ `inactive` | Ödev teslim uyarıları (Devre dışı bırakılmış). |

---

## 3. Donanım ve Kaynak İhtiyaçları

- **RAM:** Minimum 32 GB, önerilen 64 GB (Çoklu Python worker'lar ve SQLite WAL önbelleği için).
- **GPU:** 2× NVIDIA RTX 3060 12 GB — `qwen3.8:27b` (`farabi` takma adı) iki GPU'da yaklaşık 19 GB VRAM kullanır; bağlam 49152 ve keep-alive süresizdir.
- **Disk:** NVMe SSD (en az 500 GB) — Soru havuzu PDF'leri, kamera anlık görüntüleri ve pgvector indeksleri yüksek I/O gerektirir.

---

## 4. Yedekleme ve Geri Yükleme (Backup & Recovery)

### 4.1. Veritabanı Yedekleme
- **PostgreSQL (`okul_ana`):**
  ```bash
  pg_dump -U ata -d okul_ana -F c -b -v -f "/yedek/okul_ana_$(date +%Y%m%d).dump"
  ```
- **SQLite Veritabanları (`okul.db`, `yoklama.db`, `sms.db`):**
  - WAL modunda açıkken doğrudan dosya kopyalanmamalıdır! `sqlite3` online backup API kullanılmalıdır:
  ```bash
  sqlite3 /home/ata/farabi/okul/data/okul.db ".backup '/yedek/okul_$(date +%Y%m%d).db'"
  sqlite3 /home/ata/farabi/tahtayoklama/data/yoklama.db ".backup '/yedek/yoklama_$(date +%Y%m%d).db'"
  ```

### 4.2. Yapılandırma Dosyaları
- `tahtayoklama/data/zil.json`, `data/ders_programi.json` ve `.env` dosyaları günlük olarak şifrelenmiş arşivde saklanmalıdır.

---

## 5. Acil Durum Müdahale Prosedürü (Runbook)

### Senaryo 1: Ziller Çalmıyor / Tahtalar Senkronize Değil
1. `systemctl status farabi-yoklama-dashboard` kontrol edilir.
2. `tahtayoklama/data/zil.json` dosyasının geçerli bir JSON olup olmadığı denetlenir:
   `python3 -m json.tool tahtayoklama/data/zil.json > /dev/null`
3. Servis yeniden başlatılır:
   `sudo systemctl restart farabi-yoklama-dashboard`

### Senaryo 2: Yerel Asistan Yanıt Vermiyor (GPU / VRAM Dolması)
1. `nvidia-smi` çıktısı incelenir; VRAM doluluğu kontrol edilir.
2. Ollama servisi yeniden başlatılır:
   `sudo systemctl restart ollama`
3. Farabi API servisi yeniden başlatılır:
   `sudo systemctl restart farabi-api`
