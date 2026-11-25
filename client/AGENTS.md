# Farabi Client (`client/`)

Sınıf akıllı tahtalarında (Pardus / Linux / Vestel) çalışan etkileşimli sesli ders asistanı ve ince PyQt6 istemcisi. Ses oturumu Google Gemini Live WebSocket API üzerinden doğrudan tahtada yürütülür; ağır işler (kitap içeriği, YKS soruları, kazanımlar) `server/` (farabi-api) servisine yönlendirilir.

- Çalışma Alanı: Akıllı tahta (`~/farabi` sparse-checkout; tahtalar `origin/master` dalını çeker)
- Grafik Arayüz: PyQt6 HUD arayüzü (`ui.py::FarabiUI`)
- Ses Entegrasyonu: Google Gemini Live API (`google.genai`), `sounddevice`, PulseAudio (`default`)

## Komutlar
```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
python main.py                                            # istemciyi başlatma
venv/bin/python -m pytest tests/ -q                      # yerel testler
venv/bin/python -m pytest tests/test_mufredat.py -q      # tek test dosyası
venv/bin/python -c "import main"                         # import seti doğrulama
python tools/dogrula.py                                  # içerik kapısı doğrulaması
python tools/mikrofon_test.py --karsilastir              # mikrofon kalibrasyon ve SNR testi
```
- Tahtada Test: `server/tahta-ssh.sh <derslik> "cd ~/farabi/client && venv/bin/python -m pytest tests/ -q"`
- Son Kabul: Fiziksel tahta üzerinde Atakan tarafından yapılır.
- Dağıtım: Tahtalar `update_farabi.sh` ile `git pull --ff-only origin master` + `pip install` + `systemctl --user restart farabi-client.service` yapar; master'a push edilen client kodu tahtalara gider.
- Loglar: `logs/farabi.log` (tanı) ve `logs/ders/YYYY-AA-GG.txt` (ders kaydı) gerçek sınıf izidir. `tests/conftest.py` bunları `FARABI_LOG_DIR` / `FARABI_DERS_LOG_DIR` ile geçici dizine yönlendirir; yeni log yolu eklersen aynı korumayı ekle.

## Önemli Dosyalar ve Sorumlulukları
| Dosya / Dizin | Sorumluluk |
|---|---|
| `main.py` | `FarabiLive` ana oturum döngüsü, ses giriş/çıkış akışları, araç çağrılarının (`_execute_tool`) yönetimi |
| `ui.py` | `FarabiUI` PyQt6 HUD arayüzü, görsel durum göstergeleri ve dalga formu animasyonları |
| `ders_gorsel_servis.py` | Ders sırasında periyodik ekran görüntüsü alıp sunucuya ileten arka plan servisi (`systemd --user farabi-ders-gorsel`) |
| `actions/` | Modele sunulan işlev çağrısı (function calling) araçları (her araç bağımsız bir Python dosyasıdır) |
| `actions/kayit.py` | İstemcide kayıtlı tüm araçların tanımları, şemaları ve yürütme eşlemeleri |
| `core/anahtar.py` | Gemini API anahtarı havuzu yönetimi ve otomatik kota/hata rotasyonu |
| `core/ders_motoru.py` | Ders durum makinesi (`BEKLIYOR`, `YOKLAMA`, `ANLATIM`) |
| `core/tahta.py` | Derslik kimliği (`vestel9b.local`), tahta anahtarı ve sade mod tespiti |
| `core/prompt.txt` | Canlı modelin sistem talimatı ve persona kuralları |
| `core/zil.py` & `core/program.py` | Yerel zil ve ders programı verisi yönetimi |
| `core/modeller.py` | Canlı ses model adı tek yerde (model emekliliğinde yalnız burası değişir) |
| `core/saglayicilar.py` | Gemini dışı metin/görsel işleri için `server`'a ince HTTP proxy (`/api/egitim/metin_uret`, `gorsel_uret`); client'ta sağlayıcı anahtarı yok. `metin_uret`/`gorsel_uret` imzaları korunmalı, hata `RuntimeError` yükseltir |
| `core/olaylar.py` | Modüller arası olay yayını (`abone`/`yayinla`) |

