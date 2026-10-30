"""menu.py — dashboard menü çubuğu, ikon şeridi ve mobil çekmecenin TEK kaynağı (2026-10-08).
taban.html üçünü de bu ağaçtan üretir; menü öğesi başka yerde elle yazılmaz."""

import copy
import time
from pathlib import Path
from urllib.parse import parse_qs

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


ZIL_PANELI = "http://zil.local:8090/"  # kimlik gömülmez; tarayıcı Basic Auth sorar
BILGEHAN_PANELI = "http://bilgehan.local:9100/"  # okul-panel, Basic Auth
KIOSK_PANELI = "http://kiosk.local:9100/"
PANO_PANELI = "http://kiosk.local:9100/pano"  # pano içeriği: nöbetçi, slayt, bilgiler, YKS (okul-panel, Basic Auth)
KIOSK_YUZ_PANELI = "http://kiosk.local:5050/"  # yuzpanel.service, kendi girişini ister

SMUAL_URL = "https://smual.app"
SMUAL_YONETIM_URL = SMUAL_URL + "/yonetici"  # şifresiz giriş (SSO) sonraki aşamada

# 2026-10-23: üst menü çubuğu kalktı, menü SOL KENAR MENÜ oldu (Argon ilhamlı tasarım).
# Sıra = kenar menüdeki sıra. "acil": en üstte sabit kırmızı düğme; "alt": kenar menünün
# dibinde (Atos, Temalar, Ayarlar). EBYS/Duyuru panosu/Kiosk ve diğer "/b/<ad>" yer
# tutucuları menüde yok; sayfaları yapılınca buraya eklenir (yakinda.py'de duruyor).
MENU: list[dict] = [
    {"ad": "Acil durum", "kisayol": "a", "ikon": "uyari", "href": "/acil", "acil": True},
    {"ad": "Ana pano", "kisayol": "h", "ikon": "ev", "href": "/"},
    {"ad": "Okul verisi", "kisayol": "v", "ikon": "kullanicilar", "href": "/admin/okul-verisi"},
    # 2026-10-30: görev odaklı gruplar (müdür "ne yapmak istiyorum?" diye arar); makine adlı paneller Teknoloji'de.
    {
        "ad": "Öğrenciler",
        "kisayol": "r",
        "ikon": "kullanicilar",
        "ogeler": [
            {"ad": "Bugünkü yoklama", "href": "/bugun", "ikon": "ev"},
            {"ad": "Yoklama raporu", "href": "/admin/rapor", "ikon": "grafik"},
            {"ad": "Aylık özet", "href": "/aylik-ozet", "ikon": "grafik"},
            {"ad": "Öğrenci ve veli", "href": "/admin/okul-verisi?sekme=ogrenci", "ikon": "kullanicilar"},
            {"ad": "Sınıflar ve tahtalar", "href": "/admin/siniflar", "ikon": "kullanicilar"},
            {"ad": "Kulüp listeleri", "href": "/admin/kulupler", "ikon": "kullanicilar"},
            {"ad": "Kulüp yoklaması", "href": "/kulup-yoklama", "ikon": "kullanicilar"},
        ],
    },
    {
        "ad": "Öğretmenler ve program",
        "kisayol": "p",
        "ikon": "saat",
        "ogeler": [
            {"ad": "Personel", "href": "/admin/okul-verisi?sekme=personel", "ikon": "kullanicilar"},
            {"ad": "Ders programı", "href": "/admin/okul-verisi?sekme=program", "ikon": "saat"},
            {"ad": "Zil saatleri", "href": "/admin/okul-verisi?sekme=zil", "ikon": "zil"},
            {"ad": "Zil paneli", "href": "/panel-git/zil", "ikon": "zil", "yeni_sekme": True},
        ],
    },
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
    {"ad": "Tahta duyuru", "kisayol": "d", "ikon": "zil", "href": "/admin/uzaktan#duyuru"},
    {
        "ad": "Eğitim ve sınav",
        "kisayol": "e",
        "ikon": "hedef",
        "ogeler": [
            {"ad": "smual.app", "href": SMUAL_URL, "ikon": "yildiz", "yeni_sekme": True},
            {"ad": "smual.app yönetim", "href": SMUAL_YONETIM_URL, "ikon": "kaydirici", "yeni_sekme": True},
            {"ad": "Kelebek", "href": "/kelebek-git", "ikon": "tahta", "yeni_sekme": True},
        ],
    },
    {
        "ad": "Güvenlik",
        "kisayol": "k",
        "ikon": "kamera",
        "ogeler": [
            {"ad": "DVR kameralar", "href": "/kameralar", "ikon": "kamera"},
            {"ad": "IP kameralar (yedek)", "href": "/kameralar-ip", "ikon": "kamera"},
            {"ad": "Kamera kayıtları", "href": "/kameralar-kayit", "ikon": "kamera"},
            {"ad": "Güvenlik ekranı", "href": "/guvenlik", "ikon": "kamera"},
            {"ad": "Kiosk yüz tanıma paneli", "href": KIOSK_YUZ_PANELI, "ikon": "kullanicilar", "yeni_sekme": True},
        ],
    },
    {
        "ad": "Teknoloji",
        "etiket": "Teknik",
        "kisayol": "s",
        "ikon": "sunucu",
        "ogeler": [
            {"ad": "Tahtalar", "href": "/admin/uzaktan", "ikon": "tahta"},
            {"ad": "Pano Paneli", "href": "/panel-git/pano", "ikon": "tahta", "yeni_sekme": True},
            {"ad": "Kiosk Paneli", "href": "/panel-git/kiosk", "ikon": "sunucu", "yeni_sekme": True},
            {"ad": "Bilgehan Paneli", "href": "/panel-git/bilgehan", "ikon": "sunucu", "yeni_sekme": True},
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


_VARSAYILAN_SORGU = {"sekme": "ogrenci"}  # /admin/okul-verisi sekmesiz açılınca Öğrenci ve veli


def _eslesir(href: str, yol: str, sorgu: str = "") -> bool:
    if not href or not href.startswith("/") or "#" in href:
        return False
    href, _, href_sorgu = href.partition("?")
    if not (yol == "/" if href == "/" else yol == href or yol.startswith(href + "/")):
        return False
    var = parse_qs(sorgu)
    return all(
        var.get(k, [_VARSAYILAN_SORGU.get(k)])[0] == v[0] for k, v in parse_qs(href_sorgu).items()
    )


def menu_agaci(yol: str, sorgu: str = "") -> dict:
    menu = copy.deepcopy(MENU)
    konum: list[str] = []  # başlık şeridindeki kırıntı yolu: [grup, öğe] ya da [öğe]
    for ust in menu:
        for o in ust.get("ogeler", []):
            if _eslesir(o.get("href", ""), yol, sorgu):
                o["aktif"] = True
                ust["acik"] = True  # etkin sayfanın grubu açık gelir
                konum = [ust["ad"], o["ad"]]
        if _eslesir(ust.get("href", ""), yol, sorgu):
            ust["aktif"] = True
            konum = [ust["ad"]]
    return {"menu": menu, "konum": konum, "ders": zil.ust_bilgi(), "surum": statik_surum()}
