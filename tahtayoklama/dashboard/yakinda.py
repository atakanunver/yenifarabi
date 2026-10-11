"""yakinda.py — menüde yeri ayrılmış ama henüz yapılmamış bölümler için yer tutucu sayfalar
(2026-10-11). İçerik eklenince ilgili bölüm BÖLUMLER'den çıkar, kendi modülüne taşınır."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import auth
import db
import menu
import zil

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["menu_agaci"] = menu.menu_agaci
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk

# yol adı -> (başlık, ne yapacak)
BOLUMLER: dict[str, tuple[str, str]] = {
    "telegram": ("Telegram botları", "Çalışan Telegram botlarının hangi makinede çalıştığı ve durumu burada listelenecek."),
    "ag": ("Ağ taraması", "Okul ağındaki cihazların IP adresi ve bilgisayar adı taranıp burada görünecek."),
    "oyunlar": ("Oyunlar", "Oyunların listesi ve oyun yönetim paneli burada olacak."),
    "form": ("Google Form", "Form oluşturma ve formu bağlantı, SMS ya da smual.app üzerinden gönderme burada olacak."),
    "anons": ("Anons ve ses ayarları", "Anons, metinden sese, sesten metne işlemleri ile zil ve Bilgehan bilgisayarlarındaki ses ayarları burada olacak."),
    "atos": ("Atos iş ve ayarlar", "Yerel yapay zekanın iş ve işlem ayarları burada olacak."),
    "ebys": ("EBYS", "Resmi yazıların özetleri burada yazı olarak görünecek. Kaynak: Müdür PC özetleri ya da Telegram botu."),
    "pano": ("Duyuru panosu", "Okul girişindeki panonun duyuruları buradan yönetilecek."),
    "kiosk": ("Kiosk", "Okul girişindeki yüz tanıma ve giriş kiosku için ayarlar burada olacak."),
}


def _sayfa_olustur(ad: str):
    baslik, aciklama = BOLUMLER[ad]

    async def sayfa(request: Request):
        conn = db.baglanti()
        try:
            if not auth.dogrula(request, conn):
                return RedirectResponse("/giris", status_code=303)
        finally:
            conn.close()
        return templates.TemplateResponse(request, "yakinda.html", {"baslik": baslik, "aciklama": aciklama})

    sayfa.__name__ = f"yakinda_{ad}"
    return sayfa


for _ad in BOLUMLER:
    router.add_api_route(f"/b/{_ad}", _sayfa_olustur(_ad), methods=["GET"], response_class=HTMLResponse)
