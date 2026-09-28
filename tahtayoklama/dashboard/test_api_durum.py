"""app.py::api_durum testi (2026-09-28).

Kök neden: pano.html'in `hucreDoldur`'u yalnızca `yok_isimleri`'ne bakıp
"Tam"/"alindi_yok" kararı veriyordu, `izinli_isimleri`'ni (sunucu zaten
`/api/durum` yanıtında döndürüyordu) hiç okumuyordu — sadece izinli
öğrencisi olan bir ders panoda "Tam" görünüyordu (bkz. kök DECISIONS.md
2026-09-28). İstemci tarafı `pano.html`'de düzeltildi; bu test SUNUCU
sözleşmesinin (yanıtta `izinli_isimleri` alanının gerçekten dolu dönmesi)
kırılmadığını doğrular — istemci tarafı JS için Python testi yazılamaz."""

import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import app
import db
from fastapi.requests import Request


class TestApiDurumIzinli(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._eski_db_yolu = db.DB_YOLU
        db.DB_YOLU = Path(self._tmp.name) / "test.db"
        db.semayi_kur()

        conn = db.baglanti()
        conn.execute(
            "INSERT INTO yoklama_onbellek "
            "(tarih, sinif, ders_no, durum, yok_isimleri, izinli_isimleri) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("2026-09-28", "9-A", 1, "alindi", json.dumps([]), json.dumps(["Ali Veli"])),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        db.DB_YOLU = self._eski_db_yolu
        self._tmp.cleanup()

    def _istek(self):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/durum",
            "headers": [],
            "query_string": b"",
        }
        return Request(scope)

    def test_izinli_isimleri_yanitta_var_ve_tam_degil(self):
        async def run_test():
            with patch.object(app, "_oturum_gerekli", return_value=True):
                yanit = await app.api_durum(self._istek(), tarih="2026-09-28")
                govde = json.loads(yanit.body.decode())
                self.assertEqual(len(govde["satirlar"]), 1)
                satir = govde["satirlar"][0]
                self.assertIn("izinli_isimleri", satir)
                self.assertEqual(json.loads(satir["izinli_isimleri"]), ["Ali Veli"])
                self.assertEqual(json.loads(satir["yok_isimleri"] or "[]"), [])
                # durum alanı ham "alindi" olarak döner — "Tam"/"alindi_yok"
                # ayrımını istemci (pano.html) yok/izinli listelerine
                # bakarak yapar; sunucu bu kararı vermez.
                self.assertEqual(satir["durum"], "alindi")

        asyncio.run(run_test())

    def test_hem_yok_hem_izinli_bir_arada_donebilir(self):
        conn = db.baglanti()
        conn.execute(
            "INSERT INTO yoklama_onbellek "
            "(tarih, sinif, ders_no, durum, yok_isimleri, izinli_isimleri) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("2026-09-28", "9-A", 2, "alindi", json.dumps(["Ayşe Yılmaz"]), json.dumps(["Ali Veli"])),
        )
        conn.commit()
        conn.close()

        async def run_test():
            with patch.object(app, "_oturum_gerekli", return_value=True):
                yanit = await app.api_durum(self._istek(), tarih="2026-09-28")
                govde = json.loads(yanit.body.decode())
                satir = next(s for s in govde["satirlar"] if s["ders_no"] == 2)
                self.assertEqual(json.loads(satir["yok_isimleri"]), ["Ayşe Yılmaz"])
                self.assertEqual(json.loads(satir["izinli_isimleri"]), ["Ali Veli"])

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
