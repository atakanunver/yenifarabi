# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Ne bu proje

Müdür PC masaüstündeki Tkinter tabanlı `sms sistemi` (Huawei HiLink modem
üzerinden toplu SMS) uygulamasının web eşdeğeri. Farabi sunucusunda
(`farabi.local`) bağımsız bir FastAPI servisi olarak çalışır — okul
idaresinin öğrenci velilerine toplu/kişiselleştirilmiş SMS göndermesini
sağlar.

Tasarım kararları ve mimari gerekçe: `../docs/superpowers/specs/2026-09-19-smssistemi-design.md`
(bu dosyayı önce oku — kod yorumlarının çoğu ona işaret ediyor).

**Kasıtlı olarak bağımsız:** `tahtayoklama/dashboard` ile hiçbir kod paylaşımı
yok. `auth.py`/`db.py` dashboard'daki aynı isimli dosyaların desenini takip
eder ama satır satır bağımsız kopyadır — biri değişince diğeri otomatik
güncellenmez, bu bilinçli bir karar (yukarıdaki spec, "Kullanıcı kararları").
Dashboard'la bağlantı: panonun menüsündeki linkler + HMAC imzalı SSO
köprüsü (`/sms-git`, `/dogum`, `/otomasyon-git` → `/sso`).
**TEK İSTİSNA (2026-09-23):** panonun DB'si salt-okunur okunuyor —
`yoklama_kaynak.py` üzerinden; onu kullananlar `/yoklama-sms`
(`yoklama_mantik.py`) VE İlk Ders Otomasyonu (`otomasyon.py`). Aşağıdaki
"Yoklama SMS Modülü" bölümüne bak.

## Durum (2026-10-01 / Güncel)

