# Dijital Okul (`okul/`)

Öğrenciler, veliler, öğretmenler ve okul yöneticileri için mobil öncelikli okul portalı. Soru Maratonu, Bilgi Arenası, deneme sınav takibi, ödevler, izin dilekçeleri, anketler ve duyuruları içerir.

- Servis: `farabi-okul.service` (systemd, port 9090, `okul/` dizini)
- Dış Erişim: https://smual.app (Cloudflare Tunnel)
- Framework: **FastAPI** + Jinja2 + vanilla CSS (Ortak cam tema `static/cam-tema.css` ve özel değişkenler `static/cam-okul.css`)
- Veritabanı: SQLite WAL (`veri/okul.db`, 44 göç adımı)

## Komutlar
```bash
venv/bin/uvicorn app:app --host 127.0.0.1 --port 9090     # yerel geliştirme
venv/bin/python -m pytest -q                              # tüm testler
venv/bin/python -m pytest tests/test_odevler.py -q        # tek test dosyası
venv/bin/python -m pytest tests/test_odevler.py::test_adi -q  # tek test
sudo systemctl restart farabi-okul                        # üretime alma
journalctl -u farabi-okul.service -f                      # canlı loglar
```
- İlk yönetici oluşturma: `venv/bin/python scripts/yonetici_olustur.py "Ad Soyad" kullanici_adi`
- CRLF Uyarısı: `okul/` altındaki bazı dosyalar CRLF satır sonuna sahip olabilir; Python ile yazarken `newline=''` parametresi kullanılmalıdır.

## Önemli Dosyalar ve Sorumlulukları
| Dosya / Dizin | Sorumluluk |
|---|---|
| `app.py` | FastAPI uygulama girişi, güvenlik başlıkları, oturum çerezi ve router montajı |
| `deps.py` | Ortak bağımlılıklar (`db_conn`, `mevcut_kullanici`, `rol(*roller)`, `render()`, CSRF doğrulaması) |
| `db.py` | SQLite şema tanımları ve versiyonlu göç listesi (`GOCLER`, `PRAGMA user_version`) |
| `ayarlar.py` | Genel yapılandırma ve ortam değişkenleri (`AYAR`) |
| `rotalar/*.py` | Uç nokta modülleri (ince katman; iş mantığı kök modüllerde tutulur) |
| `maraton.py` | Soru Maratonu iş mantığı (bireysel soru çözme, tekrar engeli) |
| `arena.py` | Bilgi Arenası: Günlük 5 soruluk görev, XP defteri (`bilgi_xp`), seviye ve rozetler |
| `odevler.py` | Öğretmen ödev tanımlama, öğrenci teslimleri ve soru istatistikleri |
| `izin.py` & `izin_pdf.py` | Veli izin dilekçesi talepleri, yönetici onayları ve PDF dilekçe üretimi |
| `denemeler.py` | Deneme sınavı sonuçlarının analizi, karneler ve gelişim raporları |
| `analitik.py` | Anonim kullanıcı etkileşim sayaçları (içerik/IP saklanmaz) |
| `push.py` | Web Push bildirimleri (VAPID anahtarlı, ad/içerik taşımayan sabit şablonlar) |
| `sohbet.py` | Öğretmen ve yönetici arası mesajlaşma odası |
| `kaynaklar/` | Dış veri okuyucular (`program`, `yoklama`, `kazanim`, `soru`, `sms`, `zil`) |

## Uç Noktalar ve Rotalar (`rotalar/`)
- **Genel & Kimlik:** `/giris`, `/cikis`, `/sifre-degistir`, `/profil`, `/bildirimler`
- **Öğrenci & Veli:**
  - `/veli`, `/veli/izin`, `/veli/onaylar`, `/veli/denemeler`
  - `/maraton`, `/arena`, `/cografya`, `/sudoku`, `/odevler`, `/denemeler`
- **Öğretmen & Yönetici:**
  - `/ogretmen`, `/ogretmen/soru-katki`, `/ogretmen/inceleme`, `/ogretmen/onay`
  - `/yonetici`, `/yonetici/izinler`, `/yonetici/analitik`, `/yonetici/duyurular`
- **Makine & Yerel Ağ API'leri:**
  - `GET /api/izinler` → Dashboard için onaylı veli izinleri (`X-Izin-Anahtar`)
  - `GET /api/pano` → Kiosk bilgi panosu uç noktası (LAN-only, Cloudflare engelli)
  - `POST /api/soru-istek*` & `POST /api/soru-katki*` → Soru havuzu entegrasyon uçları

## Dikkat Edilecek Mimari ve Güvenlik Kuralları
1. **İki Arena Ayrımı:** smual.app üzerindeki "Bilgi Arenası" bireysel öğrenci yarışmasıdır (`okul.db`); tahtalardaki "Sınıf Arenası" ise `arenasinif/` servisidir (`veri/sonuclar.db`). İkisi birbirine bağlanmaz.
2. **Şema Göçleri:** Veritabanı şeması `db.GOCLER` listesi üzerinden yürütülür. Mevcut göçler kesinlikle değiştirilmez; yeni göç her zaman listenin sonuna `V<N+1>` olarak eklenir ve `scripts/geri_al.py`'ye geri dönüşü yazılır.
3. **Rol ve CSRF Kontrolü:** POST rotalarında `deps.rol(..., post=True)` ile CSRF token doğrulaması zorunludur. Yanlış role sahip kullanıcılar 404 ile karşılanır (bilgi sızdırılmaz).
4. **Şablon ve Cache Güncellemeleri:** Şablon veya CSS/JS değişikliği yapıldığında `base.html` ve `sw.js` içindeki sürüm (`?v=N`) artırılmalıdır.
