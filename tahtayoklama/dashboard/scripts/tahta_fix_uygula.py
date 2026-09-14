#!/usr/bin/env python3
"""dashboard/scripts/tahta_fix_uygula.py — bilinen işletim sistemi
düzeltmelerini bir/tüm tahtalara uygular.

Hem insan hem ajan (Claude Code vb.) tarafından elle çalıştırılmak üzere
tasarlandı — bir tahta ağa yeniden bağlandığında ya da yeni bir fix
eklendiğinde "şu tahtaları güncel hâle getir" demek için. Otomatik/periyodik
ÇALIŞMAZ, crontab'a eklenmedi (mudur/ders_programi_yukle.py'nin "tek
seferlik, elle" ilkesiyle aynı, bkz. o dosyanın docstring'i).

Şu an içerdiği fix'ler
-----------------------
1. **guc_tusu_yoksay** (2026-09-14, 9-B/11-B'de yaşanan gerçek olay
   sonrası — bkz. tahtayoklama/CLAUDE.md "Güç düğmesi" bölümü): ACPI güç
   düğmesine kısa basış sistemi anında kapatıyordu (systemd varsayılanı
   HandlePowerKey=poweroff — `journalctl`'de "Power key pressed short" ->
   "The system will power off now!" ile doğrulandı). Fix:
   /etc/systemd/logind.conf.d/90-guc-tusu-yoksay.conf ile
   HandlePowerKey=ignore, sonra systemd-logind'e SIGHUP (oturumları
   KESMEDEN canlı reload — `systemctl reload` bu servis için desteklenmiyor).
   İdempotent: `busctl get-property ... HandlePowerKey` zaten "ignore"
   dönüyorsa atlanır.

Yeni bir fix eklemek için DUZELTMELER listesine bir `Duzeltme` ekleyin —
`kontrol_komutu` çıktısı `beklenen` ile eşleşiyorsa "zaten uygulanmış"
sayılır, eşleşmiyorsa `uygula_komutu` çalıştırılıp tekrar kontrol edilir.

Kimlik doğrulama
-----------------
SSH bağlantısı `~/.ssh/id_ed25519_tahta` anahtarıyla `etapadmin` olarak —
bu, `server/tahta-ssh.sh --admin`'in kullandığı AYNI anahtar (etapadmin'in
ayrı bir anahtarı yok, aynı anahtar hem ogretmen hem etapadmin için kayıtlı).
Yalnızca `sudo` parolaya ihtiyaç duyuyor; `server/tahtalar.json`'daki nota
göre bazı tahtalarda NOPASSWD kurulu (`sudo -n` önce denenir), bazılarında
SSH giriş parolasıyla aynı parola isteniyor — o parola
`dashboard/config/gizli.json`'daki `"etapadmin_sifre"` alanından okunur
(gitignore'lu — REPO PUBLIC, bu alan asla commit edilecek dosyaya düz metin
yazılmaz, yalnızca elle/yerel olarak doldurulur).

Kullanım (dashboard/ dizininden)
----------------------------------
    venv/bin/python scripts/tahta_fix_uygula.py                 # tüm tahtalar
    venv/bin/python scripts/tahta_fix_uygula.py --tahta 9-B      # tek tahta
    venv/bin/python scripts/tahta_fix_uygula.py --sadece-kontrol # uygulamadan yalnızca durum raporu
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
TAHTAYOKLAMA_DIR = DASHBOARD_DIR.parent
SERVER_DIR = TAHTAYOKLAMA_DIR.parent / "server"

TAHTALAR_JSON = SERVER_DIR / "tahtalar.json"
GIZLI_JSON = DASHBOARD_DIR / "config" / "gizli.json"
SSH_ANAHTARI = Path.home() / ".ssh" / "id_ed25519_tahta"

SSH_BAGLANTI_ZAMAN_ASIMI_SN = 8
SSH_KOMUT_ZAMAN_ASIMI_SN = 20


@dataclass
class Duzeltme:
    ad: str
    aciklama: str
    kontrol_komutu: str
    beklenen: bytes
    uygula_komutu: str


DUZELTMELER = [
    Duzeltme(
        ad="guc_tusu_yoksay",
        aciklama="Güç düğmesine kısa basış anında poweroff yapmasın",
        kontrol_komutu=(
            "busctl get-property org.freedesktop.login1 /org/freedesktop/login1 "
            "org.freedesktop.login1.Manager HandlePowerKey"
        ),
        beklenen=b's "ignore"',
        uygula_komutu=(
            "mkdir -p /etc/systemd/logind.conf.d && "
            "printf '%s\\n' '[Login]' 'HandlePowerKey=ignore' "
            "> /etc/systemd/logind.conf.d/90-guc-tusu-yoksay.conf && "
            "systemctl kill -s HUP systemd-logind.service"
        ),
    ),
]


def _tahtalari_yukle(tek_tahta: str | None) -> dict[str, dict]:
    if not TAHTALAR_JSON.exists():
        print(f"HATA: {TAHTALAR_JSON} bulunamadı.", file=sys.stderr)
        sys.exit(1)
    veri = json.loads(TAHTALAR_JSON.read_text(encoding="utf-8"))
    tahtalar = {ad: bilgi for ad, bilgi in veri.items() if not ad.startswith("_")}
    if tek_tahta is None:
        return tahtalar
    if tek_tahta not in tahtalar:
        print(f"HATA: '{tek_tahta}' {TAHTALAR_JSON}'da kayıtlı değil.", file=sys.stderr)
        sys.exit(1)
    return {tek_tahta: tahtalar[tek_tahta]}


def _sudo_sifresi() -> str | None:
    """NOPASSWD kurulu tahtalarda hiç gerekmeyebilir — bu yüzden zorunlu
    değil, yalnızca `sudo -n` başarısız olursa kullanılır."""
    if not GIZLI_JSON.exists():
        return None
    veri = json.loads(GIZLI_JSON.read_text(encoding="utf-8"))
    return veri.get("etapadmin_sifre")


def _ssh_calistir(ip: str, admin_kullanici: str, komut: str, stdin_bytes: bytes) -> subprocess.CompletedProcess:
    argumanlar = [
        "ssh", "-i", str(SSH_ANAHTARI),
        "-o", f"ConnectTimeout={SSH_BAGLANTI_ZAMAN_ASIMI_SN}",
        "-o", "StrictHostKeyChecking=accept-new",
        "-T",
        f"{admin_kullanici}@{ip}",
        komut,
    ]
    return subprocess.run(
        argumanlar, input=stdin_bytes, capture_output=True,
        timeout=SSH_KOMUT_ZAMAN_ASIMI_SN,
    )


def _root_komutu_calistir(ip: str, admin_kullanici: str, iç_komut: str, sifre: str | None) -> tuple[bool, bytes, bytes]:
    """Önce `sudo -n` (parolasız) dener — server/tahtalar.json'daki nota göre
    bazı tahtalarda NOPASSWD kurulu; başarısız olursa parolayla `sudo -S`."""
    nopasswd_komutu = f"sudo -n bash -c {iç_komut!r}"
    sonuc = _ssh_calistir(ip, admin_kullanici, nopasswd_komutu, b"")
    if sonuc.returncode == 0:
        return True, sonuc.stdout, sonuc.stderr

    if not sifre:
        return False, sonuc.stdout, (
            sonuc.stderr + b"\n[NOPASSWD calismadi ve gizli.json'da etapadmin_sifre yok]"
        )

    sifreli_komut = f"sudo -S -p '' bash -c {iç_komut!r}"
    sonuc = _ssh_calistir(ip, admin_kullanici, sifreli_komut, (sifre + "\n").encode())
    return sonuc.returncode == 0, sonuc.stdout, sonuc.stderr


def tahtayi_isle(ad: str, bilgi: dict, sifre: str | None, sadece_kontrol: bool) -> None:
    ip = bilgi["ip"]
    admin_kullanici = bilgi.get("admin", "etapadmin")
    print(f"\n== {ad} ({ip}) ==")

    for fix in DUZELTMELER:
        basarili, cikti, hata = _root_komutu_calistir(ip, admin_kullanici, fix.kontrol_komutu, sifre)
        if not basarili:
            print(f"  ✗ {fix.ad}: kontrol edilemedi — {hata.decode(errors='replace').strip()[:200]}")
            continue

        if cikti.strip() == fix.beklenen:
            print(f"  ✓ {fix.ad}: zaten uygulanmış.")
            continue

        if sadece_kontrol:
            print(f"  ⚠ {fix.ad}: UYGULANMAMIŞ (--sadece-kontrol, değiştirilmedi).")
            continue

        print(f"  … {fix.ad}: uygulanıyor ({fix.aciklama})...")
        basarili, _, hata = _root_komutu_calistir(ip, admin_kullanici, fix.uygula_komutu, sifre)
        if not basarili:
            print(f"  ✗ {fix.ad}: uygulama başarısız — {hata.decode(errors='replace').strip()[:200]}")
            continue

        basarili, cikti, hata = _root_komutu_calistir(ip, admin_kullanici, fix.kontrol_komutu, sifre)
        if basarili and cikti.strip() == fix.beklenen:
            print(f"  ✓ {fix.ad}: uygulandı ve doğrulandı.")
        else:
            print(f"  ✗ {fix.ad}: uygulandı ama doğrulama beklenen değeri vermedi ({cikti!r}).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tahta", help="Yalnızca bu tahtaya uygula (server/tahtalar.json'daki ad).")
    parser.add_argument("--sadece-kontrol", action="store_true", help="Uygulamadan yalnızca mevcut durumu raporla.")
    args = parser.parse_args()

    tahtalar = _tahtalari_yukle(args.tahta)
    sifre = _sudo_sifresi()
    if sifre is None:
        print(
            f"[bilgi] {GIZLI_JSON} içinde \"etapadmin_sifre\" yok — yalnızca "
            "NOPASSWD kurulu tahtalarda işe yarayacak, gerisi atlanacak.",
            file=sys.stderr,
        )

    for ad, bilgi in tahtalar.items():
        try:
            tahtayi_isle(ad, bilgi, sifre, args.sadece_kontrol)
        except subprocess.TimeoutExpired:
            print(f"\n== {ad} ({bilgi['ip']}) ==\n  ✗ zaman aşımı — tahta ulaşılamıyor olabilir.")


if __name__ == "__main__":
    main()
