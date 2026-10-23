"""zamanlanmis_gorevler birim testleri (2026-10-17). Canlı sistem/SSH çağrılmaz: hepsi mock."""
import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.requests import Request

import auth
import db
import ssh_istemci
import zamanlanmis_gorevler as zg

BETIK = zg.BETIK


def _istek(govde=b"", cerez="gecerli", origin="http://farabi.local:8010", yol="/zamanlanmis-gorevler/api/eylem",
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


class TestIfade(unittest.TestCase):
    def test_ifade_uret(self):
        self.assertEqual(zg.ifade_uret(["Mon", "Tue", "Wed", "Thu", "Fri"], "21:00"),
                         "Mon..Fri *-*-* 21:00:00 Europe/Istanbul")
        self.assertEqual(zg.ifade_uret(["Sat", "Sun"], "17:30"), "Sat,Sun *-*-* 17:30:00 Europe/Istanbul")
        self.assertEqual(zg.ifade_uret(["Mon", "Wed", "Fri"], "08:05"), "Mon,Wed,Fri *-*-* 08:05:00 Europe/Istanbul")
        self.assertEqual(zg.ifade_uret(list(zg.GUNLER), "00:00"), "*-*-* 00:00:00 Europe/Istanbul")
        self.assertEqual(zg.ifade_uret(["Fri", "Mon", "Tue", "Wed", "Sun"], "10:00"),
                         "Mon..Wed,Fri,Sun *-*-* 10:00:00 Europe/Istanbul")

    def test_ifade_uret_gecersiz(self):
        for gunler, saat in (([], "10:00"), (["Xyz"], "10:00"), (["Mon"], "25:00"), (["Mon"], "10;00"), (["Mon"], "")):
            with self.assertRaises(ValueError, msg=(gunler, saat)):
                zg.ifade_uret(gunler, saat)

    def test_ifade_coz_gidis_donus(self):
        for gunler in (["Mon", "Tue", "Wed", "Thu", "Fri"], ["Sat", "Sun"], ["Mon", "Wed"], list(zg.GUNLER)):
            self.assertEqual(zg.ifade_coz(zg.ifade_uret(gunler, "21:15")), {"gunler": gunler, "saat": "21:15"})
        self.assertIsNone(zg.ifade_coz("*-*-01 00:00:00"))
        self.assertIsNone(zg.ifade_coz("hourly"))

    def test_slug(self):
        self.assertEqual(zg.slug("Gece Karartma Çalışması!"), "gece-karartma-calismasi")
        self.assertEqual(zg.slug("!!!"), "")


class TestSinif(unittest.TestCase):
    def test_siniflar(self):
        self.assertEqual(zg.sinif("soru-havuzu-uret"), "farabi")
        self.assertEqual(zg.sinif("farabi-gorev-deneme"), "panel")
        for ad in ("apt-daily", "logrotate", "farabi-gorev-", "farabi-gorev-A", "farabi-gorev-x;y", "../x"):
            self.assertEqual(zg.sinif(ad), "sistem", ad)

    def test_yonetilen_dort_birim(self):
        self.assertEqual(len(zg.YONETILEN), 4)  # kazanim-test* 2026-10-14'te silindi


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
        zg._analiz_onbellek.clear()
        zg._tahta_onbellek.update(t=-1e9, v=None)
        self.sahte = AsyncMock(return_value=(0, "", ""))
        y = patch.object(zg, "_komut_kos", self.sahte)
        y.start()
        self.addCleanup(y.stop)
        t = patch.object(zg, "tahta_adlari", return_value=["9-A", "9-B"])
        t.start()
        self.addCleanup(t.stop)
        d = patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=False)
        d.start()
        self.addCleanup(d.stop)

    def _eylem(self, govde, **kw):
        return asyncio.run(zg.api_eylem(_istek(json.dumps(govde).encode(), **kw)))

    def _denetim(self):
        conn = db.baglanti()
        try:
            return [dict(r) for r in conn.execute("SELECT * FROM uzaktan_denetim")]
        finally:
            conn.close()

    def _reddedilir(self, govde, kod, **kw):
        with self.assertRaises(HTTPException) as c:
            self._eylem(govde, **kw)
        self.assertEqual(c.exception.status_code, kod)
        self.sahte.assert_not_awaited()

    def test_oturumsuz_401_ve_sayfa_303(self):
        self._reddedilir({"eylem": "ac", "birim": "soru-havuzu-uret"}, 401, cerez=None)
        yanit = asyncio.run(zg.sayfa(_istek(cerez=None, yol="/zamanlanmis-gorevler", accept="text/html")))
        self.assertEqual(yanit.status_code, 303)
        with self.assertRaises(HTTPException) as c:
            asyncio.run(zg.api_liste(_istek(cerez=None)))
        self.assertEqual(c.exception.status_code, 401)

    def test_yabanci_origin_403(self):
        self._reddedilir({"eylem": "ac", "birim": "soru-havuzu-uret"}, 403, origin="http://kotu.example")
        self._reddedilir({"eylem": "ac", "birim": "soru-havuzu-uret"}, 403, origin=None)

    def test_sistem_timera_eylem_reddedilir(self):
        for eylem in ("ac", "kapat", "calistir", "takvim", "takvim-sifirla", "sil"):
            self._reddedilir({"eylem": eylem, "birim": "apt-daily", "saat": "10:00", "gunler": ["Mon"]}, 403)

    def test_farabi_timera_sil_reddedilir(self):
        self._reddedilir({"eylem": "sil", "birim": "soru-havuzu-uret"}, 403)
        self._reddedilir({"eylem": "sil", "birim": "farabi-tahta-karart-haftaici"}, 403)

    def test_bilinmeyen_eylem_ve_bozuk_birim(self):
        self._reddedilir({"eylem": "olustur2", "birim": "soru-havuzu-uret"}, 403)
        self._reddedilir({"eylem": "ac", "birim": "farabi-gorev-A;rm"}, 403)

    def test_panel_gorevi_sil_dogru_arguman(self):
        yanit = self._eylem({"eylem": "sil", "birim": "farabi-gorev-deneme"})
        self.sahte.assert_awaited_once_with(["sudo", "-n", BETIK, "sil", "deneme"])
        self.assertTrue(json.loads(yanit.body)["ok"])

    def test_ac_kapat_calistir_argumanlari(self):
        for eylem in ("ac", "kapat", "calistir"):
            self.sahte.reset_mock()
            self._eylem({"eylem": eylem, "birim": "farabi-idari-yukle"})
            self.sahte.assert_awaited_once_with(["sudo", "-n", BETIK, eylem, "farabi-idari-yukle"])

    def test_takvim_gun_kutularindan_ifade(self):
        self._eylem({"eylem": "takvim", "birim": "farabi-tahta-karart-haftaici",
                     "gunler": ["Mon", "Tue", "Wed", "Thu", "Fri"], "saat": "21:30"})
        self.sahte.assert_awaited_once_with(["sudo", "-n", BETIK, "takvim", "farabi-tahta-karart-haftaici",
                                             "Mon..Fri *-*-* 21:30:00 Europe/Istanbul"])

    def test_takvim_gelismis_ifade_oncelikli(self):
        self._eylem({"eylem": "takvim", "birim": "farabi-idari-yukle", "ifade": "Sat *-*-* 10:00:00", "gunler": ["Mon"],
                     "saat": "09:00"})
        self.assertEqual(self.sahte.await_args.args[0][-1], "Sat *-*-* 10:00:00")

    def test_takvim_gecersiz_saat_400(self):
        self._reddedilir({"eylem": "takvim", "birim": "farabi-idari-yukle", "gunler": ["Mon"], "saat": "99:99"}, 400)

    def test_betik_ifadeyi_reddederse_hata_gosterilir(self):
        self.sahte.return_value = (2, "", "farabi-zamanlayici: takvim ifadesi geçersiz")
        yanit = self._eylem({"eylem": "takvim", "birim": "farabi-idari-yukle", "ifade": "bozuk"})
        govde = json.loads(yanit.body)
        self.assertFalse(govde["ok"])
        self.assertIn("geçersiz", govde["mesaj"])

    def test_takvim_sifirla(self):
        self._eylem({"eylem": "takvim-sifirla", "birim": "soru-havuzu-uret"})
        self.sahte.assert_awaited_once_with(["sudo", "-n", BETIK, "takvim-sifirla", "soru-havuzu-uret"])

    def test_olustur_arguman_listesi(self):
        self._eylem({"eylem": "olustur", "ad": "Gece Karart", "sablon": "ekran_karart", "tahtalar": ["9-A", "9-B"],
                     "gunler": ["Sat", "Sun"], "saat": "17:00"})
        self.sahte.assert_awaited_once_with(["sudo", "-n", BETIK, "olustur", "gece-karart", "ekran_karart",
                                             "9-A,9-B", "Sat,Sun *-*-* 17:00:00 Europe/Istanbul"])
        k = self._denetim()
        self.assertEqual(k[0]["eylem"], "zamanlayici-olustur")

    def test_olustur_hepsi(self):
        self._eylem({"eylem": "olustur", "ad": "tum", "sablon": "ekran_kaldir", "tahtalar": "hepsi",
                     "ifade": "*-*-* 07:00:00"})
        self.assertEqual(self.sahte.await_args.args[0][4:], ["tum", "ekran_kaldir", "hepsi", "*-*-* 07:00:00"])

    def test_olustur_gecersizler_betige_gitmez(self):
        temel = {"eylem": "olustur", "ad": "x", "sablon": "ekran_karart", "tahtalar": ["9-A"], "gunler": ["Mon"],
                 "saat": "10:00"}
        for degisim in ({"sablon": "tahta_yeniden_baslat"}, {"sablon": "rm -rf"}, {"tahtalar": ["9-Z"]},
                        {"tahtalar": []}, {"tahtalar": ["9-A;id"]}, {"ad": "!!!"}, {"saat": "xx"}):
            self._reddedilir({**temel, **degisim}, 400)

    def test_denetim_kaydi(self):
        self._eylem({"eylem": "kapat", "birim": "soru-havuzu-uret"})
        k = self._denetim()
        self.assertEqual(len(k), 1)
        self.assertEqual(k[0]["eylem"], "zamanlayici-kapat")
        self.assertEqual(k[0]["kaynak"], "zamanlanmis-gorevler")
        self.assertIn("soru-havuzu-uret", json.dumps(k[0]))

    def test_ders_saatinde_soru_havuzu_calistir_403(self):
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=True):
            self._reddedilir({"eylem": "calistir", "birim": "soru-havuzu-uret", "onay": True}, 403)

    def test_ders_saatinde_karartma_calistir_onay_ister(self):
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=True):
            yanit = self._eylem({"eylem": "calistir", "birim": "farabi-tahta-karart-haftaici"})
            self.assertEqual(yanit.status_code, 409)
            self.sahte.assert_not_awaited()
            yanit = self._eylem({"eylem": "calistir", "birim": "farabi-tahta-karart-haftaici", "onay": True})
        self.assertEqual(yanit.status_code, 200)
        self.sahte.assert_awaited_once()

    def test_sayfa_render_edilir(self):
        yanit = asyncio.run(zg.sayfa(_istek(yol="/zamanlanmis-gorevler", accept="text/html")))
        self.assertEqual(yanit.status_code, 200)
        for parca in (b"Zamanlanm", b'id="farabi-tablo"', b'id="panel-tablo"', b'id="tahta-tablo"',
                      b'id="sistem-tablo"', b'id="form-penceresi"'):
            self.assertIn(parca, yanit.body)


