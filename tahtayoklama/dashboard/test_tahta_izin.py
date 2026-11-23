"""Onaylı veli izinleri: dashboard yapılandırması → tahta_istemci izinler.json →
yoklama.py başlangıç durumu. Ağ yok (urllib açıcısı mock'lanır); yoklama.py
PyQt6 yoksa sahte modülle içe aktarılır (yalnız saf fonksiyonlar test edilir)."""

import io
import json
import sys
import types
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from zoneinfo import ZoneInfo

import tahta_api

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tahta_istemci as ti


def _yoklama_yukle():
    try:
        import PyQt6.QtWidgets  # noqa: F401
        import yoklama
        return yoklama
    except ImportError:
        pass

    class _SahteMeta(type):
        def __getattr__(cls, ad):
            return _Sahte

    class _Sahte(metaclass=_SahteMeta):
        def __init__(self, *a, **k):
            pass

        def __call__(self, *a, **k):
            return _Sahte()

        def __getattr__(self, ad):
            return _Sahte()

    def _modul(ad):
        m = types.ModuleType(ad)
        m.__getattr__ = lambda _ad: _Sahte
        return m

    adlar = ["PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtNetwork", "PyQt6.QtWidgets"]
    eski = {a: sys.modules.get(a) for a in adlar + ["yoklama"]}
    sys.modules.update({a: _modul(a) for a in adlar})
    try:
        import yoklama
        return yoklama
    finally:
        for a, m in eski.items():
            if m is None:
                sys.modules.pop(a, None)
            else:
                sys.modules[a] = m


yoklama = _yoklama_yukle()


class _Yanit(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestDashboardIzinler(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ayar = Path(self._tmp.name) / "izin.json"
        self.ayar.write_text(json.dumps({"okul_url": "http://127.0.0.1:9090", "anahtar": "test"}))
        for yama in (mock.patch.object(tahta_api, "IZIN_AYAR_DOSYASI", self.ayar),
                     mock.patch.dict(tahta_api._izin_onbellek, clear=True),
                     mock.patch("zil.simdi_istanbul", return_value=datetime(
                         2026, 11, 23, 8, 0, tzinfo=ZoneInfo("Europe/Istanbul")))):
            yama.start()
            self.addCleanup(yama.stop)
        self.istekler = []

    def _acici(self, yanitlar=None, hata=None):
        def ac(istek, timeout):
            self.istekler.append((istek, timeout))
            if hata:
                raise hata
            tarih = istek.full_url.rsplit("tarih=", 1)[1]
            return _Yanit(json.dumps({"tarih": tarih, "siniflar": yanitlar.get(tarih, {})}).encode())
        return mock.patch("urllib.request.build_opener",
                          return_value=types.SimpleNamespace(open=ac))

    def test_yalniz_ilgili_sinif_bugun_ve_yarin(self):
        yanitlar = {"2026-11-23": {"9-A": ["12", "7"], "9-B": ["99"]},
                    "2026-11-24": {"9-A": ["12"]}}
        with self._acici(yanitlar):
            izin = tahta_api._sinif_izinleri("9-A")
        self.assertEqual(izin, {"2026-11-23": ["12", "7"], "2026-11-24": ["12"]})
        istek, zaman_asimi = self.istekler[0]
        self.assertEqual(istek.get_header("X-izin-anahtar"), "test")
        self.assertEqual(zaman_asimi, 3)

    def test_okul_ulasilamaz_bos(self):
        with self._acici(hata=urllib.error.URLError("kapali")):
            self.assertEqual(tahta_api._sinif_izinleri("9-A"), {})

    def test_bozuk_yanit_bos(self):
        def ac(istek, timeout):
            return _Yanit(b"<html>")
        with mock.patch("urllib.request.build_opener",
                        return_value=types.SimpleNamespace(open=ac)):
            self.assertEqual(tahta_api._sinif_izinleri("9-A"), {})

    def test_ayar_yoksa_istek_yok(self):
        self.ayar.unlink()
        with self._acici({}):
            self.assertEqual(tahta_api._sinif_izinleri("9-A"), {})
        self.assertEqual(self.istekler, [])

    def test_sinifsiz_tahta_bos(self):
        with self._acici({"2026-11-23": {"9-A": ["1"]}}):
            self.assertEqual(tahta_api._sinif_izinleri(None), {})
        self.assertEqual(self.istekler, [])

    def test_onbellek_60_sn(self):
        with self._acici({"2026-11-23": {"9-A": ["1"]}}):
            tahta_api._sinif_izinleri("9-A")
            tahta_api._sinif_izinleri("9-A")
        self.assertEqual(len(self.istekler), 2)  # bugün + yarın, ikinci çağrı önbellekten


class TestIstemciIzinler(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name) / "data"
        self.data.mkdir()
        for ad, deger in (("DATA_DIR", self.data), ("ROSTER_DIR", self.data / "roster"),
                          ("YEDEK_DIR", self.data / ".istemci_yedek")):
            yama = mock.patch.object(ti, ad, deger)
            yama.start()
            self.addCleanup(yama.stop)
        self.dosya = self.data / "izinler.json"

    def test_gecerli_izinler_yazilir(self):
        ti.yapilandirmayi_uygula({"izinler": {"2026-11-23": ["12"]}})
        self.assertEqual(json.loads(self.dosya.read_text()), {"2026-11-23": ["12"]})
        ti.yapilandirmayi_uygula({"izinler": {}})
        self.assertEqual(json.loads(self.dosya.read_text()), {})

    def test_anahtar_yoksa_dokunulmaz(self):
        self.dosya.write_text('{"2026-11-23": ["5"]}')
        ti.yapilandirmayi_uygula({})
        self.assertEqual(self.dosya.read_text(), '{"2026-11-23": ["5"]}')

    def test_gecersiz_yazilmaz(self):
        for bozuk in ([], "x", {"23.11.2026": ["1"]}, {"2026-11-23": "1"},
                      {"2026-11-23": [1]}, {"2026-11-23": [""]}):
            ti.yapilandirmayi_uygula({"izinler": bozuk})
        self.assertFalse(self.dosya.exists())


class TestYoklamaBaslangic(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dosya = Path(self._tmp.name) / "izinler.json"
        yama = mock.patch.object(yoklama, "IZIN_DOSYASI", self.dosya)
        yama.start()
        self.addCleanup(yama.stop)

    def test_izinli_numaralar(self):
        self.dosya.write_text('{"2026-11-23": ["12", 7], "2026-11-24": ["3"]}')
        self.assertEqual(yoklama._izinli_numaralar("2026-11-23"), {"12"})
        self.assertEqual(yoklama._izinli_numaralar("2026-11-25"), set())

    def test_yok_ya_da_bozuk_dosya_yok_sayilir(self):
        self.assertEqual(yoklama._izinli_numaralar("2026-11-23"), set())
        for bozuk in ("{bozuk", "[1, 2]", '{"2026-11-23": 5}'):
            self.dosya.write_text(bozuk)
            self.assertEqual(yoklama._izinli_numaralar("2026-11-23"), set())

    def test_baslangic_durumu_onceligi(self):
        izinli = {"12"}
        self.assertEqual(yoklama._baslangic_durumu("12", {}, izinli), "izinli")
        self.assertEqual(yoklama._baslangic_durumu("12", {"12": "var"}, izinli), "var")
        self.assertEqual(yoklama._baslangic_durumu("12", {"12": "yok"}, izinli), "yok")
        self.assertEqual(yoklama._baslangic_durumu("5", {}, izinli), "var")


if __name__ == "__main__":
    unittest.main()
