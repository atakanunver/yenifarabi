"""Görsel Oluşturma Paneli (/gorsel, 2026-11-10): haftalık ödül kartı + serbest görsel.

Arka plan yapay zekâdan (isimsiz prompt) gelir; ad/sınıf Pillow ile burada basılır (gorsel.py).
Üretim ~22 sn sürer: arka plan görevi olarak koşar, sayfa /gorsel/durum'u yoklar. Aynı anda tek üretim.
Kartlar: önizleme (kazananlar GEÇİCİ), onay, görsel arşivi (veri/gorseller/), seçili tahtalara ELLE gönderim,
tüm tahtalarda geri alma. Otomatik gönderim YOK; haftalık kartı scripts/hafta_karti_uret.py yalnız arşive bırakır.
Eylemler uzaktan_denetim'e yazılır (öğrenci adı/prompt yazılmaz). Öğrenci adı loga yazılmaz.
"""

import asyncio
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

import gorsel
import menu
import tahta_kaydi
import uzaktan_yonetim
import zil
from scripts import duvar_kagidi

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["menu_agaci"] = menu.menu_agaci
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk

_is = {"durum": "bosta", "tur": None, "mesaj": "", "baslangic": 0.0, "dosya": None}
_gorevler: set = set()  # görev referansı tutulur (GC engeli)


def _hata(mesaj: str, kod: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "mesaj": mesaj}, status_code=kod)


def _denetim(request: Request, eylem: str, ok: bool, tahta: str = "gorsel") -> None:
    uzaktan_yonetim._denetim_yaz(request, eylem, [{"tahta": tahta, "basarili": ok}])


def _durum_ozeti() -> dict:
    d = gorsel.durum_oku()
    return {
        "is": dict(_is), "kalan": gorsel.kalan_hak(), "sinir": gorsel.GUNLUK_SINIR,
        "aday": bool(d["aday_arka_plan"] and Path(d["aday_arka_plan"]).is_file()),
        "onayli": d["onayli_arka_plan"], "onay_zamani": d["onay_zamani"],
        "gunluk": d["gonderim_gunlugu"][-8:][::-1],
    }


async def _uret(tur: str, prompt: str) -> None:
    try:
        png = await asyncio.to_thread(gorsel.ai_arka_plan, prompt)
        yol = gorsel.arsivle("serbest", png) if tur == "serbest" else gorsel.aday_kaydet(png)
        _is.update(durum="hazir", mesaj="Görsel hazır.", dosya=yol.name)
    except gorsel.GorselHatasi as e:
        _is.update(durum="hata", mesaj=str(e))
    except Exception as e:  # noqa: BLE001  görev sessizce ölmesin; ayrıntı (prompt/ad) yazılmaz
        _is.update(durum="hata", mesaj=f"Beklenmeyen hata ({type(e).__name__}).")


async def _kazananlar() -> dict:
    return (await asyncio.to_thread(gorsel.hafta_kazananlari, None, True))["kategoriler"]


@router.get("/gorsel", response_class=HTMLResponse)
async def gorsel_sayfa(request: Request):
    uzaktan_yonetim._dogrula(request)
    return templates.TemplateResponse(request, "gorsel.html", {
        "varsayilan_prompt": gorsel.VARSAYILAN_PROMPT,
        "ozet": _durum_ozeti(),
        "tahtalar": [t["ad"] for t in tahta_kaydi.tahtalari_yukle()],
    })


@router.get("/gorsel/durum")
async def gorsel_durum(request: Request):
    uzaktan_yonetim._dogrula(request)
    return _durum_ozeti()


@router.post("/gorsel/uret")
async def gorsel_uret(request: Request):
    uzaktan_yonetim._dogrula(request)
    form = await request.form()
    tur = "serbest" if form.get("tur") == "serbest" else "arka_plan"
    prompt = str(form.get("prompt") or "").strip()
    if not prompt:
        return _hata("Prompt boş.")
    if len(prompt) > 2000:
        return _hata("Prompt en çok 2000 karakter olabilir.")
    if _is["durum"] == "calisiyor" and time.monotonic() - _is["baslangic"] < 200:
        return _hata("Bir üretim sürüyor, bitmesini bekle.", 409)
    if not gorsel.uretim_hakki_al():
        return _hata(f"Günlük {gorsel.GUNLUK_SINIR} üretim sınırı doldu.", 429)
    _is.update(durum="calisiyor", tur=tur, mesaj="Üretiliyor (~25 sn)…", baslangic=time.monotonic())
    gorev = asyncio.create_task(_uret(tur, prompt))
    _gorevler.add(gorev)
    gorev.add_done_callback(_gorevler.discard)
    _denetim(request, "gorsel_uret", True)
    return {"ok": True, "mesaj": _is["mesaj"]}


