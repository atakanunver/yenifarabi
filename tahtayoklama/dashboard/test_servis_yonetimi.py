"""servis_yonetimi birim testleri (2026-10-08)."""
import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

import servis_yonetimi as sy
import zil

DERS_SAATI = datetime(2026, 10, 7, 10, 0, tzinfo=zil.ISTANBUL)   # Çarşamba 10:00
AKSAM = datetime(2026, 10, 7, 20, 0, tzinfo=zil.ISTANBUL)


class TestListe(unittest.TestCase):
    def test_bilinmeyen_birim_ve_eylem_reddedilir(self):
        for birim, eylem in (("ssh", "yeniden-baslat"), ("farabi-api", "sil"),
                             ("farabi-api;rm", "yeniden-baslat"),
                             ("farabi-yoklama-dashboard", "durdur"),
                             ("farabi-api", "zamanlayici-ac")):
            with self.assertRaises(ValueError, msg=(birim, eylem)):
                sy.eylem_dogrula(birim, eylem)

    def test_gecerli_eylemler(self):
        sy.eylem_dogrula("farabi-api", "yeniden-baslat")
        sy.eylem_dogrula("soru-havuzu-uret", "zamanlayici-kapat")
        sy.eylem_dogrula("soru-havuzu-uret", "hata-temizle")


class TestDersSaati(unittest.TestCase):
    def test_ders_saatinde_uyarili_birim_onay_ister(self):
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=True):
            self.assertIn("ders", sy.onay_gerekli_mi("farabi-api", "yeniden-baslat", DERS_SAATI))
            self.assertIsNone(sy.onay_gerekli_mi("farabi-smssistemi", "yeniden-baslat", DERS_SAATI))

    def test_aksam_onay_gerekmez(self):
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=False):
            self.assertIsNone(sy.onay_gerekli_mi("farabi-api", "yeniden-baslat", AKSAM))

    def test_soru_havuzu_ders_saatinde_simdi_calistir_yasak(self):
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=True):
            self.assertTrue(sy.ders_saatinde_yasak_mi("soru-havuzu-uret", "simdi-calistir", DERS_SAATI))
            self.assertFalse(sy.ders_saatinde_yasak_mi("soru-havuzu-uret", "zamanlayici-kapat", DERS_SAATI))


class TestMaskeleVeHata(unittest.TestCase):
    def test_maskele(self):
        self.assertEqual(sy.maskele("GET http://admin:gizli@1.2.3.4/x"), "GET http://***@1.2.3.4/x")
        self.assertEqual(sy.maskele("token=abc123 ok"), "token=*** ok")
        self.assertEqual(sy.maskele("FARABI_EMBED_ANAHTAR=xyz"), "FARABI_EMBED_ANAHTAR=***")
        self.assertEqual(sy.maskele("password: hunter2"), "password: ***")

    def test_son_hata_traceback_son_satiri(self):
        satirlar = ["a", "Traceback (most recent call last):", "  File x",
                    "OSError: [Errno 7] Argument list too long: '/x/agy'",
                    "systemd[1]: x.service: Main process exited, code=exited, status=1/FAILURE"]
        self.assertEqual(sy.son_hata(satirlar), "OSError: [Errno 7] Argument list too long: '/x/agy'")

    def test_son_hata_yoksa_none(self):
        self.assertIsNone(sy.son_hata(["Started x", "ok"]))


class TestCalistir(unittest.TestCase):
    def test_betik_arguman_listesiyle_cagrilir(self):
        sahte = AsyncMock(return_value=(0, "", ""))
        with patch.object(sy, "_komut_kos", sahte):
            sonuc = asyncio.run(sy.calistir("farabi-api", "yeniden-baslat"))
        sahte.assert_awaited_once_with(["sudo", "-n", sy.BETIK, "yeniden-baslat", "farabi-api"])
        self.assertTrue(sonuc["ok"])

    def test_gecersiz_birim_betige_gitmez(self):
        sahte = AsyncMock()
        with patch.object(sy, "_komut_kos", sahte):
            with self.assertRaises(ValueError):
                asyncio.run(sy.calistir("ssh", "yeniden-baslat"))
        sahte.assert_not_awaited()

    def test_betik_hatasi_ok_false(self):
        with patch.object(sy, "_komut_kos", AsyncMock(return_value=(1, "", "Job failed"))):
            sonuc = asyncio.run(sy.calistir("sinif-arena", "baslat"))
        self.assertFalse(sonuc["ok"])
        self.assertIn("Job failed", sonuc["mesaj"])


class TestDurumAyristir(unittest.TestCase):
    def test_show_ciktisi_birimlere_ayrilir(self):
        ham = ("Id=farabi-api.service\nActiveState=active\nSubState=running\nResult=success\n"
               "MemoryCurrent=104857600\nActiveEnterTimestamp=Wed 2026-10-08 08:21:19 UTC\n\n"
               "Id=soru-havuzu-uret.timer\nActiveState=active\nSubState=waiting\nResult=success\n"
               "NextElapseUSecRealtime=Thu 2026-10-08 14:15:00 UTC\nLastTriggerUSec=Wed 2026-10-07 14:15:11 UTC\n\n"
               "Id=soru-havuzu-uret.service\nActiveState=failed\nSubState=failed\nResult=exit-code\n")
        d = sy._show_ayristir(ham)
        self.assertEqual(d["farabi-api.service"]["SubState"], "running")
        self.assertEqual(d["soru-havuzu-uret.service"]["Result"], "exit-code")
        self.assertIn("NextElapseUSecRealtime", d["soru-havuzu-uret.timer"])

    def test_durumlar_bellek_ve_zamanlayici(self):
        ham = ("Id=farabi-api.service\nActiveState=active\nSubState=running\nResult=success\n"
               "MemoryCurrent=104857600\n\n"
               "Id=soru-havuzu-uret.timer\nUnitFileState=enabled\nNextElapseUSecRealtime=Thu 2026-10-08 14:15:00 UTC\n")
        with patch.object(sy, "_komut_kos", AsyncMock(return_value=(0, ham, ""))):
            liste = {b["birim"]: b for b in asyncio.run(sy.durumlar())}
        self.assertEqual(liste["farabi-api"]["bellek_mib"], 100)
        self.assertTrue(liste["soru-havuzu-uret"]["zamanlayici_etkin"])
        self.assertIsNone(liste["farabi-api"]["zamanlayici_etkin"])
        self.assertEqual(set(liste), set(sy.BIRIMLER))


