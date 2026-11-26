# smssistemi

Okul idaresinin öğrenci, veli ve personele toplu ve kişiselleştirilmiş SMS gönderdiği, devamsızlık ve doğum günü otomasyonlarını yöneten FastAPI servisi. Müdür PC üzerindeki GSM modem köprüsü ile iletişim kurar.

- Servis: `farabi-smssistemi.service` (systemd, port 8020, `smssistemi/` dizini)
- Framework: FastAPI + Uvicorn + Jinja2 + Tailwind CSS (derlenmiş `static/stil.css`)
- Veritabanı: SQLite WAL (`veri/smssistemi.db`), salt-okunur pano entegrasyonu (`tahtayoklama/dashboard/veri/yoklama_pano.db`)
- Ağ Akışı: `Farabi :8020` → `HTTP Proxy (8080)` → `Müdür PC WifiHttpProxy.exe` → `Huawei HiLink Modem (192.168.8.1:80)`

## Komutlar
```bash
venv/bin/uvicorn app:app --reload --port 8020              # yerel çalıştırma (lifespan otomasyonunu başlatır)
venv/bin/python -m pytest -q                              # tüm testler (261 test)
venv/bin/python -m pytest test_db.py -q                   # tek test dosyası
venv/bin/python -m pytest test_db.py::test_semayi_kur_ve_gonderim_kaydet -q  # tek test
venv/bin/python scripts/sifre_belirle.py                  # ortak yönetici şifresi belirleme (config/gizli.json)
sudo systemctl restart farabi-smssistemi                  # servisi yeniden başlatma
journalctl -u farabi-smssistemi.service -f                # canlı servis logları
```

## Önemli Dosyalar ve Sorumlulukları
| Dosya | Sorumluluk |
|---|---|
| `app.py` | FastAPI uygulama girişi, oturum yönetimi, gönderim, rehber ve otomasyon rotaları |
| `sms_gonderici.py` | Huawei LTE API istemcisi, proxy oturum yönetimi ve arka plan SMS gönderim iş parçacığı |
| `gonderim.py` | Telefon numarası doğrulama, normalizasyon (`05...` / `+905...`), karakter kodlama (UCS2 / 7-bit) |
| `yoklama_mantik.py` | Pano verisinden devamsız öğrencileri tespit etme ve veli SMS taslağı oluşturma |
| `yoklama_kaynak.py` | `yoklama_pano.db` SQLite veritabanından günün devamsızlık kayıtlarını okuyan tek köprü |
| `otomasyon.py` | Hafta içi 1. ders (09:00) ve öğle (14:00) otomatik devamsızlık SMS arka plan döngüsü |
| `dogum_mantik.py` & `dogum_sms.py` | Doğum günü yaklaşan öğrenci ve personel tespiti, otomatik doğum günü kutlama SMS döngüsü |
| `arac_api.py` | Atos (AnythingLLM) ve okul portalı için güvenli makine API'si (`/api/arac/*`) |
| `rehber_api.py` | Rehber kişi ve sınıf yönetimi API'si (`/api/rehber/*`) |
| `panel_api.py` | Dashboard için devamsızlık SMS durum API'si (`/api/panel/otomasyon-durum`) |
| `db.py` | SQLite bağlantı havuzu, şema kurulumu ve CRUD işlemleri |
| `auth.py` | Şifre doğrulama ve oturum yönetimi (scrypt hash, oturum token'ı) |

## Uç Noktalar (API)
- **Kullanıcı Ekranları:**
  - `GET /`, `POST /gonder` → Toplu SMS gönderme ekranı
  - `GET /durum/{id}`, `GET /api/durum/{id}` → Gönderim ilerleme durumu ve durdurma
  - `GET /rehber` → Öğrenci, veli ve personel rehber yönetimi
  - `GET /yoklama-sms` → Günlük devamsızlık SMS inceleme ve gönderme ekranı
  - `GET /otomasyon` → Devamsızlık SMS kuralları ve zamanlayıcı ayarları
  - `GET /dogum-gunleri` → Doğum günleri takip ve SMS onay panosu
- **Makine & Entegrasyon API'leri:**
  - `POST /api/arac/{veli,ogrenci,personel}-taslak` → SMS taslağı oluşturma (alıcı sayısı ve önizleme döner)
  - `POST /api/arac/{veli,ogrenci,personel}-gonder` → Taslağı onaylayıp gönderme (`alici_sayisi` doğrulaması zorunlu)
  - `POST /api/arac/kod-sms` → Tek kullanımlık SMS onay kodu gönderme (hız sınırlamalı)
  - `POST /api/arac/hareket-uyari` & `POST /api/arac/acil` → Kamera hareket ve acil durum uyarı SMS'leri
  - `GET /api/panel/otomasyon-durum` → Dashboard Bugün sayfası kartı için günlük devamsızlık SMS özeti
  - `POST /api/mesaj-duzelt` → Yerel Ollama (`farabi`) ile mesaj metnini resmi okul SMS formatına çevirme

## Güvenlik ve Dikkat Edilecek Kurallar
1. **İki Adımlı Gönderim Güvencesi:** Toplu SMS gönderimlerinde (`arac_api.py`), önce taslak oluşturulup alıcı sayısı onaylatılmadan gönderim yapılamaz. Günlük alıcı sınırı `TOPLU_GUNLUK_AZAMI=500`'dür.
2. **Fail-Closed Yoklama:** Yoklaması henüz alınmamış veya tahtası kapalı olan sınıfların velilerine yanlış devamsızlık SMS'i gönderilmez; sistem yalnızca `durum == 'alindi'` olan sınıfları işler.
3. **Mükerrer Gönderim Koruması:** Otomasyon ve doğum günü SMS'leri gün/ders bazlı idempotency anahtarlarıyla korunur; aynı gün ikinci kez otomatik gönderim yapılmaz.
4. **Gizli Bilgiler:** `config/gizli.json`, `config/modem.json`, `config/arac.json` ve `veri/` dizini git'e dahil edilmez; kişisel telefon numaraları testlere veya dokümantasyona yazılmaz.
