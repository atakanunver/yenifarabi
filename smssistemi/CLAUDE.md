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

modem köprüsü (Müdür PC `netsh portproxy`) zaman zaman kararsız
davranıyor (`sms_gonderici._baglan` bunu 8 denemelik, gerçek API
çağrısıyla doğrulanan bir retry ile tolere ediyor) — kök neden kesin
teşhis edilmedi, tekrarlarsa önce Müdür PC'nin modeme olan Wi-Fi
sinyaline bakılmalı (bkz. `DECISIONS.md`).

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
Farabi :8020 (FastAPI)  --TCP 18080-->  Müdür PC netsh portproxy  -->  Huawei modem :80
  auth.py / db.py / sms_gonderici.py       (uygulama kodu yok,          (SIM kartlı SMS gateway)
                                             sadece OS yönlendirme)
```

Farabi, modeme (`192.168.8.1`) doğrudan ulaşamıyor — Müdür PC'nin ayrı Wi-Fi
ağında. Çözüm uygulama kodunda DEĞİL: Müdür PC'de OS seviyesinde
`netsh interface portproxy` ile `192.168.23.243:18080` → `192.168.8.1:80`
yönlendirmesi, yalnızca Farabi'nin IP'sinden erişime izin veren bir firewall
kuralıyla. `sms_gonderici.py::_baglanti_url` bu yüzden `config/modem.json`'daki
`host`/`port` olarak Müdür PC'nin adresini kullanır, modemin kendi IP'sini
değil.

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
