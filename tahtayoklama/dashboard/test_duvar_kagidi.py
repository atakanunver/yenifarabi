import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import duvar_kagidi as dk

from ssh_istemci import SSHSonuc

TAHTA = {"ad": "9-A", "ip": "10.0.0.9", "kullanici": "ogretmen", "admin": None}
OK = SSHSonuc(True, b"", b"", cikis_kodu=0)
ORTAM = (":0", "/home/ogretmen/.Xauthority", "1000")


def kos(c):
    return asyncio.run(c)


class Taban(unittest.TestCase):
    def setUp(self):
        self.komutlar = []

        async def komut(ip, kul, k, **kw):
            self.komutlar.append(k)
            return OK

        self.scp = mock.AsyncMock(return_value=OK)
        self.ortam = mock.AsyncMock(return_value=ORTAM)
        for p in (
            mock.patch.object(dk.tahta_kaydi, "tahtalari_yukle", return_value=[TAHTA]),
            mock.patch.object(dk.ssh_istemci, "komut_calistir", side_effect=komut),
            mock.patch.object(dk.ssh_istemci, "scp_gonder", self.scp),
            mock.patch.object(dk.ssh_istemci, "x_ortamini_kesfet", self.ortam),
        ):
            p.start()
            self.addCleanup(p.stop)
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.png = Path(d.name) / "a.png"
        self.png.write_bytes(b"png")


class TestGonder(Taban):
    def test_ilk_yedek_ve_ayar(self):
        r = kos(dk.gonder("9-A", self.png))
        self.assertTrue(r["basarili"])
        self.assertIn("mkdir -p /home/ogretmen/.local/share/farabi", self.komutlar[0])
        self.assertEqual(self.scp.call_args.args[3], "/home/ogretmen/.local/share/farabi/hafta-birincileri.png")
        ic = self.komutlar[-1]
        self.assertIn("gsettings get org.cinnamon.desktop.background picture-uri >", ic)
        self.assertIn("onceki-arkaplan.txt", ic)
        self.assertIn("picture-options zoom", ic)
        self.assertIn("file:///home/ogretmen/.local/share/farabi/hafta-birincileri.png", ic)

    def test_yedek_varsa_yazilmaz_kosulu(self):
        kos(dk.gonder("9-A", self.png))
        # yedek yalnız dosya yokken yazılır: koşul "[ -f yedek ] || get > yedek"
        self.assertRegex(self.komutlar[-1].replace("\\", ""), r"\[ -f \S*onceki-arkaplan\.txt \] \|\| gsettings get")

    def test_bilinmeyen_tahta(self):
        r = kos(dk.gonder("yok", self.png))
        self.assertFalse(r["basarili"])
        r = kos(dk.gonder("a;rm -rf", self.png))
        self.assertFalse(r["basarili"])
        self.scp.assert_not_called()
        self.assertEqual(self.komutlar, [])

    def test_scp_hatasi(self):
        self.scp.return_value = SSHSonuc(False, b"", b"kapali", cikis_kodu=1)
        r = kos(dk.gonder("9-A", self.png))
        self.assertFalse(r["basarili"])
        self.assertEqual(len(self.komutlar), 1)  # yalnız mkdir

    def test_oturum_yok(self):
        self.ortam.return_value = None
        self.assertFalse(kos(dk.gonder("9-A", self.png))["basarili"])


class TestGeriAl(Taban):
    def test_geri_al(self):
        r = kos(dk.geri_al("9-A"))
        self.assertTrue(r["basarili"])
        self.assertIn("onceki-arkaplan.txt", self.komutlar[-1])
        self.assertIn("picture-uri", self.komutlar[-1])
        self.scp.assert_not_called()

    def test_geri_al_bilinmeyen(self):
        self.assertFalse(kos(dk.geri_al("yok"))["basarili"])


class TestCLI(Taban):
    def test_kuru_baglanti_acmaz(self):
        with mock.patch("builtins.print") as pr:
            kod = dk.main(["--hepsi", "--kuru", "--png", str(self.png)])
        self.assertEqual(kod, 0)
        self.assertTrue(any("9-A" in str(c) for c in pr.call_args_list))
        self.scp.assert_not_called()
        self.ortam.assert_not_called()
        self.assertEqual(self.komutlar, [])

    def test_hata_cikis_kodu(self):
        self.scp.return_value = SSHSonuc(False, b"", b"x", cikis_kodu=1)
        with mock.patch("builtins.print"):
            self.assertEqual(dk.main(["--tahta", "9-A", "--png", str(self.png)]), 1)


if __name__ == "__main__":
    unittest.main()
