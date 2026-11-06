"""Okul kütüphanesi: eser (kitap) + fiziksel nüsha (demirbaş), ödünç/iade, ayırtma sırası, ayarlar, Excel, rapor.

Bir eser ISBN ile tekildir (ISBN yoksa başlık + yayınevi ile eşlenir); her fiziksel kopya ayrı bir nüshadır ve
demirbaş numarasıyla tekildir. Baskı yılı/basım sayısı nüshaya aittir (aynı ISBN'in nüshaları farklı basım olabilir).
Nüsha durumu yalnızca fiziksel hâli tutar (sağlam/hasarlı/kayıp); ödünçte mi `odunc`, ayrıldı mı `ayirtma`'dan türetilir.
Okutulan kod: `ETIKET_ONEK` ile başlıyorsa (bizim bastığımız QR etiket) demirbaştır; değilse geçerli ISBN ise eser
aranır, ayrıca aynı metinle demirbaş da aranır — ikisi ayrı listelenir, birbirine çevrilmez.
Yazma işlemleri BEGIN IMMEDIATE ile tek işlemdir: laptop ve telefonlar aynı anda okutsa da sıraya girer.
Yetki kontrolü (`islem_yetkisi`) rotalarda yapılır. Ödünç sayısı okuma sayısı DEĞİLDİR (okuma kaydı tutulmaz).
"""

import io
import re
import sqlite3
from collections import Counter
from datetime import date, timedelta

import metin
import openpyxl
import zaman

DURUMLAR = {"saglam": "Sağlam", "hasarli": "Hasarlı", "kayip": "Kayıp"}
AYIRTMA_DURUMLARI = {"bekliyor": "Sırada", "hazir": "Hazır", "tamam": "Alındı", "iptal": "İptal", "doldu": "Süresi doldu"}
AZAMI_METIN = 300
ETIKET_ONEK = "KTP-"
# Yönetim panelinden değişir (`kutuphane_ayar`); varsayılanlar okul kararı (2026-11-06, Atakan).
AYAR_VARSAYILAN = {"odunc_gun": 14, "ogrenci_limit": 2, "hatirlatma": 1}
AYAR_SINIR = {"odunc_gun": (1, 90), "ogrenci_limit": (1, 10), "hatirlatma": (0, 1)}
HATIRLATMA_GUN = 2  # son teslimden kaç gün önce uygulama içi uyarı
AYIRTMA_LIMIT = 2  # öğrenci başına açık ayırtma
HAZIR_GUN = 3  # iade edilen nüsha sıradaki öğrenciye kaç gün ayrılır
AZAMI_SATIR = 20000


class KutuphaneHatasi(Exception):
    def __init__(self, mesaj: str, kod: int = 400):
        super().__init__(mesaj)
        self.mesaj = mesaj
        self.kod = kod


def islem_yetkisi(conn: sqlite3.Connection, kullanici) -> bool:
    """Kitap ekleme, ödünç verme ve iade: yönetici ya da yetkilendirilmiş öğretmen."""
    if kullanici["rol"] == "yonetici":
        return True
    if kullanici["rol"] != "ogretmen":
        return False
    return conn.execute("SELECT 1 FROM kutuphane_yetkili WHERE kullanici_id = ?", (kullanici["id"],)).fetchone() is not None


def isbn_normalize(s: str | None) -> str | None:
    """Tire/boşluk atılır; ISBN-10 ve ISBN-13 sağlama haneleri doğrulanır. Boş girdi = ISBN yok."""
    if s is None or not str(s).strip():
        return None
    d = re.sub(r"[\s-]", "", str(s)).upper()
    if not d:  # "-" gibi boş işaretler
        return None
    if re.fullmatch(r"\d{13}", d):
        toplam = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(d[:12]))
        if (10 - toplam % 10) % 10 == int(d[12]):
            return d
    elif re.fullmatch(r"\d{9}[\dX]", d):
        toplam = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(d))
        if toplam % 11 == 0:
            return d
    raise KutuphaneHatasi("ISBN geçersiz.")


def demirbas_normalize(s: str | None) -> str:
    """Baştaki sıfırlar KORUNUR ("03244"); yalnızca boşluk atılır."""
    d = re.sub(r"\s", "", str(s or ""))
    if not d or len(d) > 30 or not re.fullmatch(r"[0-9A-Za-z./-]+", d):
        raise KutuphaneHatasi("Demirbaş numarası geçersiz.")
    return d


def _yil(s) -> int | None:
    if s is None or not str(s).strip():
        return None
    try:
        y = int(str(s).strip())
    except ValueError:
        raise KutuphaneHatasi("Baskı yılı geçersiz.") from None
    if not 1450 <= y <= zaman.simdi().year + 1:
        raise KutuphaneHatasi("Baskı yılı geçersiz.")
    return y


def _metin(s, alan: str, zorunlu: bool = False) -> str:
    m = " ".join(str(s or "").split())
    if zorunlu and not m:
        raise KutuphaneHatasi(f"{alan} boş olamaz.")
    if len(m) > AZAMI_METIN:
        raise KutuphaneHatasi(f"{alan} en çok {AZAMI_METIN} karakter olabilir.")
    return m


