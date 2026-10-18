"""guvenlik.py testleri (2026-10-18): ayrı çerez yetkisi, alarm/iptal/haber uçları."""

import asyncio
import json
import unittest
from unittest import mock

from fastapi import HTTPException
from fastapi.requests import Request

import acil
import auth
import guvenlik

AYAR = {"anahtar": "00" * 32, "sifre_hash": auth.sifre_hashle("kapi1234")}
ACIL_AYAR = {"sms_url": "http://sms", "sms_anahtar": "k"}


def _istek(yol, govde=None, cerez=None, method="POST"):
    basliklar = [(b"cookie", cerez.encode())] if cerez else []
    veri = json.dumps(govde).encode() if govde is not None else b""

    async def receive():
        return {"type": "http.request", "body": veri, "more_body": False}

    scope = {
        "type": "http",
        "method": method,
        "path": yol,
        "headers": basliklar,
        "query_string": b"",
        "client": ("10.0.0.5", 1234),
    }
    return Request(scope, receive)


class TestCerez(unittest.TestCase):
    def test_gecerli_ve_kurcalanmis(self):
        c = guvenlik.cerez_uret(AYAR, simdi=1000)
        self.assertTrue(guvenlik.cerez_gecerli(AYAR, c, simdi=1001))
        self.assertFalse(guvenlik.cerez_gecerli(AYAR, c[:-1] + "0", simdi=1001))
        self.assertFalse(guvenlik.cerez_gecerli(AYAR, "bozuk", simdi=1001))
        self.assertFalse(guvenlik.cerez_gecerli(AYAR, None))

    def test_oturum_bir_saatte_duser(self):
        c = guvenlik.cerez_uret(AYAR, simdi=1000)
        self.assertTrue(guvenlik.cerez_gecerli(AYAR, c, simdi=1000 + 3599))
        self.assertFalse(guvenlik.cerez_gecerli(AYAR, c, simdi=1000 + 3601))

    def test_kilitle_cerezi_siler(self):
        y = asyncio.run(guvenlik.cikis())
        self.assertEqual(y.headers["location"], "/guvenlik/giris")
        self.assertIn(f"{guvenlik.COOKIE_ADI}=", y.headers["set-cookie"])
        self.assertIn("Max-Age=0", y.headers["set-cookie"])

    def test_suresi_dolmus_ve_baska_anahtar(self):
        c = guvenlik.cerez_uret(AYAR, simdi=1000)
        self.assertFalse(
            guvenlik.cerez_gecerli(AYAR, c, simdi=1000 + guvenlik.OTURUM_SN + 1)
        )
        self.assertFalse(guvenlik.cerez_gecerli({"anahtar": "11" * 32}, c, simdi=1001))


class TestYetki(unittest.TestCase):
    def setUp(self):
        self.cerez = f"{guvenlik.COOKIE_ADI}={guvenlik.cerez_uret(AYAR)}"

    def test_guvenlik_cerezi_guvenlik_yollarini_acar(self):
        with mock.patch.object(guvenlik, "_ayar", return_value=AYAR):
            self.assertTrue(guvenlik.yetkili(_istek("/guvenlik", cerez=self.cerez)))

    def test_guvenlik_cerezi_yonetici_oturumu_sayilmaz(self):
        # /acil, /admin vb. auth.dogrula kullanır — "oturum" çerezi yoksa DB'ye bakmadan False.
        self.assertFalse(auth.dogrula(_istek("/acil", cerez=self.cerez), conn=None))

    def test_cerezsiz_401(self):
        with (
            mock.patch.object(guvenlik, "_ayar", return_value=AYAR),
            mock.patch.object(guvenlik.db, "baglanti"),
            mock.patch.object(guvenlik.auth, "dogrula", return_value=False),
        ):
            with self.assertRaises(HTTPException) as h:
                asyncio.run(guvenlik.durum(_istek("/api/guvenlik/durum", method="GET")))
        self.assertEqual(h.exception.status_code, 401)

    def test_kaynak_adi(self):
        self.assertEqual(acil.kaynak_adi("guvenlik:10.0.0.5"), "Güvenlik (kapı)")


