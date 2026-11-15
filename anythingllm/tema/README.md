# Atos Farabi Tema Paketi

AnythingLLM arayüzüne Farabi dashboard'unun 10 temasını (`cam` varsayılan) ve sağ üst köşedeki tema seçicisini CSS+JS enjeksiyonuyla uygular. Yerel yazı tipleri (`fontlar/`) kullanır, dış CDN içermez.

## Kurulum ve Geri Alma
- Kur / güncelle (idempotent): `./kur_tema.sh`
- Test dizininde dene: `ATOS_PUBLIC=/tmp/ornek ./kur_tema.sh`
- Geri al: `./kur_tema.sh --geri-al`

## Önemli Notlar
- Betik `/opt/anythingllm/app/server/public/farabi-tema/` altına kopyalar ve `_index.html` içine `<!-- farabi-tema -->` ekler; canlıda servisi yeniden başlatmaz (`MetaGenerator.js` / `pm2 restart` gerekebilir).
- AnythingLLM yükseltildiğinde `server/public` sıfırlanacağından `kur_tema.sh` yeniden çalıştırılmalıdır.
