"""ajan_api.py + tahta_yeniden_baslat.py testleri. httpx yok → route
fonksiyonları doğrudan çağrılır. SSH taklit, DB/ajan.json geçici."""

import asyncio
import json
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.requests import Request

import ajan_api
import app
import db
import ssh_istemci
import tahta_yeniden_baslat as ty
import uzaktan_yonetim
import zil

ANAHTAR = "test-anahtari-123"
TAHTALAR = [
    {"ad": "9-A", "ip": "10.9.9.1", "kullanici": "ogretmen", "admin": "etapadmin"},
    {"ad": "9-B", "ip": "10.9.9.2", "kullanici": "ogretmen", "admin": "etapadmin"},
    {"ad": "10-A", "ip": "10.9.9.3", "kullanici": "ogretmen", "admin": None},
]
IP_RE = re.compile(r"\d+\.\d+\.\d+\.\d+")


def _istek(istemci=("127.0.0.1", 5555), basliklar=None, govde=None, cerez=None):
    h = []
    for k, v in (basliklar or {}).items():
        h.append((k.lower().encode(), v.encode()))
    if cerez:
        h.append((b"cookie", f"oturum={cerez}".encode()))
    req = Request({"type": "http", "method": "POST", "path": "/api/ajan/x",
                   "headers": h, "client": istemci})
    req.json = AsyncMock(return_value=govde)
    return req


def _ok(stdout=b"", cikis=0):
    return ssh_istemci.SSHSonuc(cikis == 0, stdout, b"", cikis_kodu=cikis)


def _yok(cikis=1, stderr=b"", zaman_asimi=False):
    return ssh_istemci.SSHSonuc(False, b"", stderr, zaman_asimi=zaman_asimi,
                                cikis_kodu=None if zaman_asimi else cikis)


