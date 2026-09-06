# Changelog

Bu proje [Semantic Versioning](https://semver.org/lang/tr/) kullanır.

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
