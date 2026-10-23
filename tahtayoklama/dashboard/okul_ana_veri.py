"""okul_ana veri katmanı (panelin tek DB erişim noktası).

Yazma kuralları: her işlem tek transaction + denetim kaydı; doğrulama burada, arayüzde değil.
Hata = ValueError(kullanıcıya gösterilecek Türkçe mesaj). Sürücü: psycopg 3.
"""

import json
import os
import re
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

GUNLER = {1: "Pazartesi", 2: "Salı", 3: "Çarşamba", 4: "Perşembe", 5: "Cuma"}
_AD_RE = re.compile(r"^[^\x00-\x1f]{2,100}$")
_SINIF_RE = re.compile(r"^(9|10|11|12)-[A-Za-z0-9]{1,3}$")
_SAAT_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_TR_KUCUK = str.maketrans({"I": "ı", "İ": "i"})


def dsn() -> str:
    d = os.environ.get("OKUL_ANA_DSN")
    if d:
        return d
    return (
        (Path.home() / ".config/okul-ana/baglanti").read_text(encoding="utf-8").strip()
    )


def baglan():
    c = psycopg.connect(dsn(), row_factory=dict_row)
    c.execute("SET search_path = okul_ana")
    return c


def tr_kucuk(s: str) -> str:
    return s.translate(_TR_KUCUK).lower()


# --- doğrulama -----------------------------------------------------------------


def _ad(v, alan="Ad soyad"):
    v = " ".join((v or "").split())
    if not _AD_RE.match(v):
        raise ValueError(f"{alan} 2–100 karakter olmalı.")
    return v


def _tel(v):
    d = re.sub(r"\D", "", v or "")
    if not d:
        return None
    if len(d) == 10:
        d = "0" + d
    if not re.fullmatch(r"0\d{10}", d):
        raise ValueError("Telefon 11 haneli olmalı (05xx xxx xx xx).")
    return d


def _tarih(v):
    v = (v or "").strip()
    if not v:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        raise ValueError("Tarih YYYY-AA-GG biçiminde olmalı.")
    return v


def _no(v):
    try:
        n = int(str(v).strip())
    except ValueError:
        raise ValueError("Okul numarası sayı olmalı.") from None
    if not 1 <= n <= 99998:
        raise ValueError("Okul numarası 1–99998 arasında olmalı.")
    return n


# --- yardımcılar -----------------------------------------------------------------


def aktif_yil(c) -> int:
    r = c.execute("SELECT id FROM ogretim_yili WHERE aktif").fetchone()
    if not r:
        raise ValueError("Aktif öğretim yılı tanımlı değil.")
    return r["id"]


def denetim(
    c, islem: str, hedef: str, ayrinti: dict | None = None, kim: str = "yonetici"
):
    c.execute(
        "INSERT INTO denetim(islem,hedef,ayrinti,kim) VALUES(%s,%s,%s::jsonb,%s)",
        (islem, hedef, json.dumps(ayrinti or {}, ensure_ascii=False), kim),
    )


def _sinif_id(c, yil, ad):
    r = c.execute(
        "SELECT id FROM sinif WHERE yil_id=%s AND ad=%s", (yil, ad)
    ).fetchone()
    if not r:
        raise ValueError(f"'{ad}' sınıfı bulunamadı.")
    return r["id"]


# --- sınıf -----------------------------------------------------------------------


def siniflar(c):
    yil = aktif_yil(c)
    return c.execute(
        "SELECT s.id,s.ad,s.seviye,count(o.okul_no) FILTER (WHERE o.aktif) AS ogrenci_sayisi "
        "FROM sinif s LEFT JOIN sinif_atama a ON a.sinif_id=s.id "
        "LEFT JOIN ogrenci o ON o.okul_no=a.okul_no WHERE s.yil_id=%s "
        "GROUP BY s.id ORDER BY s.seviye,s.ad",
        (yil,),
    ).fetchall()


def sinif_ekle(c, ad):
    ad = (ad or "").strip().upper()
    if not _SINIF_RE.match(ad):
        raise ValueError("Sınıf adı 9-A, 10-B gibi olmalı (9–12 seviyesi).")
    yil = aktif_yil(c)
    if c.execute("SELECT 1 FROM sinif WHERE yil_id=%s AND ad=%s", (yil, ad)).fetchone():
        raise ValueError(f"'{ad}' sınıfı zaten var.")
    c.execute(
        "INSERT INTO sinif(yil_id,ad,seviye) VALUES(%s,%s,%s)",
        (yil, ad, int(ad.split("-")[0])),
    )
    denetim(c, "sinif_ekle", ad)