class _Temel(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        d = Path(self._tmp.name)
        self.anahtar_yolu = d / "ajan.json"
        self.anahtar_yolu.write_text(json.dumps({"anahtar": ANAHTAR}))
        for yama in (
            patch.object(db, "DB_YOLU", d / "test.db"),
            patch.object(ajan_api, "AJAN_ANAHTAR_YOLU", self.anahtar_yolu),
            patch("tahta_kaydi.tahtalari_yukle", return_value=TAHTALAR),
        ):
            yama.start()
            self.addCleanup(yama.stop)
        ty._SON_ISTEK.clear()
        db.semayi_kur()

    def _hdr(self, **ek):
        return {"X-Farabi-Ajan-Key": ANAHTAR, **ek}

    def _denetim(self):
        conn = db.baglanti()
        try:
            return [dict(r) for r in conn.execute("SELECT * FROM uzaktan_denetim")]
        finally:
            conn.close()


class TestDogrulama(_Temel):
    def test_yerel_olmayan_403(self):
        with self.assertRaises(HTTPException) as c:
            ajan_api._ajan_dogrula(_istek(istemci=("10.1.1.1", 1), basliklar=self._hdr()))
        self.assertEqual(c.exception.status_code, 403)

    def test_ipv6_loopback_kabul(self):
        ajan_api._ajan_dogrula(_istek(istemci=("::1", 1), basliklar=self._hdr()))

    def test_anahtar_yok_veya_yanlis_401(self):
        for h in ({}, {"X-Farabi-Ajan-Key": "yanlis"}):
            with self.subTest(h=h), self.assertRaises(HTTPException) as c:
                ajan_api._ajan_dogrula(_istek(basliklar=h))
            self.assertEqual(c.exception.status_code, 401)

    def test_dosya_yok_503(self):
        self.anahtar_yolu.unlink()
        with self.assertRaises(HTTPException) as c:
            ajan_api._ajan_dogrula(_istek(basliklar=self._hdr()))
        self.assertEqual(c.exception.status_code, 503)

    def test_bozuk_dosya_503(self):
        self.anahtar_yolu.write_text("{bozuk")
        with self.assertRaises(HTTPException) as c:
            ajan_api._ajan_dogrula(_istek(basliklar=self._hdr()))
        self.assertEqual(c.exception.status_code, 503)

    def test_gecerli_cerez_tek_basina_yetmez(self):
        conn = db.baglanti()
        token = __import__("auth").oturum_olustur(conn)
        conn.close()
        with self.assertRaises(HTTPException) as c:
            ajan_api._ajan_dogrula(_istek(cerez=token))
        self.assertEqual(c.exception.status_code, 401)

    def test_gecerli_anahtar_gecer(self):
        ajan_api._ajan_dogrula(_istek(basliklar=self._hdr()))

    def test_uclar_dogrulamayi_cagirir(self):
        req = _istek(basliklar={}, govde={"eylem": "web_ac", "tahtalar": ["9-A"]})
        with self.assertRaises(HTTPException) as c:
            asyncio.run(ajan_api.eylem(req))
        self.assertEqual(c.exception.status_code, 401)
        with self.assertRaises(HTTPException):
            asyncio.run(ajan_api.yeniden_baslat(req))
        with self.assertRaises(HTTPException):
            asyncio.run(ajan_api.tahtalar(req))


class TestTahtalar(_Temel):
    def test_canli0_yalniz_ad(self):
        yanit = asyncio.run(ajan_api.tahtalar(_istek(basliklar=self._hdr()), canli=0))
        self.assertEqual(json.loads(yanit.body), {"tahtalar": [{"ad": "9-A"}, {"ad": "9-B"}, {"ad": "10-A"}]})

    def test_canli1_sizinti_yok(self):
        durumlar = [{**t, "ulasilabilir": True, "oturum": "acik", "yoklama": True,
                     "chrome": False, "karartildi": False} for t in TAHTALAR]
        with patch("uzaktan_yonetim.tum_durumlar", new_callable=AsyncMock, return_value=durumlar):
            yanit = asyncio.run(ajan_api.tahtalar(_istek(basliklar=self._hdr()), canli=1))
        veri = json.loads(yanit.body)
        self.assertEqual(set(veri["tahtalar"][0]),
                         {"ad", "ulasilabilir", "oturum", "yoklama", "chrome", "karartildi"})
        govde = yanit.body.decode()
        for yasak in ("ip", "kullanici", "admin"):
            self.assertNotIn(f'"{yasak}"', govde)
        self.assertIsNone(IP_RE.search(govde))


class TestSistem(_Temel):
    def test_ozet_guvenli(self):
        ham = {
            "cpu": {"sicaklik_c": 55, "fanlar": []}, "cpu_kullanim_yuzde": 12,
            "gpu": [{"index": 0, "ad": "RTX", "sicaklik_c": 60, "kullanim_yuzde": 5,
                     "bellek_kullanim_mb": 100, "bellek_toplam_mb": 1000, "fan_yuzde": 30}],
            "bellek": {"yuzde": 40, "toplam_gb": 64}, "disk": {"yuzde": 50},
            "servisler": [{"birim": "ollama", "etiket": "Ollama", "durum": "active",
                           "aktif": True, "port": 11434, "pid": 5,
                           "http": {"durum": "up", "ms": 3, "hata": "http://127.0.0.1:11434 refused"}}],
            "uzak_servisler": [{"adres": "192.168.1.5:80"}],
        }
        with patch("sistem_durumu.durum_topla", new_callable=AsyncMock, return_value=ham):
            yanit = asyncio.run(ajan_api.sistem(_istek(basliklar=self._hdr())))
        govde = yanit.body.decode()
        self.assertIsNone(IP_RE.search(govde))
        self.assertNotIn("11434", govde)
        self.assertNotIn("refused", govde)
        veri = json.loads(govde)
        self.assertEqual(veri["servisler"], [{"ad": "Ollama", "durum": "active", "ms": 3}])
        self.assertEqual(veri["bellek_yuzde"], 40)
        self.assertEqual(veri["gpu"][0]["bellek_yuzde"], 10)


class TestYoklama(_Temel):
    def _ekle(self):
        conn = db.baglanti()
        for sinif in ("9-A", "9-B"):
            conn.execute(
                "INSERT INTO yoklama_onbellek (tarih, sinif, ders_no, durum, yok_isimleri, izinli_isimleri) "
                "VALUES ('2026-09-28', ?, 1, 'alindi', '[]', '[]')", (sinif,))
        conn.commit()
        conn.close()

    def test_filtre_ve_dogrulama(self):
        self._ekle()
        r = _istek(basliklar=self._hdr())
        tum = json.loads(asyncio.run(ajan_api.yoklama(r, tarih="2026-09-28")).body)
        self.assertEqual(len(tum["satirlar"]), 2)
        tek = json.loads(asyncio.run(ajan_api.yoklama(r, tarih="2026-09-28", sinif="9-A")).body)
        self.assertEqual([s["sinif"] for s in tek["satirlar"]], ["9-A"])
        for kw in ({"tarih": "bozuk"}, {"tarih": "2026-09-28", "sinif": "9 A;rm"}):
            with self.subTest(kw=kw), self.assertRaises(HTTPException) as c:
                asyncio.run(ajan_api.yoklama(r, **kw))
            self.assertEqual(c.exception.status_code, 400)


class TestDurumSatirlari(_Temel):
    def test_api_durum_ile_ayni(self):
        conn = db.baglanti()
        conn.execute(
            "INSERT INTO yoklama_onbellek (tarih, sinif, ders_no, durum, yok_isimleri, izinli_isimleri) "
            "VALUES ('2026-09-28', '9-A', 1, 'alindi', '[\"A\"]', '[]')")
        conn.commit()
        conn.close()
        req = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("1.1.1.1", 1)})
        with patch.object(app, "_oturum_gerekli", return_value=True):
            yanit = asyncio.run(app.api_durum(req, tarih="2026-09-28"))
        conn = db.baglanti()
        satirlar = app._durum_satirlari(conn, __import__("datetime").date(2026, 9, 28))
        conn.close()
        self.assertEqual(json.loads(yanit.body), {"tarih": "2026-09-28", "satirlar": satirlar})
        self.assertIn("ders_kisa_adi", satirlar[0])


