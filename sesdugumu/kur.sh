#!/usr/bin/env bash
# Farabi'den: sesdugumu/'nu Bilgehan'a kopyalar ve farabi2-ses servisini
# kurar/yeniden başlatır. sudo şifresi istenir — kullanıcı çalıştırır:
#   ! ~/farabi-v2/sesdugumu/kur.sh
set -euo pipefail
HEDEF=ata@bilgehan.local
cd "$(dirname "$0")/.."
rsync -a --delete --exclude tests --exclude __pycache__ sesdugumu/ "$HEDEF:farabi2-ses/sesdugumu/"
ssh -t "$HEDEF" 'sudo install -m 644 ~/farabi2-ses/sesdugumu/farabi2-ses.service /etc/systemd/system/farabi2-ses.service && sudo systemctl daemon-reload && sudo systemctl enable farabi2-ses && sudo systemctl restart farabi2-ses'
echo "Bekleniyor (model yükleme + CUDA graph + 25 kalıp ısıtma, ~2-3 dk)..."
for _ in $(seq 1 40); do
  if curl -sf http://bilgehan.local:8060/saglik; then echo; exit 0; fi
  sleep 5
done
echo "HATA: /saglik yanıt vermedi — ssh $HEDEF journalctl -u farabi2-ses -n 50"
exit 1
