# Yoklama Merkezi Web Panosu — Uygulama Planı

## Context

`yoklama.py` (PyQt6, dokunmatik) 7 tahtaya kurulu ve öğretmenler tarafından
fiilen kullanılıyor (9-A'da bugüne ait 5 dersin kaydı canlı olarak
doğrulandı). Ama her tahta kendi başına, ağdan tamamen izole çalışıyor —
idarenin "hangi sınıfta yoklama alınmadı" sorusuna cevap vermek için tek tek
tahtaların başına gitmek gerekiyor. Bu proje, tüm tahtaların yoklama
durumunu tek bir web sayfasında toplayan, gerektiğinde ilgili tahtada
yoklama ekranını uzaktan başlatabilen hafif bir panoya duyulan ihtiyaçtan
doğdu. Okul yeni açıldığı için sınıf↔tahta eşlemesi ve öğrenci listeleri ilk
hafta boyunca değişebilir — bu yüzden pano salt-okunur bir izleme aracı
değil, bu eşlemeleri ve listeleri web üzerinden düzenleyebilen bir araç
olarak tasarlandı.

**Doğrulanmış zemin** (bu oturumda canlı SSH ile kontrol edildi, varsayım
değil):
- `yoklama.py` tamamen ağdan izole — HTTP/socket yok, tek durum kaynağı
  tahtanın kendi diskindeki JSON dosyaları
  (`~ogretmen/tahtayoklama/data/{roster,kayitlar}/`).
- Tahtada otomatik açılmıyor — `~/Masaüstü/Yoklama.desktop` ile elle
  açılıyor (`Exec=/home/ogretmen/farabi/client/venv/bin/python
  /home/ogretmen/tahtayoklama/yoklama.py`).
- 10 tahtadan 7'si (9-A, 9-B, 10-A, 11-A, 11-B, 12-A, 12-B) çalışıyor; 3'ü
  (192.168.23.234/.235/.244, `tahtalar.json`'da `tahta-234/235/244` adıyla
  kayıtlı) `tahtayoklama` klasörü hiç olmadığı için sıfırdan kurulacak —
  kullanıcı bunlara `lab1`/`lab2`/`lab3` adını ve tek kişilik "Ali Deneme"
  test rosterını istiyor.
- SSH: `server/tahta-ssh.sh` + `server/tahtalar.json` zaten çalışıyor
  (anahtar: `~/.ssh/id_ed25519_tahta`, kullanıcı: `ogretmen`).
- **Kritik düzeltme**: yoklama kaydının dosya adı VE içeriğindeki `sinif`
  alanı, o anda tahtadaki combo box'ın seçimine göre belirleniyor — tahta
  kimliğiyle ilişkisi yok. Sınıf↔tahta eşlemesi ilk hafta değişeceği için,
  pano "tahta X = sınıf Y" varsayımıyla değil, her tahtanın o günkü TÜM
  kayıt dosyalarını tarayıp içindeki `sinif` alanına göre eşleştirerek
  çalışmalı (aşağıda Faz 2).
- **Açık risk** (kullanıcıya bilgi amaçlı, plana dahil değil): dönem
  değişiminde otomatik sessiz kayıt (`_kaydet(sessiz=True)`) var — tahta
  açık bırakılıp kimse dokunmazsa "herkes var" diye kayıt oluşur, pano bunu
  gerçek yoklamadan ayıramaz. Çözümü `yoklama.py`'ye dokunmayı gerektirir,
  bu planın kapsamı dışında — ayrı bir karar/plan konusu.

**Yeni servis, Farabi'den bağımsız**: `server/`'daki mevcut FastAPI
(`farabi-api.service`, GPU-bağımlı, ağır ML bağımlılıkları) ile
karıştırılmayacak. Yeni pano `tahtayoklama/dashboard/` altında, kendi
venv'i, kendi SQLite DB'si, kendi systemd birimi, kendi portu (8010) ile
tamamen ayrı bir servis. `server/tahtalar.json`'a geri yazma YAPILMAYACAK —
pano kendi tahta/sınıf kaydını tutar, tek seferlik tohumlama dışında
Farabi'nin dosyalarına dokunmaz.

**Teknoloji**: FastAPI + Jinja2 + vanilla JS (build adımı yok, npm yok) +
SQLite (WAL modu) + `asyncio.create_subprocess_exec` ile doğrudan `ssh`
(paramiko/APScheduler gibi yeni ağır bağımlılık yok) — repo genelindeki
"Docker yok, hafif tut" konvansiyonuna uygun.

