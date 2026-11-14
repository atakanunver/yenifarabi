#!/bin/bash
# server/pdf_okuyucu_kur.sh — tahtalarda Evince'i kurar ve varsayılan PDF okuyucu yapar.
#
# 2026-11-14, kullanıcı isteği. Neden: 9-A ve 11-A'da PDF'ler Firefox'un yerleşik
# okuyucusunda (pdf.js, `file://` içerik süreci) açılıyordu; büyük ders kitabı /
# YKS kitapçığı PDF'lerinde süreç ~2 GB RSS'ye şişip 4 GB RAM'li tahtalarda
# çekirdek OOM'una yol açtı (14 Eyl–1 Kas, ders saatleri). Evince hafif.
#
# Her tahtada:
#   1) `evince` yoksa etapadmin ile kurulur (apt-get update + install; önce `sudo -n`,
#      olmazsa parola `tahtayoklama/dashboard/config/gizli.json::etapadmin_sifre`),
#   2) ogretmen için `application/pdf` varsayılanı `org.gnome.Evince.desktop` yapılır
#      (~/.config/mimeapps.list önce bir kez `.bak-pdf` olarak yedeklenir).
# Zaten kurulu + varsayılan olan tahtaya dokunulmaz (tekrar çalıştırmak güvenli).
# Kapalı tahta atlanır (HATA satırı); gece cron'u (`# TAHTA_PDF_OKUYUCU`) tekrar dener.
#
# Kullanım:
#   ./pdf_okuyucu_kur.sh                 → varsayılan 8 tahtaya
#   ./pdf_okuyucu_kur.sh 9-A fenlab      → yalnızca verilen tahtalara
#   ./pdf_okuyucu_kur.sh --kuru [...]    → yalnızca durumu göster

set -uo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIZLI_JSON="$BASE_DIR/../tahtayoklama/dashboard/config/gizli.json"
VARSAYILAN_TAHTALAR=(9-A 9-B 10-A 11-A 11-B 12-A 12-B fenlab sporodasi)
PAKET="evince"
MASAUSTU="org.gnome.Evince.desktop"

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

# Tek satır: "DURUM <paket:VAR|YOK> <varsayilan:VAR|YOK>"
UZAK_DURUM="p=YOK; dpkg-query -W -f='\${Status}' $PAKET 2>/dev/null | grep -q 'install ok installed' && p=VAR
v=YOK; [ \"\$(xdg-mime query default application/pdf 2>/dev/null)\" = $MASAUSTU ] && v=VAR
echo \"DURUM \$p \$v\""

UZAK_KUR="DEBIAN_FRONTEND=noninteractive apt-get update >/tmp/pdf_kur.log 2>&1; DEBIAN_FRONTEND=noninteractive apt-get install -y $PAKET >>/tmp/pdf_kur.log 2>&1 || { tail -5 /tmp/pdf_kur.log; exit 1; }"

UZAK_VARSAYILAN="set -e
m=~/.config/mimeapps.list
[ -f \"\$m\" ] && [ ! -f \"\$m.bak-pdf\" ] && cp -p \"\$m\" \"\$m.bak-pdf\"
xdg-mime default $MASAUSTU application/pdf
echo VARSAYILAN_TAMAM"

durum() { timeout 30 "$BASE_DIR/tahta-ssh.sh" "$1" "$UZAK_DURUM" 2>/dev/null | grep '^DURUM' | tail -1; }

HATA=0
for t in "${TAHTALAR[@]}"; do
    d=$(durum "$t")
    if [ -z "$d" ]; then
        echo "== $t: HATA — ulaşılamadı"; HATA=1; continue
    fi
    read -r _ paket varsayilan <<<"$d"
    if [ "$paket" = VAR ] && [ "$varsayilan" = VAR ]; then
        echo "== $t: = evince kurulu, varsayılan PDF okuyucu"; continue
    fi
    if [ "$KURU" -eq 1 ]; then
        echo "== $t: ~ yapılacak (paket: $paket, varsayılan: $varsayilan)"; continue
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

    if [ "$varsayilan" = YOK ]; then
        timeout 30 "$BASE_DIR/tahta-ssh.sh" "$t" "$UZAK_VARSAYILAN" 2>/dev/null | grep -q VARSAYILAN_TAMAM \
            || { echo "== $t: HATA — varsayılan ayarlanamadı"; HATA=1; continue; }
    fi

    d=$(durum "$t")
    if [ "$d" = "DURUM VAR VAR" ]; then
        echo "== $t: + tamam (önce: paket $paket, varsayılan $varsayilan)"
    else
        echo "== $t: HATA — doğrulanamadı (${d:-?})"; HATA=1
    fi
done
[ "$KURU" -eq 1 ] && echo "(kuru çalıştırma — hiçbir şey değiştirilmedi)"
exit $HATA
