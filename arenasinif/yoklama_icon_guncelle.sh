#!/usr/bin/env bash
# yoklama_icon_guncelle.sh - Akıllı tahtalardaki Masaüstü Tahta Yoklama kısayollarının
# ikonunu öğrenci/mezuniyet temalı özel SVG ikon ile günceller.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_SCRIPT="/home/ata/farabi/server/tahta-ssh.sh"
YOKLAMA_ICON="$DIR/yoklama-icon.svg"

if [ ! -f "$YOKLAMA_ICON" ]; then
    echo "HATA: $YOKLAMA_ICON bulunamadı!" >&2
    exit 1
fi

guncelle_tahta() {
    local tahta="$1"
    echo "----------------------------------------------------"
    echo "🎒 Tahtadaki Yoklama ikonu güncelleniyor: $tahta"

    # 1. İkonu tahtaya aktar (~/.local/share/icons/ ve ~/tahtayoklama/)
    $SSH_SCRIPT "$tahta" "mkdir -p ~/.local/share/icons 2>/dev/null || true"
    $SSH_SCRIPT "$tahta" "cat > ~/.local/share/icons/yoklama-icon.svg" < "$YOKLAMA_ICON"
    $SSH_SCRIPT "$tahta" "cp ~/.local/share/icons/yoklama-icon.svg ~/tahtayoklama/yoklama-icon.svg 2>/dev/null || true"

    # 2. Masaüstündeki tüm yoklama kısayollarının Icon alanını güncelle
    $SSH_SCRIPT "$tahta" '
        shopt -s nullglob
        bulunan=0
        for f in ~/Masaüstü/*[yY]oklama*.desktop ~/Desktop/*[yY]oklama*.desktop; do
            if [ -f "$f" ]; then
                echo "  -> Güncelleniyor: $f"
                # Icon satırını değiştir veya yoksa ekle
                if grep -q "^Icon=" "$f"; then
                    sed -i "s|^Icon=.*|Icon=/home/ogretmen/.local/share/icons/yoklama-icon.svg|" "$f"
                else
                    echo "Icon=/home/ogretmen/.local/share/icons/yoklama-icon.svg" >> "$f"
                fi
                chmod +x "$f"
                gio set "$f" metadata::trusted true 2>/dev/null || true
                touch "$f"
                bulunan=$((bulunan + 1))
            fi
        done
        if [ "$bulunan" -eq 0 ]; then
            echo "  ⚠️ Uyarı: Masaüstünde yoklama .desktop dosyası bulunamadı."
        else
            echo "  ✅ $bulunan adet kısayol güncellendi."
        fi
    '
}

guncelle_yerel() {
    echo "----------------------------------------------------"
    echo "🎒 Yerel sistem güncelleniyor ($USER)"
    mkdir -p ~/.local/share/icons 2>/dev/null || true
    cp "$YOKLAMA_ICON" ~/.local/share/icons/yoklama-icon.svg
    if [ -d /home/ata/farabi/tahtayoklama ]; then
        cp "$YOKLAMA_ICON" /home/ata/farabi/tahtayoklama/yoklama-icon.svg
    fi

    # Yerel masaüstünde yoklama kısayolu varsa güncelle, yoksa oluştur
    for masaustu in "$HOME/Desktop" "$HOME/Masaüstü"; do
        if [ -d "$masaustu" ]; then
            shopt -s nullglob
            for f in "$masaustu"/*[yY]oklama*.desktop; do
                if [ -f "$f" ]; then
                    echo "  -> Yerel kısayol güncelleniyor: $f"
                    sed -i "s|^Icon=.*|Icon=$HOME/.local/share/icons/yoklama-icon.svg|" "$f"
                    chmod +x "$f"
                    gio set "$f" metadata::trusted true 2>/dev/null || true
                    touch "$f"
                fi
            done
        fi
    done
    echo "✅ Yerel sistem tamamlandı."
}

# 1. Önce yereli güncelle
guncelle_yerel

# 2. Tahtaları güncelle
HEDEF="${1:---tum-tahtalar}"
if [ "$HEDEF" = "--tum-tahtalar" ]; then
    echo "🚀 Açık olan tüm tahtalar güncelleniyor..."
    for t in 9-A 9-B 10-A 11-B 12-A 12-B fenlab; do
        guncelle_tahta "$t" || echo "⚠️ $t güncellemesinde hata oluştu, devam ediliyor."
    done
else
    guncelle_tahta "$HEDEF"
fi

echo "===================================================="
echo "🎉 Yoklama ikonları başarıyla güncellendi!"
