"""Profil (vesikalık), yıllık plan ve sınav takvimi sayfaları."""

import sqlite3

import belgeler
import dosyalar
import sinavlar
import yetki
import zaman
from deps import db_conn, istemci_ip, mevcut_kullanici, render, rol
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from rotalar.ogretmen import gorevler as ogretmen_gorevleri
from rotalar.veli import _cocuk

router = APIRouter()
FOTOLU = rol("ogrenci", "ogretmen", "yonetici")
OGRETMEN = rol("ogretmen", "yonetici")
OGRETMEN_POST = rol("ogretmen", "yonetici", post=True)


async def _oku(dosya: UploadFile, azami: int) -> bytes:
    veri = await dosya.read(
        azami + 1
    )  # sınırın bir bayt fazlası: büyük dosyayı belleğe almadan yakala
    await dosya.close()
    return veri


def _bugun() -> str:
    return zaman.simdi().strftime("%Y-%m-%d")


# --- profil / vesikalık ---


@router.get("/profil")
def profil(request: Request, k=Depends(FOTOLU)):
    return render(request, "profil.html")


@router.post("/profil/foto")
async def foto_yukle(
    request: Request,
    foto: UploadFile,
    k=Depends(rol("ogrenci", "ogretmen", "yonetici", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    try:
        belgeler.foto_degistir(conn, k, await _oku(foto, dosyalar.FOTO_AZAMI))
    except dosyalar.DosyaHatasi as e:
        return render(request, "profil.html", 422, hata=str(e))
    return RedirectResponse("/profil", status_code=303)


@router.post("/profil/foto/sil")
def foto_kaldir(
    k=Depends(rol("ogrenci", "ogretmen", "yonetici", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    belgeler.foto_sil(conn, k)
    return RedirectResponse("/profil", status_code=303)


@router.get("/foto/{kullanici_id}")
def foto(
    kullanici_id: int,
    k=Depends(mevcut_kullanici),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if not belgeler.foto_gorebilir(conn, k, kullanici_id):
        raise HTTPException(404)
    satir = conn.execute(
        "SELECT foto FROM kullanici WHERE id = ?", (kullanici_id,)
    ).fetchone()
    if not satir or not satir["foto"]:
        raise HTTPException(404)
    yol = dosyalar.yol("foto", satir["foto"])
    if not yol.exists():
        raise HTTPException(404)
    tur = satir["foto"].rsplit(".", 1)[-1]
    return FileResponse(
        yol,
        media_type=dosyalar.MIME[tur],
        headers={"Cache-Control": "private, max-age=300"},
    )


# --- yıllık plan ---


@router.get("/ogretmen/planlar")
def planlarim(
    request: Request,
    k=Depends(rol("ogretmen")),
    conn: sqlite3.Connection = Depends(db_conn),
):
    return render(
        request,
        "ogretmen/planlar.html",
        satirlar=belgeler.ogretmen_planlari(conn, k["id"]),
    )


@router.post("/ogretmen/plan")
async def plan_yukle(
    request: Request,
    dosya: UploadFile,
    sinif: str = Form(""),
    ders: str = Form(""),
    k=Depends(rol("ogretmen", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    try:
        belgeler.plan_yukle(
            conn,
            k,
            sinif,
            ders,
            dosya.filename or "",
            await _oku(dosya, dosyalar.PLAN_AZAMI),
        )
    except PermissionError:
        raise HTTPException(404) from None
    except dosyalar.DosyaHatasi as e:
        return render(
            request,
            "ogretmen/planlar.html",
            422,
            satirlar=belgeler.ogretmen_planlari(conn, k["id"]),
            hata=str(e),
        )
    return RedirectResponse("/ogretmen/planlar", status_code=303)


@router.post("/ogretmen/plan/{plan_id}/sil")
def plan_sil(
    plan_id: int, k=Depends(OGRETMEN_POST), conn: sqlite3.Connection = Depends(db_conn)
):
    if not belgeler.plan_sil(conn, k, plan_id):
        raise HTTPException(404)
    return RedirectResponse(
        "/yonetici/planlar" if k["rol"] == "yonetici" else "/ogretmen/planlar",
        status_code=303,
    )


@router.get("/plan/{plan_id}")
def plan_indir(
    plan_id: int,
    request: Request,
    k=Depends(OGRETMEN),
    conn: sqlite3.Connection = Depends(db_conn),
):
    p = belgeler.plan_getir(conn, k, plan_id)
    if p is None:
        raise HTTPException(404)
    yol = dosyalar.yol("plan", p["depo_adi"])
    if not yol.exists():
        raise HTTPException(404)
    if k["id"] != p["ogretmen_id"]:
        yetki.erisim_kaydet(
            conn, k, f"yillik_plan:{plan_id}", None, istemci_ip(request)
        )
    return FileResponse(
        yol,
        media_type=dosyalar.MIME[p["tur"]],
        filename=p["dosya_adi"],
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/yonetici/planlar")
def tum_planlar(
    request: Request,
    k=Depends(rol("yonetici")),
    conn: sqlite3.Connection = Depends(db_conn),
):
    satirlar = belgeler.tum_planlar(conn)
    return render(
        request,
        "yonetici/planlar.html",
        satirlar=satirlar,
        eksik=sum(1 for s in satirlar if s["plan_id"] is None),
    )


# --- sınavlar (öğretmen/yönetici yönetir) ---


def _sinav_sayfasi(request, conn, k, durum=200, hata=None):
    return render(
        request,
        "ogretmen/sinavlar.html",
        durum,
        hata=hata,
        gorevler=ogretmen_gorevleri(conn, k),
        sinavlar=sinavlar.ogretmen_sinavlari(conn, k, _bugun()),
        duzeyler=sinavlar.DUZEYLER,
        bugun=_bugun(),
        duzenleyebilir=lambda s: sinavlar.duzenleyebilir(k, s),
        kalan=sinavlar.kalan_gun,
    )


@router.get("/ogretmen/sinavlar")
def sinav_listesi(
    request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    return _sinav_sayfasi(request, conn, k)


@router.post("/ogretmen/sinav/yazili")
def yazili_ekle(
    request: Request,
    gorev: str = Form(""),
    ders_elle: str = Form(""),
    tarih: str = Form(""),
    ders_no: str = Form(""),
    aciklama: str = Form(""),
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    sinif, _, ders = gorev.partition("|")
    try:
        sinavlar.yazili_ekle(
            conn, k, sinif, ders or ders_elle, tarih, ders_no, aciklama
        )
    except sinavlar.YetkiYok:
        raise HTTPException(404) from None
    except sinavlar.SinavHatasi as e:
        return _sinav_sayfasi(request, conn, k, 422, str(e))
    return RedirectResponse("/ogretmen/sinavlar", status_code=303)


@router.post("/ogretmen/sinav/deneme")
async def deneme_ekle(
    request: Request,
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    form = await request.form()
    try:
        sinavlar.deneme_ekle(
            conn,
            k,
            str(form.get("baslik", "")),
            str(form.get("tarih", "")),
            form.getlist("duzey"),
            str(form.get("aciklama", "")),
        )
    except sinavlar.SinavHatasi as e:
        return _sinav_sayfasi(request, conn, k, 422, str(e))
    return RedirectResponse("/ogretmen/sinavlar", status_code=303)


@router.get("/ogretmen/sinav/{sinav_id}")
def sinav_duzenle_formu(
    sinav_id: int,
    request: Request,
    k=Depends(OGRETMEN),
    conn: sqlite3.Connection = Depends(db_conn),
):
    s = sinavlar.getir(conn, sinav_id)
    if not sinavlar.duzenleyebilir(k, s):
        raise HTTPException(404)
    return render(
        request, "ogretmen/sinav_duzenle.html", s=s, duzeyler=sinavlar.DUZEYLER
    )


@router.post("/ogretmen/sinav/{sinav_id}")
async def sinav_guncelle(
    sinav_id: int,
    request: Request,
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    form = await request.form()
    try:
        sinavlar.guncelle(
            conn,
            k,
            sinav_id,
            str(form.get("tarih", "")),
            form.get("ders_no"),
            str(form.get("aciklama", "")),
            str(form.get("baslik", "")),
            form.getlist("duzey"),
        )
    except sinavlar.YetkiYok:
        raise HTTPException(404) from None
    except sinavlar.SinavHatasi as e:
        return render(
            request,
            "ogretmen/sinav_duzenle.html",
            422,
            s=sinavlar.getir(conn, sinav_id),
            duzeyler=sinavlar.DUZEYLER,
            hata=str(e),
        )
    return RedirectResponse("/ogretmen/sinavlar", status_code=303)


@router.post("/ogretmen/sinav/{sinav_id}/sil")
def sinav_sil(
    sinav_id: int, k=Depends(OGRETMEN_POST), conn: sqlite3.Connection = Depends(db_conn)
):
    if not sinavlar.sil(conn, k, sinav_id):
        raise HTTPException(404)
    return RedirectResponse("/ogretmen/sinavlar", status_code=303)


# --- sınav takvimi (öğrenci / veli görür) ---


@router.get("/ogrenci/sinavlar")
def ogrenci_sinavlari(
    request: Request,
    k=Depends(rol("ogrenci")),
    conn: sqlite3.Connection = Depends(db_conn),
):
    o = yetki.ogrenci_kaydi(conn, k["id"])
    if o is None:
        raise HTTPException(404)
    return render(
        request,
        "sinavlar.html",
        liste=sinavlar.sinif_sinavlari(conn, o["sinif"], _bugun()),
        kalan=sinavlar.kalan_gun,
        baslik_metni="Sınavlarım",
    )


@router.get("/veli/sinavlar")
def veli_sinavlari(
    request: Request,
    ogr: int | None = None,
    k=Depends(rol("veli")),
    conn: sqlite3.Connection = Depends(db_conn),
):
    cocuklar, c = _cocuk(request, conn, k, ogr, "veli_sinavlar")
    if c is None:
        raise HTTPException(404)
    return render(
        request,
        "sinavlar.html",
        cocuklar=cocuklar,
        cocuk=c,
        liste=sinavlar.sinif_sinavlari(conn, c["sinif"], _bugun()),
        kalan=sinavlar.kalan_gun,
        baslik_metni=f"{c['ad_soyad']} — sınavlar",
    )
