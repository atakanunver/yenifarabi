#!/bin/sh
# Kullanim: sudo sh kur.sh <PROXY_URL>   (dosyalar ayni dizinde olmali)
# Proxy durumunu DEGISTIRMEZ — yalnizca betikleri ve kurallari yerlestirir.
set -eu
cd "$(dirname "$0")"
install -o root -g root -m 755 okul-sunucu /usr/local/sbin/okul-sunucu
install -o root -g root -m 755 okul-sunucu-ssh /usr/local/sbin/okul-sunucu-ssh
if [ ! -f /etc/okul-sunucu.conf ]; then
    umask 077
    printf 'PROXY_URL=%s\n' "$1" > /etc/okul-sunucu.conf
fi
chown root:root /etc/okul-sunucu.conf; chmod 600 /etc/okul-sunucu.conf
cp sudoers-okul-sunucu /tmp/okul-sunucu.sudoers
visudo -cf /tmp/okul-sunucu.sudoers
install -o root -g root -m 440 /tmp/okul-sunucu.sudoers /etc/sudoers.d/okul-sunucu
rm -f /tmp/okul-sunucu.sudoers
visudo -c >/dev/null && echo "sudoers OK"
