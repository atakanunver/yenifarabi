# tahtayoklama

Sınıf akıllı tahtalarında dokunmatik yoklama arayüzü + merkezi web panosu ("Yoklama ve Yönetim Paneli").
**Farabi'den TAMAMEN BAĞIMSIZ** (2026-08-18 kullanıcı kararı): Farabi `actions/` registry'sine girmez,
`client/`'a bağlı değildir. Farabi'nin sesli yoklaması bu sistemden habersizdir; ikisi paralel iki yoldur.
Bu dosya "şu an ne doğru" referansıdır; tarihli anlatılar ve gerekçeler kök `DECISIONS.md`'de.

## 1. Büyük resim

Tahta tarafında üç ayrı süreç, sunucuda iki erişim yolu var:

- **`yoklama.py`** (PyQt6 GUI): ağdan izole, tek durum kaynağı tahtanın kendi diskindeki JSON dosyaları (§3).
- **`tahta_istemci.py`** (ayrı süreç, §3.1): tahtadan sunucuya HTTP (`/api/v1/tahta/*`): kayıt gönderir, nabız yollar, yapılandırma (roster, zil, ders programı, kazanım) çeker, duyuru alır.
- **`announcement_agent.py`** (ayrı PyQt6 süreç): duyuru penceresi/sesi.
- **Sunucu → tahta SSH** (`dashboard/ssh_istemci.py`, `yoklayici.py`): polling, uzaktan eylemler, roster senkronu. Nabzı taze (≤5 dk) tahta kısmi turda SSH ile taranmaz; istemci kurulu olmayan tahta tamamen SSH ile taranır.
- **`dashboard/`**: tek FastAPI uygulaması; yoklama panosu + uzaktan yönetim + sınıf/roster yönetimi + duyurular + sistem durumu. SQLite `veri/yoklama_pano.db`.

**Teknoloji (bilinçli):** FastAPI + Jinja2 + vanilla JS (build yok, npm yok) + SQLite (WAL) + `asyncio.create_subprocess_exec` ile doğrudan `ssh` (paramiko/APScheduler yok). "Docker yok, hafif tut."

## 2. Dizin yapısı

```
tahtayoklama/
├── yoklama.py            — tahtada çalışan PyQt6 GUI
├── tahta_istemci.py      — tahta istemcisi (yalnız stdlib, §3.1)
├── announcement_agent.py — duyuru penceresi
├── pdf_disari_aktar.py   — e-Okul PDF → roster JSON (eski, tek seferlik)
├── test_yoklama.py       — yoklama.py testleri (pytest, ayrı dev venv)
├── data/                 — DEV kopyası; tahtalarda ~ogretmen/tahtayoklama/data/
│   ├── roster/<sinif>.json       — {"sinif", "ogrenciler": [{"no","ad_soyad","cinsiyet"}]}
│   ├── kayitlar/<tarih>_<sinif>_ders<no>.json — yoklama kaydı (yalnız tahtalarda; burada gitignore'lu)
│   ├── zil.json, ders_programi.json — `okul_ana` yayını üretir (kök CLAUDE.md); tahtalara `config_dagit.sh`/istemci dağıtır
└── dashboard/            — merkezi web panosu (§4)
```

## Komutlar

```bash
cd tahtayoklama/dashboard
venv/bin/uvicorn app:app --reload --port 8099          # elle geliştirme; DİKKAT: lifespan polling'i de başlatır (canlıyla çift polling)
venv/bin/python -m unittest discover -p 'test_*.py'    # tüm testler — pytest DEĞİL, venv'de pytest yok
venv/bin/python -m unittest test_uzaktan_ekran -v      # tek dosya (modül adı, .py YOK; dashboard/ dizininden)
venv/bin/python -m unittest test_uzaktan_ekran.TestUzaktanEkran.test_route_gecersiz_tahta   # tek test
venv/bin/python scripts/sifre_belirle.py               # ortak pano şifresi → config/gizli.json
sudo systemctl restart farabi-yoklama-dashboard.service   # yalnızca ders saatleri DIŞINDA (§10)
```

Yeni dashboard testi var olan `unittest.TestCase` desenini sürdürür. `tahtayoklama/test_yoklama.py` (tahta GUI) **pytest**'tir ve `tahtayoklama/venv`'de pytest yok; PyQt6+pytest kurulu ayrı dev venv'de:
`QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest tahtayoklama/test_yoklama.py -q`.

## 3. `yoklama.py` — tahta deployment gerçeği