Adım adım, doğrulanabilir 6 faz halinde ilerlenecek (+ isteğe bağlı Faz 7).

---

## Faz 0 — `tahtayoklama/CLAUDE.md`

Yeni dosya: `/home/ata/farabi/tahtayoklama/CLAUDE.md` (bugün yok — repodaki
tek CLAUDE.md kökte ve tamamen ilgisiz "Farabi" projesini anlatıyor).

İçerik: proje tanımı ("Farabi'den bağımsız", `yoklama.py`'nin kendi
docstring'ine referans), dizin ağacı (`yoklama.py`, `pdf_disari_aktar.py`,
`data/`, yeni `dashboard/`), tahtadaki gerçek deployment (kendi venv'i yok,
Farabi client venv'i kullanılıyor, autostart değil), veri şeması özeti,
dashboard'un ayrı servis olduğu notu, kök CLAUDE.md'nin 1/3/4/6/8 kurallarına
paralel kurallar.

**Doğrulama**: dosya var, `cd tahtayoklama` içeride çalışırken otomatik
yükleniyor.

---

## Faz 1 — Pano iskeleti, DB şeması, giriş (auth)

Yeni dizin: `/home/ata/farabi/tahtayoklama/dashboard/`

```
dashboard/
├── app.py                  — FastAPI app, route bağlama, lifespan (DB + poller başlatma)
├── db.py                   — sqlite3 bağlantı yardımcıları (WAL), şema oluşturma
├── modeller.py             — pydantic/dataclass şekilleri
├── auth.py                 — giriş/oturum çerezi
├── ssh_istemci.py          — Faz 2'de doldurulur
├── yoklayici.py            — Faz 2'de doldurulur (poller döngüsü)
├── zil.py                  — data/zil.json okuma + ders-zamanlama (yoklama.py'deki
│                              _simdiki_ders/_ders_baslangicindan_gecen_dk'nin server-side
│                              kopyası — PyQt6 bağımlılığı almamak için kasıtlı tekrar)
├── scripts/
│   ├── ilk_yukleme.py       — tek seferlik DB tohumlama
│   └── sifre_belirle.py     — giriş şifresini belirleyip hash'ini gizli.json'a yazar
├── config/
│   ├── gizli.example.json   — {"sifre_hash": "..."} şablonu, committed
│   └── gizli.json           — gerçek hash, GITIGNORE'LU
├── templates/
│   ├── giris.html
│   ├── pano.html
│   ├── admin_tahtalar.html
│   └── admin_sinif_ogrenciler.html
├── static/pano.css
├── requirements.txt          — fastapi, uvicorn[standard], jinja2, python-multipart
└── veri/yoklama_pano.db      — GITIGNORE'LU
```

### SQLite şeması (`db.py`)

```sql
CREATE TABLE siniflar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad TEXT NOT NULL UNIQUE,              -- '9-A', 'lab1', ...
    aktif INTEGER NOT NULL DEFAULT 1,
    guncelleme_zamani TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE ogrenciler (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sinif_id INTEGER NOT NULL REFERENCES siniflar(id) ON DELETE CASCADE,
    no INTEGER NOT NULL,
    ad_soyad TEXT NOT NULL,
    cinsiyet TEXT,                        -- opsiyonel
    aktif INTEGER NOT NULL DEFAULT 1,
    UNIQUE(sinif_id, no)
);

CREATE TABLE tahtalar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad TEXT NOT NULL UNIQUE,              -- yalnızca bu DB'de; server/tahtalar.json'a YAZILMAZ
    ip TEXT NOT NULL,
    mac TEXT,
    ssh_kullanici TEXT NOT NULL DEFAULT 'ogretmen',
    sinif_id INTEGER REFERENCES siniflar(id) ON DELETE SET NULL,  -- NULL = atanmamış
    aktif INTEGER NOT NULL DEFAULT 1,
    guncelleme_zamani TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE yoklama_onbellek (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarih TEXT NOT NULL,
    sinif TEXT NOT NULL,                  -- kayıttaki ham 'sinif' string'i (FK değil, kasıtlı —
                                           -- silinen/yeniden adlandırılan sınıflarda bile geçmiş
                                           -- veri okunabilir kalsın)
    ders_no INTEGER NOT NULL,
    durum TEXT NOT NULL,                  -- alindi | alinmadi | henuz_baslamadi |
                                           -- tahta_ulasilamaz | ders_yok_o_gun | tahta_atanmamis
    yok_isimleri TEXT,                    -- JSON array, yalnızca durum='alindi'
    izinli_isimleri TEXT,                 -- JSON array
    kaynak_tahta TEXT,                    -- kaydın fiilen geldiği tahta (teşhis için)
    kaydedilme_saati TEXT,
    guncelleme_zamani TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(tarih, sinif, ders_no)
);

CREATE TABLE oturumlar (
    token TEXT PRIMARY KEY,
    olusturma_zamani TEXT NOT NULL DEFAULT (datetime('now')),
    son_gorulme TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Auth

Tek ortak şifre. `scripts/sifre_belirle.py` şifreyi sorup hash'ini
`config/gizli.json`'a yazar. `POST /giris` → `hmac.compare_digest` ile
kontrol → başarılıysa `secrets.token_urlsafe(32)` oturum tokenı,
`oturumlar` tablosuna kayıt, `HttpOnly`/`SameSite=Lax` çerez (okul LAN'ında
düz HTTP olduğu için `Secure` değil — Farabi'nin kendi API'si de aynı
şekilde `0.0.0.0:8000`'de şifresiz çalışıyor, aynı emsal). Her korumalı
route'ta çerez kontrolü; yoksa `/giris`'e yönlendirme.

### systemd birimi (sunucuda elle oluşturulacak, plan dışı ama referans için)

```ini
[Unit]
Description=Yoklama Panosu
After=network.target

[Service]
Type=simple
User=ata
WorkingDirectory=/home/ata/farabi/tahtayoklama/dashboard
ExecStart=/home/ata/farabi/tahtayoklama/dashboard/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8010
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`farabi-api.service`/postgresql'e kasıtlı olarak `After=`/`Wants=` YOK —
tam ayrık.

### `scripts/ilk_yukleme.py`

1. `server/tahtalar.json`'ı oku (`_aciklama` hariç) → 10 `tahtalar` satırı.
2. 7 gerçek sınıf için `tahtayoklama/data/roster/<sinif>.json`'ı oku →
   `siniflar` + `ogrenciler`.
3. Ada göre 7 tahtayı ilgili sınıfa bağla.
4. Kullanıcının verdiği networkobjects.json'ı
   `dashboard/config/networkobjects.seed.json`'a kopyala, `HostAddress` →
   `ip` eşleşmesiyle `mac` doldur (yalnızca bilgi amaçlı alan).
5. `tahta-234/235/244` şimdilik `sinif_id=NULL` kalır (Faz 6'da adlandırılıp
   bağlanacak).

**Doğrulama**: `uvicorn app:app --port 8010` açılır; `/giris` render olur ve
belirlenen şifreyi kabul eder; `sqlite3 veri/yoklama_pano.db '.tables'` 5
tabloyu ve 7 gerçek sınıf/tahtayı gösterir; çerezsiz korumalı route
`/giris`'e yönlenir. Bu fazda henüz SSH/polling yok.

---

## Faz 2 — SSH polling motoru

Dosyalar: `ssh_istemci.py`, `yoklayici.py`, `zil.py`.

### SSH çağrısı (temel yapı taşı)

```
ssh -i ~/.ssh/id_ed25519_tahta -o BatchMode=yes -o ConnectTimeout=5 \
    -o StrictHostKeyChecking=accept-new -n <kullanici>@<ip> '<komut>'
```

`asyncio.create_subprocess_exec` ile (argüman listesi, shell string değil),
`asyncio.wait_for(proc.communicate(), timeout=15)` ile sarılı; timeout'ta
`proc.kill()`. `BatchMode=yes` kritik — anahtar çalışmazsa kimse cevap
veremeyecek bir şifre isteminde asılı kalmayı önler.

**Komut enjeksiyonu koruması**: komuta gömülen her değer (tarih, sınıf adı)
önce sıkı bir allow-list regex'ten geçer (`^\d{4}-\d{2}-\d{2}$` tarih için,
`^[A-Za-z0-9_-]+$` sınıf/tahta adı için) — uymayan girdi API sınırında 400
ile reddedilir. Roster senkron yazma yolu (Faz 5) JSON'u komut satırına
gömmek yerine **stdin** üzerinden geçirir.