@router.get("/gorsel/arsiv")
async def gorsel_arsiv(request: Request):
    uzaktan_yonetim._dogrula(request)
    return {"gorseller": gorsel.arsiv_listele()}


@router.get("/gorsel/arsiv/{ad}")
async def gorsel_arsiv_dosya(request: Request, ad: str, indir: int = 0):
    uzaktan_yonetim._dogrula(request)
    yol = gorsel.arsiv_yolu(ad)
    if yol is None:
        return Response("Görsel yok.", status_code=404)
    basliklar = {"Cache-Control": "no-store"}
    if indir:
        basliklar["Content-Disposition"] = f'attachment; filename="{ad}"'
    return FileResponse(yol, media_type="image/png", headers=basliklar)


@router.get("/gorsel/arka-plan.png")
async def gorsel_arka_plan(request: Request):
    uzaktan_yonetim._dogrula(request)
    try:
        return FileResponse(gorsel.kullanilacak_arka_plan(), media_type="image/png",
                            headers={"Cache-Control": "no-store"})
    except gorsel.GorselHatasi:
        return Response("Görsel yok.", status_code=404)


@router.get("/gorsel/onizleme.png")
async def gorsel_onizleme(request: Request):
    uzaktan_yonetim._dogrula(request)
    try:
        yol = gorsel.kart_uret_ve_arsivle(await _kazananlar())
    except ValueError:
        return Response("Bu hafta kazanan yok (geçici sonuçlarda iki kategori de boş).", status_code=404)
    except gorsel.GorselHatasi as e:
        return Response(str(e), status_code=502)
    return FileResponse(yol, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/gorsel/onayla")
async def gorsel_onayla(request: Request):
    uzaktan_yonetim._dogrula(request)
    try:
        gorsel.onayla()
    except gorsel.GorselHatasi as e:
        _denetim(request, "gorsel_onay", False)
        return _hata(str(e))
    _denetim(request, "gorsel_onay", True)
    return {"ok": True, "mesaj": "Arka plan onaylandı."}


@router.post("/gorsel/gonder")
async def gorsel_gonder(request: Request):
    """Arşivden seçilen görseli seçili tahtalara gönderir (elle; sayfa içi onaydan sonra çağrılır)."""
    uzaktan_yonetim._dogrula(request)
    form = await request.form()
    yol = gorsel.arsiv_yolu(str(form.get("dosya") or ""))
    if yol is None:
        return _hata("Görsel seçilmedi ya da arşivde yok.")
    bilinen = [t["ad"] for t in tahta_kaydi.tahtalari_yukle()]
    secili = [a for a in dict.fromkeys(form.getlist("tahta")) if a in bilinen]
    if not secili:
        return _hata("Tahta seçilmedi.")
    sonuclar = list(await asyncio.gather(*(duvar_kagidi.gonder(a, yol) for a in secili)))
    gorsel.gonderim_kaydet(sonuclar)
    uzaktan_yonetim._denetim_yaz(request, "gorsel_gonder", sonuclar)
    basarili = sum(r["basarili"] for r in sonuclar)
    return {
        "ok": basarili == len(sonuclar), "mesaj": f"{basarili}/{len(sonuclar)} tahtaya gönderildi.",
        "sonuclar": [{"tahta": r["tahta"], "ok": bool(r["basarili"]), "detay": r["detay"]} for r in sonuclar],
    }


@router.post("/gorsel/sil")
async def gorsel_sil(request: Request):
    """Arşivden seçilen tek görseli siler (sayfa içi onaydan sonra çağrılır)."""
    uzaktan_yonetim._dogrula(request)
    form = await request.form()
    try:
        gorsel.arsivden_sil(str(form.get("dosya") or ""))
    except gorsel.GorselHatasi as e:
        _denetim(request, "gorsel_sil", False)
        return _hata(str(e))
    _denetim(request, "gorsel_sil", True)
    return {"ok": True, "mesaj": "Görsel silindi."}


@router.post("/gorsel/geri-al")
async def gorsel_geri_al(request: Request):
    uzaktan_yonetim._dogrula(request)
    adlar = [t["ad"] for t in tahta_kaydi.tahtalari_yukle()]
    sonuclar = list(await asyncio.gather(*(duvar_kagidi.geri_al(a) for a in adlar)))
    uzaktan_yonetim._denetim_yaz(request, "gorsel_geri_al", sonuclar)
    basarili = sum(r["basarili"] for r in sonuclar)
    hatalar = [f"{r['tahta']}: {r['detay']}" for r in sonuclar if not r["basarili"]]
    return {"ok": not hatalar, "mesaj": f"{basarili}/{len(sonuclar)} tahta geri alındı.", "hatalar": hatalar}
