"""SMS Sistemi — FastAPI giriş noktası.

Çalıştırma: `uvicorn app:app --host 0.0.0.0 --port 8020` (smssistemi/
dizininden, kendi venv'i içinde). tahtayoklama/dashboard'dan BAĞIMSIZ —
bkz. docs/superpowers/specs/2026-09-19-smssistemi-design.md.
"""

import asyncio
from contextlib import asynccontextmanager
import json
import logging
import sys
import threading
import urllib.request
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import auth
import db
import dogum_mantik
import gonderim
import arac_api
import otomasyon
import sms_gonderici
import yoklama_kaynak
import yoklama_mantik


def log_ayarla() -> None:
    """`smssistemi.*` logger'larını INFO düzeyinde stderr'e (→ journal) yazdırır.

    uvicorn yalnızca kendi logger'larını yapılandırır; kökte handler olmadığı
    için `smssistemi.otomasyon`'un INFO satırları ("tetikleniyor" dahil)
    kayboluyordu (2026-09-29). Kök logger'a dokunulmaz (başka kütüphanelerin
    gürültüsü girmesin), `propagate=False` ile de satırlar iki kez basılmaz.
    Zaman damgası yok — journal kendisi ekliyor. İdempotent.
    """
    lg = logging.getLogger("smssistemi")
    lg.setLevel(logging.INFO)
    lg.propagate = False
    if not lg.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(levelname)s: [%(name)s] %(message)s"))
        lg.addHandler(h)


log_ayarla()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.semayi_kur()
    arac_api.sema_kur()
    gorev = asyncio.create_task(otomasyon.otomasyon_arkaplan_dongusu())
    hatirlatma = asyncio.create_task(arac_api.hatirlatma_dongusu())  # Atos SMS aracı
    yield
    gorev.cancel()
    hatirlatma.cancel()


app = FastAPI(lifespan=lifespan)
app.include_router(arac_api.router)  # /api/arac/* — Atos SMS aracı (anahtarlı)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

_DURDUR_BAYRAKLARI: dict[str, threading.Event] = {}

OLLAMA_URL = "http://192.168.23.252:11434/api/generate"
OLLAMA_MODEL = "qwen3.8:27b"


