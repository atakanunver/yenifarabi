#!/usr/bin/env python3
"""tahtaayar/tahta_fix_uygula.py — bilinen işletim sistemi düzeltmelerini
bir/tüm tahtalara uygular.

Hem insan hem ajan (Claude Code vb.) tarafından elle çalıştırılmak üzere
tasarlandı — bir tahta ağa yeniden bağlandığında, yeni kurulduğunda ya da
yeni bir fix eklendiğinde "şu tahtaları güncel hâle getir" demek için.
Otomatik/periyodik ÇALIŞMAZ, crontab'a eklenmedi (mudur/ders_programi_yukle.py'nin
"tek seferlik, elle" ilkesiyle aynı, bkz. o dosyanın docstring'i). Ayrıntı,
gerekçe ve "Güç düğmesi" bulgusunun tam hikâyesi: tahtaayar/CLAUDE.md.

2026-09-15'te `tahtayoklama/dashboard/scripts/`'ten buraya TAŞINDI (kopya
bırakılmadı) — OS/oturum düzeyi provizyon hem `client/` hem `tahtayoklama/`
altında koşan ortak bir katman, tek proje ile sınırlı değil.

Şu an içerdiği fix'ler
-----------------------
1. **guc_tusu_yoksay** (2026-09-14, 9-B/11-B'de yaşanan gerçek olay
   sonrası): ACPI güç düğmesine kısa basış sistemi anında kapatıyordu
   (systemd varsayılanı HandlePowerKey=poweroff — `journalctl`'de "Power
   key pressed short" -> "The system will power off now!" ile doğrulandı).
   Fix: /etc/systemd/logind.conf.d/90-guc-tusu-yoksay.conf ile
   HandlePowerKey=ignore, sonra systemd-logind'e SIGHUP (oturumları
   KESMEDEN canlı reload — `systemctl reload` bu servis için desteklenmiyor).
2. **guc_tusu_uzun_basis_yoksay** (2026-09-15): UZUN basış için aynı
   mantık, ayrı bir drop-in dosyada (90-...'a dokunmaz). 9-A'da etkin
   değer zaten systemd varsayılanıyla "ignore" idi — bu fix, gelecekteki
   farklı bir OS varsayılanına karşı açıkça SABİTLER (yalnızca etkin
   değere değil, drop-in dosyasının varlığına da bakar).
3. **uyku_hedefleri_maskeli** (2026-09-15): sleep/suspend/hibernate/
   hybrid-sleep target'ları maskeli olsun — tahtalar hiç uykuya geçmesin.
   9-A ve 12-A'da zaten böyleydi; bu fix mevcut durumu yeni/sıfırlanmış
   bir tahtada yeniden üretir.
4. **cinnamon_guc_tusu_yoksay** (2026-09-15): Cinnamon'un KENDİ güç
   düğmesi eylemi (`button-power` gsettings anahtarı) — systemd/logind'den
   TAMAMEN BAĞIMSIZ ikinci bir yol, 1'deki fix bunu kapsamaz. 7 aktif
   tahtanın 5'inde hâlâ `'shutdown'` idi, yalnızca 10-A ve 12-B'de daha
   önce elle `'nothing'`'e çekilmişti (script'e hiç yazılmamıştı — bu
   fix'in var olma nedeni tam olarak bu). Kullanıcı onaylı hedef değer:
   `'nothing'` (2026-09-15). **root_gerekli=False** — bu tek fix `ogretmen`
   olarak, sudo'suz çalışır (gsettings kullanıcı düzeyi bir ayardır),
   aktif bir masaüstü oturumu (D-Bus soketi) gerektirir.

Yeni bir fix eklemek için DUZELTMELER listesine bir `Duzeltme` ekleyin —
`kontrol_komutu` çıktısı `beklenen` ile eşleşiyorsa "zaten uygulanmış"
sayılır, eşleşmiyorsa `uygula_komutu` çalıştırılıp tekrar kontrol edilir.
**Kural: `kontrol_komutu` hem "zaten doğru" hem "düzeltilmesi gerek"
durumunda çıkış kodu 0 ile bitmeli** (ör. `systemctl is-enabled` maskeli
birimde 0 değil 1 döner — `|| true` ile sarmalanmalı). Sıfır olmayan çıkış
kodu bu script'te "tahtaya ulaşılamadı" ile ayırt edilemez ve fix sessizce
hiç uygulanmaz.

Kimlik doğrulama — İKİ çalıştırma bağlamı
-------------------------------------------
**root_gerekli=True (varsayılan, çoğu fix):** SSH `~/.ssh/id_ed25519_tahta`
anahtarıyla `etapadmin` olarak — bu, `server/tahta-ssh.sh --admin`'in
kullandığı AYNI anahtar (etapadmin'in ayrı bir anahtarı yok, aynı anahtar
hem ogretmen hem etapadmin için kayıtlı). Yalnızca `sudo` parolaya ihtiyaç
duyuyor; `server/tahtalar.json`'daki nota göre bazı tahtalarda NOPASSWD
kurulu (`sudo -n` önce denenir), bazılarında SSH giriş parolasıyla aynı
parola isteniyor — o parola iki aday dosyadan (bkz. GIZLI_JSON_ADAYLARI,
önce `tahtaayar/config/gizli.json`, yoksa `tahtayoklama/dashboard/config/
gizli.json`) `"etapadmin_sifre"` alanından okunur (gitignore'lu — REPO
PUBLIC, bu alan asla commit edilecek dosyaya düz metin yazılmaz). Parola
İKİ dosyaya da kopyalanmaz, tek gerçek kaynak `tahtayoklama/dashboard/
config/gizli.json`'da kalır.

**root_gerekli=False (yalnızca cinnamon_guc_tusu_yoksay):** SSH aynı
anahtarla `ogretmen` olarak, sudo hiç çağrılmaz — gsettings/dconf gibi
kullanıcı düzeyi ayarlar için. Aktif bir masaüstü oturumu (D-Bus soketi,
`/run/user/$(id -u)/bus`) gerektirir; sıfır kurulmuş, hiç giriş yapılmamış
bir tahtada bu fix başarısız olur ve "uygulanamadı" raporlar — o tahtada
script ilk öğretmen girişinden sonra tekrar çalıştırılmalı.

Kullanım
---------
    python3 tahtaayar/tahta_fix_uygula.py                          # tüm tahtalar
    python3 tahtaayar/tahta_fix_uygula.py --tahta 9-B               # tek tahta
    python3 tahtaayar/tahta_fix_uygula.py --sadece-kontrol          # uygulamadan yalnızca durum raporu
    python3 tahtaayar/tahta_fix_uygula.py --duzeltme uyku_hedefleri_maskeli  # tek düzeltme
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TAHTAAYAR_DIR = Path(__file__).resolve().parent
FARABI_DIR = TAHTAAYAR_DIR.parent

TAHTALAR_JSON = FARABI_DIR / "server" / "tahtalar.json"
# Parola TEK yerde tutulur, kopyalanmaz — önce tahtaayar'ın kendi config'i
# (bugün yok, yalnızca yol açık), yoksa tahtayoklama panosununki (bugünkü
# gerçek kaynak).
GIZLI_JSON_ADAYLARI = (
    TAHTAAYAR_DIR / "config" / "gizli.json",
    FARABI_DIR / "tahtayoklama" / "dashboard" / "config" / "gizli.json",
)
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
    # False → 'ogretmen' olarak, sudo'suz çalıştırılır (gsettings/dconf gibi
    # kullanıcı düzeyi ayarlar). Varsayılan True: mevcut düzeltmelerin hiçbiri
    # etkilenmez.
    root_gerekli: bool = True


# Cinnamon'un kendi güç düğmesi eylemi (button-power) — systemd/logind'den
# BAĞIMSIZ ikinci bir yol, bkz. tahtaayar/CLAUDE.md "Güç düğmesi" bölümü.
# 'nothing' = tuşa basınca hiçbir şey olmaz; ekran karartma zaten ayrı bir
# yoldan (sleep-display-ac = 600 sn boşta kalma, 7 tahtada da doğrulandı)
# geliyor. Değer kullanıcı onaylı (2026-09-15).
CINNAMON_GUC_TUSU_HEDEFI = "nothing"
_CINNAMON_GUC_SEMASI = "org.cinnamon.settings-daemon.plugins.power"
# gsettings YAZMA işlemi oturum D-Bus'ı ister; okuma istemez. Aktif 'ogretmen'
# oturumu yoksa bu önek başarısız olur ve fix "uygulanamadı" raporlar (sessiz
# başarısızlık değil) — 7 aktif tahtada da oturum soketi doğrulandı (2026-09-15).
_OGRETMEN_OTURUM_ONEKI = (
    "export XDG_RUNTIME_DIR=/run/user/$(id -u); "
    "export DBUS_SESSION_BUS_ADDRESS=unix:path=$XDG_RUNTIME_DIR/bus; "
)

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
    Duzeltme(
        ad="guc_tusu_uzun_basis_yoksay",
        aciklama="Güç düğmesine UZUN basış da yoksayılsın — systemd varsayılanına güvenme, açıkça sabitle",
        kontrol_komutu=(
            "{ grep -qx 'HandlePowerKeyLongPress=ignore' "
            "/etc/systemd/logind.conf.d/91-guc-tusu-uzun-basis.conf 2>/dev/null "
            "&& echo dosya=var || echo dosya=yok; } ; "
            "busctl get-property org.freedesktop.login1 /org/freedesktop/login1 "
            "org.freedesktop.login1.Manager HandlePowerKeyLongPress"
        ),
        beklenen=b'dosya=var\ns "ignore"',
        uygula_komutu=(
            "mkdir -p /etc/systemd/logind.conf.d && "
            "printf '%s\\n' '[Login]' 'HandlePowerKeyLongPress=ignore' "
            "> /etc/systemd/logind.conf.d/91-guc-tusu-uzun-basis.conf && "
            "systemctl kill -s HUP systemd-logind.service"
        ),
    ),
    Duzeltme(
        ad="uyku_hedefleri_maskeli",
        aciklama="Uyku/askıya alma hiç devreye girmesin (sleep/suspend/hibernate/hybrid-sleep maskeli)",
        kontrol_komutu=(
            "systemctl is-enabled sleep.target suspend.target hibernate.target "
            "hybrid-sleep.target 2>/dev/null || true"
        ),
        beklenen=b"masked\nmasked\nmasked\nmasked",
        uygula_komutu=(
            "systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target"
        ),
    ),
    Duzeltme(
        ad="cinnamon_guc_tusu_yoksay",
        aciklama=(
            "Cinnamon'un KENDİ güç düğmesi eylemi (button-power) kapatmayı tetiklemesin — "
            "systemd/logind'den BAĞIMSIZ ikinci bir yol"
        ),
        root_gerekli=False,
        kontrol_komutu=_OGRETMEN_OTURUM_ONEKI + f"gsettings get {_CINNAMON_GUC_SEMASI} button-power",
        beklenen=f"'{CINNAMON_GUC_TUSU_HEDEFI}'".encode(),
        uygula_komutu=(
            _OGRETMEN_OTURUM_ONEKI
            + f"gsettings set {_CINNAMON_GUC_SEMASI} button-power {CINNAMON_GUC_TUSU_HEDEFI}"
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
    değil, yalnızca `sudo -n` başarısız olursa kullanılır. İki aday dosya
    sırayla denenir, bkz. GIZLI_JSON_ADAYLARI."""
    for yol in GIZLI_JSON_ADAYLARI:
        if not yol.exists():
            continue
        veri = json.loads(yol.read_text(encoding="utf-8"))
        sifre = veri.get("etapadmin_sifre")
        if sifre:
            return sifre
    return None


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


