import asyncio
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException
from fastapi.requests import Request
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db
import gorsel
import gorsel_panel
import menu
import zil
from scripts import hafta_karti_uret

ZIL = {
    "dersler": [{"no": 1, "baslangic": "08:10", "bitis": "08:50"}],
    "ogle_arasi": {"baslangic": "12:10", "bitis": "13:30"},
    "ders_gunleri": [1, 2, 3, 4, 5],
}
UZUN = "Çağlar Şükrü Öğüt-Ünlü İğdelioğlu"


def _png(boyut=(1672, 941), renk=(10, 20, 80)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", boyut, renk).save(b, "PNG")
    return b.getvalue()


def _istek(path="/gorsel", accept="text/html"):
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "GET", "path": path, "query_string": b"",
             "headers": [(b"accept", accept.encode())], "client": ("127.0.0.1", 1),
             "server": ("farabi.local", 80), "scheme": "http"}
    return Request(scope, receive)


class _Ortak(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.gecici = Path(self.tmp.name)
        for y in (
            mock.patch.object(gorsel, "VERI", self.gecici),
            mock.patch.object(gorsel, "GORSEL_DIZINI", self.gecici / "gorseller"),
            mock.patch.object(gorsel, "DURUM_YOLU", self.gecici / "gorsel_durum.json"),
            mock.patch.object(db, "DB_YOLU", self.gecici / "t.db"),
            mock.patch.object(zil, "_zil_yukle", lambda: ZIL),
        ):
            y.start()
            self.addCleanup(y.stop)
        db.semayi_kur()
        self.addCleanup(self.tmp.cleanup)


class TestKart(unittest.TestCase):
    def test_uzun_ad_1920x1080_ve_cok_ad(self):
        k = {"maraton": [{"ad_soyad": UZUN, "sinif": "9-B", "ayrinti": "120 doğru cevap"}],
             "etkinlik": [{"ad_soyad": UZUN, "sinif": "10-A", "ayrinti": "14 etkinlik"}] * 3}
        im = Image.open(io.BytesIO(gorsel.hafta_karti(_png(), k)))
        self.assertEqual(im.size, (1920, 1080))
        self.assertEqual(im.format, "PNG")

    def test_uc_isimli_iki_panel_sol_serit_bos(self):
        arka = _png(renk=(10, 20, 80))
        uc = [{"ad_soyad": a, "sinif": "9-B", "ayrinti": "5 etkinlik"} for a in ("Ayşe Yıldız", UZUN, "Işıl Öz")]
        im = Image.open(io.BytesIO(gorsel.hafta_karti(arka, {"maraton": uc, "etkinlik": uc}))).convert("RGB")
        sol = im.crop((0, 0, 420, 1080))
        self.assertEqual(sol.getcolors(), [(420 * 1080, (10, 20, 80))])  # ikon alanı arka planla aynı
        sag = im.crop((470, 170, 1840, 900)).convert("L").point(lambda p: p > 200 and 255)
        self.assertIsNotNone(sag.getbbox())  # paneller ve yazı çizildi

    def test_tek_kategori_sag_panelde(self):
        k = [{"ad_soyad": "Ayşe Yılmaz", "sinif": "9-A", "ayrinti": "3 etkinlik"}]
        arka = _png(renk=(10, 20, 80))
        im = Image.open(io.BytesIO(gorsel.hafta_karti(arka, {"maraton": k, "etkinlik": []}))).convert("RGB")
        self.assertEqual(im.crop((0, 0, 1150, 1080)).getcolors(), [(1150 * 1080, (10, 20, 80))])
        self.assertIsNotNone(im.crop((1150, 0, 1920, 1080)).convert("L").point(lambda p: p > 200 and 255).getbbox())

    def test_cok_uzun_tek_kelime_tasmaz(self):
        k = {"etkinlik": [{"ad_soyad": "Ç" * 80, "sinif": "9-A", "ayrinti": "x" * 90}] * 3}
        im = Image.open(io.BytesIO(gorsel.hafta_karti(_png(renk=(0, 0, 0)), k))).convert("RGB")
        self.assertEqual(im.crop((0, 0, 420, 1080)).getbbox(), None)

    def test_ad_panele_sigar(self):
        b = gorsel._blok({"ad_soyad": UZUN, "sinif": "9-B", "ayrinti": "x"}, 420, 370)
        for metin, font, _ in b["satirlar"]:
            self.assertLessEqual(font.getlength(metin), 420)
        self.assertLessEqual(b["yukseklik"], 370)

    def test_tek_kategori_ve_bos(self):
        k = [{"ad_soyad": "Ayşe Yılmaz", "sinif": "9-A"}]
        for tek in ({"maraton": k, "etkinlik": []}, {"etkinlik": k}):
            im = Image.open(io.BytesIO(gorsel.hafta_karti(_png(), tek)))
            self.assertEqual(im.size, (1920, 1080))
        with self.assertRaises(ValueError):
            gorsel.hafta_karti(_png(), {"maraton": [], "etkinlik": []})
        with self.assertRaises(ValueError):
            gorsel.hafta_karti(_png(), {})

    def test_yazi_basildi_ve_gecersiz_arka_plan(self):
        k = {"maraton": [{"ad_soyad": "Ayşe", "sinif": "9-A"}]}
        arka = _png(renk=(0, 0, 0))
        cikti = Image.open(io.BytesIO(gorsel.hafta_karti(arka, k)))
        self.assertIsNotNone(cikti.getbbox() and cikti.convert("L").point(lambda p: p > 60 and 255).getbbox())
        with self.assertRaises(gorsel.GorselHatasi):
            gorsel.hafta_karti(b"png-degil", k)

    def test_font_yoksa_anlamli_hata(self):
        with mock.patch.object(gorsel, "FONT_YOLU", "/yok/font.ttf"), self.assertRaises(gorsel.GorselHatasi):
            gorsel.hafta_karti(_png(), {"maraton": [{"ad_soyad": "A", "sinif": "9-A"}]})


class _Yanit:
    def __init__(self, veri):
        self.veri = json.dumps(veri).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, *a):
        return self.veri


