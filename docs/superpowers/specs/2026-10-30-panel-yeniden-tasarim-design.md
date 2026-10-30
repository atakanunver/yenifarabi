# Yönetim paneli yeniden tasarımı (tahtayoklama/dashboard)

Tarih: 2026-10-30 · Karar veren: Atakan (okul müdürü + bilişim sorumlusu, panelin asıl kullanıcısı)

## Amaç ve neden
Panel (`farabi.local`, `tahtayoklama/dashboard`) zamanla parça parça büyüdü. Atakan'ın kendi sözleriyle sorunlar:
1. **Menüde anlam karmaşası:** öğelerin ne işe yaradığı ve nerede olduğu belli değil.
2. **Ekrana sığmayan tablolar:** 1366×768 dizüstünde yatay kaydırma, en sağı görememe, hücre araları gereksiz açık.
3. **Yönetim bilgisi karışıklığı:** sayfalarda önceliksiz, teknik, kalabalık bilgi (örn. Okul verisi sayfasının başındaki yayın günlüğü satırı).

Hedef: "üst düzey" görünen, pratik, bir bakışta anlaşılan bir yönetim paneli. Başarı = Atakan 1366×768'de hiçbir sayfada yatay kaydırma görmeden, menüde aradığını ilk denemede bulur; ana ekranda "hangi sınıfta kim yok, hangi ders eksik" 5 saniyede okunur.