def _kitap_bul(conn: sqlite3.Connection, isbn: str | None, baslik: str, yayinevi: str) -> int | None:
    if isbn:
        r = conn.execute("SELECT id FROM kitap WHERE isbn = ?", (isbn,)).fetchone()
        return r["id"] if r else None
    hedef = (metin.normalize_isim(baslik), metin.normalize_isim(yayinevi))
    for r in conn.execute("SELECT id, baslik, yayinevi FROM kitap WHERE isbn IS NULL"):
        if (metin.normalize_isim(r["baslik"]), metin.normalize_isim(r["yayinevi"])) == hedef:
            return r["id"]
    return None


def _islem(conn: sqlite3.Connection):
    """BEGIN IMMEDIATE bağlamı: yazma kilidi baştan alınır, hata olursa geri alınır."""

    class _Islem:
        def __enter__(self):
            conn.execute("BEGIN IMMEDIATE")

        def __exit__(self, tur, deger, iz):
            if tur is None:
                conn.commit()
            else:
                conn.rollback()
            return False

    return _Islem()


def nusha_ekle(
    conn: sqlite3.Connection,
    *,
    demirbas: str,
    baslik: str,
    isbn: str | None = None,
    yayinevi: str = "",
    baski_yili=None,
    basim_sayisi: str = "",
    yazar: str = "",
    tur: str = "",
    raf: str = "",
) -> int:
    """Nüshayı ekler; eser yoksa oluşturur (varsa eser bilgisine dokunmaz). Tek işlem; nüsha id döner."""
    d = demirbas_normalize(demirbas)
    i = isbn_normalize(isbn)
    b = _metin(baslik, "Başlık", zorunlu=True)
    yv = _metin(yayinevi, "Yayınevi")
    yil = _yil(baski_yili)
    alanlar = (_metin(yazar, "Yazar"), _metin(tur, "Tür"), _metin(basim_sayisi, "Basım sayısı"), _metin(raf, "Raf"))
    simdi = zaman.simdi_str()
    try:
        with _islem(conn):
            kitap_id = _kitap_bul(conn, i, b, yv)
            if kitap_id is None:
                kitap_id = conn.execute(
                    "INSERT INTO kitap (isbn, baslik, yazar, yayinevi, tur, olusturma) VALUES (?, ?, ?, ?, ?, ?)",
                    (i, b, alanlar[0], yv, alanlar[1], simdi),
                ).lastrowid
            return conn.execute(
                "INSERT INTO nusha (kitap_id, demirbas, baski_yili, basim_sayisi, raf, olusturma) VALUES (?, ?, ?, ?, ?, ?)",
                (kitap_id, d, yil, alanlar[2], alanlar[3], simdi),
            ).lastrowid
    except sqlite3.IntegrityError:
        raise KutuphaneHatasi(f"{d} demirbaş numaralı nüsha zaten kayıtlı.", 409) from None


def kitap_isbn(conn: sqlite3.Connection, isbn: str) -> dict | None:
    """Kitap ekleme formunda ISBN okutulunca mevcut eser bilgisi (önceden doldurmak için)."""
    try:
        i = isbn_normalize(isbn)
    except KutuphaneHatasi:
        return None
    r = conn.execute("SELECT * FROM kitap WHERE isbn = ?", (i,)).fetchone() if i else None
    return dict(r) if r else None


# ---- Ayarlar ve yetkililer ----

def ayarlar(conn: sqlite3.Connection) -> dict:
    a = dict(AYAR_VARSAYILAN)
    for r in conn.execute("SELECT anahtar, deger FROM kutuphane_ayar"):
        if r["anahtar"] in a:
            a[r["anahtar"]] = r["deger"]
    return a


def ayar_kaydet(conn: sqlite3.Connection, degerler: dict) -> None:
    temiz = {}
    for k, (alt, ust) in AYAR_SINIR.items():
        try:
            v = int(degerler.get(k, AYAR_VARSAYILAN[k]))
        except (TypeError, ValueError):
            raise KutuphaneHatasi("Ayar değeri sayı olmalı.") from None
        if not alt <= v <= ust:
            raise KutuphaneHatasi(f"Ayar {alt}-{ust} arasında olmalı.")
        temiz[k] = v
    with _islem(conn):
        conn.executemany(
            "INSERT INTO kutuphane_ayar (anahtar, deger) VALUES (?, ?) ON CONFLICT(anahtar) DO UPDATE SET deger = excluded.deger",
            list(temiz.items()),
        )


def ogretmenler(conn: sqlite3.Connection) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT u.id, u.ad_soyad, y.kullanici_id IS NOT NULL AS yetkili
               FROM kullanici u LEFT JOIN kutuphane_yetkili y ON y.kullanici_id = u.id
               WHERE u.rol = 'ogretmen' AND u.aktif = 1 ORDER BY u.ad_soyad"""
        )
    ]


def yetkilileri_ayarla(conn: sqlite3.Connection, ogretmen_idler: list[int]) -> None:
    gecerli = {r["id"] for r in ogretmenler(conn)}
    with _islem(conn):
        conn.execute("DELETE FROM kutuphane_yetkili")
        conn.executemany(
            "INSERT INTO kutuphane_yetkili (kullanici_id, olusturma) VALUES (?, ?)",
            [(i, zaman.simdi_str()) for i in sorted(set(ogretmen_idler) & gecerli)],
        )


# ---- Okutma / arama ----

_NUSHA_SQL = """
SELECT n.id, n.demirbas, n.raf, n.durum, n.baski_yili, n.basim_sayisi,
       k.id AS kitap_id, k.isbn, k.baslik, k.yazar, k.yayinevi, k.tur,
       o.id AS odunc_id, o.verilis, o.son_tarih, g.ad_soyad AS odunc_ad, g.sinif AS odunc_sinif, g.okul_no AS odunc_no,
       a.ogrenci_id AS ayrilan_ogrenci, ga.ad_soyad AS ayrilan_ad, ga.sinif AS ayrilan_sinif, a.hazir_bitis
