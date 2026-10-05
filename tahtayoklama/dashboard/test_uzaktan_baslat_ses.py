"""uzaktan_baslat — hatırlatma sesi (2026-10-05)."""

import asyncio
import unittest
from unittest import mock

import ssh_istemci
import uzaktan_baslat


def _s(ok=True, out=b""):
    return ssh_istemci.SSHSonuc(ok, out, b"")


TAHTA = {"ip": "1.2.3.4", "ssh_kullanici": "ogretmen", "python_yolu": "/py", "ad": "9-A"}


class TestSes(unittest.TestCase):
    def _calistir(self, komut_yaniti, scp_ok=True):
        komutlar = []

        async def komut(ip, k, c, **kw):
            komutlar.append(c)
            return komut_yaniti(c)

        async def ortam(ip, k):
            return (":0", "/x", "1001")

        scp = mock.AsyncMock(return_value=_s(scp_ok))
        with mock.patch.object(ssh_istemci, "komut_calistir", komut), \
             mock.patch.object(ssh_istemci, "x_ortamini_kesfet", ortam), \
             mock.patch.object(ssh_istemci, "scp_gonder", scp), \
             mock.patch.object(uzaktan_baslat.asyncio, "sleep", mock.AsyncMock()):
            sonuc = asyncio.run(uzaktan_baslat.baslat(TAHTA))
        return sonuc, komutlar, scp

    def test_zaten_aciksa_one_getirir_ve_ses_calar(self):
        sonuc, komutlar, scp = self._calistir(lambda c: _s(True, b"123 py" if c.startswith("pgrep") else b""))
        self.assertTrue(sonuc["basarili"])
        self.assertEqual(sonuc["durum"], "one_getirildi")
        paplay = [c for c in komutlar if "paplay" in c]
        self.assertEqual(len(paplay), 1)
        self.assertIn("XDG_RUNTIME_DIR=/run/user/1001", paplay[0])
        scp.assert_not_called()  # dosya zaten var (test -f başarılı)

    def test_yeni_baslatmada_da_ses_calar(self):
        pgrep_sayac = {"n": 0}

        def yanit(c):
            if c.startswith("pgrep"):
                pgrep_sayac["n"] += 1
                return _s(True, b"" if pgrep_sayac["n"] == 1 else b"123 py")
            return _s(True)

        sonuc, komutlar, _ = self._calistir(yanit)
        self.assertEqual(sonuc["durum"], "yeni_baslatildi")
        self.assertTrue(any("paplay" in c for c in komutlar))

    def test_dosya_yoksa_kopyalanir(self):
        def yanit(c):
            if c.startswith("pgrep"):
                return _s(True, b"123 py")
            if c.startswith("test -f"):
                return _s(False)
            return _s(True)

        _sonuc, komutlar, scp = self._calistir(yanit)
        scp.assert_called_once()
        self.assertTrue(any("paplay" in c for c in komutlar))

    def test_ses_hatasi_basariyi_bozmaz(self):
        def yanit(c):
            if c.startswith("pgrep"):
                return _s(True, b"123 py")
            if c.startswith("test -f"):
                return _s(False)
            return _s(True)

        sonuc, komutlar, _ = self._calistir(yanit, scp_ok=False)
        self.assertTrue(sonuc["basarili"])
        self.assertIn("kopyalanamadı", sonuc["detay"])
        self.assertFalse(any("paplay" in c for c in komutlar))


if __name__ == "__main__":
    unittest.main()
