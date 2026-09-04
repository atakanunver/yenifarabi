#!/usr/bin/env bash
# Güncel client Git deposunda çalıştırılır; servis varsa güvenli biçimde yeniler.
set -euo pipefail

PROJECT_DIR="${FARABI_CLIENT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
BRANCH="${FARABI_BRANCH:-master}"
SERVICE="${FARABI_CLIENT_SERVICE:-farabi-client.service}"

cd "$PROJECT_DIR"
git fetch origin "$BRANCH"

if git diff --quiet HEAD "origin/$BRANCH"; then
    echo "Farabi client zaten güncel."
    exit 0
fi

git pull --ff-only origin "$BRANCH"
venv/bin/python3 -m pip install -r requirements.txt

if systemctl --user is-enabled --quiet "$SERVICE"; then
    systemctl --user restart "$SERVICE"
    echo "Farabi client güncellendi ve $SERVICE yeniden başlatıldı."
else
    echo "Farabi client güncellendi. Otomatik yeniden başlatma için kullanıcı servisini etkinleştirin:"
    echo "  systemctl --user enable --now $SERVICE"
    echo "Ya da çalışan uygulamayı kapatıp ./farabi_start.sh ile yeniden açın."
fi
