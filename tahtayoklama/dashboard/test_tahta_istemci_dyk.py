"""tahta_istemci.py DYK kursu yapılandırması — geçici dizinle, ağ yok."""

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tahta_istemci as ti

PROGRAM = {"oturumlar": [{"gun": "pazartesi", "bas": "16:00", "bit": "17:30",
                          "kod": "DYK-11-COGRAFYA", "ders_no": 1}]}


def roster(kod: str) -> str:
    return json.dumps({"sinif": kod, "ad": "Deneme", "ogrenciler": [{"no": 1, "ad_soyad": "Ali Veli"}]})


class DykTestTabani(unittest.TestCase):
    def setUp(self):
        self._gecici = TemporaryDirectory()
        self.addCleanup(self._gecici.cleanup)
        kok = Path(self._gecici.name)
        self.data = kok / "data"
        self.roster_dir = self.data / "roster"
        self.roster_dir.mkdir(parents=True)
        self.yedek = self.data / ".istemci_yedek"
        for ad, deger in (("DATA_DIR", self.data), ("ROSTER_DIR", self.roster_dir),
                          ("YEDEK_DIR", self.yedek)):
            yama = mock.patch.object(ti, ad, deger)
            yama.start()
            self.addCleanup(yama.stop)

    def yedek_adlari(self) -> list[str]:
        return sorted(p.name.split("_", 1)[1] for p in self.yedek.glob("*")) if self.yedek.exists() else []


class TestDykRoster(DykTestTabani):
    def test_dyk_roster_yazilir(self):
        ti.yapilandirmayi_uygula({"dyk": {"DYK-11-COGRAFYA": roster("DYK-11-COGRAFYA")}})
        self.assertEqual((self.roster_dir / "DYK-11-COGRAFYA.json").read_text(),
                         roster("DYK-11-COGRAFYA"))

    def test_gecersiz_dyk_roster_yazilmaz(self):
        ti.yapilandirmayi_uygula({"dyk": {
            "DYK-A": roster("DYK-B"),                                   # kod uyuşmuyor
            "DYK-C": json.dumps({"sinif": "DYK-C", "ogrenciler": []}),  # boş liste
            "DYK-D": "bozuk",
            "KULUP-X": roster("KULUP-X"),                               # önek DYK değil
            "DYK-../x": roster("DYK-../x"),                             # _SINIF_RE dışı
            "DYK-E": 5,
        }})
        self.assertEqual(list(self.roster_dir.glob("*")), [])

    def test_degisen_roster_yedeklenir(self):
        (self.roster_dir / "DYK-11-COGRAFYA.json").write_text(roster("DYK-11-COGRAFYA"))
        yeni = json.dumps({"sinif": "DYK-11-COGRAFYA", "ogrenciler": [{"no": 2, "ad_soyad": "Veli Ali"}]})
        ti.yapilandirmayi_uygula({"dyk": {"DYK-11-COGRAFYA": yeni}})
        self.assertEqual((self.roster_dir / "DYK-11-COGRAFYA.json").read_text(), yeni)
        self.assertEqual(self.yedek_adlari(), ["DYK-11-COGRAFYA.json"])

    def test_artik_olmayan_dyk_yedege_tasinir_digerlerine_dokunulmaz(self):
        for ad in ("DYK-ESKI", "KULUP-AY", "9-A"):
            (self.roster_dir / f"{ad}.json").write_text(roster(ad))
        ti.yapilandirmayi_uygula({"dyk": {}})
        self.assertFalse((self.roster_dir / "DYK-ESKI.json").exists())
        self.assertEqual(self.yedek_adlari(), ["DYK-ESKI.json"])
        self.assertTrue((self.roster_dir / "KULUP-AY.json").exists())
        self.assertTrue((self.roster_dir / "9-A.json").exists())

    def test_dyk_anahtari_yoksa_dokunulmaz(self):
        (self.roster_dir / "DYK-ESKI.json").write_text(roster("DYK-ESKI"))
        (self.data / "dyk_program.json").write_text(json.dumps(PROGRAM))
        ti.yapilandirmayi_uygula({"zil": None})
        self.assertTrue((self.roster_dir / "DYK-ESKI.json").exists())
        self.assertTrue((self.data / "dyk_program.json").exists())
        self.assertFalse(self.yedek.exists())

    def test_dyk_dict_degilse_dokunulmaz(self):
        (self.roster_dir / "DYK-ESKI.json").write_text(roster("DYK-ESKI"))
        ti.yapilandirmayi_uygula({"dyk": None})
        ti.yapilandirmayi_uygula({"dyk": "x"})
        self.assertTrue((self.roster_dir / "DYK-ESKI.json").exists())

    def test_sinif_roster_temizligi_dyk_silmez(self):
        (self.roster_dir / "DYK-11-COGRAFYA.json").write_text(roster("DYK-11-COGRAFYA"))
        (self.roster_dir / "10-A.json").write_text(roster("10-A"))
        ti.yapilandirmayi_uygula({"sinif": "9-A", "roster": roster("9-A")})
        self.assertTrue((self.roster_dir / "DYK-11-COGRAFYA.json").exists())
        self.assertTrue((self.roster_dir / "9-A.json").exists())
        self.assertFalse((self.roster_dir / "10-A.json").exists())


class TestDykProgram(DykTestTabani):
    def test_gecerli_program_yazilir(self):
        ti.yapilandirmayi_uygula({"dyk_program": json.dumps(PROGRAM)})
        self.assertEqual(json.loads((self.data / "dyk_program.json").read_text()), PROGRAM)

    def test_degisen_program_yedeklenir(self):
        (self.data / "dyk_program.json").write_text(json.dumps({"oturumlar": []}))
        ti.yapilandirmayi_uygula({"dyk_program": json.dumps(PROGRAM)})
        self.assertEqual(json.loads((self.data / "dyk_program.json").read_text()), PROGRAM)
        self.assertEqual(self.yedek_adlari(), ["dyk_program.json"])

    def test_gecersiz_program_yazilmaz_mevcut_korunur(self):
        eski = json.dumps(PROGRAM)
        (self.data / "dyk_program.json").write_text(eski)
        for bozuk in ("bozuk", "[]", "{}", json.dumps({"oturumlar": {}}), 5, ["a"], {"oturumlar": []}):
            ti.yapilandirmayi_uygula({"dyk_program": bozuk})
        self.assertEqual((self.data / "dyk_program.json").read_text(), eski)
        self.assertFalse(self.yedek.exists())

    def test_gecersiz_program_dosya_olusturmaz(self):
        ti.yapilandirmayi_uygula({"dyk_program": "bozuk"})
        self.assertFalse((self.data / "dyk_program.json").exists())

    def test_null_mevcut_dosyayi_yedege_tasir(self):
        (self.data / "dyk_program.json").write_text(json.dumps(PROGRAM))
        ti.yapilandirmayi_uygula({"dyk_program": None})
        self.assertFalse((self.data / "dyk_program.json").exists())
        self.assertEqual(self.yedek_adlari(), ["dyk_program.json"])

    def test_null_dosya_yoksa_sessiz(self):
        ti.yapilandirmayi_uygula({"dyk_program": None})
        self.assertFalse(self.yedek.exists())

    def test_gecerli_dogrulayici(self):
        self.assertTrue(ti.dyk_program_gecerli(json.dumps(PROGRAM)))
        self.assertFalse(ti.dyk_program_gecerli("[]"))
        self.assertFalse(ti.dyk_program_gecerli("null"))
        self.assertFalse(ti.dyk_program_gecerli(json.dumps({"oturumlar": "x"})))


if __name__ == "__main__":
    unittest.main()
