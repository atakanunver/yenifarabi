#!/usr/bin/env bash
# Geliştirme: sesdugumu/'nu Bilgehan'a kopyalayıp orada testleri koşar.
# Kullanım: sesdugumu/test_uzak.sh [pytest argümanları]   (varsayılan: -m "not gpu")
set -euo pipefail
cd "$(dirname "$0")/.."
rsync -a --delete --exclude __pycache__ sesdugumu/ ata@bilgehan.local:farabi2-ses/sesdugumu/
ARG="${*:--m 'not gpu'}"
ssh -o BatchMode=yes ata@bilgehan.local "cd ~/farabi2-ses && HF_HOME=/home/ata/chatterbox-tts/.cache/huggingface HF_HUB_OFFLINE=1 ~/chatterbox-tts/.venv/bin/python -m pytest sesdugumu/tests -q $ARG"
