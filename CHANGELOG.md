# Changelog

Bu proje [Semantic Versioning](https://semver.org/lang/tr/) kullanır.

## [Yayınlanmamış] — sürüm numarası hâlâ 0.2.0 (`server/version.py`, `client/core/version.py`)

### Added

- Sunucu: `POST /api/egitim/ders_plani` — kitap sayfalarından 40 dk ders
  planı (bulut zinciri deepseek > groq > cohere, önbellek, kaynak dışı sayı
  uyarısı) (2026-09-30).
- İstemci: ders içi **⏹ DERSİ BİTİR** düğmesi, 🎤/🚫 mikrofon modu düğmesi,
  mikrofonsuz mod (2026-09-25/27).
- İstemci: `ekrandaki_soruyu_oku` ekranı görüntü olarak Gemini Live'a verir
  (2026-09-27); `kitap_sorusu` kaynak satırında tablo kaynağı `(tablo)`
  ekiyle (2026-10-01).
- Dashboard: uzaktan yönetim denetim kaydı (`uzaktan_denetim` tablosu),
  oturumsuz tarayıcı isteği `/giris`'e yönlenir (2026-10-01).

### Changed

- Ses kalıcı olarak Gemini Live'da; yerel ses (Pipecat) denemesi geri
  alındı (2026-09-28).
- Kitap metni bulut sağlayıcılara gidebilir (kullanıcı kararı, 2026-09-29).

### Fixed

- Live modeli `thinking_config` yüzünden susuyordu — kaldırıldı (2026-09-27).
- Sunucunun bulut sağlayıcı zincirleri anahtarsızdı (anahtarlar yanlış
  dosyadaydı) (2026-09-29).
- Yoklama panosunda "herkes var" görünmesi (otomatik ders sonu kaydı
  kaldırıldı) (2026-09-28).
- smssistemi: proxy kapalıyken SMS kaybı ve 3 saat geri görünen zaman
  (2026-09-28).

## [0.2.0] - 2026-09-06

### Changed

- Tahta dağıtım mekanizması rsync tabanlı server->board pull'dan GitHub tabanlı
  `git fetch`'e geçirildi (`server/farabi-kurulum.sh`) — repo public olduğu
  için tahta tarafında SSH kimlik doğrulama kaldırıldı, sürüm/rollback takibi
  artık GitHub commit geçmişinden yapılabiliyor. Ayrıntı: `DECISIONS.md`
  2026-09-05 kararları, `docs/mimari.md` §0.

### Fixed

- Üretimde `farabi-api.service`/`farabi-yoklama-dashboard.service` sistem
  Python sürümü değişikliği (3.11 -> 3.14) sonrası eksik kalan `venv/`'ler
  yeniden kuruldu; RAG API'si yeniden sağlıklı çalışır duruma getirildi.

## [0.1.0] - 2026-09-04

### Added

- İstemci ve sunucu için başlangıç semantic sürüm tanımı.
- İstemci başlangıcında HTTP tabanlı sürüm uyumluluk kontrolü.
- MAJOR sürüm uyuşmazlığında istemciyi durduran, MINOR/PATCH farkında uyarı veren davranış.
- İstemci Git güncelleme ve yeniden başlatma betiği.
