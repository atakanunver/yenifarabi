"""scripts/tahta_istemci_kur.py — tahtalara tahta_istemci.py'yi kurar /
günceller (2026-10-06). Tekrar çalıştırılabilir: her çalıştırmada tahta için
YENİ token üretilir, sunucudaki özet (config/tahta_tokenlari.json) değişir.

Kullanım (dashboard/ dizininden):
    venv/bin/python scripts/tahta_istemci_kur.py 9-A 9-B     # belirli tahtalar
    venv/bin/python scripts/tahta_istemci_kur.py --hepsi     # DB'deki tüm aktif tahtalar
    venv/bin/python scripts/tahta_istemci_kur.py --kaldir 9-A

Tahtaya `ogretmen` olarak SSH (sudo YOK): ~/tahtayoklama/tahta_istemci.py,
~/tahtayoklama/istemci.json (0600) ve ~/.config/systemd/user/
tahta-istemci.service yazılır, birim enable+restart edilir. Kapalı
tahtalar atlanır — sonra yeniden çalıştırın.
"""

import argparse
import asyncio
import hashlib
import json
import secrets
import sys
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DASHBOARD_DIR))

import db  # noqa: E402
import ssh_istemci  # noqa: E402

ISTEMCI_KAYNAK = DASHBOARD_DIR.parent / "tahta_istemci.py"
TOKEN_DOSYASI = DASHBOARD_DIR / "config" / "tahta_tokenlari.json"
VARSAYILAN_SUNUCU = "http://192.168.23.252:8010"

BIRIM = """[Unit]
Description=Tahta yoklama istemcisi (tahtayoklama/tahta_istemci.py)

[Service]
ExecStart=/usr/bin/python3 %h/tahtayoklama/tahta_istemci.py
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
"""


def _tokenlari_oku() -> dict:
    try:
        return json.loads(TOKEN_DOSYASI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _token_yaz(tahta: str, ozet: str | None) -> None:
    tokenlar = _tokenlari_oku()
    if ozet is None:
        tokenlar.pop(tahta, None)
    else:
        tokenlar[tahta] = ozet
    TOKEN_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
    gecici = TOKEN_DOSYASI.with_suffix(".tmp")
    gecici.write_text(json.dumps(tokenlar, indent=2, ensure_ascii=False), encoding="utf-8")
    gecici.chmod(0o600)
    gecici.replace(TOKEN_DOSYASI)


async def _kur(tahta: dict, sunucu: str) -> str:
    ip, kul, ad = tahta["ip"], tahta["ssh_kullanici"], tahta["ad"]
    s = await ssh_istemci.scp_gonder(ip, kul, ISTEMCI_KAYNAK, "tahtayoklama/tahta_istemci.py")
    if not s.basarili:
        return f"HATA scp: {s.stderr.decode(errors='replace').strip()[:120]}"

    token = secrets.token_urlsafe(32)
    ayar = json.dumps({"sunucu": sunucu, "token": token}).encode()
    s = await ssh_istemci.komut_calistir(
        ip, kul,
        "umask 077 && cat > ~/tahtayoklama/istemci.json.tmp && "
        "mv ~/tahtayoklama/istemci.json.tmp ~/tahtayoklama/istemci.json",
        stdin_bytes=ayar,
    )
    if not s.basarili:
        return f"HATA ayar: {s.stderr.decode(errors='replace').strip()[:120]}"
    s = await ssh_istemci.komut_calistir(
        ip, kul,
        "mkdir -p ~/.config/systemd/user && "
        "cat > ~/.config/systemd/user/tahta-istemci.service",
        stdin_bytes=BIRIM.encode(),
    )
    if not s.basarili:
        return f"HATA birim: {s.stderr.decode(errors='replace').strip()[:120]}"

    _token_yaz(ad, hashlib.sha256(token.encode()).hexdigest())

    s = await ssh_istemci.komut_calistir(
        ip, kul,
        "systemctl --user daemon-reload && "
        "systemctl --user enable tahta-istemci.service >/dev/null 2>&1 && "
        "systemctl --user restart tahta-istemci.service && sleep 3 && "
        "systemctl --user is-active tahta-istemci.service",
        zaman_asimi=30,
    )
    cikti = (s.stdout + s.stderr).decode(errors="replace").strip()
    return "tamam (active)" if s.basarili else f"HATA systemctl: {cikti[:160]}"


async def _kaldir(tahta: dict) -> str:
    s = await ssh_istemci.komut_calistir(
        tahta["ip"], tahta["ssh_kullanici"],
        "systemctl --user disable --now tahta-istemci.service >/dev/null 2>&1; "
        "rm -f ~/.config/systemd/user/tahta-istemci.service ~/tahtayoklama/istemci.json; "
        "systemctl --user daemon-reload; echo kaldirildi",
    )
    _token_yaz(tahta["ad"], None)
    return "kaldırıldı" if s.basarili else "HATA (token yine de silindi)"


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("tahtalar", nargs="*")
    p.add_argument("--hepsi", action="store_true")
    p.add_argument("--kaldir", action="store_true")
    p.add_argument("--sunucu", default=VARSAYILAN_SUNUCU)
    a = p.parse_args()
    if not a.hepsi and not a.tahtalar:
        p.error("tahta adı ya da --hepsi verin")

    conn = db.baglanti()
    try:
        tum = {r["ad"]: dict(r) for r in conn.execute(
            "SELECT ad, ip, ssh_kullanici FROM tahtalar WHERE aktif = 1"
        )}
    finally:
        conn.close()
    hedefler = list(tum) if a.hepsi else a.tahtalar
    bilinmeyen = [h for h in hedefler if h not in tum]
    if bilinmeyen:
        print(f"Bilinmeyen tahta: {', '.join(bilinmeyen)}")
        return 2

    # Sıralı — token dosyasına eşzamanlı yazma olmasın.
    hata = False
    for ad in hedefler:
        sonuc = await (_kaldir(tum[ad]) if a.kaldir else _kur(tum[ad], a.sunucu))
        hata |= sonuc.startswith("HATA")
        print(f"{ad:10} {sonuc}")
    return 1 if hata else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
