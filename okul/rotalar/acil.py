"""Acil durum rotaları (yalnızca öğretmen ve yönetici; diğer roller 404). Alarm: 2 adımlı onay + şifre; konum paylaşımı."""

import hmac
import sqlite3

import acil
import auth
from ayarlar import AYAR
from deps import db_conn, render, rol
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from kaynaklar import KaynakHatasi
from kaynaklar import acil as dis

from rotalar.pano import (
    _lan_mi,  # tünel (cf-*/x-forwarded-*) başlıklı istek LAN dışı sayılır
)

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
        konumlar=acil.konumlar(conn), son_olaylar=acil.son_olaylar(conn), ogrenci_bildirimleri=acil.ogrenci_bildirimleri(conn) if k["rol"] == "yonetici" else [],
        yerler=acil.yerler(), tatbikat=tatbikat, uyari=uyari, hata=hata, basladi=basladi,
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
    return JSONResponse({"aktif": acil.aktif(conn), "konum_id": acil.son_imza(conn)}, headers={"Cache-Control": "no-store"})


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

    def dogrula_sayfasi(hata: str, durum: int):
        tatbikat, uyari = _mod()
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
    arka.add_task(acil.bildir, k["id"], acil.ROLLER, "acil_bitti" if tur in acil.KAPATAN_TURLER else "acil")
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


# --- öğrenci: "Acil durum var, konumumu idareye gönder" (yalnızca öğrenci; bildirim yalnızca yöneticilere) ---
OGRENCI = rol("ogrenci")
OGRENCI_POST = rol("ogrenci", post=True)


@router.get("/ogrenci")
def ogrenci_onay(request: Request, k=Depends(OGRENCI)):
    return render(request, "acil_ogrenci.html", tamam=False, hata="")


@router.post("/ogrenci")
def ogrenci_gonder(
    request: Request,
    arka: BackgroundTasks,
    enlem: str = Form(""),
    boylam: str = Form(""),
    dogruluk: str = Form(""),
    k=Depends(OGRENCI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    try:
        _id, bildir = acil.ogrenci_bildir(conn, k, enlem, boylam, dogruluk)
    except acil.AcilHatasi as e:
        return render(request, "acil_ogrenci.html", status_code=e.kod, tamam=e.kod == 429, hata=e.mesaj)
    if bildir:
        arka.add_task(acil.bildir, k["id"], ("yonetici",))
    return render(request, "acil_ogrenci.html", tamam=True, hata="")


# --- panel/Telegram/tahta kaynaklı olay bildirimi (dashboard → okul; yalnızca LAN, X-Acil-Anahtar) ---
@router.post("/dis-olay", include_in_schema=False)
async def dis_olay(request: Request, arka: BackgroundTasks, conn: sqlite3.Connection = Depends(db_conn)):
    gelen = request.headers.get("X-Acil-Anahtar", "")
    if not AYAR.acil_anahtar or not _lan_mi(request) or not hmac.compare_digest(gelen, AYAR.acil_anahtar):
        raise HTTPException(404)  # varlığı sızdırma
    try:
        govde = await request.json()
        tur, tatbikat, kaynak = govde["tur"], govde.get("tatbikat", True), govde.get("kaynak", "")
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise HTTPException(400, "Geçersiz gövde.") from e
    if not isinstance(tur, str) or not isinstance(tatbikat, bool) or not isinstance(kaynak, str):
        raise HTTPException(400, "Geçersiz gövde.")
    try:
        acil.dis_olay_ekle(conn, tur, tatbikat, kaynak)
    except acil.AcilHatasi as e:
        raise HTTPException(e.kod, e.mesaj) from e
    arka.add_task(acil.bildir, 0, acil.ROLLER, "acil_bitti" if tur in acil.KAPATAN_TURLER else "acil")
    return JSONResponse({"tamam": True})
