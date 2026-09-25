#!/bin/bash
# server/geogebra_dagit.sh — GeoGebra çevrimdışı paketini (Math Apps Bundle)
# tahtaların client/icerik/geogebra/GeoGebra dizinine SSH ile kopyalar.
#
# 2026-09-25: client/actions/geogebra.py paketi önce tahtada arar, yoksa
# sunucunun /geogebra/ yolundan çekip önbelleğe alır. Ama sunucudan SOĞUK
# yükleme GeoGebra'nın parça yükleyicisini sık takıyor (fenlab ölçümü: 5'te 3;
# araç Chrome'u bir kez yeniden açıp ~11 sn'de toparlıyor) ve geometry/3d ilk
# açılışta başka parçalar çekiyor. Paket tahtada tam dururken ~3 sn, takılma
# yok. Paket gitignore'lu (client/.gitignore: icerik/*) ve farabiguncelle.sh
# yalnız `reset --hard` yaptığı için güncellemede silinmez.
#
# Kaynak: /mnt/farabi-data/farabi/geogebra/GeoGebra (server/main.py'nin
# /geogebra/ bağlamasıyla aynı dizin — paket güncellenince önce orayı değiştir).
#
# Kullanım:
#   ./geogebra_dagit.sh                 → varsayılan 8 tahtaya
#   ./geogebra_dagit.sh 9-A fenlab      → yalnızca verilen tahtalara
#   ./geogebra_dagit.sh --kuru [...]    → yalnızca hangi tahtada eksik/farklı olduğunu göster
#
# Tahtadaki paket aynıysa (dosya adı+boyut özeti) kopyalanmaz. Yazma önce
# GeoGebra.yeni'ye yapılır, sonra yer değiştirilir — yarım paket kalmaz.

set -uo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KAYNAK_UST="/mnt/farabi-data/farabi/geogebra"
VARSAYILAN_TAHTALAR=(9-A 9-B 10-A 11-A 11-B 12-A 12-B fenlab)

KURU=0
if [ "${1:-}" = "--kuru" ]; then
    KURU=1
    shift
fi
TAHTALAR=("$@")
[ ${#TAHTALAR[@]} -eq 0 ] && TAHTALAR=("${VARSAYILAN_TAHTALAR[@]}")

[ -f "$KAYNAK_UST/GeoGebra/deployggb.js" ] || { echo "HATA: paket yok: $KAYNAK_UST/GeoGebra" >&2; exit 1; }

ozet() { (cd "$1" && find . -type f -printf '%P %s\n' | LC_ALL=C sort | sha256sum | cut -c1-12); }
YEREL=$(ozet "$KAYNAK_UST/GeoGebra")
echo "kaynak özeti: $YEREL ($(du -sh "$KAYNAK_UST/GeoGebra" | cut -f1))"

# Tahtada client dizinini bulur (9-A'da ~/farabi/repo/client) ve paket özetini basar.
UZAK_OZET='c=~/farabi/client; [ -d ~/farabi/repo/client ] && c=~/farabi/repo/client
[ -d "$c" ] || { echo "CLIENT_YOK"; exit 0; }
g="$c/icerik/geogebra/GeoGebra"
if [ -f "$g/deployggb.js" ]; then (cd "$g" && find . -type f -printf "%P %s\n" | LC_ALL=C sort | sha256sum | cut -c1-12); else echo YOK; fi'

UZAK_YAZ='set -e
c=~/farabi/client; [ -d ~/farabi/repo/client ] && c=~/farabi/repo/client
d="$c/icerik/geogebra"; mkdir -p "$d"
rm -rf "$d/GeoGebra.yeni" "$d/GeoGebra.eski"
mkdir "$d/GeoGebra.yeni"
tar -C "$d/GeoGebra.yeni" -xf -
[ -f "$d/GeoGebra.yeni/deployggb.js" ]
[ -d "$d/GeoGebra" ] && mv "$d/GeoGebra" "$d/GeoGebra.eski"
mv "$d/GeoGebra.yeni" "$d/GeoGebra"
rm -rf "$d/GeoGebra.eski"
(cd "$d/GeoGebra" && find . -type f -printf "%P %s\n" | LC_ALL=C sort | sha256sum | cut -c1-12)'

HATA=0
for t in "${TAHTALAR[@]}"; do
    uzak=$(timeout 30 "$BASE_DIR/tahta-ssh.sh" "$t" "$UZAK_OZET" 2>/dev/null | tail -1)
    if [ -z "$uzak" ]; then
        echo "== $t: HATA — ulaşılamadı"; HATA=1; continue
    fi
    if [ "$uzak" = "CLIENT_YOK" ]; then
        echo "== $t: HATA — Farabi client kurulu değil"; HATA=1; continue
    fi
    if [ "$uzak" = "$YEREL" ]; then
        echo "== $t: = güncel ($uzak)"; continue
    fi
    if [ "$KURU" -eq 1 ]; then
        echo "== $t: ~ kopyalanacak ($uzak -> $YEREL)"; continue
    fi
    yeni=$(tar -C "$KAYNAK_UST/GeoGebra" -cf - . \
        | timeout 300 "$BASE_DIR/tahta-ssh.sh" "$t" "$UZAK_YAZ" 2>/dev/null | tail -1)
    if [ "$yeni" = "$YEREL" ]; then
        echo "== $t: + kopyalandı ($uzak -> $yeni)"
    else
        echo "== $t: HATA — kopyalama doğrulanamadı (tahtada: ${yeni:-?})"; HATA=1
    fi
done
[ "$KURU" -eq 1 ] && echo "(kuru çalıştırma — hiçbir dosya değiştirilmedi)"
exit $HATA
