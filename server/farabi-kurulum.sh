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

# İsteğe bağlı argümanlar — verilirse config/api_keys.json'daki ilgili
# alanlar otomatik doldurulur (gemini_api_keys HARİÇ — o hep elle girilir,
# bkz. 4. adımın sonundaki not). Verilmezse dosya .example.json'dan
# kopyalanır ve alanlar boş bırakılır, elle doldurulması gerekir.
#   $1 = derslik (ör. "9-B")
#   $2 = sunucu_url (ör. "http://192.168.23.252:8000")
#   $3 = tahta_anahtari (server/config/api_keys.json'daki board_keys[derslik]
#        ile BİREBİR aynı olmalı — bu script'in kendisi üretmez/yazmaz)
DERSLIK="${1:-}"
SUNUCU_URL="${2:-}"
TAHTA_ANAHTARI="${3:-}"

echo "== Farabi Senkronizasyon Kurulumu ($(hostname)) — GitHub tabanlı =="

# 0) Ön koşul kontrolü — yalnızca RAPORLAR, sudo çağırmaz (bu script çoğu
#    tahtada sudo'suz `ogretmen` kullanıcısıyla çalışır, bkz. tahtalar.json).
#    12-A kurulumunda (2026-09-06, DECISIONS.md) bunların hepsi elle,
#    `etapadmin` + sudo ile tek tek bulunup kurulmuştu — burada tek seferde
#    listeleniyor ki bir sonraki tahtada aynı elle-keşif tekrarlanmasın.
echo "[0/7] Ön koşullar kontrol ediliyor..."
EKSIK_PAKET=()
command -v git >/dev/null 2>&1 || EKSIK_PAKET+=("git")
command -v wmctrl >/dev/null 2>&1 || EKSIK_PAKET+=("wmctrl")
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
# "import venv" Debian'da paket eksikken de BAŞARILI olabilir — asıl gerçek
# eksik ensurepip'tir (venv oluşturma anında "ensurepip is not available"
# ile patlar, bkz. fenlab kurulumu 2026-09-17). Doğru kontrol ensurepip'in
# kendisi; eksikse Python sürümüne özel paket adı önerilir (ör. python3.11-venv).
python3 -c "import ensurepip" >/dev/null 2>&1 || EKSIK_PAKET+=("python${PYVER}-venv")
dpkg -s libportaudio2 >/dev/null 2>&1 || EKSIK_PAKET+=("libportaudio2")
dpkg -s libxcb-cursor0 >/dev/null 2>&1 || EKSIK_PAKET+=("libxcb-cursor0")
if [ "${#EKSIK_PAKET[@]}" -gt 0 ]; then
    echo "  EKSİK: ${EKSIK_PAKET[*]}"
    echo "  Bu paketler sudo gerektirir, bu script otomatik kurmaz."
    echo "  admin kullanıcıyla (etapadmin) önce şunu çalıştırın:"
    echo "    sudo apt-get update && sudo apt-get install -y ${EKSIK_PAKET[*]}"
    echo "  git eksikse aşağıdaki [1/7] adımı da başarısız olur."
else
    echo "  Tamam — git/wmctrl/venv/portaudio/xcb-cursor hepsi kurulu."
fi

# 1) Board repo yoksa: yalnızca client/ (sparse-checkout, cone modu) klonlanır.
#    server/ , docs/ , benchmark/ gibi tahtada hiç gerekmeyen dizinler hiç
#    diske inmez — partial clone (--filter=blob:none) ile de trafik azaltılır.
mkdir -p "$(dirname "$SYNC_SCRIPT")" "$(dirname "$LOG_FILE")"
if [ ! -d "$BOARD_REPO/.git" ]; then
    echo "[1/7] Repo klonlanıyor (yalnızca client/, sparse-checkout)..."
    git clone --no-checkout --filter=blob:none "$REPO_URL" "$BOARD_REPO"
    (
        cd "$BOARD_REPO"
        git sparse-checkout init --cone
        git sparse-checkout set client
        git checkout master
    )
else
    echo "[1/7] Repo zaten mevcut ($BOARD_REPO), klonlama atlanıyor."
fi

# 2) venv + bağımlılıklar — 12-A kurulumunda (2026-09-06) elle yapılmıştı,
#    bu script hiç kurmuyordu. requirements.lock.txt kullanılır (SÜRÜM
#    KİLİDİ, bkz. dosyanın kendi başlığı) — requirements.txt DEĞİL, tahtanın
#    gerçek Python'unda (3.11.2) test edilmemiş sürümler patlayabilir.
echo "[2/7] venv + bağımlılıklar kuruluyor (birkaç dakika sürebilir)..."
if [ ! -d "$CLIENT_PATH/venv" ]; then
    python3 -m venv "$CLIENT_PATH/venv"
fi
"$CLIENT_PATH/venv/bin/pip" install --quiet --upgrade pip
"$CLIENT_PATH/venv/bin/pip" install --quiet -r "$CLIENT_PATH/requirements.lock.txt"
echo "  Tamam — $CLIENT_PATH/venv hazır."

