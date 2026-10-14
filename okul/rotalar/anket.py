"""Anket rotaları. Yönetici: hazırlama, gruplara ayrı gönderme, sonuç. Öğrenci/veli/öğretmen: yanıtlama.

Yetkisiz erişim 404. Yanıtlar anonimdir (bkz. anket.py); sonuç ekranı 5'ten az yanıtlı grupları göstermez.
"""

import sqlite3

import analitik
import anket
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter()
YONETICI = rol("yonetici")
YONETICI_POST = rol("yonetici", post=True)
KATILIMCI = rol("ogrenci", "veli", "ogretmen")
KATILIMCI_POST = rol("ogrenci", "veli", "ogretmen", post=True)


def _anket(conn: sqlite3.Connection, anket_id: int) -> sqlite3.Row:
    a = anket.getir(conn, anket_id)
    if a is None:
        raise HTTPException(404)
    return a


def _detay(request, conn, anket_id: int, hata: str = "", status: int = 200):
    a = _anket(conn, anket_id)
    h = anket.hedefler(conn, anket_id)
    return render(
        request,
        "yonetici/anket_detay.html",
        status_code=status,
        a=a,
        sorular=anket.sorular(conn, anket_id),
        taslak=not h,
        hedefler=h,
        ozet={x["rol"]: x for x in anket.katilim_ozeti(conn, anket_id)},
        roller=anket.ROLLER,
        etiket=anket.ROL_ETIKET,
        turler=anket.TURLER,
        siniflar=anket.siniflar(conn),
        hata=hata,
        esik=anket.ESIK_N,
        acik=anket.acik_mi,
    )


# --- yönetici ---


@router.get("/yonetici/anketler")
def liste(request: Request, k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)):
    return render(request, "yonetici/anketler.html", anketler=anket.anket_listesi(conn), hata="")


@router.post("/yonetici/anketler")
async def olustur(request: Request, k=Depends(YONETICI_POST), conn: sqlite3.Connection = Depends(db_conn)):
    form = await request.form()
    try:
        aid = anket.olustur(conn, k["id"], str(form.get("baslik", "")), str(form.get("aciklama", "")))
    except anket.AnketHatasi as e:
        return render(
            request, "yonetici/anketler.html", status_code=400, anketler=anket.anket_listesi(conn), hata=str(e)
        )
    return RedirectResponse(f"/yonetici/anketler/{aid}", status_code=303)


@router.get("/yonetici/anketler/{anket_id}")
def detay(anket_id: int, request: Request, k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)):
    return _detay(request, conn, anket_id)


@router.post("/yonetici/anketler/{anket_id}/soru")
async def soru_ekle(
    anket_id: int, request: Request, k=Depends(YONETICI_POST), conn: sqlite3.Connection = Depends(db_conn)
):
    _anket(conn, anket_id)
    form = await request.form()
    try:
        anket.soru_ekle(
            conn, anket_id, str(form.get("tur", "")), str(form.get("metin", "")),
            str(form.get("secenekler", "")).splitlines(), form.get("zorunlu") == "1",
            [str(x) for x in form.getlist("roller")],
        )
    except anket.AnketHatasi as e:
        return _detay(request, conn, anket_id, str(e), 400)
    return RedirectResponse(f"/yonetici/anketler/{anket_id}", status_code=303)


