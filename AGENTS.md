# Farabi Projesi Genel Teknik Rehberi (`AGENTS.md`)

Bu belge, Farabi monoreposunun genel teknik mimarisini, servis haritasını, teknoloji yığınını ve geliştirici ajanlar için operasyonel standartları tanımlar.

---

## 1. Projenin Amacı
Farabi, Şehit Murat Ustaoğlu Anadolu Lisesi akıllı tahtalarında çalışan yapay zekâ destekli sesli ders asistanı ile aynı sunucu altyapısında barındırılan okul operasyon servislerini (yoklama panosu, SMS otomasyonu, dijital okul portalı, ortak sınav kelebek dağıtımı, interaktif tahta oyunları, 3D dijital ikiz ve kamera izleme) tek bir çatı altında birleştiren entegre okul ekosistemidir.

---

## 2. Gerçek Mimari ve Servis Haritası
Farabi, mikroservis benzeri bağımsız çalışan systemd servislerinden oluşur. Her servisin kendi izole Python sanal ortamı (`venv/`), portu ve veritabanı bulunur. Docker kullanılmaz; servisler doğrudan sunucu işletim sistemi üzerinde koşar.

| Servis Adı | Dizin | Port | Protokol / Framework | Görev Özeti |
|---|---|---|---|---|
| `farabi-api` | `server/` | 8000 | FastAPI / Uvicorn | Merkezi eğitsel beyin, MEB müfredat/kitap içerikleri, YKS arama, LLM proxy, ders görseli arşivi |
| `farabi-yoklama-dashboard` | `tahtayoklama/dashboard/` | 80 | FastAPI + React / Jinja2 | Akıllı tahta yoklama panosu, uzaktan tahta yönetimi, acil durum siren/anons, okul veri merkezi |
| `farabi-smssistemi` | `smssistemi/` | 8020 | FastAPI + Uvicorn | Toplu/bireysel SMS, devamsızlık ve doğum günü SMS otomasyonu (Müdür PC GSM modem köprüsü) |
| `farabi-okul` | `okul/` | 9090 | FastAPI / smual.app | Mobil öncelikli dijital okul portalı (Cloudflare Tunnel ile dışa açık), Soru Maratonu, Bilgi Arenası |
| `farabi-kelebek` | `kelebek/` | 8050 | FastAPI / ReportLab | Kelebek ortak sınav salon ve oturma düzeni dağıtımı, PDF yoklama listesi üretimi |
| `sinif-arena` | `arenasinif/` | 8030 | FastAPI / Uvicorn | Akıllı tahtalarda oynanan çok oyunculu ders yarışmaları (Sınıf Arenası, Düello, HexaFetih) |
| `farabi-atlas` | `tahtaatlasfarabi/` | 8099 | FastAPI + D3 / MapLibre | Yerel çevrimdışı Türkiye/Dünya harita laboratuvarı ve 3D küre oyunları |
| `progmatik` | `progmatik/` | 8060 | FastAPI + React + CP-SAT | Google OR-Tools CP-SAT çözücülü kısıt bazlı ders programı planlayıcı |
| `farabi-kameralar` / `hareket` | `kameralar/` | 8889 | MediaMTX / WebRTC | RTSP kamera akışlarının WebRTC'ye dönüştürülmesi ve harekete/yangına duyarlı kayıt |
| `farabi-okul3d` | `okul3d/` | 8095, 8096 | Stdlib HTTP / Three.js | Okul binası ve yerleşkesinin WebGL 3D dijital ikizi ve ortak mimari/oda adları API'si |
| `pm2-anythingllm` | `/opt/anythingllm` | 8010 | Node.js / AnythingLLM | Atos: Okul idari asistanı ve yerel veritabanı sorgulayıcı agent yetenekleri |
| *(Tahta İstemcisi)* | `client/` | — | PyQt6 + Gemini Live | Sınıf akıllı tahtalarında koşan sesli asistan arayüzü ve araç yürütücüsü |

---

