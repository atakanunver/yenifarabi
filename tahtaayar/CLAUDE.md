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

## Bilinen sınırlar

- `cinnamon_guc_tusu_yoksay` aktif bir `ogretmen` masaüstü oturumu
  (`/run/user/$(id -u)/bus` soketi) gerektirir — sıfırdan kurulmuş, hiç
  giriş yapılmamış bir tahtada bu fix "uygulanamadı" raporlar; o tahtada
  script ilk öğretmen girişinden SONRA tekrar çalıştırılmalı. Diğer üç fix
  (root, `etapadmin`+sudo) bu koşula tabi değil.
- Fiziksel güç tuşu davranışı SSH ile doğrulanamaz — yukarıya bkz.
- `tahta-234`/`tahta-235`/`tahta-236`/`tahta-244` sınıf değil (fen-lab/
  kütüphane/spor odası ya da eski/boşa çıkmış kayıt, bkz.
  `tahtayoklama/CLAUDE.md` "Faz 6"), `server/tahtalar.json`'da kayıtlı ama
  genelde ağda değil — script'in bunlar için "kontrol edilemedi" raporlaması
  normaldir.

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
- `ogretmen` kullanıcısının NOPASSWD asimetrisi (bazı tahtalarda `sudo -n`
  parolasız çalışıyor, bazılarında çalışmıyor) **normalleştirilmedi** —
  bu bir güvenlik kararı, provizyon temizliği değil; bilerek dokunulmadı.
- `sleep-inactive-ac-type` — 2026-09-15 taramasında 7 tahtada da zaten
  `'nothing'` bulundu, ayrı bir fix'e gerek kalmadı.
