import json
import tempfile
import unittest
from pathlib import Path

import program_esitligi


def _yaz(d, ad, siniflar):
    p = Path(d) / ad
    p.write_text(json.dumps({"siniflar": siniflar}), encoding="utf-8")
    return p


class TestProgramFarki(unittest.TestCase):
    def test_esit_kopyalar_fark_yok(self):
        with tempfile.TemporaryDirectory() as d:
            s = {"9-A": {"pazartesi": {"1": "matematik", "2": "fizik"}}}
            r = program_esitligi.program_farki(_yaz(d, "a.json", s), _yaz(d, "b.json", s))
        self.assertEqual(r, {"toplam": 0, "fark": []})

    def test_hucre_farki_eksik_sinif_ve_eksik_saat(self):
        with tempfile.TemporaryDirectory() as d:
            a = {"12-A": {"pazartesi": {"5": "sınav hazırlık çalışması", "6": "fizik"}}, "9-A": {"sali": {"1": "kimya"}}}
            b = {"12-A": {"pazartesi": {"5": "hedef fizik"}}}
            r = program_esitligi.program_farki(_yaz(d, "a.json", a), _yaz(d, "b.json", b))
        self.assertEqual(r["toplam"], 3)
        self.assertEqual(r["fark"][0], {"sinif": "12-A", "gun": "Pazartesi", "saat": "5", "mudur": "sınav hazırlık çalışması", "pano": "hedef fizik"})
        self.assertIn({"sinif": "12-A", "gun": "Pazartesi", "saat": "6", "mudur": "fizik", "pano": None}, r["fark"])
        self.assertIn({"sinif": "9-A", "gun": "Salı", "saat": "1", "mudur": "kimya", "pano": None}, r["fark"])

    def test_fazla_fark_kirpilir_ama_toplam_dogru(self):
        with tempfile.TemporaryDirectory() as d:
            a = {"9-A": {"cuma": {str(i): "x" for i in range(1, 9)}, "sali": {str(i): "x" for i in range(1, 9)}}}
            r = program_esitligi.program_farki(_yaz(d, "a.json", a), _yaz(d, "b.json", {}))
        self.assertEqual((r["toplam"], len(r["fark"])), (16, program_esitligi.AZAMI_GOSTER))

    def test_dosya_yok_ya_da_bozuksa_hata_doner_cokmez(self):
        with tempfile.TemporaryDirectory() as d:
            ok = _yaz(d, "a.json", {})
            bozuk = Path(d) / "bozuk.json"
            bozuk.write_text("{bozuk", encoding="utf-8")
            self.assertIn("hata", program_esitligi.program_farki(ok, Path(d) / "yok.json"))
            self.assertIn("hata", program_esitligi.program_farki(ok, bozuk))


if __name__ == "__main__":
    unittest.main()
