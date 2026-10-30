"""Tema belirteçleri, tema listesi ve yazı tipi dosyaları (static/tema.css, tema.js, menu.TEMALAR)."""
import re
import unittest
from pathlib import Path

import menu

STATIK = Path(__file__).resolve().parent / "static"


def _oku(ad: str) -> str:
    return (STATIK / ad).read_text(encoding="utf-8")


def _bloklar(css: str) -> dict:
    """{'': :root içeriği, 'argon': data-tema=argon içeriği, ...}"""
    sonuc = {}
    for m in re.finditer(r':root(?:\[data-tema="([^"]+)"\])?\s*\{([^}]*)\}', css):
        sonuc[m.group(1) or ""] = m.group(2)
    return sonuc


def _adlar(govde: str) -> set:
    return set(re.findall(r"(--[a-z0-9-]+)\s*:", govde))


class TestTema(unittest.TestCase):
    def test_her_tema_tum_tokenlari_tanimlar(self):
        bloklar = _bloklar(_oku("tema.css"))
        kok = _adlar(bloklar[""])
        self.assertEqual(len(bloklar) - 1, 8)
        for tema, govde in bloklar.items():
            if tema:
                self.assertEqual(sorted(kok - _adlar(govde)), [], tema)

    def test_tema_listesi_ve_varsayilan(self):
        css_temalar = set(_bloklar(_oku("tema.css"))) - {""}
        self.assertEqual({a for a, _ in menu.TEMALAR}, css_temalar | {"sade-koyu"})
        self.assertEqual(next(a for a, _ in menu.TEMALAR), "sade-koyu")
        self.assertEqual(len(menu.TEMALAR), 9)
        js = _oku("tema.js")
        self.assertRegex(js, r'VARSAYILAN\s*=\s*"sade-koyu"')
        self.assertRegex(js, r'klasik:\s*"argon"')
        self.assertRegex(js, r'yumusak:\s*"argon"')
        self.assertIn("FARABI_TEMALAR", js)
        self.assertNotIn("prefers-color-scheme", js)

    def test_font_dosyalari_var(self):
        urller = re.findall(r"url\(/static/fontlar/([^)]+)\)", _oku("tema.css"))
        self.assertGreaterEqual(len(urller), 12)
        for ad in urller:
            self.assertTrue((STATIK / "fontlar" / ad).is_file(), ad)

    def test_buyuk_harf_yok(self):
        for ad in ("tema.css", "bilesen.css"):
            if not (STATIK / ad).exists():  # bilesen.css Task 4'te gelir
                continue
            self.assertNotRegex(_oku(ad), r"text-transform\s*:\s*uppercase", ad)


if __name__ == "__main__":
    unittest.main()
