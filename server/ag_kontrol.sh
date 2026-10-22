#!/bin/bash
# Farabi bagimliliklari (ad cozumleme + port) kontrolu. Sorun varsa journal'a WARNING yazar.
# IP degisimi sonrasi hangi bagimliligin koptugunu gostermek icin (2026-10-19).
H=/home/ata/farabi/tahtayoklama/dashboard/veri/ag_kontrol.json; fail=0; out=""
chk() { # ad host port
  if [[ "$2" =~ ^[0-9.]+$ ]]; then ip="$2"; else ip=$(getent hosts "$2" | awk "{print \$1; exit}"); fi
  if [ -z "$ip" ]; then r="ad-cozulmedi"; fail=1
  elif timeout 4 bash -c "</dev/tcp/$ip/$3" 2>/dev/null; then r="ok"
  else r="port-kapali"; fail=1; fi
  out="$out\"$1\":{\"host\":\"$2\",\"ip\":\"${ip:-}\",\"port\":$3,\"durum\":\"$r\"},"
  [ "$r" = ok ] || logger -t farabi-ag-kontrol -p user.warning "$1 $2:$3 -> $r"
}
chk proxy_mudur_pc  mudur.local   8080
chk sms_modem_yolu  mudur.local   18080
chk dvr_kamera      192.168.23.99 554
chk debian_tts      debian.local  5002
chk bilgehan_embed  bilgehan.local 8040
chk bilgehan_ses    bilgehan.local 8060
chk zil_paneli      zil.local     8090
echo "{\"zaman\":\"$(date -Is)\",\"sorun\":$fail,\"kontroller\":{${out%,}}}" > "$H"
exit 0