class TestListe(unittest.TestCase):
    def setUp(self):
        zg._analiz_onbellek.clear()

    def test_liste_siniflandirir(self):
        unit_files = ("chrony-dnssrv@.timer static -\n"  # şablon birimi: systemctl show'u kırar, listelenmemeli
                      "apt-daily.timer enabled enabled\nlogrotate.timer enabled enabled\n"
                      "soru-havuzu-uret.timer enabled enabled\nfarabi-gorev-deneme.timer enabled disabled\n")
        show = ("Id=soru-havuzu-uret.timer\nActiveState=active\nUnitFileState=enabled\n"
                "TimersCalendar={ OnCalendar=Mon..Fri *-*-* 17:15:00 Europe/Istanbul ; next_elapse=x }\n\n"
                "Id=farabi-gorev-deneme.timer\nActiveState=inactive\nUnitFileState=disabled\n"
                "TimersCalendar={ OnCalendar=Sat *-*-* 10:00:00 ; next_elapse=x }\n\n"
                "Id=farabi-gorev-deneme.service\nExecStart={ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 "
                "/x/scripts/tahta_eylem_zamanli.py ekran_karart 9-A,9-B ; ignore_errors=no }\n\n"
                "Id=apt-daily.timer\nActiveState=active\nUnitFileState=enabled\nTimersCalendar={ OnCalendar=*-*-* 06,18:00 ; next_elapse=x }\n")
        analiz = "  Normalized form: Mon..Fri *-*-* 17:15:00 Europe/Istanbul\n    Next elapse: Mon 2026-10-19 17:15:00 +03\n"

        async def sahte(args):
            if args[0] == "systemd-analyze":
                return 0, analiz, ""
            if args[:2] == ["systemctl", "list-unit-files"]:
                return 0, unit_files, ""
            self.assertFalse(any("@" in a for a in args), args)
            return 0, show, ""
        with patch.object(zg, "_komut_kos", sahte):
            sonuc = {g["birim"]: g for g in asyncio.run(zg.liste())}
        self.assertNotIn("chrony-dnssrv@", sonuc)
        self.assertEqual(sonuc["apt-daily"]["sinif"], "sistem")
        self.assertEqual(sonuc["apt-daily"]["izinli"], [])
        self.assertEqual(sonuc["soru-havuzu-uret"]["sinif"], "farabi")
        self.assertNotIn("sil", sonuc["soru-havuzu-uret"]["izinli"])
        self.assertEqual(sonuc["soru-havuzu-uret"]["ifade_parcalari"]["saat"], "17:15")
        self.assertTrue(sonuc["soru-havuzu-uret"]["etkin"])
        p = sonuc["farabi-gorev-deneme"]
        self.assertEqual((p["sinif"], p["eylem"], p["tahtalar"]), ("panel", "ekran_karart", "9-A,9-B"))
        self.assertIn("sil", p["izinli"])
        self.assertEqual(len(sonuc), 4 + 1 + 2)  # YONETILEN + panel + 2 sistem
        self.assertIn("farabi-idari-yukle", sonuc)  # dosyada olmasa da yönetilen listede
        self.assertNotIn("kazanim-test", sonuc)  # 2026-10-14'te silindi


