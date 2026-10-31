#!/usr/bin/env bash
# baslat.sh - Sınıf Arenası Akıllı Tahta Servisini Başlatma Betiği (Port 8030)

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PORT=8030
HOST="0.0.0.0"

# Sanal ortam kontrolü
if [ ! -d "venv" ]; then
    echo "Sanal ortam oluşturuluyor..."
    python3 -m venv venv
    venv/bin/pip install --upgrade pip
    venv/bin/pip install fastapi uvicorn httpx
fi

# Port kontrolü
if ss -tulpn | grep -q ":$PORT "; then
    echo "UYARI: Port $PORT zaten kullanımda. Eski süreç sonlandırılıyor..."
    fuser -k -n tcp $PORT 2>/dev/null || true
    sleep 1
fi

echo "=========================================================="
echo "🎯 Sınıf Arenası Servisi Başlatılıyor..."
echo "📍 Sunucu: http://$HOST:$PORT"
echo "🌐 Ağ Erişimi: http://farabi.local:$PORT"
echo "=========================================================="

exec venv/bin/uvicorn server:app --host "$HOST" --port "$PORT"