# 3) config/api_keys.json — yoksa şablondan oluşturulur. derslik/sunucu_url/
#    tahta_anahtari script argümanlarıyla verildiyse doldurulur; verilmediyse
#    boş kalır, elle doldurulması gerekir. gemini_api_keys HİÇBİR ZAMAN bu
#    script tarafından yazılmaz — API anahtarı üretmek/tedarik etmek
#    kullanıcının işi (bkz. DECISIONS.md, 12-A kurulum notu).
CONFIG_FILE="$CLIENT_PATH/config/api_keys.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "[3/7] config/api_keys.json oluşturuluyor..."
    cp "$CLIENT_PATH/config/api_keys.example.json" "$CONFIG_FILE"
    python3 - "$CONFIG_FILE" "$DERSLIK" "$SUNUCU_URL" "$TAHTA_ANAHTARI" <<'PYEOF'
import json, sys
yol, derslik, sunucu_url, tahta_anahtari = sys.argv[1:5]
with open(yol, encoding="utf-8") as f:
    veri = json.load(f)
if derslik:
    veri["derslik"] = derslik
if sunucu_url:
    veri["sunucu_url"] = sunucu_url
if tahta_anahtari:
    veri["tahta_anahtari"] = tahta_anahtari
with open(yol, "w", encoding="utf-8") as f:
    json.dump(veri, f, ensure_ascii=False, indent=2)
PYEOF
    if [ -z "$DERSLIK" ] || [ -z "$SUNUCU_URL" ] || [ -z "$TAHTA_ANAHTARI" ]; then
        echo "  UYARI: derslik/sunucu_url/tahta_anahtari argüman olarak verilmedi,"
        echo "  $CONFIG_FILE elle tamamlanmalı."
    fi
    echo "  UYARI: gemini_api_keys hâlâ BOŞ — sesli ders başlamadan önce elle girilmeli."
else
    echo "[3/7] config/api_keys.json zaten mevcut, dokunulmadı."
fi

# 4) Masaüstü kısayolu — 12-A'da elle oluşturulmuştu (DECISIONS.md), aynı şablon.
MASAUSTU="$HOME/Masaüstü"
if [ -d "$MASAUSTU" ]; then
    cat > "$MASAUSTU/farabi.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Farabi
Comment=Farabi yapay zeka öğretmen asistanı
Exec=$CLIENT_PATH/farabi_start.sh
Icon=$CLIENT_PATH/farabi-icon.png
Path=$CLIENT_PATH
Terminal=false
Categories=Education;
StartupNotify=true
EOF
    chmod +x "$MASAUSTU/farabi.desktop"
    echo "[4/7] Masaüstü kısayolu yazıldı: $MASAUSTU/farabi.desktop"
else
    echo "[4/7] '$MASAUSTU' yok, masaüstü kısayolu atlandı (Pardus dışı ortam olabilir)."
fi

# 5) Pull (senkronizasyon) scriptini yaz — artık server'a hiç dokunmaz.
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
echo "[5/7] Pull scripti yazıldı: $SYNC_SCRIPT"

# 6) Heartbeat scriptini yaz — server/client_durum.py::heartbeat'e POST eder.
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
echo "[6/7] Heartbeat scripti yazıldı: $HEARTBEAT_SCRIPT"

# 7) crontab: günlük pull + periyodik heartbeat (varsa tekrarlamadan güncelle)
CRON_HOUR=$(echo "$SYNC_TIME" | cut -d: -f1)
CRON_MIN=$(echo "$SYNC_TIME" | cut -d: -f2)
SYNC_LINE="$CRON_MIN $CRON_HOUR * * * $SYNC_SCRIPT"
HEARTBEAT_LINE="*/$HEARTBEAT_INTERVAL_DK * * * * $HEARTBEAT_SCRIPT"
( crontab -l 2>/dev/null | grep -vF "$SYNC_SCRIPT" | grep -vF "$HEARTBEAT_SCRIPT" || true
  echo "$SYNC_LINE"
  echo "$HEARTBEAT_LINE" ) | crontab -
echo "[7/7] Crontab güncellendi: pull her gün ${SYNC_TIME}'de, heartbeat her ${HEARTBEAT_INTERVAL_DK} dakikada."

echo
echo "Kurulum tamamlandı."
echo "Elle YAPILMASI GEREKENLER (bu script yazmaz):"
echo "  - $CONFIG_FILE içine en az bir gemini_api_keys girilmeli (sesli ders için şart)."
echo "  - derslik/sunucu_url/tahta_anahtari argüman verilmediyse $CONFIG_FILE elle tamamlanmalı."
echo "  - tahta_anahtari server/config/api_keys.json'daki board_keys[derslik] ile BİREBİR eşleşmeli."
echo "Elle test etmek için:"
echo "  $CLIENT_PATH/venv/bin/python -c 'import main'   # temiz import"
echo "  $SYNC_SCRIPT && tail -20 $LOG_FILE"
echo "  $HEARTBEAT_SCRIPT && tail -5 $HEARTBEAT_LOG"
