"""Soru Maratonu rotaları (yalnızca öğrenci; diğer roller 404, başkasının maratonu 404)."""

import json
import sqlite3

import maraton
import yetki
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from kaynaklar import KaynakHatasi
from kaynaklar import soru as havuz

router = APIRouter(prefix="/ogrenci")
OGRENCI = rol("ogrenci")
KILIT_MESAJ = "Ders sırasında kapalı · {bit}'de açılır"


def _kendisi(conn: sqlite3.Connection, k: sqlite3.Row) -> sqlite3.Row:
    o = yetki.ogrenci_kaydi(conn, k["id"])
    if o is None:
        raise HTTPException(404)
    return o


def _maraton(conn: sqlite3.Connection, k: sqlite3.Row, maraton_id: int) -> sqlite3.Row:
    m = maraton.getir(conn, maraton_id, k["id"])
    if m is None:
        raise HTTPException(404)
    return m


def _js_mi(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


@router.get("/maraton")
def ana(request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)):
    o = _kendisi(conn, k)
    dersler = maraton.dersler(o["sinif"])
    acik = maraton.acik_maraton(conn, k["id"])
    return render(
        request,
        "ogrenci/maraton.html",
        ogrenci=o,
        dersler=dersler,
        kilit=maraton.kilit(),
        kilit_mesaj=KILIT_MESAJ,
        acik=acik,
        acik_ders=havuz.ders_adi(acik["ders"]) if acik else "",
        seri=maraton.seri(conn, k["id"]),
        sonlar=maraton.son_maratonlar(conn, k["id"]),
        ders_adi=havuz.ders_adi,
        soru_sayisi=maraton.SORU_SAYISI,
    )


