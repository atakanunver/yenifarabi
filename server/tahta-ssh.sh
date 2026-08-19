#!/bin/bash
# server/tahta-ssh.sh — server'dan herhangi bir kayıtlı tahtaya SSH ile
# bağlanmak/komut çalıştırmak için esnek, tek noktadan yardımcı script.
#
# 2026-08-19: 10 tahtaya ölçekleme altyapısının bir parçası — yeni bir
# tahta eklendiğinde yalnızca tahtalar.json'a bir satır eklemek yeterli,
# bu script'e dokunmaya gerek yok.
#
# Kullanım:
#   ./tahta-ssh.sh 9-A                     → interaktif SSH oturumu açar
#   ./tahta-ssh.sh 9-A "komut buraya"      → tek komut çalıştırıp çıkar
#   ./tahta-ssh.sh --liste                 → kayıtlı tüm tahtaları listeler
#
# Örnek — bir tahtaya push tetikleme (9-A zaten kendi farabi-simdi-gonder
# alias'ına sahip, ama uzaktan da tetiklenebilir):
#   ./tahta-ssh.sh 9-A '~/farabi/farabi-push.sh'
#
# Örnek — yeni bir tahtada pull tetikleme (farabi-kurulum.sh önceden o
# tahtada kurulmuş olmalı, bkz. client/farabi-kurulum.sh):
#   ./tahta-ssh.sh 9-B '~/.local/bin/farabiguncelle.sh'

set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KAYIT_DOSYASI="$BASE_DIR/tahtalar.json"
SSH_KEY="$HOME/.ssh/id_ed25519_tahta"

if [ ! -f "$KAYIT_DOSYASI" ]; then
    echo "HATA: $KAYIT_DOSYASI bulunamadı." >&2
    exit 1
fi

if [ "${1:-}" = "--liste" ]; then
    echo "Kayıtlı tahtalar:"
    python3 -c "
import json
veri = json.load(open('$KAYIT_DOSYASI'))
for derslik, bilgi in veri.items():
    if derslik.startswith('_'):
        continue
    print(f\"  {derslik:8s} {bilgi['kullanici']}@{bilgi['ip']}\")
"
    exit 0
fi

if [ $# -lt 1 ]; then
    echo "Kullanım: $0 <derslik> [komut]   ya da   $0 --liste" >&2
    exit 1
fi

DERSLIK="$1"
shift

BILGI=$(python3 -c "
import json, sys
veri = json.load(open('$KAYIT_DOSYASI'))
kayit = veri.get('$DERSLIK')
if not kayit:
    sys.exit(1)
print(kayit['kullanici'], kayit['ip'])
") || { echo "HATA: '$DERSLIK' tahtalar.json'da kayıtlı değil. Liste için: $0 --liste" >&2; exit 1; }

read -r KULLANICI IP <<< "$BILGI"

if [ $# -eq 0 ]; then
    exec ssh -i "$SSH_KEY" -o ConnectTimeout=5 "${KULLANICI}@${IP}"
else
    exec ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=5 "${KULLANICI}@${IP}" "$@"
fi
