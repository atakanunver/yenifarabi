"""Bilgi Arenası avatar portrelerini üretir."""

import argparse
import base64
import html
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
HAM = Path.home() / "avatar-uret" / "ham"
CIKTI = KOK / "okul/static/avatar"

# Ad, açılış seviyesi, kostüm adları, değişmeyen karakter betimi, kostüm ayrıntıları.
KARAKTERLER = {
    "kasif": ("Kaşif", 1, ("Kaşif", "Kilim Yelekli Kaşif", "Altın Pusulalı Kaşif"), "A young boy explorer with short dark brown hair, warm brown eyes, tan skin, a beige explorer shirt and a sand-colored background", ("a plain explorer outfit", "a traditional Turkish kilim-patterned vest", "an ornate golden compass")),
    "kasif_kiz": ("Kaşif Kız", 1, ("Kaşif Kız", "Kilim Yelekli Kaşif Kız", "Altın Pusulalı Kaşif Kız"), "A young girl explorer with a dark brown ponytail, warm brown eyes, tan skin, a beige explorer shirt and a peach-colored background", ("a plain explorer outfit", "a traditional Turkish kilim-patterned vest", "an ornate golden compass")),
    "keloglan": ("Keloğlan", 1, ("Keloğlan", "Kalpaklı Keloğlan", "Altın Keloğlan"), "Keloglan, a kind young Turkish folk-tale boy with a bald head, brown eyes, a simple cream tunic and a pale apricot background", ("a simple folk outfit", "a traditional Turkish kalpak hat", "gold-embroidered folk clothing")),
    "robi": ("Robi", 1, ("Robi", "Lale Desenli Robi", "Altın Robi"), "A small friendly rounded blue and silver robot with expressive cyan eyes and a pale blue background", ("a simple smooth metal shell", "traditional Turkish tulip patterns on the shell", "gold-embroidered golden metal detailing")),
    "bilge": ("Bilge Baykuş", 2, ("Bilge Baykuş", "Fesli Bilge Baykuş", "Altın Kanatlı Baykuş"), "A wise brown owl with large amber eyes, cream facial feathers and a muted lavender background", ("natural brown feathers", "a traditional Turkish fez", "gold-embroidered golden wings visible at the shoulders")),
    "van_kedisi": ("Van Kedisi", 2, ("Van Kedisi", "Nazar Boncuklu Van Kedisi", "Altın Tasmalı Van Kedisi"), "A fluffy white Turkish Van cat with one blue eye and one amber eye and a pale turquoise background", ("a simple collar", "a traditional Turkish blue nazar bead on the collar", "a gold-embroidered golden collar")),
    "farabi": ("Farabi", 3, ("Farabi", "Udlu Farabi", "Altın İşlemeli Farabi"), "A respectful portrait of Farabi, a medieval philosopher with a short dark beard, thoughtful brown eyes, a plain historical robe and a muted teal background", ("a simple historical robe", "a traditional Turkish oud held at the shoulder", "a gold-embroidered historical robe")),
    "nasreddin": ("Nasreddin Hoca", 3, ("Nasreddin Hoca", "Kitaplı Nasreddin Hoca", "Altın İşlemeli Nasreddin Hoca"), "A respectful portrait of Nasreddin Hodja, an elderly Anatolian storyteller with a white beard, kind brown eyes, a plain historical robe and a pale olive background", ("a simple historical robe", "a traditional Anatolian bound book held near the shoulder", "a gold-embroidered historical robe")),
    "tilki": ("Akıllı Tilki", 4, ("Akıllı Tilki", "Atkılı Tilki", "Altın Tilki"), "A clever friendly orange fox with a white muzzle, green eyes and a soft mint background", ("natural orange fur", "a traditional Turkish woven scarf", "gold-embroidered golden accents on its outfit")),
    "hurrem": ("Hürrem Sultan", 5, ("Hürrem Sultan", "Taçlı Hürrem Sultan", "Altın İşlemeli Hürrem Sultan"), "A respectful portrait of Hurrem Sultan with uncovered long auburn hair, green eyes, an Ottoman gown and a pale rose background", ("a simple Ottoman gown and uncovered hair", "a traditional Ottoman jeweled crown over uncovered hair", "a gold-embroidered Ottoman gown and a jeweled hair ornament")),
    "dede_korkut": ("Dede Korkut", 5, ("Dede Korkut", "Kopuzlu Dede Korkut", "Altın Kopuzlu Dede Korkut"), "A respectful portrait of Dede Korkut, an elderly Turkic storyteller with a long white beard, kind brown eyes, a plain robe and a muted blue background", ("a simple storyteller's robe", "a traditional Turkic kopuz instrument held at the shoulder", "a gold-embroidered robe and a golden kopuz at the shoulder")),
    "astro": ("Astro", 6, ("Astro", "Bayraklı Astro", "Altın Kasklı Astro"), "A young astronaut with short black hair, brown eyes, a white spacesuit, an open transparent helmet and a soft violet background", ("a plain white spacesuit", "a small traditional Turkish flag patch on the suit", "a gold-embroidered suit and a golden helmet")),
    "piri_reis": ("Piri Reis", 6, ("Piri Reis", "Haritalı Piri Reis", "Altın Pusulalı Piri Reis"), "A respectful portrait of Piri Reis, an Ottoman navigator with a neat dark beard, brown eyes, a blue historical coat and a pale sea-green background", ("a simple navigator's coat", "a traditional Ottoman nautical map held at the shoulder", "a gold-embroidered coat and a golden compass")),
    "suleyman": ("Kanuni Sultan Süleyman", 7, ("Kanuni Sultan Süleyman", "Kaftanlı Kanuni", "Altın Kaftanlı Kanuni"), "A respectful portrait of Suleiman the Magnificent with a neatly trimmed dark beard, brown eyes, Ottoman attire and a muted burgundy background", ("plain Ottoman attire", "a traditional Ottoman patterned kaftan", "a gold-embroidered Ottoman kaftan")),
    "hezarfen": ("Hezarfen Ahmed Çelebi", 7, ("Hezarfen Ahmed Çelebi", "Kanatlı Hezarfen", "Altın Kanatlı Hezarfen"), "A respectful portrait of Hezarfen Ahmed Celebi, an Ottoman aviator with short dark hair, a neat mustache, brown eyes, a simple tunic and a pale sky-blue background", ("a simple Ottoman tunic", "traditional Ottoman-inspired glider wings visible behind the shoulders", "gold-embroidered clothing and golden glider wings behind the shoulders")),
    "mimar_sinan": ("Mimar Sinan", 8, ("Mimar Sinan", "Pergelli Mimar Sinan", "Altın İşlemeli Mimar Sinan"), "A respectful portrait of Mimar Sinan, an elderly Ottoman architect with a short gray beard, brown eyes, a simple robe and a pale stone background", ("a simple architect's robe", "a traditional Ottoman architectural compass held near the shoulder", "a gold-embroidered architect's robe")),
    "ejder": ("Ejder", 8, ("Ejder", "Çini Pullu Ejder", "Altın Ejder"), "A friendly small emerald green dragon with round amber eyes, rounded horns and a pale sage background", ("smooth emerald scales", "traditional Turkish Iznik tile patterns on its scales", "gold-embroidered golden scales")),
}