FROM nusha n JOIN kitap k ON k.id = n.kitap_id
LEFT JOIN odunc o ON o.nusha_id = n.id AND o.iade IS NULL
LEFT JOIN ogrenci g ON g.id = o.ogrenci_id
LEFT JOIN ayirtma a ON a.nusha_id = n.id AND a.durum = 'hazir'
LEFT JOIN ogrenci ga ON ga.id = a.ogrenci_id
"""


def _nusha_satiri(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["durum_ad"] = DURUMLAR[d["durum"]]
    d["oduncte"] = d["odunc_id"] is not None
    d["gecikme_gun"] = gecikme_gun(d["son_tarih"]) if d["son_tarih"] else 0
    d["musait"] = d["durum"] == "saglam" and not d["oduncte"] and d["ayrilan_ogrenci"] is None
    return d


def nushalar(conn: sqlite3.Connection, kosul: str, params: tuple) -> list[dict]:
    return [_nusha_satiri(r) for r in conn.execute(f"{_NUSHA_SQL} WHERE {kosul} ORDER BY k.baslik, n.demirbas", params)]


def kod_coz(conn: sqlite3.Connection, kod: str) -> dict:
    """Kamera/elle girilen kod → {'demirbas': [nüsha], 'isbn': [nüsha], 'isbn_kodu': str|None}. İkisi karıştırılmaz."""
    k = (kod or "").strip()
    if k.upper().startswith(ETIKET_ONEK):
        try:
            d = demirbas_normalize(k[len(ETIKET_ONEK):])
        except KutuphaneHatasi:
            return {"demirbas": [], "isbn": [], "isbn_kodu": None}
        return {"demirbas": nushalar(conn, "n.demirbas = ?", (d,)), "isbn": [], "isbn_kodu": None}
    try:
        i = isbn_normalize(k)
    except KutuphaneHatasi:
        i = None
    try:
        d = demirbas_normalize(k)
    except KutuphaneHatasi:
        d = None
    return {
        "demirbas": nushalar(conn, "n.demirbas = ?", (d,)) if d else [],
        "isbn": nushalar(conn, "k.isbn = ?", (i,)) if i else [],
        "isbn_kodu": i,
    }


def demirbas_bul(conn: sqlite3.Connection, demirbas: str) -> dict | None:
    """Demirbaş okutulunca nüsha + eser bilgisi."""
    try:
        d = demirbas_normalize(demirbas)
    except KutuphaneHatasi:
        return None
    liste = nushalar(conn, "n.demirbas = ?", (d,))
    return liste[0] if liste else None


def _eslesir(aranan: str, *alanlar: str) -> bool:
    hedef = metin.normalize_isim(" ".join(a or "" for a in alanlar))
    return all(p in hedef for p in metin.normalize_isim(aranan).split())


def ogrenci_ara(conn: sqlite3.Connection, q: str, limit: int = 10) -> list[dict]:
    """Mevcut DijitalOkul öğrencilerinden (pasif hesaplar hariç) okul no ya da ad ile."""
    q = (q or "").strip()
    if not q:
        return []
    satirlar = conn.execute(
        """SELECT o.id, o.okul_no, o.ad_soyad, o.sinif,
                  (SELECT COUNT(*) FROM odunc d WHERE d.ogrenci_id = o.id AND d.iade IS NULL) AS aktif
           FROM ogrenci o LEFT JOIN kullanici u ON u.id = o.kullanici_id
           WHERE COALESCE(u.aktif, 1) = 1 ORDER BY o.okul_no"""
    ).fetchall()
    if q.isdigit():
        sonuc = [r for r in satirlar if str(r["okul_no"]) == q] + [
            r for r in satirlar if str(r["okul_no"]).startswith(q) and str(r["okul_no"]) != q
        ]
    else:
        sonuc = [r for r in satirlar if _eslesir(q, r["ad_soyad"])]
    return [dict(r) for r in sonuc[:limit]]


def katalog(conn: sqlite3.Connection, q: str = "", limit: int = 100) -> list[dict]:
    """Eser listesi + nüsha/rafta sayısı (müsait = sağlam, ödünçte değil, kimseye ayrılmamış)."""
    satirlar = conn.execute(
        """SELECT k.id, k.isbn, k.baslik, k.yazar, k.yayinevi, k.tur, COUNT(n.id) AS nusha,
                  SUM(CASE WHEN n.durum = 'saglam' AND o.id IS NULL AND a.id IS NULL THEN 1 ELSE 0 END) AS rafta,
                  SUM(CASE WHEN o.id IS NOT NULL THEN 1 ELSE 0 END) AS oduncte
           FROM kitap k LEFT JOIN nusha n ON n.kitap_id = k.id
           LEFT JOIN odunc o ON o.nusha_id = n.id AND o.iade IS NULL
           LEFT JOIN ayirtma a ON a.nusha_id = n.id AND a.durum = 'hazir'
           GROUP BY k.id ORDER BY k.baslik"""
    ).fetchall()
    if q and q.strip():
        satirlar = [r for r in satirlar if _eslesir(q, r["baslik"], r["yazar"], r["yayinevi"], r["isbn"])]
    return [dict(r) for r in satirlar[:limit]]


def nusha_durum_ayarla(conn: sqlite3.Connection, nusha_id: int, durum: str) -> None:
    if durum not in DURUMLAR:
        raise KutuphaneHatasi("Geçersiz durum.")
    with _islem(conn):
        if conn.execute("UPDATE nusha SET durum = ? WHERE id = ?", (durum, nusha_id)).rowcount != 1:
            raise KutuphaneHatasi("Nüsha bulunamadı.", 404)
        if durum != "saglam":  # ayrılmış nüsha artık verilemez: ayrılan öğrenci sıranın başına döner
            conn.execute(
                "UPDATE ayirtma SET durum = 'bekliyor', nusha_id = NULL, hazir_bitis = NULL WHERE nusha_id = ? AND durum = 'hazir'",
                (nusha_id,),
            )
        else:
            _sira_ilerlet(conn, nusha_id)


# ---- Ödünç / iade ----

def gecikme_gun(son_tarih: str, bitis: date | None = None) -> int:
    """Son teslim gününden sonraki gün sayısı (son gün teslim = gecikme yok); bitis yoksa bugün."""
    gun = bitis or zaman.simdi().date()
    return max(0, (gun - date.fromisoformat(son_tarih)).days)


_ODUNC_SQL = """
SELECT o.id, o.nusha_id, o.ogrenci_id, o.verilis, o.son_tarih, o.iade,
       n.demirbas, k.id AS kitap_id, k.baslik, k.yazar, k.isbn, g.ad_soyad, g.sinif, g.okul_no,
       v.ad_soyad AS veren_ad, al.ad_soyad AS alan_ad
