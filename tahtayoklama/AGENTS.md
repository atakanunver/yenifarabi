# tahtayoklama

Sınıf akıllı tahtalarında dokunmatik yoklama arayüzü (PyQt6) + tahta istemcisi (`tahta_istemci.py`) + merkezi web panosu (`dashboard/`, FastAPI, port 80, `farabi-yoklama-dashboard.service`).

- **Farabi Sesli Asistanından Bağımsız:** Bu sistem Farabi sesli ders asistanı motorundan bağımsız çalışır; doğrudan akıllı tahta donanımı ve merkezi web panosu arasında köprü kurar.
- **İki Ana Katman:**
  1. **Tahta Tarafı:** Dokunmatik PyQt6 GUI (`yoklama.py`), arka plan senkronizasyon istemcisi (`tahta_istemci.py`), duyuru popup (`announcement_agent.py`) ve masaüstü acil alarm (`acil_alarm.py`).
  2. **Sunucu / Dashboard Tarafı (`dashboard/`):** FastAPI tabanlı yönetim paneli, uzaktan yönetim, yoklama analitiği, acil durum siren/anons yönetimi ve tahta API'leri. (Detaylar için [dashboard/CLAUDE.md](file:///home/ata/farabi/tahtayoklama/dashboard/CLAUDE.md)).

## Tahta Bileşenleri
- **`yoklama.py`** (tahta, PyQt6 GUI): Ağdan bağımsız çalışır; durum kaynağı tahta yerel diskindeki JSON dosyalarıdır (`data/kayitlar/`, `data/roster/`). Masaüstü kısayolu (`Yoklama.desktop`) üzerinden öğretmen tarafından elle açılır. Teneffüs saatlerinde ("aktif ders yokken") yoklama kaydı kilitlidir.
- **`tahta_istemci.py`** (tahta, arka plan servisi): `systemd --user` altında `tahta-istemci.service` olarak çalışır. Yalnızca standart kütüphane (stdlib) kullanır. `istemci.json` içindeki tahta token'ı ile sunucunun `/api/v1/tahta/*` uçlarına bağlanır; son 7 günün kayıtlarını SHA-256 hash kontrolüyle sunucuya iletir, her 60 sn nabız gönderir, 10 dk'da bir güncel roster ve zil/ders programını çeker.
- **`announcement_agent.py`** (tahta): Duyuru açılır penceresi (PyQt6). Sunucudan gelen duyuruları gösterir.
- **`acil_alarm.py`** (tahta): Masaüstü "ACİL ALARM" aracı (3 saniye basılı tutma + PIN doğrulaması ile `POST /api/acil/tahta-alarm`).

## Komutlar
```bash
# Dashboard (Sunucu)
cd tahtayoklama/dashboard
venv/bin/uvicorn app:app --reload --port 8099          # yerel geliştirme (lifespan polling çalıştırır)
venv/bin/python -m unittest discover -p 'test_*.py'    # tüm testler (unittest kullanılır; pytest YOKTUR)
venv/bin/python -m unittest test_uzaktan_ekran -v      # tek test dosyası (.py uzantısı olmadan)
venv/bin/python -m unittest test_uzaktan_ekran.TestUzaktanEkran.test_route_gecersiz_tahta   # tek test metodu
sudo systemctl restart farabi-yoklama-dashboard.service   # YALNIZCA ders saatleri (08:00-17:00 TR) DIŞINDA!

# Tahta GUI Testi (PyQt6 dev ortamında)
QT_QPA_PLATFORM=offscreen python3 -m pytest tahtayoklama/test_yoklama.py -q
```

## Veri Akışı ve Senkronizasyon
1. **Roster ve Ders Programı:** Tek doğruluk kaynağı `okul_ana` PostgreSQL veritabanıdır. Panelden veya zamanlayıcıyla `tahtayoklama/data/{ders_programi,zil}.json` ve `data/roster/<sinif>.json` üretilir.
2. **Yoklama Kaydı:** Tahtada öğretmen "YOKLAMAYI KAYDET" butonuna bastığında kayıt `data/kayitlar/<tarih>_<sinif>_ders<no>.json` dosyasına yazılır.
3. **Senkronizasyon:** `tahta_istemci.py` yeni/değişen kayıtları `POST /api/v1/tahta/kayit` ile panoya aktarır; pano `veri/yoklama_pano.db` SQLite veritabanına işler.
4. **SSH Yedek Taraması:** İstemcisi yanıt vermeyen tahtalar için `ssh_istemci.py` ve `yoklayici.py` üzerinden ders pencerelerinde periyodik SSH yoklama taraması yapılır.

## Güvenlik ve Kurallar
- Tahta başı kimlik: Her tahtanın `istemci.json` dosyasında gizli bir token bulunur. Sunucu tarafında yalnızca SHA-256 hash'i saklanır.
- Canlı Üretim Hassasiyeti: Dashboard servisi canlı okul saatlerinde (08:00 - 17:00 TR) kesinlikle yeniden başlatılmamalıdır.
- Tahta İstemci Kodu: `tahta_istemci.py` ve `yoklama.py` doğrudan sınıflardaki tahtalarda çalıştığı için geriye dönük uyum kesinlikle korunmalıdır.
