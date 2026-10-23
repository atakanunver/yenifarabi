#!/usr/bin/env python3
"""okul_ana -> eski depolara YANSIMA (yoklama_pano.db, okul.db, smssistemi.db).

Kaynak tek: okul_ana (PostgreSQL). Eski depolar bu modülle yeniden üretilir; eşleştirme
okul_no ile, mevcut id/FK'ler KORUNUR. Kuru çalıştırma (varsayılan) gerçek işlemi yapıp
ROLLBACK eder, böylece sayılar birebir doğrudur. Çıktıda kişisel veri yok (yalnız sayı).

Silme politikası: yoklama ve okulda kayıt SİLİNMEZ (yoklama: aktif=0; okul: 'yetim' sayılır),
SMS rehberinde (FK yok, günlükler metin kopyası tutar) kayıt silinir.

Kullanım:  python okul_ana_yayin.py            # kuru çalıştırma
           python okul_ana_yayin.py --uygula   # yaz
Ortam:     OKUL_ANA_KOPYA=/dizin  → canlı yerine kopya dosyalara (prova) yaz.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

DB = os.environ.get("OKUL_ANA_DB", "okul_ana_test")
F = Path("/home/ata/farabi")
KOPYA = os.environ.get("OKUL_ANA_KOPYA")
ADLAR = {
    "yoklama": ("yoklama_pano.db", F / "tahtayoklama/dashboard/veri/yoklama_pano.db"),
    "okul": ("okul.db", F / "okul/veri/okul.db"),
    "sms": ("smssistemi.db", F / "smssistemi/veri/smssistemi.db"),
}
MIN_ORAN = 0.5  # DB'deki aktif öğrenci sayısı mevcudun yarısından azsa yayın reddedilir


def yol(hedef: str) -> Path:
    dosya, canli = ADLAR[hedef]
    return Path(KOPYA) / dosya if KOPYA else canli


def tel(t):
    d = re.sub(r"\D", "", t or "")
    return d or None


def _metin(v):
    """psycopg değerini psql çıktısıyla aynı metne çevir (jsonb dict/list → JSON, Python repr değil)."""
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def sorgu(sql):
    """PG okuma: OKUL_ANA_DSN varsa psycopg (üretim/panel), yoksa sudo psql (prova)."""
    dsn = os.environ.get("OKUL_ANA_DSN")
    if dsn:
        import psycopg

        with psycopg.connect(dsn) as c:
            return [[_metin(v) for v in r] for r in c.execute(sql).fetchall()]
    a = [
        "sudo",
        "-n",
        "-u",
        "postgres",
        "psql",
        "-X",
        "-q",
        "-v",
        "ON_ERROR_STOP=1",
        "-d",
        DB,
        "-At",
        "-F",
        "\t",
        "-P",
        "null=\\N",
        "-c",
        sql,
    ]
    r = subprocess.run(a, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[:400])
    return [
        [None if c == "\\N" else c for c in l.split("\t")]
        for l in r.stdout.splitlines()
        if l
    ]


@dataclass
class Istenen:
    siniflar: list = field(default_factory=list)  # [ad]
    ogrenciler: list = field(
        default_factory=list
    )  # [(no, ad, cins, tel, dogum, sinif)]
    veliler: list = field(default_factory=list)  # [(no, ad, tel, rol)]
    personel: list = field(default_factory=list)  # [(ad, tel, dogum)]


def istenen_oku() -> Istenen:
    yil = sorgu("select id from okul_ana.ogretim_yili where aktif")[0][0]
    d = Istenen()
    d.siniflar = [
        r[0]
        for r in sorgu(
            f"select ad from okul_ana.sinif where yil_id={yil} order by seviye, ad"
        )
    ]
    d.ogrenciler = [
        (int(r[0]), r[1], r[2], tel(r[3]), r[4], r[5])
        for r in sorgu(
            f"select o.okul_no,o.ad_soyad,o.cinsiyet,o.telefon,o.dogum_tarihi,s.ad "
            f"from okul_ana.ogrenci o join okul_ana.sinif_atama a on a.okul_no=o.okul_no and a.yil_id={yil} "
            f"join okul_ana.sinif s on s.id=a.sinif_id where o.aktif order by o.okul_no"
        )
    ]
    d.veliler = [
        (int(r[0]), r[1], tel(r[2]), r[3])
        for r in sorgu(
            "select vo.okul_no,v.ad_soyad,v.telefon,vo.yakinlik from okul_ana.veli_ogrenci vo "
            "join okul_ana.veli v on v.id=vo.veli_id join okul_ana.ogrenci o on o.okul_no=vo.okul_no "
            "where o.aktif order by vo.okul_no, v.id"
        )
    ]
    d.personel = [
        (r[0], tel(r[1]), r[2])
        for r in sorgu(
            "select ad_soyad,telefon,dogum_tarihi from okul_ana.personel where aktif order by id"
        )
    ]
    return d


class Say:
    def __init__(self):
        self.s = {"ekle": 0, "guncelle": 0, "pasif": 0, "sil": 0, "yetim": 0}

    def __getitem__(self, k):
        return self.s[k]

    def art(self, k, n=1):
        self.s[k] += n

    def __str__(self):
        return " ".join(f"{k}={v}" for k, v in self.s.items())


# --- yoklama_pano.db ---------------------------------------------------------


def yayin_yoklama(c, d: Istenen, say: Say):
    sid = {ad: (i, a) for i, ad, a in c.execute("select id,ad,aktif from siniflar")}
    for ad in d.siniflar:
        if ad not in sid:
            c.execute("insert into siniflar(ad,aktif) values(?,1)", (ad,))
            sid[ad] = (
                c.execute("select id from siniflar where ad=?", (ad,)).fetchone()[0],
                1,
            )
            say.art("ekle")
        elif sid[ad][1] != 1:
            c.execute(
                "update siniflar set aktif=1,guncelleme_zamani=datetime('now') where id=?",
                (sid[ad][0],),
            )
            say.art("guncelle")
    for ad, (i, a) in sid.items():
        if ad not in d.siniflar and a == 1:
            c.execute(
                "update siniflar set aktif=0,guncelleme_zamani=datetime('now') where id=?",
                (i,),
            )
            say.art("pasif")
    mev = {
        no: (i, s, ad, cins, a)
        for i, no, s, ad, cins, a in c.execute(
            "select id,no,sinif_id,ad_soyad,cinsiyet,aktif from ogrenciler"
        )
    }
    gor = set()
    for no, ad, cins, _t, _dt, sinif in d.ogrenciler:
        gor.add(no)
        if no in mev:
            i, s, mad, mcins, a = mev[no]
            if (s, mad, mcins, a) != (sid[sinif][0], ad, cins, 1):
                c.execute(
                    "update ogrenciler set sinif_id=?,ad_soyad=?,cinsiyet=?,aktif=1 where id=?",
                    (sid[sinif][0], ad, cins, i),
                )
                say.art("guncelle")
        else:
            c.execute(
                "insert into ogrenciler(sinif_id,no,ad_soyad,cinsiyet,aktif) values(?,?,?,?,1)",
                (sid[sinif][0], no, ad, cins),
            )
            say.art("ekle")
    for no, (i, *_r, a) in mev.items():
        if no not in gor and a == 1:
            c.execute("update ogrenciler set aktif=0 where id=?", (i,))
            say.art("pasif")


# --- okul.db -----------------------------------------------------------------


def yayin_okul(c, d: Istenen, say: Say):
    mev = {
        no: (i, ad, s)
        for i, no, ad, s in c.execute("select id,okul_no,ad_soyad,sinif from ogrenci")
    }
    gor = set()
    for no, ad, _c, _t, _dt, sinif in d.ogrenciler:
        gor.add(no)
        if no in mev:
            i, mad, ms = mev[no]
            if (mad, ms) != (ad, sinif):
                c.execute(
                    "update ogrenci set ad_soyad=?,sinif=? where id=?", (ad, sinif, i)
                )
                say.art("guncelle")
        else:
            c.execute(
                "insert into ogrenci(okul_no,ad_soyad,sinif) values(?,?,?)",
                (no, ad, sinif),
            )
            say.art("ekle")
    say.art("yetim", sum(1 for no in mev if no not in gor))


# --- smssistemi.db -----------------------------------------------------------


def yayin_sms(c, d: Istenen, say: Say):
    sid = {ad: i for i, ad in c.execute("select id,ad from siniflar")}
    for ad in list(d.siniflar) + ["Personel"]:
        if ad not in sid:
            c.execute("insert into siniflar(ad) values(?)", (ad,))
            sid[ad] = c.execute("select id from siniflar where ad=?", (ad,)).fetchone()[
                0
            ]
            say.art("ekle")
    # öğrenciler
    mev = {
        no: (i, ad, tel(t), s, dt)
        for i, no, ad, t, s, dt in c.execute(
            "select id,okul_no,ad_soyad,telefon,sinif_id,dogum_tarihi from kisiler where tur='ogrenci'"
        )
    }
    kid = {}
    for no, ad, _c, t, dt, sinif in d.ogrenciler:
        s = sid[sinif]
        if no in mev:
            i, mad, mt, ms, mdt = mev[no]
            kid[no] = i
            if (mad, mt, ms, mdt) != (ad, t, s, dt):
                c.execute(
                    "update kisiler set ad_soyad=?,telefon=?,sinif_id=?,dogum_tarihi=? where id=?",
                    (ad, t, s, dt, i),
                )
                say.art("guncelle")
        else:
            cur = c.execute(
                "insert into kisiler(ad_soyad,telefon,sinif_id,tur,dogum_tarihi,okul_no) values(?,?,?,'ogrenci',?,?)",
                (ad, t, s, dt, no),
            )
            kid[no] = cur.lastrowid
            say.art("ekle")
    gor = {o[0] for o in d.ogrenciler}
    for no, (i, *_r) in mev.items():
        if no not in gor:
            n = c.execute(
                "delete from kisiler where ogrenci_kisi_id=? and tur='veli'", (i,)
            ).rowcount
            c.execute("delete from kisiler where id=?", (i,))
            say.art("sil", 1 + n)
    # veliler (öğrenci başına eşleştirme: önce telefon, sonra ad)
    sinif_of = {o[0]: sid[o[5]] for o in d.ogrenciler}
    istenen = {}
    for no, ad, t, rol in d.veliler:
        istenen.setdefault(no, []).append((ad, t, rol))
    for no, i in kid.items():
        satirlar = [
            [r[0], r[1], tel(r[2]), r[3], r[4]]
            for r in c.execute(
                "select id,ad_soyad,telefon,veli_rol,sinif_id from kisiler where tur='veli' and ogrenci_kisi_id=?",
                (i,),
            )
        ]
        kullan = set()
        for ad, t, rol in istenen.get(no, []):
            e = next(
                (r for r in satirlar if r[0] not in kullan and t and r[2] == t), None
            ) or next((r for r in satirlar if r[0] not in kullan and r[1] == ad), None)
            if e:
                kullan.add(e[0])
                if (e[1], e[2], e[3], e[4]) != (ad, t, rol, sinif_of[no]):
                    c.execute(
                        "update kisiler set ad_soyad=?,telefon=?,veli_rol=?,sinif_id=? where id=?",
                        (ad, t, rol, sinif_of[no], e[0]),
                    )
                    say.art("guncelle")
            else:
                c.execute(
                    "insert into kisiler(ad_soyad,telefon,sinif_id,tur,ogrenci_kisi_id,veli_rol) "
                    "values(?,?,?,'veli',?,?)",
                    (ad, t, sinif_of[no], i, rol),
                )
                say.art("ekle")
        for r in satirlar:
            if r[0] not in kullan:
                c.execute("delete from kisiler where id=?", (r[0],))
                say.art("sil")
    # personel (önce ad, sonra telefon)
    ps = sid["Personel"]
    satirlar = [
        [r[0], r[1], tel(r[2]), r[3], r[4]]
        for r in c.execute(
            "select id,ad_soyad,telefon,dogum_tarihi,sinif_id from kisiler where tur='personel'"
        )
    ]
    kullan = set()
    for ad, t, dt in d.personel:
        e = next(
            (r for r in satirlar if r[0] not in kullan and r[1] == ad), None
        ) or next((r for r in satirlar if r[0] not in kullan and t and r[2] == t), None)
        if e:
            kullan.add(e[0])
            if (e[1], e[2], e[3], e[4]) != (ad, t, dt, ps):
                c.execute(
                    "update kisiler set ad_soyad=?,telefon=?,dogum_tarihi=?,sinif_id=? where id=?",
                    (ad, t, dt, ps, e[0]),
                )
                say.art("guncelle")
        else:
            c.execute(
                "insert into kisiler(ad_soyad,telefon,sinif_id,tur,dogum_tarihi) values(?,?,?,'personel',?)",
                (ad, t, ps, dt),
            )
            say.art("ekle")
    for r in satirlar:
        if r[0] not in kullan:
            c.execute("delete from kisiler where id=?", (r[0],))
            say.art("sil")


HEDEFLER = {"yoklama": yayin_yoklama, "okul": yayin_okul, "sms": yayin_sms}


def yayin_json(uygula: bool) -> Say:
    """zil.json + ders_programi.json: yalnız içerik değiştiyse yaz (atomik; eskisi .onceki)."""
    import okul_ana_goruntu as G

    say = Say()
    klasor = G.veri_dizini()
    for ad, uret in G.DOSYALAR.items():
        yeni = uret().encode("utf-8")
        hedef = klasor / ad
        mevcut = hedef.read_bytes() if hedef.exists() else None
        if yeni == mevcut:
            continue
        say.art("guncelle" if mevcut is not None else "ekle")
        if uygula:
            if mevcut is not None:
                (klasor / (ad + ".onceki")).write_bytes(mevcut)
            gecici = klasor / (ad + ".yeni")
            gecici.write_bytes(yeni)
            os.replace(gecici, hedef)
    return say


_KILIT = threading.Lock()


def yayinla(uygula: bool = False, hedefler=None) -> dict:
    with _KILIT:  # aynı süreçte eşzamanlı yayınlar sıraya girer
        return _yayinla(uygula, hedefler)


def _yayinla(uygula, hedefler):
    d = istenen_oku()
    if not d.ogrenciler or not d.siniflar:
        raise RuntimeError("okul_ana'da aktif öğrenci/sınıf yok — yayın reddedildi")
    sonuc = {}
    for ad in hedefler or [*HEDEFLER, "json"]:
        if ad == "json":
            sonuc[ad] = yayin_json(uygula)
            continue
        c = sqlite3.connect(yol(ad), timeout=15, isolation_level=None)
        c.execute("PRAGMA busy_timeout=15000")
        say = Say()
        try:
            c.execute("BEGIN IMMEDIATE")
            tablo = {
                "yoklama": "select count(*) from ogrenciler where aktif=1",
                "okul": "select count(*) from ogrenci",
                "sms": "select count(*) from kisiler where tur='ogrenci'",
            }[ad]
            mevcut = c.execute(tablo).fetchone()[0]
            if mevcut and len(d.ogrenciler) < MIN_ORAN * mevcut:
                raise RuntimeError(
                    f"{ad}: DB'de {len(d.ogrenciler)} öğrenci, depoda {mevcut} — olağandışı düşüş, reddedildi"
                )
            HEDEFLER[ad](c, d, say)
            c.execute("COMMIT" if uygula else "ROLLBACK")
        except BaseException:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            c.close()
        sonuc[ad] = say
    return sonuc


if __name__ == "__main__":
    uygula = "--uygula" in sys.argv
    kaynak = f"KOPYA={KOPYA}" if KOPYA else "CANLI"
    print(f"yayin [{kaynak}] {'UYGULA' if uygula else 'KURU'}")
    for ad, say in yayinla(uygula).items():
        print(f"  {ad:8s} {say}")
