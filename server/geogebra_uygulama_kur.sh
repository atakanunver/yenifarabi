#!/bin/bash
# server/geogebra_uygulama_kur.sh — GeoGebra Klasik'i tahtalara BAĞIMSIZ bir
# masaüstü programı olarak kurar ve öğretmen masaüstüne kısayol koyar.
#
# 2026-09-25, kullanıcı isteği: "geogebrayı bağımsız olarak bir yazılım program
# olarak tüm tahtalara kur, kısayolunu masaüstüne koy". Farabi'nin geogebra
# aracından (client/actions/geogebra.py + server/geogebra_dagit.sh, çevrimdışı
# web paketi + chrome --app köprüsü) TAMAMEN AYRI — bu, öğretmenin kendi başına
# açtığı normal bir uygulama.
#
# Kaynak: Pardus ETAP'ın kendi okul deposundaki resmi paket (`geogebra-classic`,
# depo.etap.org.tr yirmiuc/contrib, GeoGebra Enstitüsü yapımı Electron
# uygulaması, ~49 MB indirme / ~150 MB kurulum). Kaynak koddan derleme
# (github.com/geogebra/geogebra) bilinçli olarak seçilmedi — Gradle/Java
# derlemesi i3-2330M tahtalarda pratik değil.
#
# Her tahtada:
#   1) paket yoksa etapadmin ile kurulur (önce `sudo -n`, olmazsa parola
#      `tahtayoklama/dashboard/config/gizli.json::etapadmin_sifre`'den —
#      gitignore'lu, REPO PUBLIC, parola bu dosyaya yazılmaz),
#   2) /usr/share/applications/geogebra-classic.desktop, ogretmen'in
#      ~/Masaüstü'süne kopyalanır, çalıştırılabilir + `metadata::trusted`
#      yapılır (Cinnamon/nemo "güvenilmeyen başlatıcı" sormasın diye).
# Zaten kurulu + kısayolu olan tahtaya dokunulmaz.
#
# Kullanım:
#   ./geogebra_uygulama_kur.sh                 → varsayılan 8 tahtaya
#   ./geogebra_uygulama_kur.sh 9-A fenlab      → yalnızca verilen tahtalara
#   ./geogebra_uygulama_kur.sh --kuru [...]    → yalnızca durumu göster

set -uo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIZLI_JSON="$BASE_DIR/../tahtayoklama/dashboard/config/gizli.json"
VARSAYILAN_TAHTALAR=(9-A 9-B 10-A 11-A 11-B 12-A 12-B fenlab)
PAKET="geogebra-classic"

KURU=0
if [ "${1:-}" = "--kuru" ]; then
    KURU=1
    shift
fi
TAHTALAR=("$@")
[ ${#TAHTALAR[@]} -eq 0 ] && TAHTALAR=("${VARSAYILAN_TAHTALAR[@]}")

SIFRE=""
if [ -f "$GIZLI_JSON" ]; then
    SIFRE=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('etapadmin_sifre',''))" "$GIZLI_JSON")
fi

# Tahtanın durumunu tek satırda basar: "<paket:VAR|YOK> <kisayol:VAR|YOK>"
UZAK_DURUM="p=YOK; dpkg-query -W -f='\${Status}' $PAKET 2>/dev/null | grep -q 'install ok installed' && p=VAR
k=YOK; [ -x ~/Masaüstü/$PAKET.desktop ] && k=VAR
echo \"DURUM \$p \$k\""

UZAK_KUR="DEBIAN_FRONTEND=noninteractive apt-get install -y $PAKET >/tmp/geogebra_kur.log 2>&1 || { tail -5 /tmp/geogebra_kur.log; exit 1; }"

UZAK_KISAYOL="set -e
d=~/Masaüstü; mkdir -p \"\$d\"
cp /usr/share/applications/$PAKET.desktop \"\$d/\"
chmod +x \"\$d/$PAKET.desktop\"
export DBUS_SESSION_BUS_ADDRESS=\"unix:path=/run/user/\$(id -u)/bus\"
gio set \"\$d/$PAKET.desktop\" metadata::trusted true 2>/dev/null || true
echo KISAYOL_TAMAM"

durum() { timeout 30 "$BASE_DIR/tahta-ssh.sh" "$1" "$UZAK_DURUM" 2>/dev/null | grep '^DURUM' | tail -1; }

HATA=0
for t in "${TAHTALAR[@]}"; do
    d=$(durum "$t")
    if [ -z "$d" ]; then
        echo "== $t: HATA — ulaşılamadı"; HATA=1; continue
    fi
    read -r _ paket kisayol <<<"$d"
    if [ "$paket" = VAR ] && [ "$kisayol" = VAR ]; then
        echo "== $t: = kurulu, kısayol var"; continue
    fi
    if [ "$KURU" -eq 1 ]; then
        echo "== $t: ~ yapılacak (paket: $paket, kısayol: $kisayol)"; continue
    fi

    if [ "$paket" = YOK ]; then
        if ! timeout 600 "$BASE_DIR/tahta-ssh.sh" --admin "$t" "sudo -n bash -c '$UZAK_KUR'" </dev/null >/dev/null 2>&1; then
            if [ -z "$SIFRE" ]; then
                echo "== $t: HATA — sudo parola istiyor ve gizli.json'da etapadmin_sifre yok"; HATA=1; continue
            fi
            cikti=$(printf '%s\n' "$SIFRE" | timeout 600 "$BASE_DIR/tahta-ssh.sh" --admin "$t" "sudo -S -p '' bash -c '$UZAK_KUR'" 2>&1)
            if [ $? -ne 0 ]; then
                echo "== $t: HATA — paket kurulamadı: $(echo "$cikti" | tail -2 | tr '\n' ' ')"; HATA=1; continue
            fi
        fi
    fi

    if [ "$kisayol" = YOK ]; then
        timeout 30 "$BASE_DIR/tahta-ssh.sh" "$t" "$UZAK_KISAYOL" 2>/dev/null | grep -q KISAYOL_TAMAM \
            || { echo "== $t: HATA — kısayol yazılamadı"; HATA=1; continue; }
    fi

    d=$(durum "$t")
    if [ "$d" = "DURUM VAR VAR" ]; then
        echo "== $t: + kuruldu (önce: paket $paket, kısayol $kisayol)"
    else
        echo "== $t: HATA — doğrulanamadı (${d:-?})"; HATA=1
    fi
done
[ "$KURU" -eq 1 ] && echo "(kuru çalıştırma — hiçbir şey değiştirilmedi)"
exit $HATA
