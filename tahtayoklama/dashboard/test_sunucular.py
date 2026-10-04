"""sunucular.py birim testleri (2026-10-04, Sunucular sekmesi)."""

import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import db
import sunucular
from fastapi import HTTPException
from fastapi.requests import Request

ORNEK_DURUM = {
    "makine": "bilgehan",
    "uptime_sn": 100,
    "load": [0.1, 0.2, 0.3],
    "cpu_cekirdek": 6,
    "ram": {
        "toplam_mib": 9000,
        "kullanilan_mib": 700,
        "swap_toplam_mib": 4000,
        "swap_kullanilan_mib": 0,
    },
    "disk": {"toplam_gib": 195.8, "kullanilan_gib": 10.4, "yuzde": 5.3},
    "gpu": [],
    "ntp": {"senkron": True, "leap": "Normal"},
    "servisler": [],
    "proxy": {
        "durum": "kapali",
        "profil": False,
        "apt": False,
        "ollama": None,
        "ollama_restart_bekliyor": False,
    },
}


def _istek(
    govde: bytes = b"", cerez: str | None = None, yol: str = "/api/sunucular"
) -> Request:
    basliklar = [(b"content-type", b"application/json")]
    if cerez:
        basliklar.append((b"cookie", f"oturum={cerez}".encode()))

    async def al():
        return {"type": "http.request", "body": govde, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": yol,
        "headers": basliklar,
        "query_string": b"",
        "client": ("127.0.0.1", 1),
    }
    return Request(scope, al)


class TestAyristir(unittest.TestCase):
    def test_gecerli_json_ulasilabilir(self):
        d = sunucular.durum_ayristir(json.dumps(ORNEK_DURUM), 0, "")
        self.assertTrue(d["ulasilabilir"])
        self.assertEqual(d["makine"], "bilgehan")

    def test_son_json_satiri_alinir(self):
        cikti = "uyari satiri\n" + json.dumps(ORNEK_DURUM)
        self.assertTrue(sunucular.durum_ayristir(cikti, 0, "")["ulasilabilir"])

    def test_bozuk_cikti_hata_doner(self):
        d = sunucular.durum_ayristir(
            "", 255, "ssh: connect to host bilgehan.local port 22: No route"
        )
        self.assertFalse(d["ulasilabilir"])
        self.assertIn("No route", d["hata"])

    def test_betik_hatasi(self):
        d = sunucular.durum_ayristir('{"hata": "izin verilmeyen komut"}', 1, "")
        self.assertFalse(d["ulasilabilir"])
        self.assertEqual(d["hata"], "izin verilmeyen komut")

    def test_proxy_parolasi_sizdirilmaz(self):
        d = sunucular.durum_ayristir(
            "", 1, "proxy http://kullanici:gizliparola@10.0.0.1:8080 hatasi"
        )
        self.assertNotIn("gizliparola", json.dumps(d))


class TestKomutArgumanlari(unittest.TestCase):
    def test_yerel_sudo(self):
        self.assertEqual(
            sunucular.komut_argumanlari("farabi", "durum"),
            ["sudo", "-n", "/usr/local/sbin/okul-sunucu", "durum"],
        )

    def test_uzak_ssh_batchmode(self):
        args = sunucular.komut_argumanlari("bilgehan", "durum")
        self.assertEqual(args[0], "ssh")
        self.assertIn("BatchMode=yes", args)
        self.assertEqual(args[-2:], ["ata@bilgehan.local", "durum"])

    def test_bilinmeyen_alt_komut(self):
        with self.assertRaises(ValueError):
            sunucular.komut_argumanlari("farabi", "rm -rf /")


class TestProxyUcu(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._eski = db.DB_YOLU
        db.DB_YOLU = Path(self._tmp.name) / "test.db"
        db.semayi_kur()
        conn = db.baglanti()
        conn.execute("INSERT INTO oturumlar (token) VALUES ('gecerli')")
        conn.commit()
        conn.close()

    def tearDown(self):
        db.DB_YOLU = self._eski
        self._tmp.cleanup()

    def _cagir(self, ad, govde, cerez="gecerli"):
        istek = _istek(json.dumps(govde).encode(), cerez)
        return asyncio.run(sunucular.api_proxy(istek, ad))

    def test_sayfa_render_edilir(self):
        istek = _istek(cerez="gecerli", yol="/sunucular")
        yanit = asyncio.run(sunucular.sunucular_sayfa(istek))
        self.assertEqual(yanit.status_code, 200)
        self.assertIn(b"sunucu-listesi", yanit.body)

    def test_oturumsuz_401(self):
        with self.assertRaises(HTTPException) as c:
            self._cagir("bilgehan", {"eylem": "ac"}, cerez=None)
        self.assertEqual(c.exception.status_code, 401)

    def test_bilinmeyen_makine_404(self):
        with self.assertRaises(HTTPException) as c:
            self._cagir("zil", {"eylem": "ac"})
        self.assertEqual(c.exception.status_code, 404)

    def test_proxy_dugmesi_olmayan_makine_400(self):
        with self.assertRaises(HTTPException) as c:
            self._cagir("debian", {"eylem": "ac"})
        self.assertEqual(c.exception.status_code, 400)

    def test_gecersiz_eylem_400(self):
        with self.assertRaises(HTTPException) as c:
            self._cagir("bilgehan", {"eylem": "sil"})
        self.assertEqual(c.exception.status_code, 400)

    def test_gecerli_istek_komutu_calistirir(self):
        sahte = AsyncMock(
            return_value={**ORNEK_DURUM, "ulasilabilir": True, "mesajlar": ["tamam"]}
        )
        with patch.object(sunucular, "_calistir", sahte):
            yanit = self._cagir("bilgehan", {"eylem": "kapat"})
        sahte.assert_awaited_once_with("bilgehan", "proxy-kapat")
        govde = json.loads(yanit.body)
        self.assertTrue(govde["basarili"])
        self.assertEqual(govde["mesajlar"], ["tamam"])


class TestChatterbox(unittest.TestCase):
    def test_ulasilamazsa_hata(self):
        with patch.object(
            sunucular, "CHATTERBOX_URL", "http://127.0.0.1:9/saglik/detay"
        ):
            d = sunucular._chatterbox_oku()
        self.assertFalse(d["ulasilabilir"])


if __name__ == "__main__":
    unittest.main()
