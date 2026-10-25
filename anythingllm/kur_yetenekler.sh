#!/bin/bash
# Atos agent yeteneklerini AnythingLLM'e dağıtır (tekrar çalıştırılabilir).
#   sudo olmadan çalıştır: ./kur_yetenekler.sh   (anahtar okuma için ata kullanıcısı, yazma için sudo)
# plugin.json şablonlarındaki __SEMA__ (sema_aciklamasi.txt) ve __ANAHTAR__ (dashboard okul.json::anahtar) burada doldurulur;
# anahtar depoya yazılmaz, yalnızca /opt/anythingllm/storage altına (0600, anythingllm sahibi).
set -euo pipefail
AD="$(cd "$(dirname "$0")" && pwd)"
HEDEF=/opt/anythingllm/storage/plugins/agent-skills
OKUL_JSON=/home/ata/farabi/tahtayoklama/dashboard/config/okul.json
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
python3 - "$AD" "$TMP" "$OKUL_JSON" <<'PY'
import json, shutil, sys, pathlib
ad, tmp, okul = map(pathlib.Path, sys.argv[1:4])
sema = (ad / "sema_aciklamasi.txt").read_text(encoding="utf-8")
anahtar = json.loads(okul.read_text(encoding="utf-8"))["anahtar"]
for d in (ad / "skills").iterdir():
    if not d.is_dir():
        continue
    hedef = tmp / d.name
    shutil.copytree(d, hedef)
    pj = hedef / "plugin.json"
    if pj.exists():
        pj.write_text(pj.read_text(encoding="utf-8").replace("__SEMA__", json.dumps(sema, ensure_ascii=False)[1:-1]).replace("__ANAHTAR__", anahtar), encoding="utf-8")
PY
sudo mkdir -p "$HEDEF"
sudo cp -r "$TMP"/. "$HEDEF"/
sudo chown -R anythingllm:anythingllm /opt/anythingllm/storage/plugins
sudo find "$HEDEF" -name plugin.json -exec chmod 600 {} \;
echo "yetenekler kuruldu: $(sudo ls "$HEDEF" | tr "\n" " ")"
