#!/usr/bin/env bash
# Farabi temasını (custom.css + ikonlar) Open WebUI'ye kurar (restart gerektirmez).
#
# Neden iki hedef: Open WebUI her açılışta site-packages/open_webui/static/
# içindeki dosyaları SİLİP frontend/static/'ten yeniden kopyalar
# (open_webui/config.py, "Static DIR" bölümü). Yani:
#   - frontend/static/  → açılışta kullanılan kaynak (kalıcı)
#   - static/           → şu an servis edilen kopya (anında etki)
# pip upgrade frontend/static'i de ezer; onu systemd drop-in'indeki
# ExecStartPre (farabi-tema.conf) her açılışta bu dizinden geri yükler.
set -euo pipefail

DIZIN="$(cd "$(dirname "$0")" && pwd)"
OW=/opt/open-webui/venv/lib/python3.12/site-packages/open_webui

for hedef in "$OW/frontend/static" "$OW/static"; do
  sudo install -m 644 -o openwebui -g openwebui "$DIZIN"/static/* "$hedef/"
  echo "kuruldu: $hedef ($(ls "$DIZIN"/static | wc -l) dosya)"
done

DROPIN_DIZIN=/etc/systemd/system/open-webui.service.d
if ! cmp -s "$DIZIN/farabi-tema.conf" "$DROPIN_DIZIN/farabi-tema.conf" 2>/dev/null; then
  sudo install -d "$DROPIN_DIZIN"
  sudo install -m 644 "$DIZIN/farabi-tema.conf" "$DROPIN_DIZIN/farabi-tema.conf"
  sudo systemctl daemon-reload
  echo "drop-in kuruldu: $DROPIN_DIZIN/farabi-tema.conf (daemon-reload yapıldı, restart YOK)"
fi
