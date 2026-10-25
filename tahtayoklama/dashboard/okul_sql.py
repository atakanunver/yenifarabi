"""okul_sql.py — Atos için tek, salt-okunur SQL ucu (/api/okul/sql).

Kaynaklar her çağrıda bellek içi bir SQLite'a kopyalanır: okul_ana (PostgreSQL, salt-okunur
`atos_ro` rolü) tabloları + yoklama_pano.db yoklama tabloları. Sorgu bu kopyada çalışır, böylece
model tek SQL lehçesiyle her şeyi birleştirebilir ve canlı veri tabanına yazma yolu yoktur.
Zorlama: tek ifade (sqlite3), `set_authorizer` (yalnız SELECT + izinli tablolar), satır sınırı,
zaman aşımı. Parola/oturum/anahtar tabloları kopyaya hiç alınmaz.
"""

from __future__ import annotations

import datetime
import decimal
import re
import sqlite3
import time
from contextlib import closing

PG_TABLOLARI = (
    "ogrenci", "veli", "veli_ogrenci", "personel", "sinif", "sinif_atama",
    "ders_programi", "zil", "ogretim_yili", "derslik",
)
YOKLAMA_TABLOLARI = ("yoklama_onbellek", "kulup_yoklama")
DOSYA_TABLOLARI = ("ogretmen_programi", "kazanim", "simdi")  # config/ogretmenler.json ve data/kazanimlar.json'dan türetilir
IZINLI_TABLOLAR = frozenset(PG_TABLOLARI + YOKLAMA_TABLOLARI + DOSYA_TABLOLARI)
TABLO_FONKSIYONLARI = frozenset({"json_each", "json_tree"})
YASAK_FONKSIYONLAR = frozenset({"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"})
AZAMI_SATIR = 200
AZAMI_HUCRE = 300  # karakter
ZAMAN_ASIMI_SN = 3.0


class SqlHatasi(Exception):
    """Modele aynen gösterilebilecek (yol/anahtar içermeyen) hata metni."""


def _deger(v):
    if isinstance(v, (datetime.date, datetime.datetime, datetime.time)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return "<ikili>"
    if isinstance(v, (dict, list)):
        import json
        return json.dumps(v, ensure_ascii=False)
    return v


def pg_tablolari(dsn: str) -> dict[str, tuple[list[str], list[tuple]]]:
    """okul_ana tabloları: {ad: (kolonlar, satırlar)}. Hata → SqlHatasi (ayrıntı sızdırmaz)."""
    try:
        import psycopg

        sonuc = {}
        with psycopg.connect(dsn, connect_timeout=3) as c:
            for t in PG_TABLOLARI:
                cur = c.execute(f'SELECT * FROM "{t}"')
                sonuc[t] = ([d.name for d in cur.description], [tuple(_deger(v) for v in r) for r in cur.fetchall()])
        return sonuc
    except Exception as e:  # noqa: BLE001 — DSN/parola hata metnine sızmasın
        raise SqlHatasi("Okul veri tabanına ulaşılamadı.") from type(e)


def yoklama_tablolari(yol) -> dict[str, tuple[list[str], list[tuple]]]:
    try:
        with closing(sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=3)) as c:
            sonuc = {}
            for t in YOKLAMA_TABLOLARI:
                cur = c.execute(f'SELECT * FROM "{t}"')
                sonuc[t] = ([d[0] for d in cur.description], cur.fetchall())
            return sonuc
    except sqlite3.Error as e:
        raise SqlHatasi("Yoklama veri tabanına ulaşılamadı.") from type(e)


_SADE = str.maketrans("çğıöşü", "cgiosu")


def _sade(metin) -> str:
    """Türkçe harf/büyük-küçük duyarsız karşılaştırma anahtarı: 'AYŞE' ve 'ayse' aynı olur."""
    return str(metin).replace("İ", "i").replace("I", "ı").lower().translate(_SADE)


def _ara(kolon, aranan) -> int:
    return int(kolon is not None and _sade(aranan) in _sade(kolon))


_GUN_NO = {"pazartesi": 1, "sali": 2, "carsamba": 3, "persembe": 4, "cuma": 5}


