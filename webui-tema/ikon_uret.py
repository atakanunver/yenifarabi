"""farabilogo.jpg → Open WebUI ikon seti (webui-tema/static/).

Çalıştır: /opt/open-webui/venv/bin/python webui-tema/ikon_uret.py
(Pillow yalnızca Open WebUI venv'inde var.)

Kaynak JPG'de sahte dama "şeffaflık" zemini ve küçük boyda okunmayan
"FARABI" yazısı var → yalnızca yuvarlak amblem kesilip dışı gerçekten
şeffaf yapılır. Çember: merkez (511.5, 475), yarıçap ~297 px (ölçüldü).
"""
import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw

KAYNAK = Path("/mnt/farabi-data/farabi/farabilogo.jpg")
HEDEF = Path(__file__).resolve().parent / "static"
CX, CY, R = 511.5, 475, 298
PARSOMEN = (251, 248, 241, 255)

im = Image.open(KAYNAK).convert("RGBA")
kutu = (round(CX - R), round(CY - R), round(CX + R), round(CY + R))
amblem = im.crop(kutu)

# Kenarı yumuşak dairesel maske (4x süper örnekleme)
olcek = 4
boy = amblem.width * olcek
maske = Image.new("L", (boy, boy), 0)
ImageDraw.Draw(maske).ellipse((0, 0, boy - 1, boy - 1), fill=255)
maske = maske.resize(amblem.size, Image.LANCZOS)
amblem.putalpha(maske)


def kare(boyut, dolgu=0.0, zemin=None):
    """Amblemi boyut×boyut tuvale, kenarlarda `dolgu` oranında boşlukla yerleştir."""
    tuval = Image.new("RGBA", (boyut, boyut), zemin or (0, 0, 0, 0))
    ic = round(boyut * (1 - 2 * dolgu))
    parca = amblem.resize((ic, ic), Image.LANCZOS)
    ofs = (boyut - ic) // 2
    tuval.alpha_composite(parca, (ofs, ofs))
    return tuval


kare(512).save(HEDEF / "favicon.png")
kare(96).save(HEDEF / "favicon-96x96.png")
kare(192).save(HEDEF / "web-app-manifest-192x192.png")
kare(512).save(HEDEF / "web-app-manifest-512x512.png")
# iOS şeffaflığı siyaha boyar → parşömen zemin + kenar boşluğu
kare(180, dolgu=0.06, zemin=PARSOMEN).save(HEDEF / "apple-touch-icon.png")
kare(256).save(HEDEF / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
# Yükleme ekranı (loader.js splash.png / splash-dark.png gösterir)
kare(500, dolgu=0.1).save(HEDEF / "splash.png")
kare(500, dolgu=0.1).save(HEDEF / "splash-dark.png")

# favicon.svg: index.html'de PNG'den sonra listeli, bazı tarayıcılar SVG'yi
# tercih eder → içine 256px PNG gömülü SVG
tampon = io.BytesIO()
kare(256).save(tampon, "PNG")
b64 = base64.b64encode(tampon.getvalue()).decode()
(HEDEF / "favicon.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
    f'<image width="256" height="256" href="data:image/png;base64,{b64}"/></svg>\n'
)
print("üretildi:", sorted(p.name for p in HEDEF.iterdir()))
