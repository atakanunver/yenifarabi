# tahtayoklama

Sınıf akıllı tahtalarında dokunmatik yoklama arayüzü + (kuruluyor) merkezi
web panosu. **Farabi'den TAMAMEN BAĞIMSIZ** (bkz. `yoklama.py`'nin kendi
docstring'i, 2026-08-18 kullanıcı kararı) — Farabi'nin `actions/`
registry'sine girmez, `client/`'a bağlı değildir, kendi başına çalışır.
Farabi'nin sesli yoklaması ("derse gelmeyen öğrencilerin isimlerini söyler
misiniz?") bu sistemden habersizdir, DEĞİŞMEDİ — ikisi paralel, birbirinden
bağımsız iki yoklama yolu.

Uygulama planı: `plan.md` (bu dizinde) — **kasıtlı olarak bu dosyadan ayrı
tutuluyor**. `plan.md` = başlangıçta tasarlanan; bu dosya (`CLAUDE.md`) =
fiilen ne yapıldığı. İkisi birbirine kopyalanmaz, aralarındaki fark
istendiğinde incelenebilsin diye.

## Yapı

```
tahtayoklama/
├── yoklama.py            — tahtada çalışan PyQt6 GUI (bkz. dosyanın kendi docstring'i)
├── pdf_disari_aktar.py   — e-Okul/MEB PDF çıktısını roster JSON'a çevirir
├── data/                 — DEV kopyası; tahtalarda ~ogretmen/tahtayoklama/data/ olarak yaşar
│   ├── roster/<sinif>.json       — sınıf listesi ({"sinif", "ogrenciler": [{"no","ad_soyad","cinsiyet"}]})
│   ├── kayitlar/<tarih>_<sinif>_ders<no>.json — yoklama kaydı
│   └── zil.json                  — ders saati çizelgesi, Farabi'nin client/config/zil.json'undan KASITLI BAĞIMSIZ kopya
├── plan.md                — uygulama planı (bkz. yukarı)
└── dashboard/              — merkezi web panosu (bkz. aşağıdaki bölüm; inşa halinde)
```

## `yoklama.py` — tahta deployment gerçeği

Koddan ve canlı tahtalardan (9-A, 2026-08-23) doğrulandı:

