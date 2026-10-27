"""menu.py: menü ağacı her sayfayı içerir, aktif işaretleme, şifresiz dış bağlantı."""
import json
import unittest

import menu
from app import app

DAHILI = {"/", "/admin/siniflar", "/admin/rapor",
          "/admin/uzaktan", "/servisler", "/sistem-durumu", "/sunucular", "/veli-mesajlari",
          "/acil", "/kulup-yoklama", "/admin/kulupler", "/kameralar", "/kameralar-ip", "/zamanlanmis-gorevler"}


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
        for h in _ust_hrefler(menu.MENU):
            if h.startswith("/") and not h.startswith("//"):
                yol = h.split("#")[0]  # /panel-git/<ad> gibi parametreli rotalar da eşleşir
                self.assertTrue(any(getattr(r, "path_regex", None) and r.path_regex.match(yol) for r in app.routes), h)

    def test_dis_baglantilarda_kimlik_yok(self):
        self.assertNotIn("@", json.dumps(menu.MENU))

    def test_yeni_menu_yapisi(self):
        adlar = [u["ad"] for u in menu.MENU]
        # 2026-10-23: sol kenar menü sırası; Acil en üstte sabit, Atos/Temalar/Ayarlar dipte
        self.assertEqual(adlar, ["Acil durum", "Ana pano", "Yoklama", "Tahtalar", "Zil paneli", "Bilgehan Paneli", "Kiosk Paneli", "Pano Paneli", "Kiosk yüz tanıma paneli", "İletişim", "Eğitim",
                                 "Kelebek", "Güvenlik", "Sistem", "Atos yapay zekâ", "Temalar", "Ayarlar"])
        self.assertEqual([u["ad"] for u in menu.MENU if u.get("acil")], ["Acil durum"])
        self.assertEqual([u["ad"] for u in menu.MENU if u.get("alt")], ["Atos yapay zekâ", "Temalar", "Ayarlar"])
        for kalkan in ("EBYS", "Pano", "Kiosk", "Google Form", "Anons-Zil", "Uygulamalar"):
            self.assertNotIn(kalkan, adlar)
        hrefler = set(_ust_hrefler(menu.MENU))
        for yer_tutucu in ("/b/ebys", "/b/pano", "/b/kiosk", "/b/form", "/b/anons", "/b/oyunlar"):
            self.assertNotIn(yer_tutucu, hrefler)
        eylemler = {o.get("eylem") for u in menu.MENU if u["ad"] == "Ayarlar" for o in _ogeler(u)}
        self.assertLessEqual({"yazdir", "kisayollar", "cikis"}, eylemler)
        temalar = {o.get("eylem") for u in menu.MENU if u["ad"] == "Temalar" for o in _ogeler(u)}
        self.assertEqual(temalar, {"tema:argon", "tema:argon-koyu", "tema:koyu", "tema:black", "tema:material", "tema:material-koyu"})
        atos = [u for u in menu.MENU if u["ad"] == "Atos yapay zekâ"]
        self.assertEqual([u.get("href") for u in atos], ["atos"])

    def test_kisayollar_benzersiz(self):
        harfler = [u["kisayol"] for u in menu.MENU]
        self.assertEqual(len(harfler), len(set(harfler)))

    def test_aktif_isaretleme(self):
        agac = menu.menu_agaci("/servisler")
        aktifler = [o["ad"] for u in agac["menu"] for o in _ogeler(u) if o.get("aktif")]
        self.assertEqual(aktifler, ["Servis yönetimi"])
        self.assertEqual([u["ad"] for u in agac["menu"] if u.get("acik")], ["Sistem"])  # etkin grup açık gelir
        self.assertEqual(agac["konum"], ["Sistem", "Servis yönetimi"])
        ana = menu.menu_agaci("/")
        self.assertEqual([u["ad"] for u in ana["menu"] if u.get("aktif")], ["Ana pano"])
        self.assertEqual(ana["konum"], ["Ana pano"])
        self.assertFalse(any(o.get("aktif") or o.get("acik") for u in menu.MENU for o in [u, *_ogeler(u)]))  # kaynak bozulmaz

    def test_ana_sayfa_yalniz_tam_eslesme(self):
        agac = menu.menu_agaci("/admin/rapor")
        self.assertFalse([u for u in agac["menu"] if u.get("href") == "/" and u.get("aktif")])

    def test_taban_tum_sablon_ortamlarinda_menu_var(self):
        import importlib
        for ad in ("app", "sunucular", "kazanim_rapor", "admin", "uzaktan_yonetim", "servis_yonetimi", "zamanlanmis_gorevler", "yakinda", "veli_mesajlari"):
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
            os.utime(yol, (st.st_atime, st.st_mtime + 86400))
            menu._surum_onbellek.clear()
            s2 = menu.menu_agaci("/")["surum"]
        finally:
            os.utime(yol, (st.st_atime, st.st_mtime))
            menu._surum_onbellek.clear()
        self.assertTrue(s1)
        self.assertNotEqual(s1, s2)

    def test_ders_bilgisi_zil_yoksa_bos(self):
        # Başlık şeridi zil.json bozuk/eksikken de render edilmeli (2026-10-23)
        from unittest import mock

        import zil
        with mock.patch.object(zil, "ders_saatleri", side_effect=OSError), \
                mock.patch.object(zil, "okul_gunu_mu", return_value=True):
            self.assertEqual(zil.ust_bilgi(), "")

    def test_taban_kenar_menu_render(self):
        # Üst menü çubuğu yok, kenar menü + kırıntı yolu var (2026-10-23). DB'siz: şablonu doğrudan render et.
        from starlette.requests import Request

        import app as uygulama
        istek = Request({"type": "http", "method": "GET", "path": "/admin/rapor", "headers": [],
                         "query_string": b"", "server": ("farabi.local", 80), "scheme": "http", "root_path": ""})
        html = uygulama.templates.env.from_string(
            '{% extends "taban.html" %}{% block baslik %}Rapor{% endblock %}').render(request=istek)
        self.assertIn('class="kenar"', html)
        self.assertNotIn('role="menubar"', html)
        self.assertIn("Yoklama › Rapor", html)
        self.assertIn('aria-current="page"', html)
        self.assertIn('href="/acil"', html)

if __name__ == "__main__":
    unittest.main()