# --- öğrenci ---------------------------------------------------------------------


def ogrenciler(c, sinif=None, ara=None, pasifler=False):
    yil = aktif_yil(c)
    q = (
        "SELECT o.okul_no,o.ad_soyad,o.cinsiyet,o.telefon,o.dogum_tarihi,o.aktif,s.ad AS sinif "
        "FROM ogrenci o LEFT JOIN sinif_atama a ON a.okul_no=o.okul_no AND a.yil_id=%s "
        "LEFT JOIN sinif s ON s.id=a.sinif_id WHERE (o.aktif OR %s)"
    )
    p = [yil, pasifler]
    if sinif:
        q += " AND s.ad=%s"
        p.append(sinif)
    if ara:
        q += " AND (o.ad_soyad ILIKE %s OR o.okul_no::text = %s)"
        p += [f"%{ara}%", ara.strip()]
    return c.execute(q + " ORDER BY s.seviye,s.ad,o.okul_no", p).fetchall()


def ogrenci_getir(c, no):
    yil = aktif_yil(c)
    return c.execute(
        "SELECT o.*,s.ad AS sinif FROM ogrenci o LEFT JOIN sinif_atama a ON a.okul_no=o.okul_no AND a.yil_id=%s "
        "LEFT JOIN sinif s ON s.id=a.sinif_id WHERE o.okul_no=%s",
        (yil, no),
    ).fetchone()


def ogrenci_kaydet(c, no, ad, cinsiyet, telefon, dogum, sinif, yeni: bool):
    no, ad = _no(no), _ad(ad)
    if cinsiyet not in ("Erkek", "Kız", "", None):
        raise ValueError("Cinsiyet Erkek veya Kız olmalı.")
    cinsiyet, telefon, dogum = cinsiyet or None, _tel(telefon), _tarih(dogum)
    yil = aktif_yil(c)
    sid = _sinif_id(c, yil, sinif)
    mev = c.execute("SELECT aktif FROM ogrenci WHERE okul_no=%s", (no,)).fetchone()
    if yeni and mev and mev["aktif"]:
        raise ValueError(f"{no} numaralı öğrenci zaten kayıtlı.")
    if not yeni and not mev:
        raise ValueError(f"{no} numaralı öğrenci bulunamadı.")
    if mev:
        c.execute(
            "UPDATE ogrenci SET ad_soyad=%s,cinsiyet=%s,telefon=%s,dogum_tarihi=%s,aktif=true WHERE okul_no=%s",
            (ad, cinsiyet, telefon, dogum, no),
        )
    else:
        c.execute(
            "INSERT INTO ogrenci(okul_no,ad_soyad,cinsiyet,telefon,dogum_tarihi) VALUES(%s,%s,%s,%s,%s)",
            (no, ad, cinsiyet, telefon, dogum),
        )
    c.execute(
        "INSERT INTO sinif_atama(okul_no,yil_id,sinif_id) VALUES(%s,%s,%s) "
        "ON CONFLICT (okul_no,yil_id) DO UPDATE SET sinif_id=EXCLUDED.sinif_id",
        (no, yil, sid),
    )
    denetim(
        c, "ogrenci_ekle" if yeni else "ogrenci_guncelle", str(no), {"sinif": sinif}
    )


def ogrenci_pasif(c, no, aktif: bool):
    no = _no(no)
    n = c.execute("UPDATE ogrenci SET aktif=%s WHERE okul_no=%s", (aktif, no)).rowcount
    if not n:
        raise ValueError("Öğrenci bulunamadı.")
    denetim(c, "ogrenci_geri_al" if aktif else "ogrenci_pasif", str(no))


# --- veli ------------------------------------------------------------------------


def veliler(c, no):
    return c.execute(
        "SELECT v.id,v.ad_soyad,v.telefon,vo.yakinlik,"
        "(SELECT count(*) FROM veli_ogrenci x WHERE x.veli_id=v.id) AS bagli "
        "FROM veli_ogrenci vo JOIN veli v ON v.id=vo.veli_id WHERE vo.okul_no=%s ORDER BY v.id",
        (no,),
    ).fetchall()


