"""tahta_istemci.py sağlık ölçümü (2026-10-08) — sahte /proc ve /sys ağacıyla."""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tahta_istemci as ti  # noqa: E402


def yaz(kok: Path, yol: str, metin: str) -> None:
    p = kok / yol.lstrip("/")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(metin)


def sahte_sistem(kok: Path, devnum: str | None = "5") -> None:
    yaz(kok, "/proc/meminfo", "MemTotal: 3937280 kB\nMemAvailable: 1048576 kB\n"
        "SwapTotal: 1967100 kB\nSwapFree: 1443836 kB\n")
    yaz(kok, "/proc/loadavg", "1.52 0.90 0.40 2/400 1234\n")
    yaz(kok, "/proc/uptime", "7265.33 20000.00\n")
    yaz(kok, "/proc/vmstat", "nr_free_pages 1\noom_kill 2\npgfault 9\n")
    yaz(kok, "/proc/sys/kernel/random/boot_id", "abc-123\n")
    yaz(kok, "/sys/class/hwmon/hwmon1/temp1_input", "53000\n")
    yaz(kok, "/sys/class/hwmon/hwmon1/temp2_input", "61500\n")
    yaz(kok, "/sys/class/thermal/thermal_zone0/temp", "27800\n")
    if devnum is not None:
        yaz(kok, "/sys/bus/usb/devices/1-1.2/idVendor", "6615\n")
        yaz(kok, "/sys/bus/usb/devices/1-1.2/idProduct", "0c20\n")
        yaz(kok, "/sys/bus/usb/devices/1-1.2/devnum", devnum + "\n")
    yaz(kok, "/sys/bus/usb/devices/1-1.3/idVendor", "046d\n")
    yaz(kok, "/sys/bus/usb/devices/1-1.3/devnum", "7\n")


class TestSaglikOlcumu(unittest.TestCase):
    def test_olcumler(self):
        with TemporaryDirectory() as d:
            kok = Path(d)
            sahte_sistem(kok)
            s = ti.saglik_olc(kok, ti.DokunmatikIzci())
        self.assertEqual(s["sicaklik_c"], 61.5)          # en sıcak sensör
        self.assertEqual(s["bellek_bos_mb"], 1024)
        self.assertEqual(s["takas_mb"], 511)
        self.assertEqual(s["yuk1"], 1.52)
        self.assertEqual(s["calisma_sn"], 7265)
        self.assertEqual(s["oom_sayisi"], 2)
        self.assertEqual(s["acilis_id"], "abc-123")
        self.assertTrue(s["dokunmatik_var"])
        self.assertEqual(s["dokunmatik_kopma"], 0)

    def test_eksik_dosyalar_none_doner_patlamaz(self):
        with TemporaryDirectory() as d:
            s = ti.saglik_olc(Path(d), ti.DokunmatikIzci())
        self.assertIsNone(s["sicaklik_c"])
        self.assertIsNone(s["bellek_bos_mb"])
        self.assertIsNone(s["oom_sayisi"])
        self.assertFalse(s["dokunmatik_var"])

    def test_dokunmatik_kopma_sayilir(self):
        izci = ti.DokunmatikIzci()
        with TemporaryDirectory() as d:
            kok = Path(d)
            sahte_sistem(kok, devnum="5")
            ti.saglik_olc(kok, izci)
            # USB'den kopup yeniden tanındı: çekirdek yeni devnum verir.
            yaz(kok, "/sys/bus/usb/devices/1-1.2/devnum", "9\n")
            self.assertEqual(ti.saglik_olc(kok, izci)["dokunmatik_kopma"], 1)
            # O an kopuk: aygıt yok.
            for f in ("idVendor", "idProduct", "devnum"):
                (kok / "sys/bus/usb/devices/1-1.2" / f).unlink()
            s = ti.saglik_olc(kok, izci)
            self.assertFalse(s["dokunmatik_var"])
            self.assertEqual(s["dokunmatik_kopma"], 2)
            # Geri geldi: aynı kopma ikinci kez sayılmaz.
            sahte_sistem(kok, devnum="11")
            self.assertEqual(ti.saglik_olc(kok, izci)["dokunmatik_kopma"], 2)

    def test_nabiz_govdesi_sagligi_tasir(self):
        gonderilen = {}

        def sahte_istek(ayar, yontem, yol, govde=None):
            gonderilen.update(govde)
            return 200, {}, b""

        eski = ti.istek
        ti.istek = sahte_istek
        try:
            ti.nabiz_gonder({"sunucu": "x", "token": "t"})
        finally:
            ti.istek = eski
        self.assertIn("saglik", gonderilen)
        self.assertIn("sicaklik_c", gonderilen["saglik"])


if __name__ == "__main__":
    unittest.main()
