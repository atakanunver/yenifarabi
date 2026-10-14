"""Öğrenci avatarı: özgün SVG karakterler + level ile açılan eşyalar (dış dosya/lisans/CDN yok, koddan üretilir).

Katmanlar: çerçeve (level kademesi, otomatik) > sırt > gövde+karakter > yüz eşyası > şapka.
Seçim (karakter + 3 eşya) `avatar` tablosunda tutulur; açık olup olmadığı SUNUCUDA seviyeye göre doğrulanır
(seviye XP defterinden türetilir). Başkasının avatarı yalnızca liderlik gibi ekranlarda küçük simge olarak görünür.
"""

import itertools
import sqlite3

from markupsafe import Markup

import zaman

_sayac = itertools.count(1)

VARSAYILAN = {"karakter": "kasif", "sapka": "yok", "yuz": "yok", "sirt": "yok"}
KADEMELER = [  # (en düşük seviye, ad, çerçeve rengi, zemin rengi, yıldız)
    (1, "Çaylak", "#7a88c9", "#1d2656", 0),
    (3, "Kaşif", "#34d399", "#12423a", 1),
    (5, "Usta", "#a78bfa", "#2d1f5e", 2),
    (7, "Efsane", "#fbbf24", "#4a3510", 3),
    (9, "Şampiyon", "#22d3ee", "#0b3a4a", 4),
]


def kademe(seviye: int) -> tuple:
    k = KADEMELER[0]
    for x in KADEMELER:
        if seviye >= x[0]:
            k = x
    return k


# --- karakter gövdeleri (viewBox 0 0 100 100; baş merkezi ~ (50, 46)) ---


def _kasif() -> str:
    return (
        '<path d="M20 100 C20 78 34 70 50 70 C66 70 80 78 80 100Z" fill="#4f7cff"/>'
        '<rect x="44" y="62" width="12" height="10" rx="4" fill="#e8b98c"/>'
        '<circle cx="50" cy="46" r="21" fill="#f2c9a0"/>'
        '<path d="M28 44 C26 22 74 22 72 44 C66 34 56 31 50 31 C44 31 34 34 28 44Z" fill="#5b3a29"/>'
        '<circle cx="42" cy="47" r="2.4" fill="#222"/><circle cx="58" cy="47" r="2.4" fill="#222"/>'
        '<circle cx="37" cy="53" r="3" fill="#f7a8a8" opacity=".7"/><circle cx="63" cy="53" r="3" fill="#f7a8a8" opacity=".7"/>'
        '<path d="M43 56 Q50 62 57 56" stroke="#7a3b2e" stroke-width="2" fill="none" stroke-linecap="round"/>'
    )


def _robi() -> str:
    return (
        '<path d="M20 100 C20 80 34 72 50 72 C66 72 80 80 80 100Z" fill="#7a8cb8"/>'
        '<rect x="44" y="64" width="12" height="9" fill="#9aa8c9"/>'
        '<rect x="45" y="82" width="10" height="8" rx="2" fill="#22d3ee"/>'
        '<line x1="50" y1="27" x2="50" y2="16" stroke="#9aa8c9" stroke-width="3"/><circle cx="50" cy="14" r="4" fill="#ff5470"/>'
        '<rect x="29" y="27" width="42" height="38" rx="9" fill="#c7d2e5"/>'
        '<rect x="34" y="38" width="32" height="15" rx="7" fill="#1b2a52"/>'
        '<circle cx="43" cy="45.5" r="3.4" fill="#22d3ee"/><circle cx="57" cy="45.5" r="3.4" fill="#22d3ee"/>'
        '<path d="M43 59 H57" stroke="#6b7aa3" stroke-width="2.4" stroke-linecap="round"/>'
        '<rect x="24" y="40" width="5" height="12" rx="2" fill="#9aa8c9"/><rect x="71" y="40" width="5" height="12" rx="2" fill="#9aa8c9"/>'
    )


def _bilge() -> str:
    return (
        '<path d="M20 100 C20 80 34 72 50 72 C66 72 80 80 80 100Z" fill="#8a5a35"/>'
        '<ellipse cx="50" cy="88" rx="12" ry="14" fill="#d9b48a"/>'
        '<path d="M30 40 L28 22 L42 30Z" fill="#a9794e"/><path d="M70 40 L72 22 L58 30Z" fill="#a9794e"/>'
        '<ellipse cx="50" cy="47" rx="23" ry="22" fill="#a9794e"/>'
        '<circle cx="41" cy="45" r="9" fill="#fff"/><circle cx="59" cy="45" r="9" fill="#fff"/>'
        '<circle cx="42" cy="46" r="4" fill="#222"/><circle cx="58" cy="46" r="4" fill="#222"/>'
        '<circle cx="43.5" cy="44.5" r="1.3" fill="#fff"/><circle cx="59.5" cy="44.5" r="1.3" fill="#fff"/>'
        '<path d="M45 54 L55 54 L50 62Z" fill="#f5a623"/>'
    )