- **Python yolu tahtadan tahtaya farklı (2026-10-01 doğrulandı).** 9-A dışında kendi venv'i: `/home/ogretmen/tahtayoklama/venv/bin/python`. Yalnız **9-A** Farabi client venv'ini paylaşır (`/home/ogretmen/farabi/repo/client/venv/bin/python`). Uzaktan başlatma yolu sabit kodlamaz, adayları dener (`uzaktan_yonetim._PYTHON_ADAYLARI`, DB `tahtalar.python_yolu`). `requirements.txt`: `PyQt6`, `pdfplumber`.
- **Autostart DEĞİL:** `~/Masaüstü/Yoklama.desktop` ile öğretmen elle açar.
- **Ağ I/O yok**, yalnız tek-örnek koruması için yerel Unix soketi (`QLocalServer`/`QLocalSocket`): ikinci pencere açılmaz, ilk örnek öne gelir.
- **Kayıt tahta kimliğine değil, o an seçili sınıfa göre isimlendirilir.** Hiçbir kod "tahta X = sınıf Y" varsaymamalı; kayıt içindeki `sinif` alanı esas.
- **Otomatik/sessiz kayıt yolu SİLİNDİ (2026-09-28):** her kayıt öğretmenin elle bastığı kayıttır. Teneffüste (`_aktif_ders_no is None`) kartlar ve "YOKLAMAYI KAYDET" devre dışı (`_girisleri_ayarla`). Dönem değişince yalnız yeni dersin grubu yüklenir.
- Pencere başlığı tam `"Yoklama"`; 10 dakika kuralı ve `_pencereyi_one_getir` `yoklama.py` içinde; panonun uzaktan başlatması (`dashboard/uzaktan_baslat.py`, pgrep+wmctrl) bununla çakışmaz.
- Sınıf seçme kutusu yalnız **uygulama açılışında** `data/roster/*.json` taranarak dolar; yeni dosya için uygulamayı yeniden açmak gerekir.
- **Başlık/kazanım:** `data/ders_programi.json`'dan ders adı, `data/kazanimlar.json`'dan haftanın kazanımı (başlık altı, 13pt tek satır); ikisini istemci çeker. `kazanimlar.json` `dashboard/scripts/kazanim_yukle.py` ile üretilir. Ders dışında başlık `YOKLAMA — BOŞ`.

## 3.1 Tahta istemcisi (`tahta_istemci.py`, 2026-10-06)

Sistem `python3`, yalnız stdlib, `systemd --user` birimi `tahta-istemci.service`, ayar `~/tahtayoklama/istemci.json` (0600). Sunucu ucu: `dashboard/tahta_api.py` (`/api/v1/tahta/*`).
- `data/kayitlar/` son 7 gün, 15 sn'de bir, sha256 değiştiyse `POST /kayit` (durum `data/.istemci_durum.json`). 4xx = kalıcı ret.
- 60 sn'de `POST /nabiz` → `tahta_nabiz`; gövdede `saglik` (sıcaklık, bellek, takas, yük, OOM, dokunmatik kopması). Eşikler `dashboard/tahta_saglik.py`; gösterim `/sistem-durumu` "Tahtalar". Saatte bir tam SSH taraması.
- 10 dk'da `GET /yapilandirma` (ETag): roster (yalnız atanmış sınıf, `admin._roster_payload_olustur` ile bayt bayt aynı; sınıfsız fenlab'da roster dizinine DOKUNULMAZ), `zil.json`, `ders_programi.json`, `kazanimlar.json` (yalnız kendi düzeyi; fenlab hepsi). Doğrulanmadan yazılmaz; değişen/silinen dosya `data/.istemci_yedek/`'e.
- Kimlik: tahta başına token; sunucuda yalnız SHA-256 (`dashboard/config/tahta_tokenlari.json`, gitignore'lu).
- Kurulum/güncelleme/kaldırma: `venv/bin/python scripts/tahta_istemci_kur.py <tahta...>|--hepsi [--kaldir]` (her çalıştırma yeni token). Log: tahtada `journalctl --user -u tahta-istemci`.
- `onbellege_yaz` (`yoklayici.py`) tek yazma yolu: 'alindi' üstüne yalnız kesin daha yeni `kaydedilme_saati` yazar.
- **Duyuru (2026-10-30):** ~5 sn'de `GET /duyuru` (`dashboard/duyuru.py`; hedef `tum-okul`|tahta|sınıf) → `announcement_agent.py --goster` (PyQt6, odak çalmaz; bilgi/idare/acil). Ses: sunucuda EMA TTS wav, `GET /duyuru/<id>/ses`; ding `assets/ding.wav`. Pencere/pid `data/.duyuru/`. `--test` sunucusuz dener. Test: `test_duyuru.py`.
- **Deneme hatırlatması (2026-11-01, `dashboard/deneme_hatirlatma.py`, lifespan görevi):** okul günü ilk teneffüs başı (1. ders bitişi) ve öğle arası başında (zil.json, ilk 5 dk) okul `http://127.0.0.1:9090/api/pano` `yaklasan_denemeler`'ini çekip denemenin düzeyindeki sınıflara `bilgi` duyurusu yazar; aynı mesaj+hedef 30 dk içinde tekrar yazılmaz. Tarih tutmaz, kaynak okul sınav takvimi. Test: `test_deneme_hatirlatma.py`.
- **Duyurular paneli (2026-11-01, `dashboard/duyurular_panel.py`, `/duyurular`, kısayol d):** tahta duyurusu gönder/kapat + son 2 gün (`duyuru.formdan_gonder`, `/admin/uzaktan` formuyla ortak), otomatik deneme hatırlatmaları + sonraki gönderim, smual.app yayındaki duyurular (`okul.db` `mode=ro`, aylik_ozet istisnası), kiosk panosu duyuruları (okul `/api/pano`). Zil paneli üst çubukta solda sabit düğme (`menu.ZIL`, kısayol z). Test: `test_duyurular_panel.py`.

## 4. `dashboard/` — merkezi web panosu

Farabi `server/` FastAPI'sinden **tamamen bağımsız**: kendi venv'i, SQLite'ı, portu (**80**; drop-in `port80.conf` ana birimdeki 8010'u ezer, 8010 artık Atos), systemd birimi `farabi-yoklama-dashboard.service` (`After=`/`Wants=` YOK). `server/tahtalar.json`'a **geri yazma YOK**; pano kendi tahta/sınıf kaydını tutar.