def ollama_mesaj_duzelt(taslak: str) -> str:
    system_prompt = (
        "Sen bir okul idaresi için resmi SMS metni düzenleyicisisin.\n"
        "Görevin: Verilen taslak mesajı resmi, saygılı, net ve öz bir Türkçe okul-veli SMS metnine dönüştürmektir.\n\n"
        "KESİN KURALLAR:\n"
        "1. Yalnızca Türkçe yaz. Başka dilde asla bir şey yazma.\n"
        "2. Mesajda yalnızca iki yer tutucu kullanabilirsin: {isim} ve {ogrenci_adi}. Bunlar dışında süslü parantezli başka yer tutucu ASLA üretme, uydurma.\n"
        "3. Taslakta {isim} veya {ogrenci_adi} geçiyorsa olduğu gibi koru. Taslakta geçmiyorsa bile mesajın başına Sayın {isim} ekle ve öğrenciden bahsediyorsa {ogrenci_adi} kullan.\n"
        "4. Sadece ve sadece düzeltilmiş SMS metnini döndür. Tırnak, başlık, açıklama, yorum EKLEME.\n"
        "5. Mesaj kurumsal, net, kısa ve Türkçe dilbilgisine uygun olmalıdır.\n\n"
        "Örnek 1:\n"
        "Taslak: sayın {isim} {ogrenci_adi} yarın okula gelmesin kar tatili oldu\n"
        "Çıktı: Sayın {isim}, olumsuz hava koşulları sebebiyle yarın okulumuzda eğitime 1 gün ara verilmiştir. Öğrencimiz {ogrenci_adi} bilgisine rica olunur.\n\n"
        "Örnek 2:\n"
        "Taslak: {ogrenci_adi} velisi {isim} yarın saat 15te veli toplantısı var gelin\n"
        "Çıktı: Sayın {isim}, öğrencimiz {ogrenci_adi} ile ilgili veli toplantımız yarın saat 15.00'te okulumuzda yapılacaktır. Katılımınızı rica ederiz.\n\n"
        "Örnek 3:\n"
        "Taslak: sms atıldığı saat itibari ile öğrencimiz okula gelmemiştir\n"
        "Çıktı: Sayın {isim}, bu mesajın gönderildiği saat itibarıyla öğrencimiz {ogrenci_adi} okula gelmemiştir. Bilgilerinize sunarız."
    )
    payload = {
        "model": OLLAMA_MODEL,
        "system": system_prompt,
        "prompt": f"Taslak: {taslak}\nÇıktı:",
        "stream": False,
        "think": False,  # qwen3.x düşünmesin; 30 sn zaman aşımı (2026-10-02)
        "options": {"temperature": 0.2},
    }
    veri_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=veri_bytes, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        yanit = json.loads(resp.read().decode("utf-8"))
        duzeltilmis = yanit.get("response", "").strip()
        if (duzeltilmis.startswith('"') and duzeltilmis.endswith('"')) or (
            duzeltilmis.startswith("'") and duzeltilmis.endswith("'")
        ):
            duzeltilmis = duzeltilmis[1:-1].strip()
        return duzeltilmis




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
async def sso_giris(request: Request, t: str, s: str, hedef: str = "/"):
    """Dashboard'daki /sms-git'ten veya /dogum'dan gelen kısa ömürlü imzalı token'la
    giriş — kullanıcı dashboard'da zaten kimlik doğrulamışsa smssistemi
    şifresini tekrar girmez."""
    if not auth.sso_dogrula(t, s):
        return RedirectResponse("/giris", status_code=303)
    conn = db.baglanti()
    try:
        token = auth.oturum_olustur(conn)
    finally:
        conn.close()
    guvenli_hedef = hedef if (hedef.startswith("/") and not hedef.startswith("//")) else "/"
    yanit = RedirectResponse(guvenli_hedef, status_code=303)
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
    secilen_kisi_ids: str = Form(""),
    numaralar: str = Form(""),
    mesaj: str = Form(...),
    bekleme_sn: float = Form(2.0),
    csv_dosya: UploadFile | None = File(None),
):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        siniflar = db.siniflar_listele(conn)

        # JS panelinden gelen seçim öncelikli olur
        secilen_idler = [int(x) for x in secilen_kisi_ids.split(",") if x.strip().isdigit()]
        kisiler = []
        if secilen_idler:
            secilen_db_kisiler = db.kisiler_id_ile(conn, secilen_idler)
            for k in secilen_db_kisiler:
                isim = k["ad_soyad"]
                tel = k["telefon"]
                ogr_adi = k["ogrenci_ad"] if k["tur"] == "veli" else k["ad_soyad"]
                kisiler.append((isim, tel, gonderim.kisisellestir(mesaj, isim, ogr_adi or "")))
    finally:
        conn.close()

    # JS seçiminden alıcı gelmediyse serbest metin veya CSV'den oku
    if not kisiler:
        satirlar = numaralar
        if csv_dosya is not None and csv_dosya.filename:
            icerik = await csv_dosya.read()
            yuklenen = gonderim.csv_ayristir(icerik)
            satirlar = "\n".join(
                f"{item[0]},{item[1]},{item[2]}"
                if len(item) > 2
                else (f"{item[0]},{item[1]}" if item[0] else item[1])
                for item in yuklenen
            )

        gecerli, _gecersiz = gonderim.metinden_ayristir(satirlar)
        if not gecerli:
            return templates.TemplateResponse(
                request,
                "gonder.html",
                {"hata": "Gönderilecek geçerli numara yok.", "onizleme_numaralar": satirlar, "siniflar": siniflar},
                status_code=400,
            )

        for item in gecerli:
            isim = item[0]
            tel = item[1]
            ogr_adi = item[2] if len(item) > 2 else ""
            kisiler.append((isim, tel, gonderim.kisisellestir(mesaj, isim, ogr_adi)))

    gonderim_id = uuid.uuid4().hex[:12]
    thread = threading.Thread(
        target=_gonderim_calistir, args=(gonderim_id, kisiler, bekleme_sn), daemon=True
    )
    thread.start()
    return RedirectResponse(f"/durum/{gonderim_id}", status_code=303)


