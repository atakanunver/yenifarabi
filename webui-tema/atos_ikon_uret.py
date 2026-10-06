"""Atos amblemi → Open WebUI ikon seti (webui-tema/static/). 2026-10-05: Open WebUI → "Atos".

Çalıştır: /opt/open-webui/venv/bin/python webui-tema/atos_ikon_uret.py
(Pillow yalnızca Open WebUI venv'inde var.) Eski Farabi amblemi: ikon_uret.py.

Amblem tema renklerinden (custom.css): lacivert disk, altın halka, çini mavisi
8 köşeli yıldız (temanın desen motifi) ve ortada altın "A". Dış font yok —
DejaVu Sans Bold (sistemde). 4x süper örnekleme ile çizilip küçültülür.
"""

import base64
import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HEDEF = Path(__file__).resolve().parent / "static"
KAYNAK_KOPYA = Path("/mnt/farabi-data/farabi/atoslogo.png")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
LACIVERT = (31, 42, 107, 255)
CINI = (79, 94, 255, 255)
CINI_KOYU = (60, 72, 214, 255)
ALTIN = (198, 154, 60, 255)
ALTIN_ACIK = (230, 199, 122, 255)
PARSOMEN = (251, 248, 241, 255)


def amblem(boy: int = 1024) -> Image.Image:
    s = boy * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    m = s / 2
    d.ellipse((0, 0, s - 1, s - 1), fill=ALTIN)  # altın dış halka
    k = s * 0.035
    d.ellipse((k, k, s - 1 - k, s - 1 - k), fill=LACIVERT)  # lacivert disk
    k2 = s * 0.075
    d.ellipse(
        (k2, k2, s - 1 - k2, s - 1 - k2), outline=ALTIN_ACIK, width=round(s * 0.008)
    )

    # 8 köşeli yıldız: iki kare (biri 45°) — temanın desen motifi
    r = s * 0.36
    for aci0, renk in ((0, CINI_KOYU), (45, CINI)):
        noktalar = [
            (
                m + r * math.cos(math.radians(aci0 + 45 + 90 * i)),
                m + r * math.sin(math.radians(aci0 + 45 + 90 * i)),
            )
            for i in range(4)
        ]
        d.polygon(noktalar, fill=renk)
    d.ellipse(
        (m - s * 0.215, m - s * 0.215, m + s * 0.215, m + s * 0.215), fill=LACIVERT
    )

    # Altın "A"
    font = ImageFont.truetype(FONT, round(s * 0.30))
    kutu = d.textbbox((0, 0), "A", font=font)
    gx, gy = kutu[2] - kutu[0], kutu[3] - kutu[1]
    d.text(
        (m - gx / 2 - kutu[0], m - gy / 2 - kutu[1] + s * 0.005),
        "A",
        font=font,
        fill=ALTIN_ACIK,
    )
    return im.resize((boy, boy), Image.LANCZOS)


AMBLEM = amblem()


def kare(boyut, dolgu=0.0, zemin=None):
    tuval = Image.new("RGBA", (boyut, boyut), zemin or (0, 0, 0, 0))
    ic = round(boyut * (1 - 2 * dolgu))
    parca = AMBLEM.resize((ic, ic), Image.LANCZOS)
    ofs = (boyut - ic) // 2
    tuval.alpha_composite(parca, (ofs, ofs))
    return tuval


if __name__ == "__main__":
    HEDEF.mkdir(exist_ok=True)
    try:
        AMBLEM.save(KAYNAK_KOPYA)
    except OSError:
        pass
    kare(512).save(HEDEF / "favicon.png")
    kare(512).save(HEDEF / "logo.png")
    kare(96).save(HEDEF / "favicon-96x96.png")
    kare(192).save(HEDEF / "web-app-manifest-192x192.png")
    kare(512).save(HEDEF / "web-app-manifest-512x512.png")
    # iOS şeffaflığı siyaha boyar → parşömen zemin + kenar boşluğu
    kare(180, dolgu=0.06, zemin=PARSOMEN).save(HEDEF / "apple-touch-icon.png")
    kare(256).save(HEDEF / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    kare(500, dolgu=0.1).save(HEDEF / "splash.png")
    kare(500, dolgu=0.1).save(HEDEF / "splash-dark.png")
    tampon = io.BytesIO()
    kare(256).save(tampon, "PNG")
    b64 = base64.b64encode(tampon.getvalue()).decode()
    (HEDEF / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
        f'<image width="256" height="256" href="data:image/png;base64,{b64}"/></svg>\n'
    )
    print("üretildi:", sorted(p.name for p in HEDEF.iterdir()))
