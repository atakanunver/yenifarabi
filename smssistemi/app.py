"""SMS Sistemi — FastAPI giriş noktası.

Çalıştırma: `uvicorn app:app --host 0.0.0.0 --port 8020` (smssistemi/
dizininden, kendi venv'i içinde). tahtayoklama/dashboard'dan BAĞIMSIZ —
bkz. docs/superpowers/specs/2026-09-19-smssistemi-design.md.
"""

import threading
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import auth
import db
import gonderim
import sms_gonderici

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

_DURDUR_BAYRAKLARI: dict[str, threading.Event] = {}


@app.on_event("startup")
def _baslangic() -> None:
    db.semayi_kur()


def _oturum_sarti(request: Request, conn) -> None:
    if not auth.oturum_gecerli_mi(conn, request.cookies.get(auth.COOKIE_ADI)):
        raise HTTPException(401, "Oturum geçersiz.")


def _oturum_yoksa_giris(request: Request, conn) -> RedirectResponse | None:
    """Tarayıcıda açılan sayfalarda (API/form-POST değil) oturum yoksa ham
    401 JSON yerine /giris'e yönlendirir — dashboard'daki auth.oturum_gecerli_mi
    + RedirectResponse deseniyle aynı."""
    if not auth.oturum_gecerli_mi(conn, request.cookies.get(auth.COOKIE_ADI)):
        return RedirectResponse("/giris", status_code=303)
    return None


@app.get("/giris", response_class=HTMLResponse)
async def giris_formu(request: Request):
    return templates.TemplateResponse(request, "giris.html", {"hata": None})


