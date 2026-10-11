"""menu.py — dashboard menü çubuğu, ikon şeridi ve mobil çekmecenin TEK kaynağı (2026-10-08).
taban.html üçünü de bu ağaçtan üretir; menü öğesi başka yerde elle yazılmaz."""

import copy
import time
from pathlib import Path

STATIK_DIZINI = Path(__file__).resolve().parent / "static"
# ?v= eki: yeni şablon + tarayıcı önbelleğindeki eski CSS/JS bozuk düzen verir (2026-10-08
# önizlemede görüldü). Sürüm = static/ dosyalarının en yeni mtime'ı; 10 sn önbellekli.
_surum_onbellek: dict = {}


def statik_surum() -> str:
    simdi = time.monotonic()
    if _surum_onbellek.get("t", -1e9) + 10 < simdi:
        try:
            enson = max(f.stat().st_mtime for f in STATIK_DIZINI.iterdir() if f.is_file())
        except (OSError, ValueError):
            enson = 0
        _surum_onbellek.update(t=simdi, v=str(int(enson)))
    return _surum_onbellek["v"]


ZIL_PANELI = "http://192.168.23.230:8090/"   # kimlik gömülmez; tarayıcı Basic Auth sorar

SMUAL_URL = "https://smual.app"
SMUAL_YONETIM_URL = SMUAL_URL + "/yonetici"   # şifresiz giriş (SSO) sonraki aşamada

# 2026-10-11: menü iş akışına göre yeniden kuruldu (Düzen/Yardım/Çıkış kalktı). "/b/<ad>"
# öğeleri yakinda.py'deki yer tutucu sayfalar — içerik eklenince oradan çıkarılıp gerçek rotaya bağlanır.
MENU: list[dict] = [
    {"ad": "Ana Pano", "kisayol": "a", "ogeler": [
        {"ad": "Ana pano", "href": "/", "ikon": "ev"},
        {"ad": "Yazdır", "eylem": "yazdir"},
    ]},
    {"ad": "Yoklama", "kisayol": "y", "ogeler": [
        {"ad": "Pano", "href": "/", "ikon": "ev"},
        {"ad": "Tahtalar", "href": "/admin/tahtalar", "ikon": "monitor"},
        {"ad": "Sınıflar", "href": "/admin/siniflar", "ikon": "kullanicilar"},
        {"ad": "Rapor", "href": "/admin/rapor", "ikon": "grafik"},
    ]},
    {"ad": "Kazanımlar", "kisayol": "k", "ogeler": [
        {"ad": "Kazanım raporu", "href": "/kazanim", "ikon": "hedef"},
        {"ad": "Ölçme (smual.app)", "href": SMUAL_URL, "ikon": "hedef", "yeni_sekme": True},
    ]},
    {"ad": "Tahtalar", "kisayol": "t", "ogeler": [
        {"ad": "Uzaktan yönetim", "href": "/admin/uzaktan", "ikon": "kaydirici"},
    ]},
    {"ad": "Servisler", "kisayol": "s", "ogeler": [
        {"ad": "Servis yönetimi", "href": "/servisler", "ikon": "sunucu"},
        {"ad": "Zamanlayıcılar", "href": "/servisler#zamanlayicilar", "ikon": "saat"},
        {"ayrac": True},
        {"ad": "Sistem durumu", "href": "/sistem-durumu", "ikon": "nabiz"},
        {"ad": "Sunucular", "href": "/sunucular", "ikon": "katman"},
        {"ayrac": True},
        {"ad": "Telegram botları", "href": "/b/telegram", "ikon": "sunucu"},
        {"ad": "Ağ taraması", "href": "/b/ag", "ikon": "katman"},
    ]},
    {"ad": "Uygulamalar", "kisayol": "u", "ogeler": [
        {"ad": "smual.app", "href": SMUAL_URL, "ikon": "yildiz", "yeni_sekme": True},
        {"ad": "smual.app yönetim paneli", "href": SMUAL_YONETIM_URL, "ikon": "kaydirici", "yeni_sekme": True},
        {"ayrac": True},
        {"ad": "Oyunlar", "href": "/b/oyunlar", "ikon": "yildiz"},
    ]},
    {"ad": "SMS sistemi", "kisayol": "m", "ogeler": [
        {"ad": "SMS sistemi", "href": "/sms-git", "ikon": "zil", "yeni_sekme": True},
        {"ad": "Yoklama SMS", "href": "/yoklama-sms-git", "ikon": "zil", "yeni_sekme": True},
        {"ad": "SMS otomasyonu", "href": "/otomasyon-git", "ikon": "kaydirici", "yeni_sekme": True},
        {"ad": "Doğum günleri", "href": "/dogum", "ikon": "pasta", "yeni_sekme": True},
    ]},
    {"ad": "Google Form", "kisayol": "f", "ogeler": [
        {"ad": "Form oluştur / gönder", "href": "/b/form", "ikon": "hedef"},
        {"ad": "Kazanım formları", "href": "/kazanim", "ikon": "hedef"},
    ]},
    {"ad": "Anons-Zil", "kisayol": "z", "ogeler": [
        {"ad": "Zil paneli", "href": ZIL_PANELI, "ikon": "zil", "yeni_sekme": True},
        {"ad": "Anons ve ses ayarları", "href": "/b/anons", "ikon": "zil"},
    ]},
    {"ad": "Atos", "kisayol": "o", "ogeler": [
        {"ad": "Atos yapay zeka", "href": "atos", "ikon": "yildiz", "yeni_sekme": True},
        {"ad": "İş ve ayarlar", "href": "/b/atos", "ikon": "kaydirici"},
    ]},
    {"ad": "Görünüm", "kisayol": "g", "ogeler": [
        {"ad": "Tema", "alt": [
            {"ad": "Klasik", "eylem": "tema:klasik", "ikon": "gunes"},
            {"ad": "Yumuşak", "eylem": "tema:yumusak", "ikon": "bulut"},
            {"ad": "Koyu", "eylem": "tema:koyu", "ikon": "ay"},
        ]},
        {"ad": "Kenar şeridini gizle/göster", "eylem": "serit"},
    ]},
    {"ad": "EBYS", "kisayol": "e", "ogeler": [
        {"ad": "Resmi yazı özetleri", "href": "/b/ebys", "ikon": "sunucu"},
    ]},
    {"ad": "Pano", "kisayol": "p", "ogeler": [
        {"ad": "Duyuru panosu", "href": "/b/pano", "ikon": "monitor"},
    ]},
    {"ad": "Kiosk", "kisayol": "i", "ogeler": [
        {"ad": "Yüz tanıma / giriş", "href": "/b/kiosk", "ikon": "kullanicilar"},
    ]},
]