### Durum taraması — tahta başına tek çağrı

```bash
python3 -c "
import json, glob, os, sys
tarih = sys.argv[1]
kdir = os.path.expanduser('~/tahtayoklama/data/kayitlar')
sonuc = {}
if os.path.isdir(kdir):
    for yol in glob.glob(os.path.join(kdir, tarih + '_*_ders*.json')):
        try:
            with open(yol, encoding='utf-8') as f:
                sonuc[os.path.basename(yol)] = json.load(f)
        except Exception as e:
            sonuc[os.path.basename(yol)] = {'_hata': str(e)}
print(json.dumps(sonuc, ensure_ascii=False))
" "<doğrulanmış tarih>"
```

### Birleştirme mantığı (`yoklayici.py`)

1. Tüm `aktif=1` tahtalarda bu taramayı `asyncio.gather` ile eşzamanlı
   çalıştır; erişilemeyen tahtaları işaretle.
2. Sonuçları `sinif`/`ders_no` alanına göre (dosya adına göre DEĞİL — içerik
   esas) `(sinif, ders_no) → kayıt` haritasına topla. Aynı anahtar iki
   tahtada bulunursa (eşleme değişimi sırasında olabilir) daha geç
   `kaydedilme_saati`'ni tut, `kaynak_tahta`'yı işaretle.
