"""Bilgi Arenası rotaları: Günlük Görev (yalnızca öğrenci; diğer roller 404, başkasının turu 404).

Hızlı Mod, mevcut Soru Maratonu'dur (rotalar/oyun.py); ikisi ortak XP defterini besler.
Doğru şık yalnızca cevap verildikten sonra gelir (GET /{id}/soru/{sira}).
"""

import json
import sqlite3

import analitik
import arena
import avatar
import maraton
import oduller
import yetki
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from kaynaklar import KaynakHatasi
from kaynaklar import soru as havuz

router = APIRouter(prefix="/ogrenci/arena")
OGRENCI = rol("ogrenci")
KILIT_MESAJ = "Ders sırasında kapalı · {bit}'de açılır"
HAVUZ_MESAJ = "Soru havuzu şu an alınamıyor. Biraz sonra tekrar dene."


def _kendisi(conn: sqlite3.Connection, k: sqlite3.Row) -> sqlite3.Row:
    o = yetki.ogrenci_kaydi(conn, k["id"])
    if o is None or not arena.duzey_uygun(o["sinif"]):
        raise HTTPException(404)
    return o


def _tur(conn: sqlite3.Connection, k: sqlite3.Row, tur_id: int) -> sqlite3.Row:
    t = arena.tur_getir(conn, tur_id, k["id"])
    if t is None:
        raise HTTPException(404)
    return t


def _kilit_kontrol() -> None:
    kilit = maraton.kilit()
    if kilit:
        raise HTTPException(423, KILIT_MESAJ.format(**kilit))


def _js_mi(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


@router.get("")
def merkez(request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)):
    o = _kendisi(conn, k)
    return render(
        request,
        "ogrenci/arena.html",
        ogrenci=o,
        seviye=arena.seviye(conn, k["id"]),
        gorev=arena.gorev_durumu(conn, k["id"], o["sinif"]),
        hizli={"kilit": maraton.kilit(), "seri": maraton.seri(conn, k["id"])},
        son=arena.son_tur(conn, k["id"]),
        tekrar=arena.tekrar_onerileri(conn, k["id"]) or None,
        hafta=arena.hafta_ozeti(conn, k["id"]),
        liderlik_ozet=oduller.liderlik(conn, oduller.hafta_basi(), k["id"])["xp"],
        avatar_cfg=avatar.getir(conn, k["id"]),
        avatar_siradaki=avatar.siradaki_acilis(arena.seviye(conn, k["id"])["no"]),
    )