@router.post("/maraton/basla")
async def basla(
    request: Request,
    k=Depends(rol("ogrenci", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    o = _kendisi(conn, k)
    kilit = maraton.kilit()
    if kilit:
        raise HTTPException(423, KILIT_MESAJ.format(**kilit))
    form = await request.form()
    ders = str(form.get("ders", ""))
    try:
        mevcut = maraton.dersler(o["sinif"])
        if mevcut is None:
            raise HTTPException(503, "Soru havuzu şu an alınamıyor. Biraz sonra tekrar dene.")
        if ders not in {kod for kod, _, _ in mevcut}:
            raise HTTPException(400, "Bu ders için maraton yok.")
        mid = maraton.baslat(conn, k["id"], o["sinif"], ders)
    except KaynakHatasi as e:
        raise HTTPException(503, "Soru havuzu şu an alınamıyor. Biraz sonra tekrar dene.") from e
    except maraton.MaratonHatasi as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse(f"/ogrenci/maraton/{mid}", status_code=303)


@router.get("/maraton/{maraton_id}")
def oyna(
    maraton_id: int,
    request: Request,
    k=Depends(OGRENCI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    m = _maraton(conn, k, maraton_id)
    if m["bitis"]:
        return RedirectResponse(f"/ogrenci/maraton/{maraton_id}/sonuc", status_code=303)
    kilit = maraton.kilit()
    if kilit:
        return render(
            request, "ogrenci/maraton_soru.html", status_code=423, m=m, kilit=kilit,
            kilit_mesaj=KILIT_MESAJ, soru=None, ders_ad=havuz.ders_adi(m["ders"]),
            kareler=maraton.ilerleme(conn, maraton_id),
        )
    s = maraton.siradaki(conn, maraton_id)
    if s is not None and maraton.sure_asildi(s):  # sayfa terk edilip geç dönüldü
        maraton.cevapla(conn, maraton_id, s["sira"], None)
        return RedirectResponse(f"/ogrenci/maraton/{maraton_id}", status_code=303)
    if s is None:
        maraton.bitir(conn, maraton_id)
        return RedirectResponse(f"/ogrenci/maraton/{maraton_id}/sonuc", status_code=303)
    # doğru şık bilerek verilmez: yalnızca cevaptan sonra döner
    soru = {
        "sira": s["sira"],
        "soru": s["soru"],
        "konu": s["konu"],
        "secenekler": json.loads(s["secenekler"]),
        "kalan": maraton.kalan_sn(s),
    }
    return render(
        request, "ogrenci/maraton_soru.html", m=m, kilit=None, soru=soru,
        ders_ad=havuz.ders_adi(m["ders"]), sure=maraton.SURE,
        kareler=maraton.ilerleme(conn, maraton_id), kilit_mesaj=KILIT_MESAJ,
    )


@router.post("/maraton/{maraton_id}/cevap")
async def cevap(
    maraton_id: int,
    request: Request,
    k=Depends(rol("ogrenci", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    m = _maraton(conn, k, maraton_id)
    js = _js_mi(request)
    kilit = maraton.kilit()
    if kilit:
        mesaj = KILIT_MESAJ.format(**kilit)
        if js:
            return JSONResponse({"kilit": True, "mesaj": mesaj}, status_code=423)
        raise HTTPException(423, mesaj)
    if m["bitis"]:
        if js:
            return JSONResponse({"mesaj": "Maraton bitti.", "sonraki": f"/ogrenci/maraton/{maraton_id}/sonuc"}, status_code=409)
        return RedirectResponse(f"/ogrenci/maraton/{maraton_id}/sonuc", status_code=303)
    form = await request.form()
    try:
        sira = int(str(form.get("sira", "")))
        sec = str(form.get("sec", "")).strip()
        secim = int(sec) if sec.lstrip("-").isdigit() and int(sec) >= 0 else None
        sonuc = maraton.cevapla(conn, maraton_id, sira, secim)
    except (ValueError, maraton.MaratonHatasi) as e:
        if js:
            return JSONResponse(
                {"mesaj": str(e), "sonraki": f"/ogrenci/maraton/{maraton_id}"}, status_code=409
            )
        return RedirectResponse(f"/ogrenci/maraton/{maraton_id}", status_code=303)
    sonraki = f"/ogrenci/maraton/{maraton_id}" + ("/sonuc" if sonuc["bitti"] else "")
    if js:
        return JSONResponse({**sonuc, "sonraki": sonraki})
    return RedirectResponse(sonraki, status_code=303)


@router.get("/maraton/{maraton_id}/sonuc")
def sonuc(
    maraton_id: int,
    request: Request,
    k=Depends(OGRENCI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    m = _maraton(conn, k, maraton_id)
    if not m["bitis"]:
        return RedirectResponse(f"/ogrenci/maraton/{maraton_id}", status_code=303)
    satirlar = [
        {**dict(s), "secenekler": json.loads(s["secenekler"])}
        for s in maraton.sorular(conn, maraton_id)
    ]
    sira = next(
        (d["sira"] for d in maraton.liderlik(conn) if d["kullanici_id"] == k["id"]), None
    )
    return render(
        request, "ogrenci/maraton_sonuc.html", m=m, satirlar=satirlar,
        ders_ad=havuz.ders_adi(m["ders"]), kareler=maraton.ilerleme(conn, maraton_id),
        okul_sira=sira, seri=maraton.seri(conn, k["id"]), soru_sayisi=maraton.SORU_SAYISI,
    )


@router.get("/liderlik")
def liderlik(
    request: Request,
    kapsam: str = "sinif",
    k=Depends(OGRENCI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    o = _kendisi(conn, k)
    kapsam = "okul" if kapsam == "okul" else "sinif"
    liste = maraton.liderlik(conn, o["sinif"] if kapsam == "sinif" else None)
    return render(
        request, "ogrenci/liderlik.html", kapsam=kapsam, liste=liste,
        sinif=o["sinif"], ben=k["id"], hafta_basi=maraton.hafta_basi()[:10],
        en_iyi=maraton.EN_IYI,
    )
