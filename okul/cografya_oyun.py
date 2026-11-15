"""Coğrafya oyunu: sunucuda süre, puan ve XP."""

from datetime import datetime

import arena
import oduller
import zaman
from metin import kisa_ad

MODLAR = {"harita-bul", "ulke-adi", "baskent", "bayrak"}
YANITLAR = {"secmeli", "yazim"}
BOLGELER = {"dunya", "avrupa", "asya", "afrika", "kuzey-amerika", "guney-amerika", "okyanusya"}
SORU_EN_AZ, SORU_EN_COK = 5, 250
GUNLUK_BASLATMA = 30
SORU_BASI_EN_AZ_SN, ACIK_EN_COK_SN = 1.5, 7200
XP_EN_AZ_DOGRU, OYUN_XP_EN_COK, GUNLUK_XP_EN_COK = 5, 10, 20


class GunlukSinir(Exception):
    pass


def baslat(conn, kid, mod, yanit, bolge, soru_sayisi):
    if (mod not in MODLAR or yanit not in YANITLAR or bolge not in BOLGELER
            or type(soru_sayisi) is not int or not SORU_EN_AZ <= soru_sayisi <= SORU_EN_COK):
        raise ValueError("Geçersiz oyun ayarları")
    simdi = zaman.simdi_str()
    cur = conn.execute(
        "INSERT INTO cografya_oyun (kullanici_id, mod, yanit, bolge, soru_sayisi, baslama) "
        "SELECT ?, ?, ?, ?, ?, ? WHERE (SELECT COUNT(*) FROM cografya_oyun "
        "WHERE kullanici_id = ? AND baslama >= ? AND baslama < ?) < ?",
        (kid, mod, yanit, bolge, soru_sayisi, simdi, kid, simdi[:10] + ' 00:00:00',
         simdi[:10] + ' 23:59:59.999999', GUNLUK_BASLATMA),
    )
    if not cur.rowcount:
        raise GunlukSinir("Günlük oyun sınırına ulaşıldı")
    return cur.lastrowid


def bitir(conn, kid, oyun_id, dogru, yanlis, duzey_uygun):
    # Yazma kilidi önce alınır; hem çift bitirme hem günlük XP hesabı korunur.
    cur = conn.execute("UPDATE cografya_oyun SET bitis = ? WHERE id = ? AND kullanici_id = ? AND bitis IS NULL",
                       (zaman.simdi_str(), oyun_id, kid))
    if not cur.rowcount:
        if conn.execute("SELECT 1 FROM cografya_oyun WHERE id = ? AND kullanici_id = ?", (oyun_id, kid)).fetchone():
            raise ValueError("Oyun zaten bitirildi")
        return None
    oyun = conn.execute("SELECT * FROM cografya_oyun WHERE id = ?", (oyun_id,)).fetchone()
    sure = (zaman.simdi() - datetime.strptime(oyun["baslama"], zaman.BICIM)).total_seconds()  # noqa: DTZ007
    if (type(dogru) is not int or type(yanlis) is not int or dogru < 0 or yanlis < 0
            or dogru + yanlis > oyun["soru_sayisi"] or sure < SORU_BASI_EN_AZ_SN * (dogru + yanlis)
            or sure < 0 or sure > ACIK_EN_COK_SN):
        raise ValueError("Geçersiz oyun sonucu")
    toplam = dogru + yanlis
    puan = max(0, 10 * dogru - 3 * yanlis) + (2 * dogru if toplam and sure / toplam <= 5 else 0)
    conn.execute("UPDATE cografya_oyun SET dogru = ?, yanlis = ?, sure_sn = ?, puan = ? WHERE id = ?",
                 (dogru, yanlis, int(sure), puan, oyun_id))
    xp = 0
    if duzey_uygun and dogru >= XP_EN_AZ_DOGRU:
        gunluk = conn.execute("SELECT COALESCE(SUM(miktar), 0) FROM bilgi_xp "
                              "WHERE kullanici_id = ? AND kaynak = 'cografya' AND gun = ?",
                              (kid, zaman.simdi_str()[:10])).fetchone()[0]
        xp = max(0, min(dogru // 2, OYUN_XP_EN_COK, GUNLUK_XP_EN_COK - gunluk))
        if xp:
            arena.xp_ver(conn, kid, "cografya", f"g{oyun_id}", xp)
    return {"puan": puan, "sure_sn": int(sure), "xp": xp, "kaydedildi": True}


def liderlik(conn, kid, mod, yanit, bolge, donem, kapsam, sinif):
    if mod not in MODLAR or yanit not in YANITLAR or bolge not in BOLGELER or donem not in {"hafta", "genel"} or kapsam not in {"sinif", "okul"}:
        raise ValueError("Geçersiz liderlik filtresi")
    rows = conn.execute("""
        SELECT g.kullanici_id, o.ad_soyad, o.sinif, g.puan, g.sure_sn
        FROM cografya_oyun g JOIN ogrenci o ON o.kullanici_id = g.kullanici_id
        WHERE g.mod = ? AND g.yanit = ? AND g.bolge = ? AND g.puan IS NOT NULL
          AND (? = 'genel' OR g.bitis >= ?) AND (? = 'okul' OR o.sinif = ?)
        ORDER BY g.puan DESC, g.sure_sn ASC, g.id ASC
    """, (mod, yanit, bolge, donem, oduller.hafta_basi() + " 00:00:00", kapsam, sinif)).fetchall()
    en_iyi = {}
    for r in rows:
        if r["kullanici_id"] not in en_iyi:
            en_iyi[r["kullanici_id"]] = r
    sirali = sorted(en_iyi.values(), key=lambda r: (-r["puan"], r["sure_sn"], r["ad_soyad"], r["kullanici_id"]))
    liste = []
    onceki, sira = None, 0
    for i, r in enumerate(sirali, 1):
        deger = (r["puan"], r["sure_sn"])
        if deger != onceki:
            sira, onceki = i, deger
        liste.append({"sira": sira, "ad": kisa_ad(r["ad_soyad"]), "sinif": r["sinif"],
                      "puan": r["puan"], "sure_sn": r["sure_sn"], "ben": r["kullanici_id"] == kid})
    return {"liste": liste[:oduller.LIDER_ILK], "ben": next((r for r in liste if r["ben"]), None)}
