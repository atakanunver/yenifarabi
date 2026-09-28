#!/bin/bash
# Farabi'nin internet çıkışını Müdür PC'nin WifiHttpProxy'si (192.168.23.243:8080)
# ÜZERİNDEN mi, yoksa DOĞRUDAN mı yapacağını aç/kapat eder.
#
# Neden ayrı bir drop-in dosyası (proxy.conf), tek override.conf değil:
# `ollama.service.d/override.conf` OLLAMA_HOST/OLLAMA_KEEP_ALIVE/
# OLLAMA_LLM_LIBRARY gibi bu iş dışında hiç ilgisi olmayan ayarlar da
# taşıyor (bkz. kök CLAUDE.md "GPU yapılandırması" notu) — proxy'yi
# sed ile o dosyadan silip eklemek onları bozma riski taşırdı. Ayrı
# dosya = tek amaçlı, geri alması güvenli.
#
# 2026-09-23'te eklendi: Müdür PC'deki EBYS Telegram botundan kısıtlı bir
# SSH anahtarıyla (yalnızca bu script'i çalıştırabilir, bkz. authorized_keys
# `command=` deseni — zil-timesync anahtarıyla aynı desen) uzaktan
# tetiklenebilsin diye. Kullanım: bugün MEB hattında apt/npm/HuggingFace gibi
# işler proxy'siz başarısız olabiliyor (bkz. proje notu) — proxy'yi açıp
# kapatmak elle SSH gerektirmeden yapılabilsin istendi.

set -euo pipefail

DROP_IN_DIZIN="/etc/systemd/system/ollama.service.d"
PROXY_DOSYASI="$DROP_IN_DIZIN/proxy.conf"
PROXY_URL="http://wifi:vodafone@192.168.23.243:8080"

durum_goster() {
    if [ -f "$PROXY_DOSYASI" ]; then
        echo "PROXY: AÇIK ($PROXY_DOSYASI mevcut)"
    else
        echo "PROXY: KAPALI ($PROXY_DOSYASI yok)"
    fi
    echo "ollama.service: $(systemctl is-active ollama.service 2>/dev/null || echo bilinmiyor)"
}

proxy_ac() {
    sudo mkdir -p "$DROP_IN_DIZIN"
    sudo tee "$PROXY_DOSYASI" > /dev/null <<EOF
[Service]
Environment="HTTP_PROXY=$PROXY_URL"
Environment="HTTPS_PROXY=$PROXY_URL"
Environment="NO_PROXY=localhost,127.0.0.1"
EOF
    sudo systemctl daemon-reload
    sudo systemctl restart ollama.service
    echo "Proxy AÇILDI, ollama.service yeniden başlatıldı."
    durum_goster
}

proxy_kapat() {
    if [ -f "$PROXY_DOSYASI" ]; then
        sudo rm -f "$PROXY_DOSYASI"
        sudo systemctl daemon-reload
        sudo systemctl restart ollama.service
        echo "Proxy KAPATILDI, ollama.service yeniden başlatıldı."
    else
        echo "Proxy zaten kapalıydı, değişiklik yapılmadı."
    fi
    durum_goster
}

case "${1:-durum}" in
    ac)     proxy_ac ;;
    kapat)  proxy_kapat ;;
    durum)  durum_goster ;;
    *)      echo "Kullanım: $0 {ac|kapat|durum}" >&2; exit 1 ;;
esac
