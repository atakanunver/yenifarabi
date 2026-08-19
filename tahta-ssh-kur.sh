#!/bin/bash
# tahta-ssh-kur.sh — Yeni bir Farabi tahtasında SSH sunucusunu kurar ve
# Farabi server'ının (farabi.local) bu tahtaya bağlanabilmesi için kendi
# public key'ini authorized_keys'e ekler.
#
# 2026-08-19: 9-A tahtasında (etap) elle yapılan kurulumun (bkz. o oturumun
# notları) genel/tekrar-kullanılabilir hâli — flash bellekle fiziksel
# olarak her yeni tahtada çalıştırılmak üzere hazırlandı.
#
# Bu script YALNIZCA "server -> tahta" yönünü kurar (server bu tahtaya
# bağlanabilsin diye). "tahta -> server" yönü (gece senkron/pull için)
# AYRI bir script'in işi: client/farabi-kurulum.sh (zaten var, 9-A'da
# kullanılmıyor ama diğer tahtalar için tam bunun için yazılmıştı) —
# onu da aynı flash bellekten ayrıca çalıştırın.
#
# Kullanım (tahtada, fiziksel erişimle):
#   bash tahta-ssh-kur.sh
# sudo şifresi istenecek (apt install + systemctl için) — tahtaların
# hepsinde aynı olduğu belirtilen kullanıcı (ogretmen) zaten sudo yetkili
# olmalı, 9-A'da olduğu gibi.

set -euo pipefail

# farabi-server-to-tahta — server'daki ~/.ssh/id_ed25519_tahta.pub, sabit.
# Bu SADECE bir PUBLIC key'dir, gizli değil — flash bellekte taşınması güvenlik
# sorunu yaratmaz (özel anahtar hep server'da kalır, hiçbir zaman buraya kopyalanmaz).
SERVER_PUBLIC_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG5DEY0RF2fY8YPhqU+u1276NDChf5oeM9X8TGfP/rc/ farabi-server-to-tahta"

echo "== Farabi SSH kurulumu ($(hostname), $(hostname -I | awk '{print $1}')) =="

echo "[1/5] openssh-server kurulu mu kontrol ediliyor..."
if dpkg -l 2>/dev/null | grep -q '^ii.*openssh-server'; then
    echo "      zaten kurulu."
else
    echo "      kuruluyor (sudo şifresi istenebilir)..."
    sudo apt-get update -qq
    sudo apt-get install -y openssh-server
fi

echo "[2/5] ssh servisi açılışta aktif ediliyor ve başlatılıyor..."
sudo systemctl enable --now ssh

echo "[3/5] ~/.ssh/authorized_keys'e server'ın public key'i ekleniyor..."
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"
if grep -qF "$SERVER_PUBLIC_KEY" "$HOME/.ssh/authorized_keys" 2>/dev/null; then
    echo "      zaten ekli, atlanıyor (tekrar çalıştırmak güvenli)."
else
    echo "$SERVER_PUBLIC_KEY" >> "$HOME/.ssh/authorized_keys"
    echo "      eklendi."
fi
chmod 600 "$HOME/.ssh/authorized_keys"

echo "[4/5] parolasız sudo (NOPASSWD) kuruluyor — server'dan uzaktan komut"
echo "      çalıştırırken tekrar parola sorulmasın diye (kullanıcı kararı,"
echo "      2026-08-19: ALL=NOPASSWD:ALL, sınırsız kapsam)..."
SUDOERS_DOSYA="/etc/sudoers.d/farabi-nopasswd"
SUDOERS_SATIR="$(whoami) ALL=(ALL) NOPASSWD: ALL"
if sudo test -f "$SUDOERS_DOSYA" && sudo grep -qF "$SUDOERS_SATIR" "$SUDOERS_DOSYA" 2>/dev/null; then
    echo "      zaten kurulu, atlanıyor."
else
    GECICI=$(mktemp)
    echo "$SUDOERS_SATIR" > "$GECICI"
    if sudo visudo -cf "$GECICI" >/dev/null 2>&1; then
        sudo install -m 0440 -o root -g root "$GECICI" "$SUDOERS_DOSYA"
        echo "      kuruldu: $SUDOERS_DOSYA"
    else
        echo "      HATA: sudoers satırı visudo doğrulamasından geçemedi, kurulmadı." >&2
    fi
    rm -f "$GECICI"
fi

echo "[5/5] doğrulama..."
systemctl is-active --quiet ssh && echo "      ssh servisi: aktif" || echo "      UYARI: ssh servisi aktif değil"

echo
echo "== Tamamlandı =="
sudo -n true 2>/dev/null && echo "Parolasız sudo : ÇALIŞIYOR" || echo "Parolasız sudo : kontrol edilemedi (kabuk yeniden başlatılmış olabilir, tekrar deneyin)"
echo "Bu tahtanın IP'si : $(hostname -I | awk '{print $1}')"
echo "Bu tahtanın adı   : $(hostname)"
echo "Kullanıcı         : $(whoami)"
echo
echo "Server tarafında bu tahtaya bağlanmayı test etmek için:"
echo "  ssh -i ~/.ssh/id_ed25519_tahta $(whoami)@$(hostname -I | awk '{print $1}')"
echo
echo "Bu tahtanın hangi sınıf/derslik olduğunu (config/api_keys.json'daki"
echo "'derslik' alanı) not edip merkezi listeye eklemeyi unutmayın."
