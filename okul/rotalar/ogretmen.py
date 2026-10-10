"""Öğretmen sayfaları (yönetici de kullanabilir): sınıflar, ödev/test oluşturma, sonuçlar, duyuru."""

import sqlite3

import duyurular
import odevler
import yetki
from deps import db_conn, istemci_ip, render, rol
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from kaynaklar import KaynakHatasi, kazanim, program
from metin import sinif_seviyesi, tr_kucuk

router = APIRouter(prefix="/ogretmen")
OGRETMEN = rol("ogretmen", "yonetici")
OGRETMEN_POST = rol("ogretmen", "yonetici", post=True)


def gorevler(conn: sqlite3.Connection, k: sqlite3.Row) -> list[tuple[str, str]]:
    if k["rol"] == "yonetici":
        return [
            (r[0], "")
            for r in conn.execute("SELECT DISTINCT sinif FROM ogrenci ORDER BY sinif")
        ]
    return yetki.ogretmen_gorevleri(conn, k["id"])


def _odev(conn: sqlite3.Connection, k: sqlite3.Row, odev_id: int) -> sqlite3.Row:
    odev = odevler.odev_getir(conn, odev_id)
    if odev is None or (k["rol"] != "yonetici" and odev["ogretmen_id"] != k["id"]):
        raise HTTPException(404)
    return odev


@router.get("")
def ana(
    request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    return render(
        request,
        "ogretmen/ana.html",
        gorevler=gorevler(conn, k),
        odevler=odevler.ogretmen_odevleri(conn, k)[:10],
    )


@router.get("/sinif/{sinif}")
def sinif(
    sinif: str,
    request: Request,
    k=Depends(OGRETMEN),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if not yetki.sinif_yetkili(conn, k, sinif):
        raise HTTPException(404)
    yetki.erisim_kaydet(conn, k, f"sinif_listesi:{sinif}", None, istemci_ip(request))
    ogrenciler = conn.execute(
        "SELECT o.*, (SELECT count(*) FROM veli_ogrenci v WHERE v.ogrenci_id = o.id) AS veli_sayisi"
        " FROM ogrenci o WHERE sinif = ? ORDER BY okul_no",
        (sinif,),
    ).fetchall()
    return render(request, "ogretmen/sinif.html", sinif=sinif, ogrenciler=ogrenciler)


@router.get("/odev/yeni")
def odev_formu(
    request: Request,
    sinif: str = "",
    ders: str = "",
    tur: str = "klasik",
    havuz_ders: str = "",
    k=Depends(OGRETMEN),
    conn: sqlite3.Connection = Depends(db_conn),
):
    secenekler = gorevler(conn, k)
    if not sinif and secenekler:
        sinif, ders = secenekler[0]
    if sinif and ders and not yetki.sinif_ders_yetkili(conn, k, sinif, ders):
        raise HTTPException(404)
    havuz_dersleri, havuz, havuz_hata = [], [], False
    if tur == "test" and sinif:
        try:
            havuz_dersleri = kazanim.havuz_dersleri(sinif_seviyesi(sinif))
            if havuz_ders:
                havuz = kazanim.havuz_sorulari(sinif_seviyesi(sinif), havuz_ders)
        except KaynakHatasi:
            havuz_hata = True
    return render(
        request,
        "ogretmen/odev_yeni.html",
        secenekler=secenekler,
        sinif=sinif,
        ders=ders,
        tur=tur,
        havuz_ders=havuz_ders,
        havuz_dersleri=havuz_dersleri,
        havuz=havuz,
        havuz_hata=havuz_hata,
        soru_sayisi=5,
    )


@router.post("/odev/yeni")
async def odev_olustur(
    request: Request,
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    form = await request.form()
    sinif = str(form.get("sinif", "")).strip()
    ders = tr_kucuk(str(form.get("ders", "")).strip())
    tur = str(form.get("tur", "klasik"))
    if not sinif or not ders or not yetki.sinif_ders_yetkili(conn, k, sinif, ders):
        raise HTTPException(404)
    try:
        havuz_idler = [int(x) for x in form.getlist("havuz") if str(x).isdigit()]
        havuz = kazanim.havuz_sorulari_getir(havuz_idler) if tur == "test" else []
        sorular = (
            odevler.form_sorulari({a: str(v) for a, v in form.items()}, havuz)
            if tur == "test"
            else []
        )
        odev_id = odevler.odev_olustur(
            conn,
            k["id"],
            sinif,
            ders,
            tur,
            str(form.get("baslik", "")),
            str(form.get("aciklama", "")),
            str(form.get("teslim", "")),
            sorular,
        )
    except (odevler.OdevHatasi, KaynakHatasi) as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse(f"/ogretmen/odev/{odev_id}", status_code=303)


@router.get("/odev/{odev_id}")
def odev_sonuc(
    odev_id: int,
    request: Request,
    k=Depends(OGRETMEN),
    conn: sqlite3.Connection = Depends(db_conn),
):
    odev = _odev(conn, k, odev_id)
    yetki.erisim_kaydet(conn, k, f"odev_sonuc:{odev_id}", None, istemci_ip(request))
    return render(
        request,
        "ogretmen/odev_sonuc.html",
        odev=odev,
        tablo=odevler.sonuc_tablosu(conn, odev),
        sorular=odevler.sorular(conn, odev_id) if odev["tur"] == "test" else [],
    )


@router.post("/odev/{odev_id}/sil")
def odev_sil(
    odev_id: int, k=Depends(OGRETMEN_POST), conn: sqlite3.Connection = Depends(db_conn)
):
    _odev(conn, k, odev_id)
    conn.execute("DELETE FROM odev WHERE id = ?", (odev_id,))
    conn.commit()
    return RedirectResponse("/ogretmen", status_code=303)


@router.get("/duyuru")
def duyuru_formu(
    request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    siniflar = yetki.kullanici_siniflari(conn, k)
    if siniflar is None:
        siniflar = [
            r[0]
            for r in conn.execute("SELECT DISTINCT sinif FROM ogrenci ORDER BY sinif")
        ]
    return render(
        request,
        "duyuru_yaz.html",
        siniflar=siniflar,
        duyurular=duyurular.gorunur_duyurular(conn, k, 30),
    )


@router.post("/duyuru")
def duyuru_ekle(
    request: Request,
    baslik: str = Form(""),
    metin: str = Form(""),
    hedef_tur: str = Form("sinif"),
    hedef: str = Form(""),
    bitis: str = Form(""),
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    hedef_deger = hedef or None if hedef_tur != "okul" else None
    if not baslik.strip() or not metin.strip():
        raise HTTPException(400, "Başlık ve metin boş olamaz.")
    if not duyurular.ekleyebilir_mi(conn, k, hedef_tur, hedef_deger):
        raise HTTPException(404)
    bitis_str = f"{bitis} 23:59:59" if bitis else None
    duyurular.duyuru_ekle(
        conn, k["id"], baslik, metin, hedef_tur, hedef_deger, bitis_str
    )
    return RedirectResponse("/duyurular", status_code=303)


@router.post("/duyuru/{duyuru_id}/sil")
def duyuru_sil(
    duyuru_id: int,
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if not duyurular.sil(conn, k, duyuru_id):
        raise HTTPException(404)
    return RedirectResponse("/duyurular", status_code=303)


@router.get("/program")
def ders_programi(
    request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    try:
        haftalik = program.ogretmen_haftalik(yetki.ogretmen_gorevleri(conn, k["id"]))
    except KaynakHatasi:
        haftalik = None
    return render(request, "ogretmen/program.html", program=haftalik)
