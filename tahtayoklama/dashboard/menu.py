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
            enson = max(
                f.stat().st_mtime for f in STATIK_DIZINI.iterdir() if f.is_file()
            )
        except (OSError, ValueError):
            enson = 0
        _surum_onbellek.update(t=simdi, v=str(int(enson)))
    return _surum_onbellek["v"]


ZIL_PANELI = "http://192.168.23.230:8090/"  # kimlik gömülmez; tarayıcı Basic Auth sorar

SMUAL_URL = "https://smual.app"
SMUAL_YONETIM_URL = SMUAL_URL + "/yonetici"  # şifresiz giriş (SSO) sonraki aşamada

# 2026-10-13: menü 8 başlığa indirildi (iş akışına göre). EBYS/Duyuru panosu/Kiosk ve diğer
# "/b/<ad>" yer tutucuları menüden çıktı; sayfaları yapılınca buraya eklenir (yakinda.py'de
# yer tutucu sayfalar duruyor). Yazdır/Tema/Şerit/Çıkış "Ayarlar" altında.
MENU: list[dict] = [
    {"ad": "Ana Menü", "kisayol": "h", "ikon": "ev", "href": "/"},
    {
        "ad": "Acil Durum",
        "kisayol": "a",
        "ikon": "uyari",
        "ogeler": [{"ad": "Acil Durum", "href": "/acil", "ikon": "uyari"}],
    },
    {
        "ad": "Yoklama",
        "kisayol": "y",
        "ikon": "ev",
        "ogeler": [
            {"ad": "Pano", "href": "/", "ikon": "ev"},
            {"ad": "Rapor", "href": "/admin/rapor", "ikon": "grafik"},
            {"ad": "Sınıflar", "href": "/admin/siniflar", "ikon": "kullanicilar"},
        ],
    },
    {
        "ad": "Tahtalar",
        "kisayol": "t",
        "ikon": "tahta",
        "ikon_sinif": "ikon-yesil",
        "ogeler": [
            {"ad": "Uzaktan yönetim", "href": "/admin/uzaktan", "ikon": "kaydirici"},
            {"ad": "Tahta kayıtları", "href": "/admin/tahtalar", "ikon": "monitor"},
        ],
    },
    {
        "ad": "Eğitim",
        "kisayol": "e",
        "ikon": "hedef",
        "ogeler": [
            {"ad": "Kazanım raporu", "href": "/kazanim", "ikon": "hedef"},
            {"ayrac": True},
            {
                "ad": "smual.app",
                "href": SMUAL_URL,
                "ikon": "yildiz",
                "yeni_sekme": True,
            },
            {
                "ad": "smual.app yönetim paneli",
                "href": SMUAL_YONETIM_URL,
                "ikon": "kaydirici",
                "yeni_sekme": True,
            },
        ],
    },
    {
        "ad": "İletişim",
        "kisayol": "i",
        "ikon": "zil",
        "ogeler": [
            {
                "ad": "Velilerden Gelen Mesajlar",
                "href": "/veli-mesajlari",
                "ikon": "zil",
            },
            {
                "ad": "SMS sistemi",
                "href": "/sms-git",
                "ikon": "zil",
                "yeni_sekme": True,
            },
            {
                "ad": "Yoklama SMS",
                "href": "/yoklama-sms-git",
                "ikon": "zil",
                "yeni_sekme": True,
            },
            {
                "ad": "SMS otomasyonu",
                "href": "/otomasyon-git",
                "ikon": "kaydirici",
                "yeni_sekme": True,
            },
            {
                "ad": "Doğum günleri",
                "href": "/dogum",
                "ikon": "pasta",
                "yeni_sekme": True,
            },
        ],
    },
    {
        "ad": "Kameralar",
        "kisayol": "k",
        "ikon": "kamera",
        "ogeler": [
            {"ad": "DVR Kameralar", "href": "/kameralar", "ikon": "kamera"},
            {"ad": "IP Kameralar (yedek)", "href": "/kameralar-ip", "ikon": "kamera"},
            {"ad": "Güvenlik ekranı", "href": "/guvenlik", "ikon": "kamera"},
        ],
    },
    {
        "ad": "Sistem",
        "kisayol": "s",
        "ikon": "sunucu",
        "ogeler": [
            {"ad": "Servis yönetimi", "href": "/servisler", "ikon": "sunucu"},
            {
                "ad": "Zamanlanmış görevler",
                "href": "/zamanlanmis-gorevler",
                "ikon": "saat",
            },
            {"ayrac": True},
            {"ad": "Sistem durumu", "href": "/sistem-durumu", "ikon": "nabiz"},
            {"ad": "Sunucular", "href": "/sunucular", "ikon": "katman"},
        ],
    },
    {
        "ad": "Zil Paneli",
        "kisayol": "z",
        "ikon": "zil",
        "href": ZIL_PANELI,
        "yeni_sekme": True,
    },
    {
        "ad": "Atos Yapay Zeka",
        "kisayol": "o",
        "ikon": "yildiz",
        "href": "atos",
        "yeni_sekme": True,
        "buyuk": True,
    },
    {
        "ad": "Temalar",
        "kisayol": "m",
        "ikon": "gunes",
        "ogeler": [
            {"ad": "Klasik", "eylem": "tema:klasik", "ikon": "gunes"},
            {"ad": "Yumuşak", "eylem": "tema:yumusak", "ikon": "bulut"},
            {"ad": "Koyu", "eylem": "tema:koyu", "ikon": "ay"},
        ],
    },
    {
        "ad": "Ayarlar",
        "kisayol": "g",
        "ikon": "kaydirici",
        "ogeler": [
            {"ad": "Atos iş ve ayarlar", "href": "/b/atos", "ikon": "kaydirici"},
            {"ad": "Kenar şeridini gizle/göster", "eylem": "serit"},
            {"ad": "Yazdır", "eylem": "yazdir"},
            {"ad": "Klavye kısayolları", "eylem": "kisayollar"},
            {"ayrac": True},
            {"ad": "Çıkış", "eylem": "cikis", "ikon": "cikis"},
        ],
    },
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
    for ust in menu:
        if "ogeler" in ust:
            for o in ust["ogeler"]:
                if _eslesir(o.get("href", ""), yol):
                    o["aktif"] = True
        elif _eslesir(ust.get("href", ""), yol):
            ust["aktif"] = True
    for s in serit:
        if _eslesir(s["href"], yol):
            s["aktif"] = True
    return {"menu": menu, "serit": serit, "surum": statik_surum()}
