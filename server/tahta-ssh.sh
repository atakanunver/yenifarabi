#!/bin/bash
# server/tahta-ssh.sh — server'dan herhangi bir kayıtlı tahtaya SSH ile
# bağlanmak/komut çalıştırmak için esnek, tek noktadan yardımcı script.
#
# 2026-08-19: 10 tahtaya ölçekleme altyapısının bir parçası — yeni bir
# tahta eklendiğinde yalnızca tahtalar.json'a bir satır eklemek yeterli,
# bu script'e dokunmaya gerek yok.
#
# Kullanım:
#   ./tahta-ssh.sh 9-A                     → interaktif SSH oturumu açar (ogretmen)
#   ./tahta-ssh.sh 9-A "komut buraya"      → tek komut çalıştırıp çıkar (ogretmen)
#   ./tahta-ssh.sh --admin 9-A "komut"     → admin kullanıcısıyla (etapadmin, sudo)
#   ./tahta-ssh.sh --liste                 → kayıtlı tüm tahtaları listeler
#
# 2026-08-22: --admin eklendi — paket kurulumu/sistem değişikliği gibi işler
# için etapadmin kullanılır, ogretmen'e sudo verilmez (kasıtlı ayrım, bkz.
# tahtalar.json açıklaması). etapadmin'in sudo'su NOPASSWD DEĞİL her tahtada
# — bazılarında (9-A, 231, 233, 236) sudo hâlâ parola istiyor, bazılarında
# (240, 242) istemiyor; bu script sudo'yu kendisi çağırmaz, komutunuzda
# gerekirse parolayı siz yönetin (bkz. tahtalar.json açıklaması).
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
    print(f\"  {derslik:10s} {bilgi['kullanici']}@{bilgi['ip']}  (admin: {bilgi.get('admin', '-')})\")
"
    exit 0
fi

ADMIN_MODU=0
if [ "${1:-}" = "--admin" ]; then
    ADMIN_MODU=1
    shift
fi

if [ $# -lt 1 ]; then
    echo "Kullanım: $0 [--admin] <derslik> [komut]   ya da   $0 --liste" >&2
    exit 1
fi

DERSLIK="$1"
shift

ALAN="kullanici"
[ "$ADMIN_MODU" -eq 1 ] && ALAN="admin"

BILGI=$(python3 -c "
import json, sys
veri = json.load(open('$KAYIT_DOSYASI'))
kayit = veri.get('$DERSLIK')
if not kayit:
    sys.exit(1)
kullanici = kayit.get('$ALAN') or kayit['kullanici']
print(kullanici, kayit['ip'])
") || { echo "HATA: '$DERSLIK' tahtalar.json'da kayıtlı değil. Liste için: $0 --liste" >&2; exit 1; }

read -r KULLANICI IP <<< "$BILGI"

if [ $# -eq 0 ]; then
    exec ssh -i "$SSH_KEY" -o ConnectTimeout=5 "${KULLANICI}@${IP}"
else
    exec ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=5 "${KULLANICI}@${IP}" "$@"
fi
