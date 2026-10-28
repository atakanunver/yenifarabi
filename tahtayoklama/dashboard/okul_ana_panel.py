"""Okul verisi paneli: okul_ana (PostgreSQL) üzerinde ekle/güncelle/sil.

Dashboard'a `app.include_router(okul_ana_panel.router)` ile bağlanır. Her yazma:
tek transaction (okul_ana_veri) -> yayın (okul_ana_yayin: eski depolar + JSON). Yayın
başarısız olsa bile veri DB'de güvendedir (tek kaynak); sayfa uyarı gösterir, 'Yayınla' ile
yeniden denenir. Oturum: dashboard'un ortak şifre çerezi (auth.dogrula), admin.py ile aynı.
"""

import os
import time
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import menu
import okul_ana_veri as veri
import okul_ana_yayin as yayin
import zil

router = APIRouter(prefix="/admin/okul-verisi")
templates = Jinja2Templates(directory="templates")
templates.env.globals["menu_agaci"] = menu.menu_agaci
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk

SON_YAYIN = {"zaman": None, "durum": "henüz yayın yapılmadı", "ok": None}


def oturum_sarti(request: Request) -> None:
    import auth
    import db

    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            raise HTTPException(401, "Oturum geçersiz.")
    finally:
        conn.close()


def _yayinla() -> str | None:
    """Yayını çalıştırır; hata mesajı (str) ya da None döner. Veri zaten DB'de."""
    try:
        if not os.environ.get(
            "OKUL_ANA_DSN"
        ):  # tembel: dosya yoksa dashboard açılışı bozulmaz
            os.environ["OKUL_ANA_DSN"] = veri.dsn()
        sonuc = yayin.yayinla(True)
        SON_YAYIN.update(
            zaman=time.strftime("%H:%M:%S"),
            ok=True,
            durum="; ".join(f"{a}: {s}" for a, s in sonuc.items()),
        )
        return None
    except Exception as e:  # noqa: BLE001 — veri DB'de güvende, kullanıcıya göster
        SON_YAYIN.update(zaman=time.strftime("%H:%M:%S"), ok=False, durum=str(e)[:300])
        return f"Veri kaydedildi ama yayın başarısız: {str(e)[:200]}"


def _don(sekme: str, **q) -> RedirectResponse:
    q = {k: v for k, v in q.items() if v not in (None, "")}
    return RedirectResponse(
        "/admin/okul-verisi?" + urlencode({"sekme": sekme, **q}), status_code=303
    )


def _islem(request: Request, sekme: str, fn, ok: str, **geri):
    """oturum -> tek transaction (fn) -> yayın -> yönlendirme. ValueError = kullanıcı hatası."""
    oturum_sarti(request)
    try:
        with veri.baglan() as c:
            fn(c)
    except ValueError as e:
        return _don(sekme, hata=str(e), **geri)
    uyari = _yayinla()
    return _don(sekme, mesaj=ok, uyari=uyari, **geri)


# --- sayfa -------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
def sayfa(
    request: Request,
    sekme: str = "ogrenci",
    sinif: str = "",
    ara: str = "",
    pasifler: str = "",
    duzenle: str = "",
    pduzenle: str = "",
    psinif: str = "",
    mesaj: str = "",
    hata: str = "",
    uyari: str = "",
):
    oturum_sarti(request)
    ctx = {
        "sekme": sekme,
        "mesaj": mesaj,
        "hata": hata,
        "uyari": uyari,
        "son_yayin": SON_YAYIN,
        "gunler": veri.GUNLER,
        "sinif": sinif,
        "ara": ara,
        "pasifler": bool(pasifler),
    }
    with veri.baglan() as c:
        ctx["siniflar"] = veri.siniflar(c)
        if sekme == "ogrenci":
            ctx["ogrenciler"] = veri.ogrenciler(
                c, sinif or None, ara or None, bool(pasifler)
            )
            if duzenle:
                o = veri.ogrenci_getir(c, int(duzenle)) if duzenle.isdigit() else None
                ctx["duzenlenen"] = o
                ctx["veliler"] = veri.veliler(c, o["okul_no"]) if o else []
        elif sekme == "personel":
            ctx["personel"] = veri.personel(c, bool(pasifler))
            if pduzenle.isdigit():
                ctx["pduzenlenen"] = next(
                    (p for p in ctx["personel"] if p["id"] == int(pduzenle)), None
                )
        elif sekme == "program":
            ad = psinif or (ctx["siniflar"][0]["ad"] if ctx["siniflar"] else "")
            ctx["psinif"] = ad
            ctx["hucre"] = veri.program(c, ad) if ad else {}
            ctx["ders_nolar"] = range(1, max([8] + [n for _, n in ctx["hucre"]]) + 1)
        elif sekme == "zil":
            ctx["zil_satirlar"], ctx["zil_ayar"] = veri.zil(c)
        elif sekme == "denetim":
            ctx["denetim"] = veri.denetim_son(c)
    return templates.TemplateResponse(request, "admin_okul_verisi.html", ctx)


