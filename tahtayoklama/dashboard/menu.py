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

# 2026-10-30: panel yeniden tasarımı: üst ALAN menüsü (6 alan) → alanın sayfaları. Alan dışı sabitler:
# ACIL (kırmızı düğme), ATOS (dipte vurgulu), AYARLAR (menü), TEMALAR (tema seçici).
# EBYS/Duyuru panosu/Kiosk ve diğer "/b/<ad>" yer tutucuları menüde yok (yakinda.py'de duruyor).
# acilir: alanın sayfaları sekmede açılır listede (Eğitim: hepsi dış bağlantı; Güvenlik: sayfalar
# taban.html'siz, sol menü hiç çıkmaz).
_OKUL = "/admin/okul-verisi"
ALANLAR: list[dict] = [
    {
        "ad": "Yoklama", "anahtar": "yoklama", "kisayol": "y", "ikon": "ev",
        "sayfalar": [
            {"ad": "Ders ızgarası", "href": "/", "ikon": "ev"},
            {"ad": "Bugünkü liste", "href": "/bugun", "ikon": "ev"},
            {"ad": "Rapor", "href": "/admin/rapor", "ikon": "grafik"},
            {"ad": "Aylık özet", "href": "/aylik-ozet", "ikon": "grafik"},
            {"ad": "Kulüp yoklaması", "href": "/kulup-yoklama", "ikon": "kullanicilar"},
        ],
    },
    {
        "ad": "Öğrenci ve personel", "anahtar": "personel", "kisayol": "p", "ikon": "kullanicilar",
        "sayfalar": [
            {"ad": "Öğrenciler ve veliler", "href": _OKUL + "?sekme=ogrenci", "ikon": "kullanicilar"},
            {"ad": "Personel", "href": _OKUL + "?sekme=personel", "ikon": "kullanicilar"},
            {"ad": "Sınıflar ve tahtalar", "href": "/admin/siniflar", "ikon": "tahta"},
            {"ad": "Ders programı", "href": _OKUL + "?sekme=program", "ikon": "saat"},
            {"ad": "Zil saatleri", "href": _OKUL + "?sekme=zil", "ikon": "zil"},
            {"ad": "Kulüpler", "href": "/admin/kulupler", "ikon": "kullanicilar"},
            {"ad": "Değişiklik günlüğü", "href": _OKUL + "?sekme=denetim", "ikon": "log"},
        ],
    },
    {
        "ad": "İletişim", "anahtar": "iletisim", "kisayol": "i", "ikon": "log",
        "sayfalar": [
            {"ad": "Veli mesajları", "href": "/veli-mesajlari", "ikon": "log", "sayac": "veli"},
            {"ad": "SMS gönder", "href": "/sms-git", "ikon": "log", "yeni_sekme": True},
            {"ad": "Yoklama SMS", "href": "/yoklama-sms-git", "ikon": "log", "yeni_sekme": True},
            {"ad": "SMS otomasyonu", "href": "/otomasyon-git", "ikon": "kaydirici", "yeni_sekme": True},
            {"ad": "Doğum günleri", "href": "/dogum", "ikon": "pasta", "yeni_sekme": True},
            {"ad": "Tahta duyuru", "href": "/admin/uzaktan#duyuru", "ikon": "zil"},
        ],
    },
    {
        "ad": "Eğitim", "anahtar": "egitim", "kisayol": "e", "ikon": "hedef", "acilir": True,
        "sayfalar": [
            {"ad": "Kelebek", "href": "/kelebek-git", "ikon": "tahta", "yeni_sekme": True},
            {"ad": "smual.app", "href": SMUAL_URL, "ikon": "yildiz", "yeni_sekme": True},
            {"ad": "smual.app yönetim", "href": SMUAL_YONETIM_URL, "ikon": "kaydirici", "yeni_sekme": True},
        ],
    },
    {
        "ad": "Güvenlik", "anahtar": "guvenlik", "kisayol": "k", "ikon": "kamera", "acilir": True,
        "sayfalar": [
            {"ad": "DVR kameralar", "href": "/kameralar", "ikon": "kamera"},
            {"ad": "IP kameralar (yedek)", "href": "/kameralar-ip", "ikon": "kamera"},
            {"ad": "Kamera kayıtları", "href": "/kameralar-kayit", "ikon": "kamera"},
            {"ad": "Güvenlik ekranı", "href": "/guvenlik", "ikon": "kamera"},
            {"ad": "Kiosk yüz tanıma", "href": KIOSK_YUZ_PANELI, "ikon": "kullanicilar", "yeni_sekme": True},
        ],
    },
    {
        "ad": "Sistem", "anahtar": "sistem", "kisayol": "s", "ikon": "sunucu",
        "sayfalar": [
            {"ad": "Tahtalar", "href": "/admin/uzaktan", "ikon": "tahta"},
            {"ad": "Sistem durumu", "href": "/sistem-durumu", "ikon": "nabiz"},
            {"ad": "Servis yönetimi", "href": "/servisler", "ikon": "sunucu"},
            {"ad": "Zamanlanmış görevler", "href": "/zamanlanmis-gorevler", "ikon": "saat"},
            {"ad": "Sunucular", "href": "/sunucular", "ikon": "katman"},
            {"ad": "Zil paneli", "href": "/panel-git/zil", "ikon": "zil", "yeni_sekme": True},
            {"ad": "Pano paneli", "href": "/panel-git/pano", "ikon": "tahta", "yeni_sekme": True},
            {"ad": "Kiosk paneli", "href": "/panel-git/kiosk", "ikon": "sunucu", "yeni_sekme": True},
            {"ad": "Bilgehan paneli", "href": "/panel-git/bilgehan", "ikon": "sunucu", "yeni_sekme": True},
        ],
    },
]