def istem(kod, n):
    _, _, _, betim, kostumler = KARAKTERLER[kod]
    if n not in (1, 2, 3):
        raise ValueError("Kostüm numarası 1, 2 veya 3 olmalı")
    parilti = ", with a subtle golden shimmer" if n == 3 else ""
    return (
        f"{betim}. Wearing or featuring {kostumler[n - 1]}{parilti}. "
        "Stylized 3D animated-film character portrait, head and shoulders, centered, "
        "facing viewer, friendly smile, soft studio lighting, single plain soft-gradient "
        "background in the specified color, child-friendly, school-appropriate, "
        "respectful and not caricatured, no religious symbols, no headscarf or veil, "
        "no text, no letters, no logos, no frame."
    )


def onizleme_yaz():
    satirlar = ["<!doctype html><html lang='tr'><meta charset='utf-8'><title>Avatar önizleme</title>",
                "<style>main{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:1em}img{width:100%}figure{margin:0}</style><main>"]
    for kod, (_, _, adlar, _, _) in KARAKTERLER.items():
        for n, ad in enumerate(adlar, 1):
            kimlik = f"{kod}-{n}"
            satirlar.append(f'<figure><img src="ham/{kimlik}.png" alt=""><figcaption>{kimlik}: {html.escape(ad)}</figcaption></figure>')
    (HAM.parent / "onizleme.html").write_text("\n".join(satirlar) + "\n</main></html>\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yalniz", nargs="+", metavar="KOD-N")
    parser.add_argument("--kuru", action="store_true")
    args = parser.parse_args()
    tumu = [f"{kod}-{n}" for kod in KARAKTERLER for n in (1, 2, 3)]
    if args.yalniz and set(args.yalniz) - set(tumu):
        parser.error("Bilinmeyen avatar: " + ", ".join(sorted(set(args.yalniz) - set(tumu))))
    secilen = args.yalniz if args.yalniz else tumu
    if args.kuru:
        for kimlik in secilen:
            kod, n = kimlik.rsplit("-", 1)
            print(f"{kimlik}: {istem(kod, int(n))}")
        return 0

    from PIL import Image

    sys.path.insert(0, str(KOK / "tahtayoklama/dashboard"))
    import gorsel

    HAM.mkdir(parents=True, exist_ok=True)
    CIKTI.mkdir(parents=True, exist_ok=True)
    basarisiz = []
    for kimlik in secilen:
        kod, n = kimlik.rsplit("-", 1)
        ham = HAM / f"{kimlik}.png"
        webp = CIKTI / f"{kimlik}.webp"
        ez = bool(args.yalniz)
        if ham.exists() and webp.exists() and not ez:
            print(f"{kimlik}: mevcut, atlandı")
            continue
        try:
            if ez or not ham.exists():
                govde = {"model": gorsel.MODEL, "prompt": istem(kod, int(n)), "size": "1024x1024", "n": 1}
                istek = urllib.request.Request(gorsel.CLIPROXY_URL, data=json.dumps(govde).encode(), headers={"Content-Type": "application/json", "Authorization": f"Bearer {gorsel._anahtar()}"}, method="POST")
                with urllib.request.urlopen(istek, timeout=150) as yanit:
                    png = base64.b64decode(json.load(yanit)["data"][0]["b64_json"], validate=True)
                with Image.open(io.BytesIO(png)) as resim:
                    resim.verify()
                ham.write_bytes(png)
            if ez or not webp.exists():
                with Image.open(ham) as resim:
                    resim.resize((384, 384), Image.Resampling.LANCZOS).save(webp, "WEBP", quality=80, method=6)
            print(f"{kimlik}: hazır")
        except urllib.error.HTTPError as hata:
            print(f"{kimlik}: HTTP {hata.code}")
            basarisiz.append(kimlik)
        except (OSError, ValueError, KeyError, IndexError, TypeError, gorsel.GorselHatasi) as hata:
            print(f"{kimlik}: HTTP yok ({type(hata).__name__})")
            basarisiz.append(kimlik)
    onizleme_yaz()
    if basarisiz:
        print("Başarısız: " + ", ".join(basarisiz))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
