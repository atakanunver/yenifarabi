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
import glob
import os
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
import zipfile
from contextlib import closing

PG_TABLOLARI = (
    "ogrenci", "veli", "veli_ogrenci", "personel", "sinif", "sinif_atama",
    "ders_programi", "zil", "ogretim_yili", "derslik",
)
YOKLAMA_TABLOLARI = ("yoklama_onbellek", "kulup_yoklama")
SMS_TABLOLARI = ("kisiler", "siniflar", "gonderimler")  # smssistemi.db (rehber + gönderim kayıtları)
TC_TABLOLARI = ("tc_kimlik",)
TURETILMIS_TABLOLAR = ("ogrenci_genis", "ogretmen")  # ogrenci_genis: ogrenci + sinif + tc_kimlik + SMS kisiler; ogretmen: personel + ders programı
DOSYA_TABLOLARI = ("ogretmen_programi", "kazanim", "simdi")  # config/ogretmenler.json ve data/kazanimlar.json'dan türetilir
IZINLI_TABLOLAR = frozenset(PG_TABLOLARI + YOKLAMA_TABLOLARI + SMS_TABLOLARI + TC_TABLOLARI + TURETILMIS_TABLOLAR + DOSYA_TABLOLARI)
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


def sms_tablolari(yol) -> dict[str, tuple[list[str], list[tuple]]]:
    """SMS rehberi ve gönderim kayıtları (smssistemi.db, salt-okunur). Hata → SqlHatasi."""
    try:
        with closing(sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=3)) as c:
            sonuc = {}
            for t in SMS_TABLOLARI:
                cur = c.execute(f'SELECT * FROM "{t}"')
                sonuc[t] = ([d[0] for d in cur.description], cur.fetchall())
            return sonuc
    except sqlite3.Error as e:
        raise SqlHatasi("SMS veri tabanına ulaşılamadı.") from type(e)


_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_TC_ONBELLEK: dict = {}