FROM odunc o JOIN nusha n ON n.id = o.nusha_id JOIN kitap k ON k.id = n.kitap_id
JOIN ogrenci g ON g.id = o.ogrenci_id JOIN kullanici v ON v.id = o.veren_id
LEFT JOIN kullanici al ON al.id = o.alan_id
"""


def _odunc_satiri(r: sqlite3.Row) -> dict:
    d = dict(r)
    bitis = date.fromisoformat(d["iade"][:10]) if d["iade"] else None
    d["gecikme_gun"] = gecikme_gun(d["son_tarih"], bitis)
    d["kalan_gun"] = (date.fromisoformat(d["son_tarih"]) - zaman.simdi().date()).days
    return d


def odunc_kaydi(conn: sqlite3.Connection, odunc_id: int) -> dict | None:
    r = conn.execute(f"{_ODUNC_SQL} WHERE o.id = ?", (odunc_id,)).fetchone()
    return _odunc_satiri(r) if r else None


def aktif_odunc(conn: sqlite3.Connection, nusha_id: int) -> dict | None:
    r = conn.execute("SELECT id FROM odunc WHERE nusha_id = ? AND iade IS NULL", (nusha_id,)).fetchone()
    return odunc_kaydi(conn, r["id"]) if r else None


def aktif_odunclar(conn: sqlite3.Connection, sadece_geciken: bool = False) -> list[dict]:
    liste = [_odunc_satiri(r) for r in conn.execute(f"{_ODUNC_SQL} WHERE o.iade IS NULL ORDER BY o.son_tarih, g.sinif, g.ad_soyad")]
    return [x for x in liste if x["gecikme_gun"] > 0] if sadece_geciken else liste


def son_islemler(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    return [_odunc_satiri(r) for r in conn.execute(f"{_ODUNC_SQL} ORDER BY COALESCE(o.iade, o.verilis) DESC LIMIT ?", (limit,))]


def odunc_ver(conn: sqlite3.Connection, nusha_id: int, ogrenci_id: int, veren_id: int) -> int:
    """Tek işlem (BEGIN IMMEDIATE): aynı anda iki cihazdan okutma sıraya girer, limit ve nüsha kontrolü yarışmaz."""
    simdi = zaman.simdi()
    try:
        with _islem(conn):
            _suresi_dolanlar(conn)
            n = conn.execute("SELECT durum, kitap_id FROM nusha WHERE id = ?", (nusha_id,)).fetchone()
            if n is None:
                raise KutuphaneHatasi("Nüsha bulunamadı.", 404)
            if n["durum"] != "saglam":
                raise KutuphaneHatasi(f"Bu nüsha {DURUMLAR[n['durum']].lower()} olarak işaretli.", 409)
            if conn.execute("SELECT 1 FROM odunc WHERE nusha_id = ? AND iade IS NULL", (nusha_id,)).fetchone():
                raise KutuphaneHatasi("Bu nüsha zaten ödünçte.", 409)
            if conn.execute("SELECT 1 FROM ogrenci WHERE id = ?", (ogrenci_id,)).fetchone() is None:
                raise KutuphaneHatasi("Öğrenci bulunamadı.", 404)
            ayrilan = conn.execute(
                "SELECT a.ogrenci_id, g.ad_soyad FROM ayirtma a JOIN ogrenci g ON g.id = a.ogrenci_id"
                " WHERE a.nusha_id = ? AND a.durum = 'hazir'",
                (nusha_id,),
            ).fetchone()
            if ayrilan and ayrilan["ogrenci_id"] != ogrenci_id:
                raise KutuphaneHatasi(f"Bu nüsha {ayrilan['ad_soyad']} için ayrıldı; başka nüsha seçin.", 409)
            ayar = ayarlar(conn)
            aktif = conn.execute("SELECT COUNT(*) FROM odunc WHERE ogrenci_id = ? AND iade IS NULL", (ogrenci_id,)).fetchone()[0]
            if aktif >= ayar["ogrenci_limit"]:
                raise KutuphaneHatasi(f"Öğrencinin zaten {ayar['ogrenci_limit']} kitabı var; önce birini iade etmeli.", 409)
            oid = conn.execute(
                "INSERT INTO odunc (nusha_id, ogrenci_id, veren_id, verilis, son_tarih) VALUES (?, ?, ?, ?, ?)",
                (nusha_id, ogrenci_id, veren_id, simdi.strftime(zaman.BICIM),
                 (simdi.date() + timedelta(days=ayar["odunc_gun"])).isoformat()),
            ).lastrowid
            # Bu öğrencinin bu esere açık ayırtması (hazır ya da sırada) kapanır.
            conn.execute(
                "UPDATE ayirtma SET durum = 'tamam', kapanis = ? WHERE kitap_id = ? AND ogrenci_id = ? AND durum IN ('bekliyor', 'hazir')",
                (simdi.strftime(zaman.BICIM), n["kitap_id"], ogrenci_id),
            )
            return oid
    except sqlite3.IntegrityError:
        raise KutuphaneHatasi("Bu nüsha zaten ödünçte.", 409) from None


def iade_al(conn: sqlite3.Connection, nusha_id: int, alan_id: int) -> dict:
    """Aktif ödüncü kapatır; ikinci okutmada 409 (çift işlem yok). Sırada bekleyen varsa nüsha ona ayrılır:
    dönen kayıttaki 'ayrilan' personele "rafa koyma, ayır" bilgisidir."""
    with _islem(conn):
        _suresi_dolanlar(conn)
        r = conn.execute("SELECT id FROM odunc WHERE nusha_id = ? AND iade IS NULL", (nusha_id,)).fetchone()
        if r is None:
            raise KutuphaneHatasi("Bu nüsha ödünçte değil.", 409)
        conn.execute("UPDATE odunc SET iade = ?, alan_id = ? WHERE id = ?", (zaman.simdi_str(), alan_id, r["id"]))
        ayrilan = _sira_ilerlet(conn, nusha_id)
    kayit = odunc_kaydi(conn, r["id"])
    kayit["ayrilan"] = ayrilan
    return kayit


# ---- Ayırtma (sıra) ----

def _sira_ilerlet(conn: sqlite3.Connection, nusha_id: int) -> dict | None:
    """Nüsha boşsa (sağlam, ödünçte değil, ayrılmamış) eserin sıradaki ilk öğrencisine HAZIR_GUN gün ayrılır."""
    n = conn.execute(
        """SELECT n.kitap_id FROM nusha n WHERE n.id = ? AND n.durum = 'saglam'
           AND NOT EXISTS (SELECT 1 FROM odunc o WHERE o.nusha_id = n.id AND o.iade IS NULL)
           AND NOT EXISTS (SELECT 1 FROM ayirtma a WHERE a.nusha_id = n.id AND a.durum = 'hazir')""",
        (nusha_id,),
    ).fetchone()
    if n is None:
        return None
    a = conn.execute(
        "SELECT a.id, g.ad_soyad, g.sinif FROM ayirtma a JOIN ogrenci g ON g.id = a.ogrenci_id"
        " WHERE a.kitap_id = ? AND a.durum = 'bekliyor' ORDER BY a.id LIMIT 1",
        (n["kitap_id"],),
    ).fetchone()
    if a is None:
        return None
    bitis = (zaman.simdi() + timedelta(days=HAZIR_GUN)).strftime(zaman.BICIM)
    conn.execute("UPDATE ayirtma SET durum = 'hazir', nusha_id = ?, hazir_bitis = ? WHERE id = ?", (nusha_id, bitis, a["id"]))
    return {"ad_soyad": a["ad_soyad"], "sinif": a["sinif"], "hazir_bitis": bitis}


def _suresi_dolanlar(conn: sqlite3.Connection) -> None:
    """Süresinde alınmayan 'hazır' ayırtmalar düşer, nüsha sıradakine geçer. Çağıran işlemin içinde çalışır."""
    simdi = zaman.simdi_str()
    for r in conn.execute("SELECT id, nusha_id FROM ayirtma WHERE durum = 'hazir' AND hazir_bitis < ?", (simdi,)).fetchall():
        conn.execute("UPDATE ayirtma SET durum = 'doldu', kapanis = ? WHERE id = ?", (simdi, r["id"]))
        _sira_ilerlet(conn, r["nusha_id"])


def ayirtma_temizle(conn: sqlite3.Connection) -> None:
    """Okuma sayfalarından (öğrenci ana sayfası dahil) çağrılır; sayfayı ASLA bozmaz: süresi dolan yoksa kilit alınmaz,
    çağıranın açık işlemi varsa ya da veritabanı meşgulse temizlik atlanır (sonraki ödünç/iade işlemi zaten yapar)."""
    if conn.in_transaction:
        return
    if conn.execute("SELECT 1 FROM ayirtma WHERE durum = 'hazir' AND hazir_bitis < ?", (zaman.simdi_str(),)).fetchone():
        try:
            with _islem(conn):
                _suresi_dolanlar(conn)
        except sqlite3.OperationalError:
            pass


def ayirt(conn: sqlite3.Connection, kitap_id: int, ogrenci_id: int) -> int:
    """Öğrenci, rafta nüshası kalmamış bir eseri sıraya yazar."""
    try:
        with _islem(conn):
            _suresi_dolanlar(conn)
            k = next((x for x in katalog(conn, limit=10**9) if x["id"] == kitap_id), None)
            if k is None or k["nusha"] == 0:
                raise KutuphaneHatasi("Kitap bulunamadı.", 404)
            if k["rafta"] > 0:
                raise KutuphaneHatasi("Bu kitap şu an rafta; kütüphaneden alabilirsin.", 409)
            if conn.execute(
                "SELECT 1 FROM odunc o JOIN nusha n ON n.id = o.nusha_id WHERE n.kitap_id = ? AND o.ogrenci_id = ? AND o.iade IS NULL",
                (kitap_id, ogrenci_id),
            ).fetchone():
                raise KutuphaneHatasi("Bu kitap zaten sende.", 409)
            acik = conn.execute(
                "SELECT COUNT(*) FROM ayirtma WHERE ogrenci_id = ? AND durum IN ('bekliyor', 'hazir')", (ogrenci_id,)
            ).fetchone()[0]
            if acik >= AYIRTMA_LIMIT:
                raise KutuphaneHatasi(f"En çok {AYIRTMA_LIMIT} kitap ayırtabilirsin.", 409)
            return conn.execute(
                "INSERT INTO ayirtma (kitap_id, ogrenci_id, olusturma) VALUES (?, ?, ?)",
                (kitap_id, ogrenci_id, zaman.simdi_str()),
            ).lastrowid
    except sqlite3.IntegrityError:
        raise KutuphaneHatasi("Bu kitabı zaten ayırttın.", 409) from None


def ayirtma_iptal(conn: sqlite3.Connection, ayirtma_id: int, ogrenci_id: int) -> None:
    with _islem(conn):
        r = conn.execute(
            "SELECT nusha_id FROM ayirtma WHERE id = ? AND ogrenci_id = ? AND durum IN ('bekliyor', 'hazir')",
            (ayirtma_id, ogrenci_id),
        ).fetchone()
        if r is None:
            raise KutuphaneHatasi("Ayırtma bulunamadı.", 404)
        conn.execute("UPDATE ayirtma SET durum = 'iptal', kapanis = ? WHERE id = ?", (zaman.simdi_str(), ayirtma_id))
        if r["nusha_id"]:
            _sira_ilerlet(conn, r["nusha_id"])


def ayirtmalar(conn: sqlite3.Connection, ogrenci_id: int | None = None) -> list[dict]:
    """Açık ayırtmalar; sıra = aynı eserde kendisinden önce bekleyen sayısı + 1."""
    kosul, params = ("AND a.ogrenci_id = ?", (ogrenci_id,)) if ogrenci_id else ("", ())
    sonuc = []
    for r in conn.execute(
        f"""SELECT a.id, a.kitap_id, a.ogrenci_id, a.durum, a.olusturma, a.hazir_bitis, k.baslik, k.yazar,
                   n.demirbas, g.ad_soyad, g.sinif,
                   (SELECT COUNT(*) FROM ayirtma b WHERE b.kitap_id = a.kitap_id AND b.durum = 'bekliyor' AND b.id < a.id) + 1 AS sira
            FROM ayirtma a JOIN kitap k ON k.id = a.kitap_id JOIN ogrenci g ON g.id = a.ogrenci_id
            LEFT JOIN nusha n ON n.id = a.nusha_id
            WHERE a.durum IN ('bekliyor', 'hazir') {kosul} ORDER BY a.durum = 'hazir' DESC, a.id""",
        params,
    ):
        d = dict(r)
        d["durum_ad"] = AYIRTMA_DURUMLARI[d["durum"]]
        sonuc.append(d)
    return sonuc


# ---- Öğrenci / veli görünümü ----

def ogrenci_id_kullanici(conn: sqlite3.Connection, kullanici_id: int) -> int | None:
    r = conn.execute("SELECT id FROM ogrenci WHERE kullanici_id = ?", (kullanici_id,)).fetchone()
    return r["id"] if r else None


def kutuphanem(conn: sqlite3.Connection, ogrenci_id: int) -> dict:
    """Öğrencinin aktif ödünçleri (+ uyarı), son 20 geçmiş kaydı, açık ayırtmaları. Okurken süresi dolan ayırtmaları düşürür."""
    ayirtma_temizle(conn)
    hatirlat = bool(ayarlar(conn)["hatirlatma"])
    aktif, gecmis = [], []
    for r in conn.execute(f"{_ODUNC_SQL} WHERE o.ogrenci_id = ? ORDER BY o.verilis DESC", (ogrenci_id,)):
        d = _odunc_satiri(r)
        if d["iade"] is None:
            d["uyari"] = hatirlat and 0 <= d["kalan_gun"] <= HATIRLATMA_GUN
            aktif.append(d)
        elif len(gecmis) < 20:
            gecmis.append(d)
    aktif.sort(key=lambda x: x["son_tarih"])
    return {"aktif": aktif, "gecmis": gecmis, "ayirtmalar": ayirtmalar(conn, ogrenci_id), "hatirlatma": hatirlat}


# ---- Excel ----

_BASLIK_ESLE = {
    "isbn": "isbn", "demirbas": "demirbas", "demirbasno": "demirbas", "baskiyili": "baski_yili", "basimyili": "baski_yili",
    "baslik": "baslik", "kitapadi": "baslik", "eseradi": "baslik", "basimsayisi": "basim_sayisi", "baskisayisi": "basim_sayisi",
    "yayinevi": "yayinevi", "yazar": "yazar", "tur": "tur", "raf": "raf", "dolap": "raf",
}
_ASCII = str.maketrans("çğıöşü", "cgiosu")


def _baslik_anahtari(h) -> str:
    return re.sub(r"[^a-z]", "", metin.tr_kucuk(str(h or "")).translate(_ASCII))


def _hucre(c, alan: str) -> tuple[str, bool]:
    """(metin, sıfır_kaybı_şüphesi). Sayı olarak saklanmış demirbaşta '00000' biçimi varsa sıfırlar geri eklenir."""
    v = c.value
    if v is None:
        return "", False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if isinstance(v, float) and not v.is_integer():
            return str(v), False
        m = str(int(v))
        if alan == "demirbas":
            bicim = getattr(c, "number_format", "") or ""
            if re.fullmatch(r"0+", bicim):
                return m.zfill(len(bicim)), False
            return m, True
        return m, False
    return str(v).strip(), False


def ice_aktar(conn: sqlite3.Connection, veri: bytes) -> dict:
    """Excel'den toplu nüsha. Satır satır eklenir (her biri tek işlem); hatalı/tekrar satırlar atlanır ve raporlanır.
    Aynı dosya iki kez yüklenirse demirbaşlar zaten kayıtlı olduğu için ikinci yüklemede hiçbir şey eklenmez."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(veri), read_only=True, data_only=True)
    except Exception as e:  # openpyxl bozuk dosyada çeşitli istisnalar atar
        raise KutuphaneHatasi("Dosya okunamadı; .xlsx biçiminde bir Excel dosyası yükleyin.") from e
    satirlar = wb.active.iter_rows()
    ilk = next(satirlar, None)
    if ilk is None:
        raise KutuphaneHatasi("Dosya boş.")
    sutun = {}
    for i, c in enumerate(ilk):
        alan = _BASLIK_ESLE.get(_baslik_anahtari(c.value))
        if alan and alan not in sutun:
            sutun[alan] = i
    eksik = [a for a in ("demirbas", "baslik") if a not in sutun]
    if eksik:
        raise KutuphaneHatasi("Eksik sütun: " + ", ".join({"demirbas": "Demirbas", "baslik": "Baslik"}[a] for a in eksik))
    sonuc = {"eklenen": 0, "atlanan": [], "sifir_supheli": 0, "isbn_gecersiz": []}
    for no, satir in enumerate(satirlar, start=2):
        if no - 1 > AZAMI_SATIR:
            raise KutuphaneHatasi(f"En çok {AZAMI_SATIR} satır yüklenebilir.")
        alanlar, supheli = {}, False
        for alan, i in sutun.items():
            m, s = _hucre(satir[i], alan) if i < len(satir) else ("", False)
            alanlar[alan] = m
            supheli |= s
        if not any(alanlar.values()):
            continue
        try:  # gerçek envanterde yazım hatalı ISBN çok: satır ISBN'siz aktarılır, uyarı olarak listelenir
            isbn_normalize(alanlar.get("isbn"))
        except KutuphaneHatasi:
            sonuc["isbn_gecersiz"].append((no, alanlar["isbn"]))
            alanlar["isbn"] = None
        try:
            nusha_ekle(conn, **alanlar)
            sonuc["eklenen"] += 1
            sonuc["sifir_supheli"] += supheli
        except KutuphaneHatasi as e:
            sonuc["atlanan"].append((no, e.mesaj))
    return sonuc


