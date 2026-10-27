# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Bu dizin ne?
Giriş kiosku (yüz tanıma PC'si, `kiosk.local`, LAN `192.168.23.254`) için dijital bilgi panosunun kaynakları. **Kod Farabi sunucusunda durur ama kiosk'ta koşar**: `/home/ata/farabi` içindeki servislerin parçası değil, burada restart ile deploy edilmez. Kiosk'ta dosyalar `/home/atakan/` altında (`web/` pano içeriği, `PANO_WEB` ile değişir); buradaki kopya ile kiosk'taki canlı kopyanın senkronu elle yapılır — değiştirmeden önce kiosk'taki sürümle farkı kontrol et. Ortak kurallar için üst dizindeki `../CLAUDE.md`.

Üç dosya, hepsi **yalnızca stdlib** (bağımlılık/CDN/yeni kütüphane yok):
- `pano_server.py` — pano web servisi (port 5000). `web/` kökünü sunar (`ROOT = ../web`, yani kiosk'ta `pano_server.py`'nin bir üst dizinindeki `web/`; bu repoda `web/` YOK). `/` istek kaynağına göre bölünür: localhost (kiosk'un kendi Chrome'u) → `zemin.html` (yüz tanıma penceresinin düz zemini, CPU tasarrufu), LAN → `index.html`. `/api/resimler` = `panoresim/` listesi. Arka plan iş parçacığı 5 dk'da bir `data/config.json::farabi_url`'den (okul servisi `/api/pano`, `farabi.local:9090`) `program`, `duyurular`, `belirli_gunler` çekip `data/*.json`'a atomik yazar; boş/bozuk veri yazılmaz, hata `journalctl`'e düşer. `zil.json` senkronda YOK (elle çekildi).
- `okul_panel.py` — kiosk yönetim paneli (port 9100, Basic auth, `/etc/okul-panel.env`: `PANEL_SIFRE` zorunlu, `PANEL_SERVISLER`, `PANEL_SURECLER`, `PANO_WEB`, `PANO_SAHIP`). `/` sistem durumu + servis log/restart (beyaz liste); `/pano` pano içerik yönetimi (nöbetçi çizelgesi, YKS tarihi, slayt süresi, bilgi kartları, slayt resmi yükle/sil). Farabi dashboard'u sol menüden `:9100/pano`'ya bağlanır.
- `index.html` — tek dosya, 1920×1080 sabit tasarım ekrana ölçeklenir; veriyi `data/*.json` ve `/api/resimler`'den `fetch` ile çeker. Tarayıcı kodu ES5 tarzı (`var`, `function`) — komşu stile uy.

## Komutlar
- Test (kiosk'un kendi venv'i yok; okul venv'ini kullan): `../okul/venv/bin/python -m pytest tests -q`; tek test: `... tests/test_okul_panel.py::test_adi -q`. Testler `PANEL_SIFRE`'yi kendisi ayarlar, `tmp_path` altında sahte `web/` kurar.
- Elle çalıştırma: `PANEL_SIFRE=x PANO_WEB=/tmp/web python3 okul_panel.py` / `python3 pano_server.py [port]`.

## Dikkat
- `/pano` yazımları `_json_yaz` üzerinden gider: önce `.bak-<zaman>` yedeği (son 5 kalır), sonra `.tmp` + `os.replace` (atomik), root çalışıyorsa `PANO_SAHIP`'e chown. Yeni yazma yolu eklersen bunu kullan; `config.json`'daki bilinmeyen anahtarlar (ör. `farabi_url`, `_aciklama`) korunmalı — okuyup güncelleyip yaz.
- POST güvenliği: Basic auth + Origin/Host eşleşmesi + gövde boyut sınırı (`RESIM_LIMIT` 6 MB, `RESIM_ADEDI` 40). Resim yükleme uzantıyı dosya imzasından (magic bytes) doğrular. Bu davranışları `tests/test_okul_panel.py` kilitler; gevşetme.
- `pano_server.py` dizin listelemeyi kapatır (404), yalnızca `web/` sunar; kiosk CPU'su zayıf, animasyon/ağır iş ekleme.
- Veri akışı: Farabi/okul `/api/pano` → `pano_server.senkron` → `web/data/*.json` → `index.html`. Pano bayat görünürse önce `config.json::farabi_url` ve kiosk `journalctl` (2026-10-26 olayı: eski IP, hata yutuluyordu; `DECISIONS.md`).