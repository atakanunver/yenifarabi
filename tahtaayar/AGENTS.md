# tahtaayar
Yeni tahta kurulurken ya da mevcut tahtayı referans duruma getirirken ELLE çalıştırılan OS/oturum provizyon betiği (`tahta_fix_uygula.py`, test `test_tahta_fix_uygula.py`); ajan gerektirmez. `client/` ve `tahtayoklama/` ikisinden bağımsız ortak katman olduğu için ayrı üst düzey klasördedir.
- Tek kaynak: `DUZELTMELER` listesi yalnız burada (ikinci kopya açma). Parola `etapadmin_sifre` yalnız `tahtayoklama/dashboard/config/gizli.json`'da (gitignore'lu); betik önce `tahtaayar/config/gizli.json`'a bakar (şimdi yok), sonra oraya düşer. Parolayı başka dosyaya kopyalama, commit'leme.

## Çalıştırma
```bash
python3 tahtaayar/tahta_fix_uygula.py                                     # tüm tahtalar
python3 tahtaayar/tahta_fix_uygula.py --tahta 9-B                          # tek tahta
python3 tahtaayar/tahta_fix_uygula.py --sadece-kontrol                     # uygulamadan durum raporu
python3 tahtaayar/tahta_fix_uygula.py --duzeltme uyku_hedefleri_maskeli    # tek düzeltme
cd tahtaayar && python3 -m unittest test_tahta_fix_uygula -v               # test
```
- Ön koşul: `~/.ssh/id_ed25519_tahta`, `server/tahtalar.json` (tahta listesi/IP); yalnız stdlib, venv yok. Kullanıcı çalıştırır, önce `--sadece-kontrol`.