def ogretmen_programi_tablosu(program: dict, saatler: dict[int, dict]) -> dict:
    """ogretmenler.json::program ({sinif: {gun: {ders_no: [ad]}}}) → ogretmen_programi tablosu.
    okul_ana.ders_programi.ogretmen_id boş olduğundan öğretmen↔ders bağı yalnızca buradadır."""
    satirlar = []
    for sinif, gunler in (program or {}).items():
        for gun, dersler in (gunler or {}).items():
            for no, adlar in (dersler or {}).items():
                saat = saatler.get(int(no)) or {}
                for ad in adlar:
                    satirlar.append((ad, sinif, _GUN_NO.get(gun), int(no), saat.get("baslangic"), saat.get("bitis")))
    return {"ogretmen_programi": (["ogretmen", "sinif", "gun", "ders_no", "baslangic", "bitis"], satirlar)}


def personel_esle(tablolar: dict) -> dict:
    """ogretmen_programi'nı zenginleştirir (öğretmen ↔ sınıf ↔ saat ↔ ders tek tabloda olsun diye):
    - personel_id: ad sırası ("SOYAD AD" / "AD SOYAD") ve harf farkından bağımsız, kelime kümesi eşitliğiyle,
      görev (ogretmen/yonetici/diger) gözetmeden; bulunamayan/çoklu eşleşmede NULL.
    - ders: ders_programi'ndan (sinif adı, gun, ders_no) ile; yoksa NULL."""
    if "ogretmen_programi" not in tablolar:
        return tablolar
    esle: dict[tuple, list] = {}
    if "personel" in tablolar:
        pk, pr = tablolar["personel"]
        i_id, i_ad = pk.index("id"), pk.index("ad_soyad")
        for r in pr:
            esle.setdefault(tuple(sorted(_sade(r[i_ad]).split())), []).append(r[i_id])
    dersler: dict[tuple, str] = {}
    if "ders_programi" in tablolar and "sinif" in tablolar:
        sk, sr = tablolar["sinif"]
        ad_of = {r[sk.index("id")]: r[sk.index("ad")] for r in sr}
        dk, dr = tablolar["ders_programi"]
        for r in dr:
            dersler[(ad_of.get(r[dk.index("sinif_id")]), r[dk.index("gun")], r[dk.index("ders_no")])] = r[dk.index("ders")]
    kol, satirlar = tablolar["ogretmen_programi"]
    i = {k: n for n, k in enumerate(kol)}
    yeni = []
    for r in satirlar:
        ids = esle.get(tuple(sorted(_sade(r[i["ogretmen"]]).split())), [])
        yeni.append((r[i["ogretmen"]], ids[0] if len(ids) == 1 else None, r[i["sinif"]],
                     dersler.get((r[i["sinif"]], r[i["gun"]], r[i["ders_no"]])), r[i["gun"]], r[i["ders_no"]],
                     r[i["baslangic"]], r[i["bitis"]]))
    return {**tablolar, "ogretmen_programi": (["ogretmen", "personel_id", "sinif", "ders", "gun", "ders_no", "baslangic", "bitis"], yeni)}


def simdi_tablosu(bilgi: dict, isogun: int) -> dict:
    """Şu anki Türkiye zamanı ve ders durumu (tek satır): "öğretmen şu an hangi sınıfta?" gibi sorular için.
    bilgi = okul_bilgisi.simdi_bilgisi() çıktısı; isogun 1=Pazartesi … 7=Pazar."""
    ek = {"ders": f"{bilgi.get('ders_no')}. ders saati", "teneffus": "teneffüs", "okul_disi": "ders saati dışı"}.get(bilgi.get("durum"), "")
    satir = (bilgi.get("tarih"), bilgi.get("saat"), isogun, bilgi.get("gun"), bilgi.get("durum"), bilgi.get("ders_no"), ek)
    return {"simdi": (["tarih", "saat", "gun", "gun_adi", "durum", "ders_no", "aciklama"], [satir])}


def kazanim_tablosu(veri: dict) -> dict:
    """kazanimlar.json ({kazanimlar: {seviye: {ders: {hafta: metin}}}, haftalar: {hafta: başlangıç}}) → kazanim tablosu."""
    haftalar = (veri or {}).get("haftalar") or {}
    satirlar = []
    for seviye, dersler in ((veri or {}).get("kazanimlar") or {}).items():
        for ders, hafta_metin in (dersler or {}).items():
            for hafta, metin in (hafta_metin or {}).items():
                satirlar.append((seviye, ders, int(hafta), haftalar.get(str(hafta)), metin))
    return {"kazanim": (["seviye", "ders", "hafta", "hafta_baslangic", "metin"], satirlar)}