class TestUclar(unittest.TestCase):
    def setUp(self):
        guvenlik._son_haber.clear()
        self.yamalar = [
            mock.patch.object(guvenlik, "yetkili", return_value=True),
            mock.patch.object(acil, "_ayarlar", return_value=ACIL_AYAR),
        ]
        for y in self.yamalar:
            y.start()

    def tearDown(self):
        for y in self.yamalar:
            y.stop()

    def _hata(self, coro):
        with self.assertRaises(HTTPException) as h:
            asyncio.run(coro)
        return h.exception.status_code

    def test_alarm_baslat_cagrilir(self):
        kayit = {
            "kanallar": [{"kanal": "SMS", "basarili": True, "detay": "x"}],
            "tahtalar": [{"basarili": True}, {"basarili": False}],
        }
        with mock.patch.object(
            acil, "_baslat", new=mock.AsyncMock(return_value=kayit)
        ) as b:
            y = asyncio.run(
                guvenlik.alarm(
                    _istek("/api/guvenlik/alarm", {"tur": "yangin", "tatbikat": False})
                )
            )
        b.assert_awaited_once_with(
            ACIL_AYAR, "yangin", False, kaynak="guvenlik:10.0.0.5"
        )
        g = json.loads(y.body)
        self.assertEqual((g["tahta_toplam"], g["tahta_basarili"]), (2, 1))
        self.assertNotIn("detay", g["kanallar"][0])

    def test_alarm_gecersiz(self):
        with mock.patch.object(acil, "_baslat", new=mock.AsyncMock()) as b:
            self.assertEqual(
                self._hata(
                    guvenlik.alarm(_istek("/x", {"tur": "gecti", "tatbikat": True}))
                ),
                400,
            )
            self.assertEqual(
                self._hata(guvenlik.alarm(_istek("/x", {"tur": "kilit"}))), 400
            )
            self.assertEqual(
                self._hata(
                    guvenlik.alarm(_istek("/x", {"tur": "kilit", "tatbikat": "evet"}))
                ),
                400,
            )
        b.assert_not_awaited()

    def test_iptal_aktif_alarm_yoksa_409(self):
        with (
            mock.patch.object(acil, "son_olaylar", return_value=[]),
            mock.patch.object(acil, "_yanlis_alarm", new=mock.AsyncMock()) as y,
        ):
            self.assertEqual(self._hata(guvenlik.iptal(_istek("/x", {}))), 409)
        y.assert_not_awaited()

    def test_iptal_aktif_alarmda_cagrilir(self):
        olaylar = [{"tur": "kilit", "tatbikat": True}]
        with (
            mock.patch.object(acil, "son_olaylar", return_value=olaylar),
            mock.patch.object(
                acil, "_yanlis_alarm", new=mock.AsyncMock(return_value={})
            ) as y,
        ):
            asyncio.run(guvenlik.iptal(_istek("/x", {})))
        y.assert_awaited_once_with(ACIL_AYAR, "guvenlik:10.0.0.5")

    def test_haber_sms_telegram_kayit_ve_tekrar_engeli(self):
        with (
            mock.patch.object(
                acil, "_post", return_value={"alicilar": ["A", "B"]}
            ) as p,
            mock.patch.object(
                acil,
                "_telegram_bildir",
                return_value={"kanal": "Telegram", "basarili": True},
            ) as t,
            mock.patch.object(acil, "_olay_yaz") as o,
        ):
            asyncio.run(guvenlik.haber(_istek("/x", {"neden": "supheli"})))
            self.assertEqual(
                self._hata(guvenlik.haber(_istek("/x", {"neden": "supheli"}))), 429
            )
        url, govde, _ = p.call_args.args
        self.assertEqual(url, "http://sms/api/arac/acil")
        self.assertTrue(govde["metin"].startswith("GÜVENLİK: Şüpheli kişi / araç"))
        self.assertNotIn(acil.TATBIKAT_ONEKI, govde["metin"])
        self.assertIn("GÜVENLİK", t.call_args.args[1])
        kayit = o.call_args.args[0]
        self.assertEqual((kayit["tur"], kayit["neden"]), ("guvenlik_uyari", "supheli"))
        self.assertIsNone(acil.aktif_alarm([kayit]))  # sessiz uyarı alarm sayılmaz

    def test_haber_gecersiz_neden(self):
        self.assertEqual(
            self._hata(guvenlik.haber(_istek("/x", {"neden": "siren"}))), 400
        )


class TestSablon(unittest.TestCase):
    def test_ekran_dort_alarm_ve_nedenler(self):
        html = guvenlik.templates.get_template("guvenlik.html").render(
            alarmlar={k: acil.TURLER[k] for k in guvenlik.ALARMLAR},
            nedenler=guvenlik.NEDENLER,
            telefonlar=[{"ad": "Acil", "no": "112"}],
        )
        for t in (
            "KİLİT-KAPI",
            "TAHLİYE",
            "YANGIN",
            "DEPREM",
            "Kavga / kargaşa",
            "/api/guvenlik/alarm",
        ):
            self.assertIn(t, html)
        self.assertNotIn("TEHLİKE GEÇTİ", html)


if __name__ == "__main__":
    unittest.main()
