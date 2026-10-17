"""menu.py: menü ağacı her sayfayı içerir, aktif işaretleme, şifresiz dış bağlantı."""
import json
import unittest

import menu
from app import app

DAHILI = {"/", "/admin/tahtalar", "/admin/siniflar", "/admin/rapor", "/kazanim",
          "/admin/uzaktan", "/servisler", "/sistem-durumu", "/sunucular", "/veli-mesajlari",
          "/acil", "/kameralar", "/kameralar-ip"}


def _ogeler(ust):
    """Üst başlık doğrudan bağlantıysa (Zil Paneli, Atos Yapay Zeka) 'ogeler' yoktur."""
    return ust.get("ogeler", [])


def _ust_hrefler(menu_listesi):
    for ust in menu_listesi:
        if ust.get("href"):
            yield ust["href"]
        yield from _hrefler(_ogeler(ust))


def _hrefler(ogeler):
    for o in ogeler:
        if o.get("href"):
            yield o["href"]
        yield from _hrefler(o.get("alt", []))


class TestMenu(unittest.TestCase):
    def test_tum_sayfalar_menude(self):
        hrefler = {h.split("#")[0] for h in _ust_hrefler(menu.MENU)}
        self.assertTrue(DAHILI <= hrefler, DAHILI - hrefler)

    def test_menu_route_lari_var(self):
        rotalar = {r.path for r in app.routes}
        for h in _ust_hrefler(menu.MENU):
            if h.startswith("/") and not h.startswith("//"):
                self.assertIn(h.split("#")[0], rotalar, h)

    def test_dis_baglantilarda_kimlik_yok(self):
        self.assertNotIn("@", json.dumps(menu.MENU))

    def test_yeni_menu_yapisi(self):
        adlar = [u["ad"] for u in menu.MENU]
        self.assertEqual(adlar, ["Ana Menü", "Acil Durum", "Yoklama", "Tahtalar", "Eğitim", "İletişim", "Kameralar", "Sistem",
                          "Zil Paneli", "Atos Yapay Zeka", "Temalar", "Ayarlar"])
        for kalkan in ("EBYS", "Pano", "Kiosk", "Google Form", "Anons-Zil", "Uygulamalar"):
            self.assertNotIn(kalkan, adlar)
        hrefler = set(_ust_hrefler(menu.MENU))
        for yer_tutucu in ("/b/ebys", "/b/pano", "/b/kiosk", "/b/form", "/b/anons", "/b/oyunlar"):
            self.assertNotIn(yer_tutucu, hrefler)
        eylemler = {o.get("eylem") for u in menu.MENU if u["ad"] == "Ayarlar" for o in _ogeler(u)}
        self.assertLessEqual({"serit", "yazdir", "kisayollar", "cikis"}, eylemler)
        temalar = {o.get("eylem") for u in menu.MENU if u["ad"] == "Temalar" for o in _ogeler(u)}
        self.assertEqual(temalar, {"tema:klasik", "tema:yumusak", "tema:koyu"})
        atos = [u for u in menu.MENU if u["ad"] == "Atos Yapay Zeka"]
        self.assertEqual([u.get("href") for u in atos], ["atos"])

    def test_kisayollar_benzersiz(self):
        harfler = [u["kisayol"] for u in menu.MENU]
        self.assertEqual(len(harfler), len(set(harfler)))

    def test_aktif_isaretleme(self):
        agac = menu.menu_agaci("/servisler")
        aktifler = [o["ad"] for u in agac["menu"] for o in _ogeler(u) if o.get("aktif")]
        self.assertEqual(aktifler, ["Servis yönetimi"])
        self.assertEqual([o["ad"] for u in menu.menu_agaci("/")["menu"] for o in _ogeler(u) if o.get("aktif")], ["Pano"])
        self.assertEqual([s["ad"] for s in agac["serit"] if s.get("aktif")], ["Servis yönetimi"])
        self.assertFalse(any(o.get("aktif") for u in menu.MENU for o in [u, *_ogeler(u)]))  # kaynak bozulmaz

    def test_ana_sayfa_yalniz_tam_eslesme(self):
        agac = menu.menu_agaci("/admin/rapor")
        self.assertFalse([s for s in agac["serit"] if s["href"] == "/" and s.get("aktif")])

    def test_taban_tum_sablon_ortamlarinda_menu_var(self):
        import importlib
        for ad in ("app", "sunucular", "kazanim_rapor", "admin", "uzaktan_yonetim", "servis_yonetimi", "yakinda", "veli_mesajlari"):
            mod = importlib.import_module(ad)
            tpl = getattr(mod, "templates", None)
            if tpl is not None:
                self.assertIn("menu_agaci", tpl.env.globals, ad)

    def test_statik_surum_dosya_degisince_degisir(self):
        # Yeni şablon + tarayıcı önbelleğindeki eski pano.css = bozuk düzen (2026-10-08 önizlemede görüldü)
        import os
        import time
        s1 = menu.menu_agaci("/")["surum"]
        yol = menu.STATIK_DIZINI / "pano.css"
        st = os.stat(yol)
        try:
            os.utime(yol, (st.st_atime, st.st_mtime + 5))
            menu._surum_onbellek.clear()
            s2 = menu.menu_agaci("/")["surum"]
        finally:
            os.utime(yol, (st.st_atime, st.st_mtime))
            menu._surum_onbellek.clear()
        self.assertTrue(s1)
        self.assertNotEqual(s1, s2)


if __name__ == "__main__":
    unittest.main()
