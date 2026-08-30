"""Tahtalara doğrudan SSH — server/tahta-ssh.sh'ı shell-out etmiyoruz (o
etkileşimli kullanım için tasarlandı), aynı anahtar/kullanıcı konvansiyonunu
Python'da eşzamanlı (asyncio) tekrar ediyoruz.

paramiko YOK — plain `ssh` binary + asyncio.create_subprocess_exec, repo
genelindeki "hafif tut" konvansiyonuna uygun.
"""

import asyncio
import re
from pathlib import Path

SSH_ANAHTARI = Path.home() / ".ssh" / "id_ed25519_tahta"
BAGLANTI_ZAMAN_ASIMI_SN = 5
KOMUT_ZAMAN_ASIMI_SN = 15

_TARIH_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_AD_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class SSHSonuc:
    __slots__ = ("basarili", "stdout", "stderr", "zaman_asimi")

    def __init__(self, basarili: bool, stdout: bytes, stderr: bytes, zaman_asimi: bool = False):
        self.basarili = basarili
        self.stdout = stdout
        self.stderr = stderr
        self.zaman_asimi = zaman_asimi


def tarih_dogrula(tarih: str) -> str:
    if not _TARIH_RE.match(tarih):
        raise ValueError(f"Geçersiz tarih formatı: {tarih!r}")
    return tarih


def ad_dogrula(ad: str) -> str:
    """Sınıf/tahta adı — bu değer sonradan tahtada dosya adı/komut parçası
    olacağı için sıkı bir allow-list ile sınırlanıyor."""
    if not _AD_RE.match(ad):
        raise ValueError(f"Geçersiz ad formatı: {ad!r}")
    return ad


async def komut_calistir(
    ip: str,
    kullanici: str,
    komut: str,
    stdin_bytes: bytes | None = None,
    zaman_asimi: float = KOMUT_ZAMAN_ASIMI_SN,
) -> SSHSonuc:
    """Tek bir SSH komutu çalıştırır. Argüman listesiyle (shell string değil)
    çağrılır — komut enjeksiyonu riskini bir katman daha azaltır; yine de
    `komut` içine gömülen her değişken değer, çağıran tarafta önce
    tarih_dogrula/ad_dogrula'dan geçmiş olmalı."""
    argumanlar = [
        "ssh",
        "-i", str(SSH_ANAHTARI),
        "-o", "BatchMode=yes",  # anahtar çalışmazsa şifre istemine asılı kalma
        "-o", f"ConnectTimeout={BAGLANTI_ZAMAN_ASIMI_SN}",
        "-o", "StrictHostKeyChecking=accept-new",
        "-n" if stdin_bytes is None else "-T",
        f"{kullanici}@{ip}",
        komut,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argumanlar,
            stdin=asyncio.subprocess.PIPE if stdin_bytes is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as e:
        return SSHSonuc(False, b"", str(e).encode())

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(stdin_bytes), timeout=zaman_asimi
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return SSHSonuc(False, b"", b"zaman_asimi", zaman_asimi=True)

    return SSHSonuc(proc.returncode == 0, stdout, stderr)


async def scp_gonder(ip: str, kullanici: str, yerel_yol: Path, uzak_yol: str,
                      zaman_asimi: float = KOMUT_ZAMAN_ASIMI_SN) -> SSHSonuc:
    argumanlar = [
        "scp",
        "-i", str(SSH_ANAHTARI),
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={BAGLANTI_ZAMAN_ASIMI_SN}",
        "-o", "StrictHostKeyChecking=accept-new",
        str(yerel_yol),
        f"{kullanici}@{ip}:{uzak_yol}",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argumanlar,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as e:
        return SSHSonuc(False, b"", str(e).encode())

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=zaman_asimi)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return SSHSonuc(False, b"", b"zaman_asimi", zaman_asimi=True)

    return SSHSonuc(proc.returncode == 0, stdout, stderr)


_DURUM_TARAMA_KOMUTU = """python3 -c "
import json, glob, os, sys
tarih = sys.argv[1]
kdir = os.path.expanduser('~/tahtayoklama/data/kayitlar')
sonuc = {}
if os.path.isdir(kdir):
    for yol in glob.glob(os.path.join(kdir, tarih + '_*_ders*.json')):
        try:
            with open(yol, encoding='utf-8') as f:
                sonuc[os.path.basename(yol)] = json.load(f)
        except Exception as e:
            sonuc[os.path.basename(yol)] = {'_hata': str(e)}
print(json.dumps(sonuc, ensure_ascii=False))
" "__TARIH__\""""


async def tahtanin_kayitlarini_tara(ip: str, kullanici: str, tarih: str) -> SSHSonuc:
    """Bir tahtanın data/kayitlar/ dizinindeki, verilen tarihe ait TÜM
    kayıtları tek SSH çağrısıyla getirir (dosya başına ayrı çağrı değil)."""
    tarih_dogrula(tarih)
    # .format() değil str.replace() — komut metninde json dict literalleri
    # ({'_hata': ...}) zaten süslü parantez içeriyor, .format() bunları
    # yanlışlıkla yer tutucu sanır.
    komut = _DURUM_TARAMA_KOMUTU.replace("__TARIH__", tarih)
    return await komut_calistir(ip, kullanici, komut)