## 3. Teknoloji Yığını
- **Backend:** Python 3.14 / 3.11, FastAPI, Starlette, Uvicorn, Jinja2, Pydantic v2.
- **Frontend:** React 19 / Vite, TypeScript, Tailwind CSS (Ortak cam tema `cam-tema.css`), Framer Motion, vanilla HTML5/ES modülleri, Three.js (r128 & r187), D3.js.
- **Veritabanları:**
  - PostgreSQL: `okul_ana` (ana okul verisi), `soru_havuzu` (merkezi soru arşivi), `farabi` (temel sistem DB).
  - SQLite (WAL modu): `yoklama_pano.db`, `smssistemi.db`, `okul.db`, `sonuclar.db` (arena), `kelebek.db`, `progmatik.db`, `atlas.db`.
- **Yapay Zekâ & LLM:**
  - Akıllı Tahta Sesi: Google Gemini Live WebSocket API (`google.genai`).
  - Yerel LLM: Ollama (`qwen3.8:27b`, servisler tarafından `farabi` takma adıyla çağrılır, `127.0.0.1:11434`, `think:false`).
- **Görüntü / PDF / Çözücü:** PyMuPDF (fitz), Pillow, ReportLab, Google OR-Tools CP-SAT.
- **Medya & Donanım:** MediaMTX (WebRTC), FFmpeg (H.264 transcoding), Huawei HiLink LTE Modem, ALSA / PulseAudio.

---

## 4. Ana Klasörlerin Görevleri
- `server/`: Merkezi FastAPI backend servisi. Kitap, YKS, kazanım ve Atos veri uçları.
- `tahtayoklama/`: Tahtalarda koşan dokunmatik PyQt6 `yoklama.py` arayüzü, `tahta_istemci.py` senkronizasyon servisi ve `dashboard/` yönetim paneli.
- `smssistemi/`: Toplu SMS gönderimi, devamsızlık/doğum günü otomasyonları ve modem proxy entegrasyonu.
- `okul/`: smual.app üzerinden öğrencilere, velilere ve öğretmenlere açık olan dijital portal.
- `client/`: Tahtada çalışan ince PyQt6 sesli asistan istemcisi, Gemini Live döngüsü ve yerel eylemler (`actions/`).
- `arenasinif/`: Tahtalarda interaktif oynanan Sınıf Arenası, Düello ve HexaFetih oyun motoru.
- `kelebek/`: Kelebek sınav salonu dağıtım motoru ve PDF yoklama çizelgesi oluşturucu.
- `progmatik/`: Okul ders programı planlama aracı (Google OR-Tools CP-SAT çözücüsü).
- `tahtaatlasfarabi/`: Çevrimdışı coğrafya/tarih harita oyunları servisi.
- `kameralar/`: Güvenlik kameraları WebRTC yayınları ve hareket algılama motoru.
- `okul3d/`: Üç boyutlu okul modeli, bahçe mimarı ve kat/tahliye planı üreticisi.
- `soruhavuzu/`: PostgreSQL tabanlı onaylı soru ve görsel arşivi, öğretmen PDF katkı işleyicisi.
- `anythingllm/`: Atos AnythingLLM kurulum scriptleri ve özel SQL/SMS ajan yetenekleri.
- `tahtaayar/`: Yeni kurulan tahtaların işletim sistemi/oturum ayarlarını tek tıkla yapılandıran provizyon aracı.
- `tahtamasaustuduzeni/`: Gece tahta masaüstü kısayollarını ve HGM Küre yazılımını eşitleyen bakım aracı.
- `benchmark/`: Eski RAG ve LLM ölçüm harness'ları.
- `mudur/`: İdari kaynak ve çalışma dosyaları.
- `kazanimtest/`: Arşivlenmiş kazanım test modülü (kalıcı kapalı).

---

## 5. Servisler Arası İletişim
Servisler arası iletişimde temel kural **gevşek bağlılık (loose coupling)** ve **HTTP/JSON API** kullanımıdır:
1. **İstisna Salt-Okunur DB:** `smssistemi`, panonun `yoklama_pano.db` SQLite veritabanını salt-okunur (`mode=ro`) okuyarak devamsız öğrencileri tespit eder.
2. **Pano → SMS:** `tahtayoklama/dashboard/veli_mesajlari.py`, SMS göndermek için `smssistemi` HTTP API'sini (`config/sms_panel.json`) çağırır.
3. **Pano → Okul İzinleri:** Dashboard, Dijital Okul'dan veli izinlerini almak için `GET /api/izinler` (`X-Izin-Anahtar`) çağrısı yapar.
4. **Tahta İstemcisi → Pano:** `tahta_istemci.py`, yoklama kayıtlarını ve nabzını `POST /api/v1/tahta/*` uçlarına token doğrulamalı gönderir.
5. **Tahta İstemcisi → Server:** `client`, eğitsel sorular ve ders içeriği için `server/` uçlarına `X-Farabi-Board-Key` ile istek atar.
6. **Atos → Dashboard:** Atos SQL yeteneği, panonun `/api/okul/sql` ucuna `X-Farabi-Okul-Key` ile bağlanarak bellek içi geçici SQLite üzerinden salt-okunur sorgu çalıştırır.

