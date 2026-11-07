# Farabi Sunucusu (`/home/ata/farabi`) Klasör Yapısı, Servisler ve Sanal Ortamlar (`venv`)

**Son Güncelleme:** 2026-11-03  
**Ana Üretim Dizini:** `/home/ata/farabi` (`master` dalı)  
**Ana Yönetim Paneli:** `http://farabi.local/` (`192.168.23.20:80` — `farabi-yoklama-dashboard.service`)

---

## 1. `http://farabi.local/` Paneli Hangi Klasörleri Kullanıyor?

`http://farabi.local/` (Port **80**) doğrudan **`farabi-yoklama-dashboard.service`** servisidir ve yalnızca `/home/ata/farabi` içindeki alt klasörleri kullanır:

### A. Ana Kod & Arayüz Klasörü (Doğrudan Çalıştığı Yer)
- **`/home/ata/farabi/tahtayoklama/dashboard/`** (`app.py`, `menu.py`, `veri/yoklama_pano.db`, `venv/`)

### B. Panelin Doğrudan Okuduğu / Veri Senkronize Ettiği Klasörler
- **`/home/ata/farabi/okul/`** → Dijital Okul (`smual.app` :9090) veritabanı (`okul/veri/okul.db`), veli mesajları, öğrenci/personel senkronizasyonu (`okul_ana_yayin.py`) ve aylık özetler.
- **`/home/ata/farabi/smssistemi/`** → İletişim menüsündeki SMS gönder, Yoklama SMS, Otomasyon ve Doğum günleri sayfaları (:8020 SSO yönlendirmesi ve `smssistemi/veri/smssistemi.db`).
- **`/home/ata/farabi/kameralar/`** ve **`/mnt/farabi-data/kamera-kayit/`** → Güvenlik menüsündeki DVR/IP kameralar (:8889), kamera kayıtları ve hareket algılama durumu (`kameralar/hareket/durum.json`).
- **`/home/ata/farabi/server/`** → Tahtalara uzaktan SSH komutu gönderme (`server/tahta-ssh.sh`, `server/tahtalar.json`) ve `farabi-api` (:8000) durum kontrolü.
- **`/home/ata/farabi/kelebek/`** → Eğitim menüsündeki Kelebek sınav dağıtım sistemi (:8050).
- **`/home/ata/farabi/okul3d/`** → Yoklama menüsündeki **"3D Okul Menüsü"** (`http://192.168.23.20:8095/`, `menu.py` satır 54).
- **`/home/ata/farabi/kazanimtest/`** ve **`/mnt/farabi-data/farabi/kazanim_testleri/`** → Kazanım raporları.

---

## 2. `/home/ata/farabi` İçindeki Alt Klasörlerin Durumu

