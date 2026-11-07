# tahtayoklama

Sınıf akıllı tahtalarında dokunmatik yoklama arayüzü (PyQt6) + merkezi web panosu (`dashboard/`, FastAPI, port 80, `farabi-yoklama-dashboard.service`).
**Farabi'den TAMAMEN BAĞIMSIZ** (kullanıcı kararı): Farabi `actions/` registry'sine girmez, `client/`'a bağlı değildir; Farabi'nin sesli yoklaması bu sistemden habersizdir (iki paralel yol).

## Mimari
- **`yoklama.py`** (tahta, PyQt6 GUI): ağdan izole; tek durum kaynağı tahtanın diskindeki JSON dosyaları. Autostart DEĞİL (`~/Masaüstü/Yoklama.desktop`, öğretmen açar).
- **`tahta_istemci.py`** (tahta, ayrı süreç): sistem `python3`, yalnız stdlib, `systemd --user` `tahta-istemci.service`, ayar `~/tahtayoklama/istemci.json` (0600); sunucu ucu `dashboard/tahta_api.py` (`/api/v1/tahta/*`). `announcement_agent.py`: ayrı PyQt6 duyuru süreci.
- **Sunucu → tahta SSH** (`dashboard/ssh_istemci.py`, `yoklayici.py`): polling, uzaktan eylemler, roster senkronu. Nabzı taze (≤5 dk) tahta kısmi turda SSH ile taranmaz; istemcisiz tahta tamamen SSH ile taranır.
- Teknoloji: FastAPI + Jinja2 + vanilla JS (build/npm yok) + SQLite WAL (`veri/yoklama_pano.db`) + doğrudan `ssh` (paramiko/APScheduler yok). Yeni ağır bağımlılık: önce onay. Polling: Pzt-Cum, ilk dersten ~20 dk önce – son dersten ~20 dk sonra, ~2 dk'da bir; pencere dışında SSH yok.
- Dashboard: kendi venv/SQLite; birimde `After=`/`Wants=` YOK; port 80 drop-in `port80.conf` ile (8010 artık Atos). `server/tahtalar.json`'a geri yazma YOK.
- `data/` = DEV kopyası; tahtalarda `~ogretmen/tahtayoklama/data/`: `roster/<sinif>.json`, `kayitlar/<tarih>_<sinif>_ders<no>.json`, `zil.json`, `ders_programi.json`, `kazanimlar.json`. Roster/kayıt JSON şeması `dashboard/`'un varsaydığıyla birebir uyuşmalı.

## Komutlar
```bash
cd tahtayoklama/dashboard
venv/bin/uvicorn app:app --reload --port 8099          # DİKKAT: lifespan polling'i de başlatır (canlıyla çift polling)
venv/bin/python -m unittest discover -p 'test_*.py'    # pytest DEĞİL (venv'de pytest yok)
venv/bin/python -m unittest test_uzaktan_ekran -v      # tek dosya (modül adı, .py YOK)
venv/bin/python -m unittest test_uzaktan_ekran.TestUzaktanEkran.test_route_gecersiz_tahta   # tek test
venv/bin/python scripts/sifre_belirle.py               # ortak pano şifresi → config/gizli.json
sudo systemctl restart farabi-yoklama-dashboard.service   # YALNIZ ders saatleri (08:00-17:00 TR) DIŞINDA
```
- `tahtayoklama/test_yoklama.py` (tahta GUI) pytest'tir; `tahtayoklama/venv`'de pytest yok, PyQt6+pytest'li ayrı dev venv: `QT_QPA_PLATFORM=offscreen <venv>/bin/python -m pytest tahtayoklama/test_yoklama.py -q`.
- ⚠️ Şablonlar canlıya ANINDA yansır, Python kodu restart ister: dashboard değişikliğini master'a alınca restart et (bir kez ~8 sn sayfalar 500 verdi).