3. Her aktif sınıf × ders 1-8 için:
   - Kayıt varsa → `alindi`; `durumlar`daki `"yok"` no'larını roster'dan
     isme çevir (`str(no)` eşleşmesi; roster'da bulunamayan no → "No X"
     düşer, hata vermez).
   - Kayıt yoksa:
     - `tarih.isoweekday() ∉ ders_gunleri` → `ders_yok_o_gun`
     - sınıfa bağlı hiç tahta yok → `tahta_atanmamis`
     - bağlı tahta(lar) bu turda erişilemedi → `tahta_ulasilamaz`
     - `tarih != bugün` → `alinmadi`
     - `tarih == bugün`: ders başlamadıysa veya 10dk'lık tolerans
       içindeyse → `henuz_baslamadi`; 10dk geçtiyse → `alinmadi`
4. `yoklama_onbellek`'e `UPSERT`.

### Arka plan döngüsü

`app.py` lifespan'inde `asyncio.create_task`: Pazartesi-Cuma 08:00-16:10
dışında SSH trafiği yok; pencere içinde bugünün taraması ~2 dakikada bir.
`POST /api/yenile?tarih=...` herhangi bir tarih için anında tek tur
tetikler (geliştirme/doğrulama aracı).

**Doğrulama**: UI olmadan `curl -X POST /api/yenile?tarih=<bugün>`, sonra
`sqlite3` ile `yoklama_onbellek`'i incele — bilinen bir "yok" kaydı doğru
isimlerle `alindi` çıkmalı; ilk dersten önceki bir sınıf
`henuz_baslamadi`; 15+ dk geçmiş kayıtsız bir ders `alinmadi`; bozuk bir IP
verilince yalnızca o sınıf `tahta_ulasilamaz`, diğerleri etkilenmemeli.

---

## Faz 3 — Pano tablosu + tarih seçici

`templates/pano.html`, `static/pano.css`, `app.py`'de route.

- `GET /` (korumalı): `?tarih=` (varsayılan bugün, gelecek tarih
  reddedilir/kelepçelenir). `siniflar`'ı `(sınıf_no:int, şube:str)`'a göre
  sırala (`^(\d+)-([A-Za-z]+)$` regex; `lab1/2/3` gibi eşleşmeyenler sona,
  kendi aralarında alfabetik), `yoklama_onbellek` ile JOIN, 8 sütunlu tablo.
- Hücre kuralları: `alindi`+boş isim → yeşil "Tam"; `alindi`+isimler →
  kırmızı, virgülle isimler; `alinmadi` → amber, tıklanabilir "Yoklama
  alınmadı" (Faz 4); `tahta_ulasilamaz` → gri "Tahta ulaşılamaz",
  tıklanamaz; `henuz_baslamadi`/`ders_yok_o_gun` → boş/soluk; `tahta_atanmamis`
  → ayrı gri etiket "Tahta atanmadı".
- `GET /api/durum?tarih=...` (JSON) — ~60sn'de bir `fetch` ile tabloyu
  yerinde tazeleyen küçük vanilla JS; tarih seçicinin `onchange`'i de aynı
  uç noktayı kullanır. Build adımı yok.
