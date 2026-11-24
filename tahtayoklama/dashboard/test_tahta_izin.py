"""Onaylı veli izinleri: dashboard yapılandırması → tahta_istemci izinler.json →
yoklama.py başlangıç durumu. Ağ yok (urllib açıcısı mock'lanır); yoklama.py
PyQt6 yoksa sahte modülle içe aktarılır (yalnız saf fonksiyonlar test edilir)."""

import asyncio
import hashlib
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

from fastapi.requests import Request

import tahta_api
import yoklayici

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
        # Yönetim onayı kayıtlı durumu ezer (2026-11-24, yoklama.py).
        self.assertEqual(yoklama._baslangic_durumu("12", {"12": "var"}, izinli), "izinli")
        self.assertEqual(yoklama._baslangic_durumu("12", {"12": "yok"}, izinli), "izinli")
        self.assertEqual(yoklama._baslangic_durumu("5", {"5": "yok"}, izinli), "yok")
        self.assertEqual(yoklama._baslangic_durumu("5", {}, izinli), "var")


class TestYoklamayaIzinIsleme(unittest.TestCase):
    """Onaylı izin kayda işlenir: kayit_al (gelen kayıt) ve izinleri_uygula
    (sonradan gelen onay). Okula istek yok: _okul_izinleri patch'lenir."""
    TARIH = "2026-11-24"

    def setUp(self):
        import db
        self.db = db
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.token_dosyasi = tmp / "tokenlar.json"
        self.token_dosyasi.write_text(json.dumps({"9-A": hashlib.sha256(b"tkn").hexdigest()}))
        for yama in (mock.patch.object(db, "DB_YOLU", tmp / "test.db"),
                     mock.patch.object(tahta_api, "TOKEN_DOSYASI", self.token_dosyasi),
                     mock.patch.object(tahta_api, "IZIN_AYAR_DOSYASI", tmp / "izin_yok.json"),
                     mock.patch("zil.simdi_istanbul", return_value=datetime(
                         2026, 11, 24, 9, 0, tzinfo=ZoneInfo("Europe/Istanbul")))):
            yama.start()
            self.addCleanup(yama.stop)
        db.semayi_kur()
        conn = db.baglanti()
        conn.execute("INSERT INTO siniflar (id, ad) VALUES (1, '9-A')")
        conn.execute("INSERT INTO ogrenciler (sinif_id, no, ad_soyad) VALUES "
                     "(1, 1, 'Ali Deneme'), (1, 2, 'Ayse Deneme'), (1, 3, 'Can Deneme')")
        conn.execute("INSERT INTO tahtalar (ad, ip, ssh_kullanici, sinif_id, aktif) VALUES "
                     "('9-A', '10.0.0.1', 'ogretmen', 1, 1)")
        conn.commit()
        conn.close()

    def _kayit(self, **kw):
        k = {"sinif": "9-A", "tarih": self.TARIH, "ders_no": 1,
             "kaydedilme_saati": "08:17:00", "durumlar": {"1": "yok", "2": "yok", "3": "var"}}
        k.update(kw)
        return k

    def _istek(self, govde):
        ham = json.dumps(govde).encode()

        async def receive():
            return {"type": "http.request", "body": ham, "more_body": False}

        return Request({"type": "http", "method": "POST", "path": "/x", "query_string": b"",
                        "headers": [(b"authorization", b"Bearer tkn")],
                        "client": ("192.168.23.245", 5000)}, receive)

    def _it(self, kayit, izinler):
        with mock.patch.object(tahta_api, "_okul_izinleri", return_value=izinler) as okul, \
                mock.patch("devamsizlik_bildirim.bildir") as bildir:
            asyncio.run(tahta_api.kayit_al(self._istek(kayit)))
        okul.assert_called_once_with(self.TARIH)
        return bildir

    def _satir(self, tablo="yoklama_onbellek", ders_no=1):
        conn = self.db.baglanti()
        try:
            return conn.execute(f"SELECT * FROM {tablo} WHERE tarih = ? AND ders_no = ?",
                                (self.TARIH, ders_no)).fetchone()
        finally:
            conn.close()

    def _uygula(self, izinler):
        conn = self.db.baglanti()
        try:
            return yoklayici.izinleri_uygula(conn, self.TARIH, izinler)
        finally:
            conn.close()

    def test_kayit_al_izinli_no_yok_gelse_de_izinli_ve_bildirilmez(self):
        bildir = self._it(self._kayit(durumlar={"1": "yok", "2": "yok", "3": "var"}),
                          {"9-A": ["1", "3"], "9-B": ["2"]})
        s = self._satir()
        self.assertEqual(json.loads(s["yok_nolari"]), [2])
        self.assertEqual(json.loads(s["yok_isimleri"]), ["Ayse Deneme"])
        self.assertEqual(json.loads(s["izinli_nolari"]), [1, 3])
        self.assertEqual(json.loads(s["izinli_isimleri"]), ["Ali Deneme", "Can Deneme"])
        bildir.assert_called_once_with([2])

    def test_kayit_al_okul_kapali_degismez(self):
        bildir = self._it(self._kayit(), {})
        s = self._satir()
        self.assertEqual(json.loads(s["yok_nolari"]), [1, 2])
        self.assertEqual(json.loads(s["izinli_nolari"]), [])
        bildir.assert_called_once_with([1, 2])

    def test_kulup_kaydina_uygulanmaz(self):
        kulup = {"kod": "KULUP-DENEME"}
        with mock.patch("kulupler.bul", return_value=kulup), \
                mock.patch("kulupler.isimler", return_value={"1": "Ali Deneme"}):
            conn = self.db.baglanti()
            try:
                yoklayici.itilen_kaydi_yaz(conn, self._kayit(
                    sinif="KULUP-DENEME", ders_no=7, durumlar={"1": "yok"}), "9-A", {"1"})
            finally:
                conn.close()
        s = self._satir("kulup_yoklama", 7)
        self.assertEqual(json.loads(s["yok_nolari"]), [1])
        self.assertEqual(json.loads(s["izinli_nolari"]), [])

    def test_sonra_gelen_onay_satiri_duzeltir_saat_korunur(self):
        self._it(self._kayit(), {})
        self._it(self._kayit(ders_no=2, kaydedilme_saati="09:05:00",
                             durumlar={"1": "var", "2": "yok"}), {})
        self.assertEqual(self._uygula({"9-A": ["1", "3"]}), 1)  # ders 2'de 1 zaten var
        s = self._satir()
        self.assertEqual(s["kaydedilme_saati"], "08:17:00")
        self.assertEqual(s["durum"], "alindi")
        self.assertEqual(json.loads(s["yok_nolari"]), [2])
        self.assertEqual(json.loads(s["yok_isimleri"]), ["Ayse Deneme"])
        self.assertEqual(json.loads(s["izinli_nolari"]), [1])
        self.assertEqual(json.loads(s["izinli_isimleri"]), ["Ali Deneme"])
        self.assertEqual(json.loads(self._satir(ders_no=2)["yok_nolari"]), [2])
        self.assertEqual(self._uygula({"9-A": ["1", "3"]}), 0)  # ikinci tur: değişen yok

    def test_okul_kapaliyken_ve_null_kolonlarda_degismez(self):
        self._it(self._kayit(), {})
        once = dict(self._satir())
        self.assertEqual(self._uygula({}), 0)
        self.assertEqual(dict(self._satir()), once)
        conn = self.db.baglanti()  # eski satır: no kolonları NULL
        conn.execute("UPDATE yoklama_onbellek SET yok_nolari = NULL, izinli_nolari = NULL")
        conn.commit()
        conn.close()
        self.assertEqual(self._uygula({"9-A": ["1"]}), 0)

    def test_null_izinli_nolari_ile_tasir(self):
        self._it(self._kayit(), {})
        conn = self.db.baglanti()
        conn.execute("UPDATE yoklama_onbellek SET izinli_nolari = NULL, izinli_isimleri = NULL")
        conn.commit()
        conn.close()
        self.assertEqual(self._uygula({"9-A": ["2"]}), 1)
        s = self._satir()
        self.assertEqual(json.loads(s["izinli_nolari"]), [2])
        self.assertEqual(json.loads(s["izinli_isimleri"]), ["Ayse Deneme"])
        self.assertEqual(json.loads(s["yok_nolari"]), [1])

    def test_polling_yardimcisi_hata_yutar(self):
        import app
        with mock.patch.object(tahta_api, "_okul_izinleri", side_effect=RuntimeError("x")):
            asyncio.run(app._izinleri_uygula(self.TARIH))  # istisna fırlatmaz
        self._it(self._kayit(), {})
        with mock.patch.object(tahta_api, "_okul_izinleri", return_value={"9-A": ["1"]}):
            asyncio.run(app._izinleri_uygula(self.TARIH))
        self.assertEqual(json.loads(self._satir()["izinli_nolari"]), [1])


if __name__ == "__main__":
    unittest.main()
