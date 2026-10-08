"""menu.py — dashboard menü çubuğu, ikon şeridi ve mobil çekmecenin TEK kaynağı (2026-10-08).
taban.html üçünü de bu ağaçtan üretir; menü öğesi başka yerde elle yazılmaz."""

import copy

ZIL_PANELI = "http://192.168.23.230:8090/"   # kimlik gömülmez; tarayıcı Basic Auth sorar

MENU: list[dict] = [
    {"ad": "Dosya", "kisayol": "d", "ogeler": [
        {"ad": "Ana pano", "href": "/", "ikon": "ev"},
        {"ad": "Yazdır", "eylem": "yazdir"},
        {"ayrac": True},
        {"ad": "Çıkış", "eylem": "cikis", "ikon": "cikis"},
    ]},
    {"ad": "Düzen", "kisayol": "z", "ogeler": [
        {"ad": "Sayfayı yenile", "eylem": "yenile", "ikon": "yenile"},
        {"ad": "Bağlantıyı kopyala", "eylem": "bagla-kopyala"},
    ]},
    {"ad": "Yoklama", "kisayol": "y", "ogeler": [
        {"ad": "Pano", "href": "/", "ikon": "ev"},
        {"ad": "Tahtalar", "href": "/admin/tahtalar", "ikon": "monitor"},
        {"ad": "Sınıflar", "href": "/admin/siniflar", "ikon": "kullanicilar"},
        {"ad": "Rapor", "href": "/admin/rapor", "ikon": "grafik"},
        {"ad": "Kazanım raporu", "href": "/kazanim-rapor", "ikon": "hedef"},
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
    ]},
    {"ad": "Uygulamalar", "kisayol": "u", "ogeler": [
        {"ad": "Atos yapay zeka", "href": "atos", "ikon": "yildiz", "yeni_sekme": True},
        {"ad": "SMS sistemi", "href": "/sms-git", "ikon": "zil", "yeni_sekme": True},
        {"ad": "SMS otomasyonu", "href": "/otomasyon-git", "ikon": "kaydirici", "yeni_sekme": True},
        {"ad": "Doğum günleri", "href": "/dogum", "ikon": "pasta", "yeni_sekme": True},
        {"ad": "Zil paneli", "href": ZIL_PANELI, "ikon": "zil", "yeni_sekme": True},
    ]},
    {"ad": "Görünüm", "kisayol": "g", "ogeler": [
        {"ad": "Tema", "alt": [
            {"ad": "Klasik", "eylem": "tema:klasik", "ikon": "gunes"},
            {"ad": "Yumuşak", "eylem": "tema:yumusak", "ikon": "bulut"},
            {"ad": "Koyu", "eylem": "tema:koyu", "ikon": "ay"},
        ]},
        {"ad": "Kenar şeridini gizle/göster", "eylem": "serit"},
    ]},
    {"ad": "Yardım", "kisayol": "r", "ogeler": [
        {"ad": "Klavye kısayolları", "eylem": "kisayollar"},
        {"ad": "Hakkında", "eylem": "hakkinda"},
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
    return {"menu": menu, "serit": serit}