### SQLite şeması (özet — `db.py`)

| Tablo | Amaç |
|---|---|
| `siniflar` | id, ad ('9-A', ...), aktif |
| `ogrenciler` | sinif_id FK, no, ad_soyad, cinsiyet (opsiyonel) |
| `tahtalar` | ad, ip, ssh_kullanici, python_yolu, sinif_id FK (NULL=atanmamış), aktif — yalnız bu DB'de |
| `yoklama_onbellek` | tarih+sinif+ders_no UNIQUE; durum (`alindi`\|`alinmadi`\|`henuz_baslamadi`\|`tahta_ulasilamaz`\|`ders_yok_o_gun`\|`tahta_atanmamis`); yok/izinli isimleri JSON; sinif alanı FK DEĞİL (kasıtlı) |
| `oturumlar` | token, tek ortak şifre (`auth.py`, scrypt) |
| `uzaktan_denetim` | her uzaktan eylem: `zaman` (İstanbul, +03:00; diğer tablolar UTC), `istemci_ip`, `eylem`, `tahtalar`, `sonuc` (`9-A:ok,9-B:hata` / `secim_yok` / `<tahta>:ders_saati`), `kaynak` (`/api/ajan` çağrılarında `openwebui:<e-posta>`). `eylem` ajan çağrılarında `ajan:<eylem>`. Kullanıcı sütunu yok; URL/dosya adı/içerik yazılmaz |
| `tahta_nabiz` | tahta başına tek satır: son_gorulme (UTC), ip, istemci_surum, yoklama_acik, `saglik` JSON (sürüm 3+; `tahta_saglik.saglik_temizle` beyaz listesi) |
| `tahta_saglik_gecmis` | her nabızdaki ölçüm; 14 gün tutulur (`gecmisi_buda`), index (tahta_ad, zaman) |

### Ana bileşenler

