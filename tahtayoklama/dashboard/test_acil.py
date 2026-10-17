"""acil.py testleri (2026-10-16): kanal bağımsızlığı, tatbikat SMS yolu, ekran sayfası."""

import asyncio
import json
import unittest
from unittest import mock

import acil

AYAR = {"sms_url": "http://sms", "sms_anahtar": "k"}


class TestAcil(unittest.TestCase):
    def test_hata_veren_kanal_sozluk_doner(self):
        def patla(*_):
            raise RuntimeError("zil kapalı")

        s = asyncio.run(acil._guvenli("Zil anonsu", patla))
        self.assertEqual(
            s, {"kanal": "Zil anonsu", "basarili": False, "detay": "zil kapalı"}
        )

    def test_tatbikat_smsi_yalniz_yonetime(self):
        with mock.patch.object(
            acil, "_post", return_value={"alicilar": ["A", "B"]}
        ) as p:
            s = acil._sms_gonder(AYAR, "kilit", True)
        p.assert_called_once()
        url, govde, _ = p.call_args.args
        self.assertEqual(url, "http://sms/api/arac/acil")
        self.assertTrue(govde["metin"].startswith(acil.TATBIKAT_ONEKI))
        self.assertTrue(s["basarili"])

    def test_gercek_sms_personele_taslak_ve_gonder(self):
        cevaplar = [{"taslak_id": "t1", "alici_sayisi": 22}, {}]
        with mock.patch.object(acil, "_post", side_effect=cevaplar) as p:
            s = acil._sms_gonder(AYAR, "tahliye", False)
        urller = [c.args[0] for c in p.call_args_list]
        self.assertEqual(
            urller,
            [
                "http://sms/api/arac/personel-taslak",
                "http://sms/api/arac/personel-gonder",
            ],
        )
        self.assertNotIn(acil.TATBIKAT_ONEKI, p.call_args_list[0].args[1]["metin"])
        self.assertIn("22", s["detay"])

    def test_ekran_sablonu_tatbikat_etiketi(self):
        sablon = acil.templates.get_template("acil_ekran.html")
        html = sablon.render(t=acil.TURLER["tahliye"], tatbikat=True)
        self.assertIn("TAHLİYE", html)
        self.assertIn("Gerçek bir olay yoktur", html)
        html = sablon.render(t=acil.TURLER["gecti"], tatbikat=False)
        self.assertNotIn("Gerçek bir olay yoktur", html)

    def test_acil_sayfasi_taban_ile_render(self):
        # 2026-10-16: gun_adi_buyuk global'i eksikti → canlıda 500 verdi.
        from types import SimpleNamespace

        istek = SimpleNamespace(
            url=SimpleNamespace(path="/acil", hostname="farabi.local")
        )
        html = acil.templates.get_template("acil.html").render(
            request=istek, turler=acil.TURLER
        )
        self.assertIn("KİLİT-KAPI", html)
        self.assertIn("/api/acil/tetikle", html)


class TestTahtaAlarm(unittest.TestCase):
    def setUp(self):
        acil._pin_hatalari.clear()
        self.ozet = acil.hashlib.sha256(b"1234").hexdigest()

    def test_kat_ve_sms_metni(self):
        self.assertEqual(acil.kat_adi("9-A"), "üst kat")
        self.assertEqual(acil.kat_adi("11-B"), "giriş katı")
        metin = acil.tahta_alarm_metni("12-B", "10:42")
        self.assertIn("12-B (üst kat)", metin)
        self.assertIn("10:42", metin)
        self.assertLessEqual(len(acil.TATBIKAT_ONEKI + metin), 300)  # smssistemi sınırı

    def test_pin_dogru_yanlis_ve_kilit(self):
        self.assertTrue(acil.pin_dogru_mu("9-A", "1234", self.ozet, 0))
        for i in range(acil.PIN_HATA_SINIRI):
            self.assertFalse(acil.pin_dogru_mu("9-A", "0000", self.ozet, i))
        with self.assertRaises(acil.HTTPException) as e:
            acil.pin_dogru_mu("9-A", "1234", self.ozet, 10)  # doğru PIN de kilitli
        self.assertEqual(e.exception.status_code, 429)
        self.assertTrue(
            acil.pin_dogru_mu("9-B", "1234", self.ozet, 10)
        )  # başka tahta etkilenmez
        self.assertTrue(
            acil.pin_dogru_mu("9-A", "1234", self.ozet, 10 + acil.PIN_KILIT_SN)
        )

    def test_yalniz_sms_anons_ve_ekran_yok(self):
        async def calistir():
            with (
                mock.patch.object(
                    acil, "_sms_gonder", return_value={"kanal": "SMS", "basarili": True}
                ),
                mock.patch.object(acil, "_zil_cal") as z,
                mock.patch.object(acil, "_tahta_ekran_ac") as e,
                mock.patch.object(acil, "_olay_yaz"),
            ):
                k = await acil._baslat(
                    {"ekran_url": "u"}, "kilit", True, "tahta:9-A", "m", yalniz_sms=True
                )
            return k, z, e

        k, z, e = asyncio.run(calistir())
        z.assert_not_called()
        e.assert_not_called()
        self.assertEqual([x["kanal"] for x in k["kanallar"]], ["SMS"])