class TestIstemci(_Ortak):
    def test_ai_arka_plan_istek_ve_yanit(self):
        import base64
        png = _png()
        yakalanan = {}

        def sahte(istek, timeout):
            yakalanan.update(istek=istek, timeout=timeout)
            return _Yanit({"data": [{"b64_json": base64.b64encode(png).decode()}]})

        with mock.patch.dict("os.environ", {"CLIPROXY_API_KEY": "gizli-x"}), \
             mock.patch("urllib.request.urlopen", sahte):
            sonuc = gorsel.ai_arka_plan("lacivert zemin")
        self.assertEqual(sonuc, png)
        i = yakalanan["istek"]
        govde = json.loads(i.data)
        self.assertEqual(govde["model"], "gpt-image-2")
        self.assertEqual((govde["size"], govde["n"]), ("1536x1024", 1))
        self.assertIn("lacivert zemin", govde["prompt"])
        self.assertIn(gorsel.PROMPT_EKI, govde["prompt"])
        self.assertEqual(i.get_header("Authorization"), "Bearer gizli-x")
        self.assertEqual(yakalanan["timeout"], 150)

    def test_anahtar_dosyadan_ve_yoksa_hata(self):
        ayar = self.gecici / "cliproxy.json"
        with mock.patch.dict("os.environ", {}), mock.patch.object(gorsel, "CLIPROXY_AYAR", ayar):
            os.environ.pop("CLIPROXY_API_KEY", None)
            with self.assertRaises(gorsel.GorselHatasi) as h:
                gorsel._anahtar()
            self.assertIn("cliproxy.json", str(h.exception))
            ayar.write_text('{"anahtar": "dosya-anahtari"}')
            self.assertEqual(gorsel._anahtar(), "dosya-anahtari")

    def test_http_hatasi_ve_bos_prompt(self):
        import urllib.error
        hata = urllib.error.HTTPError("u", 500, "x", {}, None)
        with mock.patch.dict("os.environ", {"CLIPROXY_API_KEY": "k"}), \
             mock.patch("urllib.request.urlopen", side_effect=hata), \
             self.assertRaises(gorsel.GorselHatasi):
            gorsel.ai_arka_plan("x")
        with self.assertRaises(gorsel.GorselHatasi):
            gorsel.ai_arka_plan("  ")

    def test_hafta_kazananlari_url(self):
        gorulen = []

        def sahte(url, timeout):
            gorulen.append(url)
            return _Yanit({"hafta": "2026-11-09", "kesin": False, "kategoriler": {"maraton": [], "etkinlik": []}})

        with mock.patch("urllib.request.urlopen", sahte):
            v = gorsel.hafta_kazananlari("2026-11-09", True)
        self.assertEqual(v["hafta"], "2026-11-09")
        self.assertIn("127.0.0.1:9090/api/odul/hafta", gorulen[0])
        self.assertIn("hb=2026-11-09", gorulen[0])
        self.assertIn("gecici=1", gorulen[0])