## `yoklama.py` (tahta deployment gerçekleri)
- Python yolu tahtaya göre değişir: 9-A dışında `/home/ogretmen/tahtayoklama/venv/bin/python`; yalnız 9-A Farabi client venv'ini paylaşır. Başlatma adayları dener (`uzaktan_yonetim._PYTHON_ADAYLARI`, DB `tahtalar.python_yolu`).
- Ağ I/O yok; tek-örnek koruması yerel Unix soketi. Sınıf kutusu yalnız açılışta `data/roster/*.json` taranarak dolar.
- Kayıt o an seçili sınıfa göre isimlenir; "tahta X = sınıf Y" varsayma, kayıttaki `sinif` esas.
- Otomatik/sessiz kayıt YOK: her kayıt öğretmenin elle bastığı kayıt. Teneffüste (`_aktif_ders_no is None`) kartlar ve "YOKLAMAYI KAYDET" devre dışı.
- Pencere başlığı tam `"Yoklama"` (`uzaktan_baslat.py` pgrep+wmctrl buna bağlı).
- Tahtalarda çalışan `yoklama.py`'ye dokunmadan önce iki kez düşün; geriye dönük uyumu koru.

## Tahta istemcisi (`tahta_istemci.py`)
- `data/kayitlar/` son 7 gün, 15 sn'de bir, sha256 değiştiyse `POST /kayit`; 4xx = kalıcı ret.
- 60 sn'de `POST /nabiz` → `tahta_nabiz` (`saglik`; eşikler `dashboard/tahta_saglik.py`). Saatte bir tam SSH taraması.
- 10 dk'da `GET /yapilandirma` (ETag): roster (yalnız atanmış sınıf, `admin._roster_payload_olustur` ile bayt bayt aynı; sınıfsız fenlab'da roster dizinine DOKUNULMAZ), `zil.json`, `ders_programi.json`, `kazanimlar.json`. Doğrulanmadan yazılmaz; değişen dosya `data/.istemci_yedek/`'e.
- Kimlik: tahta başına token; sunucuda yalnız SHA-256 (`dashboard/config/tahta_tokenlari.json`, gitignore'lu).
- Kurulum: `venv/bin/python scripts/tahta_istemci_kur.py <tahta...>|--hepsi [--kaldir]` (her çalıştırma yeni token). Log: `journalctl --user -u tahta-istemci`.
- `yoklayici.onbellege_yaz` tek yazma yolu: 'alindi' üstüne yalnız daha yeni `kaydedilme_saati` yazar.
- Duyuru: ~5 sn'de `GET /duyuru` → `announcement_agent.py --goster`; `/duyurular` paneli (`duyuru.formdan_gonder`, `/admin/uzaktan` formuyla ortak). Test: `test_duyuru.py`, `test_duyurular_panel.py`.
- `deneme_hatirlatma.py` (lifespan): okul `http://127.0.0.1:9090/api/pano` `yaklasan_denemeler`'inden `bilgi` duyurusu yazar; aynı mesaj 30 dk tekrarlanmaz. Test: `test_deneme_hatirlatma.py`.

## SQLite şeması (özet, `db.py`)
- `siniflar`, `ogrenciler` (sinif_id FK, no, ad_soyad), `tahtalar` (ad, ip, python_yolu, sinif_id NULL=atanmamış, aktif), `oturumlar` (tek ortak şifre, scrypt).
- `yoklama_onbellek`: tarih+sinif+ders_no UNIQUE; durum `alindi|alinmadi|henuz_baslamadi|tahta_ulasilamaz|ders_yok_o_gun|tahta_atanmamis`; sinif FK DEĞİL (kasıtlı).
- `uzaktan_denetim`: `zaman` İstanbul +03:00 (diğer tablolar UTC), `eylem` (ajan: `ajan:<eylem>`), `sonuc` (`9-A:ok,9-B:hata`/`secim_yok`/`<tahta>:ders_saati`), `kaynak`. Kullanıcı sütunu yok; URL/dosya adı/içerik yazılmaz.

## Ana modüller (`dashboard/`)
- `app.py`: lifespan (DB + polling + arka plan görevleri), `/api/durum`, `/api/yenile`. `ssh_istemci.py`: `ssh`/`scp` sarmalayıcı, `x_ortamini_kesfet` (TEK kopya), allow-list doğrulama.
- `yoklayici.py`: SSH polling; tahtalar `asyncio.gather` ile paralel, `yoklama_onbellek`'e UPSERT; tahta listesini HER turda DB'den okur (IP değişince restart gerekmez).
- `zil.py`: `gun_adi_buyuk()` sabit sözlük (`.upper()` DEĞİL, Türkçe "İ"). `admin.py`: `/admin/siniflar`, roster senkron, `/admin/rapor`.
- Uzaktan: `uzaktan_yonetim.py`, `uzaktan_baslat.py`, `tahta_kaydi.py`, `tahta_yeniden_baslat.py`; `ajan_api.py`; `menu.py`, `yakinda.py`.
- `okul_ana_*.py`, `okul_bilgisi.py`, `okul_sql.py`: `okul_ana` paneli, Atos veri ucu (kök CLAUDE.md). `auth.py`: ortak şifre + smssistemi SSO (`config/sms_sso.json`).
- Sınıf listesinin TEK kaynağı = pano DB `ogrenciler`. Sunucudaki `tahtayoklama/data/roster/*.json` eski anlık görüntü; tahtalardaki roster ayrı ve günceldir (pano yazar). `ilk_yukleme.py`, `pdf_disari_aktar.py`, `smssistemi/scripts/roster_ice_aktar.py` tek seferlik, yeniden çalıştırılmaz.
- Kulüpler (`/admin/kulupler`): `dashboard/config/kulupler.json` (gitignore'lu, 0600, öğrenci verisi). Kulüp `kod`u (`KULUP-<ad>`) DEĞİŞMEZ.
- `/kazanim`: `kazanim_rapor.py` eski kazanım testi raporlarını SALT-OKUNUR gösterir (kazanım testi iptal, yeniden açma). Test: `test_kazanim_rapor.py`.
- `/sistem-durumu`: SALT OKUNUR; restart/komut endpoint'i YOK, olmamalı. Farabi PostgreSQL'ini `psql` ile salt-okunur sorgular. Birim `Environment`'ı API'ye konmaz (ollama'nınki parola içeriyor). Test: `test_sistem_durumu`.

## Uzaktan Yönetim (`/admin/uzaktan`)
- Yoklama aç/kapat, web sayfası aç/chrome kapat, ekranı karart/kaldır, duvar kağıdı; hepsi toplu. Tasarım: `docs/superpowers/specs/2026-09-15-tahta-uzaktan-yonetim-design.md`. KASITLI dışarıda: masaüstüne dosya gönderme, oturum aç/otomatik giriş.
- Hedefler HER ZAMAN `server/tahtalar.json`'dan; istemciden yalnız "ad" kabul edilir, IP/komut asla.
- Ayrı yönetici şifresi YOK; ortak pano şifresi/oturum çerezi yeterli (bilinçli risk). Eylemler `uzaktan_denetim`'e yazılır. Oturumsuz `Accept: text/html` 303 → `/giris`, JSON 401.
- Sudo gerektirmez (Farabi SSH anahtarı `~/.ssh/id_ed25519_tahta` `ogretmen`'e yetkili). TEK istisna "Yeniden Başlat" (`/admin/uzaktan/yeniden-baslat`, `_yeniden_baslat_tek`, `tahta_yeniden_baslat.py`: admin hesabı + yalnız `systemctl reboot` sudoers); ders saatinde (`ders_saatinde_mi`) reddedilir. Makine API'sinin `EYLEMLER`'ine girmez.
- Ekran görüntüsü (`GET /admin/uzaktan/ekran-goruntusu/{tahta}?ham=1`): oturum zorunlu, tahta adı `tahtalar.json`'dan doğrulanır; yakalama `import -window root`, yoksa `gnome-screenshot --file=...` (`-f` eski GNOME'da hata verir). Denetime YAZILMAZ. Test: `test_uzaktan_ekran.py`, `test_uzaktan_denetim.py`.

## Makine API'si (`/api/ajan`, `ajan_api.py`)
- Uçlar (eski Open WebUI aracı kaldırıldı): `GET /tahtalar[?canli=1]`, `/sistem`, `/yoklama[?tarih=&sinif=]`, `POST /eylem` (`uzaktan_yonetim.EYLEMLER`), `POST /yeniden-baslat`.
- Kimlik: yalnız 127.0.0.1/::1 VE `X-Farabi-Ajan-Key` (`config/ajan.json`, gitignore'lu); oturum çerezi GEÇMEZ. Yanıtlarda IP/MAC/SSH ayrıntısı/ham hata yok; bilinmeyen tahta 400.
- Yeniden başlatma: okul saatinde 409 (`ders_saatinde_mi`: ders günü ilk ders başı – son ders sonu, teneffüs/öğle DAHİL); tahta başına 120 sn bekleme (`BEKLEME_SN`). Tahtada `etapadmin` + `sudo -n /usr/bin/systemctl reboot`.

## Tahta envanteri ve atama
- Esas kaynak `server/tahtalar.json` (IP DHCP ile değişir; hostname/MAC esas). Tahtalar: 9-A, 9-B, 10-A, 11-A, 11-B, 12-A, 12-B, fenlab; sınıf olmayan: tahta-234/235/236.
- **IP değişirse sessizce `tahta_ulasilamaz` birikir.** Güncellenecek yerler: `server/tahtalar.json`, dashboard `tahtalar` tablosu, `docs/runbook.md`.
- `network.txt` ikincil, sapabilir; şüphede `tahtalar.json` + canlı doğrulama.
- Atama tablosu `/admin/siniflar`'da (`admin._siniflar_sayfasi`). "Yükle" dışında atama yalnız dashboard SQLite'ını değiştirir; tahtaya dosya yazan TEK yol "Yükle" (`admin.py::_tahtaya_roster_gonder`, eski roster dosyalarını siler).
- `senkronize` SSH başarısız olsa da HTTP 200 döner; kanıt değil, dosyayı SSH ile geri oku.
- `tahta-234`/`tahta-235`/`fenlab` sınıf DEĞİL: yoklama alınmaz, `tahta_atanmamis` kalır. `fenlab`: `sinif_id=NULL` BİLEREK; 7 sınıfın rosteri ve tüm `kazanimlar.json` gider.
- `tahta-236` (eski "11-A"): `sinif_id=NULL`, satır SİLİNMEZ.

## Kurallar
1. Tek seferde tek modül; değiştirmeden önce ilgili dosyayı oku. Son kabul (fiziksel/görsel) HER ZAMAN kullanıcıda.
2. `dashboard/config/gizli.json` asla commit edilmez.
3. Servis restart'ı yalnız 08:00-17:00 TR DIŞINDA. Tahta yeniden başlatma kuralı (`ders_saatinde_mi`, programa bağlı) ayrıdır; aynı pencere değil.

## `dashboard/scripts/` (elle tetiklenir, hiçbiri timer'a bağlı değil)
- `ders_programi_yukle.py`: `mudur/siniflar.pdf` → `tahtayoklama/data/ders_programi.json`; KISALTMALAR sözlüğü `mudur/ders_programi_yukle.py` ile SENKRON tutulmalı.
- `zil_yukle.py`: `--no-dagit` verilmedikçe her tahtaya SCP ile yazar.
- `ilk_yukleme.py`: idempotent DEĞİL, üretim DB'sinde ÇALIŞTIRMA.
- `ajan_anahtari_olustur.py`: `/api/ajan` anahtarı → `config/ajan.json` (0600); `--zorla` olmadan ezmez.

## Frontend / Dashboard tasarım standartları
Kapsam yalnız `dashboard/templates/` + `static/`. Client PyQt6 arayüzü (`client/ui.py`) kapsam DIŞI.
- **Görsel kimlik kurulu, DONDURULMUŞ** (Argon esinli; CSS/Bootstrap içeri alınmadı). Tasarım sistemi `static/pano.css` başındaki Türkçe CSS değişkenleri (`--renk-*`, `--yaricap*`, `--yazi-tipi`) ve altı tema (`data-tema`): `argon` (`:root`), `argon-koyu`, `koyu`, `black`, `material`, `material-koyu`. Kenar menü renkleri `--renk-kenar-*` (`:root`'ta var() ile türer, yalnız Material ezer). frontend-design becerisi "sıfırdan kimlik kur" modunda çalıştırılmaz; disiplini mevcut token sistemi İÇİNDE uygula.
- Ham hex renk yazılmaz; yeni değişken TÜM tema bloklarında tanımlanır (ya da `:root`'ta var() ile türetilir). Grafikler kütüphanesiz (satır içi SVG / HTML-CSS çubuk).
- Arayüz metni Türkçe, cümle düzeninde (ALL-CAPS yok).
- Sayfa sırası: Başlık > CTA > KPI > tablo/grafik; öğretmen 5 sn'de "hangi sınıfta yoklama eksik"i görebilmeli.
- Durum renkleri: başarılı `--renk-yesil`, uyarı `--renk-amber`, hata `--renk-kirmizi`, nötr `--renk-gri`; zeminler `--renk-*-zemin`. Yenisi uydurulmaz.
- Geçiş: **0.15 s** (renk/zemin), **0.12 s** (transform/gölge). Yükleme `skeleton`, boş durum `empty-state`; `pano.css` sonundaki `prefers-reduced-motion` yeni animasyonu kapsıyor mu kontrol et.
- **Menü/kabuk:** gezinmenin TEK kaynağı `menu.py` (`MENU`, `menu_agaci(yol)`); `taban.html` tek `<nav class="kenar">` üretir (`localStorage farabi_kenar_dar`); davranış `static/menu.js`, tema `static/tema.js`. Sayfa ekleyince öğeyi `menu.py`'ye ekle; yapılmamış bölümler `/b/<ad>` (`yakinda.py`). Her `Jinja2Templates` örneğine `templates.env.globals["menu_agaci"]` eklenmeli (`test_menu` denetler). Gün adı `zil.gun_adi_buyuk()` ile globals üzerinden. CSS/JS bağlantıları `?v=<static mtime>` taşır. Butonlar `.dugme` / `-ikincil` / `-tehlike` / `-kucuk` / `.dugme-ikon`; `[hidden]` her zaman gizler.
- **İkonlar:** `templates/_ikon_sprite.html` içinde satır içi `<symbol>` sprite (Lucide: 24×24, `currentColor`, `stroke-width=2`). Kullanım `<svg class="ikon"><use href="#ik-<ad>"/></svg>`; boyut `.ikon`, `.ikon-kucuk`, `.ikon-buyuk`, `.ikon-disa`. `lucide-react`/CDN KULLANILMAZ.
- **Kompakt yoğunluk:** `gap` 0.3–0.6rem, `padding` ~0.45×0.9rem, gövde 0.78–0.88rem referans; küçültme. Yeni CSS'te mevcut bir punto seç, 0.83 gibi ara değer üretme. Ölçeğe indirgemek `pano.css` için onay ister.
- Tablolarda pagination yerine dikey kaydırma; istisna büyüyen rapor tabloları (`/admin/rapor` 100 satır/sayfa, `admin.py::_sayfala`).
- ⚠️ **Kütüphane kuralı:** dashboard SIFIR dış bağımlılık (CDN, Tailwind, grafik/ikon paketi yok). Okul ağında SSL-inceleme var, tahtalar eski i3-2330M; CDN derste sessizce boş ekran verir. Gerçekten gerekirse onay al, yerel olarak `static/`'e indir.