def _like(kalip, metin, kacis=None) -> int | None:
    """SQLite LIKE'ın yerine: Türkçe harf ve büyük/küçük harf duyarsız (model `LIKE '%ayşe%'` yazsa da
    BÜYÜK harfli 'AYŞE' kaydıyla eşleşir). % = herhangi dizi, _ = tek karakter, ESCAPE desteklenir."""
    if kalip is None or metin is None:
        return None
    k, kac, regex, i = _sade(kalip), (_sade(kacis) if kacis else None), "", 0
    while i < len(k):
        c = k[i]
        if kac and c == kac and i + 1 < len(k):
            i += 1
            regex += re.escape(k[i])
        elif c == "%":
            regex += ".*"
        elif c == "_":
            regex += "."
        else:
            regex += re.escape(c)
        i += 1
    return int(re.fullmatch(regex, _sade(metin), re.DOTALL) is not None)


def _kopya(tablolar: dict) -> sqlite3.Connection:
    bellek = sqlite3.connect(":memory:")
    bellek.create_function("ara", 2, _ara, deterministic=True)
    bellek.create_function("like", 2, _like, deterministic=True)
    bellek.create_function("like", 3, _like, deterministic=True)
    for ad, (kolonlar, satirlar) in tablolar.items():
        sutun = ", ".join(f'"{k}"' for k in kolonlar)
        bellek.execute(f'CREATE TABLE "{ad}" ({sutun})')
        bellek.executemany(f'INSERT INTO "{ad}" VALUES ({",".join("?" * len(kolonlar))})', satirlar)
    bellek.commit()
    return bellek


def _yetki(eylem, a1, a2, db_adi, kaynak):
    if eylem in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    if eylem == sqlite3.SQLITE_READ:
        if db_adi not in ("main", "temp"):  # özyinelemeli CTE adı gibi gerçek tablo olmayan okumalar
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_OK if a1 in IZINLI_TABLOLAR or a1 in TABLO_FONKSIYONLARI else sqlite3.SQLITE_DENY
    if eylem == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_DENY if (a2 or "").lower() in YASAK_FONKSIYONLAR else sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def calistir(sorgu: str, tablolar: dict, azami_satir: int = AZAMI_SATIR, sure_sn: float = ZAMAN_ASIMI_SN) -> dict:
    """SELECT çalıştırır → {kolonlar, satirlar, kesildi}. Hata → SqlHatasi."""
    sorgu = (sorgu or "").strip().rstrip(";").strip()
    if not sorgu:
        raise SqlHatasi("Sorgu boş.")
    bellek = _kopya(tablolar)
    try:
        bellek.set_authorizer(_yetki)
        son = time.monotonic() + sure_sn
        bellek.set_progress_handler(lambda: 1 if time.monotonic() > son else 0, 10000)
        try:
            cur = bellek.execute(sorgu)
            satirlar = cur.fetchmany(azami_satir + 1)
        except sqlite3.DatabaseError as e:
            ileti = str(e)
            if "not authorized" in ileti or "prohibited" in ileti:
                raise SqlHatasi("İzin yok: yalnızca şu tablolarda SELECT yapılabilir: "
                                + ", ".join(sorted(IZINLI_TABLOLAR))) from None
            if "interrupted" in ileti:
                raise SqlHatasi(f"Sorgu {sure_sn:g} sn içinde bitmedi; daha dar bir sorgu yazın.") from None
            raise SqlHatasi(f"SQL hatası: {ileti}") from None
        except sqlite3.Warning:
            raise SqlHatasi("Tek bir SELECT ifadesi yazın.") from None
        kolonlar = [d[0] for d in cur.description or []]
    finally:
        bellek.close()
    kesildi = len(satirlar) > azami_satir
    cikti = [[(v[:AZAMI_HUCRE] + "…") if isinstance(v, str) and len(v) > AZAMI_HUCRE else v for v in r]
             for r in satirlar[:azami_satir]]
    return {"kolonlar": kolonlar, "satirlar": cikti, "kesildi": kesildi}
