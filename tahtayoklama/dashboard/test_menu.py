"""menu.py: menü ağacı her sayfayı içerir, aktif işaretleme, şifresiz dış bağlantı."""
import json
import re
import unittest

import menu
from app import app

DAHILI = {"/", "/admin/siniflar", "/admin/rapor",
          "/admin/uzaktan", "/servisler", "/sistem-durumu", "/sunucular", "/veli-mesajlari",
          "/acil", "/kulup-yoklama", "/admin/kulupler", "/kameralar", "/kameralar-ip", "/zamanlanmis-gorevler"}


def _sayfalar():
    for alan in menu.ALANLAR:
        yield from alan["sayfalar"]


def _hrefler():
    yield from (s["href"] for s in _sayfalar())
    yield menu.ACIL["href"]
    yield menu.ATOS["href"]
    yield from (o["href"] for o in menu.AYARLAR if o.get("href"))


class TestMenu(unittest.TestCase):
    def test_alan_sirasi(self):
        self.assertEqual([a["ad"] for a in menu.ALANLAR],
                         ["Yoklama", "Öğrenci ve personel", "İletişim", "Eğitim", "Güvenlik", "Sistem"])
        self.assertEqual([a["kisayol"] for a in menu.ALANLAR], list("ypieks"))

    def test_tum_sayfalar_menude(self):
        hrefler = {h.split("#")[0] for h in _hrefler()}
        self.assertTrue(DAHILI <= hrefler, DAHILI - hrefler)

    def test_menu_route_lari_var(self):
        for h in _hrefler():
            if h.startswith("/") and not h.startswith("//"):
                yol = h.split("#")[0].split("?")[0]  # /panel-git/<ad> gibi parametreli rotalar da eşleşir
                self.assertTrue(any(getattr(r, "path_regex", None) and r.path_regex.match(yol) for r in app.routes), h)

    def test_dis_baglantilarda_kimlik_yok(self):
        self.assertNotIn("@", json.dumps([menu.ALANLAR, menu.ACIL, menu.ATOS, menu.AYARLAR]))

    def test_yapi(self):
        self.assertEqual(menu.ACIL["href"], "/acil")
        self.assertEqual(menu.ACIL["kisayol"], "a")
        self.assertEqual(menu.ATOS["href"], "atos")
        self.assertEqual(menu.ATOS["kisayol"], "t")
        eylemler = {o.get("eylem") for o in menu.AYARLAR}
        self.assertLessEqual({"yazdir", "kisayollar", "cikis"}, eylemler)
        self.assertIn("/b/atos", {o.get("href") for o in menu.AYARLAR})
        self.assertEqual(len(menu.TEMALAR), 9)
        self.assertIn(("koyu", "Taş Tahta"), menu.TEMALAR)
        veli = next(s for s in _sayfalar() if s["ad"] == "Veli mesajları")
        self.assertEqual(veli["sayac"], "veli")

    def test_kisayollar_benzersiz(self):
        harfler = [a["kisayol"] for a in menu.ALANLAR] + [menu.ACIL["kisayol"], menu.ATOS["kisayol"]]
        self.assertEqual(len(harfler), len(set(harfler)))

    def test_aktif_isaretleme(self):
        agac = menu.menu_agaci("/servisler")
        self.assertEqual(agac["aktif_alan"]["ad"], "Sistem")
        self.assertEqual(agac["konum"], ["Sistem", "Servis yönetimi"])
        self.assertEqual([s["ad"] for s in agac["sayfalar"] if s.get("aktif")], ["Servis yönetimi"])
        self.assertEqual([a["ad"] for a in agac["alanlar"] if a.get("aktif")], ["Sistem"])
        for anahtar in ("acil", "atos", "ayarlar", "temalar", "ders", "surum"):
            self.assertIn(anahtar, agac)
        self.assertFalse(any(s.get("aktif") for s in _sayfalar()) or any(a.get("aktif") for a in menu.ALANLAR))  # kaynak bozulmaz

    def test_ana_sayfa(self):
        self.assertEqual(menu.menu_agaci("/")["konum"], ["Yoklama", "Ders ızgarası"])
        agac = menu.menu_agaci("/admin/rapor")
        self.assertNotIn("Ders ızgarası", [s["ad"] for s in agac["sayfalar"] if s.get("aktif")])

    def test_okul_verisi_sekme_duyarli_aktif(self):
        for sorgu, ad in (("", "Öğrenciler ve veliler"), ("sekme=ogrenci&sinif=9-A", "Öğrenciler ve veliler"),
                          ("sekme=personel", "Personel"), ("sekme=program", "Ders programı"),
                          ("sekme=zil", "Zil saatleri"), ("sekme=denetim", "Değişiklik günlüğü")):
            agac = menu.menu_agaci("/admin/okul-verisi", sorgu)
            self.assertEqual([s["ad"] for s in agac["sayfalar"] if s.get("aktif")], [ad], sorgu)

    def test_menude_olmayan_yol(self):
        agac = menu.menu_agaci("/admin/siniflar/5/ogrenciler")
        self.assertEqual(agac["aktif_alan"]["ad"], "Öğrenci ve personel")
        for yol in ("/kazanim", "/b/atos"):
            agac = menu.menu_agaci(yol)
            self.assertIsNone(agac["aktif_alan"], yol)
            self.assertEqual(agac["konum"], [], yol)

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

    def _render(self, yol, sorgu=b""):
        # DB'siz: şablonu doğrudan render et (httpx yok → TestClient yok).
        from starlette.requests import Request

        import app as uygulama
        istek = Request({"type": "http", "method": "GET", "path": yol, "headers": [],
                         "query_string": sorgu, "server": ("farabi.local", 80), "scheme": "http", "root_path": ""})
        return uygulama.templates.env.from_string(
            '{% extends "taban.html" %}{% block baslik %}Başlık{% endblock %}').render(request=istek)

    @staticmethod
    def _sol_menu(html):
        bas = html.find('<nav class="sol-menu"')
        return html[bas:html.index("</nav>", bas)] if bas != -1 else ""

    def test_taban_kenar_menu_render(self):
        # 2026-10-30: kenar menü yerine üst alan çubuğu + sol sayfa menüsü.
        html = self._render("/admin/rapor")
        self.assertIn('class="ust-cubuk"', html)
        self.assertNotIn('class="kenar"', html)
        self.assertNotIn("kenar.js", html)
        self.assertIn("Yoklama › Rapor", html)
        self.assertIn('aria-current="page"', html)
        self.assertIn('href="/acil"', html)
        for ad in ("tema.css", "pano.css", "bilesen.css", "tema.js", "menu.js"):
            self.assertRegex(html, rf"/static/{re.escape(ad)}\?v=\d+")
        self.assertLess(html.index("tema.css"), html.index("pano.css"))
        self.assertLess(html.index("pano.css"), html.index("bilesen.css"))
        for kimlik in ('id="toast"', 'id="cikis-form"', 'id="kisayol-penceresi"', 'id="hakkinda-penceresi"',
                       'id="mini-durum"', 'id="menu-ac"', 'data-sayac="veli"'):
            self.assertIn(kimlik, html)
        self.assertNotIn("prefers-color-scheme", html)

    def test_ust_cubukta_alti_alan(self):
        html = self._render("/admin/rapor")
        sekmeler = re.findall(r'<(?:a|summary) class="alan-sekme"[^>]*>', html)
        self.assertEqual(len(sekmeler), 6)
        for etiket, alan in zip(sekmeler, menu.ALANLAR):
            if alan.get("acilir"):  # açılır alan: sekme <summary>, sayfalar panelde
                self.assertTrue(etiket.startswith("<summary"), alan["ad"])
            else:
                self.assertIn(f'href="{alan["sayfalar"][0]["href"]}"', etiket)
        aktif = [e for e in sekmeler if 'aria-current="true"' in e]
        self.assertEqual(len(aktif), 1)
        self.assertIn('href="/"', aktif[0])  # Yoklama alanının ilk sayfası

    def test_sol_menude_yalniz_aktif_alan(self):
        sol = self._sol_menu(self._render("/servisler"))
        self.assertIn("Servis yönetimi", sol)
        self.assertNotIn("Personel", sol)
        aktif = re.findall(r'<a class="sol-oge[^"]*"[^>]*aria-current="page"[^>]*>', sol)
        self.assertEqual(len(aktif), 1)
        self.assertIn('href="/servisler"', aktif[0])

    def test_acil_ve_atos_her_sayfada(self):
        for yol in ("/servisler", "/kazanim", "/"):
            html = self._render(yol)
            self.assertIn('href="/acil"', html, yol)
            self.assertIn('href="http://farabi.local:8010/"', html, yol)
        self.assertIn("Sistem › Servis yönetimi", self._render("/servisler"))

    def test_js_siz_gezinme(self):
        # Alan sekmeleri ve sol menü düz <a href>: JS olmadan da gezinilir.
        html = self._render("/servisler")
        acilir = [a for a in menu.ALANLAR if a.get("acilir")]
        self.assertEqual(len(re.findall(r'<a class="alan-sekme"[^>]*href="[^"]+"', html)), 6 - len(acilir))
        self.assertEqual(len(re.findall(r'<details class="alan-acilir"', html)), len(acilir))  # <details> JS'siz açılır
        sol = self._sol_menu(html)
        self.assertNotIn("<button", sol)
        sistem = next(a for a in menu.ALANLAR if a["anahtar"] == "sistem")
        self.assertEqual(len(re.findall(r'<a class="sol-oge[^"]*"[^>]*href="[^"]+"', sol)),
                         len(sistem["sayfalar"]))

    def test_tema_listesi_sayfada(self):
        html = self._render("/")
        m = re.search(r"window\.FARABI_TEMALAR\s*=\s*(\[[^\]]*\])", html)
        self.assertIsNotNone(m)
        self.assertEqual(json.loads(m.group(1)), [a for a, _ in menu.TEMALAR])
        self.assertLess(m.start(), html.index("/static/tema.js"))

    def test_menude_olmayan_yolda_render(self):
        html = self._render("/kazanim")
        self.assertEqual(self._sol_menu(html), "")
        self.assertNotIn('class="sol-oge', html)
        self.assertNotIn('aria-current="true"', html)

    def test_acilir_alanlar_tum_sayfalari_listeler(self):
        # Eğitim: hepsi dış bağlantı; Güvenlik: sayfalar taban.html'siz → sol menü hiç çıkmaz (2026-10-30).
        html = self._render("/")
        beklenen = {
            "egitim": {menu.SMUAL_URL, menu.SMUAL_YONETIM_URL, "/kelebek-git"},
            "guvenlik": {"/kameralar", "/kameralar-ip", "/kameralar-kayit", "/guvenlik", menu.KIOSK_YUZ_PANELI},
        }
        for anahtar, hrefler in beklenen.items():
            bas = html.find(f'<details class="alan-acilir" data-alan="{anahtar}"')
            self.assertNotEqual(bas, -1, anahtar)
            parca = html[bas:html.index("</details>", bas)]
            self.assertEqual(set(re.findall(r'<a [^>]*?href="([^"]+)"', parca)), hrefler, anahtar)
            self.assertIn("<summary", parca)
        self.assertIn('target="_blank" rel="noopener"', html[html.find('data-alan="egitim"'):])

    def test_her_sayfa_kabuktan_erisilir(self):
        # "/" kabuğunda: açılır alanların tüm sayfaları, diğer alanların ilk sayfası (sekme bağlantısı)
        self.assertEqual({a["anahtar"] for a in menu.ALANLAR if a.get("acilir")}, {"egitim", "guvenlik"})
        html = self._render("/")
        for alan in menu.ALANLAR:
            for sayfa in (alan["sayfalar"] if alan.get("acilir") else alan["sayfalar"][:1]):
                self.assertIn(f'href="{sayfa["href"]}"', html, sayfa["ad"])
        # Açılır olmayan alanların diğer sayfaları kendi alanında sol menüden erişilir
        for alan in menu.ALANLAR:
            if alan.get("acilir"):
                continue
            ilk = alan["sayfalar"][0]["href"]
            yol, _, sorgu = ilk.partition("?")
            sol = self._sol_menu(self._render(yol, sorgu.encode()))
            for sayfa in alan["sayfalar"]:
                self.assertIn(f'href="{sayfa["href"]}"', sol, sayfa["ad"])

    def test_gun_adi_cumle_duzeni(self):
        # Üst çubukta BÜYÜK HARF yok; .capitalize() "İ"yi bozar, sabit sözlük kullanılır.
        from datetime import date

        import zil
        self.assertEqual(zil.gun_adi(date(2026, 10, 31)), "Cumartesi")
        self.assertEqual(zil.gun_adi(date(2026, 10, 28)), "Çarşamba")
        self.assertEqual(menu.menu_agaci("/")["gun"], zil.gun_adi())
        self.assertIn(f">{zil.gun_adi()}<", self._render("/"))


if __name__ == "__main__":
    unittest.main()