SERIT: list[dict] = [
    {"ad": "Ana pano", "href": "/", "ikon": "ev"},
    {"ad": "Uzaktan yönetim", "href": "/admin/uzaktan", "ikon": "kaydirici"},
    {"ad": "Yoklama raporu", "href": "/admin/rapor", "ikon": "grafik"},
    {"ad": "Servis yönetimi", "href": "/servisler", "ikon": "sunucu"},
    {"ad": "Sistem durumu", "href": "/sistem-durumu", "ikon": "nabiz"},
    {"ad": "Atos yapay zeka", "href": "atos", "ikon": "yildiz", "yeni_sekme": True},
]


def _eslesir(href: str, yol: str) -> bool:
    if not href or not href.startswith("/") or "#" in href:
        return False
    return yol == "/" if href == "/" else yol == href or yol.startswith(href + "/")


def menu_agaci(yol: str) -> dict:
    menu, serit = copy.deepcopy(MENU), copy.deepcopy(SERIT)
    ilk_ana_pano = True
    for ust in menu:
        for o in ust["ogeler"]:
            if _eslesir(o.get("href", ""), yol):
                # "/" iki menüde var; Dosya › Ana pano değil, Yoklama › Pano işaretlenir
                if o["href"] == "/" and ilk_ana_pano:
                    ilk_ana_pano = False
                    continue
                o["aktif"] = True
    for s in serit:
        if _eslesir(s["href"], yol):
            s["aktif"] = True
    return {"menu": menu, "serit": serit, "surum": statik_surum()}
