"""auth.oturum_gecerli_mi: oturum kontrolü yazma kilidini açık bırakmamalı (2026-10-23).

Taze oturumda UPDATE 0 satıra dokunup commit edilmeyince işlem açık kalıyordu; aynı
bağlantıyla SSH bekleyen /api/yenile ~50 sn boyunca tüm yazmaları "database is locked"
ile düşürdü (/veli-mesajlari, tahta nabızları, acil durum)."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import auth


class TestOturumKilidi(unittest.TestCase):
    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.yol = Path(self.dizin.name) / "t.db"
        conn = sqlite3.connect(self.yol)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE oturumlar (token TEXT PRIMARY KEY, son_gorulme TEXT)")
        conn.execute("INSERT INTO oturumlar VALUES ('t', datetime('now'))")  # taze: UPDATE 0 satır
        conn.commit()
        conn.close()

    def tearDown(self):
        self.dizin.cleanup()

    def test_taze_oturum_kilit_birakmaz(self):
        a = sqlite3.connect(self.yol)
        b = sqlite3.connect(self.yol, timeout=0)
        try:
            self.assertTrue(auth.oturum_gecerli_mi(a, "t"))
            self.assertFalse(a.in_transaction)
            b.execute("UPDATE oturumlar SET son_gorulme = son_gorulme")  # kilitliyse OperationalError
            b.commit()
        finally:
            a.close()
            b.close()


if __name__ == "__main__":
    unittest.main()