class TestEylem(_Temel):
    def _cagir(self, govde, **hdr):
        return asyncio.run(ajan_api.eylem(_istek(basliklar=self._hdr(**hdr), govde=govde)))

    def test_bilinmeyen_tahta_400_ssh_yok(self):
        with patch("ssh_istemci.komut_calistir", new_callable=AsyncMock) as k:
            with self.assertRaises(HTTPException) as c:
                self._cagir({"eylem": "chrome_kapat", "tahtalar": ["9-A", "zzz"]})
        k.assert_not_called()
        self.assertEqual(c.exception.status_code, 400)
        self.assertEqual(c.exception.detail["bilinmeyen"], ["zzz"])
        self.assertEqual(c.exception.detail["gecerli"], ["9-A", "9-B", "10-A"])

    def test_gecersiz_eylem_ve_bos_liste_400(self):
        for govde in ({"eylem": "duvar_kagidi", "tahtalar": ["9-A"]},
                      {"eylem": "chrome_kapat", "tahtalar": []},
                      {"eylem": "chrome_kapat"}):
            with self.subTest(govde=govde), self.assertRaises(HTTPException) as c:
                self._cagir(govde)
            self.assertEqual(c.exception.status_code, 400)

    def test_basarili_sizinti_yok_ve_denetim(self):
        with patch("ssh_istemci.komut_calistir", new_callable=AsyncMock, return_value=_ok()):
            yanit = self._cagir({"eylem": "chrome_kapat", "tahtalar": ["9-A", "9-B"]},
                                **{"X-Farabi-Kaynak": "kullanici-ali"})
        govde = yanit.body.decode()
        veri = json.loads(govde)
        self.assertEqual(veri["sonuclar"], [
            {"tahta": "9-A", "basarili": True, "sebep": "tamam"},
            {"tahta": "9-B", "basarili": True, "sebep": "tamam"}])
        self.assertIsNone(IP_RE.search(govde))
        for yasak in ('"ip"', '"kullanici"', '"admin"', "detay"):
            self.assertNotIn(yasak, govde)
        s = self._denetim()
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["eylem"], "ajan:chrome_kapat")
        self.assertEqual(s[0]["kaynak"], "kullanici-ali")
        self.assertEqual(s[0]["sonuc"], "9-A:ok,9-B:ok")

    def test_kaynak_varsayilan_ajan_ve_kisaltma(self):
        with patch("ssh_istemci.komut_calistir", new_callable=AsyncMock, return_value=_ok()):
            self._cagir({"eylem": "ekran_kaldir", "tahtalar": ["9-A"]})
            self._cagir({"eylem": "ekran_kaldir", "tahtalar": ["9-A"]}, **{"X-Farabi-Kaynak": "x" * 500})
        s = self._denetim()
        self.assertEqual(s[0]["kaynak"], "ajan")
        self.assertEqual(len(s[1]["kaynak"]), 120)

    def test_hata_sebepleri(self):
        durumlar = {
            "zaman_asimi": _yok(zaman_asimi=True, stderr=b"zaman_asimi"),
            "ulasilamadi": _yok(255, b"ssh: connect to host 10.9.9.1 port 22: Connection timed out"),
            "hata": _yok(1, b"bir sey 10.9.9.1 oldu"),
        }
        for beklenen, sonuc in durumlar.items():
            with self.subTest(beklenen=beklenen), \
                 patch("ssh_istemci.komut_calistir", new_callable=AsyncMock, return_value=sonuc):
                yanit = self._cagir({"eylem": "chrome_kapat", "tahtalar": ["9-A"]})
                r = json.loads(yanit.body)["sonuclar"][0]
                self.assertEqual((r["basarili"], r["sebep"]), (False, beklenen))
                self.assertIsNone(IP_RE.search(yanit.body.decode()))

    def test_oturum_yok(self):
        with patch("ssh_istemci.x_ortamini_kesfet", new_callable=AsyncMock, return_value=None):
            yanit = self._cagir({"eylem": "ekran_karart", "tahtalar": ["9-A"]})
        self.assertEqual(json.loads(yanit.body)["sonuclar"][0]["sebep"], "oturum_yok")

    def test_istisna_hata_ve_denetim(self):
        async def sahte(ip, kul, komut, **kw):
            if ip == "10.9.9.2":
                raise RuntimeError("gizli")
            return _ok()
        with patch("ssh_istemci.komut_calistir", side_effect=sahte):
            yanit = self._cagir({"eylem": "chrome_kapat", "tahtalar": ["9-A", "9-B"]})
        self.assertEqual(yanit.status_code, 200)
        r = {x["tahta"]: x for x in json.loads(yanit.body)["sonuclar"]}
        self.assertEqual(r["9-B"]["sebep"], "hata")
        self.assertTrue(r["9-A"]["basarili"])
        self.assertEqual(self._denetim()[0]["sonuc"], "9-A:ok,9-B:hata")

    def test_eylemler_haritasi(self):
        self.assertEqual(set(uzaktan_yonetim.EYLEMLER), {
            "yoklama_ac", "yoklama_kapat", "web_ac", "chrome_kapat", "ekran_karart", "ekran_kaldir"})


