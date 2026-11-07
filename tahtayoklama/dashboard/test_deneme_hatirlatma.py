import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db
import deneme_hatirlatma as dh
import duyuru
import zil

ZIL = {
    "dersler": [{"no": 1, "baslangic": "08:10", "bitis": "08:50"},
                {"no": 2, "baslangic": "09:00", "bitis": "09:40"}],
    "ogle_arasi": {"baslangic": "12:10", "bitis": "13:30"},
    "ders_gunleri": [1, 2, 3, 4, 5],
}
DENEME = {"baslik": "MEBİ 3. YKS Denemesi", "tarih": "2026-11-09", "bitis": "2026-11-15",
          "duzeyler": "11,12", "aciklama": "mebi.eba.gov.tr", "durum": "9–15 Kasım · 3 gün kaldı"}


class TestDenemeHatirlatma(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        gecici = Path(self.tmp.name)
        self.yamalar = [
            mock.patch.object(db, "DB_YOLU", gecici / "t.db"),
            mock.patch.object(duyuru, "SES_DIZINI", gecici / "ses"),
            mock.patch.object(zil, "_zil_yukle", lambda: ZIL),
        ]
        for y in self.yamalar:
            y.start()
        db.semayi_kur()
        self.conn = db.baglanti()
        self.conn.executemany("INSERT INTO siniflar (ad, aktif) VALUES (?, 1)",
                              [("9-A",), ("10-A",), ("11-A",), ("11-B",), ("12-A",)])
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        for y in self.yamalar:
            y.stop()
        self.tmp.cleanup()

    def test_yuvalar_ilk_teneffus_ve_ogle(self):
        pzt = (2026, 11, 9)
        self.assertTrue(dh.yuvada_mi(datetime(*pzt, 8, 50, tzinfo=zil.ISTANBUL)))
        self.assertTrue(dh.yuvada_mi(datetime(*pzt, 8, 54, tzinfo=zil.ISTANBUL)))
        self.assertFalse(dh.yuvada_mi(datetime(*pzt, 8, 55, tzinfo=zil.ISTANBUL)))
        self.assertFalse(dh.yuvada_mi(datetime(*pzt, 9, 40, tzinfo=zil.ISTANBUL)))  # 2. teneffüs değil
        self.assertTrue(dh.yuvada_mi(datetime(*pzt, 12, 12, tzinfo=zil.ISTANBUL)))
        self.assertFalse(dh.yuvada_mi(datetime(2026, 11, 8, 8, 50, tzinfo=zil.ISTANBUL)))  # pazar

    def test_yalniz_11_12_ve_tekrar_yok(self):
        self.assertEqual(dh.gonder(self.conn, [DENEME]), 3)
        hedefler = [r["hedef"] for r in self.conn.execute("SELECT hedef FROM duyuru ORDER BY hedef")]
        self.assertEqual(hedefler, ["11-A", "11-B", "12-A"])
        satir = self.conn.execute("SELECT mesaj, tip, sesli_oku FROM duyuru LIMIT 1").fetchone()
        self.assertEqual(tuple(satir), (
            "MEBİ 3. YKS Denemesi: 9–15 Kasım · 3 gün kaldı — mebi.eba.gov.tr", "bilgi", 0))
        self.assertEqual(dh.gonder(self.conn, [DENEME]), 0)  # aynı yuvada / restart sonrası

    def test_duzeysiz_deneme_tum_okula(self):
        self.assertEqual(dh.gonder(self.conn, [dict(DENEME, duzeyler="")]), 1)
        self.assertEqual(self.conn.execute("SELECT hedef FROM duyuru").fetchone()[0], duyuru.TUM_OKUL)

    def test_okul_ucu_yoksa_dongu_dusmez(self):
        import asyncio

        async def calistir():
            with mock.patch.object(dh, "yuvada_mi", return_value=True), \
                 mock.patch.object(dh, "denemeleri_cek", side_effect=OSError("kapalı")), \
                 mock.patch.object(dh.asyncio, "sleep", side_effect=asyncio.CancelledError), \
                 self.assertRaises(asyncio.CancelledError):
                await dh.dongu()

        asyncio.run(calistir())
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM duyuru").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
