"""Öğrenci avatarı: seviyeye göre açılan karakter ve kostümler."""

import itertools
import sqlite3

import zaman
from markupsafe import Markup, escape

_sayac = itertools.count(1)
VARSAYILAN = {"karakter": "kasif", "kostum": "1"}
KADEMELER = [
    (1, "Çaylak", "#7a88c9", "#1d2656", 0),
    (3, "Kaşif", "#34d399", "#12423a", 1),
    (5, "Usta", "#a78bfa", "#2d1f5e", 2),
    (7, "Efsane", "#fbbf24", "#4a3510", 3),
    (9, "Şampiyon", "#22d3ee", "#0b3a4a", 4),
]

# (ad, açılış seviyesi, kostüm adları)
KARAKTERLER = {
    "kasif": ("Kaşif", 1, ("Kaşif", "Kilim Yelekli Kaşif", "Altın Pusulalı Kaşif")),
    "kasif_kiz": ("Kaşif Kız", 1, ("Kaşif Kız", "Kilim Yelekli Kaşif Kız", "Altın Pusulalı Kaşif Kız")),
    "keloglan": ("Keloğlan", 1, ("Keloğlan", "Kalpaklı Keloğlan", "Altın Keloğlan")),
    "robi": ("Robi", 1, ("Robi", "Lale Desenli Robi", "Altın Robi")),
    "bilge": ("Bilge Baykuş", 2, ("Bilge Baykuş", "Fesli Bilge Baykuş", "Altın Kanatlı Baykuş")),
    "van_kedisi": ("Van Kedisi", 2, ("Van Kedisi", "Nazar Boncuklu Van Kedisi", "Altın Tasmalı Van Kedisi")),
    "farabi": ("Farabi", 3, ("Farabi", "Udlu Farabi", "Altın İşlemeli Farabi")),
    "nasreddin": ("Nasreddin Hoca", 3, ("Nasreddin Hoca", "Kitaplı Nasreddin Hoca", "Altın İşlemeli Nasreddin Hoca")),
    "tilki": ("Akıllı Tilki", 4, ("Akıllı Tilki", "Atkılı Tilki", "Altın Tilki")),
    "hurrem": ("Hürrem Sultan", 5, ("Hürrem Sultan", "Taçlı Hürrem Sultan", "Altın İşlemeli Hürrem Sultan")),
    "dede_korkut": ("Dede Korkut", 5, ("Dede Korkut", "Kopuzlu Dede Korkut", "Altın Kopuzlu Dede Korkut")),
    "astro": ("Astro", 6, ("Astro", "Bayraklı Astro", "Altın Kasklı Astro")),
    "piri_reis": ("Piri Reis", 6, ("Piri Reis", "Haritalı Piri Reis", "Altın Pusulalı Piri Reis")),
    "suleyman": ("Kanuni Sultan Süleyman", 7, ("Kanuni Sultan Süleyman", "Kaftanlı Kanuni", "Altın Kaftanlı Kanuni")),
    "hezarfen": ("Hezarfen Ahmed Çelebi", 7, ("Hezarfen Ahmed Çelebi", "Kanatlı Hezarfen", "Altın Kanatlı Hezarfen")),
    "mimar_sinan": ("Mimar Sinan", 8, ("Mimar Sinan", "Pergelli Mimar Sinan", "Altın İşlemeli Mimar Sinan")),
    "ejder": ("Ejder", 8, ("Ejder", "Çini Pullu Ejder", "Altın Ejder")),
}
BOLUMLER = ("karakter", "kostum")


def kostumler(karakter: str) -> dict:
    _, seviye, adlar = KARAKTERLER[karakter]
    return {str(i): (ad, min(seviye + 2 * (i - 1), 10)) for i, ad in enumerate(adlar, 1)}


def kademe(seviye: int) -> tuple:
    k = KADEMELER[0]
    for x in KADEMELER:
        if seviye >= x[0]:
            k = x
    return k


def _yildizlar(n: int, renk: str) -> str:
    konum = [(14, 22), (86, 22), (10, 52), (90, 52)]
    return "".join(
        f'<path d="M{x} {y - 5} l1.8 3.6 4 .6 -2.9 2.8 .7 4 -3.6 -1.9 -3.6 1.9 .7 -4 -2.9 -2.8 4 -.6Z" fill="{renk}"/>'
        for x, y in konum[:n]
    )


