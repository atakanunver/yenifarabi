"""Öğretmen liderlik ekranları: sınıfın tam Arena tablosu, sınıflar arası kıyas, haftalık ödül özeti.

Yetkisiz sınıf = 404. TAM öğrenci adları yalnızca kendi sınıfının öğretmenine (ve yöneticiye) gösterilir; sınıflar arası
kıyasta yalnızca sınıf toplamları vardır. Ödül kazananı kiosk'ta zaten herkese açıktır. Adlı görüntüleme erişim kaydına yazılır.
2026-10-15: öğrencilerin kendi ekranında gördüğü okul geneli liderlikler (Soru Maratonu + Bilgi Arenası) öğretmene de açıldı;
bunlar öğrenciyle AYNI veridir (kısa ad "Ayşe K." + sınıf), yani öğretmene öğrencinin görmediği bir şey eklenmez.
"""

import sqlite3

import maraton
import oduller
import yetki
from deps import db_conn, istemci_ip, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request

router = APIRouter(prefix="/ogretmen/liderlik")
OGRETMEN = rol("ogretmen", "yonetici")
MARATON_ILK = 20  # okul geneli Maraton tablosunda gösterilen öğrenci sayısı (öğrenci ekranı da sınırlı)


def benim_siniflarim(conn: sqlite3.Connection, k: sqlite3.Row) -> list[str]:
    if k["rol"] == "yonetici":
        return [r[0] for r in conn.execute("SELECT DISTINCT sinif FROM ogrenci ORDER BY sinif")]
    return yetki.ogretmen_siniflari(conn, k["id"])


def mini_pano(conn: sqlite3.Connection, k: sqlite3.Row) -> list[dict]:
    """Ana sayfa için: öğretmenin her sınıfına bu haftanın tek satırlık özeti."""
    benim = benim_siniflarim(conn, k)
    if not benim:
        return []
    ozet = {s["sinif"]: s for s in oduller.sinif_ozetleri(conn, oduller.hafta_basi(), set(benim))}
    return [ozet[s] for s in benim if s in ozet]


@router.get("")
def genel(
    request: Request, donem: str = "hafta", k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    hb = oduller.hafta_basi()
    benim = benim_siniflarim(conn, k)
    onceki = oduller.onceki_hafta(hb)
    donem = "tum" if donem == "tum" else "hafta"
    maraton_tum = maraton.liderlik(conn)  # öğrenci ekranıyla aynı: bu hafta, her öğrencinin en iyi 3 maratonu
    return render(
        request, "ogretmen/liderlik.html", hafta_basi=hb, benim=set(benim), benim_liste=benim,
        donem=donem, arena=oduller.liderlik(conn, hb if donem == "hafta" else None), arena_ilk=oduller.LIDER_ILK,
        maraton_ilk=maraton_tum[:MARATON_ILK], maraton_toplam=len(maraton_tum), maraton_en_iyi=maraton.EN_IYI,
        maraton_siniflarim=[d for d in maraton_tum if d["sinif"] in set(benim)],
        siniflar=oduller.sinif_ozetleri(conn, hb), gecici=oduller.siralama(conn, hb), kategoriler=oduller.KATEGORILER,
        onceki_hafta=onceki, onceki=oduller.kayitli(conn, onceki),
        min_etkinlik=oduller.MIN_ETKINLIK, min_gun=oduller.MIN_GUN, min_katilan=oduller.MIN_KATILAN,
    )


@router.get("/{sinif}")
def sinif_tablosu(
    sinif: str, request: Request, donem: str = "hafta", k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    if not yetki.sinif_yetkili(conn, k, sinif):
        raise HTTPException(404)
    yetki.erisim_kaydet(conn, k, f"sinif_liderlik:{sinif}", None, istemci_ip(request))
    donem = "tum" if donem == "tum" else "hafta"
    hb = oduller.hafta_basi() if donem == "hafta" else None
    return render(
        request, "ogretmen/liderlik_sinif.html", sinif=sinif, donem=donem, hafta_basi=hb,
        t=oduller.sinif_liderlik(conn, sinif, hb),
        yukselenler=oduller.yukselenler(conn, sinif, hb) if hb else [],
    )
