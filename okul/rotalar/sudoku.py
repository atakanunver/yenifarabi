"""Sudoku Düellosu rotaları (yalnızca öğrenci; katılımcı olmayan / başka sınıf = 404).
Çözüm istemciye hiçbir yanıtta gitmez; süre sunucuda ölçülür."""

import sqlite3

import analitik
import oduller
import sudoku
import yetki
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from metin import kisa_ad

router = APIRouter(prefix="/ogrenci/sudoku")
OGRENCI = rol("ogrenci")


def _kendisi(conn: sqlite3.Connection, k: sqlite3.Row) -> sqlite3.Row:
    o = yetki.ogrenci_kaydi(conn, k["id"])
    if o is None:
        raise HTTPException(404)
    return o


def _duello(conn: sqlite3.Connection, k: sqlite3.Row, duello_id: int) -> sqlite3.Row:
    d = sudoku.getir(conn, duello_id, k["id"])
    if d is None:
        raise HTTPException(404)
    return d


def _js_mi(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def _ad(conn: sqlite3.Connection, kid: int) -> str:
    r = conn.execute("SELECT ad_soyad FROM ogrenci WHERE kullanici_id = ?", (kid,)).fetchone()
    return kisa_ad(r["ad_soyad"]) if r else "?"


@router.get("")
def ana(request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn), hata: str = ""):
    o = _kendisi(conn, k)
    return render(
        request, "ogrenci/sudoku.html", ogrenci=o, d=sudoku.duellolarim(conn, k["id"]),
        arkadaslar=sudoku.sinif_arkadaslari(conn, o["sinif"], k["id"]), zorluklar=sudoku.ZORLUK_AD,
        ipuclari=sudoku.ZORLUK, hata=hata[:200],
    )


@router.get("/liderlik")
def liderlik(request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)):
    o = _kendisi(conn, k)
    hb = oduller.hafta_basi()
    return render(
        request, "ogrenci/sudoku_liderlik.html", sinif=o["sinif"], ben=k["id"], hafta_basi=hb,
        liste=sudoku.liderlik(conn, o["sinif"], hb), siniflar=sudoku.sinif_ozetleri(conn, hb),
        puan=sudoku.PUAN, carpan=sudoku.CARPAN,
    )


