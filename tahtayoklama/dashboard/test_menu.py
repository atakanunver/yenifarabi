"""menu.py: menü ağacı her sayfayı içerir, aktif işaretleme, şifresiz dış bağlantı."""
import json
import unittest

import menu
from app import app

DAHILI = {"/", "/admin/tahtalar", "/admin/siniflar", "/admin/rapor", "/kazanim-rapor",
          "/admin/uzaktan", "/servisler", "/sistem-durumu", "/sunucular"}


def _hrefler(ogeler):
    for o in ogeler:
        if o.get("href"):
            yield o["href"]
        yield from _hrefler(o.get("alt", []))


class TestMenu(unittest.TestCase):
    def test_tum_sayfalar_menude(self):
        hrefler = {h.split("#")[0] for ust in menu.MENU for h in _hrefler(ust["ogeler"])}
        self.assertTrue(DAHILI <= hrefler, DAHILI - hrefler)

    def test_menu_route_lari_var(self):
        rotalar = {r.path for r in app.routes}
        for ust in menu.MENU:
            for h in _hrefler(ust["ogeler"]):
                if h.startswith("/") and not h.startswith("//"):
                    self.assertIn(h.split("#")[0], rotalar, h)

    def test_dis_baglantilarda_kimlik_yok(self):
        self.assertNotIn("@", json.dumps(menu.MENU))

    def test_aktif_isaretleme(self):
        agac = menu.menu_agaci("/servisler")
        aktifler = [o["ad"] for u in agac["menu"] for o in u["ogeler"] if o.get("aktif")]
        self.assertEqual(aktifler, ["Servis yönetimi"])
        self.assertEqual([s["ad"] for s in agac["serit"] if s.get("aktif")], ["Servis yönetimi"])
        self.assertFalse(any(o.get("aktif") for u in menu.MENU for o in u["ogeler"]))  # kaynak bozulmaz

    def test_ana_sayfa_yalniz_tam_eslesme(self):
        agac = menu.menu_agaci("/admin/rapor")
        self.assertFalse([s for s in agac["serit"] if s["href"] == "/" and s.get("aktif")])

    def test_taban_tum_sablon_ortamlarinda_menu_var(self):
        import importlib
        for ad in ("app", "sunucular", "kazanim_rapor", "admin", "uzaktan_yonetim", "servis_yonetimi"):
            mod = importlib.import_module(ad)
            tpl = getattr(mod, "templates", None)
            if tpl is not None:
                self.assertIn("menu_agaci", tpl.env.globals, ad)


if __name__ == "__main__":
    unittest.main()
