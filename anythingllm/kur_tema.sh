#!/bin/bash
# Atos (AnythingLLM) arayüzüne Farabi tema dosyalarını uygular (idempotent).
# AnythingLLM üretimde index.html'i dosyadan değil utils/boot/MetaGenerator.js içindeki gömülü şablondan sunar;
# bu yüzden <link>+<script> satırı o şablona eklenir. Etkisi için pm2-anythingllm yeniden başlatılmalıdır.
# Kullanım:
#   ./kur_tema.sh              # kur / güncelle (canlıda sudo gerekir)
#   ./kur_tema.sh --geri-al    # şablon işaretini ve farabi-tema dizinini kaldır
# Test için kökler ezilebilir: ATOS_PUBLIC=/tmp/o/public ATOS_META=/tmp/o/MetaGenerator.js ./kur_tema.sh
# AnythingLLM güncellenince (MetaGenerator.js yenilenir) yeniden çalıştır.
set -euo pipefail

KAYNAK="$(cd "$(dirname "$0")" && pwd)/tema"
HEDEF="${ATOS_PUBLIC:-/opt/anythingllm/app/server/public}"
META="${ATOS_META:-/opt/anythingllm/app/server/utils/boot/MetaGenerator.js}"
TEMA_HEDEF="$HEDEF/farabi-tema"
ISARET='<!-- farabi-tema -->'
ANA_SATIR='<link rel="stylesheet" href="/index.css">'
SATIR="            $ISARET<link rel=\"stylesheet\" href=\"/farabi-tema/atos-tema.css\"><script src=\"/farabi-tema/atos-tema.js\"></script>"

GERI_AL=0
if [ "${1:-}" = "--geri-al" ]; then
  GERI_AL=1
elif [ -n "${1:-}" ]; then
  echo "Kullanım: $0 [--geri-al]" >&2
  exit 2
fi

SUDO=""
if [ ! -w "$HEDEF" ] || [ ! -w "$META" ]; then
  SUDO="sudo"
fi

k() {
  if [ -n "$SUDO" ]; then
    sudo "$@"
  else
    "$@"
  fi
}

if ! k test -d "$HEDEF" || ! k test -f "$META"; then
  echo "Hata: hedef dizin veya MetaGenerator.js bulunamadı: $HEDEF / $META" >&2
  exit 1
fi

sahip_ayarla() {
  if [ -n "$SUDO" ] && id anythingllm >/dev/null 2>&1; then
    sudo chown "$@"
  fi
}

dosya_esitle() {
  local src="$1" dst="$2"
  if k test -f "$dst" && k cmp -s "$src" "$dst"; then
    return 0
  fi
  k cp "$src" "$dst"
  k chmod 0644 "$dst"
  sahip_ayarla anythingllm:anythingllm "$dst"
}

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

if [ "$GERI_AL" -eq 1 ]; then
  if k grep -qF "$ISARET" "$META"; then
    k cat "$META" | grep -vF "$ISARET" > "$TMP"
    k cp "$TMP" "$META"
    k chmod 0644 "$META"
    sahip_ayarla anythingllm:anythingllm "$META"
    echo "MetaGenerator.js temizlendi."
  fi
  if k test -d "$TEMA_HEDEF"; then
    k rm -rf "$TEMA_HEDEF"
    echo "farabi-tema dizini kaldırıldı."
  fi
  # Yedek, temizlenmiş dosyayla birebir aynıysa kalıntı bırakma.
  while IFS= read -r yedek; do
    [ -n "$yedek" ] || continue
    if k cmp -s "$yedek" "$META"; then
      k rm -f "$yedek"
    fi
  done < <(k find "$(dirname "$META")" -maxdepth 1 -name "$(basename "$META").yedek-*" -print)
  echo "Uyarı: etkisi için pm2-anythingllm yeniden başlatılmalı."
  exit 0
fi

# 1. Tema dosyalarını kopyala (yalnız değişenleri güncelle)
for d in "$TEMA_HEDEF" "$TEMA_HEDEF/fontlar"; do
  if ! k test -d "$d"; then
    k mkdir -p "$d"
    k chmod 0755 "$d"
    sahip_ayarla anythingllm:anythingllm "$d"
  fi
done

dosya_esitle "$KAYNAK/atos-tema.css" "$TEMA_HEDEF/atos-tema.css"
dosya_esitle "$KAYNAK/atos-tema.js" "$TEMA_HEDEF/atos-tema.js"
for f in "$KAYNAK/fontlar"/*.woff2; do
  [ -f "$f" ] || continue
  dosya_esitle "$f" "$TEMA_HEDEF/fontlar/$(basename "$f")"
done

# 2. MetaGenerator.js şablonuna işaretli satırı ekle (yoksa)
if ! k grep -qF "$ISARET" "$META"; then
  if ! k grep -qF "$ANA_SATIR" "$META"; then
    echo "Hata: MetaGenerator.js içinde $ANA_SATIR bulunamadı (AnythingLLM sürümü değişmiş olabilir)." >&2
    exit 1
  fi
  YEDEK="$META.yedek-$(date +%Y%m%d-%H%M%S)"
  if [ -z "$(k find "$(dirname "$META")" -maxdepth 1 -name "$(basename "$META").yedek-*" -print | head -n1)" ]; then
    k cp "$META" "$YEDEK"
    k chmod 0644 "$YEDEK"
    sahip_ayarla anythingllm:anythingllm "$YEDEK"
    echo "Yedek alındı: $YEDEK"
  fi
  k cat "$META" | python3 -c '
import sys
ana, satir = sys.argv[1], sys.argv[2]
kaynak = sys.stdin.read()
if kaynak.count(ana) != 1:
    sys.stderr.write("Hata: %s tam olarak bir kez bulunmalı.\n" % ana)
    sys.exit(1)
sys.stdout.write(kaynak.replace(ana, ana + "\n" + satir, 1))
' "$ANA_SATIR" "$SATIR" > "$TMP"
  k cp "$TMP" "$META"
  k chmod 0644 "$META"
  sahip_ayarla anythingllm:anythingllm "$META"
  echo "MetaGenerator.js güncellendi."
fi

echo "Tema kurulumu tamamlandı: $TEMA_HEDEF"
echo "Uyarı: şablon bellekte tutulur; etkisi için pm2-anythingllm yeniden başlatılmalı."