## Çalışma Modu: SADE MOD (Varsayılan)
Tahtalarda varsayılan olarak **Sade Mod** koşar (`core/tahta.sade_mod()`; `config/api_keys.json` içinde `"sade_mod": false` kapatır, dosya/alan yoksa açık):
- 15 Temel Araç Aktiftir:
  `web_ac`, `uygulama_ac`, `dosya_ac`, `pencere_kapat`, `pdf_sayfa`, `yks_sorulari`, `geogebra`, `ekran_goruntusu_al`, `ekrandaki_soruyu_oku`, `icerigi_kapat`, `youtube_video`, `web_search`, `eba`, `yoklama_al`, `ders_icerigi` (kitap metni; 2026-11-25 kullanıcı kararı).
- `kitap_sorusu` client'tan kaldırıldı (RAG İPTAL, `1be6b08`); geri ekleme.
- `yoklama_al`, `yoklama.py`'yi önce `<client>/../tahtayoklama/` (9-A tam klon), sonra `~/tahtayoklama/` (sparse-checkout tahtalar) içinde arar.
- Ders kipleri (`ogretmenli`, `ogretmensiz`) ve dil butonları bu modda gizlidir; öğretmen sesli komutları doğrudan yürütülür.

## Sunucu ile İletişim (API)
İstemci `server/` servisine (`http://farabi.local:8000`) HTTP istekleri atar (`X-Farabi-Board-Key` başlığı ile):
- `POST /api/egitim/ders_icerigi` → Konu içeriği
- `GET /api/egitim/pdf_sayfa` → Ders kitabı sayfası PNG
- `POST /api/egitim/yks_sorulari` → YKS soru listesi
- `GET /api/egitim/kazanim` → Yıllık plan kazanımı, konu ve tema
- `POST /api/client/heartbeat` → İstemci nabzı
- `POST /api/egitim/ders_kaydi_yedek` → Ders bitişinde transcript yedeği
- `POST /api/ders-gorsel` → Ekran görüntüsü arşivi

## Kod Değiştirirken Dikkat Edilecekler
1. 🛑 **Yerel STT/TTS/Pipecat KALICI İPTAL:** Ses tek yönlü olarak tahtadaki Gemini Live WebSocket oturumu üzerinden yürütülür.
2. 🛑 **Thinking Config Yok:** Live modelinde `thinking_config` kullanıldığında model sessizleştiği için `thinking_config is None` olmalıdır.
3. **Araç Kaydı Bütünlüğü:** Yeni bir araç eklendiğinde hem `actions/<ad>.py` oluşturulmalı, hem `actions/kayit.py` içine şeması eklenmeli, hem de `main.py::_execute_tool` içinde karşılığı tanımlanmalıdır (aksi halde `test_arac_kaydi.py` düşer).
4. **Tahta Donanım Kısıtları:** Tahtalarda harici mikrofon ve standart PulseAudio (`default`) kullanılır. Ses donanımında `hw:*` sabitlemesi veya VAD geri eklenmemelidir.
5. **Konu/kazanım kaynağı:** Konu (ve ünite/tema) varsayılan olarak yıllık plandan gelir (`/api/egitim/kazanim`; ders çerçevesinde "Konu (yıllık plan, bu hafta)"). Öğretmen `konu:` yazar veya söylerse plan değeri ezilir (`kazanim_kaynagi="plan"/"ogretmen"`). Eski "yalnız öğretmenden" kuralı kaldırıldı (2026-11-25).
6. **Tahtada ders kitabı PDF'leri:** Kitaplar `~/DERSLER/<DERS>/` altına kopyalanır (kaynak `/mnt/farabi-data/farabi/kitaplar`, dağıtım `server/kitap_dagit.sh`); yerel kopya öğretmenin dosya açması içindir, render/arama server'da kalır (2026-11-25).
