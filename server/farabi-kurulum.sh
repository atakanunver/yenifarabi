#!/bin/bash
# Akıllı tahtalarda Farabi sunucusuyla günlük otomatik senkronizasyon kurulumu.
# Her tahtada bir kez çalıştırılır. SSH şifresi bir kez (ssh-copy-id adımında) istenecek.
#
# 2026-08-30: server-merkezli mimariye geçişle (9-A pilotu bitti, bkz.
# client/CLAUDE.md "9-A ↔ server code sync") CANONICAL hâle getirildi —
# artık yalnızca bir tahtanın diskinde yaşayan bir kopya değil,
# server/farabi-kurulum.sh olarak git'te. Aynı oturumda iki gerçek eksiklik
# giderildi:
#   1) Eski exclude listesi yalnızca config/api_keys.json(.zip)'i koruyordu —
#      server'ın kendi client/ çalışma kopyasının (geliştirme için orada
#      duran) venv/, logs/, .pytest_cache/, __pycache__/, memory/ gibi
#      dizinleri --delete ile tahtaya sızıp yerelini SİLEBİLİRDİ (9-A'da
#      --dry-run ile yakalandı, canlı çalıştırılmadan). Şimdi tam simetrik.
#   2) Heartbeat hiç kurulmuyordu (server/client_durum.py::heartbeat
#      2026-08-18'de yazılmış ama hiçbir board tarafında çağıran yoktu) —
#      artık bu script hem pull hem heartbeat cron'unu kuruyor, GET
#      /api/client/durum ilk kez gerçek veri görüyor.
set -euo pipefail

# --- Ayarlar (gerekirse değiştirin) ---
REMOTE_USER="ata"
REMOTE_HOST="farabi.local"
REMOTE_PATH="~/farabi/client/"
LOCAL_PATH="$HOME/farabi/client/"
SYNC_TIME="20:00"          # HH:MM — günlük tam pull
SSH_KEY="$HOME/.ssh/id_ed25519"
SYNC_SCRIPT="$HOME/.local/bin/farabiguncelle.sh"
HEARTBEAT_SCRIPT="$HOME/.local/bin/farabi-heartbeat.sh"
LOG_FILE="$HOME/.local/share/farabi-sync.log"
HEARTBEAT_LOG="$HOME/.local/share/farabi-heartbeat.log"
COMMIT_FILE="$HOME/.local/share/farabi-client-commit"
HEARTBEAT_INTERVAL_DK=15   # her 15 dakikada bir heartbeat

echo "== Farabi Senkronizasyon Kurulumu ($(hostname)) =="

# 1) SSH anahtarı yoksa oluştur
if [ ! -f "$SSH_KEY" ]; then
    echo "[1/5] SSH anahtarı oluşturuluyor..."
    ssh-keygen -t ed25519 -f "$SSH_KEY" -N "" -C "$(hostname)-farabi-sync"
else
    echo "[1/5] SSH anahtarı zaten mevcut, atlanıyor."
fi

# 2) Public key'i uzak sunucuya kopyala (parola bir kez istenecek)
echo "[2/5] Public key ${REMOTE_HOST} sunucusuna kopyalanıyor (parola istenecek)..."
ssh-copy-id -i "${SSH_KEY}.pub" "${REMOTE_USER}@${REMOTE_HOST}"

# 3) Pull (senkronizasyon) scriptini yaz
mkdir -p "$(dirname "$SYNC_SCRIPT")" "$(dirname "$LOG_FILE")" "$LOCAL_PATH"
cat > "$SYNC_SCRIPT" <<EOF
#!/bin/bash
# server -> board pull. Yön DAİMA bu — server tek doğruluk kaynağı, bkz.
# root CLAUDE.md "Kural 1" ve client/CLAUDE.md "9-A ↔ server code sync".
echo "\$(date '+%F %T') - pull başladı" >> "$LOG_FILE"
rsync -avz --delete \\
    --exclude "venv/" \\
    --exclude "__pycache__/" \\
    --exclude "*.pyc" \\
    --exclude ".pytest_cache/" \\
    --exclude "logs/" \\
    --exclude "icerik/" \\
    --exclude "kitaplar/" \\
    --exclude "YKS/" \\
    --exclude "memory/" \\
    --exclude "config/api_keys.json" \\
    --exclude "config/api_keys.json.zip" \\
    --exclude "okul dosyaları/" \\
    --exclude "*.pdf" \\
    --exclude "/Farabi.zip" \\
    -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new" \\
    "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}" "${LOCAL_PATH}" >> "$LOG_FILE" 2>&1
