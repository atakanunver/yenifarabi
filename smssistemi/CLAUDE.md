# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Ne bu proje

Müdür PC masaüstündeki Tkinter tabanlı `sms sistemi` (Huawei HiLink modem
üzerinden toplu SMS) uygulamasının web eşdeğeri. Farabi sunucusunda
(`farabi.local`) bağımsız bir FastAPI servisi olarak çalışacak — okul
idaresinin öğrenci velilerine toplu/kişiselleştirilmiş SMS göndermesini
sağlar.

Tasarım kararları ve mimari gerekçe: `../docs/superpowers/specs/2026-09-19-smssistemi-design.md`
(bu dosyayı önce oku — kod yorumlarının çoğu ona işaret ediyor).

**Kasıtlı olarak bağımsız:** `tahtayoklama/dashboard` ile hiçbir kod paylaşımı
yok. `auth.py`/`db.py` dashboard'daki aynı isimli dosyaların desenini takip
eder ama satır satır bağımsız kopyadır — biri değişince diğeri otomatik
güncellenmez, bu bilinçli bir karar (yukarıdaki spec, "Kullanıcı kararları").
Dashboard'la tek bağlantı noktası `pano.html`'deki bir nav linki.

## Durum (2026-09-19)

Üretimde çalışıyor. `farabi-smssistemi.service` aktif (port 8020),
`app.py` + `templates/`/`static/` yazıldı, gerçek bir SMS ucu ucuna
doğrulandı (bkz. kök `DECISIONS.md`). Dashboard'dan tek tıkla giriş
(SSO) çalışıyor: `/sms-git` (dashboard) → `/sso?t=..&s=..` (smssistemi),
kısa ömürlü (30sn) HMAC-imzalı token — paylaşılan anahtar
`config/sso.json` (~dashboard'daki `config/sms_sso.json` eşi),
gitignore'lu, kod/DB paylaşımı yok.

**Rehber (telefon defteri) eklendi:** `siniflar` (bu yıl için 9-A..12-B,
ekle/sil yapılabilir) + `kisiler` (ad_soyad, telefon [boş olabilir],
sinif_id, tur='ogrenci'|'veli', ogrenci_kisi_id [nullable FK → kisiler.id,
yalnızca veliler için öğrenci bağlantısı]) tabloları, `/rehber` sayfası
(CRUD + elle öğrenci seçici dropdown + CSV/Excel toplu yükleme — veli
yüklemesinde "Öğrenci Adı" sütunuyla aynı sınıftaki öğrenci otomatik eşleşir,
eşleşmeyenler yükleme özetinde "eşleşmedi: N" olarak gösterilir ve tablodan
elle bağlanabilir).

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
venv/bin/python -m pytest -q                    # tüm testler (düz dosyalar: test_*.py, tests/ dizini yok)
venv/bin/python -m pytest test_db.py -q         # tek dosya
venv/bin/python -m pytest test_db.py::test_semayi_kur_ve_gonderim_kaydet -q  # tek test

venv/bin/python scripts/sifre_belirle.py        # ortak giriş şifresini belirler, config/gizli.json'a yazar (ilk kurulumda zorunlu)

uvicorn app:app --reload --port 8020            # geliştirmede elle çalıştır (app.py yazıldıktan sonra)
```

Üretimde `farabi-smssistemi.service` adıyla systemd altında, port `8020`'de
çalışıyor (`sudo systemctl status/restart farabi-smssistemi`).

Lint: kök `/home/ata/farabi/CLAUDE.md`'deki Ruff kuralı geçerli
(`.venv-tools/bin/ruff check ... smssistemi`) — o listede `smssistemi` henüz
yok, eklenmesi gerekebilir; aynı temkinli prosedür (önce check, F8xx öncelik,
büyük ölçekli otomatik düzeltme yok) burada da uygulanır.

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
- `app.py` — route'lar üç grup: giriş/SSO (`/giris`, `/sso`, `/cikis`),
  gönderim (`/`, `/gonder`, `/durum/{id}`, `/api/durum/{id}`,
  `/durdur/{id}`, `/tekrar-gonder/{id}`, `/kayitlar`, `/api/mesaj-duzelt`)
  ve rehber (`/rehber` + `/rehber/kisi|sinif/...` CRUD +
  `/rehber/yukle` + `/api/rehber/kisiler`, JS panelinin kişi listesini
  buradan çeker). Her route kendi `db.baglanti()`'sini açıp `finally`'de
  kapatır — bağlantı paylaşılmaz.
- `config/gizli.json`, `config/modem.json`, `config/sso.json`, `veri/` —
  hepsi gitignore'lu, asla okuma/commit etme (kök CLAUDE.md'nin "Okuma"
  kısıtına ek).
- `scripts/roster_ice_aktar.py` — bir kereye mahsus, `tahtayoklama/data/
  roster/*.json`'daki öğrenci listesini rehbere (`tur='ogrenci'`,
  telefon boş) aktarır; isim+sınıf zaten varsa atlar, tekrar çalıştırmak
  güvenli.

## Test deseni

Düz `test_*.py` dosyaları proje kökünde (ayrı `tests/` dizini yok). DB
testleri gerçek SQLite dosyası kullanır ama `tmp_path`/`monkeypatch` ile her
testte izole edilir — `db.py`'ye yeni bir sorgu eklerken bu deseni koru.
