"""Yoklama Panosu — FastAPI giriş noktası.

Çalıştırma: `uvicorn app:app --host 0.0.0.0 --port 8010` (dashboard/
dizininden, kendi venv'i içinde). Farabi'nin server/main.py'sinden
BAĞIMSIZ — bkz. CLAUDE.md.
"""

import asyncio
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import admin
import auth
import db
import ssh_istemci
import uzaktan_baslat
import yoklayici
import zil

templates = Jinja2Templates(directory="templates")

_SINIF_AD_RE = re.compile(r"^(\d+)-([A-Za-z]+)$")


def _sinif_sira_anahtari(ad: str) -> tuple[int, int, str]:
    """'9-A' gibi adları sayı+şubeye göre sıralar; 'lab1' gibi eşleşmeyenler
    sona, kendi aralarında alfabetik (bkz. plan.md Faz 3)."""
    eslesme = _SINIF_AD_RE.match(ad)
    if eslesme:
        return (0, int(eslesme.group(1)), eslesme.group(2))
    return (1, 0, ad)

POLLING_ARALIGI_SN = 120


async def _polling_dongusu() -> None:
    """Pazartesi-Cuma, ilk dersten ~20dk önce - son dersten ~20dk sonra
    arasında bugünün tarihini periyodik tarar. Pencere dışında SSH trafiği
    yok."""
    while True:
        simdi = zil.simdi_istanbul()
        ilk = zil.ilk_ders_saati()
        son = zil.son_ders_bitis_saati()
        pencerede_mi = (
            zil.okul_gunu_mu(simdi.date())
            and ilk is not None and son is not None
            and (simdi.hour * 60 + simdi.minute) >= (ilk.hour * 60 + ilk.minute) - 20
            and (simdi.hour * 60 + simdi.minute) <= (son.hour * 60 + son.minute) + 20
        )
        if pencerede_mi:
            conn = db.baglanti()
            try:
                await yoklayici.bir_tur_calistir(conn, zil.simdi_istanbul().date().isoformat())
            except Exception as e:  # poller asla tüm servisi düşürmemeli
                print(f"[polling] hata: {e}")
            finally:
                conn.close()
        await asyncio.sleep(POLLING_ARALIGI_SN)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.semayi_kur()
    gorev = asyncio.create_task(_polling_dongusu())
    yield
    gorev.cancel()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(admin.router)


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
    yanit.set_cookie(
        auth.COOKIE_ADI, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30
    )
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


def _oturum_gerekli(request: Request, conn) -> bool:
    return auth.dogrula(request, conn)


@app.post("/api/yenile")
async def api_yenile(request: Request, tarih: str | None = None):
    conn = db.baglanti()
    try:
        if not _oturum_gerekli(request, conn):
            raise HTTPException(401, "Oturum geçersiz.")
        hedef = tarih or zil.simdi_istanbul().date().isoformat()
        try:
            ssh_istemci.tarih_dogrula(hedef)
        except ValueError:
            raise HTTPException(400, "Geçersiz tarih formatı, YYYY-MM-DD bekleniyor.")
        await yoklayici.bir_tur_calistir(conn, hedef)
    finally:
        conn.close()
    return JSONResponse({"basarili": True, "tarih": hedef})


@app.get("/api/durum")
async def api_durum(request: Request, tarih: str | None = None):
    conn = db.baglanti()
    try:
        if not _oturum_gerekli(request, conn):
            raise HTTPException(401, "Oturum geçersiz.")
        hedef = tarih or zil.simdi_istanbul().date().isoformat()
        try:
            ssh_istemci.tarih_dogrula(hedef)
        except ValueError:
            raise HTTPException(400, "Geçersiz tarih formatı, YYYY-MM-DD bekleniyor.")
        satirlar = conn.execute(
            "SELECT sinif, ders_no, durum, yok_isimleri, izinli_isimleri, "
            "kaynak_tahta, kaydedilme_saati, guncelleme_zamani "
            "FROM yoklama_onbellek WHERE tarih = ?",
            (hedef,),
        ).fetchall()
    finally:
        conn.close()
    return JSONResponse({"tarih": hedef, "satirlar": [dict(s) for s in satirlar]})


@app.post("/api/tahta/{tahta_id}/baslat")
async def api_tahta_baslat(request: Request, tahta_id: int):
    conn = db.baglanti()
    try:
        if not _oturum_gerekli(request, conn):
            raise HTTPException(401, "Oturum geçersiz.")
        satir = conn.execute(
            "SELECT id, ad, ip, ssh_kullanici, python_yolu FROM tahtalar WHERE id = ? AND aktif = 1",
            (tahta_id,),
        ).fetchone()
        if satir is None:
            raise HTTPException(404, "Tahta bulunamadı.")
        tahta = dict(satir)
    finally:
        conn.close()

    sonuc = await uzaktan_baslat.baslat(tahta)
    return JSONResponse(sonuc, status_code=200 if sonuc["basarili"] else 502)


@app.get("/", response_class=HTMLResponse)
async def ana_sayfa(request: Request, tarih: str | None = None):
    conn = db.baglanti()
    try:
        token = request.cookies.get(auth.COOKIE_ADI)
        if not auth.oturum_gecerli_mi(conn, token):
            return RedirectResponse("/giris", status_code=303)

        bugun = zil.simdi_istanbul().date().isoformat()
        hedef = tarih or bugun
        try:
            ssh_istemci.tarih_dogrula(hedef)
        except ValueError:
            hedef = bugun
        if hedef > bugun:  # gelecek tarih anlamsız — bugüne kelepçele
            hedef = bugun

        siniflar = [dict(r) for r in conn.execute(
            "SELECT id, ad FROM siniflar WHERE aktif = 1"
        )]
        siniflar.sort(key=lambda s: _sinif_sira_anahtari(s["ad"]))

        # Bir sınıfa bağlı TEK bir tahta varsa, "Yoklama alınmadı" hücresinin
        # tıklama hedefi o tahtanın id'si olur (Faz 4). Sıfır ya da birden
        # fazla tahta bağlıysa tıklanabilir hedef yok (çok nadir bir geçiş
        # durumu — bkz. plan.md).
        sinif_tahta: dict[int, int] = {}
        for r in conn.execute(
            "SELECT sinif_id, id, COUNT(*) OVER (PARTITION BY sinif_id) AS n "
            "FROM tahtalar WHERE sinif_id IS NOT NULL AND aktif = 1"
        ):
            if r["n"] == 1:
                sinif_tahta[r["sinif_id"]] = r["id"]

        ders_saatleri = zil.ders_saatleri()
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "pano.html",
        {
            "tarih": hedef,
            "bugun": bugun,
            "siniflar": siniflar,
            "sinif_tahta": sinif_tahta,
            "ders_saatleri": ders_saatleri,
        },
    )
