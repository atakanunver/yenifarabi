# Tahta gece/sabah bakımı — tasarım

- **Tarih:** 2026-09-28
- **Durum:** Tasarım onaylandı (kullanıcı, 2026-09-28). Plan: `docs/superpowers/plans/2026-09-29-tahta-gece-sabah-bakim.md`.
- **Kapsam:** `tahtayoklama/dashboard/` (yeni modül + CLI + tablo + durum
  kartı) ve sunucuda iki systemd timer. Tahtalara yeni yazılım/birim
  KURULMAZ.

## 1. Amaç

Her gün iki zamanlanmış iş, 8 Farabi tahtasının hepsine SSH ile:

- **21:00 (İstanbul) — gece:** açık olan her tahtada hata/donma/donanım
  loglarını tara → bulguları dashboard durum ekranına yaz → tahtayı
  yeniden başlat → açılınca tam ekran karartma + ekranı DPMS ile kapat +
  CPU'yu tasarrufa al.
- **07:00 (İstanbul) — sabah:** açık olan her tahtayı yeniden başlat →
  açılınca CPU'yu yüksek performansa al, karartmayı kaldır.

Kullanıcı kararları (2026-09-28):

- 21:00'de yalnızca kritik hatalılar değil, **açık olan tüm tahtalar**
  yeniden başlatılır. Kritik hatalar yalnızca raporlanır.
- "Tasarruf" = CPU governor `ondemand` + azami frekans en düşüğe sınırlı
  **ve** karartma penceresi + DPMS ile ekran kapatma. "Yüksek performans"
  = governor `performance` + azami frekans sınırsız.
- Yaklaşım A: sunucuda systemd timer + dashboard kodunu kullanan script;
  ayarlar reboot sonrası sunucudan SSH ile uygulanır.

## 2. Ölçülen ortam (2026-09-28, fenlab/9-B/12-A)

- Tahtalarda `power-profiles-daemon`, `tlp`, `powerprofilesctl` **yok**.
  Yalnızca cpufreq: mevcut governor'lar `ondemand performance schedutil`
  (`powersave` yok), varsayılan `schedutil`. Frekans 1 400 000–2 500 000 kHz
  (fenlab). Governor/frekans ayarı reboot'ta sıfırlanır — bu yüzden her
  açılıştan sonra yeniden uygulanması şart.
- `xset`, `wmctrl`, `eta-screen-cover` kurulu. Journal kalıcı
  (`/var/log/journal`, `journalctl -b -1` okunabiliyor).
- Sunucunun saat dilimi `Etc/UTC` — timer'larda saat dilimi açıkça
  `Europe/Istanbul` yazılır.
- 9-A'da otomatik giriş YOK (`tahtaayar/CLAUDE.md`) → reboot sonrası orada
  X oturumu olmaz, karartma/DPMS uygulanamaz; yalnızca CPU ayarı yapılır ve
  bu raporlanır.

## 3. Bileşenler

| Birim | Yer | Görev |
|---|---|---|
| `tahta_bakim.py` | `tahtayoklama/dashboard/` | İş mantığı; saf, test edilebilir fonksiyonlar |
| `scripts/tahta_bakim.py` | `tahtayoklama/dashboard/scripts/` | CLI: `gece\|sabah [--kuru] [--tahta <ad>]` |
| `farabi-tahta-gece.{service,timer}` | `/etc/systemd/system/` | `OnCalendar=*-*-* 21:00:00 Europe/Istanbul` |
| `farabi-tahta-sabah.{service,timer}` | `/etc/systemd/system/` | `OnCalendar=*-*-* 07:00:00 Europe/Istanbul` |
| `tahta_bakim` tablosu | dashboard `yoklama_pano.db` | Çalışma sonuçları |
| "Tahta Bakım Raporu" kartı | `/sistem-durumu` sayfası | Son gece + son sabah sonucu |

- Servisler `Type=oneshot`, `User=ata`, dashboard venv'i
  (`tahtayoklama/dashboard/venv/bin/python`), `WorkingDirectory=
  tahtayoklama/dashboard`. Birim dosyalarının kopyası repoda tutulur
  (plan yerini belirler).
- Timer'larda `Persistent=` **kapalı**: sunucu 21:00'de kapalıysa ve sonra
  açılırsa kaçırılan iş geç saatte çalışıp tahtaları yeniden başlatmamalı.
- Dashboard servisinden (`farabi-yoklama-dashboard`) bağımsız süreç:
  dashboard restart'ı işi kesmez. İkisi aynı SQLite'a yazar; dashboard
  yalnızca okur (kart için).