class TestYonetim(unittest.TestCase):
    def test_aktif_alarm(self):
        self.assertIsNone(acil.aktif_alarm([]))
        self.assertEqual(acil.aktif_alarm([{"tur": "deprem"}, {"tur": "zil_siren"}])["tur"], "deprem")
        self.assertIsNone(acil.aktif_alarm([{"tur": "kilit"}, {"tur": "yanlis_alarm"}]))
        self.assertIsNone(acil.aktif_alarm([{"tur": "yangin"}, {"tur": "ekranlari_kapat"}]))

    def test_yeni_senaryolar_ve_siren(self):
        for tur in ("kilit", "tahliye", "deprem", "yangin"):
            self.assertTrue(acil.TURLER[tur]["siren"], tur)
            self.assertLessEqual(len(acil.TATBIKAT_ONEKI + acil.TURLER[tur]["sms"]), 300)
        self.assertFalse(acil.TURLER["gecti"].get("siren"))

    def test_siren_sonra_anons_ve_eksik_anons(self):
        a = {"anons_idleri": {"kilit": "3e5f4cf2"}, "siren_sn": 0}
        with mock.patch.object(acil, "_zil_istek", return_value={"tamam": True}) as z:
            acil._zil_cal(a, "kilit")
        self.assertEqual([c.args[1] for c in z.call_args_list], ["/acil/siren-cal", "/anons/cal/3e5f4cf2"])
        with mock.patch.object(acil, "_zil_istek", return_value={"tamam": True}) as z:
            with self.assertRaises(RuntimeError):
                acil._zil_cal(a, "deprem")  # anonsu henüz yok → siren yine çalar
        self.assertEqual([c.args[1] for c in z.call_args_list], ["/acil/siren-cal"])

    def test_makine_anahtari(self):
        istek = mock.Mock(headers={"X-Acil-Anahtar": "yanlis"})
        with mock.patch.object(acil, "_ayarlar", return_value={"makine_anahtar": "dogru"}):
            with self.assertRaises(acil.HTTPException):
                acil._makine_dogrula(istek)
            istek.headers = {"X-Acil-Anahtar": "dogru"}
            acil._makine_dogrula(istek)


class TestMakineOkul(unittest.TestCase):
    """Okul portalının çağırdığı makine uçları: tatbikat ayardan, sms_metni, durum."""

    def _tetikle(self, govde, ayar):
        istek = mock.Mock(headers={"X-Acil-Anahtar": "k"})

        async def gov(_):
            return govde

        async def calis():
            with (
                mock.patch.object(acil, "_ayarlar", return_value={"makine_anahtar": "k", **ayar}),
                mock.patch.object(acil.tahta_api, "_govde", gov),
                mock.patch.object(acil, "_baslat", mock.AsyncMock(return_value={"tur": "kilit"})) as b,
            ):
                await acil.acil_makine_tetikle(istek)
            return b

        return asyncio.run(calis())

    def test_tatbikat_verilmezse_ayardan(self):
        b = self._tetikle({"tur": "kilit", "kaynak": "okul:1:A"}, {"tahta_alarm_tatbikat": False})
        self.assertFalse(b.call_args.args[2])
        b = self._tetikle({"tur": "kilit"}, {"tahta_alarm_tatbikat": True})
        self.assertTrue(b.call_args.args[2])

    def test_tatbikat_acik_verilirse_ayara_bakilmaz(self):
        b = self._tetikle({"tur": "kilit", "tatbikat": True}, {"tahta_alarm_tatbikat": False})
        self.assertTrue(b.call_args.args[2])

    def test_sms_metni_kisaltilir_ve_temizlenir(self):
        b = self._tetikle({"tur": "kilit", "sms_metni": "A\x00" + "b" * 400}, {})
        self.assertLessEqual(len(b.call_args.kwargs["sms_metni"]), acil.SMS_METNI_AZAMI)
        self.assertNotIn("\x00", b.call_args.kwargs["sms_metni"])

    def test_durum_anahtarsiz_401_ve_icerik(self):
        with mock.patch.object(acil, "_ayarlar", return_value={"makine_anahtar": "k", "tahta_alarm_tatbikat": True}):
            with self.assertRaises(acil.HTTPException):
                asyncio.run(acil.acil_makine_durum(mock.Mock(headers={})))
            with mock.patch.object(acil, "son_olaylar", return_value=[{"tur": "kilit", "zaman": "z", "tatbikat": True}]):
                r = asyncio.run(acil.acil_makine_durum(mock.Mock(headers={"X-Acil-Anahtar": "k"})))
        d = json.loads(r.body)
        self.assertEqual(d["aktif"]["tur"], "kilit")
        self.assertTrue(d["tatbikat"])


if __name__ == "__main__":
    unittest.main()