def veli_kaydet(c, no, veli_id, ad, telefon, yakinlik):
    no, ad, telefon = _no(no), _ad(ad), _tel(telefon)
    yakinlik = " ".join((yakinlik or "").split()) or None
    if yakinlik and len(yakinlik) > 30:
        raise ValueError("Yakınlık en fazla 30 karakter.")
    if not c.execute("SELECT 1 FROM ogrenci WHERE okul_no=%s", (no,)).fetchone():
        raise ValueError("Öğrenci bulunamadı.")
    if veli_id:
        if not c.execute(
            "SELECT 1 FROM veli_ogrenci WHERE veli_id=%s AND okul_no=%s", (veli_id, no)
        ).fetchone():
            raise ValueError("Bu veli bu öğrenciye bağlı değil.")
        c.execute(
            "UPDATE veli SET ad_soyad=%s,telefon=%s WHERE id=%s", (ad, telefon, veli_id)
        )
        c.execute(
            "UPDATE veli_ogrenci SET yakinlik=%s WHERE veli_id=%s AND okul_no=%s",
            (yakinlik, veli_id, no),
        )
        denetim(c, "veli_guncelle", str(no), {"veli_id": veli_id})
        return
    r = c.execute(
        "SELECT id FROM veli WHERE ad_soyad=%s AND telefon IS NOT DISTINCT FROM %s",
        (ad, telefon),
    ).fetchone()
    vid = (
        r["id"]
        if r
        else c.execute(
            "INSERT INTO veli(ad_soyad,telefon) VALUES(%s,%s) RETURNING id",
            (ad, telefon),
        ).fetchone()["id"]
    )
    if c.execute(
        "SELECT 1 FROM veli_ogrenci WHERE veli_id=%s AND okul_no=%s", (vid, no)
    ).fetchone():
        raise ValueError("Bu veli zaten bu öğrenciye bağlı.")
    c.execute(
        "INSERT INTO veli_ogrenci(veli_id,okul_no,yakinlik) VALUES(%s,%s,%s)",
        (vid, no, yakinlik),
    )
    denetim(c, "veli_ekle", str(no), {"veli_id": vid})


def veli_sil(c, no, veli_id):
    n = c.execute(
        "DELETE FROM veli_ogrenci WHERE veli_id=%s AND okul_no=%s", (veli_id, no)
    ).rowcount
    if not n:
        raise ValueError("Veli bağı bulunamadı.")
    c.execute(
        "DELETE FROM veli WHERE id=%s AND NOT EXISTS (SELECT 1 FROM veli_ogrenci WHERE veli_id=%s)",
        (veli_id, veli_id),
    )
    denetim(c, "veli_sil", str(no), {"veli_id": veli_id})


# --- personel ----------------------------------------------------------------------


def personel(c, pasifler=False):
    return c.execute(
        "SELECT * FROM personel WHERE aktif OR %s ORDER BY aktif DESC,ad_soyad",
        (pasifler,),
    ).fetchall()


def personel_kaydet(c, pid, ad, telefon, gorev, dogum):
    ad, telefon, dogum = _ad(ad), _tel(telefon), _tarih(dogum)
    if gorev not in ("ogretmen", "yonetici", "diger"):
        raise ValueError("Görev ogretmen, yonetici veya diger olmalı.")
    if pid:
        n = c.execute(
            "UPDATE personel SET ad_soyad=%s,telefon=%s,gorev=%s,dogum_tarihi=%s,aktif=true WHERE id=%s",
            (ad, telefon, gorev, dogum, pid),
        ).rowcount
        if not n:
            raise ValueError("Personel bulunamadı.")
        denetim(c, "personel_guncelle", str(pid))
    else:
        r = c.execute(
            "INSERT INTO personel(ad_soyad,telefon,gorev,dogum_tarihi) VALUES(%s,%s,%s,%s) RETURNING id",
            (ad, telefon, gorev, dogum),
        ).fetchone()
        denetim(c, "personel_ekle", str(r["id"]))


def personel_pasif(c, pid):
    if not c.execute("UPDATE personel SET aktif=false WHERE id=%s", (pid,)).rowcount:
        raise ValueError("Personel bulunamadı.")
    denetim(c, "personel_pasif", str(pid))


# --- ders programı -----------------------------------------------------------------


def program(c, sinif):
    yil = aktif_yil(c)
    sid = _sinif_id(c, yil, sinif)
    g = {
        (r["gun"], r["ders_no"]): r["ders"]
        for r in c.execute(
            "SELECT gun,ders_no,ders FROM ders_programi WHERE sinif_id=%s", (sid,)
        )
    }
    return g