---

## 6. Kurulum, Çalıştırma ve Test Komutları

### Test Komutları Tablosu
```bash
# Server testleri (pytest)
cd /home/ata/farabi/server && venv/bin/python -m pytest tests/ -q

# Yoklama panosu testleri (unittest - DİKKAT: pytest YOKTUR)
cd /home/ata/farabi/tahtayoklama/dashboard && venv/bin/python -m unittest discover -p 'test_*.py'

# SMS sistemi testleri (pytest)
cd /home/ata/farabi/smssistemi && venv/bin/python -m pytest -q

# Dijital okul portalı testleri (pytest)
cd /home/ata/farabi/okul && venv/bin/python -m pytest -q

# Tahta istemcisi testleri (pytest)
cd /home/ata/farabi/client && venv/bin/python -m pytest tests/ -q

# Sınıf arenası testleri (pytest)
cd /home/ata/farabi/arenasinif && venv/bin/python -m pytest -q

# Kelebek sınav sistemi testleri (pytest)
cd /home/ata/farabi/kelebek && venv/bin/python -m pytest tests -q

# Progmatik ders programı testleri (pytest + npm)
cd /home/ata/farabi/progmatik && venv/bin/python -m pytest tests -q && cd frontend && npm test

# Atlas harita oyunları testleri (pytest)
cd /home/ata/farabi/tahtaatlasfarabi && .venv/bin/python -m pytest tests/test_atlas.py -q
```

### Servis Yönetimi (Üretime Alma)
Canlı kod dizini tek olduğundan master dalına commit sonrası ilgili servisin systemd birimi yeniden başlatılır:
```bash
sudo systemctl restart farabi-api.service
sudo systemctl restart farabi-yoklama-dashboard.service   # YALNIZCA 08:00-17:00 TR DIŞINDA!
sudo systemctl restart farabi-smssistemi.service
sudo systemctl restart farabi-okul.service
sudo systemctl restart farabi-kelebek.service
sudo systemctl restart sinif-arena.service
sudo systemctl restart farabi-atlas.service
sudo systemctl restart progmatik.service
sudo systemctl restart farabi-kameralar.service
sudo systemctl restart farabi-okul3d.service
```

---

## 7. Kodlama Standartları
1. **Cerrahi Değişiklik:** Yalnızca görevin gerektirdiği kod satırlarına dokunun. Komşu kodları "düzeltmeye" veya refactor etmeye kalkışmayın.
2. **Önce Oku, Varsayma:** Kodu değiştirmeden önce ilgili fonksiyonun gerçek uygulamasını, tip dönüşümlerini ve çağıran yerleri okuyun.
3. **Statik Denetim (Lint):** Dokunulan her dosya `.venv-tools/bin/ruff check <dosya>` ile taranmalı; F821/F811/F632 hataları sıfır olmalıdır.
4. **Ortak Cam Teması (Tailwind 4):** Arayüzlerde ortak stil `ortak/cam-tema/` altındaki derlenmiş `cam-tema.css` dosyasından beslenir. Servislerin kendi `static/` klasöründeki kopyalar korunmalı ve `?v=` önbellek parametreleri güncellenmelidir.
5. **CRLF Satır Sonları:** `okul/` altındaki dosyalarda satır sonu formatına dikkat edilmeli, gereksiz diff oluşturulmamalıdır.

---