### A. Canlı Çalışan Servis Klasörleri (Aktif)
- **`server/` (5.4 GB):** `farabi-api.service` (:8000) ve `soru-havuzu-uret` zamanlayıcısının kullandığı ana Python ortamı (`server/venv`).
- **`tahtaatlasfarabi/` (297 MB):** `farabi-atlas.service` (:8099 — 3D Küre / Harita).
- **`kameralar/` (290 MB):** `farabi-kameralar.service` (:8889, `mediamtx` + `ffmpeg`) ve `farabi-hareket.service` (`kameralar/hareket/venv`).
- **`okul/` (263 MB):** `farabi-okul.service` (:9090 — `https://smual.app` Dijital Okul portalı, `okul/venv`).
- **`tahtayoklama/dashboard/` (177 MB):** `farabi-yoklama-dashboard.service` (:80 — `http://farabi.local/` ana yönetim paneli, `tahtayoklama/dashboard/venv`).
- **`kelebek/` (171 MB):** `farabi-kelebek.service` (:8050 — Ortak sınav salon dağıtım sistemi, `kelebek/venv`).
- **`smssistemi/` (149 MB):** `farabi-smssistemi.service` (:8020 — Veli SMS, devamsızlık SMS ve doğum günü otomasyonu, `smssistemi/venv`).
- **`arenasinif/` (63 MB):** `sinif-arena.service` (:8030 — Akıllı tahta sınıf yarışmaları, `arenasinif/venv`).
- **`okul3d/` (1.6 MB):** Şehit Murat Ustaoğlu Anadolu Lisesi 3D Dijital İkiz modeli (:8095 / :8096).
- **`soruhavuzu/` (1.2 MB):** `soru-havuzu-uret.timer` (Hafta içi 17:15'te otomatik soru üretir; `server/venv` ortamını kullanır).

### B. Sunucuda Servisi Olmayan Ama Akıllı Tahtalar İçin Tutulan Klasörler (Silinmemeli)
Bu klasörler Farabi'de bir arka plan servisi olarak çalışmaz ama akıllı tahtaların güncellenmesi, bakımı ve veri okuması için kullanılır:
- **`tahtamasaustuduzeni/` (166 MB):** Akıllı tahtaların masaüstü kısayollarını ve HGM Küre programını tahtalara senkronize eden bakım aracı (`bakim.py`).
- **`client/` (18 MB):** Akıllı tahtalarda çalışan sesli/görsel Farabi ders asistanının kaynak kodu (GitHub üzerinden tahtalara çekilir).
- **`mudur/` (3.6 MB):** Ders programı (`ders_programi.json`) ve idari veri dosyaları (`farabi-okul` buradan ders programını okur).
- **`tahtagoruntuyakala/` (504 KB) & `tahtaayar/` (88 KB):** Tahta ekran görüntüsü yakalama ve Pardus ETAP ayar betikleri.
- **`anythingllm/` (80 KB):** Atos (:8010) SQL ve tablo ajan yetenekleri (`skills/`).

### C. Çalışmayan / Pasif Klasörler
| Klasör | Boyut | Neden Çalışmıyor / Ne İşe Yarıyordu? |
| :--- | :--- | :--- |
| **`tahtayoklama/venv`** | **72 MB** | Bu `venv` akıllı tahtalardaki masaüstü yoklama arayüzü (`PyQt6`) içindir; Farabi sunucusunda çalışan `farabi-yoklama-dashboard` servisi kendi `tahtayoklama/dashboard/venv` ortamını kullanır. Sunucuda bu 72 MB'lık üst `venv` kullanılmıyor. |
| **`.venv-tools`** | **59 MB** | 2 Eylül'de kod analizi (`ruff`, `bandit`, `vulture`) için kurulmuş eski bir araç sanal ortamı; hiçbir servis kullanmıyor. |
| **`benchmark`** | **17 MB** | Eski RAG ve model karşılaştırma raporları (`reports/`). RAG sistemi 31 Ekim'de kalıcı olarak iptal edildiği için aktif bir görevi yok (`benchmark/venv` 1.5 GB temizlendi). |
| **`_arsiv`** | **3.4 MB** | Eski OpenWebUI teması, eski doğum günü botu (`dogum/`) ve Eylül ayı analiz notlarının tutulduğu arşiv klasörü (`_arsiv/dogum/venv` 212 MB temizlendi). |
| **`kazanimtest`** | **636 KB** | Google Form kazanım testleri. Zamanlayıcıları (`kazanim-test*.timer`) 14 Ekim'de silindi, şu an çalışmıyor. |
| **`tahtaduyuru`** | **4 KB** | Tamamen boş klasör (içinde hiçbir dosya yok). |

---

## 3. Sanal Ortamlar (`venv` & `node_modules`) Envanteri

| Sanal Ortam Yolu | Boyut | Kullanan Servis | Durum |
| :--- | :--- | :--- | :--- |
| `/home/ata/farabi/server/venv` | **5.4 GB** | `farabi-api.service` (:8000), `soru-havuzu-uret.service` (PyTorch + CUDA 13) | 🟢 Aktif |
| `/home/ata/farabi/kameralar/hareket/venv` | **235 MB** | `farabi-hareket.service` (OpenCV hareket algılama) | 🟢 Aktif |
| `/home/ata/farabi/kelebek/venv` | **169 MB** | `farabi-kelebek.service` (:8050) | 🟢 Aktif |
| `/home/ata/farabi/smssistemi/venv` | **142 MB** | `farabi-smssistemi.service` (:8020) | 🟢 Aktif |
| `/home/ata/farabi/tahtaatlasfarabi/.venv` | **136 MB** | `farabi-atlas.service` (:8099) | 🟢 Aktif |
| `/home/ata/farabi/tahtayoklama/dashboard/venv` | **135 MB** | `farabi-yoklama-dashboard.service` (:80 — `http://farabi.local/`) | 🟢 Aktif |
| `/home/ata/farabi/tahtaatlasfarabi/node_modules` | **111 MB** | `tahtaatlasfarabi` önyüz derleme paketleri | 🟡 Derleme |
| `/home/ata/farabi/okul/venv` | **100 MB** | `farabi-okul.service` (:9090 — `smual.app`) | 🟢 Aktif |
| `/home/ata/farabi/tahtayoklama/venv` | **72 MB** | Sunucuda kullanılmıyor (Tahta PyQt6 masaüstü ortamı için) | ⚪ Pasif |
| `/home/ata/farabi/arenasinif/venv` | **61 MB** | `sinif-arena.service` (:8030) | 🟢 Aktif |
| `/home/ata/farabi/.venv-tools` | **59 MB** | Sunucuda kullanılmıyor (`ruff`, `bandit`, `vulture` statik analiz) | ⚪ Pasif |
| ~~`/home/ata/farabi/benchmark/venv`~~ | ~~1.5 GB~~ | — | 🗑️ Silindi (2026-11-03) |
| ~~`/home/ata/farabi/_arsiv/dogum/venv`~~ | ~~212 MB~~ | — | 🗑️ Silindi (2026-11-03) |

---

## 4. `/home/ata/` Kök Dizininden Temizlenen Eski Worktree ve Klasörler (2026-11-03)

Aşağıdaki eski Git worktree kopyaları ve pasif klasörler diskten kaldırılmıştır (~605 MB):
- `farabi-v2` (463 MB — `v2-yerel-ses` dalı, 07 Ekim)
- `farabi-tasarim` (31 MB — `panel-yeniden-tasarim` dalı, 31 Ekim)
- `farabi-wt-mikro` (30 MB — `mikro-gorev` dalı, 25 Ekim)
- `farabi-panel-kenar-menu` (27 MB — `panel-kenar-menu` dalı, 23 Ekim)
- `farabi-agy` (25 MB — `agy/rag-iyilestirme` dalı, 05 Ekim)
- `farabi-wt-katman` (25 MB — `kazanim-katmani` dalı, 10 Ekim)
- `farabi_dataset_collector` (3.9 MB — pasif veri toplama betiği, 01 Kasım)

**`/home/ata/` altında kalan aktif `farabi*` klasörleri:**
1. **`/home/ata/farabi`** (`master` ana üretim monoreposu)
2. **`/home/ata/farabi-audit`** (`farabi-audit-watcher.service` ve `farabi-audit.timer` aktif denetim servisi)