def program_kaydet(c, sinif, hucreler: dict):
    """hucreler: {(gun, ders_no): ders|''}. Boş = hücreyi sil. Ders adı küçük harfe (Türkçe) çevrilir."""
    yil = aktif_yil(c)
    sid = _sinif_id(c, yil, sinif)
    for (gun, no), ders in hucreler.items():
        if gun not in GUNLER or not 1 <= no <= 10:
            raise ValueError("Geçersiz gün/ders numarası.")
        ders = tr_kucuk(" ".join((ders or "").split()))
        if len(ders) > 80:
            raise ValueError("Ders adı en fazla 80 karakter.")
        if ders:
            c.execute(
                "INSERT INTO ders_programi(yil_id,sinif_id,gun,ders_no,ders) VALUES(%s,%s,%s,%s,%s) "
                "ON CONFLICT (sinif_id,gun,ders_no) DO UPDATE SET ders=EXCLUDED.ders",
                (yil, sid, gun, no, ders),
            )
        else:
            c.execute(
                "DELETE FROM ders_programi WHERE sinif_id=%s AND gun=%s AND ders_no=%s",
                (sid, gun, no),
            )
    denetim(c, "program_guncelle", sinif)


# --- zil -------------------------------------------------------------------------------


def zil(c):
    yil = aktif_yil(c)
    satirlar = c.execute(
        "SELECT ders_no,to_char(baslangic,'HH24:MI') AS baslangic,to_char(bitis,'HH24:MI') AS bitis "
        "FROM zil WHERE yil_id=%s AND gun_tipi='normal' ORDER BY ders_no",
        (yil,),
    ).fetchall()
    ayar = {
        r["anahtar"]: r["deger"]
        for r in c.execute(
            "SELECT anahtar,deger FROM ayar WHERE yil_id=%s AND anahtar IN ('ders_suresi_dk','teneffus_dk')",
            (yil,),
        )
    }
    return satirlar, ayar


def _dk(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def zil_kaydet(c, saatler: list, ders_suresi, teneffus):
    """saatler: [(no, 'SS:DD', 'SS:DD')]; boş satırlar atılır. Öğle arası = en büyük boşluk (eski betikle aynı)."""
    saatler = sorted(
        (n, b.strip(), e.strip()) for n, b, e in saatler if b.strip() or e.strip()
    )
    if not saatler:
        raise ValueError("En az bir ders saati gerekli.")
    onceki = -1
    for n, b, e in saatler:
        if not (_SAAT_RE.match(b) and _SAAT_RE.match(e)):
            raise ValueError(f"{n}. ders saati SS:DD biçiminde olmalı.")
        if _dk(e) <= _dk(b):
            raise ValueError(f"{n}. ders bitişi başlangıçtan sonra olmalı.")
        if _dk(b) < onceki:
            raise ValueError(f"{n}. ders bir öncekiyle çakışıyor.")
        onceki = _dk(e)
    if len({n for n, _, _ in saatler}) != len(saatler):
        raise ValueError("Ders numaraları tekrar ediyor.")
    try:
        ders_suresi, teneffus = int(ders_suresi), int(teneffus)
    except ValueError:
        raise ValueError("Ders süresi ve teneffüs sayı olmalı.") from None
    if not (10 <= ders_suresi <= 120 and 0 <= teneffus <= 60):
        raise ValueError("Ders süresi 10–120, teneffüs 0–60 dakika olmalı.")
    yil = aktif_yil(c)
    c.execute("DELETE FROM zil WHERE yil_id=%s AND gun_tipi='normal'", (yil,))
    for n, b, e in saatler:
        c.execute(
            "INSERT INTO zil(yil_id,gun_tipi,ders_no,baslangic,bitis) VALUES(%s,'normal',%s,%s,%s)",
            (yil, n, b, e),
        )
    en = None
    for (_, _, e1), (_, b2, _) in zip(saatler, saatler[1:]):
        bosluk = _dk(b2) - _dk(e1)
        if en is None or bosluk > en[0]:
            en = (bosluk, e1, b2)
    for k, v in (
        ("ders_suresi_dk", ders_suresi),
        ("teneffus_dk", teneffus),
        ("ogle_arasi", {"baslangic": en[1], "bitis": en[2]} if en else None),
    ):
        if v is None:
            continue
        c.execute(
            "INSERT INTO ayar(yil_id,anahtar,deger) VALUES(%s,%s,%s::jsonb) "
            "ON CONFLICT (yil_id,anahtar) DO UPDATE SET deger=EXCLUDED.deger",
            (yil, k, json.dumps(v)),
        )
    denetim(c, "zil_guncelle", "normal", {"ders": len(saatler)})


def denetim_son(c, n=50):
    return c.execute(
        "SELECT zaman,islem,hedef,kim FROM denetim ORDER BY id DESC LIMIT %s", (n,)
    ).fetchall()
