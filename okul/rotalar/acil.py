"""Acil durum rotaları (yalnızca öğretmen ve yönetici; diğer roller 404). Alarm: 2 adımlı onay + şifre; konum paylaşımı."""

import sqlite3

import acil
import auth
from deps import db_conn, render, rol
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from kaynaklar import KaynakHatasi
from kaynaklar import acil as dis

router = APIRouter(prefix="/acil")
UYE = rol(*acil.ROLLER)
UYE_POST = rol(*acil.ROLLER, post=True)

ULASILAMADI = "Alarm sistemine ulaşılamadı. Zil düğmesini ve 112'yi kullanın."


def _mod() -> tuple[bool | None, str]:
    """(tatbikat mı | None=bilinmiyor, uyarı)."""
    try:
        return bool(dis.durum().get("tatbikat")), ""
    except KaynakHatasi as e:
        return None, str(e)


def _sayfa(request: Request, k, conn, hata: str = "", durum: int = 200, basladi: dict | None = None):
    tatbikat, uyari = _mod()
    return render(
        request, "acil.html", status_code=durum, turler=acil.TURLER, aktif=acil.aktif(conn),
        konumlar=acil.konumlar(conn), yerler=acil.yerler(), tatbikat=tatbikat, uyari=uyari, hata=hata, basladi=basladi,
        kendi_id=k["id"],
    )


def _tur(tur: str) -> dict:
    if tur not in acil.TURLER:
        raise HTTPException(404)
    return acil.TURLER[tur]


@router.get("")
def ana(request: Request, tamam: str = "", k=Depends(UYE), conn: sqlite3.Connection = Depends(db_conn)):
    basladi = None
    if tamam in acil.TURLER:
        son = conn.execute(
            "SELECT tatbikat FROM acil_olay WHERE kullanici_id = ? AND tur = ? AND basarili = 1 ORDER BY id DESC LIMIT 1",
            (k["id"], tamam),
        ).fetchone()
        if son is not None:
            basladi = {"ad": acil.TURLER[tamam]["ad"], "tatbikat": bool(son["tatbikat"])}
    return _sayfa(request, k, conn, basladi=basladi)


@router.get("/durum")
def durum(k=Depends(UYE), conn: sqlite3.Connection = Depends(db_conn)):
    konum = acil.konumlar(conn, 1)
    return JSONResponse(
        {"aktif": acil.aktif(conn), "konum_id": konum[0]["id"] if konum else 0}, headers={"Cache-Control": "no-store"}
    )


@router.get("/onay/{tur}")
def onay1(request: Request, tur: str, k=Depends(UYE)):
    bilgi = _tur(tur)
    tatbikat, uyari = _mod()
    return render(
        request, "acil_onay.html", tur=tur, bilgi=bilgi, yerler=acil.yerler(), tatbikat=tatbikat, uyari=uyari, hata="",
    )


@router.post("/onay/{tur}")
def onay1_gonder(
    request: Request, tur: str, yer: str = Form(""), k=Depends(UYE_POST),
):
    bilgi = _tur(tur)
    try:
        yer_ad = acil.yer_adi(yer)
    except acil.AcilHatasi as e:
        raise HTTPException(e.kod, e.mesaj) from e
    jeton = acil.jeton_uret(request.cookies.get(auth.COOKIE_ADI, ""), k["id"], tur, yer_ad)
    tatbikat, uyari = _mod()
    return render(
        request, "acil_dogrula.html", tur=tur, bilgi=bilgi, yer=yer_ad, jeton=jeton, tatbikat=tatbikat, uyari=uyari, hata="",
    )


@router.post("/baslat")
def baslat(
    request: Request,
    arka: BackgroundTasks,
    tur: str = Form(""),
    yer: str = Form(""),
    jeton: str = Form(""),
    sifre: str = Form(""),
    k=Depends(UYE_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    bilgi = _tur(tur)
    anahtar = f"acil:{k['id']}"
    tatbikat, uyari = _mod()

    def dogrula_sayfasi(hata: str, durum: int):
        return render(
            request, "acil_dogrula.html", status_code=durum, tur=tur, bilgi=bilgi, yer=yer, jeton=jeton,
            tatbikat=tatbikat, uyari=uyari, hata=hata,
        )

    if auth.engelli_mi(conn, anahtar):
        return dogrula_sayfasi("Çok fazla yanlış şifre. 10 dakika sonra tekrar dene.", 429)
    if not acil.jeton_gecerli(jeton, request.cookies.get(auth.COOKIE_ADI, ""), k["id"], tur, yer):
        return _sayfa(request, k, conn, hata="Onayın süresi doldu. Düğmeye baştan bas.", durum=400)
    if not auth.sifre_dogrula(sifre, k["sifre_hash"]):
        auth.hata_kaydet(conn, anahtar)
        return dogrula_sayfasi("Şifre yanlış.", 403)
    auth.hatalari_temizle(conn, anahtar)
    try:
        acil.baslat(conn, k, tur, yer, jeton)
    except acil.AcilHatasi as e:
        return _sayfa(request, k, conn, hata=ULASILAMADI if e.kod == 502 else e.mesaj, durum=e.kod)
    arka.add_task(acil.bildir, k["id"])
    return RedirectResponse(f"/acil?tamam={tur}", status_code=303)


@router.post("/konum")
def konum(
    request: Request,
    arka: BackgroundTasks,
    yer: str = Form(""),
    enlem: str = Form(""),
    boylam: str = Form(""),
    dogruluk: str = Form(""),
    k=Depends(UYE_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    try:
        _id, bildir = acil.konum_ekle(conn, k, yer, enlem, boylam, dogruluk)
    except acil.AcilHatasi as e:
        return _sayfa(request, k, conn, hata=e.mesaj, durum=e.kod)
    if bildir:
        arka.add_task(acil.bildir, k["id"])
    return RedirectResponse("/acil", status_code=303)