def _xlsx_satirlari(yol) -> list[dict[str, str]]:
    """İlk çalışma sayfası → satırlar ({'A': 'değer', ...}); yalnızca stdlib (openpyxl venv'de yok)."""
    with zipfile.ZipFile(yol) as z:
        ortak = []
        if "xl/sharedStrings.xml" in z.namelist():
            ortak = ["".join(t.text or "" for t in si.iter(f"{_NS}t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{_NS}si")]
        satirlar = []
        for satir in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter(f"{_NS}row"):
            hucreler = {}
            for h in satir.iter(f"{_NS}c"):
                v = h.find(f"{_NS}v")
                if h.get("t") == "inlineStr":
                    deger = "".join(t.text or "" for t in h.iter(f"{_NS}t"))
                elif v is None or v.text is None:
                    continue
                else:
                    deger = ortak[int(v.text)] if h.get("t") == "s" else v.text
                hucreler[re.sub(r"\d+", "", h.get("r", ""))] = deger.strip()
            satirlar.append(hucreler)
        return satirlar


def tc_tablosu(dizin) -> dict[str, tuple[list[str], list[tuple]]]:
    """mudur/SINIF/tcler/<sınıf>.xlsx (OKUL NO, ÖĞRENCİ AD-SOYAD, ANNE/BABA AD-SOYAD, ÖĞRENCİ/ANNE/BABA TC)
    → tc_kimlik tablosu; sınıf dosya adından. Dosya değişmedikçe (mtime) önbellekten; bozuk dosya atlanır."""
    kolonlar = ["sinif", "okul_no", "ogrenci_ad_soyad", "ogrenci_tc", "anne_ad_soyad", "anne_tc", "baba_ad_soyad", "baba_tc"]
    basliklar = ("okul no", "ogrenci ad-soyad", "ogrenci tc", "anne ad-soyad", "anne tc", "baba ad-soyad", "baba tc")
    satirlar = []
    for yol in sorted(glob.glob(f"{dizin}/*.xlsx")):
        try:
            mtime = os.stat(yol).st_mtime
            if _TC_ONBELLEK.get(yol, (None,))[0] != mtime:
                _TC_ONBELLEK[yol] = (mtime, _xlsx_satirlari(yol))
        except (OSError, KeyError, ET.ParseError, zipfile.BadZipFile):
            continue
        tum = _TC_ONBELLEK[yol][1]
        bas = next((i for i, h in enumerate(tum) if "okul no" in {_sade(v) for v in h.values()}), None)
        if bas is None:
            continue
        harf = {_sade(v): k for k, v in tum[bas].items()}
        no_k, ad_k, tc_k, aa_k, at_k, ba_k, bt_k = (harf.get(b) for b in basliklar)
        sinif = os.path.basename(yol)[:-5]
        for h in tum[bas + 1:]:
            if ad_k and h.get(ad_k):
                satirlar.append((sinif, h.get(no_k), h[ad_k], h.get(tc_k), h.get(aa_k), h.get(at_k), h.get(ba_k), h.get(bt_k)))
    return {"tc_kimlik": (kolonlar, satirlar)}


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


def _no(v) -> int | None:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def ogrenci_genis(tablolar: dict) -> dict:
    """Öğrenci başına tek satır (okul_no anahtarıyla): okul_ana ogrenci+sinif, tc_kimlik (öğrenci/anne/baba TC),
    SMS kisiler (doğum tarihi/telefon eksikse tamamlar; anne/baba telefonu veli_ogrenci'de yoksa veli_rol'den)."""
    if "ogrenci" not in tablolar:
        return tablolar

    def satirlar(ad):
        k, r = tablolar.get(ad, ([], []))
        return [dict(zip(k, x, strict=True)) for x in r]

    sinif_ad = {s["id"]: s["ad"] for s in satirlar("sinif")}
    sinif_of = {_no(a["okul_no"]): sinif_ad.get(a["sinif_id"]) for a in satirlar("sinif_atama")}
    tc = {_no(t["okul_no"]): t for t in satirlar("tc_kimlik")}
    kisiler = satirlar("kisiler")
    sms = {_no(k["okul_no"]): k for k in kisiler if k.get("tur") == "ogrenci" and _no(k.get("okul_no")) is not None}
    sms_no = {k["id"]: _no(k["okul_no"]) for k in kisiler if k.get("tur") == "ogrenci"}
    veli = {v["id"]: v for v in satirlar("veli")}
    tel: dict[tuple, str] = {}
    ad: dict[tuple, str] = {}
    for vo in satirlar("veli_ogrenci"):
        rol, v = _sade(vo.get("yakinlik") or ""), veli.get(vo["veli_id"])
        if v and rol in ("anne", "baba"):
            tel.setdefault((_no(vo["okul_no"]), rol), v["telefon"])
            ad.setdefault((_no(vo["okul_no"]), rol), v["ad_soyad"])
    for k in kisiler:
        rol = _sade(k.get("veli_rol") or "")
        if k.get("tur") == "veli" and rol in ("anne", "baba") and sms_no.get(k.get("ogrenci_kisi_id")) is not None:
            tel.setdefault((sms_no[k["ogrenci_kisi_id"]], rol), k["telefon"])
            ad.setdefault((sms_no[k["ogrenci_kisi_id"]], rol), k["ad_soyad"])
    kolonlar = ["okul_no", "ad_soyad", "sinif", "cinsiyet", "aktif", "dogum_tarihi", "telefon", "ogrenci_tc",
                "anne_ad_soyad", "anne_tc", "anne_telefon", "baba_ad_soyad", "baba_tc", "baba_telefon"]
    satir = []
    for o in satirlar("ogrenci"):
        no = _no(o["okul_no"])
        t, s = tc.get(no, {}), sms.get(no, {})
        satir.append((o["okul_no"], o["ad_soyad"], sinif_of.get(no) or t.get("sinif"), o.get("cinsiyet"), o.get("aktif"),
                      o.get("dogum_tarihi") or s.get("dogum_tarihi"), o.get("telefon") or s.get("telefon"),
                      t.get("ogrenci_tc"), t.get("anne_ad_soyad") or ad.get((no, "anne")), t.get("anne_tc"), tel.get((no, "anne")),
                      t.get("baba_ad_soyad") or ad.get((no, "baba")), t.get("baba_tc"), tel.get((no, "baba"))))
    return {**tablolar, "ogrenci_genis": (kolonlar, satir)}


def ogretmen_tablosu(tablolar: dict) -> dict:
    """Ders veren herkes (görevi 'ogretmen' olanlar + programda dersi olan yönetici/diğer personel) tek tabloda.
    personel_esle'den SONRA çağrılmalı (ogretmen_programi.personel_id gerekir)."""
    if "personel" not in tablolar or "ogretmen_programi" not in tablolar:
        return tablolar
    pk, pr = tablolar["personel"]
    ok, orr = tablolar["ogretmen_programi"]
    saat: dict = {}
    for r in orr:
        pid = r[ok.index("personel_id")]
        if pid is not None:
            saat[pid] = saat.get(pid, 0) + 1
    satir = []
    for r in pr:
        p = dict(zip(pk, r, strict=True))
        if p.get("aktif") and (p.get("gorev") == "ogretmen" or p["id"] in saat):
            satir.append((p["id"], p["ad_soyad"], p["gorev"], p.get("brans"), p["telefon"], p["dogum_tarihi"], p.get("tc_kimlik"),
                          p.get("eposta"), saat.get(p["id"], 0)))
    return {**tablolar, "ogretmen": (["personel_id", "ad_soyad", "gorev", "brans", "telefon", "dogum_tarihi", "tc_kimlik", "eposta", "haftalik_ders_saati"], satir)}


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
