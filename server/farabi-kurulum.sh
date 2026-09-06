#!/bin/bash
# Akıllı tahtalarda Farabi client'ının GitHub'dan doğrudan otomatik
# senkronizasyon kurulumu. Her tahtada bir kez çalıştırılır.
#
# 2026-09-05: rsync tabanlı server->board pull KALICI OLARAK İPTAL EDİLDİ
# (kullanıcı kararı: "tahtalar server'dan değil GitHub'dan çeksin, rsync
# iptal") — bkz. root CLAUDE.md ve docs/mimari.md §0. Yeni model:
#   GitHub (github.com/atakanunver/yenifarabi, PUBLIC) = tek doğru kaynak.
#   Her tahta kendi git checkout'unu doğrudan GitHub'dan çeker/fetch eder.
#   farabi.local artık bu akışın İÇİNDE DEĞİL — server kendi payı için
#   (server/ kodu) ayrıca GitHub'dan çeker, ama board güncellemesi buna
#   bağlı değil, server çökse/kapansa bile tahtalar GitHub'a ulaştığı
#   sürece güncellenir.
# Repo PUBLIC olduğu için tahta tarafında kimlik doğrulama GEREKMİYOR —
# önceki sürümdeki ssh-keygen/ssh-copy-id adımları (yalnızca rsync'in
# server'a SSH erişimi içindi) bu yüzden tamamen kaldırıldı. Heartbeat'in
# okuduğu commit hash artık GERÇEK bir GitHub commit'i (önceden server'a
# SSH ile sorulup server'ın kendi lokal git durumu okunuyordu — o dolaylı
# yol da gereksizleşti, tahta artık kendi `git rev-parse HEAD`'ini okuyor).
set -euo pipefail

# --- Ayarlar (gerekirse değiştirin) ---
REPO_URL="https://github.com/atakanunver/yenifarabi.git"
BOARD_REPO="$HOME/farabi"
CLIENT_PATH="$BOARD_REPO/client"
SYNC_TIME="20:00"          # HH:MM — günlük tam pull
SYNC_SCRIPT="$HOME/.local/bin/farabiguncelle.sh"
HEARTBEAT_SCRIPT="$HOME/.local/bin/farabi-heartbeat.sh"
LOG_FILE="$HOME/.local/share/farabi-sync.log"
HEARTBEAT_LOG="$HOME/.local/share/farabi-heartbeat.log"
COMMIT_FILE="$HOME/.local/share/farabi-client-commit"
HEARTBEAT_INTERVAL_DK=15   # her 15 dakikada bir heartbeat

echo "== Farabi Senkronizasyon Kurulumu ($(hostname)) — GitHub tabanlı =="

# 1) Board repo yoksa: yalnızca client/ (sparse-checkout, cone modu) klonlanır.
#    server/ , docs/ , benchmark/ gibi tahtada hiç gerekmeyen dizinler hiç
#    diske inmez — partial clone (--filter=blob:none) ile de trafik azaltılır.
mkdir -p "$(dirname "$SYNC_SCRIPT")" "$(dirname "$LOG_FILE")"
if [ ! -d "$BOARD_REPO/.git" ]; then
    echo "[1/4] Repo klonlanıyor (yalnızca client/, sparse-checkout)..."
    git clone --no-checkout --filter=blob:none "$REPO_URL" "$BOARD_REPO"
    (
        cd "$BOARD_REPO"
        git sparse-checkout init --cone
        git sparse-checkout set client
        git checkout master
    )
else
    echo "[1/4] Repo zaten mevcut ($BOARD_REPO), klonlama atlanıyor."
fi

# 2) Pull (senkronizasyon) scriptini yaz — artık server'a hiç dokunmaz.
cat > "$SYNC_SCRIPT" <<EOF
#!/bin/bash
# GitHub -> board pull. Yön DAİMA bu — GitHub tek doğruluk kaynağı, bkz.
# root CLAUDE.md ve docs/mimari.md §0 (2026-09-05, rsync iptal edildi).
cd "$BOARD_REPO" || exit 1
echo "\$(date '+%F %T') - pull başladı" >> "$LOG_FILE"
git fetch origin >> "$LOG_FILE" 2>&1
# Yalnızca TRACKED dosyalar sıfırlanır — config/api_keys.json, memory/,
# logs/, icerik/, kitaplar/, YKS/ zaten client/.gitignore'da, dokunulmaz.
git reset --hard origin/master >> "$LOG_FILE" 2>&1
CIKIS=\$?
echo "\$(date '+%F %T') - pull bitti (çıkış kodu: \$CIKIS)" >> "$LOG_FILE"