def _tilki() -> str:
    return (
        '<path d="M20 100 C20 80 34 72 50 72 C66 72 80 80 80 100Z" fill="#e07a2f"/>'
        '<path d="M43 74 L50 90 L57 74Z" fill="#fff4e0"/>'
        '<path d="M28 36 L33 14 L47 29Z" fill="#f08a3c"/><path d="M72 36 L67 14 L53 29Z" fill="#f08a3c"/>'
        '<path d="M33 30 L35 21 L42 29Z" fill="#3b2418"/><path d="M67 30 L65 21 L58 29Z" fill="#3b2418"/>'
        '<path d="M27 44 C27 28 73 28 73 44 C73 62 60 68 50 68 C40 68 27 62 27 44Z" fill="#f08a3c"/>'
        '<path d="M35 52 C42 48 58 48 65 52 C62 64 56 68 50 68 C44 68 38 64 35 52Z" fill="#fff4e0"/>'
        '<circle cx="50" cy="55" r="3" fill="#222"/>'
        '<circle cx="41" cy="45" r="2.4" fill="#222"/><circle cx="59" cy="45" r="2.4" fill="#222"/>'
    )


def _astro() -> str:
    return (
        '<path d="M18 100 C18 80 34 72 50 72 C66 72 82 80 82 100Z" fill="#dfe6f3"/>'
        '<rect x="42" y="82" width="16" height="9" rx="2" fill="#ff5470"/><circle cx="50" cy="86.5" r="2" fill="#fff"/>'
        '<circle cx="50" cy="46" r="25" fill="#eef2fa" stroke="#b6c3dc" stroke-width="2"/>'
        '<ellipse cx="50" cy="47" rx="17" ry="14" fill="#1b2a52"/>'
        '<ellipse cx="44" cy="43" rx="5" ry="3" fill="#fff" opacity=".35"/>'
        '<circle cx="44" cy="49" r="2.3" fill="#fff"/><circle cx="56" cy="49" r="2.3" fill="#fff"/>'
        '<path d="M46 55 Q50 58 54 55" stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round"/>'
        '<rect x="72" y="40" width="6" height="12" rx="3" fill="#b6c3dc"/><rect x="22" y="40" width="6" height="12" rx="3" fill="#b6c3dc"/>'
    )


def _ejder() -> str:
    return (
        '<path d="M20 100 C20 80 34 72 50 72 C66 72 80 80 80 100Z" fill="#2f9a63"/>'
        '<path d="M42 74 L50 92 L58 74Z" fill="#c8f0d6"/>'
        '<path d="M36 30 L38 14 L46 28Z" fill="#f2e3a1"/><path d="M64 30 L62 14 L54 28Z" fill="#f2e3a1"/>'
        '<path d="M44 26 L50 16 L56 26Z" fill="#7ad9a3"/>'
        '<circle cx="50" cy="46" r="21" fill="#4fbf7f"/>'
        '<ellipse cx="50" cy="57" rx="12" ry="8" fill="#8fe0b0"/>'
        '<circle cx="46" cy="57" r="1.5" fill="#2f6e4a"/><circle cx="54" cy="57" r="1.5" fill="#2f6e4a"/>'
        '<circle cx="41" cy="44" r="4" fill="#ffd23f"/><circle cx="59" cy="44" r="4" fill="#ffd23f"/>'
        '<ellipse cx="41" cy="44" rx="1.2" ry="3.2" fill="#222"/><ellipse cx="59" cy="44" rx="1.2" ry="3.2" fill="#222"/>'
        '<path d="M45 62 Q50 65 55 62" stroke="#2f6e4a" stroke-width="1.8" fill="none" stroke-linecap="round"/>'
    )


KARAKTERLER = {
    "kasif": ("Kaşif", 1, _kasif),
    "robi": ("Robi", 1, _robi),
    "bilge": ("Bilge Baykuş", 2, _bilge),
    "tilki": ("Akıllı Tilki", 4, _tilki),
    "astro": ("Astro", 6, _astro),
    "ejder": ("Ejder", 8, _ejder),
}