## 8. Güvenlik Kuralları
1. ⚠️ **Repo PUBLIC'tir:** GitHub deposu açık olduğundan kişisel veriler (öğrenci/veli isimleri, TC kimlik no, telefon numaraları, devamsızlık ayrıntıları) kesinlikle depoya aktarılamaz.
2. **Kimlik Bilgileri ve Anahtarlar:** `.env`, `gizli.json`, modem şifreleri, API keyleri veya tokenlar commit edilemez.
3. **Öğrenci Verisi Buluta Gitmez:** Öğrenci listeleri ve veli telefonları harici bulut API'lerine veya kapalı LLM'lere gönderilmez. Yerel işler yerel Ollama (`farabi`) ile çözülür.
4. **Git Sparse-Checkout Kısıtı:** `git sparse-checkout set/reapply` komutunu ASLA çalıştırmayın (izlenmeyen canlı dizinleri silebilir).

---

## 9. Değişiklik Sonrası Doğrulama Adımları
1. **Statik İnceleme:** Dokunulan dosyanın import ve sözdizimi doğruluğunu `ruff` veya `py_compile` ile test edin.
2. **Birim Testleri:** İlgili modülün yukarıda belirtilen test komutunu çalıştırın ve tüm testlerin eksiksiz geçtiğini (`passed` / `OK`) teyit edin.
3. **Diff Kontrolü:** `git diff` çıktısını inceleyerek yalnızca amaçlanan satırların değiştiğini kontrol edin.
4. **Servis Logları:** Servis yeniden başlatıldıysa `journalctl -u <servis> -n 30` ile çalışma başlangıcını ve port dinlemesini doğrulayın.

---

## 10. Alt Klasörlerdeki Özel Talimatlara Yönlendirmeler
Her alt servisin kendine özgü mimarisi ve geliştirme kuralları ilgili klasördeki teknik belgelerde yer alır:
- **Server:** [server/AGENTS.md](file:///home/ata/farabi/server/AGENTS.md)
- **Yoklama Tahta Katmanı:** [tahtayoklama/AGENTS.md](file:///home/ata/farabi/tahtayoklama/AGENTS.md)
- **Yoklama Dashboard:** [tahtayoklama/dashboard/CLAUDE.md](file:///home/ata/farabi/tahtayoklama/dashboard/CLAUDE.md)
- **SMS Sistemi:** [smssistemi/AGENTS.md](file:///home/ata/farabi/smssistemi/AGENTS.md)
- **Dijital Okul Portalı:** [okul/AGENTS.md](file:///home/ata/farabi/okul/AGENTS.md)
- **Tahta İstemcisi:** [client/AGENTS.md](file:///home/ata/farabi/client/AGENTS.md)
- **Sınıf Arenası:** [arenasinif/AGENTS.md](file:///home/ata/farabi/arenasinif/AGENTS.md)
- **Kelebek Sınav Sistemi:** [kelebek/AGENTS.md](file:///home/ata/farabi/kelebek/AGENTS.md)
- **Progmatik Ders Programı:** [progmatik/AGENTS.md](file:///home/ata/farabi/progmatik/AGENTS.md)
- **Farabi Atlas:** [tahtaatlasfarabi/AGENTS.md](file:///home/ata/farabi/tahtaatlasfarabi/AGENTS.md)
- **Kameralar:** [kameralar/AGENTS.md](file:///home/ata/farabi/kameralar/AGENTS.md)
- **Okul 3D:** [okul3d/AGENTS.md](file:///home/ata/farabi/okul3d/AGENTS.md) & [okul3d/yeni-mimari/AGENTS.md](file:///home/ata/farabi/okul3d/yeni-mimari/AGENTS.md)
- **Soru Havuzu:** [soruhavuzu/AGENTS.md](file:///home/ata/farabi/soruhavuzu/AGENTS.md)
- **Atos Yetenekleri:** [anythingllm/AGENTS.md](file:///home/ata/farabi/anythingllm/AGENTS.md)
- **Tahta Ayar / Provizyon:** [tahtaayar/AGENTS.md](file:///home/ata/farabi/tahtaayar/AGENTS.md)
- **Tahta Masaüstü Düzeni:** [tahtamasaustuduzeni/AGENTS.md](file:///home/ata/farabi/tahtamasaustuduzeni/AGENTS.md)
- **Benchmark:** [benchmark/AGENTS.md](file:///home/ata/farabi/benchmark/AGENTS.md)
- **Müdür Dosyaları:** [mudur/AGENTS.md](file:///home/ata/farabi/mudur/AGENTS.md)
- **Kazanım Testi (Arşiv):** [kazanimtest/AGENTS.md](file:///home/ata/farabi/kazanimtest/AGENTS.md)