class TestDersSaati(unittest.TestCase):
    def _t(self, y, a, g, s, d):
        return datetime(y, a, g, s, d, tzinfo=zil.ISTANBUL)

    def test_durumlar(self):
        pzt = (2026, 10, 5)
        self.assertTrue(ty.ders_saatinde_mi(self._t(*pzt, 9, 0)))      # ders içi
        self.assertTrue(ty.ders_saatinde_mi(self._t(*pzt, 8, 55)))     # teneffüs
        self.assertTrue(ty.ders_saatinde_mi(self._t(*pzt, 12, 30)))    # öğle arası (ilk-son arası)
        self.assertFalse(ty.ders_saatinde_mi(self._t(*pzt, 7, 0)))     # öncesi
        self.assertFalse(ty.ders_saatinde_mi(self._t(*pzt, 16, 0)))    # sonrası
        self.assertFalse(ty.ders_saatinde_mi(self._t(2026, 10, 10, 9, 0)))  # cumartesi

    def test_utc_gelen_saat_istanbula_cevrilir(self):
        from datetime import timezone
        # 06:00 UTC = 09:00 İstanbul → ders
        self.assertTrue(ty.ders_saatinde_mi(datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc)))
        # 14:00 UTC = 17:00 İstanbul → ders değil
        self.assertFalse(ty.ders_saatinde_mi(datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc)))


