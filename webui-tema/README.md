# Open WebUI — Farabi teması

`farabi.local:80`'deki Open WebUI (`open-webui.service`, `/opt/open-webui/venv`) için özel CSS.

- `static/` — **tek kaynak**; içindeki her dosya Open WebUI'nin `static/`'ine kopyalanır.
- `static/custom.css` — tema. Lacivert/çini mavisi (pano.css `#4f5eff`) + altın vurgu,
  8 köşeli yıldız deseni, lacivert tonlu gri skala. Açık/koyu/OLED temalarda çalışır.
  Dış font/CDN yok (okul ağı filtreli).
- `static/favicon*`, `apple-touch-icon.png`, `web-app-manifest-*.png`, `splash*.png` — Farabi
  logosu ikonları; `/mnt/farabi-data/farabi/farabilogo.jpg`'den `ikon_uret.py` üretir
  (`/opt/open-webui/venv/bin/python webui-tema/ikon_uret.py` — Pillow yalnızca o venv'de).
  Orijinal Open WebUI ikonlarının yedeği: `/opt/open-webui/data/orijinal-ikonlar/`.
- `kur.sh` — `static/*`'ı iki yere kopyalar + systemd drop-in'ini kurar. **Restart gerekmez**;
  tarayıcıda Ctrl+Shift+R yeterli.
- `farabi-tema.conf` — `/etc/systemd/system/open-webui.service.d/` drop-in'i: her açılışta
  `static/*`'ı `frontend/static/`'e geri yükler (pip upgrade sonrası kaybolmasın diye).

Değiştirmek: `static/custom.css`'i düzenle (logo için `ikon_uret.py`'yi çalıştır) → `./webui-tema/kur.sh`.

⚠️ Open WebUI her açılışta `open_webui/static/`'i silip `frontend/static/`'ten yeniden
doldurur — `static/custom.css`'e tek başına yazılan dosya ilk restart'ta kaybolur.

Kaldırmak: `sudo rm /etc/systemd/system/open-webui.service.d/farabi-tema.conf &&
sudo systemctl daemon-reload`, sonra `pip install --force-reinstall --no-deps open-webui==<sürüm>` (orijinal dosyalar geri gelir)
ve servisi yeniden başlat.

Logo/ad değişikliği lisans açısından serbest: Open WebUI lisansı ≤50 kullanıcılı (30 gün)
kurulumlarda marka değiştirmeye izin veriyor (2026-10-03: 2 kullanıcı). Kullanıcı sayısı 50'yi
aşarsa ikonlar orijinale döndürülmeli.
