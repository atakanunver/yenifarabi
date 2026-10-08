"""Yoklama Panosu — FastAPI giriş noktası.

Çalıştırma: `uvicorn app:app --host 0.0.0.0 --port 8010` (dashboard/
dizininden, kendi venv'i içinde). Farabi'nin server/main.py'sinden
BAĞIMSIZ — bkz. CLAUDE.md.
"""

import asyncio
import re
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.gzip import GZipMiddleware

import admin
import ajan_api
import okul_bilgisi
import auth
import db
import ders_programi
import kazanim_rapor
import servis_yonetimi
import sistem_durumu
import ssh_istemci
import sunucular
import tahta_api
import uzaktan_baslat
import uzaktan_yonetim
import yoklayici
import zil

templates = Jinja2Templates(directory="templates")
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk

_SINIF_AD_RE = re.compile(r"^(\d+)-([A-Za-z]+)$")


def _sinif_sira_anahtari(ad: str) -> tuple[int, int, str]:
    """'9-A' gibi adları sayı+şubeye göre sıralar; 'lab1' gibi eşleşmeyenler
    sona, kendi aralarında alfabetik (bkz. plan.md Faz 3)."""
    eslesme = _SINIF_AD_RE.match(ad)
    if eslesme:
        return (0, int(eslesme.group(1)), eslesme.group(2))
    return (1, 0, ad)

POLLING_ARALIGI_SN = 120
# Nabzı taze tahtalar (tahta istemcisi kurulu) kısmi turlarda SSH ile
# taranmaz; saatte bir yine de tam SSH taraması yapılır — istemcinin
# kaçırdığı bir kayıt olursa yedek/uzlaştırma yolu (2026-10-06).
TAM_TARAMA_ARALIGI_SN = 3600


async def _polling_dongusu() -> None:
    """Pazartesi-Cuma, ilk dersten ~20dk önce - son dersten ~20dk sonra
    arasında bugünün tarihini periyodik tarar. Pencere dışında SSH trafiği
    yok."""
    son_tam_tarama = 0.0
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
            simdi_mono = asyncio.get_running_loop().time()
            tam = simdi_mono - son_tam_tarama >= TAM_TARAMA_ARALIGI_SN
            try:
                await yoklayici.bir_tur_calistir(
                    conn, zil.simdi_istanbul().date().isoformat(), tam_tarama=tam
                )
                if tam:
                    son_tam_tarama = simdi_mono
            except Exception as e:  # poller asla tüm servisi düşürmemeli
                print(f"[polling] hata: {e}")
            finally:
                conn.close()
        await asyncio.sleep(POLLING_ARALIGI_SN)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.semayi_kur()
    gorev = asyncio.create_task(_polling_dongusu())
    # Sistem Durumu ölçümleri tek arka plan görevinde toplanır; /api/sistem-durumu
    # önbellekten okur (bkz. sistem_durumu.py docstring'i).
    durum_gorevi = asyncio.create_task(sistem_durumu.toplayici_dongusu())
    yield
    gorev.cancel()
    durum_gorevi.cancel()


app = FastAPI(lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(admin.router)
app.include_router(uzaktan_yonetim.router)
app.include_router(ajan_api.router)
app.include_router(okul_bilgisi.router)
app.include_router(sunucular.router)
app.include_router(tahta_api.router)
app.include_router(kazanim_rapor.router)
app.include_router(servis_yonetimi.router)


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


@app.get("/sms-git")
async def sms_git(request: Request):
    """smssistemi'ne kısa ömürlü imzalı bir token'la yönlendirir — dashboard'da
    zaten oturum açmış kullanıcı orada tekrar şifre girmesin diye."""
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            return RedirectResponse("/giris", status_code=303)
    finally:
        conn.close()
    zaman, imza = auth.sms_sso_token()
    return RedirectResponse(f"http://farabi.local:8020/sso?t={zaman}&s={imza}", status_code=303)


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


def _durum_satirlari(conn, hedef_tarih: date) -> list[dict]:
    """Verilen tarihin yoklama önbelleği satırları (+ ders_kisa_adi) —
    /api/durum ve /api/ajan/yoklama ortak kullanır."""
    satirlar = conn.execute(
        "SELECT sinif, ders_no, durum, yok_isimleri, izinli_isimleri, "
        "kaynak_tahta, kaydedilme_saati, guncelleme_zamani "
        "FROM yoklama_onbellek WHERE tarih = ?",
        (hedef_tarih.isoformat(),),
    ).fetchall()
    sonuc = []
    for s in satirlar:
        satir = dict(s)
        satir["ders_kisa_adi"] = ders_programi.ders_kisa_adi(
            satir["sinif"], hedef_tarih, satir["ders_no"]
        )
        sonuc.append(satir)
    return sonuc


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
        hedef_tarih = date.fromisoformat(hedef)
        sonuc = _durum_satirlari(conn, hedef_tarih)
    finally:
        conn.close()
    return JSONResponse({"tarih": hedef, "satirlar": sonuc})


@app.get("/api/sistem-durumu")
async def api_sistem_durumu(request: Request, trend: int = 0):
    """Salt okunur. `?trend=1` son 30 dk'lık ring buffer'ı da ekler (yalnızca
    Sistem Durumu sayfası ister; kenar.js'in 30 sn'lik rozet çağrısı hafif kalır)."""
    conn = db.baglanti()
    try:
        if not _oturum_gerekli(request, conn):
            raise HTTPException(401, "Oturum geçersiz.")
    finally:
        conn.close()
    return JSONResponse(await sistem_durumu.durum_topla(trend=bool(trend)))


@app.get("/sistem-durumu", response_class=HTMLResponse)
async def sistem_durumu_sayfa(request: Request):
    conn = db.baglanti()
    try:
        token = request.cookies.get(auth.COOKIE_ADI)
        if not auth.oturum_gecerli_mi(conn, token):
            return RedirectResponse("/giris", status_code=303)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "sistem_durumu.html", {})


@app.get("/dogum")
async def dogum_sayfa(request: Request):
    """smssistemi'nin /dogum-gunleri sayfasına kısa ömürlü imzalı token'la yönlendirir."""
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            return RedirectResponse("/giris", status_code=303)
    finally:
        conn.close()
    zaman, imza = auth.sms_sso_token()
    return RedirectResponse(
        f"http://farabi.local:8020/sso?t={zaman}&s={imza}&hedef=/dogum-gunleri",
        status_code=303,
    )


@app.get("/otomasyon-git")
async def otomasyon_git(request: Request):
    """smssistemi'nin /otomasyon sayfasına kısa ömürlü imzalı token'la yönlendirir."""
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            return RedirectResponse("/giris", status_code=303)
    finally:
        conn.close()
    zaman, imza = auth.sms_sso_token()
    return RedirectResponse(
        f"http://farabi.local:8020/sso?t={zaman}&s={imza}&hedef=/otomasyon",
        status_code=303,
    )


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
