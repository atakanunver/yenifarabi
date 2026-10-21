"""Hızlı Etkinlik Atama rotaları (öğretmen/yönetici). Yetkisiz = 404, yalnızca kendi sınıf+dersine atama."""

import sqlite3

import analitik
import etkinlik
import push
import soru_bildirim
import yetki
from deps import db_conn, render, rol
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from kaynaklar import KaynakHatasi, arena_soru, kazanim
from metin import sinif_seviyesi, tr_kucuk

router = APIRouter(prefix="/ogretmen/hizli")
OGRETMEN = rol("ogretmen", "yonetici")
OGRETMEN_POST = rol("ogretmen", "yonetici", post=True)


def _gorevler(conn: sqlite3.Connection, k: sqlite3.Row) -> list[tuple[str, str]]:
    if k["rol"] == "yonetici":
        return [(r[0], "") for r in conn.execute("SELECT DISTINCT sinif FROM ogrenci ORDER BY sinif")]
    return yetki.ogretmen_gorevleri(conn, k["id"])


def _havuz_dersleri(sinif: str) -> tuple[list[str], bool]:
    try:
        return kazanim.havuz_dersleri(sinif_seviyesi(sinif)), False
    except KaynakHatasi:
        return [], True


def _kazanimlar(conn: sqlite3.Connection, sinif: str, havuz_ders: str) -> list[dict]:
    if not havuz_ders or sinif_seviyesi(sinif) >= 12:  # 12. sınıf donduruldu
        return []
    try:
        return arena_soru.kazanimlar(sinif_seviyesi(sinif), havuz_ders, yasak=soru_bildirim.gizli_idler(conn))
    except KaynakHatasi:
        return []


@router.get("")
def form(
    request: Request, sinif: str = "", ders: str = "", havuz_ders: str = "",
    k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    gorevler = _gorevler(conn, k)
    if not gorevler:
        return render(request, "ogretmen/hizli.html", gorevler=[], sinif="", ders="", havuz_dersleri=[], havuz_hata=False,
                      secili_havuz="", kazanimlar=[], adetler=etkinlik.ADETLER, sureler=etkinlik.SURELER)
    if not sinif:
        sinif, ders = gorevler[0]
    if (sinif, ders) not in gorevler:
        raise HTTPException(404)
    havuz, hata = _havuz_dersleri(sinif)
    secili = havuz_ders if havuz_ders in havuz else (tr_kucuk(ders) if tr_kucuk(ders) in havuz else "")
    return render(request, "ogretmen/hizli.html", gorevler=gorevler, sinif=sinif, ders=ders, havuz_dersleri=havuz,
                  havuz_hata=hata, secili_havuz=secili, kazanimlar=_kazanimlar(conn, sinif, secili),
                  adetler=etkinlik.ADETLER, sureler=etkinlik.SURELER)


@router.post("")
async def ata(request: Request, arka: BackgroundTasks, k=Depends(OGRETMEN_POST), conn: sqlite3.Connection = Depends(db_conn)):
    f = await request.form()
    sinif = str(f.get("sinif", "")).strip()
    havuz_ders = str(f.get("havuz_ders", "")).strip()
    ders = str(f.get("ders", "")).strip()
    if k["rol"] == "yonetici":
        ders = ders or havuz_ders  # yöneticinin görevi yok: havuz dersi adı kullanılır
        yetkili = bool(sinif) and conn.execute("SELECT 1 FROM ogrenci WHERE sinif = ?", (sinif,)).fetchone() is not None
    else:
        yetkili = bool(sinif and ders) and yetki.sinif_ders_yetkili(conn, k, sinif, ders)
    if not yetkili:
        raise HTTPException(404)
    try:
        adet = int(str(f.get("adet", "")))
    except ValueError:
        raise HTTPException(400, "Geçersiz soru sayısı.") from None
    secilen = None
    if str(f.get("kazanim", "")).strip():
        try:
            kid = int(str(f.get("kazanim")))
        except ValueError:
            raise HTTPException(400, "Geçersiz kazanım.") from None
        secilen = next((x for x in _kazanimlar(conn, sinif, havuz_ders) if x["id"] == kid), None)
        if secilen is None:
            raise HTTPException(400, "Bu ders için seçilen kazanımda yeterli soru yok.")
    onceki_son = conn.execute("SELECT COALESCE(MAX(id), 0) FROM odev").fetchone()[0]
    try:
        odev_id = etkinlik.hizli_ata(
            conn, k["id"], sinif, ders, havuz_ders, adet, str(f.get("sure", "")), str(f.get("not", "")), secilen
        )
    except (etkinlik.EtkinlikHatasi, KaynakHatasi) as e:
        raise HTTPException(400, str(e)) from e
    analitik.istekten(request, "ogretmen_hizli_etkinlik", str(odev_id))
    if odev_id > onceki_son:  # çift dokunmada eski ödev döner (TEKRAR_SN): ikinci kez bildirme
        arka.add_task(push.odev_bildir, sinif, k["id"])
    return RedirectResponse(f"/ogretmen/odev/{odev_id}", status_code=303)