@app.post("/api/mesaj-duzelt")
async def api_mesaj_duzelt(request: Request):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
    finally:
        conn.close()

    try:
        body = await request.json()
        taslak = body.get("taslak", "")
    except Exception:
        form = await request.form()
        taslak = form.get("taslak", "")

    taslak = (taslak or "").strip()
    if not taslak:
        return JSONResponse({"hata": "Düzeltilecek taslak mesaj boş olamaz."}, status_code=400)

    try:
        # urllib senkron (30 sn'ye kadar) — thread'e alınmazsa tüm 8020 donar.
        duzeltilmis = await asyncio.to_thread(ollama_mesaj_duzelt, taslak)
        return JSONResponse({"duzeltilmis": duzeltilmis})
    except Exception as e:
        return JSONResponse({"hata": f"Yapay zeka servisi yanıt vermedi: {e}"}, status_code=502)


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
        sinif_ogrencileri = db.sinif_bazli_ogrenciler(conn)
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
            "sinif_ogrencileri": sinif_ogrencileri,
        },
    )


@app.post("/rehber/kisi/ekle")
async def rehber_kisi_ekle(
    request: Request,
    ad_soyad: str = Form(...),
    telefon: str = Form(""),
    sinif_id: int = Form(...),
    tur: str = Form(...),
    ogrenci_kisi_id: str | None = Form(None),
):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        tel = gonderim.normalize_phone(telefon) if telefon.strip() else None
        ogr_id = int(ogrenci_kisi_id) if (tur == "veli" and ogrenci_kisi_id and ogrenci_kisi_id.strip().isdigit()) else None
        db.kisi_ekle(conn, ad_soyad.strip(), tel, sinif_id, tur, ogr_id)
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
    ogrenci_kisi_id: str | None = Form(None),
):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        tel = gonderim.normalize_phone(telefon) if telefon.strip() else None
        ogr_id = int(ogrenci_kisi_id) if (tur == "veli" and ogrenci_kisi_id and ogrenci_kisi_id.strip().isdigit()) else None
        db.kisi_guncelle(conn, kisi_id, ad_soyad.strip(), tel, sinif_id, tur, ogr_id)
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
        satirlar = gonderim.rehber_dosyasindan_oku(dosya.filename, icerik, tur=tur)

        eklendi = guncellendi = atlandi = eslesmedi = 0
        for satir in satirlar:
            ad_soyad = satir["ad_soyad"]
            if not ad_soyad:
                atlandi += 1
                continue
            hedef_sinif_id = sinif_id
            if satir["sinif"]:
                hedef_sinif_id = db.sinif_ekle(conn, satir["sinif"])
            telefon = satir["telefon"] or None

            ogrenci_kisi_id = None
            if tur == "veli":
                ogrenci_adi = (satir.get("ogrenci_adi") or "").strip()
                if ogrenci_adi:
                    ogr = db.kisi_bul_isimle(conn, ogrenci_adi, hedef_sinif_id, "ogrenci")
                    if ogr is not None:
                        ogrenci_kisi_id = ogr["id"]
                    else:
                        eslesmedi += 1

            var_olan = db.kisi_bul_isimle(conn, ad_soyad, hedef_sinif_id, tur)
            if var_olan is not None:
                degisti = False
                yeni_tel = var_olan["telefon"]
                if telefon and telefon != var_olan["telefon"]:
                    yeni_tel = telefon
                    degisti = True
                yeni_ogr_id = var_olan.get("ogrenci_kisi_id")
                if tur == "veli" and ogrenci_kisi_id is not None and ogrenci_kisi_id != var_olan.get("ogrenci_kisi_id"):
                    yeni_ogr_id = ogrenci_kisi_id
                    degisti = True

                if degisti:
                    db.kisi_guncelle(conn, var_olan["id"], ad_soyad, yeni_tel, hedef_sinif_id, tur, yeni_ogr_id)
                    guncellendi += 1
                else:
                    atlandi += 1
            else:
                db.kisi_ekle(conn, ad_soyad, telefon, hedef_sinif_id, tur, ogrenci_kisi_id)
                eklendi += 1
    finally:
        conn.close()

    return RedirectResponse(
        f"/rehber?sinif_id={sinif_id}&tur={tur}&mesaj=yuklendi:{eklendi}:{guncellendi}:{atlandi}:{eslesmedi}",
        status_code=303,
    )