# --- eşyalar ---
SAPKALAR = {
    "yok": ("Şapkasız", 1, ""),
    "kasket": ("Kasket", 2, '<path d="M30 39 C30 22 70 22 70 39Z" fill="#e63946"/><path d="M58 38 H79 Q77 44 66 43Z" fill="#b42330"/>'
              '<circle cx="50" cy="24" r="2.6" fill="#fff"/>'),
    "buyucu": ("Büyücü Şapkası", 4, '<path d="M50 3 L69 37 H31Z" fill="#5b3df5"/><ellipse cx="50" cy="37" rx="23" ry="5" fill="#4630c9"/>'
               '<path d="M50 14 l2 5 5 .5 -4 3.5 1.2 5 -4.2 -2.8 -4.2 2.8 1.2 -5 -4 -3.5 5 -.5Z" fill="#ffd23f"/>'),
    "tac": ("Altın Taç", 7, '<path d="M31 33 L34 15 L43 26 L50 11 L57 26 L66 15 L69 33Z" fill="#ffd23f" stroke="#c9a000" stroke-width="1.5" stroke-linejoin="round"/>'
            '<circle cx="50" cy="26" r="2.4" fill="#e63946"/><circle cx="38" cy="29" r="1.8" fill="#22d3ee"/><circle cx="62" cy="29" r="1.8" fill="#22d3ee"/>'),
    "kulaklik": ("Oyuncu Kulaklığı", 9, '<path d="M28 48 C26 18 74 18 72 48" stroke="#2b2f4a" stroke-width="4.5" fill="none"/>'
                 '<rect x="22" y="40" width="9" height="16" rx="4" fill="#22d3ee"/><rect x="69" y="40" width="9" height="16" rx="4" fill="#22d3ee"/>'),
}
YUZLER = {
    "yok": ("Yüz eşyası yok", 1, ""),
    "gozluk": ("Okuma Gözlüğü", 3, '<circle cx="42" cy="47" r="7.5" fill="#fff" fill-opacity=".18" stroke="#2b2f4a" stroke-width="2"/>'
               '<circle cx="58" cy="47" r="7.5" fill="#fff" fill-opacity=".18" stroke="#2b2f4a" stroke-width="2"/>'
               '<path d="M49.5 46 H50.5" stroke="#2b2f4a" stroke-width="2"/>'),
    "gunes": ("Güneş Gözlüğü", 5, '<rect x="33" y="41" width="15" height="10" rx="4" fill="#111827"/><rect x="52" y="41" width="15" height="10" rx="4" fill="#111827"/>'
              '<path d="M48 45 H52" stroke="#111827" stroke-width="2"/><path d="M36 43 L40 43" stroke="#fff" stroke-opacity=".5" stroke-width="1.5"/>'),
    "maske": ("Kahraman Maskesi", 8, '<path d="M31 42 C38 38 62 38 69 42 C69 52 62 54 57 51 C53 49 47 49 43 51 C38 54 31 52 31 42Z" fill="#e63946"/>'
              '<ellipse cx="42" cy="46" rx="4" ry="3" fill="#fff"/><ellipse cx="58" cy="46" rx="4" ry="3" fill="#fff"/>'),
}
SIRTLAR = {
    "yok": ("Sırt eşyası yok", 1, ""),
    "pelerin": ("Kahraman Pelerini", 6, '<path d="M28 70 L12 100 L88 100 L72 70Z" fill="#e63946"/><path d="M28 70 L20 100 L80 100 L72 70Z" fill="#b42330" opacity=".5"/>'),
    "kanat": ("Işık Kanatları", 10, '<path d="M30 70 C6 60 4 38 10 28 C20 40 30 52 40 62Z" fill="#fff" fill-opacity=".9"/>'
              '<path d="M70 70 C94 60 96 38 90 28 C80 40 70 52 60 62Z" fill="#fff" fill-opacity=".9"/>'),
}
BOLUMLER = {
    "karakter": ("Karakter", KARAKTERLER),
    "sapka": ("Şapka", SAPKALAR),
    "yuz": ("Yüz", YUZLER),
    "sirt": ("Sırt", SIRTLAR),
}


def _yildizlar(n: int, renk: str) -> str:
    konum = [(14, 22), (86, 22), (10, 52), (90, 52)]
    return "".join(
        f'<path d="M{x} {y - 5} l1.8 3.6 4 .6 -2.9 2.8 .7 4 -3.6 -1.9 -3.6 1.9 .7 -4 -2.9 -2.8 4 -.6Z" fill="{renk}"/>'
        for x, y in konum[:n]
    )