class TestDurum(_Ortak):
    def test_sayac_sinir_ve_onay(self):
        for _ in range(gorsel.GUNLUK_SINIR):
            self.assertTrue(gorsel.uretim_hakki_al())
        self.assertFalse(gorsel.uretim_hakki_al())
        self.assertEqual(gorsel.kalan_hak(), 0)
        with self.assertRaises(gorsel.GorselHatasi):
            gorsel.onayla()
        aday = gorsel.aday_kaydet(_png())
        self.assertTrue(aday.is_file())
        onayli = gorsel.onayla("2026-11-09")
        d = json.loads(gorsel.DURUM_YOLU.read_text())
        self.assertEqual(d["onayli_arka_plan"], str(onayli))
        self.assertEqual(d["hafta"], "2026-11-09")
        self.assertEqual(d["uretim"]["sayi"], gorsel.GUNLUK_SINIR)
        gorsel.gonderim_kaydet([{"tahta": "fenlab", "basarili": True}])
        self.assertEqual(gorsel.durum_oku()["gonderim_gunlugu"][-1]["tahta"], "fenlab")

    def test_kart_arsivlenir(self):
        gorsel.aday_kaydet(_png())
        yol = gorsel.kart_uret_ve_arsivle({"maraton": [{"ad_soyad": "Ali", "sinif": "9-A"}]})
        self.assertRegex(yol.name, r"^\d{4}-\d{2}-\d{2}_\d{4}_kart\.png$")
        with Image.open(yol) as im:
            self.assertEqual(im.size, (1920, 1080))


def _kaz(kesin=True, dolu=True):
    k = {"maraton": [{"ad_soyad": "Uydurma Kişi", "sinif": "9-A", "ayrinti": "x"}] if dolu else [], "etkinlik": []}
    return {"hafta": "2026-11-02", "kesin": kesin, "kategoriler": k}


class TestHaftaKarti(_Ortak):
    def _kos(self, kaz, ai=None, **kw):
        ai = ai or mock.Mock(return_value=_png())
        from scripts import duvar_kagidi
        with mock.patch.object(gorsel, "hafta_kazananlari", return_value=kaz), \
             mock.patch.object(gorsel, "ai_arka_plan", ai), \
             mock.patch.object(duvar_kagidi, "gonder", mock.AsyncMock()) as g, \
             mock.patch.object(duvar_kagidi, "geri_al", mock.AsyncMock()) as ga, \
             mock.patch("ssh_istemci.komut_calistir", mock.AsyncMock()) as ssh:
            kod = hafta_karti_uret.calistir(**kw)
        g.assert_not_called()
        ga.assert_not_called()
        ssh.assert_not_called()
        return kod, ai

    def test_aday_yok(self):
        for kaz in (_kaz(kesin=False), _kaz(dolu=False)):
            kod, ai = self._kos(kaz)
            self.assertEqual(kod, 0)
            ai.assert_not_called()
        self.assertEqual(gorsel.arsiv_listele(), [])

    def test_kart_olusur_idempotent_ve_zorla(self):
        kod, ai = self._kos(_kaz())
        self.assertEqual(kod, 0)
        ai.assert_called_once()
        kartlar = [x for x in gorsel.arsiv_listele() if x["tur"] == "hafta-kart"]
        self.assertEqual(len(kartlar), 1)
        self.assertNotIn("Uydurma", kartlar[0]["ad"])
        self.assertEqual(gorsel.durum_oku()["hafta_kartlari"]["2026-11-02"], kartlar[0]["ad"])
        self.assertEqual(self._kos(_kaz())[0], 0)  # tekrar: üretmez
        self.assertEqual(len([x for x in gorsel.arsiv_listele() if x["tur"] == "hafta-kart"]), 1)
        self._kos(_kaz(), zorla=True)
        self.assertEqual(len([x for x in gorsel.arsiv_listele() if x["tur"] == "hafta-kart"]), 2)

    def test_onayli_arka_plan_kullanilir_ve_sinir(self):
        gorsel.aday_kaydet(_png())
        gorsel.onayla()
        kod, ai = self._kos(_kaz())
        self.assertEqual(kod, 0)
        ai.assert_not_called()
        # onaysız + sınır dolu -> hata kodu, kart yok
        gorsel.durum_guncelle(onayli_arka_plan=None, hafta_kartlari={},
                              uretim={"tarih": gorsel.bugun(), "sayi": gorsel.GUNLUK_SINIR})
        kod, ai = self._kos(_kaz())
        self.assertEqual(kod, 1)
        ai.assert_not_called()