@app.get("/api/rehber/telefonlar")
@app.get("/api/rehber/kisiler")
async def rehber_telefonlar(request: Request, sinif_id: int | None = None, tur: str | None = None):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        kisiler = db.kisiler_listele(conn, sinif_id=sinif_id, tur=tur)
    finally:
        conn.close()
    return JSONResponse(
        {
            "kisiler": [
                {
                    "id": k["id"],
                    "ad_soyad": k["ad_soyad"],
                    "telefon": k["telefon"],
                    "sinif_id": k["sinif_id"],
                    "sinif_ad": k["sinif_ad"],
                    "tur": k["tur"],
                    "ogrenci_kisi_id": k["ogrenci_kisi_id"],
                    "ogrenci_ad": k["ogrenci_ad"],
                    "okul_no": k.get("okul_no"),
                    "veli_rol": k.get("veli_rol"),
                }
                for k in kisiler
            ]
        }
    )


# --- Yoklama SMS Modülü ------------------------------------------------------
# Gönderim İÇİN YENİ BİR YOL YOK: sayfa, alıcı veli id'lerini mevcut
# `POST /gonder`'e post eder. Böylece `/durum/{id}`, `/kayitlar`, `/durdur` ve
# `/tekrar-gonder` bedavaya gelir ve riskli gönderim yolunda tek satır yeni kod
# çalışmaz (plan 2026-09-23, kullanıcı kararı: "önce liste + onay").


@app.get("/yoklama-sms", response_class=HTMLResponse)
async def yoklama_sms(
    request: Request,
    tarih: str | None = None,
    esik: int | None = None,
    mesaj: str | None = None,
):
    conn = db.baglanti()
    try:
        yonlendirme = _oturum_yoksa_giris(request, conn)
        if yonlendirme is not None:
            return yonlendirme
        hata = None
        ozet = None
        try:
            ozet = yoklama_mantik.devamsiz_ozet(
                conn,
                tarih=tarih,
                esik=esik if esik is not None else yoklama_mantik.ESIK_VARSAYILAN,
            )
        except yoklama_kaynak.YoklamaKaynakYok as exc:
            # Pano DB'si okunamıyorsa sayfa 500 vermez — Farabi'nin "servis
            # çökse de iş durmaz" ilkesinin buradaki karşılığı.
            hata = str(exc)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "yoklama_sms.html",
        {
            "ozet": ozet,
            "hata": hata,
            "mesaj": mesaj,
            "sablon_varsayilan": yoklama_mantik.SABLON_VARSAYILAN,
            "esik_min": yoklama_mantik.ESIK_MIN,
            "esik_max": yoklama_mantik.ESIK_MAX,
            "bugun": yoklama_mantik.bugun_istanbul().isoformat(),
        },
    )


@app.post("/yoklama-sms/sablon")
async def yoklama_sablon_kaydet(request: Request, yoklama_sms_sablonu: str = Form(...)):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        db.ayar_yaz(conn, yoklama_mantik.AYAR_SABLON, yoklama_sms_sablonu.strip())
    finally:
        conn.close()

    return RedirectResponse("/yoklama-sms?mesaj=sablon_kaydedildi", status_code=303)


# --- Otomasyon Modülü (Sabah 09:00 ve Öğle 14:00 Devamsızlık SMS) ------------