# --- yazma uçları --------------------------------------------------------------------


@router.post("/sinif")
async def sinif_ekle(request: Request):
    f = await request.form()
    return _islem(
        request, "ogrenci", lambda c: veri.sinif_ekle(c, f.get("ad")), "Sınıf eklendi."
    )


@router.post("/ogrenci")
async def ogrenci_kaydet(request: Request):
    f = await request.form()
    yeni = f.get("yeni") == "1"
    no = f.get("okul_no", "")
    return _islem(
        request,
        "ogrenci",
        lambda c: veri.ogrenci_kaydet(
            c,
            no,
            f.get("ad_soyad"),
            f.get("cinsiyet"),
            f.get("telefon"),
            f.get("dogum_tarihi"),
            f.get("sinif"),
            yeni,
        ),
        "Öğrenci eklendi." if yeni else "Öğrenci güncellendi.",
        duzenle=no,
    )


@router.post("/ogrenci/{no}/pasif")
def ogrenci_pasif(request: Request, no: int):
    return _islem(
        request,
        "ogrenci",
        lambda c: veri.ogrenci_pasif(c, no, False),
        "Öğrenci pasifleştirildi.",
    )


@router.post("/ogrenci/{no}/geri")
def ogrenci_geri(request: Request, no: int):
    return _islem(
        request,
        "ogrenci",
        lambda c: veri.ogrenci_pasif(c, no, True),
        "Öğrenci geri alındı.",
        duzenle=str(no),
    )


@router.post("/veli")
async def veli_kaydet(request: Request):
    f = await request.form()
    no = f.get("okul_no", "")
    vid = int(f["veli_id"]) if (f.get("veli_id") or "").isdigit() else None
    return _islem(
        request,
        "ogrenci",
        lambda c: veri.veli_kaydet(
            c, no, vid, f.get("ad_soyad"), f.get("telefon"), f.get("yakinlik")
        ),
        "Veli kaydedildi.",
        duzenle=no,
    )


@router.post("/veli/{no}/{vid}/sil")
def veli_sil(request: Request, no: int, vid: int):
    return _islem(
        request,
        "ogrenci",
        lambda c: veri.veli_sil(c, no, vid),
        "Veli bağı silindi.",
        duzenle=str(no),
    )


@router.post("/personel")
async def personel_kaydet(request: Request):
    f = await request.form()
    pid = int(f["id"]) if (f.get("id") or "").isdigit() else None
    return _islem(
        request,
        "personel",
        lambda c: veri.personel_kaydet(
            c,
            pid,
            f.get("ad_soyad"),
            f.get("telefon"),
            f.get("gorev"),
            f.get("dogum_tarihi"),
            f.get("brans"),
        ),
        "Personel kaydedildi.",
    )


@router.post("/personel/{pid}/pasif")
def personel_pasif(request: Request, pid: int):
    return _islem(
        request,
        "personel",
        lambda c: veri.personel_pasif(c, pid),
        "Personel pasifleştirildi.",
    )


@router.post("/program")
async def program_kaydet(request: Request):
    f = await request.form()
    sinif = f.get("sinif", "")
    hucreler = {}
    for k, v in f.items():
        if k.startswith("h_"):
            try:
                _, g, n = k.split("_")
                hucreler[(int(g), int(n))] = v
            except ValueError:
                continue
    return _islem(
        request,
        "program",
        lambda c: veri.program_kaydet(c, sinif, hucreler),
        "Ders programı kaydedildi.",
        psinif=sinif,
    )


@router.post("/zil")
async def zil_kaydet(request: Request):
    f = await request.form()
    saatler = [(n, f.get(f"b{n}", ""), f.get(f"e{n}", "")) for n in range(1, 11)]
    return _islem(
        request,
        "zil",
        lambda c: veri.zil_kaydet(c, saatler, f.get("ders_suresi"), f.get("teneffus")),
        "Zil saatleri kaydedildi.",
    )


@router.post("/yayinla")
def yayinla_elle(request: Request):
    oturum_sarti(request)
    uyari = _yayinla()
    return _don("ogrenci", mesaj=None if uyari else "Yayın tamamlandı.", uyari=uyari)
