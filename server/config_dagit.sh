#!/bin/bash
# server/config_dagit.sh — GitHub'a GİTMEYEN (gitignore'lu) tahta ayarlarını
# SSH ile tahtalara dağıtır ve hash ile doğrular.
#
# 2026-09-25: kod GitHub'dan çekiliyor (farabiguncelle.sh) ama zil.json,
# ders_programi.json ve api_keys.json gitignore'lu — tahtalarda elle
# kopyalanıp birbirinden kopmuştu (bazılarında zil.json hiç yoktu, Gemini
# anahtarı değişince 8 tahtaya tek tek yazmak gerekti).
#
# Kaynaklar (tek doğru kaynak bu sunucu):
#   ../tahtayoklama/data/zil.json          → client/config/zil.json
#                                            + ~/tahtayoklama/data/zil.json
#   ../mudur/ders_programi.json            → client/config/ders_programi.json
#   config/api_keys_tahta_ortak.json       → client/config/api_keys.json içine
#                                            BİRLEŞTİRİLİR (yalnız ortak alanlar;
#                                            derslik/tahta_anahtari tahtaya özel,
#                                            dokunulmaz)
#
# Kullanım:
#   ./config_dagit.sh                 → varsayılan 8 tahtaya dağıt
#   ./config_dagit.sh 9-A fenlab      → yalnızca verilen tahtalara
#   ./config_dagit.sh --kuru [...]    → hiçbir şey yazmadan farkları göster
#
# Açık bir Farabi penceresi yeni ayarları yeniden başlatılınca alır.

set -uo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZIL="$BASE_DIR/../tahtayoklama/data/zil.json"
DERS_PROGRAMI="$BASE_DIR/../mudur/ders_programi.json"
ORTAK="$BASE_DIR/config/api_keys_tahta_ortak.json"
VARSAYILAN_TAHTALAR=(9-A 9-B 10-A 11-A 11-B 12-A 12-B fenlab)

KURU=0
if [ "${1:-}" = "--kuru" ]; then
    KURU=1
    shift
fi
TAHTALAR=("$@")
[ ${#TAHTALAR[@]} -eq 0 ] && TAHTALAR=("${VARSAYILAN_TAHTALAR[@]}")

for f in "$ZIL" "$DERS_PROGRAMI" "$ORTAK"; do
    [ -f "$f" ] || { echo "HATA: kaynak yok: $f" >&2; exit 1; }
    python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$f" \
        || { echo "HATA: geçersiz JSON: $f" >&2; exit 1; }
done

ZIL_B64=$(base64 -w0 "$ZIL")
DP_B64=$(base64 -w0 "$DERS_PROGRAMI")
ORTAK_B64=$(base64 -w0 "$ORTAK")

# Tahtada koşan kısım. Gizli değer ekrana basılmaz — yalnızca sha256 öneki.
UZAK=$(cat <<'UZAK_SON'
python3 - "$KURU" "$ZIL_B64" "$DP_B64" "$ORTAK_B64" <<'PY'
import base64, hashlib, json, os, sys
kuru = sys.argv[1] == "1"
zil, dp, ortak = (base64.b64decode(a) for a in sys.argv[2:5])
h = lambda b: hashlib.sha256(b).hexdigest()[:8]
ev = os.path.expanduser("~")
client = f"{ev}/farabi/repo/client" if os.path.isdir(f"{ev}/farabi/repo/client") else f"{ev}/farabi/client"
cikti = []

def yaz(yol, icerik, mod=0o644):
    eski = open(yol, "rb").read() if os.path.exists(yol) else None
    ad = yol.replace(ev, "~")
    if eski == icerik:
        cikti.append(f"  = {ad} ({h(icerik)})")
        return
    cikti.append(f"  {'~' if kuru else '+'} {ad} {h(eski) if eski else 'YOK'} -> {h(icerik)}")
    if not kuru:
        tmp = yol + ".tmp"
        with open(tmp, "wb") as f:
            f.write(icerik)
        os.chmod(tmp, mod)
        os.replace(tmp, yol)

if not os.path.isdir(f"{client}/config"):
    print("  HATA: Farabi client kurulu değil:", client); sys.exit(1)
yaz(f"{client}/config/zil.json", zil)
yaz(f"{client}/config/ders_programi.json", dp)
if os.path.isdir(f"{ev}/tahtayoklama/data"):
    yaz(f"{ev}/tahtayoklama/data/zil.json", zil)

ak = f"{client}/config/api_keys.json"
d = json.load(open(ak)) if os.path.exists(ak) else {}
for alan, deger in json.loads(ortak).items():
    if not alan.startswith("_"):
        d[alan] = deger
d.pop("gemini_api_key", None)  # eski tek-anahtar alanı; yalnızca gemini_api_keys kullanılır
eksik = [a for a in ("derslik", "tahta_anahtari") if not d.get(a)]
yaz(ak, (json.dumps(d, ensure_ascii=False, indent=2) + "\n").encode(), 0o600)
if eksik:
    cikti.append(f"  ! tahtaya özel alan eksik: {eksik}")
cikti.append(f"  derslik={d.get('derslik')} mikrofon={d.get('mikrofon')} gemini={h(json.dumps(d.get('gemini_api_keys')).encode())}")
print("\n".join(cikti))
PY
UZAK_SON
)

HATA=0
for t in "${TAHTALAR[@]}"; do
    echo "== $t"
    if ! printf 'KURU=%s ZIL_B64=%s DP_B64=%s ORTAK_B64=%s\n%s\n' \
            "$KURU" "$ZIL_B64" "$DP_B64" "$ORTAK_B64" "$UZAK" \
        | timeout 60 "$BASE_DIR/tahta-ssh.sh" "$t" 'bash -s' 2>&1 | grep -v '^Warning'; then
        echo "  HATA: $t'ye ulaşılamadı ya da yazılamadı"
        HATA=1
    fi
done
[ "$KURU" -eq 1 ] && echo "(kuru çalıştırma — hiçbir dosya değiştirilmedi)"
exit $HATA
