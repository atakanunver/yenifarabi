#!/bin/bash
# setup_anythingllm.sh — Atos (AnythingLLM) Docker'sız (bare-metal) kurulum betiği.
#
# 2026-10-25'te Farabi sunucusunda (Ubuntu, RTX 3060 x2, Ollama yerelde) FİİLEN çalıştırılıp doğrulanan adımlardır.
# Tekrar çalıştırılabilir (idempotent): var olan adımı atlar, .env'i yeniden yazar, PM2 süreçlerini yeniden başlatır.
#
# Kullanım:   sudo ./setup_anythingllm.sh            (root ya da sudo yetkili kullanıcı)
# Ayarlar (ortam değişkeniyle ezilebilir):
#   ATOS_PORT=8010  ATOS_MODEL=gemma4:12b  ATOS_CTX=49152  ATOS_PAROLA=...   (parola VARSAYILAN YOK: vermezsen sorar)
#
# REHBERDEKİ VARSAYIMLARDAN DÜZELTMELER (resmî repo/BARE_METAL.md'den doğrulandı):
#  - `yarn install` + `yarn build` kökte YETMEZ: kökte `build` yok. Gerçek akış: her alt projede `yarn install`,
#    `frontend/.env` (VITE_API_BASE='/api'), `cd frontend && yarn build`, `cp -R frontend/dist server/public`,
#    `prisma generate` + `prisma migrate deploy`, sunucu ve collector AYRI süreç.
#  - `SERVER_MODE` diye bir ortam değişkeni YOK. Tek kullanıcı + parola = `AUTH_TOKEN`. Çok kullanıcılı mod yalnızca
#    arayüzden (Ayarlar > Çok kullanıcılı mod) açılır ve GERİ ALINAMAZ; burada kullanılmıyor.
#  - Collector kendi `collector/.env` dosyasında `STORAGE_DIR` ister (yoksa açılışta çöker).
#  - Dosya yükleme: sunucu (üretim kipinde) yükleme klasörünü STORAGE_DIR/../../collector/hotdir olarak hesaplar; Docker düzeninde
#    (/app/server/storage) doğru çıkar, bizim düzende /opt/collector/hotdir'e düşer ve "ENOENT" ile her yükleme çöker.
#    Çözüm: /opt/collector -> /opt/anythingllm/app/collector sembolik bağı (adım 4).
#  - OCR varsayılan olarak yalnızca İngilizce tanır (Türkçe harfler kaybolur: "şubat" -> "subat"); TARGET_OCR_LANG="tur,eng".
#  - Okul ağı SSL denetimi yapar: Node için NODE_EXTRA_CA_CERTS, Puppeteer'ın Chromium indirmesi atlanır (web kazıma yok).
#  - Node: resmî hedef 18; Node 22 ile sorunsuz kuruldu ve çalıştı.
set -euo pipefail

PORT="${ATOS_PORT:-8010}"
MODEL="${ATOS_MODEL:-gemma4:12b}"
CTX="${ATOS_CTX:-49152}"          # Ollama num_ctx olarak gider; sunucu OLLAMA_CONTEXT_LENGTH ile AYNI olmalı
SURUM="${ATOS_SURUM:-v1.18.0}"
KULLANICI=anythingllm
DIZIN=/opt/anythingllm
UYGULAMA="$DIZIN/app"
DEPO="$(cd "$(dirname "$0")" && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "root (sudo) gerekli"; exit 1; }
PAROLA="${ATOS_PAROLA:-}"
if [ -z "$PAROLA" ]; then read -r -s -p "Atos erişim parolası: " PAROLA; echo; fi
[ -n "$PAROLA" ] || { echo "parola boş olamaz"; exit 1; }

echo "== 1/7 Sistem bağımlılıkları"
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential python3 git curl ca-certificates
if ! command -v node >/dev/null || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 18 ]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
node -v
NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt npm install -g yarn pm2

echo "== 2/7 Kullanıcı ve kaynak kod ($SURUM)"
id "$KULLANICI" >/dev/null 2>&1 || useradd -r -m -d "$DIZIN" -s /bin/bash "$KULLANICI"
sudo -u "$KULLANICI" bash -c "[ -d '$UYGULAMA' ] || git clone --depth 1 --branch '$SURUM' https://github.com/Mintplex-Labs/anything-llm.git '$UYGULAMA'"

echo "== 3/7 Bağımlılıklar (server, collector, frontend)"
sudo -u "$KULLANICI" bash -s <<ALT
set -e
export NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt PUPPETEER_SKIP_DOWNLOAD=true PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
cd '$UYGULAMA'
for d in server collector frontend; do (cd \$d && yarn install --network-timeout 600000 2>&1 | tail -2); done
ALT

