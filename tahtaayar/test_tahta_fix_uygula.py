"""reboot_sudoers düzeltmesi için testler (yalnızca stdlib; ssh/sudo YOK)."""
import subprocess
import unittest
from pathlib import Path

import tahta_fix_uygula as t

_YENIDEN_BASLAT = Path(__file__).resolve().parent.parent / "tahtayoklama" / "dashboard" / "tahta_yeniden_baslat.py"


def _fix():
    return [d for d in t.DUZELTMELER if d.ad == "reboot_sudoers"]


class RebootSudoersTest(unittest.TestCase):
    def test_bir_kez_ve_son_eleman(self):
        self.assertEqual(len(_fix()), 1)
        f = _fix()[0]
        self.assertIs(t.DUZELTMELER[-1], f)
        self.assertTrue(f.root_gerekli)
        self.assertEqual(f.beklenen, b"var")

    def test_komut_icerigi(self):
        f = _fix()[0]
        self.assertIn(t._REBOOT_SUDOERS_SATIR, f.kontrol_komutu)
        self.assertIn(t._REBOOT_SUDOERS_SATIR, f.uygula_komutu)
        self.assertIn(t._REBOOT_SUDOERS_DOSYA, f.kontrol_komutu)
        self.assertIn("visudo -cf", f.uygula_komutu)
        self.assertIn("install -m 0440", f.uygula_komutu)
        self.assertLess(f.uygula_komutu.index("visudo -cf"), f.uygula_komutu.index("install -m 0440"))
        self.assertTrue(f.uygula_komutu.startswith("test -x /usr/bin/systemctl && "))

    def test_tirnak_guvenligi(self):
        f = _fix()[0]
        for komut in (f.kontrol_komutu, f.uygula_komutu):
            if repr(komut).startswith('"'):
                self.assertNotIn("$", komut)
                self.assertNotIn("`", komut)
            self.assertFalse("'" in komut and '"' in komut)

    def test_kontrol_komutu_yerelde_yok_der(self):
        f = _fix()[0]
        if Path(t._REBOOT_SUDOERS_DOSYA).exists():
            self.skipTest("bu makinede sudoers dosyası var")
        r = subprocess.run(
            ["bash", "-c", f"bash -c {f.kontrol_komutu!r}"], capture_output=True, check=False
        )
        self.assertEqual(r.stdout.strip(), b"yok")

    def test_dashboard_komutuyla_birebir(self):
        metin = _YENIDEN_BASLAT.read_text(encoding="utf-8")
        self.assertIn("sudo -n /usr/bin/systemctl reboot", metin)
        self.assertTrue(t._REBOOT_SUDOERS_SATIR.endswith("/usr/bin/systemctl reboot"))


if __name__ == "__main__":
    unittest.main()
