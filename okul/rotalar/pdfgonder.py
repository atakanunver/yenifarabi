"""PDF gönder (öğretmen → sınıf), PDF'ten foto teslimli ödev ve öğrencinin foto yüklemesi."""

import sqlite3

import analitik
import dosyalar
import odevler
import push
import sinifpdf
import yetki
from deps import db_conn, istemci_ip, render, rol
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, RedirectResponse
from metin import tr_kucuk

from rotalar.belge_sinav import _oku
from rotalar.ogrenci import _kendisi
from rotalar.ogrenci import _odev as _ogrenci_odev
from rotalar.ogretmen import gorevler

router = APIRouter()
OGRETMEN = rol("ogretmen", "yonetici")
OGRETMEN_POST = rol("ogretmen", "yonetici", post=True)
OGRENCI = rol("ogrenci")
GORUNTULEYEN = rol("ogrenci", "ogretmen", "yonetici")


def _liste(request, conn, k, status=200, **ek):
    return render(
        request,
        "ogretmen/pdf.html",
        status,
        secenekler=gorevler(conn, k),
        pdfler=sinifpdf.ogretmen_pdfleri(conn, k),
        **ek,
    )


@router.get("/ogretmen/pdf")
def pdf_liste(request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)):
    return _liste(request, conn, k)


@router.post("/ogretmen/pdf")
async def pdf_yukle(
    request: Request,
    arka: BackgroundTasks,
    dosya: UploadFile,
    secim: str = Form(""),
    ders: str = Form(""),
    baslik: str = Form(""),
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    sinif, _, d = secim.partition("|")
    ders = tr_kucuk((d or ders).strip())
    try:
        pdf_id = sinifpdf.gonder(
            conn, k, sinif.strip(), ders, baslik,
            dosya.filename or "", await _oku(dosya, dosyalar.PLAN_AZAMI),
        )
    except PermissionError:
        raise HTTPException(404) from None
    except dosyalar.DosyaHatasi as e:
        return _liste(request, conn, k, 422, hata=str(e))
    analitik.istekten(request, "ogretmen_pdf_gonder", str(pdf_id))
    arka.add_task(push.pdf_bildir, sinif.strip(), k["id"])
    return RedirectResponse(f"/ogretmen/pdf/{pdf_id}/odev", status_code=303)


@router.post("/ogretmen/pdf/{pdf_id}/sil")
def pdf_sil(pdf_id: int, k=Depends(OGRETMEN_POST), conn: sqlite3.Connection = Depends(db_conn)):
    if not sinifpdf.pdf_sil(conn, k, pdf_id):
        raise HTTPException(404)
    return RedirectResponse("/ogretmen/pdf", status_code=303)


def _sahip_pdf(conn, k, pdf_id):
    p = sinifpdf.pdf_gorebilir(conn, k, pdf_id)
    if p is None or k["rol"] == "ogrenci":
        raise HTTPException(404)
    return p


@router.get("/ogretmen/pdf/{pdf_id}/odev")
def pdf_odev_formu(
    pdf_id: int, request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    return render(request, "ogretmen/pdf_odev.html", pdf=_sahip_pdf(conn, k, pdf_id))


@router.post("/ogretmen/pdf/{pdf_id}/odev")
def pdf_odev_ver(
    pdf_id: int,
    request: Request,
    arka: BackgroundTasks,
    baslik: str = Form(""),
    aciklama: str = Form(""),
    teslim: str = Form(""),
    sayfa_bas: str = Form(""),
    sayfa_bit: str = Form(""),
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    pdf = _sahip_pdf(conn, k, pdf_id)
    try:
        odev_id = sinifpdf.odev_ver(conn, k, pdf, baslik, aciklama, teslim, sayfa_bas, sayfa_bit)
    except (sinifpdf.PdfHatasi, odevler.OdevHatasi) as e:
        return render(request, "ogretmen/pdf_odev.html", 422, pdf=pdf, hata=str(e))
    analitik.istekten(request, "ogretmen_odev_olustur", str(odev_id))
    arka.add_task(push.odev_bildir, pdf["sinif"], k["id"])
    return RedirectResponse(f"/ogretmen/odev/{odev_id}", status_code=303)


@router.get("/ogrenci/dosyalar")
def dosyalar_listesi(request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)):
    o = _kendisi(conn, k)
    return render(request, "ogrenci/dosyalar.html", pdfler=sinifpdf.sinif_pdfleri(conn, o["sinif"]))


@router.get("/pdf/{pdf_id}")
def pdf_goster(
    pdf_id: int, request: Request, k=Depends(GORUNTULEYEN), conn: sqlite3.Connection = Depends(db_conn)
):
    p = sinifpdf.pdf_gorebilir(conn, k, pdf_id)
    if p is None:
        raise HTTPException(404)
    yol = dosyalar.yol("pdf", p["depo_adi"])
    if not yol.exists():
        raise HTTPException(404)
    if k["rol"] == "yonetici" and k["id"] != p["ogretmen_id"]:
        yetki.erisim_kaydet(conn, k, f"sinif_pdf:{pdf_id}", None, istemci_ip(request))
    return FileResponse(
        yol,
        media_type=dosyalar.MIME["pdf"],
        content_disposition_type="inline",
        filename=p["dosya_adi"],
        headers={"Cache-Control": "private, no-store"},
    )


@router.post("/ogrenci/odev/{odev_id}/foto")
async def odev_foto(
    odev_id: int,
    request: Request,
    dosya: UploadFile,
    k=Depends(rol("ogrenci", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    o = _kendisi(conn, k)
    odev = _ogrenci_odev(conn, o, odev_id)
    try:
        sinifpdf.foto_yukle(conn, odev, o["id"], await _oku(dosya, dosyalar.FOTO_AZAMI))
    except (dosyalar.DosyaHatasi, sinifpdf.PdfHatasi, odevler.OdevHatasi) as e:
        raise HTTPException(400, str(e)) from e
    analitik.istekten(request, "odev_foto_yukle", str(odev_id))
    return RedirectResponse(f"/ogrenci/odev/{odev_id}", status_code=303)


@router.get("/odev-foto/{odev_id}/{ogrenci_id}")
def odev_foto_goster(
    odev_id: int,
    ogrenci_id: int,
    request: Request,
    k=Depends(GORUNTULEYEN),
    conn: sqlite3.Connection = Depends(db_conn),
):
    f = sinifpdf.foto_gorebilir(conn, k, odev_id, ogrenci_id)
    if f is None:
        raise HTTPException(404)
    yol = dosyalar.yol("odev_foto", f["depo_adi"])
    if not yol.exists():
        raise HTTPException(404)
    if k["rol"] != "ogrenci":
        yetki.erisim_kaydet(conn, k, f"odev_foto:{odev_id}:{ogrenci_id}", None, istemci_ip(request))
    return FileResponse(
        yol, media_type=dosyalar.MIME[f["tur"]], headers={"Cache-Control": "private, no-store"}
    )
