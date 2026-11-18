"""PDF gönder (öğretmen → sınıf), PDF'ten foto teslimli ödev ve öğrencinin foto yüklemesi."""

import sqlite3

import analitik
import dosyalar
import odevler
import inceleme
import push
import sinifpdf
import soru_katki
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
from metin import sinif_seviyesi, tr_kucuk

from rotalar.belge_sinav import _oku
from rotalar.ogrenci import _kendisi
from rotalar.ogrenci import _odev as _ogrenci_odev
from rotalar.ogretmen import gorevler

router = APIRouter()
OGRETMEN = rol("ogretmen", "yonetici")
OGRETMEN_POST = rol("ogretmen", "yonetici", post=True)
OGRENCI = rol("ogrenci")
GORUNTULEYEN = rol("ogrenci", "ogretmen", "yonetici")


# ?havuz= kodları → kullanıcıya gösterilen metin (URL'den serbest metin yansıtılmaz)
HAVUZ_NOTLARI = {
    "sirada": "PDF sınıfa gönderildi ve sorular soru havuzu kuyruğuna alındı; birkaç dakika içinde işlenir.",
    "onaysiz": "PDF sınıfa gönderildi; ancak izin onayı işaretlenmediği için sorular havuza gönderilmedi.",
    "uygunsuz": "PDF sınıfa gönderildi; bu sınıf/ders için soru havuzu yok, sorular havuza gönderilmedi.",
    "cevap": "PDF sınıfa gönderildi; cevap anahtarı okunamadığı için sorular havuza gönderilmedi. "
    "Soru havuzuna katkı sayfasından yeniden deneyebilirsiniz.",
    "hata": "PDF sınıfa gönderildi; sorular havuza gönderilemedi. Soru havuzuna katkı sayfasından yeniden deneyebilirsiniz.",
}


def _havuz_cifti(conn, k, sinif: str, ders: str) -> tuple[int, str] | None:
    """Sınıf + ders → (seviye, havuz kodu); havuzda karşılığı yoksa (12. sınıf, eşleşmeyen ders) None."""
    try:
        sev = sinif_seviyesi(sinif)
    except ValueError:
        return None
    kod = inceleme.havuz_kodu(ders)
    if kod and (sev, kod) in soru_katki.secenekler(conn, k):
        return sev, kod
    return None


def _havuz_uygun(conn, k, secenekler) -> list[str]:
    """Havuz katkısı yapılabilecek "sınıf|ders" seçimleri (yöneticide ders serbest metin: sunucu karar verir)."""
    if k["rol"] == "yonetici":
        return []
    return [f"{s}|{d}" for s, d in secenekler if _havuz_cifti(conn, k, s, d)]


def _liste(request, conn, k, status=200, **ek):
    secenekler = gorevler(conn, k)
    return render(
        request,
        "ogretmen/pdf.html",
        status,
        secenekler=secenekler,
        havuz_uygun=_havuz_uygun(conn, k, secenekler),
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
    soru_uret: str = Form(""),
    kvkk: str = Form(""),
    soru_bas: str = Form(""),
    soru_bit: str = Form(""),
    havuza: str = Form(""),
    havuz_onay: str = Form(""),
    cevap: str = Form(""),
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if soru_uret:
        raise HTTPException(410, "PDF'ten otomatik soru üretimi kaldırıldı; soru arşivi kullanılıyor.")
    sinif, _, d = secim.partition("|")
    ders = tr_kucuk((d or ders).strip())
    veri = await _oku(dosya, dosyalar.PLAN_AZAMI)
    try:
        pdf_id = sinifpdf.gonder(conn, k, sinif.strip(), ders, baslik, dosya.filename or "", veri)
    except PermissionError:
        raise HTTPException(404) from None
    except dosyalar.DosyaHatasi as e:
        return _liste(request, conn, k, 422, hata=str(e))
    analitik.istekten(request, "ogretmen_pdf_gonder", str(pdf_id))
    arka.add_task(push.pdf_bildir, sinif.strip(), k["id"])
    yol = f"/ogretmen/pdf/{pdf_id}/odev"
    if havuza == "evet":
        kod = _havuza_gonder(request, conn, k, (sinif.strip(), ders), (baslik, dosya.filename or ""), veri, cevap, havuz_onay)
        yol += f"?havuz={kod}"
    return RedirectResponse(yol, status_code=303)


def _havuza_gonder(request, conn, k, sinif_ders, ad, veri, cevap, onay) -> str:
    """PDF zaten gönderildi; havuz katkısı başarısız olsa da akış bozulmaz. HAVUZ_NOTLARI kodu döner."""
    cift = _havuz_cifti(conn, k, *sinif_ders)
    if cift is None:
        return "uygunsuz"
    if not onay:
        return "onaysiz"
    try:
        kid = soru_katki.gonder(conn, k, cift[0], cift[1], ad[0], ad[1], veri, cevap)
    except soru_katki.KatkiHatasi:
        return "cevap"
    except (dosyalar.DosyaHatasi, PermissionError):
        return "hata"
    analitik.istekten(request, "ogretmen_soru_katki", str(kid))
    return "sirada"


@router.post("/ogretmen/pdf/{pdf_id}/soru")
def pdf_soru_iste(
    pdf_id: int,
    request: Request,
    kvkk: str = Form(""),
    soru_bas: str = Form(""),
    soru_bit: str = Form(""),
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    raise HTTPException(410, "PDF'ten otomatik soru üretimi kaldırıldı; soru arşivi kullanılıyor.")


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
    return render(
        request,
        "ogretmen/pdf_odev.html",
        pdf=_sahip_pdf(conn, k, pdf_id),
        havuz_notu=HAVUZ_NOTLARI.get(request.query_params.get("havuz", "")),
    )


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
