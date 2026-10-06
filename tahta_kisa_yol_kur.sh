#!/usr/bin/env bash
# tahta_kisa_yol_kur.sh - Akıllı Tahtaların Masaüstüne "OYUNLAR" Klasörü,
# "Sınıf Arenası", "HexaFetih" ve "Yoklama" Kısayollarını Kurar.
# Hem yüksek çözünürlüklü PNG hem de filtre-bağımsız SVG ikonları dağıtır.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_SCRIPT="/home/ata/farabi/server/tahta-ssh.sh"

ARENA_PNG="$DIR/arena-icon.png"
ARENA_SVG="$DIR/arena-icon.svg"
FETIH_PNG="$DIR/fetih-icon.png"
FETIH_SVG="$DIR/fetih-icon.svg"
OYUNLAR_PNG="$DIR/oyunlar-icon.png"
OYUNLAR_SVG="$DIR/oyunlar-icon.svg"
YOKLAMA_PNG="$DIR/yoklama-icon.png"
YOKLAMA_SVG="$DIR/yoklama-icon.svg"

kur_tahta() {
    local tahta="$1"
    echo "----------------------------------------------------"
    echo "📦 Tahtaya kuruluyor: $tahta"

    # 1. Klasörleri oluştur
    $SSH_SCRIPT "$tahta" "mkdir -p ~/.local/share/icons/hicolor/256x256/apps ~/.local/share/icons/hicolor/scalable/apps ~/.icons ~/Masaüstü/OYUNLAR ~/Desktop/OYUNLAR 2>/dev/null || true"

    # 2. İkonları SSH stdin ile aktar (hem PNG hem SVG)
    $SSH_SCRIPT "$tahta" "cat > ~/.local/share/icons/arena-icon.png" < "$ARENA_PNG"
    $SSH_SCRIPT "$tahta" "cat > ~/.local/share/icons/arena-icon.svg" < "$ARENA_SVG"
    $SSH_SCRIPT "$tahta" "cat > ~/.local/share/icons/fetih-icon.png" < "$FETIH_PNG"
    $SSH_SCRIPT "$tahta" "cat > ~/.local/share/icons/fetih-icon.svg" < "$FETIH_SVG"
    $SSH_SCRIPT "$tahta" "cat > ~/.local/share/icons/oyunlar-icon.png" < "$OYUNLAR_PNG"
    $SSH_SCRIPT "$tahta" "cat > ~/.local/share/icons/oyunlar-icon.svg" < "$OYUNLAR_SVG"
    $SSH_SCRIPT "$tahta" "cat > ~/.local/share/icons/yoklama-icon.png" < "$YOKLAMA_PNG"
    $SSH_SCRIPT "$tahta" "cat > ~/.local/share/icons/yoklama-icon.svg" < "$YOKLAMA_SVG"

    # 3. İkonları tema dizinlerine kopyala, kilitleri temizle ve kısayolları kur
    $SSH_SCRIPT "$tahta" '
        # İkonları XDG hicolor ve ~/.icons altına da yay
        cp ~/.local/share/icons/*.png ~/.local/share/icons/hicolor/256x256/apps/ 2>/dev/null || true
        cp ~/.local/share/icons/*.svg ~/.local/share/icons/hicolor/scalable/apps/ 2>/dev/null || true
        cp ~/.local/share/icons/*.png ~/.icons/ 2>/dev/null || true

        # Chrome Singleton kilit çakışmalarını temizle (kilitlenme önleme)
        rm -f ~/.config/arena-chrome/Singleton* 2>/dev/null || true
        if ! pgrep -u ogretmen -f "google-chrome.*--type" >/dev/null 2>&1; then
            rm -f ~/.config/google-chrome/Singleton* 2>/dev/null || true
        fi

        # OYUNLAR klasör ikonu (.directory ve gio)
        cat > ~/Masaüstü/OYUNLAR/.directory <<EOF
[Desktop Entry]
Type=Directory
Icon=/home/ogretmen/.local/share/icons/oyunlar-icon.png
EOF
        gio set ~/Masaüstü/OYUNLAR metadata::custom-icon file:///home/ogretmen/.local/share/icons/oyunlar-icon.png 2>/dev/null || true

        if [ -d ~/Desktop/OYUNLAR ]; then
            cp ~/Masaüstü/OYUNLAR/.directory ~/Desktop/OYUNLAR/.directory 2>/dev/null || true
            gio set ~/Desktop/OYUNLAR metadata::custom-icon file:///home/ogretmen/.local/share/icons/oyunlar-icon.png 2>/dev/null || true
        fi

        # 1. Oyun: Sınıf Arenası (Jeopardy) .desktop kısayolu
        cat > ~/Masaüstü/OYUNLAR/Sinif-Arenasi.desktop <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Sınıf Arenası
GenericName=Akıllı Tahta Yarışması (Jeopardy)
Comment=Farabi.local İnteraktif Sınıf Arenası Yarışması
Exec=google-chrome --app=http://farabi.local:8030/arena --user-data-dir=/home/ogretmen/.config/arena-chrome --start-maximized --no-first-run --no-default-browser-check
Icon=/home/ogretmen/.local/share/icons/arena-icon.png
Terminal=false
Categories=Education;Game;
StartupNotify=true
EOF

        chmod +x ~/Masaüstü/OYUNLAR/Sinif-Arenasi.desktop
        gio set ~/Masaüstü/OYUNLAR/Sinif-Arenasi.desktop metadata::trusted true 2>/dev/null || true
        gio set ~/Masaüstü/OYUNLAR/Sinif-Arenasi.desktop metadata::custom-icon file:///home/ogretmen/.local/share/icons/arena-icon.png 2>/dev/null || true

        # 2. Oyun: HexaFetih (Bölge Fetih & Strateji) .desktop kısayolu
        cat > ~/Masaüstü/OYUNLAR/Hexa-Fetih.desktop <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=HexaFetih
GenericName=Bölge Fetih ve Strateji Arenası
Comment=Farabi.local Hexagon Petek Harita Bilgi ve Strateji Yarışması
Exec=google-chrome --app=http://farabi.local:8030/fetih --user-data-dir=/home/ogretmen/.config/arena-chrome --start-maximized --no-first-run --no-default-browser-check
Icon=/home/ogretmen/.local/share/icons/fetih-icon.png
Terminal=false
Categories=Education;Game;
StartupNotify=true
EOF

        chmod +x ~/Masaüstü/OYUNLAR/Hexa-Fetih.desktop
        gio set ~/Masaüstü/OYUNLAR/Hexa-Fetih.desktop metadata::trusted true 2>/dev/null || true
        gio set ~/Masaüstü/OYUNLAR/Hexa-Fetih.desktop metadata::custom-icon file:///home/ogretmen/.local/share/icons/fetih-icon.png 2>/dev/null || true

        # 3. Oyun: Tahta Düellosu (Çark & Hızlı Cevap) .desktop kısayolu
        cat > ~/Masaüstü/OYUNLAR/Tahta-Duellosu.desktop <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Tahta Düellosu
GenericName=Çark & Hızlı Cevap Maratonu
Comment=Farabi.local İki Kişilik Dokunmatik Tahta Düellosu
Exec=google-chrome --app=http://farabi.local:8030/duello --user-data-dir=/home/ogretmen/.config/arena-chrome --start-maximized --no-first-run --no-default-browser-check
Icon=/home/ogretmen/.local/share/icons/arena-icon.png
Terminal=false
Categories=Education;Game;
StartupNotify=true
EOF

        chmod +x ~/Masaüstü/OYUNLAR/Tahta-Duellosu.desktop
        gio set ~/Masaüstü/OYUNLAR/Tahta-Duellosu.desktop metadata::trusted true 2>/dev/null || true
        gio set ~/Masaüstü/OYUNLAR/Tahta-Duellosu.desktop metadata::custom-icon file:///home/ogretmen/.local/share/icons/arena-icon.png 2>/dev/null || true

        if [ -d ~/Desktop/OYUNLAR ]; then
            cp ~/Masaüstü/OYUNLAR/Sinif-Arenasi.desktop ~/Desktop/OYUNLAR/Sinif-Arenasi.desktop 2>/dev/null || true
            cp ~/Masaüstü/OYUNLAR/Hexa-Fetih.desktop ~/Desktop/OYUNLAR/Hexa-Fetih.desktop 2>/dev/null || true
            cp ~/Masaüstü/OYUNLAR/Tahta-Duellosu.desktop ~/Desktop/OYUNLAR/Tahta-Duellosu.desktop 2>/dev/null || true
            chmod +x ~/Desktop/OYUNLAR/*.desktop 2>/dev/null || true
            gio set ~/Desktop/OYUNLAR/Sinif-Arenasi.desktop metadata::trusted true 2>/dev/null || true
            gio set ~/Desktop/OYUNLAR/Hexa-Fetih.desktop metadata::trusted true 2>/dev/null || true
            gio set ~/Desktop/OYUNLAR/Tahta-Duellosu.desktop metadata::trusted true 2>/dev/null || true
        fi


        # Yoklama Kısayollarının İkonunu Güncelle
        for f in ~/Masaüstü/*[yY]oklama*.desktop ~/Desktop/*[yY]oklama*.desktop; do
            if [ -f "$f" ]; then
                sed -i "s|^Icon=.*|Icon=/home/ogretmen/.local/share/icons/yoklama-icon.png|" "$f"
                chmod +x "$f"
                gio set "$f" metadata::trusted true 2>/dev/null || true
                gio set "$f" metadata::custom-icon file:///home/ogretmen/.local/share/icons/yoklama-icon.png 2>/dev/null || true
                touch "$f"
            fi
        done

        # Masaüstü ve ikon önbelleğini tazele
        touch ~/Masaüstü/OYUNLAR/*.desktop ~/Masaüstü/OYUNLAR/ 2>/dev/null || true
        gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor 2>/dev/null || true
    '

    echo "✅ $tahta: OYUNLAR (Sınıf Arenası + HexaFetih) başarıyla kuruldu!"
}

# Yerel masaüstüne de kur (farabi.local sunucusu / test kullanıcısı)
kur_yerel() {
    echo "----------------------------------------------------"
    echo "📦 Yerel sisteme kuruluyor ($USER)"
    mkdir -p ~/.local/share/icons/hicolor/256x256/apps ~/.icons ~/Desktop/OYUNLAR ~/Masaüstü/OYUNLAR 2>/dev/null || true
    cp "$ARENA_PNG" "$ARENA_SVG" "$FETIH_PNG" "$FETIH_SVG" "$OYUNLAR_PNG" "$OYUNLAR_SVG" "$YOKLAMA_PNG" "$YOKLAMA_SVG" ~/.local/share/icons/
    cp ~/.local/share/icons/*.png ~/.local/share/icons/hicolor/256x256/apps/ 2>/dev/null || true

    cat > ~/Desktop/OYUNLAR/Sinif-Arenasi.desktop <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Sınıf Arenası
GenericName=Akıllı Tahta Yarışması (Jeopardy)
Comment=Farabi.local İnteraktif Sınıf Arenası Yarışması
Exec=google-chrome --app=http://farabi.local:8030/arena --user-data-dir=$HOME/.config/arena-chrome --start-maximized --no-first-run --no-default-browser-check
Icon=$HOME/.local/share/icons/arena-icon.png
Terminal=false
Categories=Education;Game;
StartupNotify=true
EOF

    cat > ~/Desktop/OYUNLAR/Hexa-Fetih.desktop <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=HexaFetih
GenericName=Bölge Fetih ve Strateji Arenası
Comment=Farabi.local Hexagon Petek Harita Bilgi ve Strateji Yarışması
Exec=google-chrome --app=http://farabi.local:8030/fetih --user-data-dir=$HOME/.config/arena-chrome --start-maximized --no-first-run --no-default-browser-check
Icon=$HOME/.local/share/icons/fetih-icon.png
Terminal=false
Categories=Education;Game;
StartupNotify=true
EOF

    chmod +x ~/Desktop/OYUNLAR/*.desktop
    if [ -d ~/Masaüstü ]; then
        cp -r ~/Desktop/OYUNLAR ~/Masaüstü/ 2>/dev/null || true
        chmod +x ~/Masaüstü/OYUNLAR/*.desktop 2>/dev/null || true
    fi
    echo "✅ Yerel masaüstü kısayolları hazırlandı."
}

kur_yerel

HEDEF="${1:---tum-tahtalar}"
if [ "$HEDEF" = "--tum-tahtalar" ]; then
    echo "🚀 Açık olan tüm tahtalara dağıtılıyor..."
    for t in 9-A 9-B 10-A 11-B 12-A 12-B fenlab; do
        kur_tahta "$t" || echo "⚠️ $t kurulumunda hata oluştu, devam ediliyor."
    done
else
    kur_tahta "$HEDEF"
fi

echo "===================================================="
echo "🎉 Tüm işlemler tamamlandı!"
