"""scripts/farabi-servis: beyaz liste + doğru systemctl çağrısı (sahte systemctl ile)."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

BETIK = Path(__file__).parent / "scripts" / "farabi-servis"


class TestFarabiServis(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.kayit = Path(self._tmp.name) / "cagri.txt"
        sahte = Path(self._tmp.name) / "systemctl"
        sahte.write_text(f'#!/bin/bash\necho "$@" >> {self.kayit}\n')
        sahte.chmod(0o755)
        sahte_run = Path(self._tmp.name) / "systemd-run"
        sahte_run.write_text(f'#!/bin/bash\necho "RUN $@" >> {self.kayit}\n')
        sahte_run.chmod(0o755)
        self.ortam = {**os.environ, "FARABI_SERVIS_SYSTEMCTL": str(sahte),
                      "FARABI_SERVIS_SYSTEMD_RUN": str(sahte_run)}

    def _kos(self, *arg):
        return subprocess.run(["bash", str(BETIK), *arg], env=self.ortam,
                              capture_output=True, text=True)

    def _cagrilar(self):
        return self.kayit.read_text().splitlines() if self.kayit.exists() else []

    def test_yeniden_baslat_servis(self):
        r = self._kos("yeniden-baslat", "farabi-api")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._cagrilar(), ["restart farabi-api.service"])

    def test_liste_disi_birim_2_ve_cagri_yok(self):
        for birim in ("ssh", "farabi-api;rm", "../x", "farabi-api.service", ""):
            r = self._kos("yeniden-baslat", birim)
            self.assertEqual(r.returncode, 2, birim)
        self.assertEqual(self._cagrilar(), [])

    def test_liste_disi_eylem_2(self):
        self.assertEqual(self._kos("sil", "farabi-api").returncode, 2)
        self.assertEqual(self._cagrilar(), [])

    def test_dashboard_durdurulamaz_yeniden_baslat_gecikmeli(self):
        self.assertEqual(self._kos("durdur", "farabi-yoklama-dashboard").returncode, 2)
        r = self._kos("yeniden-baslat", "farabi-yoklama-dashboard")
        self.assertEqual(r.returncode, 0, r.stderr)
        cagri = self._cagrilar()
        self.assertEqual(len(cagri), 1)
        # benzersiz geçici birim + --collect: ikinci tıkta / başarısız birimde "already exists" olmasın
        self.assertRegex(cagri[0], r"^RUN --on-active=2 --collect --unit=farabi-dashboard-yeniden-\d+ "
                                   r"/usr/bin/systemctl restart farabi-yoklama-dashboard\.service$")
        r2 = self._kos("yeniden-baslat", "farabi-yoklama-dashboard")
        self.assertEqual(r2.returncode, 0)
        self.assertNotEqual(self._cagrilar()[0].split()[3], self._cagrilar()[1].split()[3])

    def test_ollama_restart_beklemez(self):
        # ExecStartPost model ön-yüklemesi ~1-3 dk; beklenirse 60 sn zaman aşımı "başarısız" gösterir
        self.assertEqual(self._kos("yeniden-baslat", "ollama").returncode, 0)
        self.assertEqual(self._cagrilar(), ["restart --no-block ollama.service"])

    def test_zamanlayici_eylemleri(self):
        self._kos("zamanlayici-kapat", "soru-havuzu-uret")
        self._kos("zamanlayici-ac", "soru-havuzu-uret")
        self._kos("simdi-calistir", "soru-havuzu-uret")
        self._kos("hata-temizle", "soru-havuzu-uret")
        self.assertEqual(self._cagrilar(), [
            "disable --now soru-havuzu-uret.timer",
            "enable --now soru-havuzu-uret.timer",
            "start --no-block soru-havuzu-uret.service",
            "reset-failed soru-havuzu-uret.service",
        ])

    def test_servise_zamanlayici_eylemi_reddedilir(self):
        self.assertEqual(self._kos("zamanlayici-ac", "farabi-api").returncode, 2)
        self.assertEqual(self._kos("yeniden-baslat", "kazanim-test").returncode, 2)

    def test_betik_listesi_python_listesiyle_ayni(self):
        import servis_yonetimi
        metin = BETIK.read_text()
        servisler = set(re.search(r"SERVISLER=\"([^\"]+)\"", metin).group(1).split())
        zamanlayicilar = set(re.search(r"ZAMANLAYICILAR=\"([^\"]+)\"", metin).group(1).split())
        py = servis_yonetimi.BIRIMLER
        self.assertEqual(servisler, {k for k, v in py.items() if v["tur"] == "servis"})
        self.assertEqual(zamanlayicilar, {k for k, v in py.items() if v["tur"] == "zamanlayici"})


if __name__ == "__main__":
    unittest.main()