class TestTahtaTarafi(unittest.TestCase):
    def setUp(self):
        zg._tahta_onbellek.update(t=-1e9, v=None)

    def _calistir(self, sahte):
        tahtalar = [{"ad": "9-A", "ip": "1.1.1.1", "kullanici": "ogretmen", "admin": None},
                    {"ad": "9-B", "ip": "1.1.1.2", "kullanici": "ogretmen", "admin": None},
                    {"ad": "9-C", "ip": "1.1.1.3", "kullanici": "ogretmen", "admin": None}]
        with patch.object(zg.tahta_kaydi, "tahtalari_yukle", return_value=tahtalar), \
             patch.object(ssh_istemci, "komut_calistir", sahte):
            return asyncio.run(zg.tahta_zamanlayicilari())

    def test_hata_dayaniklilik(self):
        async def sahte(ip, kullanici, komut, **kw):
            if ip == "1.1.1.1":
                return ssh_istemci.SSHSonuc(True, b"Sat 2026-10-17 21:00:00 +03 3h ekran-kapat.timer\n0 3 * * * /x/y\n", b"", cikis_kodu=0)
            if ip == "1.1.1.2":
                raise OSError("bağlantı")
            return ssh_istemci.SSHSonuc(False, b"", b"timeout", zaman_asimi=True)
        sonuc = self._calistir(sahte)
        by = {t["tahta"]: t for t in sonuc["tahtalar"]}
        self.assertTrue(by["9-A"]["ulasilabilir"])
        self.assertEqual(len(by["9-A"]["timer"]), 1)
        self.assertEqual(by["9-A"]["cron"], ["0 3 * * * /x/y"])
        self.assertFalse(by["9-B"]["ulasilabilir"])
        self.assertFalse(by["9-C"]["ulasilabilir"])

    def test_salt_okunur_komut_ve_onbellek(self):
        sahte = AsyncMock(return_value=ssh_istemci.SSHSonuc(True, b"", b"", cikis_kodu=0))
        self._calistir(sahte)
        self.assertEqual(sahte.await_count, 3)
        for cagri in sahte.await_args_list:
            self.assertEqual(cagri.args[2], zg.TAHTA_KOMUT)
        self.assertNotIn("systemctl stop", zg.TAHTA_KOMUT)
        with patch.object(ssh_istemci, "komut_calistir", sahte):
            asyncio.run(zg.tahta_zamanlayicilari())  # önbellekten
        self.assertEqual(sahte.await_count, 3)


if __name__ == "__main__":
    unittest.main()
