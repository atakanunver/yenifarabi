"""menu.py — dashboard menü çubuğu, ikon şeridi ve mobil çekmecenin TEK kaynağı (2026-10-08).
taban.html üçünü de bu ağaçtan üretir; menü öğesi başka yerde elle yazılmaz."""

import copy
import time
from pathlib import Path

import zil

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


ZIL_PANELI = "http://192.168.23.23:8090/"  # kimlik gömülmez; tarayıcı Basic Auth sorar

SMUAL_URL = "https://smual.app"
SMUAL_YONETIM_URL = SMUAL_URL + "/yonetici"  # şifresiz giriş (SSO) sonraki aşamada

# 2026-10-23: üst menü çubuğu kalktı, menü SOL KENAR MENÜ oldu (Argon ilhamlı tasarım).
# Sıra = kenar menüdeki sıra. "acil": en üstte sabit kırmızı düğme; "alt": kenar menünün
# dibinde (Atos, Temalar, Ayarlar). EBYS/Duyuru panosu/Kiosk ve diğer "/b/<ad>" yer
# tutucuları menüde yok; sayfaları yapılınca buraya eklenir (yakinda.py'de duruyor).
MENU: list[dict] = [
    {"ad": "Acil durum", "kisayol": "a", "ikon": "uyari", "href": "/acil", "acil": True},
    {"ad": "Ana pano", "kisayol": "h", "ikon": "ev", "href": "/"},
    {
        "ad": "Yoklama",
        "kisayol": "y",
        "ikon": "onay",
        "ogeler": [
            {"ad": "Rapor", "href": "/admin/rapor", "ikon": "grafik"},
            {"ad": "Sınıflar ve öğrenciler", "href": "/admin/siniflar", "ikon": "kullanicilar"},
            {"ad": "Kulüp yoklaması", "href": "/kulup-yoklama", "ikon": "kullanicilar"},
        ],
    },
    {
        "ad": "Tahtalar",
        "kisayol": "t",
        "ikon": "tahta",
        "ogeler": [
            {"ad": "Uzaktan yönetim", "href": "/admin/uzaktan", "ikon": "kaydirici"},
            {"ad": "Tahta kayıtları", "href": "/admin/tahtalar", "ikon": "monitor"},
        ],
    },
    {"ad": "Zil paneli", "kisayol": "z", "ikon": "zil", "href": ZIL_PANELI, "yeni_sekme": True},
    {
        "ad": "İletişim",
        "kisayol": "i",
        "ikon": "log",
        "sayac": "veli",
        "ogeler": [
            {"ad": "Veli mesajları", "href": "/veli-mesajlari", "ikon": "log"},
            {"ad": "SMS gönder", "href": "/sms-git", "ikon": "log", "yeni_sekme": True},
            {"ad": "Yoklama SMS", "href": "/yoklama-sms-git", "ikon": "log", "yeni_sekme": True},
            {"ad": "SMS otomasyonu", "href": "/otomasyon-git", "ikon": "kaydirici", "yeni_sekme": True},
            {"ad": "Doğum günleri", "href": "/dogum", "ikon": "pasta", "yeni_sekme": True},
        ],
    },
    {
        "ad": "Eğitim",
        "kisayol": "e",
        "ikon": "hedef",
        "ogeler": [
            {"ad": "Kazanım raporu", "href": "/kazanim", "ikon": "hedef"},
            {"ad": "smual.app", "href": SMUAL_URL, "ikon": "yildiz", "yeni_sekme": True},
            {"ad": "smual.app yönetim", "href": SMUAL_YONETIM_URL, "ikon": "kaydirici", "yeni_sekme": True},
        ],
    },
    {
        "ad": "Güvenlik",
        "kisayol": "k",
        "ikon": "kamera",
        "ogeler": [
            {"ad": "DVR kameralar", "href": "/kameralar", "ikon": "kamera"},
            {"ad": "IP kameralar (yedek)", "href": "/kameralar-ip", "ikon": "kamera"},
            {"ad": "Güvenlik ekranı", "href": "/guvenlik", "ikon": "kamera"},
        ],
    },
    {
        "ad": "Sistem",
        "kisayol": "s",
        "ikon": "sunucu",
        "ogeler": [
            {"ad": "Sistem durumu", "href": "/sistem-durumu", "ikon": "nabiz"},
            {"ad": "Servis yönetimi", "href": "/servisler", "ikon": "sunucu"},
            {"ad": "Zamanlanmış görevler", "href": "/zamanlanmis-gorevler", "ikon": "saat"},
            {"ad": "Sunucular", "href": "/sunucular", "ikon": "katman"},
        ],
    },
    {
        "ad": "Atos yapay zekâ",
        "kisayol": "o",
        "ikon": "yildiz",
        "href": "atos",
        "yeni_sekme": True,
        "alt": True,
        "vurgu": True,
    },
    {
        "ad": "Temalar",
        "kisayol": "m",
        "ikon": "gunes",
        "alt": True,
        "ogeler": [
            {"ad": "Argon açık", "eylem": "tema:argon", "ikon": "gunes"},
            {"ad": "Argon koyu", "eylem": "tema:argon-koyu", "ikon": "ay"},
            {"ad": "Material açık", "eylem": "tema:material", "ikon": "gunes"},
            {"ad": "Material koyu", "eylem": "tema:material-koyu", "ikon": "ay"},
            {"ad": "Black", "eylem": "tema:black", "ikon": "ay"},
            {"ad": "Taş Tahta", "eylem": "tema:koyu", "ikon": "tahta"},
        ],
    },
    {
        "ad": "Ayarlar",
        "kisayol": "g",
        "ikon": "kaydirici",
        "alt": True,
        "ogeler": [
            {"ad": "Atos iş ve ayarlar", "href": "/b/atos", "ikon": "kaydirici"},
            {"ad": "Yazdır", "eylem": "yazdir", "ikon": "indir"},
            {"ad": "Klavye kısayolları", "eylem": "kisayollar", "ikon": "kaydirici"},
            {"ad": "Çıkış", "eylem": "cikis", "ikon": "cikis"},
        ],
    },
]


def _eslesir(href: str, yol: str) -> bool:
    if not href or not href.startswith("/") or "#" in href:
        return False
    return yol == "/" if href == "/" else yol == href or yol.startswith(href + "/")


def menu_agaci(yol: str) -> dict:
    menu = copy.deepcopy(MENU)
    konum: list[str] = []  # başlık şeridindeki kırıntı yolu: [grup, öğe] ya da [öğe]
    for ust in menu:
        for o in ust.get("ogeler", []):
            if _eslesir(o.get("href", ""), yol):
                o["aktif"] = True
                ust["acik"] = True  # etkin sayfanın grubu açık gelir
                konum = [ust["ad"], o["ad"]]
        if _eslesir(ust.get("href", ""), yol):
            ust["aktif"] = True
            konum = [ust["ad"]]
    return {"menu": menu, "konum": konum, "ders": zil.ust_bilgi(), "surum": statik_surum()}