@app.post("/giris")
async def giris_gonder(request: Request, sifre: str = Form(...)):
    if not auth.giris_dene(sifre):
        return templates.TemplateResponse(
            request, "giris.html", {"hata": "Şifre yanlış."}, status_code=401
        )
    conn = db.baglanti()
    try:
        token = auth.oturum_olustur(conn)
    finally:
        conn.close()
    yanit = RedirectResponse("/", status_code=303)
    yanit.set_cookie(auth.COOKIE_ADI, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return yanit


@app.get("/sso")
async def sso_giris(request: Request, t: str, s: str):
    """Dashboard'daki /sms-git'ten gelen kısa ömürlü imzalı token'la
    giriş — kullanıcı dashboard'da zaten kimlik doğrulamışsa smssistemi
    şifresini tekrar girmez."""
    if not auth.sso_dogrula(t, s):
        return RedirectResponse("/giris", status_code=303)
    conn = db.baglanti()
    try:
        token = auth.oturum_olustur(conn)
    finally:
        conn.close()
    yanit = RedirectResponse("/", status_code=303)
    yanit.set_cookie(auth.COOKIE_ADI, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return yanit


@app.post("/cikis")
async def cikis(request: Request):
    token = request.cookies.get(auth.COOKIE_ADI)
    conn = db.baglanti()
    try:
        if token:
            auth.oturum_sil(conn, token)
    finally:
        conn.close()
    yanit = RedirectResponse("/giris", status_code=303)
    yanit.delete_cookie(auth.COOKIE_ADI)
    return yanit


@app.get("/", response_class=HTMLResponse)
async def anasayfa(request: Request):
    conn = db.baglanti()
    try:
        yonlendirme = _oturum_yoksa_giris(request, conn)
        siniflar = db.siniflar_listele(conn) if yonlendirme is None else None
    finally:
        conn.close()
    if yonlendirme is not None:
        return yonlendirme
    return templates.TemplateResponse(
        request, "gonder.html", {"hata": None, "onizleme_numaralar": "", "siniflar": siniflar}
    )


@app.post("/gonder")
async def gonder(
    request: Request,
    numaralar: str = Form(""),
    mesaj: str = Form(...),
    bekleme_sn: float = Form(2.0),
    csv_dosya: UploadFile | None = File(None),
):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        siniflar = db.siniflar_listele(conn)
    finally:
        conn.close()

    satirlar = numaralar
    if csv_dosya is not None and csv_dosya.filename:
        icerik = await csv_dosya.read()
        yuklenen = gonderim.csv_ayristir(icerik)
        satirlar = "\n".join(f"{isim},{tel}" if isim else tel for isim, tel in yuklenen)

    gecerli, _gecersiz = gonderim.metinden_ayristir(satirlar)
    if not gecerli:
        return templates.TemplateResponse(
            request,
            "gonder.html",
            {"hata": "Gönderilecek geçerli numara yok.", "onizleme_numaralar": satirlar, "siniflar": siniflar},
            status_code=400,
        )

    gonderim_id = uuid.uuid4().hex[:12]
    kisiler = [(isim, tel, gonderim.kisisellestir(mesaj, isim)) for isim, tel in gecerli]
    thread = threading.Thread(
        target=_gonderim_calistir, args=(gonderim_id, kisiler, bekleme_sn), daemon=True
    )
    thread.start()
    return RedirectResponse(f"/durum/{gonderim_id}", status_code=303)


def _gonderim_calistir(gonderim_id: str, kisiler: list[tuple[str, str, str]], bekleme_sn: float) -> None:
    bayrak = threading.Event()
    _DURDUR_BAYRAKLARI[gonderim_id] = bayrak
    conn = db.baglanti()

    def kaydet(isim: str, telefon: str, mesaj: str, durum: str, hata_metni: str | None) -> None:
        db.gonderim_kaydet(conn, gonderim_id, isim, telefon, mesaj, durum, hata_metni)

    try:
        ayarlar = sms_gonderici.modem_ayarlarini_yukle()
        sms_gonderici.toplu_gonder(ayarlar, kisiler, kaydet, bayrak, bekleme_sn)
    finally:
        conn.close()
        _DURDUR_BAYRAKLARI.pop(gonderim_id, None)


@app.post("/durdur/{gonderim_id}")
async def durdur(request: Request, gonderim_id: str):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
    finally:
        conn.close()
    bayrak = _DURDUR_BAYRAKLARI.get(gonderim_id)
    if bayrak is not None:
        bayrak.set()
    return JSONResponse({"durduruldu": bayrak is not None})


@app.post("/tekrar-gonder/{gonderim_id}")
async def tekrar_gonder(request: Request, gonderim_id: str, bekleme_sn: float = Form(2.0)):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        basarisizlar = db.gonderim_basarisizlari(conn, gonderim_id)
    finally:
        conn.close()

    if not basarisizlar:
        return RedirectResponse(f"/durum/{gonderim_id}", status_code=303)

    yeni_gonderim_id = uuid.uuid4().hex[:12]
    thread = threading.Thread(
        target=_gonderim_calistir, args=(yeni_gonderim_id, basarisizlar, bekleme_sn), daemon=True
    )
    thread.start()
    return RedirectResponse(f"/durum/{yeni_gonderim_id}", status_code=303)


@app.get("/durum/{gonderim_id}", response_class=HTMLResponse)
async def durum_sayfasi(request: Request, gonderim_id: str):
    conn = db.baglanti()
    try:
        yonlendirme = _oturum_yoksa_giris(request, conn)
    finally:
        conn.close()
    if yonlendirme is not None:
        return yonlendirme
    return templates.TemplateResponse(request, "durum.html", {"gonderim_id": gonderim_id})


@app.get("/api/durum/{gonderim_id}")
async def durum_api(request: Request, gonderim_id: str):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        satirlar = db.gonderim_satirlari(conn, gonderim_id)
    finally:
        conn.close()
    devam_ediyor = gonderim_id in _DURDUR_BAYRAKLARI
    return JSONResponse({"satirlar": satirlar, "devam_ediyor": devam_ediyor})


@app.get("/kayitlar", response_class=HTMLResponse)
async def kayitlar(request: Request):
    conn = db.baglanti()
    try:
        yonlendirme = _oturum_yoksa_giris(request, conn)
        ozetler = db.gonderim_ozetleri(conn) if yonlendirme is None else None
    finally:
        conn.close()
    if yonlendirme is not None:
        return yonlendirme
    return templates.TemplateResponse(request, "kayitlar.html", {"ozetler": ozetler})


# --- Rehber ----------------------------------------------------------------


@app.get("/rehber", response_class=HTMLResponse)
async def rehber(request: Request, sinif_id: int | None = None, tur: str | None = None, mesaj: str | None = None):
    conn = db.baglanti()
    try:
        yonlendirme = _oturum_yoksa_giris(request, conn)
        if yonlendirme is not None:
            return yonlendirme
        siniflar = db.siniflar_listele(conn)
        kisiler = db.kisiler_listele(conn, sinif_id=sinif_id, tur=tur)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "rehber.html",
        {
            "siniflar": siniflar,
            "kisiler": kisiler,
            "secili_sinif_id": sinif_id,
            "secili_tur": tur,
            "mesaj": mesaj,
        },
    )


@app.post("/rehber/kisi/ekle")
async def rehber_kisi_ekle(
    request: Request,
    ad_soyad: str = Form(...),
    telefon: str = Form(""),
    sinif_id: int = Form(...),
    tur: str = Form(...),
):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        tel = gonderim.normalize_phone(telefon) if telefon.strip() else None
        db.kisi_ekle(conn, ad_soyad.strip(), tel, sinif_id, tur)
    finally:
        conn.close()
    return RedirectResponse(f"/rehber?sinif_id={sinif_id}&tur={tur}", status_code=303)


@app.post("/rehber/kisi/{kisi_id}/duzenle")
async def rehber_kisi_duzenle(
    request: Request,
    kisi_id: int,
    ad_soyad: str = Form(...),
    telefon: str = Form(""),
    sinif_id: int = Form(...),
    tur: str = Form(...),
):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        tel = gonderim.normalize_phone(telefon) if telefon.strip() else None
        db.kisi_guncelle(conn, kisi_id, ad_soyad.strip(), tel, sinif_id, tur)
    finally:
        conn.close()
    return RedirectResponse(f"/rehber?sinif_id={sinif_id}&tur={tur}", status_code=303)


@app.post("/rehber/kisi/{kisi_id}/sil")
async def rehber_kisi_sil(request: Request, kisi_id: int, sinif_id: int = Form(...), tur: str = Form(...)):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        db.kisi_sil(conn, kisi_id)
    finally:
        conn.close()
    return RedirectResponse(f"/rehber?sinif_id={sinif_id}&tur={tur}", status_code=303)


@app.post("/rehber/sinif/ekle")
async def rehber_sinif_ekle(request: Request, ad: str = Form(...)):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        db.sinif_ekle(conn, ad.strip())
    finally:
        conn.close()
    return RedirectResponse("/rehber", status_code=303)


@app.post("/rehber/sinif/{sinif_id}/sil")
async def rehber_sinif_sil(request: Request, sinif_id: int):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        basarili = db.sinif_sil(conn, sinif_id)
    finally:
        conn.close()
    mesaj = "" if basarili else "sinif_kullanimda"
    return RedirectResponse(f"/rehber?mesaj={mesaj}", status_code=303)


@app.post("/rehber/yukle")
async def rehber_yukle(
    request: Request,
    sinif_id: int = Form(...),
    tur: str = Form(...),
    dosya: UploadFile = File(...),
):
    ad_kucuk = (dosya.filename or "").lower()
    if not ad_kucuk.endswith((".csv", ".xlsx", ".xlsm")):
        return RedirectResponse("/rehber?mesaj=desteklenmeyen_format", status_code=303)

    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        icerik = await dosya.read()
        satirlar = gonderim.rehber_dosyasindan_oku(dosya.filename, icerik)

        eklendi = guncellendi = atlandi = 0
        for satir in satirlar:
            ad_soyad = satir["ad_soyad"]
            if not ad_soyad:
                atlandi += 1
                continue
            hedef_sinif_id = sinif_id
            if satir["sinif"]:
                hedef_sinif_id = db.sinif_ekle(conn, satir["sinif"])
            telefon = satir["telefon"] or None

            var_olan = db.kisi_bul_isimle(conn, ad_soyad, hedef_sinif_id, tur)
            if var_olan is not None:
                if telefon and telefon != var_olan["telefon"]:
                    db.kisi_guncelle(conn, var_olan["id"], ad_soyad, telefon, hedef_sinif_id, tur)
                    guncellendi += 1
                else:
                    atlandi += 1
            else:
                db.kisi_ekle(conn, ad_soyad, telefon, hedef_sinif_id, tur)
                eklendi += 1
    finally:
        conn.close()

    return RedirectResponse(
        f"/rehber?sinif_id={sinif_id}&tur={tur}&mesaj=yuklendi:{eklendi}:{guncellendi}:{atlandi}",
        status_code=303,
    )


@app.get("/api/rehber/telefonlar")
async def rehber_telefonlar(request: Request, sinif_id: int, tur: str):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        kisiler = db.kisiler_telefonlu(conn, sinif_id, tur)
    finally:
        conn.close()
    return JSONResponse({"kisiler": [{"ad_soyad": a, "telefon": t} for a, t in kisiler]})
