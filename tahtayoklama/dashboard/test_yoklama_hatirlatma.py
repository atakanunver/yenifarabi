"""tahta_istemci.yoklama_hatirlat — 35. dakika sesli hatırlatma (geçici dizin, ses yok)."""

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tahta_istemci as ti

ZIL = {"dersler": [{"no": 1, "baslangic": "08:10", "bitis": "08:50"},
                   {"no": 2, "baslangic": "09:00", "bitis": "09:40"}]}
PROGRAM = {"siniflar": {"9-A": {"pazartesi": {"1": "matematik", "2": ""}}}}
DYK = {"oturumlar": [{"gun": "pazartesi", "bas": "16:00", "bit": "17:30",
                      "kod": "DYK-11-COGRAFYA", "ders_no": 1}]}
PZT = datetime(2026, 11, 23)  # pazartesi
TARIH = "2026-11-23"


def an(saat: str) -> datetime:
    return PZT.replace(hour=int(saat[:2]), minute=int(saat[3:]))


class TestYoklamaHatirlat(unittest.TestCase):
    def setUp(self):
        g = TemporaryDirectory()
        self.addCleanup(g.cleanup)
        kok = Path(g.name)
        self.data = kok / "data"
        self.roster = self.data / "roster"
        self.kayit = self.data / "kayitlar"
        self.roster.mkdir(parents=True)
        self.kayit.mkdir()
        self.ses = kok / "assets" / "ogretmenimyoklama.mp3"
        for ad, deger in (("DATA_DIR", self.data), ("ROSTER_DIR", self.roster),
                          ("KAYIT_DIR", self.kayit), ("HATIRLATMA_SESI", self.ses)):
            y = mock.patch.object(ti, ad, deger)
            y.start()
            self.addCleanup(y.stop)
        y = mock.patch.object(ti, "_hatirlatilanlar", set())
        y.start()
        self.addCleanup(y.stop)
        self.cal = mock.patch.object(ti, "hatirlatma_sesi_cal", return_value=True).start()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(ti, "log").start()
        self._yaz("zil.json", ZIL)
        self._yaz("ders_programi.json", PROGRAM)
        self._yaz("roster/9-A.json", {"sinif": "9-A", "ogrenciler": []})

    def _yaz(self, ad, veri):
        (self.data / ad).write_text(json.dumps(veri), encoding="utf-8")

    def _kayit(self, kod, no):
        (self.kayit / f"{TARIH}_{kod}_ders{no}.json").write_text("{}", encoding="utf-8")

    def test_34_dk_calmaz_35_dk_calar(self):
        self.assertEqual(ti.yoklama_hatirlat(an("08:44")), [])
        self.assertEqual(ti.yoklama_hatirlat(an("08:45")), [(TARIH, "ders", 1)])
        self.cal.assert_called_once()

    def test_sinif_kaydi_varsa_calmaz(self):
        self._kayit("9-A", 1)
        self.assertEqual(ti.yoklama_hatirlat(an("08:45")), [])
        self.cal.assert_not_called()

    def test_kulup_kaydi_varsa_calmaz(self):
        self._kayit("KULUP-SATRANC", 1)
        self.assertEqual(ti.yoklama_hatirlat(an("08:46")), [])

    def test_programda_ders_yoksa_calmaz(self):
        self.assertEqual(ti.yoklama_hatirlat(an("09:35")), [])  # 2. ders boş
        self.assertEqual(ti.yoklama_hatirlat(PZT.replace(day=24, hour=8, minute=45)), [])  # salı yok

    def test_sinifsiz_tahtada_normal_ders_calmaz(self):
        (self.roster / "9-A.json").unlink()
        self._yaz("roster/KULUP-SATRANC.json", {"sinif": "KULUP-SATRANC"})
        self.assertEqual(ti.yoklama_hatirlat(an("08:45")), [])

    def test_ayni_ders_ikinci_kez_calmaz(self):
        ti.yoklama_hatirlat(an("08:45"))
        self.assertEqual(ti.yoklama_hatirlat(an("08:47")), [])
        self.cal.assert_called_once()

    def test_ders_bitince_calmaz(self):
        self.assertEqual(ti.yoklama_hatirlat(an("08:50")), [])

    def test_dyk_35_dk_calar_kayit_varsa_calmaz(self):
        (self.roster / "9-A.json").unlink()  # sınıfsız tahta: yalnız DYK
        self._yaz("dyk_program.json", DYK)
        self.assertEqual(ti.yoklama_hatirlat(an("16:34")), [])
        self.assertEqual(ti.yoklama_hatirlat(an("16:35")), [(TARIH, "DYK-11-COGRAFYA", 1)])
        ti._hatirlatilanlar.clear()
        self._kayit("DYK-11-COGRAFYA", 1)
        self.assertEqual(ti.yoklama_hatirlat(an("16:40")), [])

    def test_bozuk_dosyalar_istisna_vermez(self):
        (self.data / "zil.json").write_text("{bozuk", encoding="utf-8")
        self._yaz("dyk_program.json", {"oturumlar": [None, {"gun": "pazartesi", "bas": "x"}]})
        self.assertEqual(ti.yoklama_hatirlat(an("08:45")), [])


class TestSesCal(unittest.TestCase):
    def test_ses_dosyasi_yoksa_false(self):
        with mock.patch.object(ti, "HATIRLATMA_SESI", Path("/yok/x.mp3")), mock.patch.object(ti, "log"):
            self.assertFalse(ti.hatirlatma_sesi_cal())

    def test_calar_yoksa_false(self):
        with TemporaryDirectory() as d:
            ses = Path(d) / "x.mp3"
            ses.write_bytes(b"")
            with mock.patch.object(ti, "HATIRLATMA_SESI", ses), mock.patch.object(ti, "log"), \
                    mock.patch.object(ti.shutil, "which", return_value=None):
                self.assertFalse(ti.hatirlatma_sesi_cal())

    def test_ilk_bulunan_calar_arka_planda(self):
        with TemporaryDirectory() as d:
            ses = Path(d) / "x.mp3"
            ses.write_bytes(b"")
            with mock.patch.object(ti, "HATIRLATMA_SESI", ses), \
                    mock.patch.object(ti.shutil, "which", side_effect=lambda k: k == "cvlc"), \
                    mock.patch.object(ti.subprocess, "Popen") as p:
                self.assertTrue(ti.hatirlatma_sesi_cal())
            self.assertEqual(p.call_args.args[0][0], "cvlc")


if __name__ == "__main__":
    unittest.main()
