"""bilesen.css: ortak bileşen sınıfları tanımlı mı, ham renk yok mu."""
import re
import unittest
from pathlib import Path

CSS = (Path(__file__).parent / "static" / "bilesen.css").read_text(encoding="utf-8")

SECICILER = [
    ".dugme", ".dugme-birincil", ".dugme-ikincil", ".dugme-tehlike", ".dugme-kucuk", ".dugme-ikon",
    ".rozet", ".rozet-yesil", ".rozet-amber", ".rozet-kirmizi", ".rozet-gri", ".rozet-mavi",
    "a.cip", ".cip.secili", ".cip-satir", ".ara-kutu",
    ".tablo-kutu", "table.tablo", ".tablo th", ".tablo td", "tr.pasif",
    ".serit", ".serit-uyari", ".serit-kritik", ".serit-bilgi",
    ".baslik-eylem", ".durum-yazi",
    ".ayrinti-duzen", ".ayrinti-panel", ".form-alan", ".eksik",
    ".bos-durum", ".form-hata",
]


class TestBilesen(unittest.TestCase):
    def test_bilesen_siniflari_tanimli(self):
        eksik = [s for s in SECICILER if s not in CSS]
        self.assertEqual(eksik, [])

    def test_ham_renk_yok(self):
        govde = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
        self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,6}\b", govde))
        self.assertNotIn("rgb(", govde)
        self.assertNotIn("rgba(", govde)

    def test_azaltilmis_hareket_son_blok(self):
        self.assertTrue(CSS.rstrip().endswith("}"))
        self.assertGreater(CSS.rfind("prefers-reduced-motion"), CSS.rfind("@media print"))


if __name__ == "__main__":
    unittest.main()
