"""uzaktan_yonetim._yeniden_baslat_tek — panelden tahta yeniden başlatma (2026-10-23).
Ders saatinde reboot komutu HİÇ çağrılmaz; sonuç Türkçe detay + denetim kodu taşır."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import tahta_yeniden_baslat
import uzaktan_yonetim

TAHTA = {"ad": "9-A", "ip": "x", "kullanici": "ogretmen", "admin": "etapadmin"}


class TestPanelYenidenBaslat(unittest.TestCase):
    def test_ders_saatinde_reboot_cagrilmaz(self):
        sahte = AsyncMock()
        with patch.object(tahta_yeniden_baslat, "ders_saatinde_mi", return_value=True), \
                patch.object(tahta_yeniden_baslat, "yeniden_baslat_tek", sahte):
            sonuc = asyncio.run(uzaktan_yonetim._yeniden_baslat_tek(TAHTA, {}))
        sahte.assert_not_awaited()
        self.assertFalse(sonuc["basarili"])
        self.assertEqual(sonuc["denetim_kodu"], "ders_saati")
        self.assertIn("Ders saatinde", sonuc["detay"])

    def test_ders_disinda_sebep_turkce_detay(self):
        for sebep, basarili, parca in (("tamam", True, "Yeniden başlatılıyor"),
                                       ("bekleme", False, "bekle"),
                                       ("izin_yok", False, "yetki")):
            with self.subTest(sebep=sebep):
                sahte = AsyncMock(return_value={"tahta": "9-A", "basarili": basarili, "sebep": sebep})
                with patch.object(tahta_yeniden_baslat, "ders_saatinde_mi", return_value=False), \
                        patch.object(tahta_yeniden_baslat, "yeniden_baslat_tek", sahte):
                    sonuc = asyncio.run(uzaktan_yonetim._yeniden_baslat_tek(TAHTA, {}))
                sahte.assert_awaited_once_with(TAHTA)
                self.assertEqual(sonuc["basarili"], basarili)
                self.assertIn(parca, sonuc["detay"])

    def test_route_kayitli(self):
        yollar = {r.path for r in uzaktan_yonetim.router.routes}
        self.assertIn("/admin/uzaktan/yeniden-baslat", yollar)


if __name__ == "__main__":
    unittest.main()