- Mevcut kod yeniden kullanılır: `ssh_istemci.komut_calistir`,
  `ssh_istemci.x_ortamini_kesfet`, `tahta_kaydi.tahtalari_yukle`,
  `zil.simdiki_ders`/`zil.okul_gunu_mu`/`zil.simdi_istanbul`, karartma
  komutları `uzaktan_yonetim._ekran_karart_tek`/`_ekran_kaldir_tek` ile
  aynı (kopyalamak yerine ortak yardımcıya taşımak plan kararı). Root
  komutları `tahtaayar/tahta_fix_uygula.py`'deki desenle: önce `sudo -n`,
  olmazsa `gizli.json::etapadmin_sifre` ile `sudo -S`.

**Hedef tahtalar:** `tahta_kaydi.tahtalari_yukle()` çıktısından adı
`tahta-` ile başlayanlar çıkarılır (sınıfı atanmamış `.234/.235/.236`
kayıtları) → 8 Farabi tahtası. Tahtalar paralel işlenir; biri diğerini
beklemez/durdurmaz.

## 4. Akış

### 4.1 Gece (21:00)

Her tahta için:

1. **Erişim:** SSH ulaşılamazsa → `kapali`, dur.
2. **Log taraması** (`ogretmen`, sudo'suz; journal okuma izni yoksa aynı
   sorgular `etapadmin`+sudo ile):
   - `journalctl -b 0 -k -p 0..3 --no-pager` ve `journalctl -b 0 -p 0..2
     --no-pager` → kalıp listesiyle sınıflandır. **Kritik** kalıplar:
     `soft lockup`, `hung_task`/`blocked for more than`, `Machine Check`/
     `mce:`, `I/O error`, `Out of memory`/`oom-kill`, `GPU hang`/
     `i915.*(hang|reset)`, `segfault` (Xorg/cinnamon), `EXT4-fs error`.
     Diğer err+ satırları **uyarı** (sayı + ilk birkaç örnek).
   - **Temiz kapanmama:** `journalctl -b -1 -n 50 --no-pager` içinde
     kapanış izi (`systemd-shutdown`, `Reached target.*(Power-Off|Reboot|
     Shutdown)`, `Shutting down`) yoksa kritik: "önceki açılış temiz
     kapanmadı (donma/elektrik kesintisi şüphesi)".
   - Farabi client logu: `farabi.log` içinde son 24 saatin `ERROR` ve
     `Traceback` sayısı → uyarı. Yol 9-A'da `~/farabi/repo/client/logs/`,
     diğerlerinde `~/farabi/client/logs/`.
3. **Kayıt:** bulgular `tahta_bakim`'a yazılır (reboot'tan ÖNCE — tahta
   geri gelmese bile rapor kalır).
4. **Okul saati kilidi:** okul günü ve `zil.ilk_ders_saati()` ≤ şimdi <
   `zil.son_ders_bitis_saati()` (bugün 08:10–15:50, teneffüsler DAHİL) ise
   reboot YAPILMAZ, `detay`'a "Okul saati içinde, reboot atlandı" yazılır.
   (2026-09-29 plan aşamasında "şu an ders var mı" kilidinden genişletildi:
   teneffüste `simdiki_ders` None döndüğü için elle çalıştırma tahtaları
   teneffüste yeniden başlatabilirdi.)
5. **Reboot:** `etapadmin` + `sudo systemctl reboot`.
6. **Geri gelmesini bekle:** 5 sn aralıkla SSH dene, en fazla 360 sn.
   Gelmezse → `geri_gelmedi`, dur. Gelince X oturumu için 20 sn bekle.
7. **Gece modu:**
   - root: her `cpu*/cpufreq/scaling_governor` ← `ondemand`,
     `scaling_max_freq` ← `cpuinfo_min_freq`.
   - `ogretmen`: `x_ortamini_kesfet` → `eta-screen-cover` başlat +
     `wmctrl ... -b add,maximized_vert,maximized_horz` → `xset dpms force
     off`. X oturumu yoksa (9-A) bu adım atlanır, not düşülür.
8. Son durum kaydı güncellenir: `tamam` / `kritik` (kritik bulgu varsa,
   işlemler başarılı olsa bile) / `hata` (bir adım başarısızsa; detayda
   hangisi).

### 4.2 Sabah (07:00)

1. Erişim yoksa → `kapali` (Wake-on-LAN kapsam dışı).
2. Okul saati kilidi (4.1 adım 4 ile aynı).
3. Reboot → geri gelmesini bekle (4.1 adım 5–6).
4. **Sabah modu:** root: governor ← `performance`, `scaling_max_freq` ←
   `cpuinfo_max_freq`. `ogretmen`: `pkill -f '[e]ta-screen-cover'`
   (reboot sonrası normalde çalışmıyor; güvence), `xset dpms force on`.