@app.get("/otomasyon", response_class=HTMLResponse)
async def otomasyon_sayfa(
    request: Request,
    gorunum: str | None = None,
    sekme: str | None = None,
    mesaj: str | None = None,
):
    conn = db.baglanti()
    try:
        yonlendirme = _oturum_yoksa_giris(request, conn)
        if yonlendirme is not None:
            return yonlendirme

        aktif_sabah = db.ayar_oku(conn, otomasyon.AYAR_AKTIF) or "0"
        aktif_ogle = db.ayar_oku(conn, otomasyon.AYAR_OGLE_AKTIF) or "0"
        # Tek ana şalter: ikisinden biri açıksa açık sayılır
        # Ana şalter yalnızca İKİSİ de açıksa AKTİF görünür (2026-10-06): eskiden
        # "veya" idi — 14:00 otomasyonu 2026-10-04'te eklendiğinde sabah zaten
        # açıktı, öğle ayarı hiç açılmadı ama sayfa "AÇIK (09:00 ve 14:00)"
        # diyordu; 14:00 SMS'i hiç gitmedi. Yalnızca biri açıksa şablon uyarır.
        aktif = "1" if (aktif_sabah == "1" and aktif_ogle == "1") else "0"

        sablon_sabah = otomasyon.sablonu_oku(conn, "ilk_ders")
        sablon_ogle = otomasyon.sablonu_oku(conn, "ogle")
        son_sonuc_sabah = otomasyon.son_sonuc_oku(conn, "ilk_ders")
        son_sonuc_ogle = otomasyon.son_sonuc_oku(conn, "ogle")

        hata = None
        derleme_sabah = None
        derleme_ogle = None

        try:
            derleme_sabah = otomasyon.ilk_ders_devamsizlar(conn)
        except Exception as exc:
            hata = f"Yoklama panosu verisi okunamadı: {exc}"
            derleme_sabah = {
                "ders_no": 1,
                "tarih": otomasyon.bugun_istanbul().isoformat(),
                "dahil_siniflar": [],
                "haric_siniflar": [],
                "ogrenciler": [],
                "gonderilecek_smsler": [],
                "toplam_ogrenci": 0,
                "toplam_veli_sms": 0,
                "telefonsuz_sayisi": 0,
                "eslesmeyen_sayisi": 0,
                "izinli_sayisi": 0,
                "ulasilabilir_ogrenci": 0,
            }

        try:
            derleme_ogle = otomasyon.ogle_devamsizlar(conn)
        except Exception as exc:
            if not hata:
                hata = f"Yoklama panosu verisi okunamadı: {exc}"
            derleme_ogle = {
                "ders_no": 6,
                "tarih": otomasyon.bugun_istanbul().isoformat(),
                "dahil_siniflar": [],
                "haric_siniflar": [],
                "ogrenciler": [],
                "gonderilecek_smsler": [],
                "toplam_ogrenci": 0,
                "toplam_veli_sms": 0,
                "telefonsuz_sayisi": 0,
                "eslesmeyen_sayisi": 0,
                "izinli_sayisi": 0,
                "ulasilabilir_ogrenci": 0,
                "yalnizca_ogle_sayisi": 0,
            }
    finally:
        conn.close()

    # Önizleme görünümü: URL parametresi varsa o, yoksa saat >= 12 ise öğle, değilse sabah
    simdi_saat = otomasyon.simdi_istanbul().hour
    varsayilan_gorunum = "ogle" if simdi_saat >= 12 else "sabah"
    secili_gorunum = gorunum or sekme or varsayilan_gorunum
    if secili_gorunum not in ("sabah", "ogle"):
        secili_gorunum = varsayilan_gorunum

    return templates.TemplateResponse(
        request,
        "otomasyon.html",
        {
            "aktif": aktif,
            "aktif_sabah": aktif_sabah,
            "aktif_ogle": aktif_ogle,
            "sablon": sablon_sabah,
            "sablon_sabah": sablon_sabah,
            "sablon_ogle": sablon_ogle,
            "son_sonuc": son_sonuc_sabah,
            "son_sonuc_sabah": son_sonuc_sabah,
            "son_sonuc_ogle": son_sonuc_ogle,
            "derleme": derleme_sabah,
            "derleme_sabah": derleme_sabah,
            "derleme_ogle": derleme_ogle,
            "secili_gorunum": secili_gorunum,
            "mesaj": mesaj,
            "hata": hata,
        },
    )


@app.post("/otomasyon/durum-degistir")
async def otomasyon_durum_degistir(
    request: Request,
    aktif: str = Form("0"),
    servis: str | None = Form(None),
):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        yeni_deger = "1" if aktif == "1" else "0"
        if servis in ("ogle", "ogleden_sonra"):
            db.ayar_yaz(conn, otomasyon.AYAR_OGLE_AKTIF, yeni_deger)
            return RedirectResponse("/otomasyon?mesaj=durum_degisti&sekme=ogle", status_code=303)
        elif servis in ("ilk_ders", "sabah"):
            db.ayar_yaz(conn, otomasyon.AYAR_AKTIF, yeni_deger)
            return RedirectResponse("/otomasyon?mesaj=durum_degisti", status_code=303)
        else:
            # Tek ana şalter: her iki servisi birden açar/kapatır
            db.ayar_yaz(conn, otomasyon.AYAR_AKTIF, yeni_deger)
            db.ayar_yaz(conn, otomasyon.AYAR_OGLE_AKTIF, yeni_deger)
            return RedirectResponse("/otomasyon?mesaj=durum_degisti", status_code=303)
    finally:
        conn.close()


