"""scripts/farabi-zamanlayici: beyaz liste, ifade doğrulama ve üretilen dosyalar (sahte systemctl/systemd-analyze ile)."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

BETIK = Path(__file__).parent / "scripts" / "farabi-zamanlayici"


class TestFarabiZamanlayici(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        kok = Path(self._tmp.name)
        self.kayit = kok / "cagri.txt"
        self.dizin = kok / "systemd"
        self.dizin.mkdir()
        sahte = kok / "systemctl"
        sahte.write_text(f'#!/bin/bash\necho "$@" >> {self.kayit}\n[[ "$1" == "is-active" ]] && exit 0\nexit 0\n')
        sahte.chmod(0o755)
        analiz = kok / "analyze"
        # "bozuk" içeren ifade geçersiz sayılır
        analiz.write_text('#!/bin/bash\n[[ "$*" == *bozuk* ]] && exit 1\nexit 0\n')
        analiz.chmod(0o755)
        self.ortam = {**os.environ, "FARABI_ZAMANLAYICI_SYSTEMCTL": str(sahte),
                      "FARABI_ZAMANLAYICI_ANALYZE": str(analiz),
                      "FARABI_ZAMANLAYICI_DIZIN": str(self.dizin),
                      "FARABI_ZAMANLAYICI_DASHBOARD": "/dash"}

    def _kos(self, *arg):
        return subprocess.run(["bash", str(BETIK), *arg], env=self.ortam, capture_output=True, text=True)

    def _cagrilar(self):
        return self.kayit.read_text().splitlines() if self.kayit.exists() else []

    def test_ac_kapat_calistir(self):
        self.assertEqual(self._kos("ac", "soru-havuzu-uret").returncode, 0)
        self.assertEqual(self._kos("kapat", "soru-havuzu-uret").returncode, 0)
        self.assertEqual(self._kos("calistir", "farabi-tahta-karart-haftaici").returncode, 0)
        self.assertEqual(self._cagrilar(), [
            "enable --now soru-havuzu-uret.timer",
            "disable --now soru-havuzu-uret.timer",
            "start --no-block farabi-tahta-karart.service",
        ])

    def test_liste_disi_birim_reddedilir(self):
        for birim in ("apt-daily", "sysstat-collect", "farabi-api", "x;rm", "../x", "farabi-gorev-", "farabi-gorev-A",
                      "farabi-gorev-a b", "farabi-gorev-" + "a" * 31, ""):
            self.assertEqual(self._kos("kapat", birim).returncode, 2, birim)
        self.assertEqual(self._cagrilar(), [])

    def test_bilinmeyen_eylem_ve_fazla_arguman(self):
        self.assertEqual(self._kos("yeniden-baslat", "soru-havuzu-uret").returncode, 2)
        self.assertEqual(self._kos("ac", "soru-havuzu-uret", "fazla").returncode, 2)
        self.assertEqual(self._kos("ac").returncode, 2)
        self.assertEqual(self._cagrilar(), [])

    def test_takvim_dropin_yazar_ve_yeniden_baslatir(self):
        ifade = "Mon..Fri *-*-* 21:30:00 Europe/Istanbul"
        r = self._kos("takvim", "farabi-tahta-karart-haftaici", ifade)
        self.assertEqual(r.returncode, 0, r.stderr)
        dosya = self.dizin / "farabi-tahta-karart-haftaici.timer.d" / "zaman.conf"
        self.assertEqual(dosya.read_text(), f"[Timer]\nOnCalendar=\nOnCalendar={ifade}\n")
        self.assertIn("daemon-reload", self._cagrilar())
        self.assertIn("restart farabi-tahta-karart-haftaici.timer", self._cagrilar())

    def test_takvim_gecersiz_ifadeler_reddedilir(self):
        for ifade in ("bozuk 21:00", "", "-h", "$(rm -rf /)", "21:00; reboot", "a`b`", "x\ny", "a" * 101, "21:00'"):
            r = self._kos("takvim", "soru-havuzu-uret", ifade)
            self.assertEqual(r.returncode, 2, repr(ifade))
        self.assertEqual(self._cagrilar(), [])
        self.assertEqual(list(self.dizin.iterdir()), [])

    def test_takvim_sifirla(self):
        self._kos("takvim", "soru-havuzu-uret", "*-*-* 08:00:00")
        self.assertEqual(self._kos("takvim-sifirla", "soru-havuzu-uret").returncode, 0)
        self.assertFalse((self.dizin / "soru-havuzu-uret.timer.d").exists())

    def test_olustur_dosyalari_ve_etkinlestirme(self):
        r = self._kos("olustur", "gece-karart", "ekran_karart", "9-A,9-B", "Mon..Fri *-*-* 21:00:00 Europe/Istanbul")
        self.assertEqual(r.returncode, 0, r.stderr)
        servis = (self.dizin / "farabi-gorev-gece-karart.service").read_text()
        self.assertIn("ExecStart=/dash/venv/bin/python scripts/tahta_eylem_zamanli.py ekran_karart 9-A,9-B", servis)
        self.assertIn("User=ata", servis)
        zamanlayici = (self.dizin / "farabi-gorev-gece-karart.timer").read_text()
        self.assertIn("OnCalendar=Mon..Fri *-*-* 21:00:00 Europe/Istanbul", zamanlayici)
        self.assertIn("Persistent=false", zamanlayici)
        self.assertEqual(self._cagrilar(), ["daemon-reload", "enable --now farabi-gorev-gece-karart.timer"])
        # aynı id ikinci kez oluşturulamaz
        self.assertEqual(self._kos("olustur", "gece-karart", "ekran_karart", "hepsi", "21:00").returncode, 2)

    def test_olustur_reddedilenler(self):
        T = "Mon *-*-* 21:00:00"
        gecersiz = [
            ("a;b", "ekran_karart", "9-A", T),          # id
            ("Gece", "ekran_karart", "9-A", T),          # büyük harf
            ("ok", "reboot", "9-A", T),                  # eylem listede değil
            ("ok", "ekran_karart", "9-A;rm", T),         # tahta adında kabuk karakteri
            ("ok", "ekran_karart", "9 A", T),
            ("ok", "ekran_karart", "", T),
            ("ok", "ekran_karart", "9-A", "bozuk"),      # ifade
            ("ok", "ekran_karart", "9-A", "$(id)"),
        ]
        for arg in gecersiz:
            self.assertEqual(self._kos("olustur", *arg).returncode, 2, arg)
        self.assertEqual(self._cagrilar(), [])
        self.assertEqual(list(self.dizin.iterdir()), [])

    def test_olustur_hepsi_tahtasi(self):
        self.assertEqual(self._kos("olustur", "tum", "ekran_kaldir", "hepsi", "Sat,Sun *-*-* 17:00:00").returncode, 0)
        self.assertIn("ekran_kaldir hepsi", (self.dizin / "farabi-gorev-tum.service").read_text())

    def test_sil_yalniz_panel_gorevleri(self):
        self._kos("olustur", "gecici", "ekran_kaldir", "9-B", "*-*-* 12:00:00")
        self.kayit.write_text("")
        self.assertEqual(self._kos("sil", "gecici").returncode, 0)
        self.assertFalse((self.dizin / "farabi-gorev-gecici.timer").exists())
        self.assertFalse((self.dizin / "farabi-gorev-gecici.service").exists())
        # Farabi'nin kendi timer'ları, sistem timer'ları ve olmayan görev silinemez
        for hedef in ("soru-havuzu-uret", "farabi-tahta-karart-haftaici", "apt-daily", "yok", "../x", "a;b"):
            self.assertEqual(self._kos("sil", hedef).returncode, 2, hedef)

    def test_yonetilen_liste_modulle_ayni(self):
        # zamanlanmis_gorevler.YONETILEN ile betikteki YONETILEN birebir aynı olmalı.
        metin = BETIK.read_text()
        satir = next(s for s in metin.splitlines() if s.startswith("YONETILEN="))
        betikteki = set(satir.split('"')[1].split())
        import zamanlanmis_gorevler
        self.assertEqual(betikteki, set(zamanlanmis_gorevler.YONETILEN))


if __name__ == "__main__":
    unittest.main()