def sablon_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ISBN", "Demirbas", "BaskiYili", "Baslik", "BasimSayisi", "Yayinevi", "Yazar", "Tur", "Raf"])
    ws.append(["9786052793978", "03244", 2025, "Bahadır : Sirius’un seçimi", "3.Basim", "Can Yayınları", "", "Roman", "A-3"])
    for kol in "AB":  # ISBN ve demirbaş METİN: Excel baştaki sıfırı silmesin
        for c in ws[kol]:
            c.number_format = "@"
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


# ---- Rapor ----

def rapor(conn: sqlite3.Connection) -> dict:
    """Sayılar ödünç işlemidir; okunduğu doğrulanmış kitap sayısı DEĞİLDİR."""
    bugun = zaman.simdi().date()
    nusha_say = Counter(r["durum"] for r in conn.execute("SELECT durum FROM nusha"))
    aktif = aktif_odunclar(conn)
    odunc = conn.execute(
        """SELECT o.verilis, o.ogrenci_id, g.ad_soyad, g.sinif, k.id AS kitap_id, k.baslik, k.yazar
           FROM odunc o JOIN ogrenci g ON g.id = o.ogrenci_id JOIN nusha n ON n.id = o.nusha_id JOIN kitap k ON k.id = n.kitap_id"""
    ).fetchall()
    gun_bas = (bugun - timedelta(days=29)).isoformat()
    gunluk = Counter(r["verilis"][:10] for r in odunc if r["verilis"][:10] >= gun_bas)
    aylik = Counter(r["verilis"][:7] for r in odunc)
    ogrenci = Counter((r["ad_soyad"], r["sinif"]) for r in odunc)
    kitap = Counter((r["kitap_id"], r["baslik"]) for r in odunc)
    yazar = Counter(r["yazar"] for r in odunc if r["yazar"])
    alinan = {r["kitap_id"] for r in odunc}
    return {
        "eser": conn.execute("SELECT COUNT(*) FROM kitap").fetchone()[0],
        "nusha": sum(nusha_say.values()),
        "hasarli": nusha_say["hasarli"],
        "kayip": nusha_say["kayip"],
        "oduncte": len(aktif),
        "geciken": sum(1 for x in aktif if x["gecikme_gun"] > 0),
        "rafta": sum(x["rafta"] or 0 for x in katalog(conn, limit=10**9)),
        "toplam_odunc": len(odunc),
        "gunluk": [((bugun - timedelta(days=i)).isoformat(), gunluk[(bugun - timedelta(days=i)).isoformat()]) for i in range(29, -1, -1)],
        "aylik": sorted(aylik.items())[-12:],
        "siniflar": sorted(Counter(r["sinif"] for r in odunc).items()),
        "ogrenciler": [(a, s, n) for (a, s), n in ogrenci.most_common(10)],
        "kitaplar": [(b, n) for (_, b), n in kitap.most_common(10)],
        "yazarlar": yazar.most_common(10),
        "hic_alinmamis": [dict(r) for r in conn.execute("SELECT id, baslik, yazar, isbn FROM kitap ORDER BY baslik") if r["id"] not in alinan],
    }