class TestYenidenBaslatTek(_Temel):
    def _tek(self, t, sonuclar):
        k = AsyncMock(side_effect=sonuclar)
        with patch("ssh_istemci.komut_calistir", k):
            return asyncio.run(ty.yeniden_baslat_tek(t)), k

    def test_admin_yok_izin_yok_ssh_yok(self):
        r, k = self._tek(TAHTALAR[2], [])
        k.assert_not_called()
        self.assertEqual((r["basarili"], r["sebep"]), (False, "izin_yok"))

    def test_sudo_l_basarisiz_reboot_cagrilmaz(self):
        r, k = self._tek(TAHTALAR[1], [_yok(1, b"sudo: a password is required")])
        self.assertEqual(k.await_count, 1)
        self.assertIn("-l", k.await_args.args[2])
        self.assertEqual((r["basarili"], r["sebep"]), (False, "izin_yok"))

    def test_sudo_l_ulasilamadi_ve_zaman_asimi(self):
        r, _ = self._tek(TAHTALAR[1], [_yok(255, b"ssh: connect refused")])
        self.assertEqual(r["sebep"], "ulasilamadi")
        ty._SON_ISTEK.clear()
        r, _ = self._tek(TAHTALAR[1], [_yok(zaman_asimi=True)])
        self.assertEqual(r["sebep"], "zaman_asimi")

    def test_basarili_komut_birebir(self):
        r, k = self._tek(TAHTALAR[1], [_ok(), _ok()])
        self.assertEqual(r, {"tahta": "9-B", "basarili": True, "sebep": "tamam"})
        self.assertEqual(k.await_args_list[0].args[:3], ("10.9.9.2", "etapadmin", "sudo -n -l /usr/bin/systemctl reboot"))
        self.assertEqual(k.await_args_list[1].args[:3], ("10.9.9.2", "etapadmin", "sudo -n /usr/bin/systemctl reboot"))

    def test_cikis_255_basarili(self):
        r, _ = self._tek(TAHTALAR[1], [_ok(), _yok(255, b"Connection to x closed by remote host.")])
        self.assertEqual((r["basarili"], r["sebep"]), (True, "tamam"))
        self.assertNotIn("x closed", json.dumps(r))

    def test_reboot_diger_hata(self):
        r, _ = self._tek(TAHTALAR[1], [_ok(), _yok(1, b"boom")])
        self.assertEqual((r["basarili"], r["sebep"]), (False, "hata"))

    def test_bekleme_ikinci_cagri_ssh_yapmaz(self):
        self._tek(TAHTALAR[1], [_ok(), _ok()])
        r, k = self._tek(TAHTALAR[1], [])
        k.assert_not_called()
        self.assertEqual((r["basarili"], r["sebep"]), (False, "bekleme"))

    def test_eszamanli_iki_istek_tek_reboot(self):
        komutlar = []

        async def sahte(ip, kul, komut, **kw):
            komutlar.append(komut)
            await asyncio.sleep(0.01)
            return _ok()

        async def ikili():
            return await asyncio.gather(ty.yeniden_baslat_tek(TAHTALAR[1]), ty.yeniden_baslat_tek(TAHTALAR[1]))

        with patch("ssh_istemci.komut_calistir", side_effect=sahte):
            r = asyncio.run(ikili())
        self.assertEqual(sorted(x["sebep"] for x in r), ["bekleme", "tamam"])
        self.assertEqual([k for k in komutlar if k == "sudo -n /usr/bin/systemctl reboot"].__len__(), 1)

    def test_basarisiz_onkontrol_bekleme_baslatmaz(self):
        self._tek(TAHTALAR[1], [_yok(1, b"x")])
        self.assertNotIn("9-B", ty._SON_ISTEK)
        r, _ = self._tek(TAHTALAR[1], [_ok(), _ok()])
        self.assertEqual(r["sebep"], "tamam")

    def test_bekleme_suresi_dolunca_tekrar_olur(self):
        with patch("tahta_yeniden_baslat.time.monotonic", return_value=1000.0):
            self._tek(TAHTALAR[1], [_ok(), _ok()])
        with patch("tahta_yeniden_baslat.time.monotonic", return_value=1121.0):
            r, _ = self._tek(TAHTALAR[1], [_ok(), _ok()])
        self.assertEqual(r["sebep"], "tamam")

    def test_9a_uyari(self):
        r, _ = self._tek(TAHTALAR[0], [_ok(), _ok()])
        self.assertIn("giriş ekranında", r["uyari"])
        r, _ = self._tek(TAHTALAR[1], [_ok(), _ok()])
        self.assertNotIn("uyari", r)


