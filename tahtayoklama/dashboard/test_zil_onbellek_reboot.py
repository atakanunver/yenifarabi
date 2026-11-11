"""Yayın sonrası zil/ders programı önbelleği tazelenir; zil okunamazsa reboot ders saati sayılır."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import okul_ana_goruntu as G
import okul_ana_yayin
import tahta_yeniden_baslat
import zil


class TestYayinOnbellek(unittest.TestCase):
    def test_dosya_yazilinca_onbellekler_temizlenir(self):
        with tempfile.TemporaryDirectory() as d,                 mock.patch.object(G, "veri_dizini", return_value=Path(d)),                 mock.patch.object(G, "DOSYALAR", {"zil.json": lambda: "{}"}),                 mock.patch("zil.yenile") as zy, mock.patch("ders_programi.yenile") as dy:
            okul_ana_yayin.yayin_json(True)
            zy.assert_called_once()
            dy.assert_called_once()
            zy.reset_mock()
            okul_ana_yayin.yayin_json(True)  # içerik aynı: yazma yok, temizleme yok
            zy.assert_not_called()

    def test_kuru_calismada_temizlenmez(self):
        with tempfile.TemporaryDirectory() as d,                 mock.patch.object(G, "veri_dizini", return_value=Path(d)),                 mock.patch.object(G, "DOSYALAR", {"zil.json": lambda: "{}"}),                 mock.patch("zil.yenile") as zy:
            okul_ana_yayin.yayin_json(False)
            zy.assert_not_called()


class TestDersSaatiZilYok(unittest.TestCase):
    def _bak(self, simdi):
        with mock.patch.object(zil, "ders_saatleri", return_value=[]):
            return tahta_yeniden_baslat.ders_saatinde_mi(simdi)

    def test_zil_bos_hafta_ici_gunduz_ders_sayilir(self):
        self.assertTrue(self._bak(datetime(2026, 11, 11, 10, 0)))  # çarşamba

    def test_zil_bos_aksam_ve_hafta_sonu_serbest(self):
        self.assertFalse(self._bak(datetime(2026, 11, 11, 17, 30)))
        self.assertFalse(self._bak(datetime(2026, 11, 14, 10, 0)))  # cumartesi


if __name__ == "__main__":
    unittest.main()