Üretimde çalışıyor. `farabi-smssistemi.service` aktif (port 8020),
`app.py` + `templates/`/`static/` yazıldı, gerçek bir SMS ucu ucuna
doğrulandı (bkz. kök `DECISIONS.md`). Dashboard'dan tek tıkla giriş
(SSO) çalışıyor: `/sms-git` (dashboard) → `/sso?t=..&s=..` (smssistemi),
kısa ömürlü (30sn) HMAC-imzalı token — paylaşılan anahtar
`config/sso.json` (~dashboard'daki `config/sms_sso.json` eşi),
gitignore'lu, kod/DB paylaşımı yok.

**Loglama (2026-09-29):** `app.py::log_ayarla()` yalnızca `smssistemi.*`
logger ağacını INFO düzeyinde stderr'e (→ journal) bağlar, kök logger'a
dokunmaz. Otomasyonun gerçekten kendiliğinden çalıştığının kanıtı journal'daki
"tetikleniyor" satırı + `otomasyon_ilk_ders_son_sonuc.tetikleyen ==
"otomatik_zamanlayici"`. Test: `test_log_ayari.py`.

**Rehber (telefon defteri) eklendi:** `siniflar` (bu yıl için 9-A..12-B,
ekle/sil yapılabilir) + `kisiler` (ad_soyad, telefon [boş olabilir],
sinif_id, tur='ogrenci'|'veli'|'personel', ogrenci_kisi_id [nullable FK → kisiler.id,
yalnızca veliler için öğrenci bağlantısı], dogum_tarihi [ISO YYYY-MM-DD],
okul_no [INTEGER], veli_rol [TEXT: 'Anne'|'Baba'|'Teyze'|'Anneanne']) tabloları, `/rehber` sayfası.

**Tüm Sınıfların Veli & Öğrenci Telefonları Baştan Aktarıldı (`scripts/velitelefon_ice_aktar.py` — 2026-09-24):**
- Kaynak: `velitelefon/` dizinindeki 7 sınıf Excel dosyası (`9-A.xlsx`, `9-B.xlsx`, `10-A.xlsx`, `11-A.xlsx`, `11-B.xlsx`, `12-A.xlsx`, `12-B.xlsx`).
- 102 öğrencinin okul numaraları (`okul_no`), kendi telefonları (92 adet) ve veli telefonları (191 adet) ilişkisel olarak sıfırdan kuruldu.
- Çift Veli İlişkisi: 89 öğrencinin hem Anne hem Baba olmak üzere 2 velisi, 13 öğrencinin 1 velisi oluşturuldu. Birincil veli Excel'deki gerçek adıyla, ikincisi `{Öğrenci Adı} Babası` / `{Öğrenci Adı} Annesi` formatında kaydedildi.
- Kardeşler: Her veli satırı tek bir öğrenciye `ogrenci_kisi_id` ile bağlandı (SMS kişiselleştirmede doğru çocuğun adının geçmesi için).
- İsimler Türkçe Title Case (Baş Harfleri Büyük) olarak normalize edildi.
- 12-B'de yanlış tür ile girilmiş bir kayıt (öğrenci yerine veli/baba olması gereken bir isim öğrenci olarak girilmişti) temizlendi; yerine doğru öğrenci eklendi, yanlış girilen isim baba olarak kaydedildi.
- 11-A'ya geçen bir öğrenci güncel sınıfına taşındı.
- Doğrulanmış doğum tarihleri (99 öğrenci, 23 personel) eksiksiz korundu. Toplam: 102 öğrenci, 191 veli, 23 personel (316 kişi).

**Doğum Günleri Modülü (2026-09-20/21 eklendi):**
- Sayfalar: `/dogum-gunleri` (yaklaşan ve bugünkü doğum günleri panosu, personel/öğrenci filtresi, doğrudan doğum tarihi düzenleme, otomatik SMS ayarları şalteri) ve `/dogum-gunleri/ice-aktar` (Excel analizi, 3 kategoriye ayırma).
- Yaş Kuralı & İş Mantığı (`dogum_mantik.py`):
  - 13–19 yaş: Aktif öğrenci (101 mevcut öğrenciyle eşleşenler doğrudan bağlanır, onay gerekmez).
  - 20 yaş ve üzeri: Personel adayı (varsayılan seçili, `tur='personel'`, Personel sınıfına eklenir).
  - Listede olmayan eski/ayrılan öğrenciler: Ayrılan öğrenci adayı (varsayılan seçili DEĞİL, DB temiz tutulur).
- Dashboard Entegrasyonu: Tahtayoklama panosunda sol menüye "Doğum Günleri" linki (`/dogum`) eklendi; HMAC-imzalı SSO ile `:8020/dogum-gunleri` sayfasına şifresiz, doğrudan geçiş sağlar.

**Sınıf Excel & PDF İçe Aktarım ve Doğrulama (`scripts/sinif_bilgi_ice_aktar.py` — 2026-09-21):**
- `/home/ata/farabi/mudur/SINIF/` altındaki dosyaları işler (`9-LAR.xlsx`, `10-LAR.xlsx`, `11ler.xlsx`, `12ler.xlsx`, `10-A.xlsx`, `12-A.xlsx`, `9A.PDF`, `9B.PDF`).
- 101 aktif öğrencinin 99'unun doğum tarihi karşılaştırmalı olarak doğrulanıp kaydedildi.
- 10-A ve 12-A sınıflarının öğrenci telefonları (23 adet) ve veli telefonları (45 adet, `ogrenci_kisi_id` ile bağlı) aktarıldı.
- Tekrarlayan/mükerrer kayıt engelleme: İkinci kez çalıştırıldığında 0 ekleme yapar, veritabanında 0 mükerrer numara garantilenir.

**Yoklama SMS Modülü (2026-09-23 eklendi):**
- Sayfa: `/yoklama-sms` — bugün devamsız olan öğrencileri, eşleşen veli
  telefonlarını ve hazır mesaj şablonunu listeler. Kullanıcı gözden geçirip
  gönderir; **otomatik/zamanlanmış gönderim YOK** (kullanıcı kararı).
- **Gönderim için yeni kod yolu yazılmadı:** sayfa, seçili veli id'lerini mevcut
  `POST /gonder`'e post eder — `/durum/{id}`, `/kayitlar`, `/durdur`,
  `/tekrar-gonder` bu sayede bedavaya gelir.
- Devamsız tanımı (`yoklama_mantik.py`): **bugün en az N derste yok**,
  varsayılan `N=4`, sayfadan değiştirilebilir. 1. derse bakmak geç gelen
  öğrencinin velisine yanlış SMS gönderirdi.
- ⚠️ **Yoklaması alınmamış / tahtası ulaşılamaz sınıf listeye GİRMEZ**, ayrı bir
  uyarı kutusunda sebebiyle gösterilir. Panonun `yoklayici.py:126`'sı
  `alindi` olmayan her satıra boş isim dizisi yazdığı için "kimse yok değil" ile
  "yoklama hiç alınmadı" ayırt edilemez — bu ayrım yapılmazsa 12-A'nın
  2026-09-22'de yaşadığı gibi bir heartbeat kopmasında tüm sınıfın velisine
  "okula gelmedi" SMS'i giderdi.
- İzinli ders "yok" sayılmaz; gün içinde izinli görünen öğrenci varsayılan
  seçili gelmez. Velisi/telefonu bulunamayan öğrenci "Veli telefonu yoktur"
  etiketiyle listede KALIR, gönderimde pas geçilir (sessizce düşürülmez).
- İsim eşleştirme sınıf kapsamlıdır (aynı ad iki sınıfta olabilir). İsim başka
  bir sınıfta bulunursa SMS yine gönderilmez ama sebep satırda yazılır —
  2026-09-23'te canlı veride gerçekten bulundu (panoda 11-A, rehberde 11-B).
- Şablon `ayarlar` tablosunda (`yoklama_sms_sablonu`), `{isim}`/`{ogrenci_adi}`
  yer tutucularıyla. Varsayılan: "Sayın {isim}, öğrenciniz {ogrenci_adi} bugün
  **derslere katılmamıştır**. Bilginize."
  ⚠️ "okula gelmemiştir" DEĞİL — bilinçli: eşik kuralı kısmi devamsızlığı da
  kapsıyor (canlı örnek: 6 dersin 4'ünde yok, 2 derse girmiş), o öğrencinin
  velisine "okula gelmedi" demek yanlış bilgi olurdu.
- **Geçmiş tarihte gönderim KAPALI** (buton hiç basılmaz): mesaj "bugün" diyor,
  eski bir listeyle gönderilirse veliye yanlış gün bildirilirdi. Geçmiş tarih
  yalnızca inceleme için görüntülenir.
- **Veli ilişkisi (2026-09-23'te doğrulandı):** bir öğrencinin BİRDEN ÇOK velisi
  olabilir ve hepsine ayrı SMS gider (canlıda 21 öğrencinin 2 velisi var).
  Tersi tekil: bir veli SATIRI tek bir `ogrenci_kisi_id` taşır — kardeşler için
  aynı kişi iki ayrı satır olarak girilir, her çocuk için ayrı SMS alır. Rehberde
  "aynı veli" diye birleşik bir kavram yok. Mükerrer (öğrenci, telefon) çifti
  canlıda 0.

**Devamsızlık SMS Otomasyon Modülü (2026-09-24 ilk ders, 2026-10-04 öğleden sonra eklendi — `otomasyon.py`):**
- **Amaç:** Okul günleri (Pazartesi-Cuma) yoklama veritabanını kontrol ederek:
  1. Sabah 09:00'da 1. derse gelmeyen öğrencilerin anne ve babalarına otomatik SMS gönderir.
  2. Öğleden sonra 14:00'te öğleden sonraki derse (6. ders: 13:30 - 14:10) gelmeyen öğrencilerin anne ve babalarına otomatik SMS gönderir.
- **Güvenlik & Fail-Closed:** Yalnızca ilgili derste (1 veya 6) `durum == 'alindi'` olan sınıflar taranır. Tahtası kapalı veya yoklaması alınmamış sınıflar hariç tutulur. İzinli öğrenciler devamsız sayılmaz.
- **İdempotency:** `otomasyon_ilk_ders_son_tarih` ve `otomasyon_ogle_son_tarih` ayarları ile aynı gün mükerrer çalışmalar kesin olarak engellenir. İki servis birbirinden bağımsızdır (sabahın çalışması öğleyi engellemez). İstisna: hiçbir `send_sms` denenmediyse (proxy/modem bağlantısı hiç kurulamadı, satırlar "BAĞLANTI HATASI" önekli) son tarih yazılmaz ve pencere içinde yeniden denenir. Koşulu "hiç başarılı yok"a genişletme — mükerrer SMS riski (DECISIONS.md 2026-09-28).
- **Arayüz (`/otomasyon`):**
  - Üstte sekmeler: "☀️ Sabah 09:00 Servisi (1. Ders)" ve "🌤️ Öğleden Sonra 14:00 Servisi (6. Ders)".
  - Her iki servis için bağımsız açma/kapatma şalteri (`otomasyon_ilk_ders_aktif`, `otomasyon_ogle_aktif`, varsayılan '0' KAPALI).
  - Ayrı varsayılan şablon düzenleyicileri:
    - Sabah: "Sayın {isim}, öğrenciniz {ogrenci_adi} sabah ilk saate gelmemiştir. Bilginize."
    - Öğle: "Sayın {isim}, öğrenciniz {ogrenci_adi} öğleden sonra derslere gelmemiştir. Bilginize."
  - Yapay Zeka ile Mesaj Düzenleme butonu (`/api/mesaj-duzelt`).
  - Bugünkü ders canlı simülasyonu / test önizlemesi (öğle sekmesinde "Tüm Gün Yok" vs "Öğleden Sonra Gelmedi / Kaçtı" rozeti gösterilir) ve manuel gönderim butonu.
- **Dashboard Entegrasyonu:**
  - Tahtayoklama panosunda menüye "SMS Otomasyonu" linki (`/otomasyon-git`) eklendi; HMAC-imzalı SSO ile doğrudan `:8020/otomasyon` sayfasına geçiş sağlar.
- **Arka Plan Servisi:** FastAPI `lifespan` döngüsünde 30 saniyede bir saati kontrol eden asenkron zamanlayıcı görevi (`otomasyon.otomasyon_arkaplan_dongusu`). Tetik pencereleri İstanbul saatiyle 09:00–09:10 (1. ders) ve 14:00–14:10 (6. ders); servis bu aralıklarda kapalıysa o gün çalışmaz. Görev uvicorn sürecinin içinde koşar — birden çok worker ile başlatılırsa her biri kendi döngüsünü açar, mükerrer gönderimi yalnızca `…_son_tarih` ayarları engeller.
- ⚠️ **Yoklama SMS'ten farklı gönderim yolu:** otomasyon `POST /gonder`'i KULLANMAZ; `otomasyon_calistir` doğrudan `sms_gonderici`'yi kendi thread'inde çağırıp satırları kendisi `gonderimler`'e yazar (`oto1_...` sabah, `oto6_...` öğle). Gönderim mantığında (normalizasyon, UCS2/7-bit, kayıt formatı) yapılan bir değişiklik iki yolda da kontrol edilmeli.

**Doğum günü `sms_otomatik` şalteri yalnızca ayar olarak var:** `/dogum-gunleri/ayarlar` `sms_otomatik` ve `dogum_sms_sablonu`'nu `ayarlar` tablosuna yazar, ama (2026-09-28 itibarıyla) bu değeri okuyup doğum günü SMS'i gönderen bir döngü/görev YOK — `lifespan`'daki tek arka plan görevi ilk ders otomasyonu. Şalteri açmak hiçbir şey göndermez.

> ⚠️ **"Kasıtlı olarak bağımsız" kuralının TEK İSTİSNASI burasıdır.**
> `yoklama_kaynak.py`, yoklama panosunun veritabanını
> (`tahtayoklama/dashboard/veri/yoklama_pano.db`) `mode=ro` ile **doğrudan**
> okur. Alternatif (panoya HMAC imzalı `/api/devamsiz` endpoint'i) kullanıcıya
> sunuldu ve doğrudan okuma seçildi — gerekçe kök `DECISIONS.md` 2026-09-23
> kaydında. Sapmanın yarıçapı bilerek tek dosyaya hapsedildi: panonun şemasını
> bilen tek modül `yoklama_kaynak.py`, HTTP+HMAC'e geçilmek istenirse yalnızca
> `gunun_satirlari`'nın gövdesi değişir. **Panonun `yoklama_onbellek` şeması
> değişirse burası sessizce kırılır** — `test_yoklama_mantik.py`'deki
> `_PANO_SEMA` sabiti o şemanın kopyasıdır, birlikte güncellenmeli.

**Gönderim & Kişiselleştirme & Yapay Zeka:**
- `gonder.html` 2 panelli arayüze kavuştu: Sağ panelde Sınıf+Tür filtresi ile
  kişiler checkbox'lı liste olarak gelir ("Tümünü Seç" + tek tek seçim serbest),
  işaretli kişiler anında sol paneldeki alıcı listesine eklenir. Sol paneldeki
  serbest textarea / CSV yükleme paralel çalışır, gönderirken panelden yapılan
  seçim önceliklidir.
- `kisisellestir`: `{isim}` (alıcı adı) ve `{ogrenci_adi}` (veli için bağlı
  öğrencinin adı, öğrenci için kendi adı) yer tutucularını destekler.
- Ollama entegrasyonu: Farabi'deki `qwen2.5:14b` (`192.168.23.252:11434`) modeline
  bağlanan `POST /api/mesaj-duzelt` endpoint'i ve mesaj kutusu yanındaki "✨ Düzelt (AI)"
  butonu — taslak metni resmi Türkçe okul SMS'ine çevirir, `{isim}` ve
  `{ogrenci_adi}` yer tutucularını olduğu gibi korur.

**Modem köprüsü 2026-09-20'de değişti:** `netsh portproxy` (ham TCP
yönlendirme, HTTP framing'i bozuyordu — kronik `BadStatusLine`, aylarca
çözülmemişti) yerine Müdür PC'de gerçek bir HTTP forward proxy
(`WifiHttpProxy.exe`, Wi-Fi arayüzüne bound) kullanılıyor artık. Kök
neden ve çözüm detayı `DECISIONS.md` 2026-09-20 kaydında; ayrıntı için
aşağıdaki "Mimari" bölümüne bak. `sms_gonderici._baglan` yine de her
denemede tamamen taze bir bağlantı kurup gerçek bir API çağrısıyla
doğruluyor (8 deneme) — artık asıl kronik hatayı tolere etmek için değil,
genel bir güvenlik payı olarak.

## Komutlar

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt
venv/bin/python -m pytest -q                    # tüm testler (düz dosyalar: test_*.py, tests/ dizini yok) — 2026-10-04: 130 geçti
venv/bin/python -m pytest test_db.py -q         # tek dosya
venv/bin/python -m pytest test_db.py::test_semayi_kur_ve_gonderim_kaydet -q  # tek test

venv/bin/python scripts/sifre_belirle.py        # ortak giriş şifresini belirler, config/gizli.json'a yazar (ilk kurulumda zorunlu)

venv/bin/uvicorn app:app --reload --port 8020   # geliştirmede elle (DİKKAT: lifespan otomasyon döngüsünü de başlatır)

# Bir kerelik veri aktarım script'leri — --kuru-calistir destekleyenlerde önce onu çalıştır
venv/bin/python scripts/dogum_ice_aktar.py --kuru-calistir
```

Üretimde `farabi-smssistemi.service` adıyla systemd altında, port `8020`'de
çalışıyor (`sudo systemctl status/restart farabi-smssistemi`, log:
`journalctl -u farabi-smssistemi.service`). Bu dizin canlı üretim — kod
değişikliği restart'a kadar yayına girmez.

Lint: kök `/home/ata/farabi/CLAUDE.md`'deki Ruff kuralı geçerli
(`../.venv-tools/bin/ruff check .` ya da yalnızca dokunduğun dosya);
2026-10-01 taban çizgisi `smssistemi` için 40 bulgu — farkı oku.
⚠️ `test_otomasyon*.py` gitignore'lu `config/modem.json`'a bağımlı;
worktree'de koşulursa 4 test düşer (ana kopyada koş ya da `config/`'e geçici
symlink). Aynı
temkinli prosedür (önce check, F8xx öncelik, büyük ölçekli otomatik
düzeltme yok) burada da uygulanır.

## Mimari (özet — ayrıntı için spec dosyası)

```
Farabi :8020 (FastAPI)  --HTTP proxy (8080)-->  Müdür PC WifiHttpProxy.exe  -->  Huawei modem :80 (192.168.8.1)
  auth.py / db.py / sms_gonderici.py            (Wi-Fi arayüzüne bound,          (SIM kartlı SMS gateway)
                                                  gerçek HTTP/CONNECT relay)
```

**2026-09-20'de değişti** (bkz. `DECISIONS.md` aynı tarihli kayıt —
ayrıntılı teşhis, denenen/reddedilen alternatifler orada): önceki
mekanizma `netsh interface portproxy` idi (ham TCP seviyesinde
`192.168.23.243:18080` → `192.168.8.1:80` yönlendirmesi) ama bu, HTTP
mesaj çerçevelemesini korumadığı için kronik `BadStatusLine`/
`ConnectionReset` hatalarına yol açıyordu — köprünün kendisi kırılgandı,
uygulama kodundan düzeltilemezdi. Çözüm: Müdür PC'de gerçek bir HTTP
forward proxy'ye (`WifiHttpProxy.exe`) geçildi; Farabi artık modeme
kendi GERÇEK IP'siyle (`192.168.8.1`, `config/modem.json`'daki
`modem_ip`) doğrudan konuşuyor, proxy yalnızca taşımayı yapıyor —
modemin kendi Host-eşleşme kontrolü de böylece doğal şekilde geçiyor.
`sms_gonderici.py::_baglanti_url` artık `modem_ip`'yi hedefler;
proxy'nin adresi/kimlik bilgileri ayrı alanlarda (`proxy_host`,
`proxy_port`, `proxy_user`, `proxy_pass`). Eski `host`/`port` alanları
(köprü adresiydi) `config/modem.json`'da durabilir ama artık okunmuyor.

⚠️ **WifiHttpProxy.exe, Müdür PC'de systemd/Windows servisi DEĞİL** —
kullanıcının elle çalıştırdığı bir batch script + .exe. Müdür PC yeniden
başlatılırsa otomatik ayağa kalkmayabilir; kalıcı hale getirme (görev
zamanlayıcı/başlangıç klasörü) henüz yapılmadı. Ayrıca bu script'in
kaynağında (kullanıcının ayrı bir amaçla — okulun filtrelenmiş
Ethernet'ini Wi-Fi üzerinden atlatmak için — yazdırdığı) bir TTL=65
ayarı (carrier-tethering-tespitini atlatmaya yönelik) vardı; bu ayar
**bilinçli olarak devreye alınmadı**, yalnızca HTTP proxy kısmı
kullanılıyor.

- `db.py` — SQLite (`veri/smssistemi.db`, gitignore'lu), tek durum kaynağı.
  `gonderimler` (her SMS satırı, `gonderim_id` ile toplu gönderim gruplanır)
  ve `oturumlar` (cookie token'ları) tabloları. `baglanti()` her çağrıda yeni
  bağlantı açar (WAL modu) — testler `monkeypatch.setattr(db, "DB_YOLU", ...)`
  ile izole edilir.
- `auth.py` — tek ortak şifre (kullanıcı bazlı hesap yok). `scrypt` ile
  hash'lenmiş şifre `config/gizli.json`'da (gitignore'lu, yok
  `scripts/sifre_belirle.py` ile üretilir). Oturum cookie'si DB'deki
  `oturumlar` tablosuna karşılık gelir, JWT/imzalı cookie değil.
- `gonderim.py` — saf fonksiyonlar (ağ/DB çağrısı yok), Windows'taki masaüstü
  `app.py`'sinin telefon normalizasyon/doğrulama/CSV mantığının web'e taşınmış
  hâli. `05XXXXXXXXX` ve `+905XXXXXXXXX` dışındaki formatlar geçersiz sayılır.
- `sms_gonderici.py` — `huawei_lte_api` senkron/bloklayan bir kütüphane;
  `toplu_gonder` bu yüzden `durdur_bayragi` (Event) ile iptal edilebilir bir
  döngü olarak yazılmış; `app.py::_gonderim_calistir` bunu bir
  `threading.Thread` (daemon) içinde çalıştırıyor, `/durum/{gonderim_id}`
  sayfası `/api/durum/{gonderim_id}`'yi polluyor. Türkçe karakter içeren
  mesajlar UCS2, ASCII mesajlar 7-bit modunda gönderilir (`gonderim.is_ascii`).
  `_proxy_session`, `requests.Session`'ı özelleştiren `_TekSeferlikSession`
  kullanır — WifiHttpProxy her TCP bağlantısında yalnızca tek istek işleyip
  soketi kapattığı için, varsayılan bağlantı havuzu (connection pooling)
  ikinci istekte `ConnectionReset`/`ReadTimeout` veriyordu; her istekten
  sonra adapter havuzu kapatılıp sonraki isteğin taze bağlantı açması
  zorlanıyor (bkz. yukarıdaki "Mimari" ve `DECISIONS.md` 2026-09-20).
- `app.py` — route grupları: giriş/SSO (`/giris`, `/sso`, `/cikis`),
  gönderim (`/`, `/gonder`, `/durum/{id}`, `/api/durum/{id}`,
  `/durdur/{id}`, `/tekrar-gonder/{id}`, `/kayitlar`, `/api/mesaj-duzelt`),
  rehber (`/rehber` + `/rehber/kisi|sinif/...` CRUD +
  `/rehber/yukle` + `/api/rehber/kisiler`, JS panelinin kişi listesini
  buradan çeker), `/yoklama-sms*`, `/otomasyon*` + `/api/otomasyon/durum`,
  `/dogum-gunleri*`. İş mantığı route'ta değil, saf modüllerde:
  `yoklama_mantik.py`, `otomasyon.py`, `dogum_mantik.py`, `gonderim.py` —
  testler de bu ayrımı izler (`test_<modül>.py` saf mantık,
  `test_<modül>_app.py` route). Her route kendi `db.baglanti()`'sini açıp
  `finally`'de kapatır — bağlantı paylaşılmaz.
- `config/gizli.json`, `config/modem.json`, `config/sso.json`, `veri/` —
  hepsi gitignore'lu, asla okuma/commit etme (kök CLAUDE.md'nin "Okuma"
  kısıtına ek).
- `scripts/roster_ice_aktar.py` — bir kereye mahsus, `tahtayoklama/data/
  roster/*.json`'daki öğrenci listesini rehbere (`tur='ogrenci'`,
  telefon boş) aktarır; isim+sınıf zaten varsa atlar, tekrar çalıştırmak
  güvenli.

## Atos SMS aracı API'si (`arac_api.py`, 2026-10-05)

Open WebUI "SMS ve Hatırlatma" aracının (`openwebui/farabi_sms_araci.py`,
yalnızca İdare) makine API'si; kimlik `X-Sms-Arac-Key` (`config/arac.json`
`anahtar`, gitignore'lu — yönetici adları/telefonları da orada, koda yazılmaz).

| Uç | İş |
|---|---|
| `POST /api/arac/hatirlatma` | yönetime zamanlı hatırlatma, ONAYSIZ; saat yoksa 10:00 TR, not ≤120 kr |
| `GET /api/arac/hatirlatmalar`, `POST /api/arac/hatirlatma/{id}/iptal` | listele / iptal |
| `POST /api/arac/acil` | yönetime anında SMS |
| `POST /api/arac/veli-taslak` → `POST /api/arac/veli-gonder` | veli SMS'i iki adımlı: taslak (alıcı sayısı + önizleme, 30 dk geçerli) → açık onay → gönderim |
| `POST /api/arac/ogrenci-taslak` → `POST /api/arac/ogrenci-gonder` | aynı akış, alıcı = sınıfın telefonlu öğrencileri (2026-10-07, `kazanimtest/` test linki için). Taslaklar aynı `veli_taslaklari` tablosunda `tur` kolonuyla ayrılır; veli taslağı öğrenci ucundan gönderilemez (ve tersi). `ogrenci-taslak`a `test_telefon` verilirse sınıf yerine yalnızca o numaraya gider (deneme) |
| `POST /api/arac/kisisel-taslak` → `POST /api/arac/kisisel-gonder` | kişiye özel SMS (2026-10-08, kazanım raporu): gövde `{ogeler:[{okul_no, metin_sablon}], test_telefon?}`; öğrenci YALNIZCA `kisiler.okul_no` ile bulunur (sınıf kullanılmaz), alıcı = öğrenci (telefonu varsa) + velileri, öğe içinde tekil; `{ad}` sunucuda doldurulur (`str.replace`), her metin ≤300. Yanıtta `bulunamayan`/`alicisiz` okul_no listeleri. `test_telefon` varsa yalnızca İLK bulunan öğe, yalnızca o numaraya. Ayrı `kisisel_taslaklari` tablosu (veli/öğrenci taslaklarıyla çapraz kullanılamaz); gönderimde alıcılar yeniden çözülür, tek `gonder` çağrısı, 30 dk geçerli |

Gönderim mevcut modem göndericisiyle (`sms_gonderici.toplu_gonder`), sonuç
`gonderimler` tablosuna (`/kayitlar`'da görünür). Testlerdeki telefonlar
sahte (`0555…`) — gerçek numara teste yazılmaz (public repo).

## Test deseni

Düz `test_*.py` dosyaları proje kökünde (ayrı `tests/` dizini yok). DB
testleri gerçek SQLite dosyası kullanır ama `tmp_path`/`monkeypatch` ile her
testte izole edilir — `db.py`'ye yeni bir sorgu eklerken bu deseni koru.
