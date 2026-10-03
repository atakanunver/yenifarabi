# tahtaayar

Bu klasördeki script'ler yeni bir tahta kurulurken ya da mevcut bir tahtayı
sağlam referans duruma getirirken çalıştırılır — **ajan gerektirmez**.
`client/` (Farabi sesli ders asistanı) ve `tahtayoklama/` (yoklama) ikisi de
aynı fiziksel tahtalarda koşuyor; OS/oturum düzeyi provizyon (güç düğmesi,
uyku, ekran karartma gibi) ikisinden de bağımsız, ortak bir katman — bu
yüzden `client/`/`tahtayoklama/`'nın altında değil, ayrı bir üst düzey
klasörde yaşıyor.

## Taşıma notu (2026-09-15)

`tahta_fix_uygula.py`, `tahtayoklama/dashboard/scripts/`'ten buraya
TAŞINDI (git mv, kopya bırakılmadı). Gerekçe: repoda zaten yaşanmış bir
"iki kopya senkron kalmadı" hatası var (`mudur/ders_programi_yukle.py` ile
`tahtayoklama/dashboard/scripts/ders_programi_yukle.py`'nin KISALTMALAR
sözlüğü — bkz. `tahtayoklama/CLAUDE.md`, "iki ayrı dosya, tek doğru kaynak
yok"). İkinci bir `DUZELTMELER` listesi aynı yarayı açardı.

Parola da tek yerde: `etapadmin_sifre` yalnızca
`tahtayoklama/dashboard/config/gizli.json`'da duruyor (gitignore'lu),
ikinci bir dosyaya kopyalanmadı. `tahta_fix_uygula.py` önce
`tahtaayar/config/gizli.json`'a bakar (bugün yok, yalnızca yol açık),
yoksa o dosyaya düşer.

## Çalıştırma

```bash
python3 tahtaayar/tahta_fix_uygula.py                                     # tüm tahtalar
python3 tahtaayar/tahta_fix_uygula.py --tahta 9-B                          # tek tahta
python3 tahtaayar/tahta_fix_uygula.py --sadece-kontrol                     # uygulamadan yalnızca durum raporu
python3 tahtaayar/tahta_fix_uygula.py --duzeltme uyku_hedefleri_maskeli    # tek düzeltme
```

Ön koşullar: `~/.ssh/id_ed25519_tahta` (SSH anahtarı), `server/tahtalar.json`
(tahta listesi/IP), yalnızca stdlib — venv gerekmez.

## Güç düğmesi — İKİ AYRI YOL (2026-09-15'te netleşti)

`tahtayoklama/CLAUDE.md`'de daha önce "aşağıdaki Güç düğmesi bulgusu"na
atıf yapılıyordu ama böyle bir bölüm orada hiç yazılmamıştı — gerçek
hikâye burada:

