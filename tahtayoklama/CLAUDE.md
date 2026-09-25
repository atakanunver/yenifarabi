# tahtayoklama

> **Konsolide doküman (2026-09-17).** Bu dosya, daha önce ayrı duran
> `CLAUDE.md` (fiilen ne yapıldığı), `plan.md` (başlangıç tasarımı, artık
> %90+ uygulanmış) ve aynı gün üretilen `eylulanaliz.md` denetim raporunun
> tahtayoklama'yı ilgilendiren bulgularını **tek, güncel, kronolojik
> olmayan** bir referansta topluyor. `plan.md` bu birleştirmeyle
> **kaldırıldı** (kullanıcı onayıyla) — faz faz anlatım yerine, aşağıda
> "neyin nasıl çalıştığı" konu başlıklarına göre anlatılıyor. Geçmiş
> kararların ayrıntılı gerekçesi hâlâ kök `/home/ata/farabi/DECISIONS.md`'de
> duruyor, oradan silinmedi.

Sınıf akıllı tahtalarında dokunmatik yoklama arayüzü + merkezi web panosu.
**Farabi'den TAMAMEN BAĞIMSIZ** (2026-08-18 kullanıcı kararı) — Farabi'nin
`actions/` registry'sine girmez, `client/`'a bağlı değildir, kendi başına
çalışır. Farabi'nin sesli yoklaması ("derse gelmeyen öğrencilerin isimlerini
söyler misiniz?") bu sistemden habersizdir — ikisi paralel, birbirinden
bağımsız iki yoklama yolu.

## 1. Neden var, nasıl çalışır

`yoklama.py` (PyQt6, dokunmatik) her tahtada kendi başına, **ağdan tamamen
izole** çalışır — idarenin "hangi sınıfta yoklama alınmadı" sorusuna cevap
vermek için tek tek tahtaların başına gitmek gerekiyordu. `dashboard/` bu
ihtiyaçtan doğdu: tüm tahtaların durumunu tek sayfada toplar, gerektiğinde
ilgili tahtada yoklama ekranını uzaktan açar, sınıf/roster/tahta eşlemesini
web üzerinden düzenlemeye izin verir.

**Teknoloji (bilinçli tercih):** FastAPI + Jinja2 + vanilla JS (build adımı
yok, npm yok) + SQLite (WAL) + `asyncio.create_subprocess_exec` ile
doğrudan `ssh` (paramiko/APScheduler gibi yeni ağır bağımlılık yok) —
repo genelindeki "Docker yok, hafif tut" konvansiyonuna uygun.

## 2. Dizin yapısı

```
tahtayoklama/
├── yoklama.py            — tahtada çalışan PyQt6 GUI
├── pdf_disari_aktar.py   — e-Okul/MEB PDF çıktısını roster JSON'a çevirir
├── data/                 — DEV kopyası; tahtalarda ~ogretmen/tahtayoklama/data/ olarak yaşar
│   ├── roster/<sinif>.json       — sınıf listesi ({"sinif", "ogrenciler": [{"no","ad_soyad","cinsiyet"}]})
│   ├── kayitlar/<tarih>_<sinif>_ders<no>.json — yoklama kaydı
│   └── zil.json                  — ders saati çizelgesi, Farabi'nin client/config/zil.json'undan KASITLI BAĞIMSIZ kopya
└── dashboard/              — merkezi web panosu (bkz. §4)
```

## 3. `yoklama.py` — tahta deployment gerçeği

