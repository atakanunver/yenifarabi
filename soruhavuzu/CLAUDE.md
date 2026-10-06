# soruhavuzu

Oyunlar (Sınıf Arenası vb.) için hazır soru havuzu: ders kitapları, kazanım
testleri ve YKS çıkmış sorularından **yerel Ollama** (qwen3.8:27b) ile soru
üretir, ayrı PostgreSQL veritabanına (`soru_havuzu`) yazar; üretim bitince
**AGY** (Antigravity) tüm havuzu bir kez denetler. Plan:
`docs/superpowers/plans/2026-10-05-soru-havuzu.md`; kararlar kök
`DECISIONS.md` 2026-10-05.

- Çalıştırma (kökten, server venv'i — psycopg2/pymupdf/httpx orada):
  `server/venv/bin/python -m soruhavuzu.calistir <kur|katalog|uret|denetle|durum>`
- `uret` ders saati dışında çalışır (`zaman.uretim_serbest`), pencere
  kapanınca "ders saati penceresi — durduruldu" deyip çıkar; GPU'yu derste
  Ollama'nın diğer kullanıcılarına bırakır.
- Zamanlayıcı: `systemd/soru-havuzu-uret.{service,timer}` →
  `/etc/systemd/system/` (hafta içi 14:15 UTC = 17:15 TR, hafta sonu 05:00
  UTC). Birim dosyası değişirse oraya da kopyalanmalı.
- DB şifresi `~/.pgpass`'tan; şema `sema.sql`.
- Test: `server/venv/bin/python -m pytest soruhavuzu/tests -q`.
- Bilinen: uzun üretimde Ollama arada 500 / zaman aşımı veriyor
  (2026-10-05 gecesi ~3500 işlemde 16 hata, %0,5) — birim atlanır, akış sürer.
