## 2026-10-06 - Sınıf Arenası tamamen yerel çalışır + sonuç veritabanı
- Tailwind Play CDN, jsdelivr confetti, unpkg lucide@latest ve Google Fonts kaldırıldı; statik /static altında (tailwind.css 3.4.19 CLI ile derlenmiş, lucide yalnızca kullanılan ikonlarla ~8 KB, fontlar woff2). Sürümler: static/vendor/SURUMLER.txt.
- Neden: eski i3 tahtalarda Tailwind tarayıcıda derlenince çok yavaştı; okul internetine bağımlılık ve unpinned lucide riski vardı.
- Biten oyun sonuçları veri/sonuclar.db (SQLite, gitignore'lu) içinde; /ozet sayfası ve /api/arena/ozet. Öğrenci verisi makineden çıkmaz.
- Türkçe büyük/küçük harf: turkce.py (str.capitalize/lower "Ingilizce"/"i̇ngilizce" üretiyordu); KAPSAM_ESLEME aramaları tr_kucuk ile.
- İstemci hata raporu: static/hata.js (tekrar süzme) + sunucuda (ip,mesaj) hız sınırı; sendBeacon artık application/json Blob (text/plain 422 veriyordu).

## 2026-10-07 - Şube bazlı soru takibi ve tekrar engelleme (Soru rotasyonu)
- Soruların aynı şubede (örn. 9-A) haftalar boyunca tekrar sorulmasını engellemek için PostgreSQL `soru_havuzu` veritabanında `soru_kullanim` (soru_id, sube, oyun, tarih) tablosu kuruldu.
- Soru çekiminde (`havuz._cek`) o şubede sorulmuş sorular `ORDER BY CASE WHEN id IN (SELECT soru_id FROM soru_kullanim WHERE sube = %s) THEN 1 ELSE 0 END` mantığıyla en sona itilir; henüz sorulmamış taze sorular 0 önceliğiyle gelir.
- Sınıf Arenası (`istek.sinif`), HexaFetih (`secilen_sinif`) ve Tahta Düellosu (`sube`) şube kodunu havuza aktarır; oynanan sorular anında o şube hanesine yazılır.
- Her derste 300–500 onaylı soru bulunduğu için bir sınıf tüm eğitim yılı boyunca (~36 hafta) aynı soruyu tekrar görmeden yarışabilir.

## 2026-10-07 - Sınıflar Arası Skor Tablosu ve Okul Liderlik Sistemi
- Düello ve sınıf içi yarışmalarda (Sınıf Arenası & HexaFetih) toplanan puan ve soruları birleştiren Sınıflar Arası Skor Tablosu geliştirildi (`sonuc_deposu.siniflar_arasi_skorlar` ve `GET /api/arena/siniflar-arasi`).
- Sınıflar, doğru cevaplanan toplam soru sayısı ve toplam puana göre 1'den N'e sıralanır; "En Çok Soru Cevaplayan Sınıf" ve sınıfın yıldız öğrencisi öne çıkarılır.
- Okul geneli ve kategori bazlı (Genel, Düello, Takım) "En Çok Soru Bilen Öğrenciler" MVP liderlik tablosu eklendi.
- `/ozet` sayfası interaktif şampiyonluk paneli, madalyalar (🥇🥈🥉), dönemsel filtreler ve oyun türü kırılımlarıyla zenginleştirildi; tüm oyun başlıklarına (`sinif_arena.html`, `hexafetih.html`, `duello.html`) doğrudan erişim sağlandı.
## 2026-10-13 - Öğrenci listeleri ve dinamik takım kurucu entegrasyonu düzeltildi
- Sorun: Yerel `data/roster/*.json` dosyaları boş olduğu için tahta oyunlarında (Sınıf Arenası, HexaFetih, Düello) öğrenci listeleri boş geliyor (`0/0 Mevcut`), takımlara öğrenci atanamıyor ve Düello çarkı varsayılan sahte isimlere ("Ahmet Yılmaz", "Ayşe Kaya") düşüyordu.
- Çözüm 1: `yoklama_pano.db` üzerindeki 7 sınıfın (9-A, 9-B, 10-A, 11-A, 11-B, 12-A, 12-B) 96 öğrencisi `data/roster/{sinif}.json` dosyalarına aktarıldı.
- Çözüm 2: `server._ogrencileri_ve_yoklamayi_getir` içine otomatik DB yedeği (fallback) eklendi; roster JSON dosyası olmasa bile doğrudan SQLite `ogrenciler` tablosundan sınıf listesi yüklenir.
## 2026-10-13 - Görsel Sanatlar dersi ve MEB soru bankası oyunlara entegre edildi
- `/mnt/farabi-data/farabi/kazanim_test/9_sinif_gorsel_sanatlar_soru_bankasi.pdf` dosyasındaki 18 resmi MEB sorusu ve cevap anahtarı ayrıştırıldı.
- `farabi.kazanim_test_soru` tablosuna 18 adet çoktan seçmeli MEB Görsel Sanatlar sorusu eklendi.
- `soru_havuzu.soru` tablosuna 9, 10, 11 ve 12. sınıflar için toplam 72 onaylı soru eklendi (`durum='onayli'`, `ders='gorsel_sanatlar'`).
- Sınıf Arenası (`sinif_arena.html`): PDF'teki 4 tema (`Sanata Bakış`, `Çizgiden Boyuta`, `Zamanın İzinde Sanat`, `Sanat ve Teknoloji Evreni`) ve zorluk seviyeleri (100–400 puan) ile doğrudan 16 kartlık Jeopardy panosu oluşturuldu.
- Tahta Düellosu (`duello.html`) ve HexaFetih (`hexafetih.html`): `gorsel_sanatlar` ders anahtarı ve havuz soru çekimi entegre edildi; HexaFetih 18 soruyu 19 petek üzerinde döngüsel olarak tam dolduruyor.
- smual.app Soru Maratonu: 9, 10, 11 ve 12. sınıflarda "Görsel Sanatlar" dersi aktif hale geldi (18 soru onaylı).
