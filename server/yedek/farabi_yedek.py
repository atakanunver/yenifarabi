#!/usr/bin/env python3
"""Farabi veri yedegi -> Debian NAS (rsync/ssh, kisitli anahtar).

SQLite: sqlite3.backup (canli DB icin tutarli kopya) + integrity_check.
PostgreSQL: pg_dump -Fc (farabi, soru_havuzu, okul_ana).
Yapilandirma: git disi config/*.json + baglanti dosyalari tek yapilandirma.tar.gz (0600; sifre/anahtar icerir).
Kaynak: repoda server/yedek/farabi_yedek.py; /home/ata/farabi-yedek/farabi-yedek.py buna sembolik baglantidir.
Hedef: debian.local:YedekFarabi/<YYYY-MM-DD>/ (rrsync ile kisitli).
Hata olursa cikis kodu != 0 (systemd 'failed' gorur).
"""

import datetime
import hashlib
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

HOME = Path("/home/ata")
SQLITE = {
    "yoklama_pano.db": HOME / "farabi/tahtayoklama/dashboard/veri/yoklama_pano.db",
    "okul.db": HOME / "farabi/okul/veri/okul.db",
    "smssistemi.db": HOME / "farabi/smssistemi/veri/smssistemi.db",
    "sonuclar.db": HOME / "farabi/arenasinif/veri/sonuclar.db",
}
PG_DB = ("farabi", "soru_havuzu", "okul_ana")
# HOME'a gore kalip; yeni config dosyasi eklenince kendiliginden yedege girer. Repo PUBLIC, bu dosyalar git disi.
YAPILANDIRMA = (
    "farabi/tahtayoklama/dashboard/config/*.json",
    "farabi/okul/config/*.json",
    "farabi/smssistemi/config/*.json",
    "farabi/server/config/*.json",
    "farabi/server/tahtalar.json",
    "farabi/kazanimtest/config/*.json",
    "farabi/kameralar/hareket/ayar.json",
    ".config/okul-ana/baglanti",
    ".pgpass",
)
STAGING = HOME / "yedek-staging"
HEDEF = "ata@debian.local"
ANAHTAR = HOME / ".ssh/id_ed25519_yedek"
BUGUN = datetime.date.today().isoformat()  # noqa: DTZ011 - sunucu saat dilimi Europe/Istanbul


def sqlite_yedekle(ad: str, kaynak: Path, hedef_dizin: Path) -> None:
    hedef = hedef_dizin / ad
    src = sqlite3.connect(f"file:{kaynak}?mode=ro", uri=True)
    dst = sqlite3.connect(hedef)
    try:
        src.backup(dst)
        sonuc = dst.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        dst.close()
        src.close()
    if sonuc != "ok":
        raise RuntimeError(f"{ad}: integrity_check={sonuc}")


def pg_yedekle(db: str, hedef_dizin: Path) -> None:
    with open(hedef_dizin / f"{db}.pgdump", "wb") as f:
        subprocess.run(
            ["sudo", "-n", "-u", "postgres", "pg_dump", "-Fc", db],
            stdout=f,
            check=True,
        )


def yapilandirma_yedekle(hedef_dizin: Path, home: Path = HOME) -> int:
    """Kalibin eslestirdigi dosyalari yapilandirma.tar.gz'ye koyar (0600); dosya sayisini doner."""
    dosyalar = sorted({p for kalip in YAPILANDIRMA for p in home.glob(kalip) if p.is_file()})
    if not dosyalar:
        raise RuntimeError("yapilandirma dosyasi bulunamadi")
    hedef = hedef_dizin / "yapilandirma.tar.gz"
    hedef.touch(mode=0o600)
    with tarfile.open(hedef, "w:gz") as tar:
        for p in dosyalar:
            tar.add(p, arcname=str(p.relative_to(home)))
    hedef.chmod(0o600)
    return len(dosyalar)


def manifest(hedef_dizin: Path) -> None:
    satirlar = []
    for p in sorted(hedef_dizin.iterdir()):
        if p.name == "SHA256SUMS":
            continue
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        satirlar.append(f"{h}  {p.name}")
    (hedef_dizin / "SHA256SUMS").write_text("\n".join(satirlar) + "\n")


def main() -> int:
    gun = STAGING / BUGUN
    if gun.exists():
        shutil.rmtree(gun)
    gun.mkdir(parents=True)
    for ad, kaynak in SQLITE.items():
        sqlite_yedekle(ad, kaynak, gun)
    for db in PG_DB:
        pg_yedekle(db, gun)
    n = yapilandirma_yedekle(gun)
    manifest(gun)
    subprocess.run(
        [
            "rsync",
            "-a",
            "--partial",
            "-e",
            f"ssh -i {ANAHTAR} -o IdentitiesOnly=yes -o BatchMode=yes",
            f"{gun}/",
            f"{HEDEF}:{BUGUN}/",
        ],
        check=True,
    )
    shutil.rmtree(gun)
    print(f"yedek tamam: {BUGUN} (yapilandirma: {n} dosya)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 - hata mesajini journal'a yaz
        print(f"YEDEK HATASI: {e}", file=sys.stderr)
        sys.exit(1)