class TestPanel(_Ortak):
    def test_sayfa_oturumsuz_303_oturumlu_200(self):
        with mock.patch("auth.dogrula", return_value=False), self.assertRaises(HTTPException) as h:
            asyncio.run(gorsel_panel.gorsel_sayfa(_istek()))
        self.assertEqual(h.exception.status_code, 303)
        self.assertEqual(h.exception.headers["Location"], "/giris")
        with mock.patch("auth.dogrula", return_value=True), \
             mock.patch("tahta_kaydi.tahtalari_yukle", return_value=[{"ad": "fenlab"}]):
            yanit = asyncio.run(gorsel_panel.gorsel_sayfa(_istek()))
        self.assertEqual(yanit.status_code, 200)
        html = yanit.body.decode()
        self.assertIn("Görsel Oluşturma Paneli", html)
        self.assertIn('id="prompt"', html)
        self.assertIn("Görsel arşivi", html)
        self.assertIn('name="tahta" value="fenlab"', html)
        self.assertNotIn("confirm(", html)

    def test_arsiv_listele_ve_yol_gecisi(self):
        a = gorsel.arsivle("hafta-kart", _png())
        b = gorsel.arsivle("serbest", _png())
        c = gorsel.arsivle("serbest", _png())  # aynı dakika: ek numara
        self.assertNotEqual(b, c)
        (a.parent / "baska.png").write_bytes(_png())
        (a.parent / "x.txt").write_text("x")
        liste = gorsel.arsiv_listele()
        self.assertEqual({x["ad"] for x in liste}, {a.name, b.name, c.name})
        self.assertEqual([x["ad"] for x in liste], sorted([a.name, b.name, c.name], reverse=True))
        self.assertEqual(next(x for x in liste if x["ad"] == a.name)["tur"], "hafta-kart")
        self.assertEqual(gorsel.arsiv_yolu(a.name), a)
        gizli = self.gecici / "gizli.png"
        gizli.write_bytes(_png())
        for kotu in ("../gizli.png", "../../gizli.png", "/etc/passwd", "baska.png", "", a.name + "/..", "2026-11-10_0610_x/../a.png"):
            self.assertIsNone(gorsel.arsiv_yolu(kotu), kotu)
        with mock.patch("uzaktan_yonetim._dogrula"):
            self.assertEqual(asyncio.run(gorsel_panel.gorsel_arsiv_dosya(_istek(), "../gizli.png")).status_code, 404)
            self.assertEqual(asyncio.run(gorsel_panel.gorsel_arsiv_dosya(_istek(), a.name)).status_code, 200)
            self.assertEqual(len(asyncio.run(gorsel_panel.gorsel_arsiv(_istek()))["gorseller"]), 3)

    def _gonder_istegi(self, dosya, tahtalar):
        req = _istek()
        form = mock.Mock()
        form.get = {"dosya": dosya}.get
        form.getlist = lambda k: list(tahtalar)
        req.form = mock.AsyncMock(return_value=form)
        return req

    def test_gonder_secili_tahtalara_ve_hatalar(self):
        yol = gorsel.arsivle("hafta-kart", _png())
        sahte = mock.AsyncMock(side_effect=lambda a, y: {"tahta": a, "basarili": a != "b", "detay": "x"})
        with mock.patch("uzaktan_yonetim._dogrula"), \
             mock.patch("tahta_kaydi.tahtalari_yukle", return_value=[{"ad": "a"}, {"ad": "b"}, {"ad": "c"}]), \
             mock.patch.object(gorsel_panel.duvar_kagidi, "gonder", sahte), \
             mock.patch("uzaktan_yonetim._denetim_yaz") as den:
            v = asyncio.run(gorsel_panel.gorsel_gonder(self._gonder_istegi(yol.name, ["a", "b", "yok"])))
            self.assertEqual(sahte.await_count, 2)  # bilinmeyen tahta elenir
            self.assertFalse(v["ok"])
            self.assertEqual([r["ok"] for r in v["sonuclar"]], [True, False])
            self.assertEqual(sahte.await_args.args[1], yol)
            self.assertEqual(den.call_args.args[1], "gorsel_gonder")
            self.assertEqual(len(gorsel.durum_oku()["gonderim_gunlugu"]), 2)
            # seçili boş / geçersiz dosya
            sahte.reset_mock()
            self.assertEqual(asyncio.run(gorsel_panel.gorsel_gonder(self._gonder_istegi(yol.name, []))).status_code, 400)
            self.assertEqual(asyncio.run(gorsel_panel.gorsel_gonder(self._gonder_istegi("../x.png", ["a"]))).status_code, 400)
            sahte.assert_not_awaited()

    def test_geri_al_her_tahta(self):
        sahte = mock.AsyncMock(side_effect=lambda a: {"tahta": a, "basarili": a != "b", "detay": "x"})
        with mock.patch("uzaktan_yonetim._dogrula"), \
             mock.patch("tahta_kaydi.tahtalari_yukle", return_value=[{"ad": "a"}, {"ad": "b"}]), \
             mock.patch.object(gorsel_panel.duvar_kagidi, "geri_al", sahte), \
             mock.patch("uzaktan_yonetim._denetim_yaz") as den:
            v = asyncio.run(gorsel_panel.gorsel_geri_al(_istek()))
        self.assertEqual(sahte.await_count, 2)
        self.assertFalse(v["ok"])
        self.assertEqual(len(v["hatalar"]), 1)
        self.assertEqual(den.call_args.args[1], "gorsel_geri_al")

    def test_uret_sinir_ve_arka_plan_gorevi(self):
        async def kos():
            req = _istek()
            form = mock.Mock()
            form.get = {"prompt": "mavi zemin", "tur": "arka_plan"}.get
            req.form = mock.AsyncMock(return_value=form)
            with mock.patch("uzaktan_yonetim._dogrula"), \
                 mock.patch("uzaktan_yonetim._denetim_yaz"), \
                 mock.patch.object(gorsel, "ai_arka_plan", return_value=_png()) as ai:
                gorsel_panel._is.update(durum="bosta")
                v = await gorsel_panel.gorsel_uret(req)
                self.assertTrue(v["ok"])
                await asyncio.gather(*gorsel_panel._gorevler)
                self.assertEqual(gorsel_panel._is["durum"], "hazir")
                self.assertEqual(ai.call_args.args[0], "mavi zemin")
                self.assertTrue(gorsel.durum_oku()["aday_arka_plan"])
                self.assertTrue(gorsel_panel._is["dosya"].endswith("_arka-plan.png"))
                # sınır
                gorsel.durum_guncelle(uretim={"tarih": gorsel.bugun(), "sayi": gorsel.GUNLUK_SINIR})
                r = await gorsel_panel.gorsel_uret(req)
                self.assertEqual(r.status_code, 429)

        asyncio.run(kos())

    def test_menu_ogesi(self):
        sayfalar = [s for a in menu.ALANLAR for s in a["sayfalar"]]
        oge = next(s for s in sayfalar if s["href"] == "/gorsel")
        self.assertEqual(oge["ad"], "Görsel Oluşturma Paneli")
        self.assertEqual(menu.menu_agaci("/gorsel")["konum"][1], "Görsel Oluşturma Paneli")


if __name__ == "__main__":
    unittest.main()