# Bu tahtanın az önce hangi sürümü çektiğini kaydet — heartbeat bunu okur.
# Artık gerçek bir GitHub commit hash'i (önceki sürümde server'a SSH ile
# sorulup server'ın kendi lokal git durumu okunuyordu, dolaylıydı).
git rev-parse --short HEAD > "$COMMIT_FILE" 2>/dev/null || echo "bilinmiyor" > "$COMMIT_FILE"
EOF
chmod +x "$SYNC_SCRIPT"
echo "[2/4] Pull scripti yazıldı: $SYNC_SCRIPT"

# 3) Heartbeat scriptini yaz — server/client_durum.py::heartbeat'e POST eder.
#    "Farabi asla dersi bozmaz": main.py'ye HİÇ dokunmaz, ayrı bir cron.
#    Hata olursa yutulur (server zaten ulaşılamazsa sessiz geçer).
cat > "$HEARTBEAT_SCRIPT" <<EOF
#!/bin/bash
KEYS="$CLIENT_PATH/config/api_keys.json"
DERSLIK=\$(python3 -c "import json,sys
try:
    print(json.load(open(sys.argv[1])).get('derslik','') or '')
except Exception:
    print('')" "\$KEYS" 2>/dev/null)
SUNUCU=\$(python3 -c "import json,sys
try:
    print(json.load(open(sys.argv[1])).get('sunucu_url','') or 'http://127.0.0.1:8000')
except Exception:
    print('http://127.0.0.1:8000')" "\$KEYS" 2>/dev/null)
ANAHTAR=\$(python3 -c "import json,sys
try:
    print(json.load(open(sys.argv[1])).get('tahta_anahtari','') or '')
except Exception:
    print('')" "\$KEYS" 2>/dev/null)
COMMIT=\$(cat "$COMMIT_FILE" 2>/dev/null || echo "")
[ -z "\$DERSLIK" ] && exit 0   # derslik tanımsızsa raporlanacak kimlik yok, sessizce çık
# /api/client/heartbeat auth.dogrula_tahta'ya bağlı (server/client_durum.py) —
# X-Farabi-Board-Key olmadan her zaman 401 alınırdı (2026-09-06'da bulundu,
# ilk sürümde eksikti).
curl -s -m 5 -X POST "\${SUNUCU}/api/client/heartbeat" \\
    -H "Content-Type: application/json" \\
    -H "X-Farabi-Board-Key: \$ANAHTAR" \\
    -d "{\\"derslik\\":\\"\$DERSLIK\\",\\"commit\\":\\"\$COMMIT\\",\\"hostname\\":\\"\$(hostname)\\",\\"ip\\":\\"\$(hostname -I 2>/dev/null | awk '{print \$1}')\\"}" \\
    >> "$HEARTBEAT_LOG" 2>&1
echo "" >> "$HEARTBEAT_LOG"
EOF
chmod +x "$HEARTBEAT_SCRIPT"
echo "[3/4] Heartbeat scripti yazıldı: $HEARTBEAT_SCRIPT"

# 4) crontab: günlük pull + periyodik heartbeat (varsa tekrarlamadan güncelle)
CRON_HOUR=$(echo "$SYNC_TIME" | cut -d: -f1)
CRON_MIN=$(echo "$SYNC_TIME" | cut -d: -f2)
SYNC_LINE="$CRON_MIN $CRON_HOUR * * * $SYNC_SCRIPT"
HEARTBEAT_LINE="*/$HEARTBEAT_INTERVAL_DK * * * * $HEARTBEAT_SCRIPT"
( crontab -l 2>/dev/null | grep -vF "$SYNC_SCRIPT" | grep -vF "$HEARTBEAT_SCRIPT" || true
  echo "$SYNC_LINE"
  echo "$HEARTBEAT_LINE" ) | crontab -
echo "[4/4] Crontab güncellendi: pull her gün ${SYNC_TIME}'de, heartbeat her ${HEARTBEAT_INTERVAL_DK} dakikada."

echo
echo "Kurulum tamamlandı."
echo "Elle test etmek için:"
echo "  $SYNC_SCRIPT && tail -20 $LOG_FILE"
echo "  $HEARTBEAT_SCRIPT && tail -5 $HEARTBEAT_LOG"
