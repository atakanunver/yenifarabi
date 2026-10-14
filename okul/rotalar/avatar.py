"""Avatar seçimi (yalnızca öğrenci, yalnızca kendi avatarı). Önizleme GET ile, kayıt POST ile; açılmamış eşya reddedilir."""

import sqlite3

import arena
import avatar
import yetki
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/ogrenci/avatar")
OGRENCI = rol("ogrenci")


def _kendisi(conn: sqlite3.Connection, k: sqlite3.Row) -> sqlite3.Row:
    o = yetki.ogrenci_kaydi(conn, k["id"])
    if o is None:
        raise HTTPException(404)
    return o


def _sayfa(request, conn, k, secim: dict, hata: str = "", status: int = 200, kaydedildi: bool = False):
    sev = arena.seviye(conn, k["id"])
    kayitli = avatar.getir(conn, k["id"])
    return render(
        request, "ogrenci/avatar.html", status_code=status, seviye=sev, secim=secim, kayitli=kayitli,
        degisti=secim != kayitli, bolumler=avatar.BOLUMLER, kademe=avatar.kademe(sev["no"]),
        siradaki=avatar.siradaki_acilis(sev["no"]), hata=hata, kaydedildi=kaydedildi,
    )


@router.get("")
def secim(request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)):
    """Önizleme: sorgu parametreleri kayıtlı avatarın üstüne uygulanır (kaydetmez). Açılmamış seçenek önizlenemez."""
    _kendisi(conn, k)
    sev = arena.seviye(conn, k["id"])["no"]
    cfg = avatar.getir(conn, k["id"])
    for bolum in avatar.BOLUMLER:
        kod = request.query_params.get(bolum, "")
        if avatar.acik_mi(bolum, kod, sev):
            cfg[bolum] = kod
    return _sayfa(request, conn, k, cfg, kaydedildi=request.query_params.get("tamam") == "1")


@router.post("")
async def kaydet(request: Request, k=Depends(rol("ogrenci", post=True)), conn: sqlite3.Connection = Depends(db_conn)):
    _kendisi(conn, k)
    form = await request.form()
    sev = arena.seviye(conn, k["id"])["no"]
    cfg = {b: str(form.get(b, "")) for b in avatar.BOLUMLER}
    try:
        avatar.kaydet(conn, k["id"], cfg, sev)
    except ValueError as e:
        return _sayfa(request, conn, k, avatar.cfg_temiz(cfg), str(e), 400)
    return RedirectResponse("/ogrenci/avatar?tamam=1", status_code=303)
