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
