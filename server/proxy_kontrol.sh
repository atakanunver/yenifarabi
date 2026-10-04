#!/bin/bash
# Farabi'nin internet çıkışını Müdür PC'nin WifiHttpProxy'si (192.168.23.243:8080)
# ÜZERİNDEN mi, yoksa DOĞRUDAN mı yapacağını aç/kapat eder.
#
# 2026-10-04: Asıl iş artık /usr/local/sbin/okul-sunucu'da (kaynak:
# server/okul-sunucu/) — sistem geneli proxy (profile.d + apt) + Ollama
# drop-in'i (ollama.service.d/proxy.conf) birlikte yönetiliyor, dashboard'un
# Sunucular sekmesi de aynı betiği kullanıyor. Bu dosya yalnızca EBYS
# Telegram botunun eski arayüzünü ({ac|kapat|durum}, insan okunur çıktı)
# korumak için ince bir sarmalayıcı — bot `sudo .../proxy_kontrol.sh <eylem>`
# çağırıyor, argümanları değiştirme.
#
# Davranış farkı: ders saatinde (08:00–17:00) Ollama restart'ı artık 17:05'e
# erteleniyor (önceden hemen restart ediyordu, qwen VRAM'dan düşüyordu).

set -euo pipefail

BETIK=/usr/local/sbin/okul-sunucu
calistir() {
    if [ "$(id -u)" -eq 0 ]; then "$BETIK" "$1"; else sudo -n "$BETIK" "$1"; fi
}

ozetle() {
    python3 -c '
import json, sys
d = json.loads(sys.stdin.read().strip().splitlines()[-1])
if "hata" in d and "makine" not in d:
    print("HATA:", d["hata"]); sys.exit(1)
for m in d.get("mesajlar", []):
    print(m)
p = d["proxy"]
etiket = {"acik": "AÇIK", "kapali": "KAPALI", "kismi": "KISMİ"}[p["durum"]]
print("PROXY: %s (sistem=%s, apt=%s, ollama=%s)" % (etiket, p["profil"], p["apt"], p["ollama"]))
if p.get("ollama_restart_bekliyor"):
    print("Ollama restart 17:05 icin ertelendi (ders saati).")
for s in d.get("servisler", []):
    if s["ad"] == "ollama":
        print("ollama.service:", s["durum"])
'
}

case "${1:-durum}" in
    ac)     calistir proxy-ac | ozetle ;;
    kapat)  calistir proxy-kapat | ozetle ;;
    durum)  calistir durum | ozetle ;;
    *)      echo "Kullanım: $0 {ac|kapat|durum}" >&2; exit 1 ;;
esac
