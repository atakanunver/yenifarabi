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

## Artımlı denetim (2026-10-06)
- `uret` artık yalnızca "hepsi bitince" denetlemez: başlangıçta (üretimden önce) ve
  pencere hâlâ açıksa döngü bitince SINIRLI denetim yapar — `calistir.DENETIM_AZAMI_PAKET=8`
  (paket=100 soru) ve `DENETIM_AZAMI_DK=45`, hangisi önce dolarsa. Her paketten önce
  `zaman.uretim_serbest()` bakılır, ders saati başlayınca hemen durur. (Hafta içi pencere
  07:30'da kapandığı için sadece döngü sonu denetimi fiilen çalışmazdı; bu yüzden başta da var.)
- Tüm birimler bitince eskisi gibi kalan her şey denetlenir (ders saati kontrolüyle).
  Elle `denetle` sınırsız ve ders saati kontrolsüz.
- Sıra (`vt.DENETLENECEK_SQL`): onaylı sayısı en az (sınıf, ders) önce, eşitlikte yüksek sınıf.
- `durum` sınıf başına onaylı / denetim bekleyen satırı da basar.

## Şık sırası dengesi (2026-10-10)
- `sik.kanonik_sira`: şıklar metin hash'ine (sayısal şıklar değere) göre kanonik sıraya dizilir; `vt.soru_ekle` her yeni soruya uygular. Konuma atıflı şıklar ("A ve B", "hepsi") dokunulmaz.
- Geçmiş için: `python -m soruhavuzu.calistir sik-karistir [--kuru]` (önce/sonra A/B/C/D dağılımı yazar; ikinci çalıştırmada 0 değişiklik).
