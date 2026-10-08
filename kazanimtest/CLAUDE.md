# kazanimtest

Haftanın yıllık plan kazanımına göre soru seçer (MEB `kazanim_test_soru` → yetmezse
`soru_havuzu` onaylı), agy ile eler, öğretmene Excel/Word üretir, Google Apps Script ile
**Google Form (Quiz) + yanıt Tablosu** açar, isteğe bağlı öğrencilere SMS atar. Servis DEĞİL
(soruhavuzu gibi script + timer, server venv'i). smssistemi'ne yalnızca HTTP
(`/api/arac/ogrenci-taslak`, `/ogrenci-gonder`, `X-Sms-Arac-Key`).

- Çalıştırma (kökten): `server/venv/bin/python -m kazanimtest.calistir uret [--tarih YYYY-MM-DD] [--sinif 9-A] [--ders biyoloji] [--kuru] [--sms]` ve `... durum`.
  `--kuru` = yalnızca `/mnt/farabi-data/farabi/kazanim_testleri/` altına xlsx+docx (Form/SMS/DB yok).
- `... sonuc`: son `sonuc_gun` (ayar, varsayılan 30) günün formlarının gönderimlerini Apps Script'ten (`islem:"sonuclar"`) çekip `form_cevap`a yazar (UNIQUE sayesinde tekrar güvenli; aynı okul no birden çok gönderirse EN ERKEN gönderim sayılır, ilk yazılan kalır). Geçersiz okul no atlanır, eşleşmeyen şık `secilen NULL`/yanlış sayılır; özet `journalctl`'de. Timer `systemd/kazanim-test-sonuc.{service,timer}` (her gün 21:00 UTC, `/etc`'ye elle kopyalanır).
- `... anlik-doldur`: `form_testi.sorular` (jsonb anlık görüntü: kimlik, soru, şıklar, doğru, etiket, `kazanim_satiri` = bge-m3 ile en benzer kazanım satırı) NULL olan eski kayıtları `havuz:`/`meb:` kimliklerinden doldurur. Yeni formlarda `uret` kendisi yazar. `soru_sira` = bu dizideki 0 tabanlı sıra.
- Sonuç çekmek için `sorular` dolu olmalı; `sema.sql` (ALTER + `form_cevap`) `uret`ten ÖNCE uygulanmalı (yoksa `kaydet` kolon hatası verir).
- Test: `server/venv/bin/python -m pytest kazanimtest/tests -q` (DB/agy/ağ/embedding mock'lu).
- Şema `sema.sql` (`form_testi`, `UNIQUE(sinif, ders, hafta)`) soru_havuzu DB'ye elle uygulanır:
  `psql -h 127.0.0.1 -U farabi -d soru_havuzu -f kazanimtest/sema.sql`.
- Ayar `config/ayar.json`: `dersler` = beyaz liste (ders ANAHTARI: biyoloji, fizik, edebiyat…;
  başlangıçta BOŞ → hiçbir şey üretilmez), `soru_sayisi` 10.
- Ders adı eşlemesi tek yerde: `soruhavuzu/dersler.py::ders_anahtari` (program "hedef fizik",
  MEB tablosu "Türk Dili ve Edebiyatı", havuz "edebiyat" hep aynı anahtara iner).
  Kazanım metni ise programdaki HAM adla `kazanimlar.json`'dan aranır.
- ⚠️ MEB `kazanim_test_soru`: yalnızca 12. sınıf, şıklar A-E (5), `cevap` kolonu BOŞ (2026-10-07
  ölçümü) → şu an MEB adayı çıkmaz, hepsi soru havuzundan gelir. Seçici cevabı dolu + 4 şıklı
  satırları alır; cevap anahtarı yüklenirse otomatik devreye girer.
- `--sms-test`: `--sms` ile aynı akış ama taslağa `gizli.json::test_telefon` eklenir → SMS sınıfa değil yalnızca o numaraya gider (alan yoksa hata, SMS atılmaz; test gönderimi `sms_gonderim_id` işaretlemez). Numara yalnızca gitignore'lu gizli.json'a yazılır, repoya asla.
- Timer `systemd/kazanim-test.{service,timer}` `/etc/systemd/system/`'e elle kopyalanır; ilk
  haftalarda `--sms` YOK. Birim değişirse oraya da kopyala.
- **Google'a proxy ile gidilir** (`gizli.json::proxy` = Müdür PC WifiHttpProxy, ollama.service'teki
  `HTTPS_PROXY` ile aynı). Doğrudan bağlantı okulun SSL incelemesine takılıyor (certifi: "self-signed";
  sistem deposu: Python 3.14 katı X509 "Missing Authority Key Identifier"). Proxy kapalıysa form açılmaz.
- Apps Script 401 + "Sayfa Bulunamadı / dosyayı açamıyoruz" döndürürse: dağıtımın erişimi "Herkes" değil.
- Gizlilik: Google'a yalnızca soru metinleri + "Okul numarası" alanı ve cevapları gider; ad/telefon gitmez.

## Apps Script kurulumu (bir kez, okulun Google hesabıyla)
1. https://script.google.com → Yeni proje; ad: "Kazanım Testi".
2. `apps_script/Code.gs` içeriğini yapıştır, kaydet.
3. Proje Ayarları → Betik Özellikleri → `ANAHTAR` = uzun rastgele bir dize.
4. Dağıt → Yeni dağıtım → Tür: Web uygulaması; Şu kullanıcı olarak çalıştır: **Ben**;
   Erişim: **Herkes** (anahtar doğrulaması kodda). İlk seferde Forms/Drive/Sheets izinlerini onayla.
5. Verilen `.../exec` adresini `config/gizli.json::script_url`'e, aynı ANAHTAR'ı `anahtar`'a yaz;
   SMS aracı anahtarını `sms_arac_anahtar`'a yaz (`gizli.example.json` örnek; dosya gitignore'lu).
6. Kod değişirse: Dağıt → Dağıtımları yönet → düzenle → Yeni sürüm (`sonuclar` işlemi için Code.gs yeniden dağıtılmalı; aksi halde `sonuc` eski kodu çağırır ve hata alır).
7. Deneme: `calistir uret --kuru ...` sonra `--kuru`suz tek sınıf/ders; formu telefondan doldur.

## Analiz raporu (`analiz`, Faz 2 adım 2)
- `calistir analiz` (salt-okunur DB): her `form_testi` sınıfı için tüm zamanlar analizi → `<cikti_dizini>/rapor/<sinif>.json` (atomik yazım, UTF-8). `kazanim-test-sonuc.service`: `sonuc` (başarısız olsa da, `-` önekli) sonra `analiz`. Birim `/etc`'ye elle kopyalanır. `analiz.sinif_analizi(conn, sinif, baslangic, bitis, esikler)` aylık rapor için tarih aralığı alır (`form_testi.olusturma`, TR günü).
- Eşikler `ayar.json`: `zorlanilan_esik` 0.5 (sınıf oranı < eşik), `eksik_esik` 0.5 (oran < → eksik), `guclu_esik` 0.8 (oran >= → güçlü), `kazanim_min_soru` 2 (öğrencide bundan az soru → `az_veri`).
- JSON (İSİM YOK, yalnızca okul_no): `sinif, uretim, aralik, esikler, testler[{id,ders,hafta,tarih,kazanim,form_url,katilim,ortalama_oran,sorular[{sira,soru,kazanim_satiri,dogru_orani,cevap_sayisi,en_cok_secilen_yanlis{sik_harfi,oran}|null}]}], kazanimlar[{ders,kazanim_satiri,soru_sayisi,cevap_sayisi,dogru_orani,zorlanilan}]` (zorlanılan önce, oran artan), `ogrenciler[{okul_no,test_sayisi,dogru,toplam,oran,eksik_sayisi,guclu_sayisi,kazanimlar[{ders,kazanim_satiri,soru,dogru,oran,durum,sayfalar}]}]`. `sayfalar` = öğrencinin yanlış/boş yaptığı soruların kaynak sayfaları ("Kimya 9, s. 54-55"). `sorular` NULL formlar atlanır (log).

## Aylık veli/öğrenci raporu (`aylik`, Faz 2 adım 5)
- `calistir aylik [--ay YYYY-MM] [--sinif 9-A] [--sms | --sms-test] [--kuru]` (`aylik.py`). Varsayılan ay = önceki ay (Europe/Istanbul). O ayda formu olan her sınıf için `analiz.sinif_analizi(ay aralığı)` → teste katılan her öğrenci için rapor verisi (teste katılmayana rapor yok). `--kuru`: hesaplar + özet loglar; Google/DB/SMS'e yazmaz.
- Gizlilik: Google'a YALNIZCA `sinif + okul_no + kazanım sonuçları` gider (rapor verisinde ad/telefon alanı yok, testle sabitli). İsim yalnızca SMS metnine smssistemi'nde `{ad}` yerine girer.
- Şema `aylik_rapor` (`sema.sql`, ELLE uygulanır): `UNIQUE(ay, okul_no)`; tekrar çalıştırmada MEVCUT token kullanılır (link değişmez), veri/geçerlilik güncellenir. Token `secrets.token_urlsafe(16)`, geçerlilik `ayar.json::rapor_gecerlilik_gun` (90).
- Apps Script: `islem:"rapor_yaz"` → "Kazanım Raporları" e-tablosu (ilk çağrıda oluşur, Kazanım Testleri klasörüne taşınır, id Script Properties `RAPOR_TABLO_ID`; sütunlar token, ay, sinif, okul_no, son_gecerlilik, veri_json, yazilma; aynı token güncellenir; 50'lik partiler). `doGet?r=<token>` mobil rapor sayfası (tüm metinler `kacis_()` ile escape; yoksa/süresi geçtiyse genel mesaj).
- Link = `gizli.json::script_url + "?r=" + token`. SMS şablonu `ayar.json::rapor_sms_sablon` (`{ay_adi}`, `{link}` burada, `{ad}` smssistemi'nde doldurulur; ad payı 45 karakterle ≤300 denetlenir, sığmazsa SMS atılmaz). Tek `kisisel-taslak` → `kisisel-gonder` (taslak 30 dk geçerli). `--sms-test`: `gizli.json::test_telefon`, yalnız ilk bulunan öğe, `aylik_rapor.sms_*` işaretlenmez. Gerçek gönderimde `sms_gonderim_id` dolu satırlar tekrar gönderilmez; yanıttaki bulunamayan/alıcısız log'a yazılır (o satırlar işaretlenmez).
- Timer `systemd/kazanim-test-aylik.{service,timer}` (her ayın 1'i 06:00 UTC, SMS YOK; `/etc`'ye elle kopyalanır). İlk ay SMS'siz: raporlar kontrol edilince `--sms-test` sonra `--sms` elle.
- ⚠️ `Code.gs` değişti (`rapor_yaz` + `doGet`): Apps Script'te kodu yapıştır, Dağıt → Dağıtımları yönet → düzenle → Yeni sürüm (yoksa `/exec` eski kodu çalıştırır; `doGet` yeni izin gerektirmez ama `rapor_yaz` ilk çağrıda Sheets/Drive izni ister).