- Tarih seçici: `<input type=date max=bugün>`.

**Doğrulama**: `/` bugün için Faz 2'nin manuel doğrulamasıyla eşleşmeli;
dün için geçmiş durum önbellekten (SSH tetiklemeden) doğru gelmeli.

---

## Faz 4 — Uzaktan başlatma

`ssh_istemci.py`'ye ekleme, yeni `uzaktan_baslat.py`, `pano.html`'de
tıklama + toast.

**Fazın ilk adımı, kod yazmadan önce**: 9-A'da elle tek bir SSH oturumuyla
aşağıdaki `DISPLAY`/`XAUTHORITY` keşfinin gerçekten kullanılabilir değer
döndürdüğünü doğrula — `/home/ogretmen/.Xauthority`'yi sabit kodlama,
güncel XFCE/Pardus kurulumlarında bu genelde `/run/user/1000/xauth_XXXXXX`
altında olur.

### A — Canlı oturumun X ortamını keşfet

```bash
PID=$(pgrep -u ogretmen -x xfce4-session | head -1)
[ -n "$PID" ] && tr '\0' '\n' < /proc/$PID/environ | grep -E '^(DISPLAY|XAUTHORITY)='
```
`PID` boşsa → "tahtada aktif masaüstü oturumu yok" hatasıyla hemen çık,
deneme.

### B — Zaten çalışıyor mu kontrolü

```bash
pgrep -af 'tahtayoklama/yoklama.py'
```

- **Çalışıyorsa**: pencere başlığı tam olarak `"Yoklama"` (doğrulandı,
  `yoklama.py:170`) →
  `DISPLAY=<keşfedilen> XAUTHORITY=<keşfedilen> wmctrl -a Yoklama`
  (`xdotool` tahtalarda YOK, `wmctrl` VAR — doğrulandı).
- **Çalışmıyorsa**: `disown` değil `setsid` (SSH'ın etkileşimsiz komut
  kanalında iş kontrolü yok, `disown`'ın tutunacağı bir şey olmaz):
  ```bash
  setsid env DISPLAY=<keşfedilen> XAUTHORITY=<keşfedilen> \
    /home/ogretmen/farabi/client/venv/bin/python /home/ogretmen/tahtayoklama/yoklama.py \
    </dev/null >/tmp/yoklama_dashboard_baslatma.log 2>&1 &
  ```
  ~2sn sonra `pgrep -af` ile tekrar kontrol edip sonucu raporla.

### API

`POST /api/tahta/{tahta_id}/baslat` (korumalı) →
`{"basarili": bool, "durum": "one_getirildi"|"yeni_baslatildi"|"hata", "detay": "..."}`.
`pano.html`'de "Yoklama alınmadı" tıklamasından `fetch` ile çağrılır, toast
gösterir; başarılıysa o tarih için `/api/yenile` tetiklenir (not: bu hücreyi
otomatik `alindi`ya çevirmez — sadece ekranı açar, kayıt öğretmenin
kaydetmesiyle oluşur).

**Önemli sınır**: SSH süreç var mı diye bakabilir, ekranda GERÇEKTEN
görünür mü diye bakamaz (o daha ağır bir araç, örn. `veyon-cli` screenshot,
kapsam dışı). `pgrep` başarısı panonun sunabileceği kabul sinyali; bu fazın
gerçek kabulü 9-A'da elle bir kez gözle doğrulamak.

**Doğrulama**: 9-A'da çalışan `yoklama.py`'yi kapat, panodan "Yoklama
alınmadı" hücresine tıkla → API `yeni_baslatildi` dönmeli, tahtada
`pgrep -af yoklama.py` süreci göstermeli, fiziksel ekranda (veya VNC ile)
pencere görünmeli. Sonra tekrar tıkla, `one_getirildi` + pencere gerçekten
öne gelmeli.

---

## Faz 5 — Yönetim ekranları: tahta↔sınıf atama, roster düzenleme, senkron

`templates/admin_tahtalar.html`, `admin_sinif_ogrenciler.html`, `app.py`'de
(veya ayrı `admin.py` router) route'lar.

### Tahta ↔ sınıf atama

- `GET /admin/tahtalar`: tüm tahtalar (ad, ip, mac, sınıf açılır menüsü,
  aktif anahtarı).
- `POST /admin/tahtalar/{id}`: `sinif_id` (null olabilir), `aktif`. **SSH
  YOK** — yalnızca panonun kendi eşlemesini değiştirir, tahtadaki dosyalara
  dokunmaz (anlık, güvenli).
- **Hızlı takas aksiyonu** (kullanıcı isteği): tabloda her satırda "Şununla
  yer değiştir ↔" açılır menüsü — başka bir sınıf seçilince iki tahtanın
  `sinif_id`'leri tek işlemde (transaction) karşılıklı değiştirilir (örn.
  10-A ↔ 10-B). Bu, dropdown'la iki ayrı düzenleme yapmaktan daha az
  hataya açık (aradaki anda iki sınıfın da atanmamış görünmesi riskini
  önler).