class TestYenidenBaslatRoute(_Temel):
    def _cagir(self, govde, **hdr):
        return asyncio.run(ajan_api.yeniden_baslat(_istek(basliklar=self._hdr(**hdr), govde=govde)))

    def test_ders_saatinde_409_ssh_yok(self):
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=True), \
             patch("ssh_istemci.komut_calistir", new_callable=AsyncMock) as k:
            yanit = self._cagir({"tahtalar": ["9-B"]})
        k.assert_not_called()
        self.assertEqual(yanit.status_code, 409)
        self.assertEqual(json.loads(yanit.body)["durum"], "ders_saati")
        satirlar = self._denetim()
        self.assertEqual(len(satirlar), 1)
        self.assertEqual(satirlar[0]["eylem"], "ajan:yeniden_baslat")
        self.assertEqual(satirlar[0]["kaynak"], "ajan")
        self.assertEqual(satirlar[0]["sonuc"], "9-B:ders_saati")

    def test_400_denetim_yazmaz(self):
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=True):
            with self.assertRaises(HTTPException):
                self._cagir({"tahtalar": ["yok"]})
        self.assertEqual(self._denetim(), [])

    def test_istisna_hata_ve_denetim(self):
        async def sahte(ip, kul, komut, **kw):
            if ip == "10.9.9.2":
                raise RuntimeError("gizli 10.9.9.2")
            return _ok()
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=False), \
             patch("ssh_istemci.komut_calistir", side_effect=sahte):
            yanit = self._cagir({"tahtalar": ["9-A", "9-B"]})
        self.assertEqual(yanit.status_code, 200)
        r = {x["tahta"]: x for x in json.loads(yanit.body)["sonuclar"]}
        self.assertEqual(r["9-B"], {"tahta": "9-B", "basarili": False, "sebep": "hata"})
        self.assertTrue(r["9-A"]["basarili"])
        self.assertNotIn("gizli", yanit.body.decode())
        self.assertEqual(self._denetim()[0]["sonuc"], "9-A:ok,9-B:hata")

    def test_bilinmeyen_tahta_400(self):
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=False), \
             patch("ssh_istemci.komut_calistir", new_callable=AsyncMock) as k:
            with self.assertRaises(HTTPException) as c:
                self._cagir({"tahtalar": ["9-B", "yok"]})
        k.assert_not_called()
        self.assertEqual(c.exception.status_code, 400)

    def test_ders_disi_calisir_ve_denetim(self):
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=False), \
             patch("ssh_istemci.komut_calistir", new_callable=AsyncMock, return_value=_ok()):
            yanit = self._cagir({"tahtalar": ["9-B", "10-A"]}, **{"X-Farabi-Kaynak": "ali"})
        veri = json.loads(yanit.body)
        self.assertEqual([(r["tahta"], r["sebep"]) for r in veri["sonuclar"]],
                         [("9-B", "tamam"), ("10-A", "izin_yok")])
        self.assertIsNone(IP_RE.search(yanit.body.decode()))
        s = self._denetim()
        self.assertEqual((s[0]["eylem"], s[0]["kaynak"]), ("ajan:yeniden_baslat", "ali"))


class TestSema(unittest.TestCase):
    def test_iki_kez_calisir_kaynak_var(self):
        with tempfile.TemporaryDirectory() as d, patch.object(db, "DB_YOLU", Path(d) / "t.db"):
            db.semayi_kur()
            db.semayi_kur()
            conn = db.baglanti()
            sutunlar = [r["name"] for r in conn.execute("PRAGMA table_info(uzaktan_denetim)")]
            conn.close()
        self.assertEqual(sutunlar.count("kaynak"), 1)

    def test_eski_tabloya_eklenir(self):
        with tempfile.TemporaryDirectory() as d, patch.object(db, "DB_YOLU", Path(d) / "t.db"):
            conn = db.baglanti()
            conn.execute("CREATE TABLE uzaktan_denetim (id INTEGER PRIMARY KEY AUTOINCREMENT, zaman TEXT NOT NULL, "
                         "istemci_ip TEXT, eylem TEXT NOT NULL, tahtalar TEXT NOT NULL, sonuc TEXT NOT NULL)")
            conn.commit()
            conn.close()
            db.semayi_kur()
            conn = db.baglanti()
            sutunlar = [r["name"] for r in conn.execute("PRAGMA table_info(uzaktan_denetim)")]
            conn.close()
        self.assertIn("kaynak", sutunlar)


if __name__ == "__main__":
    unittest.main()