@router.post("/yonetici/anketler/{anket_id}/soru/{soru_id}/sil")
def soru_sil(
    anket_id: int, soru_id: int, request: Request, k=Depends(YONETICI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    _anket(conn, anket_id)
    try:
        anket.soru_sil(conn, anket_id, soru_id)
    except anket.AnketHatasi as e:
        return _detay(request, conn, anket_id, str(e), 400)
    return RedirectResponse(f"/yonetici/anketler/{anket_id}", status_code=303)


@router.post("/yonetici/anketler/{anket_id}/dagit")
async def dagit(
    anket_id: int, request: Request, k=Depends(YONETICI_POST), conn: sqlite3.Connection = Depends(db_conn)
):
    _anket(conn, anket_id)
    form = await request.form()
    try:
        anket.dagit(
            conn, anket_id, str(form.get("rol", "")), str(form.get("sinif", "")), str(form.get("kapanis", ""))
        )
    except anket.AnketHatasi as e:
        return _detay(request, conn, anket_id, str(e), 400)
    return RedirectResponse(f"/yonetici/anketler/{anket_id}", status_code=303)


@router.post("/yonetici/anketler/{anket_id}/kapat")
async def kapat(
    anket_id: int, request: Request, k=Depends(YONETICI_POST), conn: sqlite3.Connection = Depends(db_conn)
):
    _anket(conn, anket_id)
    form = await request.form()
    try:
        anket.kapat(conn, anket_id, str(form.get("rol", "")))
    except anket.AnketHatasi as e:
        return _detay(request, conn, anket_id, str(e), 400)
    return RedirectResponse(f"/yonetici/anketler/{anket_id}", status_code=303)


@router.post("/yonetici/anketler/{anket_id}/sil")
def sil(
    anket_id: int, request: Request, k=Depends(YONETICI_POST), conn: sqlite3.Connection = Depends(db_conn)
):
    _anket(conn, anket_id)
    try:
        anket.sil(conn, anket_id)
    except anket.AnketHatasi as e:
        return _detay(request, conn, anket_id, str(e), 400)
    return RedirectResponse("/yonetici/anketler", status_code=303)


@router.get("/yonetici/anketler/{anket_id}/sonuc")
def sonuc(anket_id: int, request: Request, k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)):
    a = _anket(conn, anket_id)
    return render(
        request, "yonetici/anket_sonuc.html", a=a, ozet=anket.katilim_ozeti(conn, anket_id),
        sorular=anket.sonuc(conn, anket_id), esik=anket.ESIK_N, turler=anket.TURLER,
    )


# --- katılımcılar (öğrenci / veli / öğretmen) ---


def _uygun(conn: sqlite3.Connection, k: sqlite3.Row, anket_id: int) -> sqlite3.Row:
    """Yalnızca kendisine gönderilmiş, açık ve henüz yanıtlanmamış anket; aksi 404 (varlığı sızdırma)."""
    a = anket.getir(conn, anket_id)
    h = anket.hedefler(conn, anket_id).get(k["rol"]) if a else None
    if a is None or h is None or not anket.kapsiyor_mu(conn, k, h) or not anket.acik_mi(h):
        raise HTTPException(404)
    return a


def _form(request, conn, k, a, hata: str = "", status: int = 200):
    return render(
        request, "anket_doldur.html", status_code=status, a=a,
        sorular=anket.sorular(conn, a["id"], k["rol"]), hata=hata,
    )


@router.get("/anket")
def anketlerim(
    request: Request, tamam: int = 0, k=Depends(KATILIMCI), conn: sqlite3.Connection = Depends(db_conn)
):
    return render(request, "anket_liste.html", anketler=anket.kullanicinin_anketleri(conn, k), tamam=bool(tamam))


@router.get("/anket/{anket_id}")
def doldur(anket_id: int, request: Request, k=Depends(KATILIMCI), conn: sqlite3.Connection = Depends(db_conn)):
    a = _uygun(conn, k, anket_id)
    if anket.yanitladi_mi(conn, anket_id, k["id"]):
        return RedirectResponse("/anket", status_code=303)
    return _form(request, conn, k, a)


@router.post("/anket/{anket_id}")
async def gonder(
    anket_id: int, request: Request, k=Depends(KATILIMCI_POST), conn: sqlite3.Connection = Depends(db_conn)
):
    a = _uygun(conn, k, anket_id)
    form = await request.form()
    girdi = {s["id"]: [str(v) for v in form.getlist(f"s{s['id']}")] for s in anket.sorular(conn, anket_id, k["rol"])}
    try:
        anket.yanitla(conn, k, anket_id, girdi)
    except anket.AnketHatasi as e:
        if anket.yanitladi_mi(conn, anket_id, k["id"]):
            return RedirectResponse("/anket", status_code=303)
        return _form(request, conn, k, a, str(e), 400)
    analitik.istekten(request, "anket_yanitla", str(anket_id))
    return RedirectResponse("/anket?tamam=1", status_code=303)
