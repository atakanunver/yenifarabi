import unittest

from tools.ders_gorsel_olc import (
    cpu_yuzdesi,
    esik_karari,
    log_parse,
    rss_parse,
    stat_tick,
)


class OlcumTestleri(unittest.TestCase):
    def test_cpu_tek_cekirdek_ve_gecersiz_aralik(self):
        self.assertEqual(cpu_yuzdesi(250, 1, 100), 250)
        with self.assertRaises(ValueError):
            cpu_yuzdesi(1, 0, 100)

    def test_sahte_proc(self):
        self.assertEqual(rss_parse('Name:\tservis\nVmRSS:\t 2048 kB\n'), 2)
        with self.assertRaises(ValueError):
            rss_parse('Name:\tservis\n')
        self.assertEqual(stat_tick('42 (ad (deneme)) S ' + ' '.join(map(str, range(1, 20)))), 23)

    def test_log_ve_eksik_veri(self):
        self.assertEqual(log_parse('grab_p95=12.3 karsilastirma_p95=4.5\ngrab_p95=41'),
                         {'grab_p95': 41.0, 'karsilastirma_p95': 4.5})
        self.assertEqual(log_parse('baska_grab_p95=99'),
                         {'grab_p95': None, 'karsilastirma_p95': None})

    def test_esik(self):
        self.assertTrue(esik_karari(5, 5))
        self.assertFalse(esik_karari(5.1, 5))
        self.assertIsNone(esik_karari(None, 5))


if __name__ == '__main__':
    unittest.main()