@app.post("/otomasyon/ayarlar")
async def otomasyon_ayarlar_kaydet(
    request: Request,
    sablon: str = Form(...),
    servis: str = Form("ilk_ders"),
):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        ayar_adi = otomasyon.AYAR_OGLE_SABLON if servis in ("ogle", "ogleden_sonra") else otomasyon.AYAR_SABLON
        db.ayar_yaz(conn, ayar_adi, sablon.strip())
    finally:
        conn.close()

    sekme_param = "&sekme=ogle" if servis in ("ogle", "ogleden_sonra") else ""
    return RedirectResponse(f"/otomasyon?mesaj=ayarlar_kaydedildi{sekme_param}", status_code=303)


@app.post("/otomasyon/calistir")
async def otomasyon_manuel_calistir(
    request: Request,
    servis: str = Form("ilk_ders"),
):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
    finally:
        conn.close()

    # Gönderim dakikalarca sürebilir — event loop'u bloklamasın (bkz. otomasyon_calistir_thread).
    sonuc = await asyncio.to_thread(
        otomasyon.otomasyon_calistir_thread, servis=servis, kuru=False, tetikleyen="manuel_arayuz"
    )

    sekme_param = "&sekme=ogle" if servis in ("ogle", "ogleden_sonra") else ""
    durum = sonuc.get("durum")
    if durum == "zaten_calisti":
        return RedirectResponse(f"/otomasyon?mesaj=zaten_calisti{sekme_param}", status_code=303)
    if durum == "calisiyor":
        return RedirectResponse(f"/otomasyon?mesaj=calisiyor{sekme_param}", status_code=303)
    if durum == "basarisiz":
        return RedirectResponse(f"/otomasyon?mesaj=basarisiz{sekme_param}", status_code=303)
    return RedirectResponse(f"/otomasyon?mesaj=gonderildi{sekme_param}", status_code=303)


@app.get("/api/otomasyon/durum")
async def api_otomasyon_durum(request: Request, servis: str | None = None):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        if servis in ("ogle", "ogleden_sonra"):
            return JSONResponse(
                {
                    "servis": "ogle",
                    "aktif": db.ayar_oku(conn, otomasyon.AYAR_OGLE_AKTIF) or "0",
                    "sablon": otomasyon.sablonu_oku(conn, "ogle"),
                    "son_tarih": db.ayar_oku(conn, otomasyon.AYAR_OGLE_SON_TARIH) or "",
                    "son_sonuc": otomasyon.son_sonuc_oku(conn, "ogle"),
                }
            )
        elif servis in ("ilk_ders", "sabah"):
            return JSONResponse(
                {
                    "servis": "ilk_ders",
                    "aktif": db.ayar_oku(conn, otomasyon.AYAR_AKTIF) or "0",
                    "sablon": otomasyon.sablonu_oku(conn, "ilk_ders"),
                    "son_tarih": db.ayar_oku(conn, otomasyon.AYAR_SON_TARIH) or "",
                    "son_sonuc": otomasyon.son_sonuc_oku(conn, "ilk_ders"),
                }
            )
        return JSONResponse(
            {
                "aktif": db.ayar_oku(conn, otomasyon.AYAR_AKTIF) or "0",
                "sablon": otomasyon.sablonu_oku(conn, "ilk_ders"),
                "son_tarih": db.ayar_oku(conn, otomasyon.AYAR_SON_TARIH) or "",
                "son_sonuc": otomasyon.son_sonuc_oku(conn, "ilk_ders"),
                "sabah": {
                    "aktif": db.ayar_oku(conn, otomasyon.AYAR_AKTIF) or "0",
                    "sablon": otomasyon.sablonu_oku(conn, "ilk_ders"),
                    "son_tarih": db.ayar_oku(conn, otomasyon.AYAR_SON_TARIH) or "",
                    "son_sonuc": otomasyon.son_sonuc_oku(conn, "ilk_ders"),
                },
                "ogle": {
                    "aktif": db.ayar_oku(conn, otomasyon.AYAR_OGLE_AKTIF) or "0",
                    "sablon": otomasyon.sablonu_oku(conn, "ogle"),
                    "son_tarih": db.ayar_oku(conn, otomasyon.AYAR_OGLE_SON_TARIH) or "",
                    "son_sonuc": otomasyon.son_sonuc_oku(conn, "ogle"),
                },
            }
        )
    finally:
        conn.close()