ACIL: dict = {"ad": "Acil durum", "kisayol": "a", "ikon": "uyari", "href": "/acil"}
ATOS: dict = {"ad": "Atos yapay zekâ", "kisayol": "t", "ikon": "yildiz", "href": "atos", "yeni_sekme": True}
AYARLAR: list[dict] = [
    {"ad": "Atos iş ve ayarlar", "href": "/b/atos", "ikon": "kaydirici"},
    {"ad": "Yazdır", "eylem": "yazdir", "ikon": "indir"},
    {"ad": "Klavye kısayolları", "eylem": "kisayollar", "ikon": "kaydirici"},
    {"ad": "Çıkış", "eylem": "cikis", "ikon": "cikis"},
]
# (anahtar, ad); sırası tema döngü düğmesinin sırasıdır, ilki varsayılan
TEMALAR: list[tuple[str, str]] = [
    ("sade-koyu", "Sade koyu"),
    ("kurumsal", "Sakin kurumsal"),
    ("lacivert", "Lacivert"),
    ("argon", "Argon açık"),
    ("argon-koyu", "Argon koyu"),
    ("material", "Material açık"),
    ("material-koyu", "Material koyu"),
    ("black", "Black"),
    ("koyu", "Taş Tahta"),
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
    alanlar = copy.deepcopy(ALANLAR)
    aktif_alan = None
    aktif_sayfa = None
    for alan in alanlar:
        for sayfa in alan["sayfalar"]:
            if aktif_sayfa is None and _eslesir(sayfa["href"], yol, sorgu):
                sayfa["aktif"] = True
                alan["aktif"] = True
                aktif_alan, aktif_sayfa = alan, sayfa
    return {
        "alanlar": alanlar,
        "aktif_alan": aktif_alan,
        "sayfalar": aktif_alan["sayfalar"] if aktif_alan else [],
        "konum": [aktif_alan["ad"], aktif_sayfa["ad"]] if aktif_alan else [],
        "acil": copy.deepcopy(ACIL),
        "atos": copy.deepcopy(ATOS),
        "ayarlar": copy.deepcopy(AYARLAR),
        "temalar": list(TEMALAR),
        "ders": zil.ust_bilgi(),
        "gun": zil.gun_adi(),
        "surum": statik_surum(),
    }
