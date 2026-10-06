## 2026-10-06 - Sınıf Arenası tamamen yerel çalışır + sonuç veritabanı
- Tailwind Play CDN, jsdelivr confetti, unpkg lucide@latest ve Google Fonts kaldırıldı; statik /static altında (tailwind.css 3.4.19 CLI ile derlenmiş, lucide yalnızca kullanılan ikonlarla ~8 KB, fontlar woff2). Sürümler: static/vendor/SURUMLER.txt.
- Neden: eski i3 tahtalarda Tailwind tarayıcıda derlenince çok yavaştı; okul internetine bağımlılık ve unpinned lucide riski vardı.
- Biten oyun sonuçları veri/sonuclar.db (SQLite, gitignore'lu) içinde; /ozet sayfası ve /api/arena/ozet. Öğrenci verisi makineden çıkmaz.
- Türkçe büyük/küçük harf: turkce.py (str.capitalize/lower "Ingilizce"/"i̇ngilizce" üretiyordu); KAPSAM_ESLEME aramaları tr_kucuk ile.
- İstemci hata raporu: static/hata.js (tekrar süzme) + sunucuda (ip,mesaj) hız sınırı; sendBeacon artık application/json Blob (text/plain 422 veriyordu).