def cfg_temiz(cfg: dict | None) -> dict:
    """Bilinmeyen/eksik kodlar varsayılana döner (veritabanı ya da form bozuk olsa da SVG güvenli kalır)."""
    c = dict(VARSAYILAN)
    for bolum, (_, sozluk) in BOLUMLER.items():
        if cfg and cfg.get(bolum) in sozluk:
            c[bolum] = cfg[bolum]
    return c


def svg(cfg: dict | None, seviye: int, boyut: int = 96, etiket: str = "") -> Markup:
    """Avatarın SVG'si (iç içe kullanım için benzersiz clipPath id). Girdi doğrulanır; kullanıcı metni SVG'ye girmez."""
    c = cfg_temiz(cfg)
    _, _, cerceve, zemin, yildiz = kademe(max(1, int(seviye)))
    n = next(_sayac)
    govde = KARAKTERLER[c["karakter"]][2]()
    ad = KARAKTERLER[c["karakter"]][0]
    return Markup(
        f'<svg class="avatar" width="{int(boyut)}" height="{int(boyut)}" viewBox="0 0 100 100" role="img" '
        f'aria-label="{etiket or ad + " avatarı, seviye " + str(int(seviye))}">'
        f'<defs><clipPath id="av{n}"><circle cx="50" cy="50" r="47"/></clipPath></defs>'
        f'<circle cx="50" cy="50" r="47" fill="{zemin}"/>'
        f'<g clip-path="url(#av{n})">{SIRTLAR[c["sirt"]][2]}{govde}{YUZLER[c["yuz"]][2]}</g>'
        f'{SAPKALAR[c["sapka"]][2]}'
        f'<circle cx="50" cy="50" r="47" fill="none" stroke="{cerceve}" stroke-width="{3 + (yildiz > 0)}"/>'
        f'{_yildizlar(yildiz, cerceve)}</svg>'
    )


def acik_mi(bolum: str, kod: str, seviye: int) -> bool:
    return kod in BOLUMLER[bolum][1] and BOLUMLER[bolum][1][kod][1] <= seviye


def getir(conn: sqlite3.Connection, kullanici_id: int) -> dict:
    r = conn.execute("SELECT karakter, sapka, yuz, sirt FROM avatar WHERE kullanici_id = ?", (kullanici_id,)).fetchone()
    return cfg_temiz(dict(r) if r else None)


def kaydet(conn: sqlite3.Connection, kullanici_id: int, cfg: dict, seviye: int) -> dict:
    """Seçimi doğrular (varlık + seviye) ve yazar. Açılmamış eşya seçilmişse ValueError."""
    c = cfg_temiz(cfg)
    for bolum, kod in c.items():
        if not acik_mi(bolum, kod, seviye):
            raise ValueError(f"{BOLUMLER[bolum][1][kod][0]} henüz açılmadı (Seviye {BOLUMLER[bolum][1][kod][1]}).")
    conn.execute(
        "INSERT INTO avatar (kullanici_id, karakter, sapka, yuz, sirt, guncelleme) VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (kullanici_id) DO UPDATE SET karakter = excluded.karakter, sapka = excluded.sapka,"
        " yuz = excluded.yuz, sirt = excluded.sirt, guncelleme = excluded.guncelleme",
        (kullanici_id, c["karakter"], c["sapka"], c["yuz"], c["sirt"], zaman.simdi_str()),
    )
    conn.commit()
    return c


def acilanlar(eski: int, yeni: int) -> list[str]:
    """eski < seviye <= yeni aralığında açılan karakter/eşya adları (seviye atlama bildirimi)."""
    return [
        f"{ad} ({BOLUMLER[b][0].lower()})"
        for b, (_, sozluk) in BOLUMLER.items()
        for kod, (ad, sev, _) in sozluk.items()
        if eski < sev <= yeni and kod != "yok"
    ]


def siradaki_acilis(seviye: int) -> tuple[int, list[str]] | None:
    """Bir sonraki açılış: (seviye, adlar) ya da hepsi açıksa None."""
    ileri = sorted({sev for _, sozluk in BOLUMLER.values() for _, (_, sev, _) in sozluk.items() if sev > seviye})
    if not ileri:
        return None
    return ileri[0], acilanlar(ileri[0] - 1, ileri[0])