CIKIS=\$?
echo "\$(date '+%F %T') - pull bitti (çıkış kodu: \$CIKIS)" >> "$LOG_FILE"

# Bu tahtanın az önce hangi sürümü çektiğini kaydet — heartbeat bunu okur.
# "kısa-hash+Ndirty": sunucuda commit edilmemiş client/ değişikliği varsa
# (server-merkezli iş akışında normal — bkz. client/CLAUDE.md'deki
# "auto-commit boşluğu" notu) bunu SAKLAMAK yerine AÇIKÇA işaretliyoruz;
# yanlış bir "şu commit'i çalıştırıyor" izlenimi vermek, hiç göstermemekten
# daha kötü.
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "${REMOTE_USER}@${REMOTE_HOST}" '
    cd ~/farabi &&
    HASH=\$(git log -1 --format=%h -- client/ 2>/dev/null || echo "bilinmiyor") &&
    KIRLI=\$(git status --short client/ 2>/dev/null | wc -l) &&
    if [ "\$KIRLI" -gt 0 ]; then echo "\${HASH}+\${KIRLI}dirty"; else echo "\$HASH"; fi
' > "$COMMIT_FILE" 2>/dev/null || echo "bilinmiyor" > "$COMMIT_FILE"
EOF
chmod +x "$SYNC_SCRIPT"
echo "[3/5] Pull scripti yazıldı: $SYNC_SCRIPT"

# 4) Heartbeat scriptini yaz — server/client_durum.py::heartbeat'e POST eder.
#    "Farabi asla dersi bozmaz": main.py'ye HİÇ dokunmaz, ayrı bir cron.
#    Hata olursa yutulur (server zaten ulaşılamazsa sessiz geçer).
cat > "$HEARTBEAT_SCRIPT" <<EOF
#!/bin/bash
KEYS="$LOCAL_PATH/config/api_keys.json"
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
COMMIT=\$(cat "$COMMIT_FILE" 2>/dev/null || echo "")
[ -z "\$DERSLIK" ] && exit 0   # derslik tanımsızsa raporlanacak kimlik yok, sessizce çık
curl -s -m 5 -X POST "\${SUNUCU}/api/client/heartbeat" \\
    -H "Content-Type: application/json" \\
    -d "{\\"derslik\\":\\"\$DERSLIK\\",\\"commit\\":\\"\$COMMIT\\",\\"hostname\\":\\"\$(hostname)\\",\\"ip\\":\\"\$(hostname -I 2>/dev/null | awk '{print \$1}')\\"}" \\
    >> "$HEARTBEAT_LOG" 2>&1
echo "" >> "$HEARTBEAT_LOG"
EOF
chmod +x "$HEARTBEAT_SCRIPT"
echo "[4/5] Heartbeat scripti yazıldı: $HEARTBEAT_SCRIPT"

# 5) crontab: günlük pull + periyodik heartbeat (varsa tekrarlamadan güncelle)
CRON_HOUR=$(echo "$SYNC_TIME" | cut -d: -f1)
CRON_MIN=$(echo "$SYNC_TIME" | cut -d: -f2)
SYNC_LINE="$CRON_MIN $CRON_HOUR * * * $SYNC_SCRIPT"
HEARTBEAT_LINE="*/$HEARTBEAT_INTERVAL_DK * * * * $HEARTBEAT_SCRIPT"
( crontab -l 2>/dev/null | grep -vF "$SYNC_SCRIPT" | grep -vF "$HEARTBEAT_SCRIPT" || true
  echo "$SYNC_LINE"
  echo "$HEARTBEAT_LINE" ) | crontab -
echo "[5/5] Crontab güncellendi: pull her gün ${SYNC_TIME}'de, heartbeat her ${HEARTBEAT_INTERVAL_DK} dakikada."

echo
echo "Kurulum tamamlandı."
echo "Elle test etmek için:"
echo "  $SYNC_SCRIPT && tail -20 $LOG_FILE"
echo "  $HEARTBEAT_SCRIPT && tail -5 $HEARTBEAT_LOG"