- **Sürükle-bırak** (istenen, ikinci bir katman): aynı sayfada satırları
  sürükleyip birbirinin üzerine bırakınca yukarıdaki takas endpoint'ini
  çağıran düz JS (`draggable="true"` + `dragstart`/`drop` olayları, kütüphane
  yok) — dropdown takas her zaman çalışan güvenilir yol, sürükle-bırak onun
  üzerine ince bir kolaylık katmanı.
- `POST /admin/tahtalar` (yeni tahta ekleme).

### Roster düzenleyici

- `GET /admin/siniflar`: sınıf listesi + öğrenci sayıları.
- `GET /admin/siniflar/{id}/ogrenciler`: düzenlenebilir tablo, satır
  ekle/çıkar, `cinsiyet` opsiyonel kalır.
- `POST /admin/siniflar/{id}/ogrenciler`: gönderilen satırlarla rosteri
  komple değiştirir (satır-satır fark alma değil — sınıf başına ~20
  öğrenci, düşük frekanslı bir işlem, komple değiştirmek en basit doğru
  semantik).
- `POST /admin/siniflar` (yeni sınıf): `ad` için `^[A-Za-z0-9_-]+$`
  doğrulaması (bu string sonradan tahtada dosya adı olacak — SSH sınırında
  değil, burada da doğrulanmalı).

### Tahtaya senkronize et

`POST /admin/siniflar/{id}/senkronize`:
1. Bu sınıfa bağlı tüm tahtaları bul (normalde bir tane; geçiş döneminde
   birden fazla/sıfır olabilir, ikisini de ele al, tahta başına sonuç
   raporla).
2. `yoklama.py`'nin beklediği tam şemayı üret: `{"sinif": ad, "ogrenciler":
   [{"no", "ad_soyad", "cinsiyet"}...]}` (cinsiyet yoksa anahtarı hiç
   yazma, `null` değil — `9-A.example.json` şemasıyla birebir).
3. **Stdin ile** (komut satırı enjeksiyonu değil) atomik yaz:
   ```bash
   ssh ... 'cat > ~/tahtayoklama/data/roster/<sinif>.json.tmp && \
             mv ~/tahtayoklama/data/roster/<sinif>.json.tmp \
                ~/tahtayoklama/data/roster/<sinif>.json'
   ```
   (`.tmp` + `mv` atomik — yarım yazılmış dosyayı `yoklama.py` asla
   görmez.)
4. Tahta başına `{"tahta", "basarili", "detay"}` sonucu ekranda göster.

**Doğrulama**: panodan bir tahtayı başka sınıfa ata (SSH yok, anında) →
Faz 3 tablosu bir sonraki polling turunda bunu yansıtmalı. Bir rosteri
düzenleyip senkronize et → tahtaya elle SSH ile `cat` ederek dosyayı
doğrula → tahtada `yoklama.py`'yi aç, yeni rosterin combo box'ta göründüğünü
gör.

---

## Faz 6 — Eksik 3 tahtayı kur (lab1/lab2/lab3)

**İlk adım, dosyalara dokunmadan önce**: `.234`/`.235`/`.244`'te
`~/farabi/client/venv` (PyQt6 ile) gerçekten var mı doğrula —
`~/tahtayoklama` yokluğu doğrulandı ama bu venv'in varlığı henüz
doğrulanmadı:
```bash
ssh ogretmen@<ip> "test -x ~/farabi/client/venv/bin/python && \
  ~/farabi/client/venv/bin/python -c 'import PyQt6'"
