"""Tahtalara duvar kağıdı gönderir / eskisine döndürür (ssh_istemci + tahta_kaydi yeniden kullanılır).

Kullanım: python scripts/duvar_kagidi.py (--tahta AD | --hepsi) [--kuru] [--geri-al] --png YOL
İçe aktarma: `await gonder(tahta_adi, png_yolu)` / `await geri_al(tahta_adi)` -> {"tahta","basarili","detay"}.
İlk gönderimde mevcut arka plan onceki-arkaplan.txt'ye yazılır, sonraki gönderimlerde üzerine yazılmaz.
"""

import argparse
import asyncio
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ssh_istemci
import tahta_kaydi

UZAK_DIZIN = ".local/share/farabi"
PNG_AD = "hafta-birincileri.png"
YEDEK_AD = "onceki-arkaplan.txt"
ANAHTAR = "org.cinnamon.desktop.background"


def _tahta_bul(ad: str) -> dict | None:
    try:
        ssh_istemci.ad_dogrula(ad)
    except ValueError:
        return None
    return next((t for t in tahta_kaydi.tahtalari_yukle() if t["ad"] == ad), None)


def _sonuc(t: dict, basarili: bool, detay: str) -> dict:
    return {"tahta": t["ad"], "basarili": basarili, "detay": detay}


def _hata_metni(s) -> str:
    return "zaman aşımı" if s.zaman_asimi else s.stderr.decode(errors="replace")[:200]


async def _gsettings(t: dict, ic_komut: str):
    """DISPLAY/DBUS ortamıyla bash -c çalıştırır; ortam yoksa None döner."""
    ortam = await ssh_istemci.x_ortamini_kesfet(t["ip"], t["kullanici"])
    if ortam is None:
        return None
    display, xauthority, uid = ortam
    komut = (
        f"env DISPLAY={shlex.quote(display)} XAUTHORITY={shlex.quote(xauthority)} "
        f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{shlex.quote(uid)}/bus "
        f"bash -c {shlex.quote(ic_komut)}"
    )
    return await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], komut)


async def gonder(tahta_adi: str, png_yolu) -> dict:
    t = _tahta_bul(tahta_adi)
    if t is None:
        return {"tahta": tahta_adi, "basarili": False, "detay": "Bilinmeyen tahta."}
    png = Path(png_yolu)
    if not png.is_file():
        return _sonuc(t, False, f"PNG bulunamadı: {png}")
    ev = f"/home/{t['kullanici']}"
    dizin = f"{ev}/{UZAK_DIZIN}"
    uzak_png = f"{dizin}/{PNG_AD}"
    yedek = f"{dizin}/{YEDEK_AD}"

    mk = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], f"mkdir -p {shlex.quote(dizin)}")
    if not mk.basarili:
        return _sonuc(t, False, f"Dizin oluşturulamadı: {_hata_metni(mk)}")
    sc = await ssh_istemci.scp_gonder(t["ip"], t["kullanici"], png, uzak_png, zaman_asimi=60)
    if not sc.basarili:
        return _sonuc(t, False, f"Dosya gönderilemedi: {_hata_metni(sc)}")

    uri = f"file://{uzak_png}"
    ic_komut = (
        f"[ -f {shlex.quote(yedek)} ] || gsettings get {ANAHTAR} picture-uri > {shlex.quote(yedek)}; "
        f"gsettings set {ANAHTAR} picture-uri {shlex.quote(uri)} && "
        f"gsettings set {ANAHTAR} picture-options zoom"
    )
    s = await _gsettings(t, ic_komut)
    if s is None:
        return _sonuc(t, False, "Dosya gönderildi ama aktif oturum yok.")
    if not s.basarili:
        return _sonuc(t, False, _hata_metni(s))
    return _sonuc(t, True, "Duvar kağıdı ayarlandı.")


async def geri_al(tahta_adi: str) -> dict:
    t = _tahta_bul(tahta_adi)
    if t is None:
        return {"tahta": tahta_adi, "basarili": False, "detay": "Bilinmeyen tahta."}
    yedek = f"/home/{t['kullanici']}/{UZAK_DIZIN}/{YEDEK_AD}"
    ic_komut = (
        f"[ -s {shlex.quote(yedek)} ] || {{ echo yedek yok >&2; exit 3; }}; "
        f"gsettings set {ANAHTAR} picture-uri \"$(cat {shlex.quote(yedek)})\""
    )
    s = await _gsettings(t, ic_komut)
    if s is None:
        return _sonuc(t, False, "Aktif oturum yok.")
    if not s.basarili:
        return _sonuc(t, False, _hata_metni(s))
    return _sonuc(t, True, "Önceki arka plana dönüldü.")


async def _calistir(args) -> int:
    if args.hepsi:
        adlar = [t["ad"] for t in tahta_kaydi.tahtalari_yukle()]
    else:
        adlar = [args.tahta]
    islem = "geri al" if args.geri_al else f"gönder ({args.png})"
    if args.kuru:
        for ad in adlar:
            bilinen = "" if _tahta_bul(ad) else " [BİLİNMEYEN TAHTA]"
            print(f"KURU {ad}: {islem}{bilinen}")
        return 0
    hata = 0
    for ad in adlar:
        r = await (geri_al(ad) if args.geri_al else gonder(ad, args.png))
        print(f"{'ok  ' if r['basarili'] else 'HATA'} {ad}: {r['detay']}")
        hata += not r["basarili"]
    return 1 if hata else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--tahta")
    g.add_argument("--hepsi", action="store_true")
    p.add_argument("--kuru", action="store_true")
    p.add_argument("--geri-al", action="store_true")
    p.add_argument("--png", required=True)
    args = p.parse_args(argv)
    if not args.geri_al and not Path(args.png).is_file():
        p.error(f"PNG bulunamadı: {args.png}")
    return asyncio.run(_calistir(args))


if __name__ == "__main__":
    sys.exit(main())