| Dosya | İş |
|---|---|
| `app.py` | giriş noktası, lifespan (DB + polling + arka plan görevleri), `/`, `/giris`, `/api/durum`, `/api/yenile`, `/api/tahta/{id}/baslat` |
| `ssh_istemci.py` | `ssh`/`scp` sarmalayıcı, `x_ortamini_kesfet` (DISPLAY/XAUTHORITY/uid — tek kopya), `tahtanin_kayitlarini_tara`, allow-list doğrulama |
| `yoklayici.py` | SSH polling motoru: aktif tahtalar `asyncio.gather` ile paralel, `yoklama_onbellek`'e UPSERT; tahta listesini HER turda DB'den okur |
| `tahta_api.py`, `tahta_saglik.py` | tahta istemcisinin HTTP ucu, sağlık eşikleri (§3.1) |
| `zil.py` | `zil.json` + ders zamanlaması, `Europe/Istanbul`; `gun_adi_buyuk()` sabit sözlük (`.upper()` DEĞİL, Türkçe "İ") |
| `admin.py` | `/admin/siniflar` (sınıflar+tahta ataması), roster düzenleme/senkron, `/admin/rapor` devamsızlık+CSV |
| `uzaktan_yonetim.py`, `uzaktan_baslat.py`, `tahta_kaydi.py`, `tahta_yeniden_baslat.py` | uzaktan yönetim (§5) |
| `ajan_api.py` | `/api/ajan/*` makine API'si (§5.2) |
| `menu.py`, `yakinda.py` | tek menü kaynağı, `/b/<ad>` yer tutucular (tasarım bölümü) |
| `duyuru.py`, `duyurular_panel.py`, `deneme_hatirlatma.py`, `acil.py` | duyuru, duyurular paneli, otomatik hatırlatma, acil durum |
| `sistem_durumu.py` | `/sistem-durumu` (§4.1) |
| `kulupler.py`, `kulup_yoklama.py` | kulüp listeleri/yoklaması (§4.0a) |
| `kazanim_rapor.py` | `/kazanim` (§4.0) |
| `okul_ana_*.py`, `okul_bilgisi.py`, `okul_sql.py` | `okul_ana` paneli/yayını, Atos veri ucu (kök CLAUDE.md "Atos veri erişimi") |
| `guvenlik.py`, `kameralar.py`, `sunucular.py`, `servis_yonetimi.py`, `zamanlanmis_gorevler.py` | güvenlik/kamera, sunucu ve servis yönetim sayfaları |
| `db.py`, `auth.py`, `ders_programi.py`, `devamsizlik_bildirim.py`, `veli_mesajlari.py`, `aylik_ozet.py`, `bugun.py` | şema/bağlantı, ortak şifre + smssistemi SSO (`config/sms_sso.json`), pano ders etiketi, bildirim/özet sayfaları |
| `static/kenar.js`, `static/menu.js`, `static/tema.js` | kenar menü + tema |

**Polling penceresi:** Pazartesi-Cuma, ilk dersten ~20 dk önce – son dersten ~20 dk sonra, ~2 dk'da bir; pencere dışında SSH yok.

**Sınıf listesinin tek kaynağı = pano DB `ogrenciler` (2026-10-08).** Sunucudaki `tahtayoklama/data/roster/*.json` eski anlık görüntü, arşive taşındı; Atos öğrenci aracı DB'den okur. Tahtalardaki `~/tahtayoklama/data/roster/` ayrı ve günceldir (pano yazar). `ilk_yukleme.py`, `pdf_disari_aktar.py`, `smssistemi/scripts/roster_ice_aktar.py` tek seferlik, yeniden çalıştırılmaz.

### 4.0a Kulüp listeleri (`/admin/kulupler`, 2026-10-23)
Kaynak `dashboard/config/kulupler.json` (gitignore'lu, 0600, öğrenci verisi); ilk dolum `scripts/kulup_ice_aktar.py`, sonra panelden. Kulüp `kod`u (`KULUP-<ad>`) değişmez (`kulup_yoklama` kayıtları ve roster dosya adı ona bağlı). Kulüp, `sinif` alanındaki sınıfın tahtasına `/yapilandirma` ile ≤10 dk'da gider; sınıf değişince eski tahtadaki dosyayı istemci kaldırır. Test: `test_kulup_duzenle.py`.

### 4.0 Kazanımlar (`/kazanim`, eski `/kazanim-rapor` 308 ile yönlenir)
`kazanim_rapor.py`: kazanimtest'in `/mnt/farabi-data/farabi/kazanim_testleri/rapor/<sinif>.json` dosyalarını **salt-okunur** gösterir. Öğrenci adı yalnız panonun roster'ından (`okul_no` = `ogrenciler.no`). Sınıf seçimi dizindeki dosya adlarından (yol enjeksiyonu yok). Test: `test_kazanim_rapor.py`.

### 4.1 Sistem Durumu (`/sistem-durumu`, `/api/sistem-durumu[?trend=1]`)
`sistem_durumu.py`: lifespan'daki tek arka plan görevinde ölçüm (donanım, HTTP/SQL/uzak yoklamalar), API önbellekten okur; trend bellekte. SALT OKUNUR; restart/komut endpoint'i YOK, olmamalı. Farabi PostgreSQL'ini (`metrik`, `pg_stat_*`) `psql` ile salt-okunur sorgular (DB paylaşımı kuralının bilinçli ikinci istisnası). SMS modemine bağlanmaz, yalnız Müdür PC proxy portuna TCP. Birim `Environment`'ı API'ye konmaz (ollama'nınki parola içeriyor). Test: `test_sistem_durumu`.