```
- **Varsa**: diğer 7 tahtayla birebir aynı şekilde devam et.
- **Yoksa**: kullanıcıyla birlikte karar ver — (a) `tahtayoklama`'ya kendi
  venv'ini kur (`ogretmen` sudo'suz, `python3 -m venv` + `pip install
  PyQt6 pdfplumber` yeterli, `etapadmin`'e hiç dokunmadan) ya da (b)
  `etapadmin` + apt (tutarsız NOPASSWD riski taşıyor). (a) önerilir.

### Adımlar

1. Pano DB'sinde 3 tahtayı yeniden adlandır: `tahta-234→lab1`,
   `tahta-235→lab2`, `tahta-244→lab3`.
2. 3 yeni sınıf oluştur (`lab1`/`lab2`/`lab3`), her birine tek öğrenci:
   `no=1, ad_soyad="Ali Deneme"`. Her sınıfı ilgili tahtaya bağla.
3. Tahta başına SSH ile: `mkdir -p ~/tahtayoklama/data/{roster,kayitlar}`,
   `yoklama.py` + `data/zil.json`'ı `scp` ile kopyala (aynı dosya, bağımsız
   kopya — sembolik link değil, mevcut konvansiyona uygun), rosterı Faz
   5'in senkron endpoint'i üzerinden yaz (ayrı bir mekanizma gerekmez),
   `~/Masaüstü/Yoklama.desktop`'ı diğer 7 tahtadaki doğrulanmış içerikle
   birebir oluştur.

**Doğrulama**: pano tablosunda `lab1/2/3` artık `tahta_atanmamis` değil,
gerçek zamanlama durumlarıyla görünmeli; fiziksel tahtada (veya Faz 4'ün
uzaktan başlatmasıyla) `yoklama.py` açılıp tek roster kaydı "Ali Deneme"
görünmeli; bir test kaydı kaydedilip panoda bir sonraki polling turunda
doğru göründüğü teyit edilmeli.

---

## Faz 7 (opsiyonel, ayrı onay gerekir) — Gerçek yoklama vs. otomatik kayıt ayrımı

`yoklama.py`'nin sessiz otomatik kaydı (`_kaydet(sessiz=True)`,
dönem geçişinde) ile öğretmenin "YOKLAMAYI KAYDET"e bilerek basması şu an
ayırt edilemiyor — ikisi de aynı `alindi` durumunu üretiyor. Gerçek çözüm
`yoklama.py`'ye bir `elle_kaydedildi: bool` alanı eklemeyi gerektiriyor
(tahtada ÇALIŞAN, kullanımda olan bir dosyayı değiştirmek — kural 3/5'e
göre ayrı bir onay ve ayrı bir plan konusu, bu fazın kapsamına şimdi dahil
edilmedi, yalnızca burada kayıt altına alınıyor).

---

## Kullanıcıya açık bırakılan kararlar

1. Roster senkronu yalnızca o an bağlı tek tahtaya mı gitsin (önerilen),
   yoksa sınıfı hiç taşımış tüm tahtalara mı?
2. `izinli` (izinli/mazeretli) öğrenciler pano hücresinde `yok`un yanında
   ayrı renkte gösterilsin mi, yoksa hiç gösterilmesin mi (varsayılan:
   yalnızca `yok` isimleri)?
3. Panonun kuruluşundan önceki tarihler için (7 tahta zaten kullanımda) bir
   defalık geçmişe dönük tarama yapılsın mı, yoksa önbellek kuruluş
   gününden mi başlasın?
4. `lab1/2/3` daha ilk gerçek öğrenci eklenmeden pano tablosunda görünsün
   mü (varsayılan: evet, "aktif tahta" oldukları için), yoksa gizli mi
   kalsın?

## Doğrulama için kritik dosyalar

- `/home/ata/farabi/tahtayoklama/yoklama.py` — kayıt/roster şeması, dosya
  adlandırma, pencere başlığı, kendi kendine öne gelme mantığı
- `/home/ata/farabi/tahtayoklama/data/zil.json` — 10 dakikalık zamanlama
  mantığının kaynağı
- `/home/ata/farabi/server/tahtalar.json` — tek seferlik tohumlama kaynağı
- `/home/ata/farabi/server/tahta-ssh.sh` — SSH anahtar/kullanıcı
  konvansiyonu (shell out edilmeyecek, aynı desen Python'da tekrarlanacak)
- `/home/ata/farabi/CLAUDE.md` — yeni `tahtayoklama/CLAUDE.md` ve dashboard
  kod stilinin örnek aldığı üst düzey konvansiyon
