#!/bin/bash
# server/mikrofonsuz_dagit.sh — 2026-09-25 mikrofonsuz mod dağıtımı.
#
# Her Farabi tahtasında:
#   1. kodu GitHub'dan çeker (~/.local/bin/farabiguncelle.sh)
#   2. config/api_keys.json'a "mikrofon": false yazar (dosya ekrana basılmaz)
#   3. config/zil.json'u tahtayoklama/data/zil.json'dan kopyalar
#      (e-Okul çizelgesi, 08:10–15:50 — client/config/zil.example.json ESKİ)
#   4. sürümü, ayarı ve zil okumasını doğrular
#
# Çalışan Farabi süreci yeniden BAŞLATILMAZ — yeni kod bir sonraki açılışta
# devreye girer (öğretmen Farabi'yi kapatıp açmalı).
#
# Kullanım:  bash server/mikrofonsuz_dagit.sh [tahta ...]   (varsayılan: 8 tahta)

set -uo pipefail
cd "$(dirname "$0")/.."

TAHTALAR=("$@")
[ ${#TAHTALAR[@]} -eq 0 ] && TAHTALAR=(9-A 9-B 10-A 11-A 11-B 12-A 12-B fenlab)
ZIL_B64=$(base64 -w0 tahtayoklama/data/zil.json)

for t in "${TAHTALAR[@]}"; do
    echo "== $t"
    timeout 120 server/tahta-ssh.sh "$t" "
        R=\$HOME/farabi; [ -d \$HOME/farabi/repo/.git ] && R=\$HOME/farabi/repo
        C=\$R/client
        \$HOME/.local/bin/farabiguncelle.sh >/dev/null 2>&1; echo \"  guncelle rc=\$?\"
        echo \"  surum: \$(git -C \$R log --oneline -1)\"
        python3 -c \"
import json
p='\$C/config/api_keys.json'
c=json.load(open(p, encoding='utf-8'))
c['mikrofon']=False
json.dump(c, open(p,'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('  mikrofon:', c['mikrofon'])
\"
        echo '$ZIL_B64' | base64 -d > \$C/config/zil.json
        cd \$C && ./venv/bin/python -c \"
from core import zil, tahta
print('  zil:', zil.ders_durumu().get('kisa') or '-', '| mikrofon_var:', tahta.mikrofon_var())
\" 2>/dev/null | tail -1
    " 2>&1 | grep -v '^$'
done