def rapor_xlsx(conn: sqlite3.Connection) -> bytes:
    r = rapor(conn)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Özet"
    for etiket, anahtar in (("Eser", "eser"), ("Fiziksel nüsha", "nusha"), ("Rafta", "rafta"), ("Ödünçte", "oduncte"),
                            ("Gecikmiş", "geciken"), ("Hasarlı", "hasarli"), ("Kayıp", "kayip"), ("Toplam ödünç işlemi", "toplam_odunc")):
        ws.append([etiket, r[anahtar]])
    ws.append(["Not", "Ödünç sayısı, okunduğu doğrulanmış kitap sayısı değildir."])

    def sayfa(ad, baslik, satirlar):
        s = wb.create_sheet(ad)
        s.append(baslik)
        for x in satirlar:
            s.append(list(x))
        return s

    s = sayfa("Nüshalar", ["Demirbas", "ISBN", "Baslik", "Yazar", "Yayinevi", "BaskiYili", "BasimSayisi", "Raf", "Durum", "Ödünçte"],
              [(n["demirbas"], n["isbn"] or "", n["baslik"], n["yazar"], n["yayinevi"], n["baski_yili"], n["basim_sayisi"],
                n["raf"], n["durum_ad"], "Evet" if n["oduncte"] else "") for n in nushalar(conn, "1", ())])
    for c in s["A"]:
        c.number_format = "@"
    sayfa("Ödünçteki", ["Demirbas", "Baslik", "Öğrenci", "Sınıf", "Veriliş", "Son tarih", "Gecikme (gün)"],
          [(x["demirbas"], x["baslik"], x["ad_soyad"], x["sinif"], x["verilis"], x["son_tarih"], x["gecikme_gun"]) for x in aktif_odunclar(conn)])
    sayfa("Aylık", ["Ay", "Ödünç"], r["aylik"])
    sayfa("Sınıflar", ["Sınıf", "Ödünç"], r["siniflar"])
    sayfa("Öğrenciler", ["Öğrenci", "Sınıf", "Ödünç"], r["ogrenciler"])
    sayfa("Popüler kitaplar", ["Başlık", "Ödünç"], r["kitaplar"])
    sayfa("Popüler yazarlar", ["Yazar", "Ödünç"], r["yazarlar"])
    sayfa("Hiç alınmamış", ["Başlık", "Yazar", "ISBN"], [(x["baslik"], x["yazar"], x["isbn"] or "") for x in r["hic_alinmamis"]])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def etiket_nushalari(conn: sqlite3.Connection, bas: str = "", bit: str = "", kitap_id: int | None = None) -> list[dict]:
    """Etiket basılacak nüshalar: eser, ya da demirbaş aralığı (sayısal demirbaşlarda sayıya göre, sıfırlar korunur)."""
    if kitap_id:
        return nushalar(conn, "k.id = ?", (kitap_id,))
    bas, bit = (bas or "").strip(), (bit or "").strip() or (bas or "").strip()
    if not bas:
        return []
    if bas.isdigit() and bit.isdigit():
        liste = [n for n in nushalar(conn, "1", ()) if n["demirbas"].isdigit() and int(bas) <= int(n["demirbas"]) <= int(bit)]
    else:
        liste = nushalar(conn, "n.demirbas BETWEEN ? AND ?", (bas, bit))
    return sorted(liste, key=lambda n: (len(n["demirbas"]), n["demirbas"]))[:600]