## DUZELTMELER (7)
- Root (`etapadmin` + `sudo -S`): `guc_tusu_yoksay`, `guc_tusu_uzun_basis_yoksay`, `uyku_hedefleri_maskeli`, `otomatik_giris`, `reboot_sudoers`.
- Kullanıcı düzeyi (`root_gerekli=False`, `ogretmen` oturumu, sudo YOK): `cinnamon_guc_tusu_yoksay`, `ekran_karartma`.
- `guc_tusu_yoksay`: `/etc/systemd/logind.conf.d/90-guc-tusu-yoksay.conf` → `HandlePowerKey=ignore` (varsayılan `poweroff`, kısa basış sistemi kapatıyordu). `guc_tusu_uzun_basis_yoksay`: `91-guc-tusu-uzun-basis.conf` → `HandlePowerKeyLongPress=ignore`.
- `cinnamon_guc_tusu_yoksay`: Cinnamon'un KENDİ güç tuşu eylemi (`org.cinnamon.settings-daemon.plugins.power` `button-power`) logind'den bağımsızdır; hedef `'nothing'` (kullanıcı kararı; `'blank'` seçilmedi). Güç tuşu için İKİ yol var, ikisi de kapalı olmalı.
- `ekran_karartma`: `sleep-display-ac` = 600 (10 dk boşta karartma). Sürüklenme olabiliyor (fenlab'da 0 bulundu), bu yüzden yönetilir. Güç tuşuyla ilgisi yok.
- `otomatik_giris`: `/etc/lightdm/lightdm.conf.d/50-tahta-autologin.conf` (`[Seat:*]`, `autologin-user=ogretmen`, `autologin-user-timeout=0`, `autologin-session=cinnamon`; içerik çalışan tahtalardan alındı, uydurma değil). `cinnamon_guc_tusu_yoksay`'ın ön koşulu.
- `reboot_sudoers`: `/etc/sudoers.d/farabi-reboot` ← `etapadmin ALL=(root) NOPASSWD: /usr/bin/systemctl reboot` (YALNIZ bu komut). Gerekçe: dashboard `POST /api/ajan/yeniden-baslat` (`tahtayoklama/dashboard/tahta_yeniden_baslat.py`) ve panelin `/admin/uzaktan/yeniden-baslat`'ı tahtada `sudo -n /usr/bin/systemctl reboot` çalıştırır. Komut metni dashboard'dakiyle BİREBİR olmalı (sudoers argüman eşleşmesi tam). Kural geçici dosyada `visudo -cf` ile doğrulanmadan kurulmaz.
  - Geri alma (tahtada): `sudo rm /etc/sudoers.d/farabi-reboot`.
  - ⚠️ `--sadece-kontrol` yalnız dosyada satır var mı bakar (`grep`); sudo'nun kuralı etkin saydığını göstermez. Etkin yetki `etapadmin` olarak `sudo -n -l /usr/bin/systemctl reboot` ile doğrulanmalı.

## Tuzaklar / bilinen sınırlar
- ⚠️ Fiziksel güç tuşu davranışı SSH ile test EDİLEMEZ; son kabul Atakan'da, fiziksel tahtada. Güç tuşu fix'inin "kendi kendine kapanma" şikâyetlerinin kanıtlanmış kök nedeni olduğu iddia EDİLMEZ (elle açma/kapamalar yanlış atfedilmiş olabilir).
- `cinnamon_guc_tusu_yoksay` aktif `ogretmen` masaüstü oturumu (`/run/user/$(id -u)/bus`) ister; hiç giriş yapılmamış tahtada "uygulanamadı" döner → ilk öğretmen girişinden sonra tekrar çalıştır. `ekran_karartma` da aynı koşulda.
- `--sadece-kontrol` yalnız `DUZELTMELER`'e bakar; "hepsi ✓" tahtaların aynı olduğunu göstermez. Gerçek farklar için salt-okunur tarama betiğini birkaç tahtada (referans 9-B/12-B) çalıştırıp çıktıları `diff`'le (sistem birimleri, sudoers, `/var/log/lightdm/lightdm.log`, `loginctl`, `gsettings list-recursively`). `ogretmen` sistem journal'ını ve `/var/log/lightdm/`'i okuyamaz; `etapadmin`+sudo gerekir.
- Hiçbir tahtada ayrı VNC birimi (`x11vnc.service`) olmamalı (hatalı birim 9-A'da fare/klavye/dokunmatik kilitlenmesi yapmıştı); Veyon'un kendi x11vnc'si (port 11200) normal.
- Kilit ekranı = "otomatik giriş yok" gibi görünür: oturum kilitlenirse (`custom-screensaver-command = 'dm-tool lock'`) LightDM greeter VT8'de öne geçer, `ogretmen` VT7'de arkada kalır. Teşhis: `loginctl show-session <id> -p Active`. Kurtarma (`etapadmin` ile): `sudo loginctl activate <ogretmen-oturum-id>`.
- Sudo referansı: `/etc/sudoers.d/farabi-nopasswd` = `etapadmin ALL=(ALL) NOPASSWD: ALL`; `ogretmen` `sudo` grubunda DEĞİL, `sudo -n` başarısız. `etapadmin` parolasız sudo HER tahtada yok (2026-09-29: 11-A, 12-A, fenlab parolalı); betikler `gizli.json::etapadmin_sifre` ile `sudo -S`'e düşer. `ogretmen` sudo'su için otomatik fix YOK; sudoers'a dokunan yeni fix ayrı karar ister.
- fenlab: `veyon-watchdog.timer` yok (diğer tahtalarda var), `sleep-display-battery` 0 — dokunulmadı.
- `tahta-234/235/236` sınıf değil (client kurulu değil), `server/tahtalar.json`'da kayıtlı, genelde ağda yok; "kontrol edilemedi" normal. Kapalı tahtalar (ör. 11-B) erişilemez.
- Sistem düzeyi dconf kilitleme (`/etc/dconf/db/local.d/90-guc-tusu` + `locks/` + `/etc/dconf/profile/user` + `dconf update`) tırmanma yolu olarak belgeli, UYGULANMADI; root düzeyi, kalıcı, ayrı onay ister.

## Kapsam dışı
- Farabi client kurulumu → `server/farabi-kurulum.sh`; `tahtayoklama` kurulumu → elle (`tahtayoklama/CLAUDE.md`); `zil.json`/`ders_programi.json` dağıtımı → `tahtayoklama/dashboard/scripts/zil_yukle.py`.
