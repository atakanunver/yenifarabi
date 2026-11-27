"""Veli izin talebi rotaları: veli formu + talepleri, yönetici listesi/detayı/kararı, LAN-only /api/izinler."""

import hmac
import sqlite3
from datetime import date

import dosyalar
import izin
import yetki
import zaman
from ayarlar import AYAR
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
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from rotalar.belge_sinav import _oku
from rotalar.pano import _lan_mi
from rotalar.veli import _cocuk

router = APIRouter()
VELI = rol("veli")
VELI_POST = rol("veli", post=True)
YONETICI = rol("yonetici")
YONETICI_POST = rol("yonetici", post=True)
_YONETICI = Depends(YONETICI)
_YONETICI_POST = Depends(YONETICI_POST)
_DB = Depends(db_conn)


def _form_bagi(conn: sqlite3.Connection, k, c, **ek):
    return {
        "cocuk": c,
        "talepler": izin.veli_talepleri(conn, k["id"], c["id"]),
        "hak": izin.hak_ozeti(conn, c["id"]),
        "nedenler": izin.NEDENLER,
        "bugun": zaman.simdi().strftime("%Y-%m-%d"),
        "metin_azami": izin.METIN_AZAMI,
        **ek,
    }


@router.get("/veli/izin")
def veli_izin(
    request: Request,
    ogr: int | None = None,
    gonderildi: str = "",
    k=Depends(VELI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    cocuklar, c = _cocuk(request, conn, k, ogr, "veli_izin")
    if c is None:
        raise HTTPException(404)
    return render(request, "veli/izin.html", cocuklar=cocuklar, gonderildi=gonderildi == "1", **_form_bagi(conn, k, c))


@router.post("/veli/izin")
async def veli_izin_gonder(
    request: Request,
    arka: BackgroundTasks,
    ogr: int = Form(...),
    baslangic: str = Form(""),
    bitis: str = Form(""),
    neden_tur: str = Form(""),
    neden_metin: str = Form(""),
    ek: UploadFile | None = None,
    k=Depends(VELI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    cocuklar, c = _cocuk(request, conn, k, ogr, "veli_izin")
    if c is None:
        raise HTTPException(404)
    ek_veri = await _oku(ek, dosyalar.PLAN_AZAMI) if ek is not None and ek.filename else None
    try:
        talep_id = izin.olustur(conn, k["id"], c["id"], baslangic, bitis, neden_tur, neden_metin, ek_veri)
    except izin.IzinHatasi as e:
        if e.kod == 404:
            raise HTTPException(404) from None
        girdi = {"baslangic": baslangic, "bitis": bitis, "neden_tur": neden_tur, "neden_metin": neden_metin}
        return render(
            request, "veli/izin.html", e.kod if e.kod == 429 else 422,
            cocuklar=cocuklar, hata=e.mesaj, girdi=girdi, **_form_bagi(conn, k, c),
        )
    arka.add_task(izin.talep_bildir, talep_id)
    return RedirectResponse(f"/veli/izin?ogr={c['id']}&gonderildi=1", status_code=303)


@router.get("/veli/izin/gun")
def veli_izin_gun(baslangic: str = "", bitis: str = "", k=Depends(VELI)):
    """Formdaki canlı gün sayısı (yalnız gösterim; kayıtta sunucu yeniden hesaplar)."""
    try:
        bas, bit = izin.tarih_coz(baslangic), izin.tarih_coz(bitis)
    except izin.IzinHatasi:
        return JSONResponse({"gun": None})
    if bas > bit or (bit - bas).days + 1 > izin.ARALIK_AZAMI:
        return JSONResponse({"gun": None})
    return JSONResponse({"gun": izin.is_gunu(bas, bit)})


def _dosya_yaniti(depo: str | None, tur: str | None, ad: str):
    if not depo or not tur:
        raise HTTPException(404)
    try:
        yol = dosyalar.yol(izin.EK_KLASOR, depo)
    except dosyalar.DosyaHatasi:
        raise HTTPException(404) from None
    if not yol.exists():
        raise HTTPException(404)
    return FileResponse(
        yol,
        media_type=dosyalar.MIME[tur],
        content_disposition_type="inline",
        filename=f"{ad}.{tur}",
        headers={"Cache-Control": "private, no-store"},
    )


def _talep_dosyasi(d: dict, ne: str):
    if ne == "pdf":
        return _dosya_yaniti(d["pdf_depo"], "pdf", f"izin-dilekcesi-{d['id']}")
    if ne == "ek":
        return _dosya_yaniti(d["ek_depo"], d["ek_tur"], f"izin-eki-{d['id']}")
    raise HTTPException(404)


@router.get("/veli/izin/{talep_id}/{ne}")
def veli_izin_dosya(talep_id: int, ne: str, k=Depends(VELI), conn: sqlite3.Connection = Depends(db_conn)):
    d = izin.veli_detay(conn, k["id"], talep_id)
    if d is None:
        raise HTTPException(404)
    return _talep_dosyasi(d, ne)


# --- yönetici ---


@router.get("/yonetici/izinler")
def yonetici_izinler(request: Request, k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)):
    return render(
        request, "yonetici/izinler.html", talepler=izin.liste(conn), bekleyen=izin.bekleyen_sayisi(conn)
    )


def _ekle_formu(request: Request, conn: sqlite3.Connection, girdi: dict, hata: str = "", durum: int = 200):
    ogrenciler: dict[str, list[dict]] = {}
    for r in conn.execute("SELECT id, okul_no, ad_soyad, sinif FROM ogrenci ORDER BY sinif, okul_no"):
        ogrenciler.setdefault(r["sinif"], []).append({"id": r["id"], "ad": f"{r['okul_no']} - {r['ad_soyad']}"})
    return render(
        request, "yonetici/izinler_ekle.html", durum, ogrenciler=ogrenciler, nedenler=izin.NEDENLER,
        bugun=zaman.simdi().strftime("%Y-%m-%d"), metin_azami=izin.METIN_AZAMI, girdi=girdi, hata=hata,
    )


@router.get("/yonetici/izinler/ekle")
def yonetici_izin_ekle_formu(request: Request, k=_YONETICI, conn: sqlite3.Connection = _DB):
    return _ekle_formu(request, conn, {})


@router.post("/yonetici/izinler/ekle")
def yonetici_izin_ekle(
    request: Request,
    ogrenci: int = Form(0),
    baslangic: str = Form(""),
    bitis: str = Form(""),
    neden_tur: str = Form(""),
    neden_metin: str = Form(""),
    k=_YONETICI_POST,
    conn: sqlite3.Connection = _DB,
):
    try:
        talep_id = izin.yonetici_ekle(conn, k["id"], ogrenci, baslangic, bitis, neden_tur, neden_metin)
    except izin.IzinHatasi as e:
        girdi = {"ogrenci": ogrenci, "baslangic": baslangic, "bitis": bitis, "neden_tur": neden_tur, "neden_metin": neden_metin}
        mesaj = "Öğrenci seçin." if e.kod == 404 else e.mesaj
        return _ekle_formu(request, conn, girdi, mesaj, 422)
    yetki.erisim_kaydet(conn, k, f"izin_ekle:{talep_id}", ogrenci, istemci_ip(request))
    return RedirectResponse("/yonetici/izinler", status_code=303)


def _yonetici_talep(conn: sqlite3.Connection, talep_id: int) -> dict:
    d = izin.detay(conn, talep_id)
    if d is None:
        raise HTTPException(404)
    return d


@router.get("/yonetici/izinler/{talep_id}")
def yonetici_izin_detay(
    talep_id: int, request: Request, hata: str = "", k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)
):
    d = _yonetici_talep(conn, talep_id)
    yetki.erisim_kaydet(conn, k, f"izin:{talep_id}", d["ogrenci_id"], istemci_ip(request))
    t = date.fromisoformat(d["baslangic"])
    hak = izin.hak_ozeti(conn, d["ogrenci_id"], t, ek=d["gun"] if d["durum"] == "bekliyor" else 0)
    mesaj = {"yanit": "Bu talep zaten yanıtlanmış."}.get(hata, "")  # URL'den metin yansıtılmaz
    return render(request, "yonetici/izinler_detay.html", t=d, hak=hak, hata=mesaj)


@router.get("/yonetici/izinler/{talep_id}/{ne}")
def yonetici_izin_dosya(
    talep_id: int, ne: str, request: Request, k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)
):
    d = _yonetici_talep(conn, talep_id)
    yanit = _talep_dosyasi(d, ne)
    yetki.erisim_kaydet(conn, k, f"izin_{ne}:{talep_id}", d["ogrenci_id"], istemci_ip(request))
    return yanit


@router.post("/yonetici/izinler/{talep_id}/karar")
def yonetici_izin_karar(
    talep_id: int,
    arka: BackgroundTasks,
    karar: str = Form(""),
    k=Depends(YONETICI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if karar not in ("onayla", "reddet"):
        raise HTTPException(400)
    try:
        izin.karar_ver(conn, talep_id, k["id"], karar == "onayla")
    except izin.IzinHatasi as e:
        if e.kod == 404:
            raise HTTPException(404) from None
        return RedirectResponse(f"/yonetici/izinler/{talep_id}?hata=yanit", status_code=303)
    arka.add_task(izin.sonuc_bildir, talep_id)
    return RedirectResponse(f"/yonetici/izinler/{talep_id}", status_code=303)


@router.post("/yonetici/izinler/{talep_id}/sil")
def yonetici_izin_sil(
    talep_id: int, request: Request, k=Depends(YONETICI_POST), conn: sqlite3.Connection = Depends(db_conn)
):
    try:
        d = izin.sil(conn, talep_id)
    except izin.IzinHatasi:
        raise HTTPException(404) from None
    yetki.erisim_kaydet(conn, k, f"izin_sil:{talep_id}", d["ogrenci_id"], istemci_ip(request))
    return RedirectResponse("/yonetici/izinler", status_code=303)


# --- LAN-only: tahtayoklama dashboard'u onaylı izinleri çeker ---


@router.get("/api/izinler")
def api_izinler(request: Request, tarih: str = "", conn: sqlite3.Connection = Depends(db_conn)):
    """Tünelden (cf-*/x-forwarded-*) gelirse ya da X-Izin-Anahtar yanlış/tanımsızsa 404."""
    if not _lan_mi(request):
        raise HTTPException(404)
    verilen = request.headers.get("x-izin-anahtar", "")
    if not AYAR.izin_anahtar or not hmac.compare_digest(verilen.encode(), AYAR.izin_anahtar.encode()):
        raise HTTPException(404)
    try:
        g = date.fromisoformat(tarih).isoformat()
    except ValueError:
        return JSONResponse({"tamam": False, "mesaj": "Geçersiz tarih."}, status_code=400)
    return JSONResponse({"tarih": g, "siniflar": izin.onayli_siniflar(conn, g)})