# --- Doğum Günleri Modülü ----------------------------------------------------


@app.get("/dogum-gunleri", response_class=HTMLResponse)
async def dogum_gunleri(
    request: Request,
    sinif_id: int | None = None,
    tur: str | None = None,
    durum: str | None = None,
    mesaj: str | None = None,
):
    conn = db.baglanti()
    try:
        yonlendirme = _oturum_yoksa_giris(request, conn)
        if yonlendirme is not None:
            return yonlendirme
        stats = dogum_mantik.dogum_gunu_istatistikleri(conn)
        siniflar = db.siniflar_listele(conn)
        kisiler = db.kisiler_listele(conn, sinif_id=sinif_id, tur=tur)
        if durum == "tanimli":
            kisiler = [k for k in kisiler if k.get("dogum_tarihi")]
        elif durum == "eksik":
            kisiler = [k for k in kisiler if not k.get("dogum_tarihi")]
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "dogum_gunleri.html",
        {
            "stats": stats,
            "siniflar": siniflar,
            "kisiler": kisiler,
            "secili_sinif_id": sinif_id,
            "secili_tur": tur,
            "secili_durum": durum,
            "mesaj": mesaj,
        },
    )


@app.get("/dogum-gunleri/ice-aktar", response_class=HTMLResponse)
async def dogum_ice_aktar_sayfa(request: Request):
    conn = db.baglanti()
    try:
        yonlendirme = _oturum_yoksa_giris(request, conn)
        if yonlendirme is not None:
            return yonlendirme
        analiz = dogum_mantik.excel_analiz_et(conn=conn)
    finally:
        conn.close()

    return templates.TemplateResponse(
        request,
        "dogum_ice_aktar.html",
        {"analiz": analiz},
    )


@app.post("/dogum-gunleri/ice-aktar")
async def dogum_ice_aktar_uygula(request: Request):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        form = await request.form()
        secilen_personeller = form.getlist("personel")
        secilen_ayrilanlar = form.getlist("ayrilan")
        dogum_mantik.aktarim_uygula(
            conn,
            secilen_personeller=secilen_personeller,
            secilen_ayrilanlar=secilen_ayrilanlar,
        )
    finally:
        conn.close()

    return RedirectResponse("/dogum-gunleri?mesaj=aktarildi", status_code=303)


@app.post("/dogum-gunleri/kisi/{kisi_id}/tarih")
async def dogum_kisi_tarih_kaydet(
    request: Request,
    kisi_id: int,
    dogum_tarihi: str | None = Form(None),
):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        iso = dogum_tarihi.strip() if dogum_tarihi and dogum_tarihi.strip() else None
        db.kisi_dogum_tarihi_guncelle(conn, kisi_id, iso)
    finally:
        conn.close()

    return RedirectResponse("/dogum-gunleri?mesaj=tarih_kaydedildi", status_code=303)


@app.post("/dogum-gunleri/ayarlar")
async def dogum_ayarlar_kaydet(
    request: Request,
    sms_otomatik: str = Form("0"),
    dogum_sms_sablonu: str = Form(...),
):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        oto = "1" if sms_otomatik == "1" else "0"
        db.ayar_yaz(conn, "sms_otomatik", oto)
        db.ayar_yaz(conn, "dogum_sms_sablonu", dogum_sms_sablonu.strip())
    finally:
        conn.close()

    return RedirectResponse("/dogum-gunleri?mesaj=ayarlar_kaydedildi", status_code=303)