def _duzeltme_komutu_calistir(
    fix: Duzeltme, ip: str, bilgi: dict, sifre: str | None, komut: str
) -> tuple[bool, bytes, bytes]:
    """Düzeltmenin gerektirdiği kullanıcı/yetki bağlamını seçer — root
    gerekiyorsa etapadmin+sudo, gerekmiyorsa (gsettings/dconf gibi kullanıcı
    düzeyi ayarlar) doğrudan ogretmen, sudo hiç çağrılmadan."""
    if fix.root_gerekli:
        return _root_komutu_calistir(ip, bilgi.get("admin", "etapadmin"), komut, sifre)
    sonuc = _ssh_calistir(ip, bilgi.get("kullanici", "ogretmen"), komut, b"")
    return sonuc.returncode == 0, sonuc.stdout, sonuc.stderr


def tahtayi_isle(
    ad: str, bilgi: dict, sifre: str | None, sadece_kontrol: bool, duzeltmeler: list[Duzeltme]
) -> None:
    ip = bilgi["ip"]
    print(f"\n== {ad} ({ip}) ==")

    for fix in duzeltmeler:
        basarili, cikti, hata = _duzeltme_komutu_calistir(fix, ip, bilgi, sifre, fix.kontrol_komutu)
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
        basarili, _, hata = _duzeltme_komutu_calistir(fix, ip, bilgi, sifre, fix.uygula_komutu)
        if not basarili:
            print(f"  ✗ {fix.ad}: uygulama başarısız — {hata.decode(errors='replace').strip()[:200]}")
            continue

        basarili, cikti, hata = _duzeltme_komutu_calistir(fix, ip, bilgi, sifre, fix.kontrol_komutu)
        if basarili and cikti.strip() == fix.beklenen:
            print(f"  ✓ {fix.ad}: uygulandı ve doğrulandı.")
        else:
            print(f"  ✗ {fix.ad}: uygulandı ama doğrulama beklenen değeri vermedi ({cikti!r}).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tahta", help="Yalnızca bu tahtaya uygula (server/tahtalar.json'daki ad).")
    parser.add_argument("--sadece-kontrol", action="store_true", help="Uygulamadan yalnızca mevcut durumu raporla.")
    parser.add_argument("--duzeltme", help="Yalnızca bu adlı düzeltmeyi işle (varsayılan: hepsi).")
    args = parser.parse_args()

    if args.duzeltme is not None:
        gecerli_adlar = [f.ad for f in DUZELTMELER]
        if args.duzeltme not in gecerli_adlar:
            print(f"HATA: '{args.duzeltme}' bilinmiyor. Geçerli adlar: {', '.join(gecerli_adlar)}", file=sys.stderr)
            sys.exit(1)
        duzeltmeler = [f for f in DUZELTMELER if f.ad == args.duzeltme]
    else:
        duzeltmeler = DUZELTMELER

    tahtalar = _tahtalari_yukle(args.tahta)
    sifre = _sudo_sifresi()
    if sifre is None:
        adaylar = ", ".join(str(y) for y in GIZLI_JSON_ADAYLARI)
        print(
            f"[bilgi] {adaylar} içinde \"etapadmin_sifre\" yok — yalnızca "
            "NOPASSWD kurulu tahtalarda işe yarayacak, gerisi atlanacak.",
            file=sys.stderr,
        )

    for ad, bilgi in tahtalar.items():
        try:
            tahtayi_isle(ad, bilgi, sifre, args.sadece_kontrol, duzeltmeler)
        except subprocess.TimeoutExpired:
            print(f"\n== {ad} ({bilgi['ip']}) ==\n  ✗ zaman aşımı — tahta ulaşılamıyor olabilir.")


if __name__ == "__main__":
    main()