import json
from pathlib import Path
from tempfile import TemporaryDirectory

import auth
import db
from fastapi import HTTPException
from fastapi.requests import Request


def _istek(govde=b"", cerez="gecerli", origin="http://farabi.local:8010", yol="/api/servisler/eylem",
           accept="application/json"):
    headers = [(b"host", b"farabi.local:8010"), (b"accept", accept.encode())]
    if cerez:
        headers.append((b"cookie", f"{auth.COOKIE_ADI}={cerez}".encode()))
    if origin:
        headers.append((b"origin", origin.encode()))
    alindi = {"v": False}

    async def receive():
        if alindi["v"]:
            return {"type": "http.disconnect"}
        alindi["v"] = True
        return {"type": "http.request", "body": govde, "more_body": False}
    scope = {"type": "http", "method": "POST", "path": yol, "headers": headers,
             "client": ("10.0.0.5", 1), "query_string": b""}
    return Request(scope, receive)


class TestUclar(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        yama = patch.object(db, "DB_YOLU", Path(self._tmp.name) / "test.db")
        yama.start()
        self.addCleanup(yama.stop)
        db.semayi_kur()
        conn = db.baglanti()
        conn.execute("INSERT INTO oturumlar (token) VALUES ('gecerli')")
        conn.commit()
        conn.close()

    def _eylem(self, govde, **kw):
        return asyncio.run(sy.api_eylem(_istek(json.dumps(govde).encode(), **kw)))

    def _denetim(self):
        conn = db.baglanti()
        try:
            return [dict(r) for r in conn.execute("SELECT * FROM uzaktan_denetim")]
        finally:
            conn.close()

    def test_oturumsuz_401(self):
        with self.assertRaises(HTTPException) as c:
            self._eylem({"birim": "farabi-api", "eylem": "yeniden-baslat"}, cerez=None)
        self.assertEqual(c.exception.status_code, 401)

    def test_yabanci_origin_403(self):
        with self.assertRaises(HTTPException) as c:
            self._eylem({"birim": "farabi-api", "eylem": "yeniden-baslat"}, origin="http://kotu.site")
        self.assertEqual(c.exception.status_code, 403)

    def test_liste_disi_400_betik_cagrilmaz(self):
        sahte = AsyncMock()
        with patch.object(sy, "_komut_kos", sahte):
            with self.assertRaises(HTTPException) as c:
                self._eylem({"birim": "ssh", "eylem": "yeniden-baslat"})
        self.assertEqual(c.exception.status_code, 400)
        sahte.assert_not_awaited()

    def test_ders_saatinde_onaysiz_409_onayli_calisir_ve_denetlenir(self):
        sahte = AsyncMock(return_value=(0, "", ""))
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=True), \
             patch.object(sy, "_komut_kos", sahte):
            yanit = self._eylem({"birim": "farabi-api", "eylem": "yeniden-baslat"})
            self.assertEqual(yanit.status_code, 409)
            sahte.assert_not_awaited()
            yanit = self._eylem({"birim": "farabi-api", "eylem": "yeniden-baslat", "onay": True})
        self.assertEqual(yanit.status_code, 200)
        sahte.assert_awaited_once()
        kayit = self._denetim()
        self.assertEqual(len(kayit), 1)
        self.assertEqual(kayit[0]["eylem"], "servis-yeniden-baslat")
        self.assertEqual(kayit[0]["kaynak"], "servisler")

    def test_ders_saatinde_soru_havuzu_simdi_calistir_403(self):
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=True), \
             patch.object(sy, "_komut_kos", AsyncMock()) as sahte:
            with self.assertRaises(HTTPException) as c:
                self._eylem({"birim": "soru-havuzu-uret", "eylem": "simdi-calistir", "onay": True})
        self.assertEqual(c.exception.status_code, 403)
        sahte.assert_not_awaited()

    def test_log_ucu_maskeli_ve_son_hata(self):
        cikti = ("2026-10-07T23:01:03+00:00 farabi python[474141]: Traceback (most recent call last):\n"
                 "2026-10-07T23:01:03+00:00 farabi python[474141]: OSError: boom token=gizli\n")
        with patch.object(sy, "_komut_kos", AsyncMock(return_value=(0, cikti, ""))):
            yanit = asyncio.run(sy.api_log(_istek(yol="/api/servisler/log/soru-havuzu-uret"),
                                           "soru-havuzu-uret"))
        govde = json.loads(yanit.body)
        self.assertNotIn("gizli", json.dumps(govde))
        self.assertTrue(govde["son_hata"].startswith("OSError: boom"))


if __name__ == "__main__":
    unittest.main()