@router.post("/meydan-oku")
async def meydan_oku(
    request: Request,
    k=Depends(rol("ogrenci", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    o = _kendisi(conn, k)
    form = await request.form()
    try:
        rakip = int(str(form.get("rakip", "")))
    except ValueError:
        raise HTTPException(404) from None
    try:
        did = sudoku.meydan_oku(conn, k["id"], o["sinif"], rakip, str(form.get("zorluk", "")))
    except sudoku.SudokuHatasi as e:
        if _js_mi(request):
            return JSONResponse({"mesaj": str(e)}, status_code=400)
        return RedirectResponse(f"/ogrenci/sudoku?hata={e}", status_code=303)
    analitik.istekten(request, "sudoku_meydan", str(did))
    if _js_mi(request):
        return JSONResponse({"id": did, "sonraki": "/ogrenci/sudoku"})
    return RedirectResponse("/ogrenci/sudoku", status_code=303)


async def _karar(request: Request, duello_id: int, k, conn: sqlite3.Connection, islem) -> RedirectResponse | JSONResponse:
    _duello(conn, k, duello_id)
    try:
        islem(conn, duello_id, k["id"])
    except sudoku.SudokuHatasi as e:
        if _js_mi(request):
            return JSONResponse({"mesaj": str(e)}, status_code=409)
        return RedirectResponse(f"/ogrenci/sudoku?hata={e}", status_code=303)
    if _js_mi(request):
        return JSONResponse({"sonraki": "/ogrenci/sudoku"})
    return RedirectResponse("/ogrenci/sudoku", status_code=303)


@router.post("/{duello_id}/kabul")
async def kabul(duello_id: int, request: Request, k=Depends(rol("ogrenci", post=True)), conn: sqlite3.Connection = Depends(db_conn)):
    return await _karar(request, duello_id, k, conn, sudoku.kabul)


@router.post("/{duello_id}/red")
async def red(duello_id: int, request: Request, k=Depends(rol("ogrenci", post=True)), conn: sqlite3.Connection = Depends(db_conn)):
    return await _karar(request, duello_id, k, conn, sudoku.red)


@router.get("/{duello_id}")
def oyna(duello_id: int, request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn), uyari: str = ""):
    d = _duello(conn, k, duello_id)
    if d["durum"] != "surer":
        return RedirectResponse(f"/ogrenci/sudoku/{duello_id}/sonuc", status_code=303)
    ben = sudoku.oyun(conn, duello_id, k["id"])
    if ben is not None and ben["bitis"]:
        return RedirectResponse(f"/ogrenci/sudoku/{duello_id}/sonuc", status_code=303)
    ben = sudoku.baslat(conn, duello_id, k["id"])
    rakip_id = d["rakip_kid"] if d["kuran_kid"] == k["id"] else d["kuran_kid"]
    return render(
        request, "ogrenci/sudoku_oyun.html", d={"id": d["id"], "zorluk_ad": sudoku.ZORLUK_AD[d["zorluk"]], "son_tarih": d["son_tarih"]},
        bulmaca=d["bulmaca"], gecen=sudoku.gecen_sn(ben), hata=ben["hata"], ceza=sudoku.HATA_CEZA,
        rakip=_ad(conn, rakip_id), uyari=uyari[:200],
    )


@router.post("/{duello_id}/gonder")
async def gonder(duello_id: int, request: Request, k=Depends(rol("ogrenci", post=True)), conn: sqlite3.Connection = Depends(db_conn)):
    _duello(conn, k, duello_id)
    js = _js_mi(request)
    form = await request.form()
    # JS tek "tahta" alanı gönderir; JS'siz form 81 adet "h" alanı (boş = 0)
    tahta = str(form.get("tahta", "")) or "".join((str(v).strip() or "0")[:1] for v in form.getlist("h"))
    try:
        s = sudoku.gonder(conn, duello_id, k["id"], tahta)
    except sudoku.SudokuHatasi as e:
        if js:
            return JSONResponse({"mesaj": str(e), "sonraki": f"/ogrenci/sudoku/{duello_id}"}, status_code=409)
        return RedirectResponse(f"/ogrenci/sudoku/{duello_id}?uyari={e}", status_code=303)
    sonraki = f"/ogrenci/sudoku/{duello_id}/sonuc" if s["dogru"] else f"/ogrenci/sudoku/{duello_id}"
    if s["dogru"]:
        analitik.istekten(request, "sudoku_bitir", str(duello_id))
    if js:
        return JSONResponse({**s, "sonraki": sonraki})
    return RedirectResponse(sonraki, status_code=303)


@router.get("/{duello_id}/sonuc")
def sonuc(duello_id: int, request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)):
    d = _duello(conn, k, duello_id)
    ben_kuran = d["kuran_kid"] == k["id"]
    rakip_id = d["rakip_kid"] if ben_kuran else d["kuran_kid"]
    benim, onun = sudoku.oyun(conn, duello_id, k["id"]), sudoku.oyun(conn, duello_id, rakip_id)
    s = sudoku.sonuc(conn, d)
    return render(
        request, "ogrenci/sudoku_sonuc.html", d={"id": d["id"], "durum": d["durum"], "zorluk_ad": sudoku.ZORLUK_AD[d["zorluk"]],
        "son_tarih": d["son_tarih"]}, rakip=_ad(conn, rakip_id), sonuc=(s["kuran"] if ben_kuran else s["rakip"]) if s else None,
        benim_skor=sudoku.skor(benim), onun_skor=sudoku.skor(onun), benim=benim, onun=onun,
        kazanc=(sudoku.PUAN[(s["kuran"] if ben_kuran else s["rakip"])] * sudoku.CARPAN[d["zorluk"]]) if s else 0,
        ben_kuran=ben_kuran, ceza=sudoku.HATA_CEZA,
    )