echo "== 4/7 Ortam dosyaları"
JWT=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40)
mkdir -p "$DIZIN/storage"
cat > "$UYGULAMA/server/.env" <<ENV
SERVER_PORT=$PORT
JWT_SECRET="$JWT"
AUTH_TOKEN="$PAROLA"
STORAGE_DIR="$DIZIN/storage"
DISABLE_TELEMETRY="true"
LLM_PROVIDER='ollama'
OLLAMA_BASE_PATH='http://127.0.0.1:11434'
OLLAMA_MODEL_PREF='$MODEL'
OLLAMA_MODEL_TOKEN_LIMIT=$CTX
EMBEDDING_ENGINE='native'
VECTOR_DB='lancedb'
TARGET_OCR_LANG="tur,eng"
ENV
printf 'STORAGE_DIR="%s"\n' "$DIZIN/storage" > "$UYGULAMA/collector/.env"
echo "VITE_API_BASE='/api'" > "$UYGULAMA/frontend/.env"
# Yükleme klasörü köprüsü: sunucu STORAGE_DIR/../../collector/hotdir'e yazar (= $(dirname "$DIZIN")/collector/hotdir), collector ise
# kendi dizinindeki hotdir'i izler; ikisini aynı yere bağla.
ln -sfn "$UYGULAMA/collector" "$(dirname "$DIZIN")/collector"
chown "$KULLANICI:$KULLANICI" "$UYGULAMA/server/.env" "$UYGULAMA/collector/.env" "$UYGULAMA/frontend/.env" "$DIZIN/storage"
chmod 600 "$UYGULAMA/server/.env"

echo "== 5/7 Arayüz derlemesi (Türkçe varsayılan) ve veri tabanı"
sudo -u "$KULLANICI" bash -s <<ALT
set -e
export NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
cd '$UYGULAMA/frontend'
# Arayüz tarayıcı dilinden bağımsız Türkçe açılsın (tr çevirisi eksiksiz: 1254/1254 anahtar). AnythingLLM güncellenirse bu satır yeniden uygulanmalı.
grep -q 'lng: "tr"' src/i18n.js || sed -i 's|    fallbackLng: "en",|    lng: "tr", // Atos: arayüz her zaman Türkçe\n    fallbackLng: "en",|' src/i18n.js
yarn build 2>&1 | tail -1
cd .. && rm -rf server/public && cp -R frontend/dist server/public
cd server && npx prisma generate --schema=./prisma/schema.prisma >/dev/null && npx prisma migrate deploy --schema=./prisma/schema.prisma | tail -1
ALT

echo "== 6/7 PM2 (sunucu + belge işleyici) ve açılışta otomatik başlama"
sudo -u "$KULLANICI" bash -s <<ALT
export PM2_HOME='$DIZIN/.pm2' NODE_ENV=production NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
pm2 delete allm-server allm-collector >/dev/null 2>&1 || true
pm2 start index.js --name allm-server    --cwd '$UYGULAMA/server'    --time >/dev/null
pm2 start index.js --name allm-collector --cwd '$UYGULAMA/collector' --time >/dev/null
pm2 save >/dev/null
ALT
env PATH="$PATH:/usr/local/bin" PM2_HOME="$DIZIN/.pm2" "$(command -v pm2)" startup systemd -u "$KULLANICI" --hp "$DIZIN" >/dev/null 2>&1 || true
systemctl enable pm2-anythingllm >/dev/null 2>&1 || true

echo "== 7/7 Atos adı, logo ve agent yetenekleri"
sleep 12
TOKEN=$(curl -s -X POST "http://127.0.0.1:$PORT/api/request-token" -H 'Content-Type: application/json' -d "{\"password\":\"$PAROLA\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("token",""))')
if [ -n "$TOKEN" ]; then
  curl -s -X POST "http://127.0.0.1:$PORT/api/admin/system-preferences" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
       -d '{"custom_app_name":"Atos","meta_page_title":"Atos"}' >/dev/null
  [ -f /mnt/farabi-data/farabi/atoslogo.png ] && curl -s -X POST "http://127.0.0.1:$PORT/api/system/upload-logo" -H "Authorization: Bearer $TOKEN" \
       -F "logo=@/mnt/farabi-data/farabi/atoslogo.png" >/dev/null || true
fi
# Agent yetenekleri (sql-sorgu, tablo-dosyasi): dashboard okul.json anahtarı gerekir; ata kullanıcısıyla çalıştırın:
echo "Yetenekler için (sudo OLMADAN, ata kullanıcısıyla):  $DEPO/kur_yetenekler.sh"

cat <<BITIS

Kurulum tamam:  http://$(hostname -I | awk '{print $1}'):$PORT/   (tek kullanıcı modu, parola: girdiğiniz AUTH_TOKEN)

İlk girişte yapılacaklar (Ayarlar):
 1. Yapay Zekâ Sağlayıcıları > LLM: Ollama, Base URL http://127.0.0.1:11434, model $MODEL, bağlam $CTX
    (.env ile zaten ayarlı; arayüzde "Ollama" ve modelin seçili geldiğini doğrulayın).
 2. Ajan Yetenekleri: "sql-sorgu" ve "tablo-dosyasi" (kur_yetenekler.sh sonrası listede görünür) açık olsun.
    Hazır "SQL Agent" bağlayıcısı yalnızca PostgreSQL/MySQL/MSSQL okur (SQLite desteklemez); yoklama + öğretmen programı için
    özel "sql-sorgu" yeteneği kullanılır. Excel/PDF için "tablo-dosyasi" (SQL sonucunu doğrudan dosyaya çevirir).
 3. Sohbette ajanı çağırmak için mesajı  @agent  ile başlatın (örn. "@agent 9-A sınıf listesini Excel yap").
 4. Ollama sunucu tarafı (bir kez): OLLAMA_CONTEXT_LENGTH=$CTX (tüm istemcilerle AYNI), OLLAMA_KEEP_ALIVE=-1.
BITIS
