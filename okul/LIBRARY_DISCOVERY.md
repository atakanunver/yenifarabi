# Kütüphane otomasyonu — keşif ve plan (2026-11-06)

## Keşif bulguları
| Konu | Bulgu |
|---|---|
| Uygulama | `okul/` = smual.app: FastAPI + Jinja2 + vanilla CSS/JS, port 9090, Cloudflare Tunnel (HTTPS dışarıdan). Ayrı uygulama yok, modül buraya eklenir. |
| Veritabanı | SQLite `veri/okul.db`; göç = `db.GOCLER` listesi, `PRAGMA user_version`, her göç tek `BEGIN…COMMIT`. Geri alma `scripts/geri_al.py` `GERI[N]`. Üretim 2026-11-06'da V39. |
| Kimlik/rol | `kullanici.rol` ∈ ogrenci/veli/ogretmen/yonetici; oturum çerezi (`auth.py`), yetki merkezi `yetki.py`, yetkisiz = 404. Öğrenci kaydı `ogrenci` (okul_no, ad_soyad, sinif, kullanici_id), veli bağı `veli_ogrenci`. |
| Arayüz | "Kareli defter" teması, `static/okul.css` + `temalar.css` değişkenleri; rol ana sayfaları kart düzeni. |
| PWA | `static/manifest.webmanifest`, `static/sw.js` (SURUM + STATIK listesi; yeni statik dosya STATIK'e eklenir). |
| Excel | `ice_aktar.py` (öğrenci/öğretmen CSV/XLSX aktarımı) örnek alınır. |
| Bildirim | Web Push `push.py`; payload SABİT şablon (ad/kitap adı konmaz). Saatlik zamanlayıcı örneği `scripts/odev_uyari.py`. |
| Güvenlik | Form CSRF (`deps.py`), Jinja otomatik kaçış, parametreli SQL, `app.py` güvenlik başlıkları. |
| Test | `venv/bin/python -m pytest -q`; `conftest.py` `gecici_ortam` db'yi `tmp_path`'e alır, `saat` fixture'ı zamanı sabitler. |

## Okul ayarları (Atakan)
- Ödünç süresi 14 gün, öğrenci başına 2 kitap (`kutuphane.ODUNC_GUN`, `OGRENCI_LIMIT`).
- Ödünç/iade: yönetici + `kutuphane_yetkili` listesindeki öğretmenler; diğer öğretmenler yalnızca katalog.
- Teslim tarihi hatırlatması açık (`HATIRLATMA`).
- USB barkod okuyucu YOK → yalnızca kamera. Laptop kütüphanede ana nokta, öğretmen telefonları ek terminal.
- Kitaplarda demirbaş BARKODU yok; yalnızca sayı yazan etiket var.

## Kararlar
- **Eser/nüsha ayrımı:** `kitap` (ISBN tekil, başlık, yazar, yayınevi, tür, kapak) + `nusha` (demirbaş tekil, baskı yılı, basım sayısı, raf, durum). Baskı yılı/basım nüshada (aynı ISBN'in kopyaları farklı basım olabilir). Demirbaş TEXT ("03244" sıfırı korunur).
- **Kamera akışı:** kamera kitabın arkasındaki ISBN'i (EAN-13) okur → o eserin nüshaları listelenir; tek nüsha ise doğrudan seçilir, çoksa personel etiketteki demirbaşı seçer/yazar. İadede ISBN okutulunca yalnızca ödünçteki nüshalar gelir (çoğu zaman tek). Etiket OCR'ı yok (ağır, hatalı).
- **Kamera kütüphanesi:** Android/masaüstü Chrome'da yerleşik `BarcodeDetector`; yoksa (iPhone Safari) `static/vendor/zxing-0.21.3.min.js` (@zxing/library 0.21.3, MIT; jsdelivr + unpkg sha256 aynı `d7cc8f69…652d`). Görüntü sunucuya GİTMEZ, yalnızca okunan kod gönderilir. CDN yok.
- **Ödünç bütünlüğü:** `odunc` kaydı silinmez (denetim izi: veren, alan, tarihler). Kısmi tekil indeks `odunc_aktif_nusha` + `BEGIN IMMEDIATE` ile iki cihazdan eşzamanlı okutmada yalnızca biri geçer; çift okutma 409.
- **Ödünç ≠ okuma:** raporlarda yalnızca "ödünç sayısı" denir; okundu bilgisi tutulmaz.
- **KVKK:** öğrenci verisi kopyalanmaz, `ogrenci.id` ile bağlanır; push metni sabit.

## Uygulama sırası
1. ✅ Şema V40: `kitap`, `nusha`, `kutuphane_yetkili`, `odunc`, `kutuphane_ayar`, `ayirtma` + `kutuphane.py`.
2. ✅ Rotalar `rotalar/kutuphane.py` (yetki sunucuda, CSRF, yetkisiz = 404) + ana ekran (Ver/Al/Ekle/Liste/Ödünçteki/Gecikenler/Raporlar).
3. ✅ Kamera `static/kutuphane-kamera.js` (BarcodeDetector → ZXing yedeği, kamera seçimi, tek okuma kilidi, elle giriş).
4. ✅ Kütüphanem (öğrenci ana ekran kartı + `/kutuphane/benim`, veli yalnızca kendi çocuğu), ayırtma sırası (iade edilen nüsha sıradakine 3 gün ayrılır), son 2 gün uygulama içi hatırlatma.
5. ✅ Excel içe/dışa aktarma, raporlar, A4 QR etiket (3×7, `KTP-<demirbaş>`), yönetici ayarları (süre, limit, hatırlatma, yetkili öğretmenler).
6. ⏳ Fiziksel cihaz denemesi (kamera yalnızca HTTPS'te: smual.app) — üretime alındıktan sonra; push hatırlatması (zamanlayıcı kurulumu onay ister).
7. ⏳ İkinci aşama: Okuma Ligi — doğrulanmış okuma (ödünçten ayrı tablo), puan/yorum, öğretmen onaylı okuma etkinliği, rozetler mevcut `bilgi_xp`/rozet altyapısıyla.

## Üretime alma / geri dönüş
- Alma: master'a commit → ders saati dışında `sudo systemctl restart farabi-okul` (açılışta V40 göçü yalnızca yeni tablo ekler, mevcut veriye dokunmaz). Öncesinde `veri/okul.db` yedeği.
- Geri dönüş: `venv/bin/python scripts/geri_al.py --hedef 39` (kütüphane tabloları silinir — kütüphane verisi gider) + önceki commit'e dönüş + restart.