5. Kayıt: `tamam` / `hata`. Sabah log taraması yapılmaz.

### 4.3 `--kuru`

Yalnızca erişim + log taraması + kayıt; reboot, CPU, karartma YOK. Kayıtta
`mod` = `gece_kuru`/`sabah_kuru` — gerçek çalışmalarla karışmaz.

## 5. Veri modeli

```sql
CREATE TABLE IF NOT EXISTS tahta_bakim (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    calisma_id    TEXT NOT NULL,      -- bir çalışmanın tüm tahtaları aynı id
    mod           TEXT NOT NULL,      -- gece | sabah | gece_kuru | sabah_kuru
    tahta_adi     TEXT NOT NULL,
    baslangic_utc TEXT NOT NULL,      -- datetime('now'), UTC
    bitis_utc     TEXT,
    durum         TEXT NOT NULL,      -- tamam | kritik | kapali | geri_gelmedi | hata | calisiyor
    kritik_json   TEXT NOT NULL DEFAULT '[]',
    uyari_json    TEXT NOT NULL DEFAULT '[]',
    detay         TEXT NOT NULL DEFAULT ''
);
```

- Zaman UTC saklanır, yalnızca gösterimde İstanbul'a çevrilir
  (smssistemi 2026-09-28 dersi: ham UTC gösterimi 3 saat geri görünüyordu).
- Otomatik silme yok (proje log politikasıyla uyumlu). Günde 16 satır.
- Tablo `db.py`'nin mevcut `CREATE TABLE IF NOT EXISTS` bloğuna eklenir;
  mevcut tablolara dokunulmaz.

## 6. Dashboard kartı

- `/sistem-durumu` sayfasına "Tahta Bakım Raporu" kartı; veri mevcut
  `/api/sistem-durumu` JSON'una ek bir alan olarak ya da ayrı bir salt-okur
  endpoint'le gelir (plan kararı; mevcut alanlar değişmez).
- Son `gece` ve son `sabah` çalışması: çalışma saati (İstanbul), tahta
  başına durum rozeti, kritik bulgular açılır liste.
- `pano.css` token'ları + satır içi ikon sprite; yeni kütüphane/CDN yok
  (`tahtayoklama/CLAUDE.md` tasarım standartları).

## 7. Hata durumları

| Durum | Davranış |
|---|---|
| Tahta kapalı/ulaşılamaz | `kapali`, reboot denenmez |
| Okul saati (08:10–15:50) | reboot atlanır, rapor yazılır |
| Reboot sonrası 360 sn'de gelmedi | `geri_gelmedi` |
| sudo başarısız (NOPASSWD yok + parola yok/yanlış) | CPU adımı atlanır → `hata`; karartma/DPMS yine denenir |
| X oturumu yok (9-A, oturum açılmamış) | karartma/DPMS atlanır, detayda not |
| Script çökmesi | yakalanan istisna o tahtada `hata`; diğer tahtalar sürer; systemd journal'da iz |
| Aynı anda iki çalışma | CLI dosya kilidiyle (`flock`) ikinciyi reddeder |

Kural 2: işler ders dışı saatlerde; okul saati kilidi ek güvence. Tahtadaki
Farabi client/yoklama bu işten habersizdir, yalnızca normal açılışla
yeniden başlar.

## 8. Test ve devreye alma

- `unittest` (dashboard deseni, pytest değil): kritik/uyarı kalıp
  sınıflandırması, temiz/kirli önceki açılış tespiti, okul saati kilidi, hedef
  tahta filtresi (`tahta-` hariç), DB kaydı + UTC→İstanbul gösterimi,
  sahte `ssh_istemci` ile adım sırası (tarama → kayıt → reboot → bekle →
  mod) ve hata dalları.
- Canlı prova, sırayla:
  1. `--kuru gece` 8 tahtada — yalnızca tarama, kart görünümü kontrolü.
  2. Yalnızca `--tahta fenlab` ile gerçek `gece`, sonra gerçek `sabah`.
  3. Atakan fiziksel tahtada kontrol eder (karartma, ekran kapalı, sabah
     normal açılış) — Kural 12.
  4. Ancak bundan sonra timer'lar `systemctl enable --now` ile açılır.
- Ruff: yalnızca dokunulan dosyalar.

## 9. Kapsam dışı

- Wake-on-LAN (kapalı tahtayı sabah açmak).
- Tahtaya açılış servisi kurmak (yaklaşım C) — açılıştaki ~1–2 dk'lık
  normal-mod aralığı sorun olursa yeniden değerlendirilir.
- 9-A'ya otomatik giriş eklemek (`tahtaayar`'da ayrı karar bekliyor).
- Kritik bulguda otomatik bildirim (SMS/Telegram).
