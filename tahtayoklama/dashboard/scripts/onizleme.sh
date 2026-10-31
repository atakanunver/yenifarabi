#!/bin/bash
# Yeniden tasarım dalını canlıya yazmadan :8098'de çalıştırır (salt-okunur önizleme).
# Canlı DB yalnız okunur (sqlite backup API); config canlıdan dosya dosya bağlanır.
set -euo pipefail

CANLI=/home/ata/farabi/tahtayoklama/dashboard
DIZIN="$(cd "$(dirname "$0")/.." && pwd)"
TMP=/tmp/farabi-onizleme
mkdir -p "$TMP"

python3 - "$CANLI/veri/yoklama_pano.db" "$TMP/yoklama_pano.db" <<'PY'
import sqlite3, sys
kaynak = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
hedef = sqlite3.connect(sys.argv[2])
kaynak.backup(hedef)
hedef.close(); kaynak.close()
PY

cd "$DIZIN"
if [ -L config ]; then
    :
elif [ -d config ]; then
    # config/ içinde izlenen dosya var; yalnız eksik canlı dosyaları bağla, git'ten gizle
    DISLA="$(git rev-parse --git-path info/exclude)"
    for f in "$CANLI"/config/*; do
        ad="$(basename "$f")"
        if [ ! -e "config/$ad" ]; then
            ln -s "$f" "config/$ad"
            echo "tahtayoklama/dashboard/config/$ad" >> "$DISLA"
        fi
    done
else
    ln -s "$CANLI/config" config
fi

export FARABI_ONIZLEME=1 FARABI_PANEL_DB="$TMP/yoklama_pano.db"
exec "$CANLI/venv/bin/uvicorn" app:app --host 0.0.0.0 --port 8098