## 5. Uzaktan Yönetim (`/admin/uzaktan`)

Windows'taki `tahta_panel.py`'nin web karşılığı: yoklama aç/kapat, web sayfası aç/chrome kapat, ekranı karart/kaldır, duvar kağıdı; hepsi toplu. Tasarım: `docs/superpowers/specs/2026-09-15-tahta-uzaktan-yonetim-design.md`.
**Kasıtlı dışarıda** (etapadmin+sudo gerektirir): masaüstüne dosya gönderme, oturum aç/otomatik giriş kur-kaldır, "kapat butonunu karartmaya çevir".

- Hedefler HER ZAMAN `server/tahtalar.json`'dan (`tahta_kaydi.py`); istemciden yalnız "ad" kabul edilir, IP/komut asla.
- Ayrı yönetici şifresi YOK; ortak pano şifresi/oturum çerezi yeterli (bilinçli kabul edilmiş risk). Eylemler `uzaktan_denetim`'e yazılır; log hatası eylemi engellemez (`_denetim_yaz`). Oturumsuz tarayıcı isteği (`Accept: text/html`) 303 → `/giris`, JSON 401.
- Sudo gerektirmez: Farabi'nin SSH anahtarı (`~/.ssh/id_ed25519_tahta`) `ogretmen`'e yetkili. **Tek istisna: "Yeniden Başlat"** (`/admin/uzaktan/yeniden-baslat`, `_yeniden_baslat_tek`): sudo işi `tahta_yeniden_baslat.py`'de (admin hesabı + yalnız `systemctl reboot` sudoers, 120 sn bekleme); ders saatinde (`ders_saatinde_mi`) reddedilir, tarayıcıda onay sorulur. Makine API'sinin `EYLEMLER`'ine girmez.
- **Canlı ekranlar:** sayfa altında açık tahtaların ekranı 3 sütunda, 30 sn'de bir sırayla (`ekran-goruntusu?ham=1`, 8 sn zaman aşımı, sekme gizliyken durur). Karta sağ tık = tek tahtaya toplu eylem menüsü.
- X-ortamı keşfi tek yerde: `ssh_istemci.x_ortamini_kesfet()` (iki kopya senkron kalmamıştı, bkz. `tahtaayar/CLAUDE.md`).
- Duvar kağıdı: `_duvar_kagidi_tek` yalnız Cinnamon `gsettings` çıkış kodunu raporlar (`$CINNAMON_DURUM`), GNOME yedek/best-effort. Tahta seçilmeden gönderim JS ile engellenir.
- **Ders:** şüpheli "çalışmıyor" bildiriminde önce statik koda değil canlı tahtaya (`server/tahta-ssh.sh` salt-okunur teşhis) bak.
- Küçük açık: "Yoklama Aç" art arda 2 SSH turu yapıyor (`_python_yolu_bul` + `x_ortamini_kesfet`).

### 5.1 Ekran görüntüsü (`GET /admin/uzaktan/ekran-goruntusu/{tahta}?ham=1`)
Oturum zorunlu, tahta adı `tahtalar.json`'dan doğrulanır. SSH ile yakalama, fallback zinciri: `import -window root -resize 1280x -quality 70 jpg:-` (ImageMagick); yoksa `gnome-screenshot --file=/tmp/tahta_ss.png && cat ... && rm -f ...` (fenlab; eski GNOME'da `-f "$F"` hata verir, `--file=` şart). Pillow ile >1280 px küçültülür, JPEG %75. `ham=1` ikili JPEG döner (yeni sekmede açılır), hata durumunda HTML hata sayfası; `ham=0` JSON. Tabloda son sütun `.ss-link-btn` (`target="_blank"`), görsel gömülmez. Ekran görüntüsü/sayfa görüntüleme denetime YAZILMAZ. Test: `test_uzaktan_ekran.py`, `test_uzaktan_denetim.py`.