@router.post("/basla")
def basla(
    request: Request,
    k=Depends(rol("ogrenci", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    o = _kendisi(conn, k)
    var = arena.bugunku_tur(conn, k["id"]) is not None
    if not var:
        _kilit_kontrol()
    try:
        tur = arena.baslat(conn, k["id"], o["sinif"])
    except KaynakHatasi as e:
        raise HTTPException(503, HAVUZ_MESAJ) from e
    except arena.ArenaHatasi as e:
        raise HTTPException(400, str(e)) from e
    if not var:
        analitik.istekten(request, "arena_basla", str(tur))
    return RedirectResponse(f"/ogrenci/arena/{tur}", status_code=303)


@router.get("/liderlik")
def liderlik(
    request: Request, donem: str = "hafta", k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)
):
    """Bilgi Arenası liderliği: en çok XP kazanan, en çok doğru, en çok soru çözen (hafta ya da tüm zamanlar)."""
    _kendisi(conn, k)
    donem = "tum" if donem == "tum" else "hafta"
    hb = oduller.hafta_basi() if donem == "hafta" else None
    return render(
        request, "ogrenci/arena_liderlik.html", donem=donem, hafta_basi=hb,
        tablolar=oduller.liderlik(conn, hb, k["id"]), ilk=oduller.LIDER_ILK,
    )


@router.get("/ilerleme")
def ilerleme(request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)):
    _kendisi(conn, k)
    return render(
        request,
        "ogrenci/arena_ilerleme.html",
        seviye=arena.seviye(conn, k["id"]),
        rozetler=arena.rozetler(conn, k["id"]),
        gunler=arena.gunler(conn, k["id"]),
        hafta=arena.hafta_ozeti(conn, k["id"]),
        kazanimlar=arena.kazanim_calismalari(conn, k["id"]) or None,
    )


def _soru_ekrani(request, conn, t, s, geri=None):
    soru = {
        "sira": s["sira"],
        "soru": s["soru"],
        "konu": s["konu"],
        "secenekler": json.loads(s["secenekler"]),
    }
    return render(
        request,
        "ogrenci/arena_soru.html",
        tur={"id": t["id"], "soru_sayisi": arena.SORU_SAYISI},
        soru=soru,
        kareler=arena.kareler(conn, t["id"]),
        geri=geri,
    )


@router.get("/{tur_id}")
def oyna(
    tur_id: int,
    request: Request,
    k=Depends(OGRENCI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    _kendisi(conn, k)
    t = _tur(conn, k, tur_id)
    if t["durum"] == "tamam":
        return RedirectResponse(f"/ogrenci/arena/{tur_id}/sonuc", status_code=303)
    if t["durum"] != "acik":
        return RedirectResponse("/ogrenci/arena", status_code=303)
    _kilit_kontrol()
    s = arena.siradaki(conn, tur_id)
    if s is None:  # tüm sorular cevaplı ama tur kapanmamış olamaz; yine de güvenli çıkış
        return RedirectResponse(f"/ogrenci/arena/{tur_id}/sonuc", status_code=303)
    return _soru_ekrani(request, conn, t, s)


@router.post("/{tur_id}/cevap")
async def cevap(
    tur_id: int,
    request: Request,
    k=Depends(rol("ogrenci", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    _kendisi(conn, k)
    t = _tur(conn, k, tur_id)
    form = await request.form()
    try:
        sira = int(str(form.get("sira", "")))
        sec = int(str(form.get("sec", "")))
    except ValueError as e:
        raise HTTPException(400, "Geçersiz cevap.") from e
    _kilit_kontrol()
    soru = arena.soru_getir(conn, tur_id, sira)
    if soru is None or not 0 <= sec < len(json.loads(soru["secenekler"])):
        raise HTTPException(400, "Geçersiz cevap.")
    try:
        sonuc = arena.cevapla(conn, tur_id, sira, sec)
    except arena.ArenaHatasi as e:
        # çift dokunma / eski sekme: ödül yok; JS'siz akışta sessizce güncel soruya dön
        if _js_mi(request):
            return JSONResponse({"mesaj": str(e), "sonraki": f"/ogrenci/arena/{tur_id}"}, status_code=409)
        return RedirectResponse(f"/ogrenci/arena/{tur_id}", status_code=303)
    if sonuc["bitti"]:
        analitik.istekten(request, "arena_tamamla", str(t["id"]))
    sonraki = f"/ogrenci/arena/{tur_id}/soru/{sira}"
    if _js_mi(request):
        return JSONResponse({**sonuc, "sonraki": sonraki})
    return RedirectResponse(sonraki, status_code=303)


@router.get("/{tur_id}/soru/{sira}")
def geri_bildirim(
    tur_id: int,
    sira: int,
    request: Request,
    k=Depends(OGRENCI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    """Cevaplanmış sorunun geri bildirimi; doğru şık yalnızca burada (cevaptan sonra) görünür."""
    _kendisi(conn, k)
    t = _tur(conn, k, tur_id)
    s = arena.soru_getir(conn, tur_id, sira)
    if s is None:
        raise HTTPException(404)
    if s["cevap"] is None:
        return RedirectResponse(f"/ogrenci/arena/{tur_id}", status_code=303)
    son = sira == arena.SORU_SAYISI
    geri = {
        "dogru": s["cevap"] == s["dogru_index"],
        "dogru_index": s["dogru_index"],
        "secilen": s["cevap"],
        "sonraki": f"/ogrenci/arena/{tur_id}/sonuc" if son else f"/ogrenci/arena/{tur_id}",
    }
    return _soru_ekrani(request, conn, t, s, geri)


@router.get("/{tur_id}/sonuc")
def sonuc(
    tur_id: int,
    request: Request,
    k=Depends(OGRENCI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    _kendisi(conn, k)
    t = _tur(conn, k, tur_id)
    if t["durum"] != "tamam":
        return RedirectResponse(f"/ogrenci/arena/{tur_id}", status_code=303)
    satirlar = [
        {
            "sira": s["sira"], "soru": s["soru"], "konu": s["konu"],
            "secenekler": json.loads(s["secenekler"]), "dogru_index": s["dogru_index"],
            "cevap": s["cevap"],
        }
        for s in arena.sorular(conn, tur_id)
    ]
    yeni = [r for r in arena.rozetler(conn, k["id"]) if r["kazanildi"] and r["tarih"] >= t["basla"]]
    return render(
        request,
        "ogrenci/arena_sonuc.html",
        tur={
            "dogru": t["dogru"], "soru_sayisi": arena.SORU_SAYISI, "xp": t["xp"],
            "ders_ad": havuz.ders_adi(t["ders"]),
        },
        satirlar=satirlar,
        kazanim_ozet=arena.kazanim_ozeti(conn, tur_id),
        yeni_rozetler=[{"ad": r["ad"]} for r in yeni],
        seviye_atladi=arena.seviye_atladi(conn, k["id"], t),
        seviye=arena.seviye(conn, k["id"]),
        avatar_cfg=avatar.getir(conn, k["id"]),
        yaris=oduller.liderlik(conn, oduller.hafta_basi(), k["id"])["xp"],
        acilanlar=avatar.acilanlar(
            arena.seviye_hesapla(arena.toplam_xp(conn, k["id"]) - t["xp"])["no"], arena.seviye(conn, k["id"])["no"]
        ),
    )