def cfg_temiz(cfg: dict | None) -> dict:
    if not cfg:
        return dict(VARSAYILAN)
    karakter = cfg.get("karakter", "kasif")
    kostum = cfg.get("kostum", "1")
    if isinstance(karakter, str) and "-" in karakter and "kostum" not in cfg:
        karakter, kostum = karakter.rsplit("-", 1)
    if karakter not in KARAKTERLER or kostum not in ("1", "2", "3"):
        return dict(VARSAYILAN)
    return {"karakter": karakter, "kostum": kostum}


def svg(cfg: dict | None, seviye: int, boyut: int = 96, etiket: str = "") -> Markup:
    c = cfg_temiz(cfg)
    _, _, cerceve, zemin, yildiz = kademe(max(1, int(seviye)))
    n = next(_sayac)
    ad = kostumler(c["karakter"])[c["kostum"]][0]
    label = escape(etiket or ad + " avatarı, seviye " + str(int(seviye)))
    return Markup(
        f'<svg class="avatar" width="{int(boyut)}" height="{int(boyut)}" viewBox="0 0 100 100" role="img" '
        f'aria-label="{label}">'
        f'<defs><clipPath id="av{n}"><circle cx="50" cy="50" r="47"/></clipPath></defs>'
        f'<circle cx="50" cy="50" r="47" fill="{zemin}"/>'
        f'<g clip-path="url(#av{n})"><image href="/static/avatar/{c["karakter"]}-{c["kostum"]}.webp?v=1" '
        f'x="3" y="3" width="94" height="94" preserveAspectRatio="xMidYMid slice"/></g>'
        f'<circle cx="50" cy="50" r="47" fill="none" stroke="{cerceve}" stroke-width="{3 + (yildiz > 0)}"/>'
        f'{_yildizlar(yildiz, cerceve)}</svg>'
    )


def acik_mi(bolum: str, kod: str, seviye: int, karakter: str = "kasif") -> bool:
    if bolum == "karakter":
        return kod in KARAKTERLER and KARAKTERLER[kod][1] <= seviye
    if bolum == "kostum" and karakter in KARAKTERLER:
        return kod in kostumler(karakter) and kostumler(karakter)[kod][1] <= seviye
    return False


def getir(conn: sqlite3.Connection, kullanici_id: int) -> dict:
    r = conn.execute("SELECT karakter, sapka, yuz, sirt FROM avatar WHERE kullanici_id = ?", (kullanici_id,)).fetchone()
    return cfg_temiz(dict(r) if r else None)


def kaydet(conn: sqlite3.Connection, kullanici_id: int, cfg: dict, seviye: int) -> dict:
    c = cfg_temiz(cfg)
    karakter, kostum = c["karakter"], c["kostum"]
    for ad, sev in (KARAKTERLER[karakter][:2], kostumler(karakter)[kostum]):
        if sev > seviye:
            raise ValueError(f"{ad} henüz açılmadı (Seviye {sev}).")
    db_kod = karakter if kostum == "1" else f"{karakter}-{kostum}"
    conn.execute(
        "INSERT INTO avatar (kullanici_id, karakter, sapka, yuz, sirt, guncelleme) VALUES (?, ?, ?, ?, ?, ?)"
        " ON CONFLICT (kullanici_id) DO UPDATE SET karakter = excluded.karakter, sapka = excluded.sapka,"
        " yuz = excluded.yuz, sirt = excluded.sirt, guncelleme = excluded.guncelleme",
        (kullanici_id, db_kod, "yok", "yok", "yok", zaman.simdi_str()),
    )
    conn.commit()
    return c


def acilanlar(eski: int, yeni: int) -> list[str]:
    sonuc = []
    for kod, (ad, sev, _) in KARAKTERLER.items():
        if eski < sev <= yeni:
            sonuc.append(f"{ad} (karakter)")
        for n, (kostum_ad, kostum_sev) in kostumler(kod).items():
            if n != "1" and eski < kostum_sev <= yeni:
                sonuc.append(f"{kostum_ad} (kostüm)")
    return sonuc


def siradaki_acilis(seviye: int) -> tuple[int, list[str]] | None:
    for sev in range(seviye + 1, 11):
        adlar = acilanlar(sev - 1, sev)
        if adlar:
            return sev, adlar
    return None