### 5.2 Makine API'si (`/api/ajan`, `ajan_api.py`)
Tek istemci: eski Open WebUI "Farabi Yönetim" aracı (`_arsiv/openwebui/`; AnythingLLM'e taşınmadı).
- Uçlar: `GET /tahtalar[?canli=1]`, `GET /sistem`, `GET /yoklama[?tarih=&sinif=]`, `POST /eylem` (`uzaktan_yonetim.EYLEMLER`), `POST /yeniden-baslat`.
- Kimlik: yalnız 127.0.0.1/::1 VE `X-Farabi-Ajan-Key` (`config/ajan.json`, gitignore'lu). Oturum çerezi GEÇMEZ.
- Yanıtlarda IP/MAC/kullanıcı adı/SSH ayrıntısı/ham hata yok; bilinmeyen tahta 400 (`bilinmeyen` listesi), hiçbir şey çalıştırılmaz.
- Yeniden başlatma: okul saatinde 409 (`ders_saatinde_mi`: ders günü ilk ders başı – son ders sonu, teneffüs/öğle DAHİL); tahta başına 120 sn bekleme (`BEKLEME_SN`, atomik). Tahtada `etapadmin` + `sudo -n /usr/bin/systemctl reboot` (kural: tahtaayar `reboot_sudoers`).
- Denetim: her çağrı `uzaktan_denetim`'e (`ajan:<eylem>`, `kaynak`); reddedilen reboot `<tahta>:ders_saati`.

## 6. Tahta envanteri

**Esas kaynak `server/tahtalar.json`** (IP DHCP ile değişir; hostname/MAC esas, kök CLAUDE.md). Aşağıdaki tablo 2026-09-17 anlık görüntüsüdür, IP'ler eski olabilir.

| Tahta | IP (09-17) | Not |
|---|---|---|
| 9-A | .245 | Farabi client venv'ini paylaşır |
| 9-B | .235 | donanım değişti, MAC 00:09:df:83:5c:45 |
| 10-A | .242 | |
| 11-A | .228 | |
| 11-B | .233 | |
| 12-A | .226 | 2026-09-22'de .231→.226 (aynı MAC `00:09:df:83:ff:cc`, `vestel12a`) |
| 12-B | .240 | |
| tahta-234 / 235 / 236 | .234 / .235 / .236 | sınıf değil / eski 11-A kaydı (§7) |
| fenlab | .244 | fen laboratuvarı, ortak kullanım (eski tahta-244), MAC `00:09:df:8c:32:8a` |

- **IP değişirse sessizce `tahta_ulasilamaz` birikir** (12-A olayı: günün yarısı yoklamasız kaldı). IP/MAC güncellenecek yerler: `server/tahtalar.json`, dashboard `tahtalar` tablosu, `docs/runbook.md`. Polling listeyi her turda DB'den okuduğu için restart gerekmez. Açık iyileştirme: "uzun süre ulaşılamayan tahtanın MAC'i başka IP'de görünüyor" uyarısı yok.
- `network.txt` ikincil referanstır ve sapabilir (sınıf etiketleri kaymıştı); şüphede `tahtalar.json` + canlı doğrulama.
- OS-düzeyi güç/uyku düzeltmeleri `tahtaayar/tahta_fix_uygula.py --sadece-kontrol` ile taranır; 8/8 tahta aynı ayarda (2026-09-17).

## 7. Tahta↔sınıf ataması — kalıcı gerçekler

- `/admin/tahtalar` ayrı sayfa değil: atama tablosu `/admin/siniflar` (`admin._siniflar_sayfasi`) içinde, eski adres yönlenir.
- **"Yükle" dışında atama yalnız dashboard SQLite'ını değiştirir, tahtaya bir şey göndermez.** Tahtaya dosya yazan TEK yol atama+senkronun birleştiği "Yükle" (`admin.py::_tahtaya_roster_gonder`, eski roster dosyalarını siler). Takas route'u/sürükle-bırak kaldırıldı.
- `senkronize` SSH başarısız olsa da HTTP 200 döner; 200 tahtaya ulaştığının kanıtı DEĞİL, dosyayı SSH ile geri oku.
- **`tahta-234`/`tahta-235`/`fenlab` sınıf DEĞİL** (234/235'in hangisi kütüphane, hangisi spor odası belirsiz). Yoklama alınmaz; `siniflar`'a eklenmediler, `tahta_atanmamis` kalır. Lab1/2/3 kurulumu iptal.
- **`fenlab`:** hostname `fenlab`; dashboard'da `sinif_id=NULL` BİLEREK (tek sınıfa sabitlemek yanlış). Roster dizininde 7 sınıfın hepsi var (combo box'tan seçilir); `kazanimlar.json` hepsi gider. Farabi client + tahtayoklama kuruldu (`gemini_api_keys` boş bırakıldı, kullanıcı girer). `farabi-kurulum.sh` ön koşul kontrolü `ensurepip`'e bakar (Debian'da `python3.X-venv`).
- **`tahta-236`:** eski "11-A" kaydı; DB'de `sinif_id=NULL`, satır SİLİNMEDİ (SSH ihtimali).

## 8. Açık işler

1. Uzaktan Yönetim'de ayrı yönetici rolü yok (bilinçli kabul edilmiş risk); denetim tablosu var.
2. Harici Windows araçlarıyla ilişki netleşmedi (§9).
3. Küçük iyileştirme: "Yoklama Aç" fazladan SSH turu (§5).

## 9. Harici tahta yönetim programları (kullanıcının Windows PC'si, depoda YOK)

`C:\Users\exa\Desktop\TAHTA ISLERI\tahta_panel.py`, `tahta_ssh.py` — aynı tahtaları uzaktan yönetir; içerik okunamadı. Muhtemel kimlik (TEYİT EDİLMEDİ): 9-B/11-B/12-A SSH loglarında `192.168.23.243`'ten ~30 sn'de bir `etapadmin` girişi (`pkexec .../ETAKisitActivator.py --disable-websites-restriction`); bu IP `tahtalar.json`'da yok. `/admin/uzaktan` işlevlerinin bir kısmını web'e taşıdı; çakışma sınırı belirsiz.

## 10. Kurallar (kök CLAUDE.md'ye paralel)

1. Tahtalarda ÇALIŞAN `yoklama.py`'ye dokunmadan önce iki kez düşün; canlı sistem, geriye dönük uyumu koru. Veri şeması (roster/kayıt JSON) `dashboard/`'un varsaydığıyla birebir uyuşmalı.
2. Tek seferde tek modül. Değiştirmeden önce ilgili dosyayı oku.
3. Docker yok, systemd servisleri. Yeni ağır bağımlılık (paramiko, APScheduler, Redis...) için önce onay.
4. `dashboard/config/gizli.json` asla commit edilmez.
5. Servis restart'ları (`farabi-yoklama-dashboard` vb.) yalnız ders saatleri (08:00-17:00 TR) DIŞINDA. Tahta yeniden başlatma kuralı (§5.2, `ders_saatinde_mi`, programa bağlı) ayrıdır; aynı pencere değil.
6. Son kabul (fiziksel/görsel doğrulama) HER ZAMAN kullanıcıdadır.

## 11. `dashboard/scripts/` — bakım/kurulum araçları

Tek seferlik, elle tetiklenir; hiçbiri crontab/timer'a bağlı değil:
- **`ders_programi_yukle.py`** — `mudur/siniflar.pdf` → `tahtayoklama/data/ders_programi.json` (pano etiketi). Dağıtım yapmaz. **KISALTMALAR sözlüğü `mudur/ders_programi_yukle.py` ile SENKRON tutulmalı** (tek doğru kaynak yok). Ders programının güncel kaynağı `okul_ana` (kök CLAUDE.md).
- **`zil_yukle.py`** — `VARSAYILAN_SAATLER` sabitinden, `--no-dagit` verilmedikçe `tahtalar.json`'daki her tahtaya SCP ile yazar.
- **`ilk_yukleme.py`** — tek seferlik DB tohumlama; idempotent DEĞİL, üretim DB'sinde çalıştırma.
- **`sifre_belirle.py`** — ortak pano şifresi hash'i → `config/gizli.json`.
- **`ajan_anahtari_olustur.py`** — `/api/ajan` anahtarı → `config/ajan.json` (0600); `--zorla` olmadan ezmez, ekrana basmaz. `--zorla` sonrası `openwebui/kur.py` yeniden çalıştırılmalı.
- **`kazanim_yukle.py`**, **`tahta_istemci_kur.py`** — §3, §3.1.
- `tahta_fix_uygula.py` → `tahtaayar/tahta_fix_uygula.py`'ye taşındı.

## Frontend / Dashboard Tasarım Standartları

Kapsam yalnız `dashboard/templates/` + `static/`. Client PyQt6 arayüzü (`client/ui.py`) kapsam DIŞI.

**Görsel kimlik kurulu, dondurulmuş sayılır** (Atakan onayıyla Creative Tim Argon esinli; CSS/Bootstrap içeri ALINMADI). Tasarım sistemi `static/pano.css` başındaki Türkçe CSS değişkenleri (`--renk-*`, `--yaricap*`, `--yazi-tipi`) ve altı tema (`data-tema`): `argon` (`:root`), `argon-koyu`, `koyu`, `black`, `material`, `material-koyu`. Kenar menü renkleri `--renk-kenar-*` (`:root`'ta var() ile türer, yalnız Material ezer). Kayıt yoksa sistem tercihi (açık→`argon`, koyu→`argon-koyu`); eski `klasik`/`yumusak` → `argon`. frontend-design becerisi "sıfırdan kimlik kur" modunda çalıştırılmaz; disiplini mevcut token sistemi İÇİNDE uygula.
- Ham hex renk yazılmaz; yeni değişken TÜM tema bloklarında tanımlanır (ya da `:root`'ta var() ile türetilir).
- Grafikler kütüphanesiz: satır içi SVG (`/sistem-durumu`) ya da HTML/CSS çubuk (`admin._rapor_grafikleri`).
- Arayüz metni Türkçe, cümle düzeninde (ALL-CAPS etiket yok).
- Sayfa sırası: Başlık > CTA > KPI > tablo/grafik; öğretmen 5 sn'de "hangi sınıfta yoklama eksik"i görebilmeli.
- Durum renkleri: başarılı `--renk-yesil`, uyarı `--renk-amber`, hata `--renk-kirmizi`, nötr `--renk-gri`; zeminler `--renk-*-zemin`. Yenisi uydurulmaz.
- Geçiş süreleri yerleşik: **0.15 s** (renk/zemin), **0.12 s** (transform/gölge). Yükleme için `skeleton`, boş durum için `empty-state` (ne olduğunu ve ne yapılacağını söyler). `pano.css` sonundaki `prefers-reduced-motion` bloğu yeni animasyonu kapsıyor mu kontrol et.
- **Menü ve kabuk:** gezinmenin TEK kaynağı `menu.py` (`MENU`, `menu_agaci(yol)` → `menu`, `konum`, `ders`); `taban.html` tek `<nav class="kenar">` üretir (geniş / `html.kenar-dar` 72 px, `localStorage farabi_kenar_dar` / <720 px çekmece). Davranış `static/menu.js` (↑↓/F10/`?`). Acil durum en üstte kırmızı, dipte `alt: True` (Atos, Temalar, Ayarlar). Başlık şeridinde menü yok: kırıntı, `h1`, `ust_sag`, gün/saat/ders, tema düğmesi. Sayfa ekleyince öğeyi `menu.py`'ye ekle; yapılmamış bölümler `/b/<ad>` (`yakinda.py`). Her `Jinja2Templates` örneğine `templates.env.globals["menu_agaci"]` eklenmeli (`test_menu` denetler). Gün adı `zil.gun_adi_buyuk()` ile `templates.env.globals` üzerinden. CSS/JS bağlantıları `?v=<static mtime>` taşır. Butonlar `.dugme` / `-ikincil` / `-tehlike` / `-kucuk` / `.dugme-ikon`; `[hidden]` her zaman gizler.
- ⚠️ Şablonlar canlıya ANINDA yansır, Python kodu restart ister: dashboard değişikliğini master'a alınca `farabi-yoklama-dashboard`'u yeniden başlat (2026-10-08'de ~8 sn sayfalar 500 verdi).
- **İkonlar:** `templates/_ikon_sprite.html` içinde satır içi `<symbol>` sprite (Lucide konvansiyonu: 24×24, `currentColor`, `stroke-width=2`). Kullanım: `<svg class="ikon"><use href="#ik-<ad>"/></svg>`; boyut `.ikon`, `.ikon-kucuk`, `.ikon-buyuk`, `.ikon-disa`. Eksik ikon Lucide/Tabler kaynağından `ik-` önekli Türkçe adla sprite'a eklenir. `lucide-react`/CDN KULLANILMAZ. İkonu ince sayfalara (`uzaktan_yonetim`, `admin_tahtalar`, `admin_sinif_ogrenciler`, `admin_siniflar`, `admin_rapor`) ikon eklemek serbest.
- **Kompakt yoğunluk:** `gap` 0.3–0.6rem, `padding` ~0.45×0.9rem, gövde 0.78–0.88rem zaten referans; küçültme. Boşluk token'ı yok ve ~10 yakın punto var: yeni CSS'te mevcut bir değeri seç, 0.83 gibi ara değer üretme. Ölçeğe indirgemek `pano.css` (üretim) için ayrıca onay ister.
- Canlı göstergeler (yeşil pulse nokta); tablolarda pagination yerine dikey kaydırma. İstisna: büyüyen rapor tabloları sayfalanır (`/admin/rapor` 100 satır/sayfa, `admin.py::_sayfala`).
- ⚠️ **Kütüphane kuralı:** dashboard SIFIR dış bağımlılıkla çalışır (CDN, Tailwind, grafik/ikon paketi yok). Okul ağında SSL-inceleme var ve tahtalar eski i3-2330M; CDN derste sessizce boş ekran verir. Gerçekten gerekirse onay al ve yerel olarak `static/`'e indir.
