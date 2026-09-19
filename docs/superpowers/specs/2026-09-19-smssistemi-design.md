# SMS Sistemi — Farabi Bağımsız Web Modülü

2026-09-19. Müdür PC masaüstündeki `sms sistemi` (Tkinter, Huawei HiLink
modem üzerinden toplu SMS) uygulamasının işlevini, Farabi sunucusunda
tahtayoklama/dashboard'dan bağımsız yeni bir web projesi (`smssistemi`)
olarak taşır. Dashboard sadece bu projeye bir nav linki verir.

## Amaç

Kısa vadede masaüstü uygulamasının web eşdeğeri: toplu/kişiselleştirilmiş
SMS gönderimi, tarayıcıdan, Farabi'de barındırılan. Orta vadede
(`fikirler.md` #1, bu spec'in kapsamı DIŞINDA) yoklama sisteminden
otomatik "öğrenci gelmedi" tetikleyicisiyle veliye SMS atacak temel altyapı.

## Kapsam

**Var (bu spec):**
- Numara girişi (manuel `isim,telefon` veya CSV yükleme), doğrulama
  (`05XXXXXXXXX` / `+905XXXXXXXXX`), geçersizlerin ayrı gösterimi.
- `{isim}` kişiselleştirme, gönderimler arası bekleme süresi, gönderimi
  durdurma, başarısızları tekrar gönderme.
- Gönderim kaydı (SQLite) — masaüstündeki aylık düz metin log yerine.
- Ortak paylaşılan şifre + cookie oturumu (dashboard'un `auth.py`
  deseniyle aynı desen — kod paylaşımı yok, bağımsız kopya).
- Kendi systemd servisi, kendi portu (8020), kendi venv'i.
- Dashboard `pano.html` nav'ına tek bir link.

**Yok (ertelendi, ayrı karar turu gerekir):**
- Yoklama sisteminden otomatik tetikleyici (webhook/DB polling).
- İki yönlü SMS / veli onayı (gelen kutusu okuma).
- WhatsApp/Telegram yedek kanal.
- Merkezi öğrenci/veli veritabanı (PostgreSQL `farabi` DB'ye taşıma).
- AI destekli mesaj taslağı (qwen2.5:14b entegrasyonu).
- Teslimat durumu / kotalama panosu.

## Kullanıcı kararları (2026-09-19)

- **Bağımsızlık:** `smssistemi`, `tahtayoklama/dashboard` koduna hiç
  bağımlı değil — ayrı klasör, ayrı venv, ayrı systemd servisi, ayrı DB.
  Dashboard'la tek bağlantı noktası: nav'daki link.
- **Ağ erişimi:** Farabi (`192.168.23.252`), modeme (`192.168.8.1`,
  Müdür PC'nin ayrı Wi-Fi ağı) doğrudan ulaşamıyor — 2026-09-19'da
  `curl`/`ping` ile doğrulandı (bağlantı reddedildi / %100 kayıp).
  Çözüm: Müdür PC'de **uygulama kodu değil**, işletim sistemi seviyesinde
  `netsh interface portproxy` ile TCP yönlendirmesi — Müdür PC'nin LAN
  IP'sinde (`192.168.23.243:18080`) dinleyip modemin `192.168.8.1:80`
  portuna yönlendirir. Sadece Farabi'nin IP'sinden (`192.168.23.252`)
  erişime izin veren dar bir firewall kuralıyla korunur.
- **Portlar:** Müdür PC portproxy dinleme portu `18080`. `smssistemi`
  web servisi Farabi'de port `8020`.
- **Test:** Uçtan uca doğrulama için kullanıcının kendi numarasına
  (`5059399303`) gerçek bir SMS gönderilecek.

## Mimari

```
Farabi (192.168.23.252)                Müdür PC (192.168.23.243 / 192.168.8.121)
┌─────────────────────────┐            ┌──────────────────────────────┐
│ smssistemi (FastAPI)     │  TCP 18080 │ netsh portproxy               │
│ :8020                    │───────────▶│ 192.168.23.243:18080          │
│  - auth.py (cookie)      │            │   → 192.168.8.1:80            │
│  - db.py (SQLite)        │            │ (uygulama kodu YOK, sadece    │
│  - sms_gonderici.py      │            │  OS yönlendirme + firewall    │
│    (huawei_lte_api,      │            │  kuralı: remoteip=            │
│    base_url=Müdür PC:18080)│          │  192.168.23.252)               │
│  - app.py (router+UI)    │            └──────────────────────────────┘
└─────────────────────────┘                         │
         ▲                                            ▼
         │ nav linki                          Huawei modem (192.168.8.1)
tahtayoklama/dashboard                         (SIM kartlı SMS gateway)
(:8010, pano.html)
```

`smssistemi`, masaüstü uygulamasındaki (`C:\Users\exa\Desktop\sms
sistemi\app.py`) `normalize_phone` / `is_valid_phone` / gönderim akışı
mantığını referans alır; Tkinter yerine FastAPI + Jinja2 (dashboard'un
"hafif tut" kuralıyla aynı — SPA/fetch yok, form-POST).

## Bileşenler

**Müdür PC (sadece network altyapısı, kod yok):**
- `netsh interface portproxy add v4tov4 listenaddress=192.168.23.243
  listenport=18080 connectaddress=192.168.8.1 connectport=80`
- Firewall kuralı: TCP 18080, `remoteip=192.168.23.252` (sadece Farabi).

**Farabi `/home/ata/farabi/smssistemi/`:**
- `app.py` — FastAPI giriş noktası, router'lar, `/giris` `/cikis`.
- `auth.py` — ortak şifre + cookie oturum (dashboard `auth.py` deseninin
  bağımsız kopyası: `scrypt` hash, `config/gizli.json`).
- `db.py` — SQLite (`veri/smssistemi.db`): `gonderimler`, `oturumlar`
  tabloları.
- `sms_gonderici.py` — `huawei_lte_api` sarmalayıcı; `Connection` URL'i
  `http://<user>:<pass>@192.168.23.243:18080/` (modem kimlik bilgileri
  Müdür PC'deki `sifre.json`'dan bire bir taşınır, Farabi'de kendi
  `config/modem.json`'unda tutulur — bağımsız kopya).
- `gonderim.py` — numara ayrıştırma/doğrulama (`app.py`'den taşınan
  `normalize_phone`/`is_valid_phone` mantığı), arka plan gönderim işi
  (Tkinter thread yerine FastAPI `BackgroundTasks` + `asyncio`).
- `templates/` — `giris.html`, `gonder.html`, `kayitlar.html`
  (dashboard'un `taban.html` desenine benzer, ayrı kopya).
- `requirements.txt`, `venv/`.
- systemd: `farabi-smssistemi.service`, `uvicorn app:app --host 0.0.0.0
  --port 8020`.

**Dashboard (`tahtayoklama/dashboard`):**
- `pano.html` nav'ına tek satır link: `http://farabi.local:8020/`.
  Başka hiçbir değişiklik yok — router/DB/kod paylaşımı yok.

## Veri modeli (SQLite, `smssistemi/db.py`)

```sql
CREATE TABLE gonderimler (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    isim          TEXT,
    telefon       TEXT NOT NULL,
    mesaj         TEXT NOT NULL,
    durum         TEXT NOT NULL,   -- 'gonderildi' | 'hata'
    hata_metni    TEXT,
    gonderim_id   TEXT NOT NULL,   -- aynı toplu gönderimi gruplamak için
    zaman         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE oturumlar (
    token             TEXT PRIMARY KEY,
    olusturma_zamani  TEXT NOT NULL DEFAULT (datetime('now')),
    son_gorulme       TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## Güvenlik

- Modem kimlik bilgileri Farabi'de `config/modem.json` içinde saklanır
  (dashboard'un `config/gizli.json` dosyasının izin/gitignore
  muamelesiyle aynı — düz metin şifre, paylaşılmaz/commitlenmez).
- Web arayüzü: ortak şifre + `httponly` cookie oturum (dashboard
  `auth.py` deseniyle birebir aynı, bağımsız kopya).
- Müdür PC portproxy: sadece `192.168.23.252` (Farabi) kaynak IP'sine
  izin veren firewall kuralı — LAN'daki başka bir cihaz bu portu
  kullanarak modeme/SMS'e erişemez.

## Test planı

1. Müdür PC'de portproxy + firewall kuralı kurulduktan sonra Farabi'den
   `curl http://192.168.23.243:18080/` ile modemin web arayüzüne
   (login sayfası) ulaşılabildiği doğrulanır.
2. `smssistemi` servisi başlatılır, dashboard'daki linkten erişilip
   ortak şifreyle giriş yapılır.
3. Tek kişilik gerçek SMS testi: `5059399303` numarasına kısa bir test
   mesajı gönderilir, `gonderimler` tablosunda `gonderildi` durumu ve
   arayüzde sonuç görülür.