- **Kendi venv'i YOK.** Tahtalarda `Exec=/home/ogretmen/farabi/client/venv/bin/python
  /home/ogretmen/tahtayoklama/yoklama.py` — Farabi'nin client venv'i
  kullanılıyor (zaten PyQt6 kurulu olduğu için). `requirements.txt`
  (`PyQt6`, `pdfplumber`) yalnızca dev makinede anlamlı.
- **Autostart DEĞİL.** `~/Masaüstü/Yoklama.desktop` ile öğretmen elle
  açıyor. Tahta açıldığında kendiliğinden başlamıyor.
- **Tamamen ağdan izole.** HTTP/socket/network I/O YOK. Tek durum kaynağı
  tahtanın kendi diskindeki JSON dosyaları
  (`~ogretmen/tahtayoklama/data/{roster,kayitlar}/`).
- **Kayıt tahta kimliğine değil, o an seçili sınıfa göre isimlendirilir.**
  Bir tahtanın hangi sınıfa ait olduğu dosya sisteminde tutulmuyor — yalnızca
  o an combo box'ta hangi sınıf seçiliyse o. Sınıf↔tahta eşlemesi
  değiştikçe (ör. ilk hafta) bir sınıfın kaydı farklı fiziksel tahtalardan
  gelebilir — bunu varsayan hiçbir kod "tahta X = sınıf Y" eşlemesine
  güvenmemeli, kayıt içeriğindeki `sinif` alanı esas alınmalı.
- **Otomatik sessiz kayıt riski**: ders dönemi değiştiğinde önceki dersin
  hâli otomatik kaydedilir (`_kaydet(sessiz=True)`) — tahta açık bırakılıp
  kimse dokunmazsa "herkes var" diye gerçek olmayan bir kayıt oluşur.
  Öğretmenin bilerek "YOKLAMAYI KAYDET"e basmasıyla aynı `alindi` durumunu
  üretir, şu an ayırt edilemiyor (bkz. `plan.md` Faz 7 — henüz yapılmadı).
- Pencere başlığı tam olarak `"Yoklama"`; 10 dakika kuralı ve kendi
  kendine öne gelme (`_pencereyi_one_getir`) `yoklama.py` içinde zaten var,
  panonun uzaktan başlatma özelliğiyle çakışmaz — pano yalnızca "hiç
  çalışmıyor" durumunu ele alır.

## `dashboard/` — merkezi web panosu

10 tahtanın yoklama durumunu tek sayfada toplayan, gerektiğinde ilgili
tahtada yoklama ekranını uzaktan açabilen, sınıf/roster/tahta eşlemesini
web üzerinden düzenlemeye izin veren ayrı bir servis.

- Farabi'nin `server/`'daki FastAPI'sinden (`farabi-api.service`,
  GPU-bağımlı) **tamamen bağımsız**: kendi venv'i, kendi SQLite DB'si, kendi
  portu, kendi systemd birimi. Deploy/restart döngüleri kasıtlı olarak
  birbirine bağlı değil.
- `server/tahtalar.json`'a geri yazma YAPILMAZ — pano kendi tahta/sınıf
  kaydını tutar (tek seferlik tohumlama dışında Farabi'nin dosyalarına
  dokunmaz).
- Detaylı mimari, DB şeması, SSH komutları, faz sırası: `plan.md`.
- Durum (bu bölüm, ilerledikçe güncellenecek): _henüz inşa edilmedi._

## Kurallar (kök `/home/ata/farabi/CLAUDE.md`'nin 1/3/4/6/8 maddelerine paralel)

1. Tahtalarda ÇALIŞAN `yoklama.py`'ye dokunmadan önce iki kez düşün —
   canlı, kullanımda bir sistem; geriye dönük uyumluluğu koru.
2. Tek seferde tek modül değiştir.
3. Değiştirmeden önce ilgili dosyayı oku — özellikle `yoklama.py`'nin veri
   şeması (roster/kayıt JSON) `dashboard/`'un varsaydığı şemayla birebir
   uyuşmalı.
4. Docker yok, systemd servisleri (kök CLAUDE.md'nin "Kurulum Biçimi"
   bölümüyle aynı konvansiyon).
5. Yeni ağır bağımlılık (paramiko, APScheduler, Redis, vb.) eklemeden önce
   onay iste — mevcut plan bilinçli olarak stdlib + FastAPI + Jinja2 +
   SQLite ile sınırlı tutuyor.
6. `dashboard/config/gizli.json` asla commit edilmez (repo konvansiyonu:
   `.example.json` şablonu committed, gerçek dosya gitignore'lu).

## Şu an yapılmayacaklar / henüz tamamlanmamış

`plan.md`'deki fazların tamamı henüz bitmedi — bu bölüm her faz
tamamlandıkça güncellenecek:

- ✅ Faz 0 (bu dosya) — TAMAMLANDI (2026-08-23)
- ✅ Faz 1 (pano iskeleti, DB, auth) — TAMAMLANDI (2026-08-23), uçtan uca
  doğrulandı (giriş/çıkış, oturum çerezi, DB tohumlama). Plandan tek
  sapma: `tahtalar` tablosuna plan.md'de olmayan bir `python_yolu` sütunu
  eklendi — canlı SSH ile doğrulandı ki `yoklama.py`'yi çalıştıran python
  yolu tahtadan tahtaya FARKLI (9-A hariç hepsi kendi
  `~/tahtayoklama/venv`'ini kullanıyor, yalnızca 9-A Farabi'nin
  `~/farabi/client/venv`'ini kullanıyor — `network.txt`'teki not
  doğrulandı). Faz 4 (uzaktan başlatma) bu yolu sabit kodlamak yerine
  buradan okuyacak.
- ✅ Faz 2 (SSH polling motoru) — TAMAMLANDI (2026-08-23), gerçek tahtalara
  karşı uçtan uca doğrulandı: 7 tahtanın hepsi tarandı, bugünün 5 gerçek
  dersi doğru `alindi` çıktı, `ders_gunleri` dışı dersler (bugün fiilen
  Pazar — `zil.json`'da yalnızca Pzt-Cuma tanımlı) doğru `ders_yok_o_gun`
  çıktı, isim çözümleme (roster'da bulunamayan no dahil) test edildi. Plandan
  tek sapma: `zil.py`'ye `Europe/Istanbul` saat dilimi sabitlendi
  (`zoneinfo`) — dashboard'un barınacağı sunucunun sistem saat dilimi ne
  olursa olsun (bu dev ortamı UTC, tahtalar +03 çalışıyor, canlı doğrulandı)
  ders zamanlaması karşılaştırmaları her zaman Türkiye saatiyle yapılsın diye;
  plan.md bunu öngörmüyordu.
- ✅ Faz 3 (pano tablosu + tarih seçici) — TAMAMLANDI (2026-08-23). Sunucu
  tarafı (sıralama, sinif↔tahta eşlemesi, gelecek tarih kelepçeleme) `curl`
  ile doğrulandı; tarayıcı görsel doğrulaması YAPILMADI (Chrome uzantısı bu
  oturumda kullanılamadı) — kullanıcı kendi tarayıcısında `http://<sunucu
  IP>:8010/` açıp gözle teyit etmeli.
- ✅ Faz 4 (uzaktan başlatma) — TAMAMLANDI (2026-08-23), 9-A'da uçtan uca
  doğrulandı: hem "çalışmıyor → başlat" hem "çalışıyor → öne getir" yolları
  gerçek SSH ile test edildi, ardından test süreci temizlendi. Plandan iki
  sapma:
  1. **Masaüstü ortamı XFCE DEĞİL, Cinnamon** — canlı doğrulandı (9-A,
     `cinnamon-session` süreci; `.xsession` dosyası `xfce4-session` yazsa
     da fiilen çalışan bu değil). X ortamı keşfi (`uzaktan_baslat.py`)
     belirli bir oturum yöneticisi sürecine bağlı KALMADAN, DISPLAY=:0 olan
     herhangi bir süreci genel taramayla buluyor — plan.md'nin varsaydığı
     `pgrep -x xfce4-session` yaklaşımı kullanılmadı, kullanılsaydı sessizce
     hiçbir tahtada çalışmazdı.
  2. **`pgrep -af` öz-eşleşme hatası** — SSH üzerinden bileşik komutlarla
     (`cmd1; cmd2 || cmd3`) çalıştırıldığında, geride kalan sarmalayıcı
     kabuk sürecinin KENDİ komut metni arama deseniyle eşleşip yanlış
     pozitif üretebiliyor (canlı gözlemlendi, debug sırasında). Üretim
     kodundaki `_CALISIYOR_MU_KOMUTU` klasik `[t]ahtayoklama` köşeli parantez
     numarasıyla bağışık yapıldı.
  Ayrıca: gerçek sunucuda (`hostname` = `farabi`, bu makinenin kendisi)
  `farabi-yoklama-dashboard.service` systemd birimi kuruldu, etkinleştirildi
  ve `0.0.0.0:8010`'da çalışıyor — `farabi-api.service` ile aynı desen,
  ona `After=`/`Wants=` YOK (tam ayrık). Giriş şifresi ayrıca üretildi
  (test şifresi DEĞİL) — kullanıcıya ayrıca iletildi,
  `dashboard/config/gizli.json`'da (gitignore'lu).
- ✅ Faz 5 (yönetim ekranları) — TAMAMLANDI (2026-08-23). `/admin/tahtalar`
  (sınıf ataması, aktif/pasif, hızlı takas + sürükle-bırak) ve
  `/admin/siniflar` (+ `/admin/siniflar/{id}/ogrenciler` roster düzenleme,
  `.../senkronize` tahtaya SSH ile atomik yazma) canlı sistemde test edildi:
  yeni sınıf oluşturma, roster kaydetme, senkron hem başarılı hem (dizin
  yok) başarısız yol, tahta↔sınıf takas ve geri-takas — hepsi gerçek 9-A/
  9-B/tahta-235 üzerinde doğrulandı, test verisi sonra temizlendi, üretim
  durumu (9-A→9-A, 9-B→9-B) bozulmadan bırakıldı. Plandan sapma yok.
- ⏳ Faz 6 — kullanıcı isteğiyle bekletiliyor (bkz. yukarıdaki "Faz 6" bölümü)
- ✅ Görsel tasarım yenileme (2026-08-23, plan.md'de yoktu — kullanıcı
  isteğiyle sonradan eklendi) — `static/pano.css` CSS-değişkenli bir tasarım
  sistemiyle baştan yazıldı (renk paleti, durum rozetleri/pill'ler, kart
  görünümü, sticky başlık/ilk sütun), `giris.html` ve `admin_*.html`
  şablonları aynı sisteme taşındı, favicon eklendi. Tarayıcı görsel
  doğrulaması YAPILMADI (Chrome uzantısı bu oturumda da kullanılamadı) —
  yalnızca curl ile yapısal doğrulama (sayfalar 200 dönüyor, pill/favicon
  markup'ı doğru üretiliyor) yapıldı; kullanıcı kendi tarayıcısında
  değerlendirmeli.
- ⛔ Faz 7 (gerçek yoklama vs. otomatik kayıt ayrımı, `yoklama.py`'de
  `elle_kaydedildi` alanı) — ayrı onay gerekir, bu proje kapsamında henüz
  planlanmadı
- ✅ Rapor ekranı (2026-08-24, plan.md'de yoktu — kullanıcı isteğiyle
  sonradan eklendi) — `/admin/rapor`: tarih aralığı + sınıf filtresiyle
  (a) tarih/sınıf/ders detay tablosu, (b) öğrenci bazlı devamsızlık sayacı
  (`yoklama_onbellek`'teki `yok_isimleri`/`izinli_isimleri` JSON alanları
  parse edilip (sınıf, öğrenci) anahtarıyla sayılıyor — isim çakışmasını
  önlemek için sınıf da anahtarda), (c) her ikisi için CSV indirme
  (`utf-8-sig` + `;` ayraç, Türkçe karakterler Excel'de bozulmasın diye).
  `ders_yok_o_gun` satırları rapordan filtrelenir (hafta sonu/tatil
  gürültüsü). Not: `yoklama_onbellek` adı "önbellek" olsa da hiçbir satır
  silinmiyor (`ON CONFLICT ... DO UPDATE`, `yoklayici.py`) — yani "günlük
  yoklamaların veritabanında tutulması" zaten baştan beri sağlanıyordu,
  eksik olan yalnızca bu geriye dönük görünümdü. `/admin/rapor` ve
  `/admin/rapor/csv` uçtan uca curl ile doğrulandı (elle oluşturulmuş
  oturum token'ıyla, gerçek şifre kullanılmadan); tarayıcı görsel
  doğrulaması yapılmadı.

## Tahta↔sınıf ataması, kalıcı gerçek (2026-08-24)

Eylül'e hazırlık: fiziksel odalar arasında üçlü bir rotasyon yapıldı —
"9-B" tahtası artık 10-A'yı, "10-A" tahtası artık 11-B'yi, "11-B" tahtası
artık 9-B'yi gösteriyor (oda üzerindeki tabela DEĞİŞMEDİ, yalnızca içerik).
Bununla ilgili öğrenilenler:

- **`/admin/tahtalar`'daki atama/takas SADECE dashboard'un kendi
  SQLite'ını değiştirir, tahtaya HİÇBİR ŞEY göndermez** — bunu ilk elden
  yaşandı: kullanıcı bu ekranla atama yaptı, "değişiklik uygulanmadı"
  diye bildirdi, log'da o gün hiç `/admin/siniflar/*/senkronize` isteği
  olmadığı görüldü. Tahtaya gerçekten dosya yazan TEK yol
  `/admin/siniflar/{id}/ogrenciler` sayfasındaki `Senkronize et` — atama
  değiştikten SONRA ayrıca çalıştırılması gerekiyor, otomatik tetiklenmiyor.
- `sinif_senkronize` başarı/hata farkı olmadan her zaman HTTP 200 döner
  (SSH gerçekten başarısız olsa bile) — sunucu log'undaki "200 OK" satırı
  dosyanın tahtaya ulaştığının kanıtı DEĞİL. Doğrulama SSH ile dosyayı
  geri okuyarak yapıldı (`cat`/`ls`), dashboard'un kendi render'ına
  güvenilmedi.
- `senkronize` eski roster dosyasını SİLMEZ, yalnızca yeni dosyayı ekler
  (`{sinif}.json` adıyla) — tahtada eski ve yeni sınıf dosyası bir arada
  kalıyor. Bu swap'ta elle SSH ile silindi (`9-B.json` .242'den,
  `11-B.json` .239'dan).
- `yoklama.py`'nin sınıf seçme kutusu (`QComboBox`) yalnızca **uygulama
  açılışında** `data/roster/*.json` taranarak dolduruluyor — yeni
  senkronize edilen dosya, uygulama zaten açıksa combo'da görünmez,
  öğretmenin uygulamayı kapatıp yeniden açması gerekir. Faz 4'teki uzaktan
  başlatma yalnızca ÖLÜ bir örneği başlatıyor, canlı bir örneği yeniden
  başlatmıyor — bu ayrım henüz hiçbir yerde otomatikleştirilmedi.
- 192.168.23.233 (10-A tahtası) bu swap sırasında ağda erişilemez durumda
  bulundu (ping bile dönmedi) — 11-B roster'ı oraya HENÜZ gönderilemedi,
  DB'de sinif_id doğru (11-B) ama tahtanın diskinde hâlâ eski `10-A.json`
  var. Tahta açılıp ağa bağlanınca `/admin/siniflar/3/ogrenciler` (11-B)
  sayfasından `Senkronize et` tekrar çalıştırılmalı.
  ✅ **Çözüldü (2026-08-24, aynı gün ilerleyen saatte):** tahta ağa geri
  bağlandı, `192.168.23.233`'e `11-B.json` gönderildi ve eski `10-A.json`
  silindi — bkz. aşağıdaki "`/admin/tahtalar` sadeleştirmesi" notu (asıl
  kullanıcı şikayeti buydu: "web arayüzü işlemi yapmıyor").

### `/admin/tahtalar` sadeleştirmesi + atama=yükleme birleşmesi (2026-08-24)

Kullanıcı canlıda tam olarak yukarıdaki "atama SADECE DB'yi değiştirir,
tahtaya hiçbir şey göndermez" tuzağına bir kez daha düştü (log'da aynı
tahtaya art arda iki `POST /admin/tahtalar/3` görüldü — kullanıcı "kaydet"e
basıp hiçbir şey olmadığını görmüştü) ve ayrıca "takas et" / sürükle-bırak
özelliğini kafa karıştırıcı buldu. Kullanıcı isteğiyle:

- **`tahta_takas` route'u ve UI'daki "Şununla yer değiştir ↔" sürükle-bırak
  özelliği tamamen kaldırıldı** — artık iki tahtanın sınıfını karşılıklı
  değiştirmenin tek yolu, her ikisinde ayrı ayrı doğru listeyi seçmek.
- **Atama ve senkronizasyon TEK adımda birleştirildi**: `/admin/tahtalar`
  sayfasında bir tahtaya liste seçip "Yükle"ye basmak artık hem DB'deki
  `sinif_id`'yi günceller HEM DE seçilen roster'ı SSH ile AYNI İSTEKTE o
  tek tahtaya yazar — `/admin/siniflar/{id}/ogrenciler` sayfasındaki ayrı
  "Senkronize et" adımı artık gerekmiyor (o buton ve route hâlâ duruyor,
  bir sınıfa bağlı BİRDEN FAZLA tahtayı tek seferde senkronize etmek
  isteyen ileri kullanım için — ama günlük "bu tahtaya bu listeyi yükle"
  akışı artık tek tıkla).
- **Her yüklemede tahtadaki eski roster dosyaları otomatik silinir**
  (`find ... -delete`, yeni yazılan dosya hariç) — kullanıcının ayrı
  isteği: "web arayüzünde değişiklik yapıldığı anda json dosyasını
  değiştir, tahtadaki eski dosyayı sil". Önceden bu elle SSH ile
  yapılıyordu (bkz. yukarıdaki swap notu); artık `admin.py`'deki
  `_tahtaya_roster_gonder` her çağrıda yapıyor, hem tekil "Yükle" hem
  toplu "Senkronize et" yolunda.
- `aktif` kutusu ve "IP ile tahtayı tanı" başlığı kasıtlı olarak
  KORUNDU — kullanıcının şikayeti yalnızca takas/sürükle-bırak
  karmaşasıyla ilgiliydi, tahta ekleme/aktif-pasif etme özelliği aynı
  kaldı.
- Not: `yoklama.py`'nin sınıf seçme kutusu hâlâ yalnızca uygulama
  açılışında taranıyor (bkz. yukarıdaki not) — bu davranış bu değişiklikle
  değişmedi, "Yükle" tahtaya dosyayı anında yazar ama uygulama zaten açıksa
  öğretmenin onu kapatıp yeniden açması hâlâ gerekiyor.

### 11. tahta bulundu, gerçek 11-A oldu — eski 11-A/236 boşa çıktı (2026-08-24)

Kök `CLAUDE.md`'nin "Ağ Envanteri" bölümünde (2026-08-24 eklendi) belirtilen
11. tahta bugün ağa bağlandı: `192.168.23.228`, MAC `00:09:df:83:50:6e`.
Kullanıcı bunun **gerçek 11-A sınıfı** olduğunu teyit etti — önceden `11-A`
etiketiyle kayıtlı olan `192.168.23.236` yanlış/eskiydi. Tam kimlik bilgisi
ve IP listesi `network.txt`'te (gitignore'lu); burada yalnızca bu projeye
özgü sonuç kayıtlı:

- 228'e sıfırdan tahtayoklama kuruldu: `~/tahtayoklama/venv` (PyQt6 +
  pdfplumber pip ile — diğer tahtalarla aynı desen, 9-A hariç hepsi böyle
  kurulu), `data/roster/11-A.json` (mevcut 11-A roster'ının aynısı —
  sınıfın kendisi değişmedi, yalnızca fiziksel tahtası değişti),
  `~/Masaüstü/Yoklama.desktop`. `QT_QPA_PLATFORM=offscreen` ile modül
  import/syntax doğrulaması yapıldı (gerçek dokunmatik ekranda görsel
  doğrulama YAPILMADI — uzaktan erişimle mümkün değil).
- Dashboard DB'sinde (`veri/yoklama_pano.db`): eski `tahtalar` satırı
  (id=4, ip=.236) `tahta-236` adına yeniden adlandırıldı, `sinif_id` NULL
  yapıldı (11-A sınıfı/roster'ı — `siniflar.id=2` — SİLİNMEDİ, kullanıcının
  açık isteği buydu, yalnızca tahta ataması kaldırıldı). 228 için yeni
  satır eklendi (`ad='11-A'`, `sinif_id=2`) — uygulamanın kendi
  `/admin/tahtalar/{id}` ("Yükle") route'u üzerinden test edilip
  `senkron-sonuc-tek basarili` sonucu doğrulandı.
- ⚠️ **Açık iş:** eski tahta (236) kurulum sırasında ağda erişilemez
  durumdaydı ("no route to host") — diskindeki eski
  `data/roster/11-A.json` dosyası SİLİNEMEDİ. Ağa geri bağlanınca ya elle
  SSH ile silinmeli ya da `/admin/tahtalar` üzerinden boş bir "Yükle"
  (sinif_id'siz) çalıştırılıp elle temizlenmeli — aksi halde o tahtanın
  öğretmeni combo box'ta hâlâ "11-A"yı görüp yanlış fiziksel odadan
  yoklama girebilir (bkz. yukarıdaki swap notundaki aynı risk).
- `server/tahtalar.json`'da `"11-A"` artık 228'i gösteriyor, eski kayıt
  `"tahta-236"` adıyla ayrı satırda korundu (silinmedi — SSH erişimi hâlâ
  gerekebilir).
- ✅ **Düzeltildi (2026-08-24, aynı gün ilerleyen saatte): "yoklama sistemi
  çalışmıyor" şikayeti.** Kök neden: 228'de `libxcb-cursor0` sistem
  kütüphanesi eksikti (Qt6 6.5.0+'ın xcb platform plugin'i için zorunlu;
  9-A/9-B gibi diğer tahtalarda kurulu, bu tahtaya sıfırdan kurulumda
  atlanmış). Eksikken `yoklama.py` hiçbir pencere açmadan sessizce
  çöküyordu — `Terminal=false` olduğu için öğretmen hiçbir hata görmüyor,
  yalnızca "simgeye tıklayınca hiçbir şey olmuyor" izlenimi ediniyordu.
  `sudo apt-get install -y libxcb-cursor0` (etapadmin) ile kuruldu; gerçek
  `DISPLAY=:0`'da `yoklama.py` yeniden başlatılıp `xwininfo -root -tree` ile
  1920x1080 "Yoklama" penceresinin fiilen açıldığı doğrulandı, test süreci
  sonra kapatıldı. Diğer tahtalarda bu paket zaten var — yalnızca 228'e
  özgü bir kurulum eksiğiydi, kod tarafında değişiklik gerekmedi.

## Faz 6 — kullanıcı isteğiyle BEKLETİLİYOR (2026-08-23)

`tahta-234`/`tahta-235`/`tahta-244` sınıf DEĞİL — üçü birden fen-lab/
kütüphane/spor odasından biri (kullanıcı teyidi, hangi IP'nin hangisi
olduğu henüz netleşmedi, bkz. `network.txt`). Bu 3 yerde yoklama
alınmayacak — Faz 6 (lab1/lab2/lab3 kurulumu) planı bu yüzden kullanıcı
isteğiyle iptal/beklemede; dashboard'da bu 3 tahta `tahta_atanmamis`
durumunda kalmaya devam edecek, `siniflar` tablosuna eklenmeyecekler.

Ayrıca kullanıcı bilinen 10 tahtaya ek **11. bir tahta** olduğunu bildirdi
— şu an fişi çekili/kapalı, IP/MAC bilinmiyor, "orası bir sınıf olabilir."
Bu tahta ağa bağlanıp IP/MAC tespit edilene kadar hiçbir şey yapılamaz;
bağlandığında hem `network.txt` hem `server/tahtalar.json` hem bu projenin
DB'si güncellenmeli (`scripts/ilk_yukleme.py`'nin tek-seferlik semantiğine
göre elle bir `tahtalar` satırı eklenecek, yeniden tüm DB tohumlanmayacak).