**Yol 1 — systemd/logind (ÇÖZÜLDÜ 2026-09-14, sabitlendi 2026-09-15).**
`HandlePowerKey` varsayılanı `poweroff` — güç düğmesine KISA basış sistemi
anında kapatıyordu (9-B/11-B'de gerçek olay, `journalctl`'de "Power key
pressed short" → "The system will power off now!" ile doğrulandı). Fix:
`/etc/systemd/logind.conf.d/90-guc-tusu-yoksay.conf` ile
`HandlePowerKey=ignore`. UZUN basış için de aynı yaklaşım ayrı bir dosyada
(`91-guc-tusu-uzun-basis.conf`, `HandlePowerKeyLongPress=ignore`) — 9-A'da
etkin değer zaten systemd varsayılanıyla "ignore" idi, ama bu dosya
olmadan gelecekteki farklı bir OS/systemd varsayılanına karşı hiçbir
koruma yoktu; şimdi açıkça sabit.

**Yol 2 — Cinnamon'un KENDİ güç düğmesi eylemi (BULUNDU 2026-09-15).**
`org.cinnamon.settings-daemon.plugins.power` şemasının `button-power`
anahtarı — bu, masaüstü oturumunun kendi tuş yakalaması üzerinden çalışır,
**logind'den tamamen bağımsızdır**. Yani 2026-09-14'teki fix güç düğmesi
yollarının yalnızca BİRİNİ kapatmıştı. Canlı tarandığında (7 aktif tahta,
`gsettings get` — sudo GEREKMEZ, kullanıcı düzeyi bir ayardır):

| Tahta | `button-power` (2026-09-15 taramasında) |
|---|---|
| 10-A, 12-B | `'nothing'` (daha önce elle düzeltilmiş, script'e hiç yazılmamıştı) |
| 9-A, 9-B, 11-A, 11-B, 12-A | `'shutdown'` |

Yedi tahtada da geçerli enum aynı: `gsettings range` →
`'blank' 'suspend' 'shutdown' 'hibernate' 'interactive' 'nothing'`.
Kullanıcı onayıyla hedef değer **`'nothing'`** seçildi (tuş hiçbir şey
yapmaz) — `'blank'` (tuşa basınca anında ekranı karart) da değerlendirildi
ama tercih edilmedi. Fix `cinnamon_guc_tusu_yoksay` olarak eklendi ve
2026-09-15'te 7/7 aktif tahtaya uygulandı, uçtan uca doğrulandı.

**Dürüst belirsizlik:** Yol 2, 2026-09-14 fix'inden SONRA da süren "kendi
kendine kapanma" bildirimleri için güçlü bir aday açıklamadır, ama
**belirli bir olayın kanıtlanmış kök nedeni değildir.** 2026-09-15'te
kullanıcı 9-A/9-B'yi ilgisiz bir pano-bug testi için kendisi elle açıp
kapatıyordu; o günün bazı "kendi kendine kapandı" bildirimleri bu elle
işlemlerin yanlış atfedilmesi olabilir. Kesin kanıt ancak fiziksel bir
basış testiyle ya da `journalctl`'de Yol 2'ye özgü bir izle gelir —
**fiziksel tuş davranışı SSH ile test edilemez, son kabul kullanıcıya
ait** (kök `CLAUDE.md`'nin "son kabul testi her zaman Atakan tarafından
fiziksel tahtada yapılır" ilkesiyle aynı).

**Ekran karartma zaten ayrı, çözülü bir konu:** `sleep-display-ac = 600`
(10 dk boşta kalmada ekran karartma) 7 tahtada da aynı, güç tuşuyla ilgisi
yok. "Oda ekranı karartsın" isteği bu boşta-kalma zamanlayıcısıyla zaten
karşılanıyor.

> ⚠️ **Düzeltme (2026-09-22): "7 tahtada da aynı, ayrı bir fix'e gerek yok"
> varsayımı tutmadı.** `fenlab` (.244) taranınca `sleep-display-ac = 0`
> (= hiç karartma) bulundu. Yukarıdaki cümle yazıldığında yalnızca 7 sınıf
> tahtası taranmıştı, laboratuvar kapsam dışındaydı. Sürüklenmenin sessizce
> sürmemesi için **`ekran_karartma` artık yönetilen bir fix** (aşağıya bkz.)
> — değer yine 600, ama artık ölçülüp uygulanıyor.

## 2026-09-22'de eklenen iki fix

`DUZELTMELER` listesi 4'ten 6'ya çıktı:

- **`otomatik_giris`** (root) — `/etc/lightdm/lightdm.conf.d/50-tahta-autologin.conf`
  drop-in dosyasıyla `ogretmen` oturumu parola sorulmadan açılır. İçerik
  uydurulmadı: 9-B/10-A/11-A/12-A/12-B'de ZATEN bu dosyayla kurulu bulundu,
  birebir oradan alındı (`[Seat:*]` + `autologin-user=ogretmen` +
  `autologin-user-timeout=0` + `autologin-session=cinnamon`).
  **Bu fix `cinnamon_guc_tusu_yoksay`'ın ön koşuludur** — o fix aktif bir
  `ogretmen` oturumu ister (bkz. "Bilinen sınırlar"), otomatik giriş kurulu
  olan tahtada bu koşul kendiliğinden sağlanır.
- **`ekran_karartma`** (kullanıcı düzeyi, sudo YOK) — `sleep-display-ac` = 600.

2026-09-22 taraması (10 kayıtlı tahtanın erişilebilen 7'si):

| Durum | Tahtalar |
|---|---|
| Her iki fix de uygulanmış | 9-B, 10-A, 11-A, 12-A, 12-B, fenlab |
| `otomatik_giris` EKSİK | **9-A** (karartma tamam) |
| Erişilemedi (kapalı) | 11-B, tahta-234/235/236 |

`fenlab`'a ikisi de bu tarihte uygulandı ve doğrulandı. **9-A'ya bilinçli
olarak DOKUNULMADI** — pilot tahta ve kendine özgü bir klasör yapısı var
(`~/farabi/repo/client`, bkz. kök `CLAUDE.md`); otomatik girişin orada
istenip istenmediği kullanıcıya sorulacak.

> ⚠️ **Güncel durum (2026-09-29): yukarıdaki "9-A'ya dokunulmadı" notu
> ESKİDİ.** 9-A'da `50-tahta-autologin.conf` artık kurulu ve çalışıyor
> (`--sadece-kontrol`: 6/6 fix uygulanmış); 9-A diğer sınıf tahtalarıyla
> aynı referans durumda. Bkz. aşağıdaki "2026-09-29 ham karşılaştırması".

## 2026-09-29 ham karşılaştırması — fix script'inin GÖRMEDİĞİ farklar

`tahta_fix_uygula.py --sadece-kontrol` yalnızca `DUZELTMELER` listesindeki
6 maddeye bakar; "hepsi ✓" tahtaların AYNI olduğu anlamına gelmez. 9-A'da
her şey ✓ görünürken şikâyetlerin gerçek nedenleri listede olmayan yerlerdeydi
ve ancak tahtalar arası ham karşılaştırmayla (sistem birimleri, sudoers,
`/var/log/lightdm/lightdm.log`, `loginctl`, `gsettings list-recursively`)
bulundu. Ayrıntı: `DECISIONS.md` 2026-09-29.

- **9-A `x11vnc.service` (KALDIRILDI):** yalnızca 9-A'da elle eklenmiş,
  hatalı tanımlı bir VNC birimi (`Type=forking` + `-bg -loop`) 90 sn'de bir
  zaman aşımına düşüp yeniden başlıyor, her seferinde `:0`'ın klavye
  eşlemesine dokunuyordu → fare/klavye/dokunmatik kilitlenmesi. Dosya
  `/root/x11vnc.service.kaldirildi-20260929`'da. Hiçbir tahtada ayrı bir
  VNC birimi olmamalı (Veyon'un kendi x11vnc'si, port 11200, ayrı ve
  normal).
- **"Otomatik giriş yok" = kilit ekranı:** autologin çalışsa bile oturum
  sonradan kilitlenirse (`lightdm.log`: `Seat seat0: Locking`,
  `custom-screensaver-command = 'dm-tool lock'`) LightDM greeter VT8'de
  öne geçer, `ogretmen` oturumu VT7'de arkada kalır — öğretmen parola
  ekranı görür. Teşhis: `loginctl show-session <id> -p Active` (kullanıcı
  oturumu `Active=no`, `c1` greeter `Active=yes`). Kurtarma, `etapadmin`
  ile: `sudo loginctl activate <ogretmen-oturum-id>`. Kilidi 9-A'da neyin
  tetiklediği bulunamadı.
- **Sudo (EŞİTLENDİ):** referans durum — `/etc/sudoers.d/farabi-nopasswd`
  = `etapadmin ALL=(ALL) NOPASSWD: ALL`, `ogretmen` `sudo` grubunda DEĞİL,
  `ogretmen` için `sudo -n` başarısız. 9-A tersti (`ogretmen` NOPASSWD +
  `sudo` grubu, `etapadmin` parolalı); 2026-09-29'da kullanıcı kararıyla
  referansa getirildi. `etapadmin` için parolasız sudo HER tahtada yok —
  2026-09-29 ölçümü (`sudo -n true`): 9-A, 9-B, 10-A, 11-B, 12-B parolasız;
  11-A (`farabi-nopasswd` dosyası hiç yok), 12-A, fenlab (dosya var ama
  parola istiyor, içeriği okunmadı) parolalı. `ogretmen` hiçbirinde
  sudo'lu değil. Parolalı tahtalara dokunulmadı; script'ler zaten
  `gizli.json::etapadmin_sifre` ile `sudo -S`'e düşüyor.
- **fenlab:** `veyon-watchdog.timer` yok (diğer 8 tahtada var),
  `sleep-display-battery` 0 (diğerlerinde 600, prizde etkisiz) — ikisine de
  dokunulmadı.

Tekrar kullanılabilir yöntem: aynı salt-okunur tarama script'ini birkaç
tahtada çalıştırıp çıktıları `diff`'lemek (referans olarak 9-B/12-B).
`ogretmen` sistem journal'ını ve `/var/log/lightdm/`'i okuyamaz — bunlar
için `etapadmin`+`sudo` gerekir.

## Bilinen sınırlar

- `cinnamon_guc_tusu_yoksay` aktif bir `ogretmen` masaüstü oturumu
  (`/run/user/$(id -u)/bus` soketi) gerektirir — sıfırdan kurulmuş, hiç
  giriş yapılmamış bir tahtada bu fix "uygulanamadı" raporlar; o tahtada
  script ilk öğretmen girişinden SONRA tekrar çalıştırılmalı. `DUZELTMELER`'deki
  6 fix'in 4'ü root (`etapadmin`+sudo: `guc_tusu_yoksay`,
  `guc_tusu_uzun_basis_yoksay`, `uyku_hedefleri_maskeli`, `otomatik_giris`)
  ve bu koşula tabi değil; `ekran_karartma` da kullanıcı düzeyi
  (`root_gerekli=False`).
- Fiziksel güç tuşu davranışı SSH ile doğrulanamaz — yukarıya bkz.
- `tahta-234`/`tahta-235`/`tahta-236` sınıf değil (sınıfı atanmamış,
  client kurulu değil), `server/tahtalar.json`'da kayıtlı ama genelde ağda
  değil — script'in bunlar için "kontrol edilemedi" raporlaması normaldir.
  (Eski `tahta-244` 2026-09-17'de `fenlab` oldu; artık 8 kurulu tahtadan
  biri ve diğerleri gibi kontrol edilir.)

## Tırmanma yolu (belgelendi, ŞİMDİ UYGULANMADI)

Kullanıcı-düzeyi `gsettings` yeterli gelmezse (yeni kullanıcı profili,
öğretmenin GUI'den elle geri alması) bir sonraki basamak sistem-düzeyi
`dconf` kilitleme: `/etc/dconf/db/local.d/90-guc-tusu` (değer) +
`/etc/dconf/db/local.d/locks/90-guc-tusu` (kilit) +
`/etc/dconf/profile/user`'ın `system-db:local` satırı içermesi +
`dconf update`. Root düzeyi, kalıcı, GUI'den geri alınamaz — buna karşılık
ayrı bir onay ve muhtemelen yeniden oturum açma gerektirir. Bu iş
kapsamında YAPILMADI.

## Kapsam dışı (bilerek yapılmayanlar)

- Farabi client kurulumu → `server/farabi-kurulum.sh`
- `tahtayoklama` uygulama kurulumu → elle, bkz. `tahtayoklama/CLAUDE.md`
- `zil.json` / `ders_programi.json` dağıtımı →
  `tahtayoklama/dashboard/scripts/zil_yukle.py` (taşınmadı — bu,
  tahtayoklama'nın kendi veri akışı, OS provizyonu değil)
- ~~`ogretmen` kullanıcısının NOPASSWD asimetrisi normalleştirilmedi~~ —
  **2026-09-29'da kullanıcı kararıyla ÇÖZÜLDÜ:** asimetrinin kaynağı
  yalnızca 9-A'ydı (`ogretmen` NOPASSWD); artık 8 tahtanın hiçbirinde
  `ogretmen` sudo'lu değil. Yukarıdaki "2026-09-29 ham karşılaştırması"na
  bkz. Hâlâ `DUZELTMELER`'e eklenmedi (sudoers'a dokunan otomatik fix ayrı
  karar ister).
- `sleep-inactive-ac-type` — 2026-09-15 taramasında 7 tahtada da zaten
  `'nothing'` bulundu, ayrı bir fix'e gerek kalmadı.

## reboot_sudoers (2026-10-03)

`DUZELTMELER`'in son girdisi: `/etc/sudoers.d/farabi-reboot` içine
`etapadmin ALL=(root) NOPASSWD: /usr/bin/systemctl reboot` yazar — `etapadmin`
YALNIZCA bu tek komutu parolasız çalıştırabilir. Neden: Open WebUI "Farabi
Yönetim" aracı → dashboard `/api/ajan/yeniden-baslat`
(`tahtayoklama/dashboard/tahta_yeniden_baslat.py`) tahtada `sudo -n
/usr/bin/systemctl reboot` çalıştırıyor; 11-A, 12-A ve fenlab'da sudo parola
istiyordu. Kural geçici dosyada `visudo -cf` ile doğrulanmadan kurulmaz.
Komut metni dashboard'dakiyle birebir olmalı (sudoers argüman eşleşmesi tam).

Kullanıcı çalıştırır (önce kontrol):

    python3 tahtaayar/tahta_fix_uygula.py --sadece-kontrol
    python3 tahtaayar/tahta_fix_uygula.py --duzeltme reboot_sudoers

Geri alma (tahtada): `sudo rm /etc/sudoers.d/farabi-reboot`

Test: `cd tahtaayar && python3 -m unittest test_tahta_fix_uygula -v`