## Kapsam
- Panelin TÜM sayfaları (`templates/` altındaki, `taban.html`'i genişleten 25+ şablon) yeni kabuğa ve yeni görsel dile geçer.
- **Tek seferde geçiş:** canlıya parça parça değil, hepsi bitip Atakan önizlemede onaylayınca tek seferde alınır.
- Kapsam dışı (bu belge): `giris.html` ve `acil_ekran.html` (tam ekran acil görüntüsü) yalnız yeni renklere uyar, düzenleri değişmez. smssistemi (:8020), okul portalı (:9090), kelebek gibi ayrı servislerin arayüzleri DEĞİŞMEZ (menüden bağlantı olarak kalırlar).
- Davranış/iş mantığı değişmez: URL'ler, form POST uçları, yetki kontrolleri, veri akışları aynı kalır. Bu bir arayüz yeniden tasarımıdır.

## Kararlar (Atakan'ın seçtikleri, örnek ekranlar üzerinden)

### 1. Kabuk: üstte ana alanlar, solda o alanın sayfaları (seçenek B)
- Üst çubuk: solda "Atos" markası, ardından 6 ana alan sekmesi; sağda **Acil durum** (kırmızı, her sayfada görünür), Atos yapay zekâ bağlantısı, gün/saat/ders bilgisi, tema düğmesi, çıkış.
- Sol menü: yalnızca seçili alanın sayfaları (düz liste, iç içe grup yok). Etkin sayfa vurgulu.
- 6 alan ve içerikleri (Atakan onayladı, Eğitim ayrı alan kararı onun):
  - **Yoklama:** Ders ızgarası (ana ekran, `/`), Bugünkü liste (`/bugun`), Rapor, Aylık özet, Kulüp yoklaması.
  - **Öğrenci ve personel:** Öğrenciler ve veliler, Personel, Sınıflar ve tahtalar, Ders programı, Zil saatleri, Kulüpler.
  - **İletişim:** Veli mesajları (okunmamış sayacı korunur), SMS gönder, Yoklama SMS, SMS otomasyonu, Doğum günleri, Tahta duyuru.
  - **Eğitim:** Kelebek, smual.app, smual.app yönetim.
  - **Güvenlik:** DVR kameralar, IP kameralar (yedek), Kamera kayıtları, Güvenlik ekranı, Kiosk yüz tanıma.
  - **Sistem:** Tahtalar (uzaktan yönetim), Sistem durumu, Servis yönetimi, Zamanlanmış görevler, Sunucular, harici paneller (Zil, Pano, Kiosk, Bilgehan).
  - Ayarlar menüsündeki öğeler (Atos iş ve ayarlar, Yazdır, Klavye kısayolları, Çıkış) ve Temalar üst çubuktaki bir kullanıcı/ayar açılır menüsüne taşınır.
- Yeni sekmede açılan dış bağlantılar (SMS, kelebek, smual, harici paneller) dış bağlantı ikonuyla işaretli kalır.
- Gezinmenin tek kaynağı `menu.py::MENU` olmaya devam eder (alan → sayfalar ağacına dönüşür); şablona elle menü yazılmaz. Etkin alan/sayfa tespiti mevcut `menu_agaci(yol, sorgu)` mantığıyla (sekme duyarlı eşleşme dahil).
- Klavye erişimi korunur: alan sekmeleri ve sol menü klavyeyle gezilebilir, mevcut harf kısayolları alanlara/sayfalara yeniden dağıtılır, `?` kısayol penceresi kalır.
- Telefon (<=720 px): üst alan sekmeleri ve sol menü tek bir açılır çekmecede birleşir.

### 2. Ana ekran: yoklama ızgarası, isimler hücrede (seçenek 2)
- `/` sayfası Yoklama alanının "Ders ızgarası"dır; içerik bugünkü gibi sınıf × ders tablosu.
- Hücrede devamsız isimleri çerçevesiz, küçük kırmızı metin olarak; çok devamsız varsa satır aşağı uzar (yatay taşma yok). "Tam", "Alınmadı", "Tahta ulaşılamaz" küçük renkli rozet. Hücrede ders kısa adı ve öğretmen etiketi korunur.
- Şu anki ders sütunu vurgulu ("5 · şimdi").
- Sorunlar ızgaranın ÜSTÜNDE tek satırlık uyarı şeridinde (bugün altta duran "N derste yoklama alınmadı" bloğu): sorun listesi kısa, "Tahtada aç" eylemi korunur; yoklama yüzdesi ve devamsız toplamı şeridin sağında.
- Bugünkü 4 büyük KPI kartı küçülür/şeride ya da başlık satırına iner (bilgi karışıklığını azaltmak için) — biçimi uygulayıcıya bırakıldı, ama ızgaranın 1366×768'de ilk ekranda görünmesi şart.
- Tarih seçici, son güncelleme ve "Şimdi yenile" başlık satırının sağında.

### 3. Yönetim sayfaları: liste + sağda ayrıntı paneli (seçenek 1)
- Kayıt listesi olan sayfalarda (Öğrenciler ve veliler, Personel, Sınıflar ve tahtalar, Kulüpler, Veli mesajları ve benzerleri) ortak desen:
  - Başlık satırı: sayfa adı + tek birincil düğme ("+ Personel ekle"); teknik durum tek küçük ifade ("● Yayınlandı 14:07", ayrıntısı üzerine gelince/tıklayınca).
  - Sayaçlar tıklanınca süzen **filtre çipleri** (Aktif 23 · TC eksik 1 · E-posta eksik 4 · Pasif 0) + anlık arama kutusu.
  - Liste solda; satıra tıklayınca sağda **ayrıntı paneli** açılır, kaydın tüm alanları orada düzenlenir (Kaydet, Pasifleştir/Geri al). Liste yerinde kalır, sayfa kaymaz. Eksik alanlar panelde turuncu işaretli.
  - Yeni kayıt da aynı panelde boş form olarak açılır.
  - Panel açıkken 1366 genişlikte liste + panel birlikte sığmalı; liste sütunları buna göre seçilir (ör. Personel: ad, görev, branş, telefon listede; e-posta, TC, doğum panelde).
- Okul verisi sayfasının sekmeleri (öğrenci/personel/program/zil/denetim) ayrı sol menü sayfaları olur; "Yayınla (yeniden dene)" düğmesi yalnız yayın başarısızken görünür.
- Panel davranışı sunucu taraflı kalabilir (seçili kayıt `?duzenle=` gibi bir parametreyle sayfayı yeniden üretir) ya da küçük düz JS ile açılabilir; ikisi de kabul, ama form POST uçları ve doğrulama sunucuda aynı kalır.

### 4. Görsel stil: sade koyu (seçenek C) varsayılan; temalar artar
- Yeni varsayılan tema: **sade koyu** — örnek ekrandaki C: koyu zemin (`#0d1117` civarı), daha az kutu ve kenarlık, yumuşak durum renkleri (yeşil/amber/kırmızı/mavi vurgu), ince ayraçlar.
- Mevcut 6 tema (Argon açık/koyu, Material açık/koyu, Black, Taş Tahta) KALIR (Atakan kararı). Ayrıca "tema sayısını artır" kararıyla örnek ekranlardaki diğer iki görünüm de tema olur:
  - **Sakin kurumsal** (açık; beyaz zemin, ince çizgi, mavi vurgu — örnek A),
  - **Lacivert** (koyu lacivert üst çubuk, açık içerik — örnek B).
  - Toplam 9 tema. (Hangi iki temanın ekleneceği benim kararım; Atakan yalnızca "artır" dedi.)
- Kayıtlı tema tercihi olanlar kendi temasında kalır; tercihi olmayan herkes yeni sade koyu ile açılır.
- Yeni düzen (kabuk, ızgara, panel) tüm temalarda çalışır; temalar yalnızca CSS değişkenlerini değiştirir.
- **Her temanın kendi yazı tipi olur** (Atakan isteği: "temalarda font istiyorum"). Bugün yalnız Geist kurulu ve `--yazi-tipi` yalnız `:root`'ta tanımlı; bu yüzden temalarda font değişmiyor. Yeni yapıda her tema bloğu `--yazi-tipi` (ve gerekirse `--yazi-tipi-baslik`, rakamlar için `--yazi-tipi-sayi`) tanımlar.
  - Fontlar yerel `static/` altında woff2 (latin + latin-ext, Türkçe karakterler şart), açık lisanslı (OFL vb.); CDN'den yüklenmez. Yazı tipi dosyalarını indirmek için uygulama sırasında Atakan'dan onay alınır (dosya adı/kaynak/boyut bildirilir).
  - Font seçimi uygulayıcıya bırakıldı; tema karakterine uygun ve 1366×768'de küçük puntoda okunaklı olmalı (örn. sade koyu için Inter ya da IBM Plex Sans, Sakin kurumsal için Source Sans 3, Taş Tahta için daha yuvarlak bir yazı tipi). Tüm temalarda toplam font yükü makul tutulur (tema başına en çok 2 dosya; yalnız seçili temanın fontu yüklenir).

## Kısıtlar (değişmez)
- Teknoloji: FastAPI + Jinja2 + düz CSS + düz JS. Build adımı, npm, React, Tailwind, Bootstrap YOK. CDN YOK (okul ağı SSL denetimi yapıyor; tahtalar eski). Yeni kütüphane gerekirse onay + yerel `static/`.
- Yazı tipi yerel Geist; ikonlar `templates/_ikon_sprite.html` satır içi SVG sprite (eksik ikon aynı Lucide çizim tarzıyla eklenir).
- Renkler yalnızca CSS değişkeni (`--renk-*`); yeni değişken TÜM tema bloklarında tanımlanır ya da `:root`'ta türetilir. Ham hex yalnız tema tanım bloklarında.
- Arayüz Türkçe, cümle düzeninde (BÜYÜK HARF başlık yok — bugünkü büyük harf tablo başlıkları da düzelir).
- Öncelikli çözünürlük 1366×768 (ve tahtalar); hiçbir sayfada yatay kaydırma olmamalı (telefon hariç, orada tablo kendi içinde kayabilir).
- Erişilebilirlik: klavye ile tam gezinme, görünür odak, `aria-current`/`aria-expanded`, yeterli kontrast (koyu temada da), `prefers-reduced-motion`.
- CSS/JS bağlantıları `?v=<static mtime>` taşımaya devam eder (`menu.statik_surum`).
- Her `Jinja2Templates` örneğinde `templates.env.globals["menu_agaci"]` kalır (`test_menu` denetler).

## Canlı üretim kısıtları (geçiş)
- `/home/ata/farabi` CANLI: servisler bu çalışma dizininden koşar, şablon/CSS değişikliği ANINDA yansır. Bu yüzden geliştirme canlı dizinde YAPILMAZ: ayrı git worktree + ayrı dal.
- Önizleme: worktree'den ayrı bir portta dashboard örneği çalıştırılır; Atakan tüm sayfaları orada gezip onaylar. Önizleme canlı veriyi DEĞİŞTİRMEMELİ: SQLite DB'nin kopyası kullanılır, yoklama polling'i ve sistem durumu toplayıcısı canlıyla çift çalışmamalı, okul_ana (PostgreSQL) ve dış servislere yazan eylemler önizlemede denenmez. Bunun mekanizması (ortam değişkeni vb.) uygulayıcıya bırakıldı; mekanizma canlı davranışı değiştirmemeli.
- Geçiş: onaydan sonra tek merge + ders saati dışında (08:00-17:00 TR dışı) `farabi-yoklama-dashboard` restart.
- Geri dönüş: geçişten önceki commit not edilir; sorun olursa o commit'e dönüp restart.

## Doğrulama
- Mevcut testler (`venv/bin/python -m unittest discover -p 'test_*.py'`) geçer; menü yapısı testleri yeni alan ağacına göre güncellenir.
- Tarayıcıda 1366×768'de tüm menü sayfaları gezilir: belge genişliği ve hiçbir kaydırma kutusu taşmaz (bugün kullanılan iframe ölçüm betiği gibi bir otomatik kontrol).
- 9 temanın her birinde ana ekran ve bir yönetim sayfası gözle kontrol (kontrast, okunurluk).
- Klavye ile: alan sekmeleri, sol menü, ayrıntı paneli formu gezilebilir.
- Son kabul: Atakan önizlemede (ve geçişten sonra fiziksel ekranında).

## Arayüz dondurma (Atakan kararı)
Geçişe kadar canlı panelin arayüzünde (menu.py, templates/, static/) değişiklik yapılmaz; yalnız acil hata düzeltmesi. Acil düzeltme olursa yeni dala da taşınır.

## Benim kararlarım (builder-check sonrası, Atakan'a sunuldu)
- **Dal:** yeni dal `panel-yeniden-tasarim`, canlının bulunduğu `atos-anythingllm-gemma`'dan (2026-10-30 taşma düzeltmesi commit'i dahil) ayrı worktree'de açılır; geçişte yine `atos-anythingllm-gemma`'ya merge edilir (canlı o dalı koşuyor). Master'a alma ayrı karardır.
- **Güvenlik sayfaları** (`kameralar*.html`, `guvenlik.html`, kendi girişli `/guvenlik`): bugün `taban.html`'i genişletmiyorlar; yeni kabuğa alınmaz, yalnız yeni renk/font değişkenlerine uyar (giris/acil_ekran gibi). Menüde Güvenlik alanından bağlantı olarak kalırlar.
- **Yerleşmeyen sayfalar:** Okul verisi "Denetim günlüğü" → Öğrenci ve personel alanının son sayfası ("Değişiklik günlüğü"). `/b/atos` ve yer tutucu sayfalar → üst çubuktaki ayar menüsü. `/kazanim` menüye girmez (kazanım testi kalıcı iptal; bugün de menüde yok).
- **Varsayılan tema:** kayıtlı tercihi olmayan herkes, işletim sistemi açık ya da koyu olsun, sade koyu ile açılır (ana tema C seçildi).
- **Ayrıntı paneli kapsamı:** Öğrenciler ve veliler, Personel, Sınıflar ve tahtalar, Kulüpler. Sınıf listesi (`admin_sinif_ogrenciler`) ve kulüp üyeleri (`admin_kulup_uyeler`) ayrı alt sayfa kalır, yalnız yeni görünüme geçer. Filtre çipleri yalnız mevcut veriden hesaplanan sayaçlarla (Personel: aktif/telefonsuz/TC/e-posta eksik/pasif; Öğrenci: aktif/telefonsuz/pasif); yeni sorgu alanı eklenmez.

## Uygulayıcıya bırakılanlar
- Kesin renk değerleri, punto/boşluk ölçeği (bir `--bosluk-*`/`--punto-*` ölçeği kurmak serbest ve önerilir), ikon seçimi.
- KPI kartlarının ana ekranda nasıl sadeleşeceği (ızgara ilk ekranda görünsün şartıyla).
- Ayrıntı panelinin sunucu taraflı mı JS'li mi olacağı.
- Sistem durumu, servisler, kameralar gibi liste/kayıt olmayan sayfaların iç düzeni (yeni kabuk + görsel dil + sığma kuralı içinde).
- CSS'in tek dosya mı (`pano.css`) yoksa birkaç dosyaya mı bölüneceği.