- **Kendi venv'i YOK.** Tahtalarda `Exec=/home/ogretmen/farabi/client/venv/bin/python
  /home/ogretmen/tahtayoklama/yoklama.py` — Farabi'nin client venv'i
  kullanılıyor (PyQt6 zaten kurulu olduğu için). `requirements.txt`
  (`PyQt6`, `pdfplumber`) yalnızca dev makinede anlamlı.
- **Autostart DEĞİL.** `~/Masaüstü/Yoklama.desktop` ile öğretmen elle açar.
- **Tamamen ağdan izole.** HTTP/socket/network I/O YOK. Tek durum kaynağı
  tahtanın kendi diskindeki JSON dosyaları.
- **Kayıt tahta kimliğine değil, o an seçili sınıfa göre isimlendirilir** —
  tahta↔sınıf eşlemesi değiştikçe kayıt farklı fiziksel tahtalardan gelebilir;
  hiçbir kod "tahta X = sınıf Y" eşlemesine güvenmemeli, kayıt içeriğindeki
  `sinif` alanı esas alınmalı.
- **Otomatik sessiz kayıt riski (çözülmedi, bkz. §8):** ders dönemi
  değiştiğinde önceki dersin hâli otomatik kaydedilir (`_kaydet(sessiz=True)`)
  — tahta açık bırakılıp kimse dokunmazsa "herkes var" diye gerçek olmayan
  bir kayıt oluşur, öğretmenin bilerek kaydetmesiyle ayırt edilemez.
- Pencere başlığı tam olarak `"Yoklama"`; 10 dakika kuralı ve kendi kendine
  öne gelme (`_pencereyi_one_getir`) zaten `yoklama.py` içinde var, panonun
  uzaktan başlatmasıyla çakışmaz.
- Sınıf seçme kutusu (`QComboBox`) yalnızca **uygulama açılışında**
  `data/roster/*.json` taranarak dolar — yeni senkronize edilen dosya,
  uygulama zaten açıksa görünmez, öğretmenin kapatıp yeniden açması gerekir.

## 4. `dashboard/` — merkezi web panosu

Farabi'nin `server/`'daki FastAPI'sinden (`farabi-api.service`, GPU-bağımlı)
**tamamen bağımsız**: kendi venv'i, kendi SQLite DB'si (`veri/yoklama_pano.db`),
kendi portu (8010), kendi systemd birimi (`farabi-yoklama-dashboard.service`,
`After=`/`Wants=` YOK — tam ayrık). `server/tahtalar.json`'a **geri yazma
YAPILMAZ** — pano kendi tahta/sınıf kaydını tutar.

### SQLite şeması (özet — `db.py`)

| Tablo | Amaç |
|---|---|
| `siniflar` | id, ad ('9-A', 'tahta-234'...), aktif |
| `ogrenciler` | sinif_id FK, no, ad_soyad, cinsiyet (opsiyonel) |
| `tahtalar` | ad, ip, ssh_kullanici, python_yolu, sinif_id FK (NULL=atanmamış), aktif — **yalnızca bu DB'de**, `server/tahtalar.json`'a yazılmaz |
| `yoklama_onbellek` | tarih+sinif+ders_no UNIQUE; durum (`alindi`\|`alinmadi`\|`henuz_baslamadi`\|`tahta_ulasilamaz`\|`ders_yok_o_gun`\|`tahta_atanmamis`); yok/izinli isimleri JSON; sinif alanı FK DEĞİL (kasıtlı — silinen sınıfta bile geçmiş veri okunabilir kalsın) |
| `oturumlar` | token, tek ortak şifreyle giriş (`auth.py`, scrypt hash) |

### Ana bileşenler

| Dosya | İş |
|---|---|
| `app.py` | FastAPI giriş noktası, lifespan (DB kur + polling görevi), `/`, `/giris`, `/api/durum`, `/api/yenile`, `/api/tahta/{id}/baslat` |
| `ssh_istemci.py` | `ssh`/`scp` subprocess sarmalayıcı (paramiko YOK), `komut_calistir`, `scp_gonder`, `x_ortamini_kesfet` (DISPLAY/XAUTHORITY/uid keşfi — tek kopya), `tahtanin_kayitlarini_tara`, tarih/ad allow-list doğrulama |
| `yoklayici.py` | SSH polling motoru — tüm aktif tahtaları `asyncio.gather` ile paralel tarar, `yoklama_onbellek`'e UPSERT eder |
| `zil.py` | `data/zil.json` okuma + ders-zamanlama, `Europe/Istanbul` saat dilimine sabit; `gun_adi_buyuk()` (2026-09-17 eklendi) — büyük harf Türkçe gün adı, `.upper()` DEĞİL sabit sözlük kullanır (Türkçe "İ" locale hatasından kaçınmak için) |
| `admin.py` | `/admin/tahtalar`, `/admin/siniflar`, `/admin/siniflar/{id}/ogrenciler`, `/admin/rapor` — tahta↔sınıf atama, roster düzenleme/senkron, devamsızlık raporu+CSV |
| `uzaktan_yonetim.py`, `uzaktan_baslat.py`, `tahta_kaydi.py` | Faz 6 — bkz. §5 |
| `ders_programi.py` | pano hücrelerindeki ders kısa adı etiketi (MAT, İNG, ...) |

**Polling penceresi:** Pazartesi-Cuma, ilk dersten ~20dk önce - son dersten
~20dk sonra arasında ~2 dakikada bir; pencere dışında SSH trafiği yok.

**2026-09-17 — isim değişikliği + gün etiketi:** Panonun marka adı
"Yoklama Panosu"dan **"Yoklama ve Yönetim Paneli"**ye değiştirildi (yalnızca
yoklama değil, `/admin/uzaktan` de artık aynı panonun bir parçası olduğu
için) — 7 şablonun hepsinde `<title>`/`<h1>` güncellendi
(`giris.html`/`pano.html` hariç diğerlerinde yalnızca `<title>` soneki).
Aynı oturumda `header`'ın en soluna (`<h1>`'den önce) büyük harf Türkçe gün
adı eklendi (`zil.gun_adi_buyuk()`, her üç Python dosyasında
(`app.py`/`admin.py`/`uzaktan_yonetim.py`) `templates.env.globals` üzerinden
Jinja fonksiyonu olarak kaydedildi — ~12 ayrı `TemplateResponse` çağrısına
tek tek dokunmadan). `giris.html`'e eklenmedi (o sayfa `<header>` içermeyen
ortalanmış bir giriş kartı, "sol üst" kavramı yok). **Hatırlatma:** okul
hafta sonu kapalı olduğu için `ders_programi.json`/`zil.json`/polling
penceresi zaten yalnızca Pazartesi-Cuma anlamlı — bu varsayım proje
genelinde geçerliliğini koruyor, gün etiketi widget'ı 7 günü de doğru
gösterse bile hafta sonu görünürlüğünün işlevsel bir önemi yok.

### 4.1 Sistem Durumu / Farabi Health (2026-09-25)

`/sistem-durumu` + `/api/sistem-durumu[?trend=1]` — `sistem_durumu.py`. Ölçüm
lifespan'daki tek arka plan görevinde (donanım 15 sn, HTTP/SQL/uzak yoklamalar
60 sn), API önbellekten okur; 30 dk trend bellekte (restart'ta sıfırlanır).
SALT OKUNUR — restart/komut endpoint'i YOK, olmamalı. ⚠️ Farabi'nin PostgreSQL'ini
(`metrik`, `pg_stat_*`) `psql` ile salt-okunur sorgular — servisler arası DB
paylaşımı kuralının bilinçli ikinci istisnası (bkz. kök DECISIONS.md 2026-09-25).
SMS modemine asla bağlanmaz, yalnızca Müdür PC proxy portuna TCP. Birim
`Environment`'ı API'ye konmaz (ollama'nınki proxy parolası içeriyor).
Test: `venv/bin/python -m unittest test_sistem_durumu -v`.

## 5. Uzaktan Yönetim paneli (`/admin/uzaktan`) — Windows aracının web karşılığı

Windows'ta ayrı çalışan `tahta_panel.py` (tkinter+paramiko, kullanıcının
kendi makinesindeki `TAHTA ISLERI` projesi) yerine, panoya entegre bir
bölüm: yoklama aç/kapat, web sayfası aç/chrome kapat, ekranı karart/kaldır,
duvar kağıdı değiştir — hepsi toplu (çoklu tahta seçimi). Tasarım belgesi:
`docs/superpowers/specs/2026-09-15-tahta-uzaktan-yonetim-design.md`.

**Kasıtlı olarak dışarıda bırakılan** (etapadmin+sudo gerektiren, sistem
dosyalarına dokunan işlemler — Faz 1'in "ogretmen'e doğrudan SSH, sudo yok"
modeliyle uyuşmuyor): masaüstüne dosya gönderme, oturum aç/otomatik giriş
kur-kaldır, "kapat butonunu karartmaya çevir".

**Mimari kararlar:**
- Tahta hedefleri HER ZAMAN `server/tahtalar.json`'dan (`tahta_kaydi.py`)
  çözülür — istemciden yalnızca "ad" kabul edilir, IP/komut asla.
- Ayrı bir yönetici şifresi YOK — panonun mevcut ortak öğretmen
  şifresi/oturum çerezi yeterli kabul edildi (bkz. §8, güvenlik riski).
- Hiçbir işlem sudo/root gerektirmez — Farabi'nin SSH anahtarı
  (`~/.ssh/id_ed25519_tahta`) zaten `ogretmen` hesabına doğrudan yetkili.
- X-ortamı (DISPLAY/XAUTHORITY/uid) keşfi tek yerde: `ssh_istemci.x_ortamini_kesfet()`
  — `uzaktan_baslat.py` ve `uzaktan_yonetim.py` ikisi de bunu kullanır
  (önceden iki kopyaydı, birleştirildi — bkz. `tahtaayar/CLAUDE.md`'deki
  "iki kopya senkron kalmadı" dersi).

**2026-09-17 kod denetimi sonucu (bu dosyanın önceki `eylulanaliz.md`
raporundan taşındı):** Kod, tasarım belgesiyle **birebir uyumlu** bulundu;
gerçek tahtalara karşı canlı test edildi (bkz. §6) ve **doğru çalışıyor**.
⚠️ Bu denetim statik bir kod incelemesiydi, "doğru çalışıyor" kanıtı
2026-09-15'teki eski canlı teste dayanıyordu — aynı gün ilerleyen
saatlerde kullanıcının gerçek kullanımı "duvar kağıdı" için bunu
çürüttü, bkz. madde 5 (aşağıda). Bulunan, kod hatası SAYILMAYAN ama
iyileştirilebilecek noktalar:

1. `auth.gecerli_oturum()` (dependency tarzı fonksiyon, `auth.py:81`) hiçbir
   route tarafından çağrılmıyor — ölü kod. Repodaki her route (bu dosya
   dahil) `auth.dogrula()` + elle `raise HTTPException(401,...)` desenini
   tekrarlıyor. Ya `gecerli_oturum` silinmeli ya da route'lar ona taşınmalı.
2. `/admin/uzaktan*` route'ları oturumsuz istekte çıplak 401 döndürüyor,
   ana pano (`/`) gibi `/giris`'e yönlendirmiyor (bu, `admin.py`'nin zaten
   yerleşik davranışı — yeni bir hata değil, ama tutarsız).
3. **Loglama yok:** hiçbir uzaktan yönetim eylemi (kim, ne zaman, hangi
   tahtaya, hangi eylemi yaptı) kaydedilmiyor. Ortak şifreyle giren HERKES
   fiziksel tahtaları etkileyebildiği için (bilinçli kabul edilmiş risk,
   tasarım belgesinde de yazılı) en azından basit bir log satırı eklenmesi
   önerilir.
4. Küçük verimsizlik: "Yoklama Aç" eylemi `_python_yolu_bul()` ve
   `uzaktan_baslat.baslat()` içindeki `x_ortamini_kesfet()` olmak üzere
   art arda 2 SSH round-trip yapıyor (sonuç doğru, yalnızca ~1 tur fazladan
   gecikme).
5. **BULUNDU VE DÜZELTİLDİ (2026-09-17) — "Duvar Kağıdı Değiştir" "yaptım
   ama çalışmadı" şikâyeti.** Kullanıcı panelden gerçekten bir görsel
   yükledi (9-A, bugün 08:20); `server/tahta-ssh.sh 9-A` ile canlı,
   salt-okunur SSH teşhisiyle doğrulandı: dosya diskte geçerli bir JPEG
   olarak duruyordu VE `gsettings get org.cinnamon.desktop.background
   picture-uri` bu dosyayı gösteriyordu — yani SSH/gsettings mekanizması
   BOZUK DEĞİLDİ, o seferinde fiilen çalışmıştı. Yine de kodda iki gerçek
   sorun bulundu:
   - `_duvar_kagidi_tek`'teki `ic_komut`, üç `gsettings set` çağrısını `;`
     ile zincirliyordu — bash'te `;` zincirinin çıkış kodu SADECE son
     komutundur. Asıl görünür etkiyi belirleyen ilk çağrı
     (`org.cinnamon.desktop.background`, masaüstü Cinnamon olduğu için)
     başarısız olsa bile, son sıradaki yedek `org.gnome.desktop.background`
     çağrısı başarılıysa panel yanlışlıkla "Duvar kağıdı değiştirildi."
     diyebiliyordu. **Düzeltildi:** artık yalnızca Cinnamon çağrısının
     çıkış kodu (`$CINNAMON_DURUM`) raporlanıyor, GNOME çağrısı gerçek bir
     best-effort/yedek oldu (hatası göz ardı edilir).
   - Dosya seçilip HİÇBİR tahta kutusu işaretlenmeden gönderilirse route
     sessizce "Hiçbir tahta seçilmedi." diyen tek bir satır ekliyordu —
     bu satır tam sayfa yeniden yüklendiğinde "Eylemler" bölümünün
     ÜSTÜNDE kalıyordu (kullanıcı az önce sayfanın altındaki butona
     tıklamıştı), kolayca gözden kaçıyordu. **Düzeltildi:** artık form
     JS'i gönderilmeden önce en az bir tahta seçili mi diye kontrol edip
     `alert()` ile uyarıyor (tüm `.uz-eylem-form`'lar için, yalnızca duvar
     kağıdı değil); sonuç listesi de sayfa yüklenince otomatik olarak
     görünüme kaydırılıyor (`scrollIntoView`).
   - **Ders:** "kod denetiminde bulunmadı" iki günlük statik bir gözlemdi;
     gerçek kullanıcı denemesi + canlı SSH teşhisi farklı, daha güvenilir
     bir kanıt kaynağı — şüpheli bir "çalışmıyor" bildirimi geldiğinde
     önce statik koda değil, canlı tahtaya bakılmalı (bkz. kök
     `CLAUDE.md`'nin log okuma ilkesiyle aynı prensip).

### 5.1 Canlı Ekran Görüntüsü (Screenshot) — Yeni Sekmede Görüntüleme (2026-09-21)

Kullanıcı isteği: `http://farabi.local:8010/admin/uzaktan` bölümünde tablo düzenini bozmayan bir screenshot butonu yer alması, tıklandığında anlık ekran görüntüsünün doğrudan yeni sekmede tam boy açılması (`target="_blank"`).

**Mimari ve Gerçekleştirim:**
- **Backend Route:** `GET /admin/uzaktan/ekran-goruntusu/{tahta_adi}?ham=1` (`uzaktan_yonetim.py`):
  - Oturum zorunlu (`auth.dogrula()`).
  - Tahta adı `server/tahtalar.json` üzerinden doğrulanır.
  - SSH üzerinden ekran yakalama: Farklı Linux sürümlerini desteklemek için çoklu araç fallback zinciri kullanılır:
    1. Birincil: `import -window root -resize 1280x -quality 70 jpg:-` (ImageMagick, ~0.4s — standart tahtalarda mevcuttur).
    2. Yedek: `gnome-screenshot --file=/tmp/tahta_ss.png && cat /tmp/tahta_ss.png && rm -f /tmp/tahta_ss.png` (`fenlab` gibi `import` olmayan tahtalar için — *not: eski GNOME sürümlerinde `-f "$F"` argüman hatası verdiği için `--file=...` parametresi zorunludur*).
  - Sunucu tarafı optimizasyon: Pillow ile görsel kontrol edilir; genişlik > 1280px ise oran korunarak küçültülür ve %75 kalitede JPEG olarak sıkıştırılır (~20–30 KB).
  - İkili JPEG Akışı (`ham=1`):
    - Başarılı durumda `Response(content=jpeg_bytes, media_type="image/jpeg", headers={"Cache-Control": "no-cache, ..."})` döner; tarayıcı yerel görsel görüntüleyicisinde tam ekran, yakınlaştırılabilir (zoom) olarak açar.
    - Tahta çevrimdışı veya hata durumunda şık bir HTML hata sayfası döner ("Ekran Görüntüsü Alınamadı", "Tekrar Dene", "Kapat" butonlarıyla).
    - API / otomasyon istekleri için varsayılan (`ham=0`) JSON yanıt formatı korunmuştur.
- **Frontend & Tablo Düzeni:**
  - `uzaktan_yonetim.html`: Tabloya son sütun olarak `<th>Screenshot</th>` eklendi.
  - Satır yüksekliğini veya sütun genişliklerini kesinlikle bozmayan, `.pill` ile aynı yükseklik ve font boyutuna sahip `.ss-link-btn` tasarlandı (`target="_blank"`, rel="noopener noreferrer").
  - Tablo içine görsel veya thumbnail gömülmez; satır kayması, taşma veya modal pencere karmaşası yoktur. Ulaşılamayan tahtalar için sade bir `—` işareti gösterilir.
- **Testler:** `test_uzaktan_ekran.py` (9/9 test): JSON yanıtı, binary `?ham=1` akışı, hata anında HTML yanıtı, `import` -> `gnome-screenshot` fallback mekanizması, 401 yetkisiz erişim, 404 bilinmeyen tahta ve çevrimdışı tahta durumları test edilmiştir.

## 6. Tahta envanteri ve canlı durum (2026-09-17'de doğrulandı)

`server/tahtalar.json` tek doğru kaynak. O gün yapılan canlı bağlantı testi
(`uzaktan_yonetim.tum_durumlar()` gerçek SSH ile çalıştırılarak, ~06:10 TR):

| Tahta | IP | O gün ulaşılabilir mi | Not |
|---|---|---|---|
| 9-A | .245 | ✗ (No route to host) | 7 aktif sınıftan biri; sabah erken saatte kapalı olması muhtemel, arıza kanıtı değil |
| 9-B | .239 | ✓ | normal |
| 10-A | .242 | ✓ | normal |
| 11-A | .228 | ✓ | normal |
| 11-B | .233 | ✓ | normal |
| 12-A | ~~.231~~ **.226** | ✓ | ⚠️ 2026-09-22'de IP değişti (DHCP kirası), aynı fiziksel tahta — bkz. aşağıdaki not |
| 12-B | .240 | ✓ | normal |
| tahta-234 | .234 | ✗ | sınıf değil (bkz. §7) |
| tahta-235 | .235 | ✗ | sınıf değil (bkz. §7) |
| tahta-236 | .236 | ✗ | eski/boşa çıkmış 11-A kaydı (bkz. §7) |
| fenlab (eski tahta-244) | .244 | ✓ | ortak kullanım alanı (fen laboratuvarı), sınıflara sabit değil — Farabi+tahtayoklama artık kurulu, bkz. §7 |

> ⚠️ **2026-09-22 — 12-A'nın IP'si `.231` → `.226` oldu ve yoklamayı canlı
> olarak BOZDU.** DHCP kirası değişti; aynı fiziksel tahta (MAC
> `00:09:df:83:ff:cc`, hostname `vestel12a` ile doğrulandı). **Etkisi
> `yoklama_onbellek`'te ölçüldü:** 12-A'nın 1-3. ders yoklaması `alindi`,
> 4-8. ders `tahta_ulasilamaz` — `.231`'in son heartbeat'i 10:30, yani tam
> 3. dersin bitişi. Pano tahtayı o anda kaybetti ve günün yarısı yoklamasız
> kaldı. Düzeltildi: `server/tahtalar.json` + dashboard `tahtalar` tablosu
> (`ip` ve `mac`) güncellendi, uzaktan ekran görüntüsü yeni IP'de
> doğrulandı. `yoklayici.bir_tur_calistir` tahta listesini HER turda
> DB'den okuduğu için servis restart'ı GEREKMEDİ.
>
> **Bu, §7'deki "otomatik MAC→IP çözümleme henüz YOK, IP değişirse elle
> güncellenmeli" açık ucunun gerçekleşmiş hâli.** Sessizce oldu — hiçbir
> uyarı üretilmedi, yalnızca `tahta_ulasilamaz` satırları birikti. Pano
> "bir tahta uzun süre ulaşılamazken aynı MAC başka bir IP'de görünüyor"
> durumunu tespit edip uyarabilseydi aynı gün yakalanırdı; bu hâlâ açık
> bir iyileştirme.

**2026-09-17 ek düzeltme (aynı gün, doküman birleştirmesi sırasında
bulundu):** Bu tablodaki `.233`/`.239`/`.242` satırları `server/tahtalar.json`'dan
alındığı için doğruydu, ama `network.txt` (insan-okunur ikinci referans)
bu üç IP'nin sınıf etiketlerini birbirine KAYDIRMIŞ halde tutuyordu (10-A/
11-B/9-B yerine 9-B/10-A/11-B gibi — IP/MAC doğruydu, isim yanlıştı). Her
üç tahtanın kendi `data/roster/*.json` ve `client/config/api_keys.json`
(`derslik` alanı) dosyaları canlı SSH ile okunarak doğrulandı:
`server/tahtalar.json` DOĞRUYDU, `network.txt` YANLIŞTI — düzeltildi.
**Ders:** iki kayıt dosyası (biri "resmi" JSON, biri "insan-okunur ek
referans") olan her yerde, ikisi arasında sessizce sapma olabilir — şüphe
varsa asıl kaynağa (`server/tahtalar.json`) ve mümkünse canlı doğrulamaya
güvenin, ikincil referans dosyasına değil.

`tahtaayar/tahta_fix_uygula.py --sadece-kontrol` ile aynı gün taranan
OS-düzeyi güç/uyku düzeltmeleri: **7 aktif sınıf tahtasının 7'sinde de**
dört düzeltme de uygulanmış durumda (regresyon yok). `fenlab`'ta o an
(kontrol anında) üç düzeltme hiç uygulanmamıştı — aynı gün, kullanıcı
talebiyle `--tahta fenlab` ile uygulandı, artık **8/8 tahta aynı ayarda**
(bkz. §7'deki tam kurulum notu).

## 7. Tahta↔sınıf ataması — kalıcı gerçekler ve açık uçlar

- **`/admin/tahtalar`'daki atama SADECE dashboard'un kendi SQLite'ını
  değiştirir, tahtaya HİÇBİR ŞEY göndermez** — tahtaya gerçekten dosya
  yazan TEK yol, atama+senkronun tek adımda birleştiği "Yükle" butonu
  (`admin.py::_tahtaya_roster_gonder`, her yüklemede eski roster
  dosyalarını da otomatik siler). Eski "takas" route'u ve sürükle-bırak
  özelliği kullanıcı isteğiyle tamamen kaldırıldı (kafa karıştırıcı
  bulunmuştu).
- `senkronize` her zaman HTTP 200 döner (SSH gerçekten başarısız olsa
  bile) — "200 OK" tahtaya ulaştığının kanıtı DEĞİL, doğrulama SSH ile
  dosyayı geri okuyarak yapılmalı.
- **`tahta-234`/`tahta-235`/`fenlab` sınıf DEĞİL** (`fenlab` = eski
  `tahta-244`, 2026-09-17'de kullanıcı teyidiyle "fen laboratuvarı" olarak
  tanımlandı ve yeniden adlandırıldı — bkz. aşağıdaki not; `tahta-234`/
  `tahta-235`'in hangisinin kütüphane, hangisinin spor odası olduğu hâlâ
  netleşmedi). Bu 3 yerde yoklama alınmayacak diye Faz 6 (lab1/lab2/lab3
  kurulumu) kullanıcı isteğiyle iptal/beklemede kaldı — `siniflar`
  tablosuna hiç eklenmediler, `tahta_atanmamis` durumunda kalmaya devam
  ediyorlar.
  - **`fenlab` yeniden adlandırması (2026-09-17):** Makine hostname'i
    `hostnamectl set-hostname fenlab` + `/etc/hosts` güncellemesiyle
    "etap"tan "fenlab"a değiştirildi (etapadmin+sudo). `server/tahtalar.json`'da
    `"tahta-244"` anahtarı `"fenlab"` oldu ve `"mac": "00:09:df:8c:32:8a"`
    alanı eklendi — kullanıcı isteğiyle: **IP DHCP ile değişebilir, kimlik
    doğrulaması için MAC esas alınmalı** (otomatik MAC→IP çözümleme henüz
    YOK — IP değişirse `server/tahtalar.json`'daki `ip` alanı elle
    güncellenmeli). Dashboard SQLite'ındaki (`tahtalar` tablosu, id=10)
    `ad` alanı da `"fenlab"`a güncellendi.
  - ✅ **Tam kurulum (2026-09-17, aynı gün, kullanıcı talebiyle):** `fenlab`
    diğer 7 aktif tahtayla birebir aynı duruma getirildi:
    - `tahtaayar/tahta_fix_uygula.py --tahta fenlab` çalıştırıldı — güç
      düğmesi/uzun basış/uyku hedefleri maskeleme fix'lerinin 3'ü de
      uygulandı ve doğrulandı (yalnızca `cinnamon_guc_tusu_yoksay` zaten
      vardı). Artık 7 aktif tahta + fenlab, 8/8 aynı OS-düzeyi ayarda.
    - Farabi client kuruldu (`server/farabi-kurulum.sh fenlab
      http://192.168.23.252:8000 <yeni tahta_anahtari>`) — kurulum sırasında
      script'in [0/7] ön koşul kontrolü gerçek bir eksiği KAÇIRDIĞI ortaya
      çıktı: `python3 -c "import venv"` başarılı dönüyor ama Debian'da asıl
      gerekli olan `ensurepip` ayrı pakette (`python3.11-venv`) —
      script GÜNCELLENDİ (artık `import ensurepip` kontrol ediyor, eksikse
      Python sürümüne göre doğru paket adını öneriyor). `libportaudio2`/
      `libxcb-cursor0`/`git`/`wmctrl` da eksikti, etapadmin+sudo ile kuruldu.
      Kurulum sonrası `import main` temiz, heartbeat `{"status":"ok"}`
      döndü — `server/config/api_keys.json`'daki `board_keys` içine
      `fenlab` için yeni bir anahtar eklendi. `gemini_api_keys` diğer
      kurulumlarla aynı ilkeyle BOŞ bırakıldı (kullanıcı elle girmeli).
    - tahtayoklama kuruldu — 9-A dışındaki diğer tahtalarla aynı desen:
      kendi `~/tahtayoklama/venv` (PyQt6+pdfplumber pip ile), `yoklama.py` +
      `data/zil.json` kopyalandı, `~/Masaüstü/YoklamaFenLab.desktop`
      oluşturuldu. **Fark:** fenlab tek bir sınıfa ait olmadığı
      (ortak/paylaşılan kullanım alanı, dersler mekan değişikliğiyle farklı
      sınıflar tarafından kullanılabiliyor) için `data/roster/`'a TEK bir
      sınıf değil, **mevcut 7 sınıfın hepsinin roster'ı** kopyalandı
      (9-A/9-B/10-A/11-A/11-B/12-A/12-B) — `yoklama.py`'nin combo box'ı
      açılışta `data/roster/*.json`'ı taradığı için (bkz. §3) öğretmen artık
      hangi sınıf o an oradaysa onu seçebiliyor, canlı doğrulandı (7/7
      roster dosyası görüldü). Dashboard tarafında hiçbir değişiklik
      GEREKMEDİ — mimari zaten kayıt içeriğindeki `sinif` alanını esas
      aldığı için (bkz. §3, "kayıt tahta kimliğine değil sınıfa göre") bu
      paylaşımlı kullanım otomatik olarak destekleniyor; `fenlab`'ın
      dashboard'da `sinif_id=NULL`/`tahta_atanmamis` kalması BİLEREK
      değiştirilmedi (tek sınıfa sabitlemek yanlış olurdu).
    - **Yapılmadı (kullanıcı elle tamamlamalı, diğer kurulumlarla aynı
      ilke):** `gemini_api_keys` boş, fiziksel/görsel son kabul testi
      yapılmadı (kural gereği kullanıcıya ait).
- **`tahta-236`**: önceden "11-A" etiketiyle kayıtlıydı, gerçek 11-A'nın
  `192.168.23.228`'de bulunmasıyla (2026-08-24) boşa çıktı — dashboard
  DB'sinde `sinif_id=NULL` yapıldı ama satır SİLİNMEDİ, `server/tahtalar.json`'da
  da ayrı satır olarak korunuyor (SSH erişimi gerekebilir ihtimaline karşı).

## 8. Bilinen riskler / açık işler (öncelik sırasıyla)

1. **Commit edilmemiş değişiklikler, 2 gündür bekliyor (kaybolma riski).**
   `dashboard/static/pano.css` + 7 `templates/*.html` (koyu/yumuşak tema
   sistemi) değiştirilmiş; `static/tema.js` ve
   `dashboard/yedek/2026-09-15_tema_oncesi/` (değişiklik öncesi elle
   alınmış yedek) izlenmiyor. Değişiklik tutarlı görünüyor (tüm ilgili
   şablonlarda `tema.js`/`data-tema` kullanımı var) — kullanıcı onayı ile
   commit edilmesi önerilir.
2. ~~`fenlab` güç-düğmesi açık sorusu~~ — **ÇÖZÜLDÜ (2026-09-17)**, bkz. §7 "Tam kurulum" notu.
3. **Uzaktan Yönetim'de loglama yok, ayrı bir yönetici rolü yok** — bkz. §5
   madde 3 (bilinçli kabul edilmiş risk, ama izlenebilirlik hiç yok).
4. **Otomatik sessiz kayıt ayrımı (Faz 7, hiç başlanmadı)** — `yoklama.py`'nin
   dönem geçişindeki sessiz otomatik kaydı ile öğretmenin bilerek
   kaydetmesi ayırt edilemiyor; çözüm `yoklama.py`'ye (canlı, kullanımda
   bir dosyaya) `elle_kaydedildi: bool` alanı eklemeyi gerektiriyor — ayrı
   bir onay/plan konusu, kasıtlı olarak ertelendi.
5. **Harici Windows araçlarıyla ilişki netleşmedi** — bkz. §9.
6. Küçük iyileştirmeler: `auth.gecerli_oturum` ölü kodu, `/admin/uzaktan`
   401→`/giris` tutarsızlığı, "Yoklama Aç"taki fazladan SSH turu (§5).

## 9. Harici tahta yönetim programları (kullanıcının Windows PC'si)

Bu depoya DAHİL DEĞİL, ayrı bir makinede yaşıyor ama aynı 11 tahtayı
uzaktan yönetiyor:

- `C:\Users\exa\Desktop\TAHTA ISLERI\tahta_panel.py`
- `C:\Users\exa\Desktop\TAHTA ISLERI\tahta_ssh.py`

Bu oturumdan dosya içeriği OKUNAMADI (uzak/erişilemez yol). **Muhtemel
kimlik:** 9-B/11-B/12-A'nın SSH loglarında `192.168.23.243`'ten gelen,
~30 saniyede bir tekrar eden `etapadmin` girişleri — her girişte `pkexec
.../ETAKisitActivator.py --disable-websites-restriction` çalıştırılıyor.
Bu IP `server/tahtalar.json`'daki envanterde YOK — ayrı bir yönetici
istasyonu. **TEYİT EDİLMEDİ**, yalnızca zaman/davranış örtüşmesiyle en
olası açıklama. `/admin/uzaktan` (§5) bu iki programın işlevinin bir
kısmını (muhtemelen tamamını değil) web'e taşımış durumda — iki aracın
tam olarak nerede çakıştığı hâlâ netleşmedi.

## 10. Kurallar (kök `/home/ata/farabi/CLAUDE.md`'nin 1/3/4/6/8 maddelerine paralel)

1. Tahtalarda ÇALIŞAN `yoklama.py`'ye dokunmadan önce iki kez düşün —
   canlı, kullanımda bir sistem; geriye dönük uyumluluğu koru.
2. Tek seferde tek modül değiştir.
3. Değiştirmeden önce ilgili dosyayı oku — özellikle `yoklama.py`'nin veri
   şeması (roster/kayıt JSON) `dashboard/`'un varsaydığı şemayla birebir
   uyuşmalı.
4. Docker yok, systemd servisleri.
5. Yeni ağır bağımlılık (paramiko, APScheduler, Redis, vb.) eklemeden önce
   onay iste.
6. `dashboard/config/gizli.json` asla commit edilmez.
7. Servis restart'ları yalnızca ders saatleri (08:00-17:00 TR) DIŞINDA.
8. Son kabul testi (fiziksel/görsel doğrulama) HER ZAMAN kullanıcı
   tarafından yapılır, otomatikleştirilmez.

## 11. `dashboard/scripts/` — bakım/kurulum araçları

Tek seferlik, elle (ya da bir ajan tarafından elle) tetiklenen araçlar,
hiçbiri crontab/systemd timer'a bağlı değil:

- **`ders_programi_yukle.py`** — `mudur/siniflar.pdf`'i (aSc k12 çıktısı)
  `tahtayoklama/data/ders_programi.json`'a çevirir (pano etiketi için).
  `mudur/ders_programi_yukle.py`'nin PDF-çözme mantığının taşınmış hâli ama
  farklı iş yapıyor: mudur'unki Farabi client'ına SSH ile dağıtım da
  yapıyor, bu YAPMAZ. **KISALTMALAR sözlüğü mudur'unkiyle SENKRON
  tutulmalı** (iki ayrı dosya, tek doğru kaynak yok — geçmişte bunun
  senkron dışı kalması "seçmeli X" ders adlarının RAG'de eşleşmemesine
  yol açmıştı, bkz. kök `sorunlar.md`/`DECISIONS.md`).
- **`zil_yukle.py`** — kaynağı `mudur/giris cikis saatleri.jpg`, elle okunup
  `VARSAYILAN_SAATLER` sabitine gömülü. `--no-dagit` verilmedikçe
  `server/tahtalar.json`'daki her tahtaya SCP ile yazar.
- `tahta_fix_uygula.py` buradan **taşındı** → `tahtaayar/tahta_fix_uygula.py`
  (OS/oturum provizyonu `client/` ve `tahtayoklama/` ortak katmanı olduğu
  için üst düzey klasöre alındı, kopya bırakılmadı).


## Frontend / Dashboard Tasarım Standartları

*(2026-09-25'te kök `CLAUDE.md`'den buraya taşındı; kapsamı yalnızca bu
alt proje. Yollar `dashboard/`'a görelidir.)*

Rol: **Senior Product Designer & Frontend Architect.** Geçerli olduğu yer
**yalnızca `tahtayoklama/dashboard/templates/` + `static/`**. Client'ın
PyQt6 arayüzü (`client/ui.py`) bu bölümün kapsamı DIŞINDA — Qt widget'ına
web tasarım kuralı uygulanmaz.

**Görsel kimlik zaten kurulu, dondurulmuş sayılır.** Tasarım sistemi
`static/pano.css` başındaki Türkçe adlı CSS değişkenleri (`--renk-*`,
`--yaricap*`, `--yazi-tipi`) ve üç tema: `klasik` (varsayılan), `yumusak`,
`koyu` — `data-tema` ile. frontend-design becerisi "sıfırdan ayırt edici
kimlik kur" modunda çalıştırılmaz; disiplini (kısıtlılık, erişilebilirlik,
klavye odağı, arayüz metni) mevcut token sistemi İÇİNDE uygulanır.
- Ham hex renk yazılmaz, var olan değişken kullanılır.
- Yeni bir değişken gerekiyorsa ÜÇ tema bloğunda da tanımlanır.
- Arayüz metni Türkçe, cümle düzeninde (ALL-CAPS etiket yok).

**Hiyerarşi ve taranabilirlik.** Sayfa başı sırası: Başlık > birincil
eylem (CTA) > kritik metrikler (KPI) > tablo/grafik. Veri kartları, durum
rozetleri ve kritik metrikler ilk bakışta okunmalı — bilgi yoğunluğu
öğretmenin 5 saniyede "hangi sınıfta yoklama eksik" sorusunu
cevaplayabileceği kadar olmalı.

**Semantik durum renkleri** — `pano.css`'teki eşleşme zaten bu, yenisi
uydurulmaz: başarılı `--renk-yesil`, uyarı `--renk-amber`, kritik/hata
`--renk-kirmizi`, nötr/bilgi `--renk-gri`. Zemin karşılıkları
`--renk-*-zemin`. Varsayılan bootstrap görünümünden ve tek düze gri
paletten kaçın.

**Mikro etkileşimler ve durumlar.** Buton hover, tablo satır vurgusu.
Geçiş süresi `pano.css`'te zaten yerleşik: **0.15 s** (renk/zemin) ve
**0.12 s** (transform/gölge) — yeni süre uydurma, bu ikisini kullan.
Veri yüklenirken `skeleton` iskelet, veri yokken düzgün bir `empty-state`
(ne olduğunu ve ne yapılacağını söyleyen, özür dilemeyen metin)
tasarlanır — boş tablo bırakılmaz.
⚠️ `pano.css`'te **`prefers-reduced-motion` bloğu YOK** (2026-09-20'de
doğrulandı). Pulse/skeleton gibi kendiliğinden dönen bir animasyon
eklenirken bu medya sorgusu da eklenmeli — sürekli animasyon tek
erişilebilirlik açığımız.

**İkonlar — sprite zaten var, CDN yok.** İkon alanları açıkça
tanımlanmalı; ikonsuz veri paneli kabul edilmez. Ama mekanizma kurulu:
`templates/_ikon_sprite.html` içinde **27 adet satır içi `<symbol>`** (2026-09-25 sayımı),
zaten **Lucide çizim konvansiyonunda** (24×24 viewBox,
`stroke="currentColor"`, `stroke-width="2"`, yuvarlak uçlar). Kullanım:
`<svg class="ikon"><use href="#ik-<ad>"/></svg>`. Boyut sınıfları hazır:
`.ikon` (1.05em, metinle birlikte ölçeklenir), `.ikon-kucuk` (0.85em),
`.ikon-buyuk` (2.4rem), `.ikon-disa` (satır sonuna iter).
- Eksik ikon gerekiyorsa Lucide/Tabler'ın SVG kaynağından **yeni bir
  `<symbol>` olarak sprite'a eklenir** — `ik-` önekiyle, Türkçe adla.
- **`lucide-react` veya CDN script'i KULLANILMAZ**: bu stack Jinja2 +
  vanilla CSS, React yok; CDN okul ağında (SSL-inceleme) ve eski
  i3-2330M tahtalarda sessizce boş ikon bırakır. Satır içi sprite
  sıfır istek atar ve çevrimdışı çalışır — kazanan desen bu.
- İkon coverage'ı bugün ince olan sayfalar: `uzaktan_yonetim.html`,
  `admin_tahtalar.html`, `admin_sinif_ogrenciler.html` (1'er ikon),
  `admin_siniflar.html`, `admin_rapor.html` (2'şer). Bu sayfalara
  dokunulduğunda ikon eklemek serbest, ayrı onay gerektirmez.

**Kompakt / pro yoğunluk.** Hedef "profesyonel operasyon paneli"
hissiyatı — geniş boşluk yok. **Dashboard bugün ZATEN bu yoğunlukta**
(2026-09-20'de ölçüldü): `gap` 0.3–0.6rem, `padding` 0.45×0.9rem
civarı, gövde metni 0.78–0.88rem. Tailwind'in `p-8`/`gap-8` (2rem)
sorunu burada YOK — yani "daha kompakt yap" diye mevcut değerleri
küçültme, referans bunlar.
⚠️ Gerçek eksik şu: **boşluk token'ı hiç yok** (`--bosluk-*` aranıp
bulunamadı) ve **10 farklı yakın punto** serpiştirilmiş (0.78 / 0.8 /
0.82 / 0.85 / 0.86 / 0.88rem — ölçek değil, gürültü). Yeni CSS yazarken
bu listeden var olan bir değeri seç, 0.83 gibi yeni bir ara değer
üretme. Bunu gerçek bir ölçeğe (`--bosluk-1/2/3`, `--punto-*`)
indirgemek istenen bir iyileştirme ama `pano.css` üretimde — Kural 6
gereği ayrıca onay ister, kendiliğinden yapılmaz.

**Yerel/edge dashboard ergonomisi.** Servis/donanım durumu için anlık
"canlı" göstergeler (yeşil pulse nokta) kullanılır — tahta çevrimiçi mi,
yoklama açık mı gibi. Tablolarda pagination yerine akıcı dikey kaydırma
ve kompakt filtre alanı tercih edilir.

> ⚠️ **Kütüphane kuralı — Kural 8 burada da geçerli.** Dashboard bugün
> SIFIR dış bağımlılıkla çalışıyor: CDN yok, Tailwind yok, grafik
> kütüphanesi yok, ikon paketi yok (ikonlar `templates/_ikon_sprite.html`
> içinde satır içi SVG sprite). Tailwind / Lucide / Chart.js / ApexCharts
> / Tremor önerilebilir ama **onay almadan eklenmez** — üstelik okul
> ağında SSL-inceleme (MEB-CERT-TTVPN) var ve tahtalar eski i3-2330M,
> yani CDN'e bağlı bir çözüm derste sessizce boş ekran verebilir. Yeni
> kütüphane gerçekten gerekiyorsa: yerel olarak `static/`'e indirilir,
> CDN'den çağrılmaz.

---

*Bu dosya `/home/ata/farabi/tahtayoklama/CLAUDE.md` olarak tutulur, dizine
`cd` edildiğinde otomatik yüklenir. Kök `/home/ata/farabi/DECISIONS.md`
kronolojik karar günlüğünü (neden X yapıldı, Y neden reddedildi) ayrı ve
bozulmadan tutmaya devam ediyor — bu dosya onun yerine geçmez, yalnızca
"şu an ne doğru" sorusuna tek bir yerden cevap verir.*
