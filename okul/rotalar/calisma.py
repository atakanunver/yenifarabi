"""Serbest çalışma ve yanlışları tekrar (yalnızca öğrenci, 9-11; diğer roller 404, başkasının sorusu 404).

XP/rozet/haftalık hedef YOK. Doğru şık yalnızca cevap verildikten sonra gelir (GET /{id}).
"""

import json
import sqlite3

import analitik
import arena
import calisma
import maraton
import soru_bildirim
import yetki
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from kaynaklar import KaynakHatasi, arena_soru
from kaynaklar import soru as havuz

router = APIRouter(prefix="/ogrenci/calisma")
OGRENCI = rol("ogrenci")
OGRENCI_POST = rol("ogrenci", post=True)
HAVUZ_MESAJ = "Soru havuzu şu an alınamıyor. Biraz sonra tekrar dene."


def _kendisi(conn: sqlite3.Connection, k: sqlite3.Row) -> sqlite3.Row:
    o = yetki.ogrenci_kaydi(conn, k["id"])
    if o is None or not arena.duzey_uygun(o["sinif"]):
        raise HTTPException(404)
    return o


def _kilit_kontrol() -> None:
    kilit = maraton.kilit()
    if kilit:
        raise HTTPException(423, f"Ders sırasında kapalı · {kilit['bit']}'de açılır")


@router.get("")
def merkez(request: Request, ders: str = "", k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)):
    o = _kendisi(conn, k)
    hata, dersler, kazanimlar = False, [], []
    try:
        duzey = maraton.duzey(o["sinif"])
        dersler = [kod for kod, _ in havuz.dersler(duzey)]
        if ders in dersler:
            kazanimlar = arena_soru.kazanimlar(duzey, ders, soru_bildirim.gizli_idler(conn))
    except KaynakHatasi:
        hata = True
    return render(
        request, "ogrenci/calisma.html", tekrar=calisma.tekrar_sayisi(conn, k["id"]), dersler=dersler,
        ders=ders if ders in dersler else "", kazanimlar=kazanimlar, hata=hata, acik=calisma.acik(conn, k["id"]),
    )


@router.post("/tekrar/basla")
def tekrar_basla(request: Request, k=Depends(OGRENCI_POST), conn: sqlite3.Connection = Depends(db_conn)):
    _kendisi(conn, k)
    _kilit_kontrol()
    try:
        cid = calisma.tekrar_baslat(conn, k["id"])
    except calisma.CalismaHatasi:
        return RedirectResponse("/ogrenci/calisma", status_code=303)
    analitik.istekten(request, "calisma_tekrar", str(cid))
    return RedirectResponse(f"/ogrenci/calisma/{cid}", status_code=303)


@router.post("/serbest/basla")
def serbest_basla(
    request: Request,
    ders: str = Form(""),
    kazanim: str = Form(""),
    k=Depends(OGRENCI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    o = _kendisi(conn, k)
    _kilit_kontrol()
    try:
        kid = int(kazanim) if kazanim.strip() else None
    except ValueError:
        raise HTTPException(400, "Geçersiz kazanım.") from None
    try:
        cid = calisma.serbest_baslat(conn, k["id"], o["sinif"], ders, kid)
    except KaynakHatasi as e:
        raise HTTPException(503, HAVUZ_MESAJ) from e
    except calisma.CalismaHatasi as e:
        raise HTTPException(400, str(e)) from e
    analitik.istekten(request, "calisma_serbest", str(cid))
    return RedirectResponse(f"/ogrenci/calisma/{cid}", status_code=303)


def _soru_ekrani(request, conn, k, c):
    geri = None
    if c["cevap"] is not None:
        geri = {"dogru": c["cevap"] == c["dogru_index"], "dogru_index": c["dogru_index"], "secilen": c["cevap"]}
    return render(
        request,
        "ogrenci/calisma_soru.html",
        c={"id": c["id"], "kaynak": c["kaynak"], "ders": c["ders"], "kazanim_id": c["kazanim_id"], "konu": c["konu"],
           "kazanim_kod": c["kazanim_kod"], "soru": c["soru"], "secenekler": json.loads(c["secenekler"]),
           "soru_id": c["soru_id"], "bildirildi": soru_bildirim.bildirdi_mi(conn, k["id"], c["soru_id"])},
        soru={"soru_id": c["soru_id"], "bildirildi": soru_bildirim.bildirdi_mi(conn, k["id"], c["soru_id"])},
        geri=geri,
    )


@router.get("/{calisma_id}")
def oyna(calisma_id: int, request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)):
    _kendisi(conn, k)
    c = calisma.getir(conn, calisma_id, k["id"])
    if c is None:
        raise HTTPException(404)
    if c["cevap"] is None:
        _kilit_kontrol()
    if c["cevap"] == calisma.PAS:
        return RedirectResponse("/ogrenci/calisma", status_code=303)
    return _soru_ekrani(request, conn, k, c)


@router.post("/{calisma_id}/cevap")
def cevap(
    calisma_id: int, sec: int = Form(...), k=Depends(OGRENCI_POST), conn: sqlite3.Connection = Depends(db_conn)
):
    _kendisi(conn, k)
    _kilit_kontrol()
    try:
        calisma.cevapla(conn, k["id"], calisma_id, sec)
    except calisma.CalismaHatasi:  # çift dokunma / eski sekme: güncel duruma dön
        pass
    return RedirectResponse(f"/ogrenci/calisma/{calisma_id}", status_code=303)


@router.post("/{calisma_id}/gec")
def gec(calisma_id: int, k=Depends(OGRENCI_POST), conn: sqlite3.Connection = Depends(db_conn)):
    _kendisi(conn, k)
    if calisma.getir(conn, calisma_id, k["id"]) is None:
        raise HTTPException(404)
    calisma.gec(conn, k["id"], calisma_id)
    return RedirectResponse("/ogrenci/calisma", status_code=303)
