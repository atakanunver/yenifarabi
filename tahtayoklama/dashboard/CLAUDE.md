# Yoklama Dashboard (`tahtayoklama/dashboard/`)

Merkezi okul yoklama panosu, tahta uzaktan yönetimi, okul veri merkezi, acil durum siren/anons ve sistem durumu izleme servisi.

- Servis: `farabi-yoklama-dashboard.service` (systemd, port 80, `tahtayoklama/dashboard/` dizini)
  - Not: Systemd birimi 8010 portu tanımlasa da `port80.conf` drop-in'i ile port **80** üzerinden sunulur.
- Framework: **FastAPI** + Uvicorn + Jinja2 + vanilla JS / React (`arayuz/` Vite + TypeScript)
- Veritabanı: SQLite WAL (`veri/yoklama_pano.db`) + doğrudan `okul_ana` (PostgreSQL) entegrasyonu
- Bağımsızlık: Farabi'nin `server/main.py` servisinden bağımsızdır; kendi venv ve veritabanına sahiptir.

## Komutlar
```bash
venv/bin/uvicorn app:app --reload --port 8099          # yerel geliştirme (DİKKAT: lifespan polling çift çalışır)
venv/bin/python -m unittest discover -p 'test_*.py'    # TÜM TESTLER (696 test, pytest YOKTUR)
venv/bin/python -m unittest test_uzaktan_ekran -v      # tek modül testi
venv/bin/python -m unittest test_uzaktan_ekran.TestUzaktanEkran.test_route_gecersiz_tahta  # tek test
venv/bin/python scripts/sifre_belirle.py               # ortak pano şifresi → config/gizli.json
sudo systemctl restart farabi-yoklama-dashboard.service   # YALNIZCA 08:00-17:00 TR DIŞINDA!
journalctl -u farabi-yoklama-dashboard.service -f      # servis logları
```
- ⚠️ Şablonlar (`templates/`) ve statik dosyalar değişiklikte canlıya anında yansır; `.py` dosyaları restart ister.
- Venv'de `httpx` veya `pytest` yoktur. Testlerde `fastapi.testclient.TestClient` yerine `Request` elle kurgulanarak doğrudan korutinler çağrılır.

## Mimari ve Önemli Modüller
- `app.py`: FastAPI giriş noktası ve router montajı (`include_router`).
- **Önemli Router ve Mantık Modülleri:**
  | Modül | Sorumluluk |
  |---|---|
  | `tahta_api.py` | Tahta istemcileri için `/api/v1/tahta/*` uçları (kayıt push, nabız, yapılandırma pull) |
  | `yoklayici.py` | Yoklama önbelleği (`yoklama_onbellek`) ve hafta içi ders saatlerinde SSH polling döngüsü |
  | `admin.py` | Yönetici paneli, sınıf/öğrenci/roster yönetimi |
  | `okul_ana_panel.py` | PostgreSQL `okul_ana` yönetim ekranı ve JSON yayınlama motoru |
  | `okul_sql.py` & `okul_bilgisi.py` | Atos (AnythingLLM) `/api/okul/sql` salt-okunur güvenli sorgu motoru |
  | `uzaktan_yonetim.py` & `uzaktan_baslat.py` | Tahtalarda uzaktan ekran izleme, kilitleme, uygulama açma ve reboot |
  | `acil.py` | Acil durum alarmı (zil sireni, acil SMS, tahta kiosk karartma/uyarı) |
  | `duyurular_panel.py` & `duyuru.py` | Tahtalara anlık görsel/sesli duyuru gönderme |
  | `sistem_durumu.py` & `sunucular.py` | Küme sunucuları ve tahtaların donanım/ağ sağlık izlemesi |
  | `servis_yonetimi.py` | `/usr/local/sbin/farabi-servis` üzerinden izinli systemd servislerini yönetme |
  | `zamanlanmis_gorevler.py` | Sistem cron/timer işlerinin yönetimi (`farabi-zamanlayici`) |
  | `gorsel_panel.py` | Haftalık ders görseli ve sınıf afişi yönetimi |
  | `kulup_yoklama.py` & `dyk_yoklama.py` | Sosyal kulüp ve DYK hafta sonu kurs yoklama yönetimi |
  | `veli_mesajlari.py` | SMS sistemi entegrasyonu (`smssistemi` HTTP API) |

## Kimlik Doğrulama ve Yetkilendirme Katmanları
1. **Yönetici Oturumu (`auth.dogrula`):** Ortak yönetici şifresi doğrulaması (`config/gizli.json` scrypt hash), çerez tabanlı oturum.
2. **Güvenlik Paneli (`/guvenlik`):** Kendi özel şifresi ve oturum çerezi (`config/guvenlik.json`). `/admin` oturumundan tamamen ayrıdır.
3. **Makine API Anahtarları (Yerel Ağ / LAN Zorunlu):**
   - `/api/ajan/*` → `X-Farabi-Ajan-Key`
   - `/api/v1/tahta/*` → Tahta başına token (SHA-256 doğrulaması)
   - `/api/okul/sql` → `X-Farabi-Okul-Key` + `X-Farabi-Rol: admin`

## Dikkat Edilecek Kurallar ve Tuzaklar
1. **Menü Ağacı:** Yeni bir sayfa router'ı eklendiğinde `menu.py::MENU` yapısına eklenmeli ve ilgili Jinja şablonuna `templates.env.globals["menu_agaci"]` tanımlanmalıdır (aksi halde `test_menu` testi düşer).
2. **Tahta İstemci Sürümü:** `tahta_istemci.SURUM` sabiti `test_kulup.py` ile kilitlenmiştir. Sürüm yükseltmelerinde test de güncellenmelidir.
3. **Atos Veri Erişimi:** `okul_sql.py` veya `okul_bilgisi.py` üzerinde yeni bir tablo eklenirken izinli tablo listesine (`IZINLI_TABLOLAR`) eklenmeli, şema metni (`sema_aciklamasi.txt`) güncellenmeli ve `anythingllm/kur_yetenekler.sh` yeniden çalıştırılmalıdır.
4. **Acil Durum Tetikleme:** `acil.py` içindeki tatbikat ve gerçek alarm ayrımına dikkat edilmeli, geliştirme/test ortamında gerçek acil SMS ve siren tetiklenmemelidir.
