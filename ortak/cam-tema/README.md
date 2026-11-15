# cam-tema

Farabi web servisleri için ortak uzamsal cam teması (Tailwind 4, preflight yok, dış URL/CDN yok).

- Derleme: `npm install && npm run build` -> `dist/cam-tema.css` (commit'e girer; üretimde node yok).
- Servisler ayrı venv/makinede olduğundan `dist/cam-tema.css` ve `fontlar/` kendi `static/` dizinine KOPYALANIR
  (font yolu göreli: `fontlar/...`, css ile aynı dizinde durmalı).
- Gövde `class="cam-sayfa"`, ilk çocuk `<div class="cam-ortam" aria-hidden="true">`; duvar kağıdı için `--duvar-resmi: url(...)`.
- Pencere/şerit bulanıksızdır (dashboard cam.css kararı); yalnız `cam-dialog` hafif blur(6px) taşır.
- Örnek: `ornek.html` (tüm bileşenler).

Sınıflar: `cam-sayfa`, `cam-ortam`, `cam-pencere`, `cam-serit`, `cam-kart`, `cam-dialog`, `cam-perde`,
`cam-dugme` (+`-ikincil`, `-tehlike`, `-kucuk`), `cam-girdi`, `cam-tablo`, `cam-pill` + `cam-pill-oge`
(`aria-pressed="true"`/`.aktif`), `cam-rozet` (+`-yesil` `-kirmizi` `-mavi` `-mor` `-amber`),
`cam-baslik`, `cam-metin`, `cam-metin-2`, `cam-metin-3`, `cam-rakam`, `cam-ayrac`.
Tailwind yardımcıları yalnız `ornek.html`'te geçenler dist içindedir; servis şablonlarında anlamsal `cam-*` sınıflarını kullanın.
