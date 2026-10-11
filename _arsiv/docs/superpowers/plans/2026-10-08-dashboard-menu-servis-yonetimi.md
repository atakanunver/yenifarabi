# Dashboard Menü Çubuğu + Servis Yönetimi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dashboard'a (`farabi.local:8010`) Windows tarzı menü çubuğu kabuğu ve farabi.local servis/zamanlayıcılarını onaylı, denetim kayıtlı biçimde yöneten `/servisler` sayfası eklemek.

**Architecture:** Menü ağacı tek kaynak `menu.py`'de; `taban.html` menü çubuğu, ikon şeridi ve mobil çekmeceyi bu ağaçtan üretir. Servis eylemleri `servis_yonetimi.py` → `sudo -n /usr/local/sbin/farabi-servis <eylem> <birim>` (root'a ait beyaz listeli betik) üzerinden; durum `systemctl show`, log `journalctl` (sudo'suz, `ata` `adm` grubunda).

**Tech Stack:** FastAPI + Jinja2 + vanilla JS/CSS (CDN yok), Python 3.14 venv, unittest (pytest DEĞİL), systemd, bash.

**Spec:** `docs/superpowers/specs/2026-10-08-dashboard-menu-servis-yonetimi-design.md`

## Global Constraints

- Çalışma dizini `tahtayoklama/dashboard/`; testler `venv/bin/python -m unittest discover -p 'test_*.py'` (venv'de pytest yok).
- Renkler yalnızca `static/pano.css` başındaki `--renk-*` token'ları; ham hex yok; yeni token gerekirse üç tema bloğunda (`:root`, `[data-tema="yumusak"]`, `[data-tema="koyu"]`).
- Geçiş süreleri yalnızca `0.15s` (renk/zemin) ve `0.12s` (transform/gölge).
- İkonlar yalnızca `templates/_ikon_sprite.html` `<symbol id="ik-...">` (Lucide çizimi: 24×24, `stroke="currentColor"`, `stroke-width="2"`, yuvarlak uçlar); CDN/kütüphane yok.
- Arayüz metni Türkçe, cümle düzeni (ALL-CAPS etiket yok).
- Üretim DB'sine testte dokunulmaz: `db.DB_YOLU` geçici dosyaya yamalanır.
- Yönetilen birim listesi YALNIZCA iki yerde ve birebir aynı: `servis_yonetimi.BIRIMLER` ve `scripts/farabi-servis` `case` blokları (Task 1 testi ikisini karşılaştırır).
- Ön koşul: başka oturumun commit'lenmemiş `static/pano.css`, `kazanim_rapor.py`, `templates/kazanim_rapor.html`, `test_kazanim_rapor.py` değişiklikleri commit'lenmiş olmalı (`git status --short tahtayoklama/dashboard` bu dosyaları göstermemeli). Göstermiyorsa başla; gösteriyorsa DUR ve kullanıcıya sor.
- Dashboard restart'ı (`sudo systemctl restart farabi-yoklama-dashboard`) yalnızca Task 7'de, kullanıcıya haber vererek.

## Review Focus

- Beyaz liste dışı birim adı (ör. `ssh`, `farabi-api;rm`, `../x`) API'ye gelirse → 400, betik ÇAĞRILMAZ (Task 3 testi).
- Dashboard kendini durdur isteği (`farabi-yoklama-dashboard` + `durdur`) → reddedilir; yeniden başlat gecikmeli olur (Task 1 + Task 3 testleri).
- Log satırında `http://kullanici:sifre@host`, `token=..`, `ANAHTAR=..` geçerse ekrana `***` ile gelir (Task 2 testi).
- Ders saatinde `farabi-api` restart'ı ilk istekte `onay_gerekli` döner, `onay: true` ile ikinci istekte çalışır; soru havuzu "şimdi çalıştır" ders saatinde reddedilir (Task 2 testi).
- `Origin` başka host ise POST → 403 (Task 3 testi); menüde zil bağlantısında `@` yok (Task 4 testi).

---

## Dosya haritası

| Dosya | Sorumluluk |
|---|---|
| `scripts/farabi-servis` (yeni) | root betik: eylem+birim beyaz listesi, systemctl çağrısı |
| `scripts/farabi-servis.sudoers` (yeni) | `ata` için yalnızca betiğe NOPASSWD |
| `test_farabi_servis.py` (yeni) | betiği sahte `systemctl` ile koşar; liste eşitliği |
| `servis_yonetimi.py` (yeni) | BIRIMLER, eylem doğrulama, ders saati kuralı, durum, log+maskeleme, son hata, çalıştırma, router |
| `test_servis_yonetimi.py` (yeni) | modül + uç testleri |
| `menu.py` (yeni) | menü ağacı + aktif öğe |
| `test_menu.py` (yeni) | ağaç ↔ route, zil bağlantısı |
| `templates/taban.html` | kabuk: menü çubuğu, şerit, çekmece |
| `static/menu.js` (yeni) | menubar davranışı, tema/şerit tercihi, kısayollar |
| `static/kenar.js` | yalnız mini durum rozeti kalır (çekmece menu.js'e taşınır) |
| `static/pano.css` | kabuk CSS, menü, şerit, servis sayfası, reduced-motion |
| `templates/_ikon_sprite.html` | `ik-oynat`, `ik-durdur`, `ik-log`, `ik-uyari` |
| `templates/servisler.html` (yeni) | sayfa + sayfa JS'i |
| `app.py` | `include_router(servis_yonetimi.router)` |

---

### Task 1: Ayrıcalıklı sarmalayıcı betik + sudoers

**Files:**
- Create: `tahtayoklama/dashboard/scripts/farabi-servis`
- Create: `tahtayoklama/dashboard/scripts/farabi-servis.sudoers`
- Test: `tahtayoklama/dashboard/test_farabi_servis.py`

**Interfaces:**
- Produces: CLI `farabi-servis <eylem> <birim>`; eylemler `yeniden-baslat|durdur|baslat|zamanlayici-ac|zamanlayici-kapat|simdi-calistir|hata-temizle`; çıkış 0 başarı, 2 beyaz liste dışı, systemctl'in kodu diğer. Ortam değişkeni `FARABI_SERVIS_SYSTEMCTL` yalnızca test içindir (varsayılan `/usr/bin/systemctl`), `FARABI_SERVIS_SYSTEMD_RUN` aynı (varsayılan `/usr/bin/systemd-run`).

- [ ] **Step 1: Failing test yaz**

`test_farabi_servis.py`:
```python
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
        self.assertEqual(self._cagrilar(), [
            "RUN --on-active=2 --unit=farabi-dashboard-yeniden /usr/bin/systemctl restart farabi-yoklama-dashboard.service"])

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
```

- [ ] **Step 2: Kırmızı olduğunu gör**

Run: `cd tahtayoklama/dashboard && venv/bin/python -m unittest test_farabi_servis -v`
Expected: FAIL/ERROR (betik yok; `servis_yonetimi` yok — son test Task 2'de yeşile döner, bu task'ta yalnız ilk 6 test yeşil olmalı).

- [ ] **Step 3: Betiği yaz**

`scripts/farabi-servis`:
```bash
#!/bin/bash
# farabi-servis — dashboard'un (/servisler) TEK ayrıcalıklı kapısı (2026-10-08).
# Kurulum: sudo install -o root -g root -m 755 scripts/farabi-servis /usr/local/sbin/farabi-servis
# Liste servis_yonetimi.BIRIMLER ile BİREBİR aynı olmalı (test_farabi_servis karşılaştırır).
set -euo pipefail
SYSTEMCTL="${FARABI_SERVIS_SYSTEMCTL:-/usr/bin/systemctl}"
SYSTEMD_RUN="${FARABI_SERVIS_SYSTEMD_RUN:-/usr/bin/systemd-run}"
SERVISLER="farabi-api farabi-smssistemi farabi-yoklama-dashboard ollama open-webui sinif-arena"
ZAMANLAYICILAR="kazanim-test kazanim-test-sonuc kazanim-test-aylik soru-havuzu-uret farabi-idari-yukle"

reddet() { echo "farabi-servis: izin yok: $*" >&2; exit 2; }
[[ $# -eq 2 ]] || reddet "kullanım: farabi-servis <eylem> <birim>"
eylem="$1"; birim="$2"
listede() { local x; for x in $2; do [[ "$x" == "$1" ]] && return 0; done; return 1; }

if listede "$birim" "$SERVISLER"; then
  case "$eylem" in
    yeniden-baslat)
      if [[ "$birim" == "farabi-yoklama-dashboard" ]]; then
        # İsteği yanıtlayan süreci öldürmemek için 2 sn gecikmeli, ayrı birimde.
        exec "$SYSTEMD_RUN" --on-active=2 --unit=farabi-dashboard-yeniden \
          /usr/bin/systemctl restart farabi-yoklama-dashboard.service
      fi
      exec "$SYSTEMCTL" restart "$birim.service" ;;
    durdur)
      [[ "$birim" == "farabi-yoklama-dashboard" ]] && reddet "dashboard kendini durduramaz"
      [[ "$birim" == "ollama" ]] && reddet "ollama yalnızca yeniden başlatılabilir"
      exec "$SYSTEMCTL" stop "$birim.service" ;;
    baslat)
      exec "$SYSTEMCTL" start "$birim.service" ;;
    hata-temizle)
      exec "$SYSTEMCTL" reset-failed "$birim.service" ;;
    *) reddet "$eylem $birim" ;;
  esac
elif listede "$birim" "$ZAMANLAYICILAR"; then
  case "$eylem" in
    zamanlayici-ac)    exec "$SYSTEMCTL" enable --now "$birim.timer" ;;
    zamanlayici-kapat) exec "$SYSTEMCTL" disable --now "$birim.timer" ;;
    simdi-calistir)    exec "$SYSTEMCTL" start --no-block "$birim.service" ;;
    hata-temizle)      exec "$SYSTEMCTL" reset-failed "$birim.service" ;;
    *) reddet "$eylem $birim" ;;
  esac
else
  reddet "$eylem $birim"
fi
```
`chmod +x scripts/farabi-servis`.

`scripts/farabi-servis.sudoers`:
```
# /etc/sudoers.d/farabi-servis — dashboard yalnızca beyaz listeli betiği çağırır (2026-10-08)
ata ALL=(root) NOPASSWD: /usr/local/sbin/farabi-servis
```

- [ ] **Step 4: İlk 6 test yeşil**

Run: `venv/bin/python -m unittest test_farabi_servis -v`
Expected: 6 PASS, `test_betik_listesi_python_listesiyle_ayni` ERROR (servis_yonetimi yok — Task 2).
Ayrıca: `bash -n scripts/farabi-servis` hatasız.

- [ ] **Step 5: Commit**

```bash
git add tahtayoklama/dashboard/scripts/farabi-servis tahtayoklama/dashboard/scripts/farabi-servis.sudoers tahtayoklama/dashboard/test_farabi_servis.py
git commit -m "dashboard: farabi-servis beyaz listeli ayrıcalık betiği + sudoers kaynağı"
```

---

### Task 2: `servis_yonetimi.py` çekirdeği (liste, kural, durum, log, çalıştırma)

**Files:**
- Create: `tahtayoklama/dashboard/servis_yonetimi.py`
- Test: `tahtayoklama/dashboard/test_servis_yonetimi.py`

**Interfaces:**
- Consumes: `tahta_yeniden_baslat.ders_saatinde_mi(simdi=None) -> bool`; `zil.simdi_istanbul()`.
- Produces:
  - `BIRIMLER: dict[str, dict]` — anahtar birim adı (sonek yok); değer `{"ad": str, "tur": "servis"|"zamanlayici", "eylemler": tuple[str,...], "ders_uyarisi": bool, "aciklama": str}`.
  - `eylem_dogrula(birim: str, eylem: str) -> None` — geçersizse `ValueError`.
  - `onay_gerekli_mi(birim: str, eylem: str, simdi=None) -> str | None` — ders saatinde uyarı metni ya da None.
  - `ders_saatinde_yasak_mi(birim: str, eylem: str, simdi=None) -> bool` — soru havuzu şimdi-çalıştır.
  - `maskele(satir: str) -> str`.
  - `son_hata(satirlar: list[str]) -> str | None` — son Traceback'in son satırı ya da son "Failed with result" satırı.
  - `async calistir(birim: str, eylem: str) -> dict` → `{"ok": bool, "kod": int, "mesaj": str}`.
  - `async durumlar() -> list[dict]` — her birim için `{"birim","ad","tur","aktif_durum","alt_durum","sonuc","bellek_mib","baslama","sonraki","son_tetik","eylemler","ders_uyarisi","aciklama"}`.
  - `async log_oku(birim: str, satir: int = 200, yalniz_uyari: bool = False) -> list[str]` (maskeli).

- [ ] **Step 1: Failing testler**

`test_servis_yonetimi.py` (bu task'ın kısmı):
```python
"""servis_yonetimi birim testleri (2026-10-08)."""
import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

import servis_yonetimi as sy
import zil

DERS_SAATI = datetime(2026, 10, 7, 10, 0, tzinfo=zil.ISTANBUL)   # Çarşamba 10:00
AKSAM = datetime(2026, 10, 7, 20, 0, tzinfo=zil.ISTANBUL)


class TestListe(unittest.TestCase):
    def test_bilinmeyen_birim_ve_eylem_reddedilir(self):
        for birim, eylem in (("ssh", "yeniden-baslat"), ("farabi-api", "sil"),
                             ("farabi-api;rm", "yeniden-baslat"),
                             ("farabi-yoklama-dashboard", "durdur"),
                             ("farabi-api", "zamanlayici-ac")):
            with self.assertRaises(ValueError, msg=(birim, eylem)):
                sy.eylem_dogrula(birim, eylem)

    def test_gecerli_eylemler(self):
        sy.eylem_dogrula("farabi-api", "yeniden-baslat")
        sy.eylem_dogrula("soru-havuzu-uret", "zamanlayici-kapat")
        sy.eylem_dogrula("soru-havuzu-uret", "hata-temizle")


class TestDersSaati(unittest.TestCase):
    def test_ders_saatinde_uyarili_birim_onay_ister(self):
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=True):
            self.assertIn("ders", sy.onay_gerekli_mi("farabi-api", "yeniden-baslat", DERS_SAATI))
            self.assertIsNone(sy.onay_gerekli_mi("farabi-smssistemi", "yeniden-baslat", DERS_SAATI))

    def test_aksam_onay_gerekmez(self):
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=False):
            self.assertIsNone(sy.onay_gerekli_mi("farabi-api", "yeniden-baslat", AKSAM))

    def test_soru_havuzu_ders_saatinde_simdi_calistir_yasak(self):
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=True):
            self.assertTrue(sy.ders_saatinde_yasak_mi("soru-havuzu-uret", "simdi-calistir", DERS_SAATI))
            self.assertFalse(sy.ders_saatinde_yasak_mi("soru-havuzu-uret", "zamanlayici-kapat", DERS_SAATI))


class TestMaskeleVeHata(unittest.TestCase):
    def test_maskele(self):
        self.assertEqual(sy.maskele("GET http://admin:gizli@1.2.3.4/x"), "GET http://***@1.2.3.4/x")
        self.assertEqual(sy.maskele("token=abc123 ok"), "token=*** ok")
        self.assertEqual(sy.maskele("FARABI_EMBED_ANAHTAR=xyz"), "FARABI_EMBED_ANAHTAR=***")
        self.assertEqual(sy.maskele("password: hunter2"), "password: ***")

    def test_son_hata_traceback_son_satiri(self):
        satirlar = ["a", "Traceback (most recent call last):", "  File x", "OSError: [Errno 7] Argument list too long: '/x/agy'",
                    "systemd[1]: x.service: Main process exited, code=exited, status=1/FAILURE"]
        self.assertEqual(sy.son_hata(satirlar), "OSError: [Errno 7] Argument list too long: '/x/agy'")

    def test_son_hata_yoksa_none(self):
        self.assertIsNone(sy.son_hata(["Started x", "ok"]))


class TestCalistir(unittest.TestCase):
    def test_betik_arguman_listesiyle_cagrilir(self):
        sahte = AsyncMock(return_value=(0, "", ""))
        with patch.object(sy, "_komut_kos", sahte):
            sonuc = asyncio.run(sy.calistir("farabi-api", "yeniden-baslat"))
        sahte.assert_awaited_once_with(["sudo", "-n", sy.BETIK, "yeniden-baslat", "farabi-api"])
        self.assertTrue(sonuc["ok"])

    def test_gecersiz_birim_betige_gitmez(self):
        sahte = AsyncMock()
        with patch.object(sy, "_komut_kos", sahte):
            with self.assertRaises(ValueError):
                asyncio.run(sy.calistir("ssh", "yeniden-baslat"))
        sahte.assert_not_awaited()

    def test_betik_hatasi_ok_false(self):
        with patch.object(sy, "_komut_kos", AsyncMock(return_value=(1, "", "Job failed"))):
            sonuc = asyncio.run(sy.calistir("sinif-arena", "baslat"))
        self.assertFalse(sonuc["ok"])
        self.assertIn("Job failed", sonuc["mesaj"])


class TestDurumAyristir(unittest.TestCase):
    def test_show_ciktisi_birimlere_ayrilir(self):
        ham = ("Id=farabi-api.service\nActiveState=active\nSubState=running\nResult=success\n"
               "MemoryCurrent=104857600\nActiveEnterTimestamp=Wed 2026-10-08 08:21:19 UTC\n\n"
               "Id=soru-havuzu-uret.timer\nActiveState=active\nSubState=waiting\nResult=success\n"
               "NextElapseUSecRealtime=Thu 2026-10-08 14:15:00 UTC\nLastTriggerUSec=Wed 2026-10-07 14:15:11 UTC\n\n"
               "Id=soru-havuzu-uret.service\nActiveState=failed\nSubState=failed\nResult=exit-code\n")
        d = sy._show_ayristir(ham)
        self.assertEqual(d["farabi-api.service"]["SubState"], "running")
        self.assertEqual(d["soru-havuzu-uret.service"]["Result"], "exit-code")
        self.assertIn("NextElapseUSecRealtime", d["soru-havuzu-uret.timer"])
```

- [ ] **Step 2: Kırmızı**

Run: `venv/bin/python -m unittest test_servis_yonetimi -v` → ImportError.

- [ ] **Step 3: Modülü yaz**

`servis_yonetimi.py`:
```python
"""servis_yonetimi.py — /servisler: farabi.local servis ve zamanlayıcılarının durumu +
onaylı, denetim kayıtlı eylemler (2026-10-08, spec
docs/superpowers/specs/2026-10-08-dashboard-menu-servis-yonetimi-design.md).

Ayrıcalık YALNIZCA `sudo -n /usr/local/sbin/farabi-servis <eylem> <birim>` ile
(kabuk yok, argüman listesi). Log/durum okumak sudo gerektirmez (`ata` adm grubunda).
BIRIMLER scripts/farabi-servis'teki listelerle birebir aynı (test_farabi_servis)."""

import asyncio
import re

import tahta_yeniden_baslat

BETIK = "/usr/local/sbin/farabi-servis"
KOMUT_ZAMAN_ASIMI_SN = 60

_S = ("yeniden-baslat", "durdur", "baslat", "hata-temizle")
_Z = ("zamanlayici-ac", "zamanlayici-kapat", "simdi-calistir", "hata-temizle")
BIRIMLER: dict[str, dict] = {
    "farabi-api": {"ad": "Farabi Brain", "tur": "servis", "eylemler": _S, "ders_uyarisi": True,
                   "aciklama": "Tahtalardaki kitap/YKS soruları ~10 sn yanıt vermez."},
    "farabi-smssistemi": {"ad": "SMS sistemi", "tur": "servis", "eylemler": _S, "ders_uyarisi": False,
                          "aciklama": "09:00/14:00 otomasyon penceresindeyse gönderim kesilebilir."},
    "farabi-yoklama-dashboard": {"ad": "Yoklama panosu (bu sayfa)", "tur": "servis",
                                 "eylemler": ("yeniden-baslat",), "ders_uyarisi": False,
                                 "aciklama": "Sayfa birkaç saniye bağlantıyı kaybeder, sonra kendiliğinden döner."},
    "ollama": {"ad": "Ollama (qwen3.8:27b)", "tur": "servis", "eylemler": ("yeniden-baslat", "hata-temizle"),
               "ders_uyarisi": True, "aciklama": "Model yeniden yüklenir (~1 dk); Atos ve soru üretimi bekler."},
    "open-webui": {"ad": "Atos", "tur": "servis", "eylemler": _S, "ders_uyarisi": True,
                   "aciklama": "Atos sohbetleri bağlantıyı kaybeder."},
    "sinif-arena": {"ad": "Sınıf arenası", "tur": "servis", "eylemler": _S, "ders_uyarisi": True,
                    "aciklama": "Süren yarışma oturumları sıfırlanabilir."},
    "kazanim-test": {"ad": "Kazanım testi (hafta içi 16:30)", "tur": "zamanlayici", "eylemler": _Z,
                     "ders_uyarisi": False, "aciklama": "Haftalık kazanım testi formunu üretir."},
    "kazanim-test-sonuc": {"ad": "Kazanım testi sonuçları (her gün 00:00)", "tur": "zamanlayici",
                           "eylemler": _Z, "ders_uyarisi": False, "aciklama": "Form cevaplarını çeker."},
    "kazanim-test-aylik": {"ad": "Aylık kazanım raporu (ayın 1'i)", "tur": "zamanlayici", "eylemler": _Z,
                           "ders_uyarisi": False, "aciklama": "Önceki ayın raporlarını üretir."},
    "soru-havuzu-uret": {"ad": "Soru havuzu üretimi (gece)", "tur": "zamanlayici", "eylemler": _Z,
                         "ders_uyarisi": False,
                         "aciklama": "Yerel Ollama ile soru üretir; ders saatinde kendiliğinden durur."},
    "farabi-idari-yukle": {"ad": "İdari belge yükleme (02:30)", "tur": "zamanlayici", "eylemler": _Z,
                           "ders_uyarisi": False, "aciklama": "mudur/ belgelerini RAG'a yükler."},
}
# Ders saatinde tamamen reddedilen eylemler (GPU'yu derste Ollama'nın diğer kullanıcılarına bırak).
DERS_SAATINDE_YASAK = {("soru-havuzu-uret", "simdi-calistir")}

_MASKE = [
    (re.compile(r"(://)[^/\s:@]+:[^/\s@]+@"), r"\1***@"),
    (re.compile(r"(?i)\b([A-Z0-9_]*(?:token|key|anahtar|sifre|şifre|password|secret)[A-Z0-9_]*)(\s*[=:]\s*)\S+"),
     r"\1\2***"),
]


def eylem_dogrula(birim: str, eylem: str) -> None:
    tanim = BIRIMLER.get(birim)
    if tanim is None or eylem not in tanim["eylemler"]:
        raise ValueError(f"izin yok: {eylem} {birim}")


def onay_gerekli_mi(birim: str, eylem: str, simdi=None) -> str | None:
    tanim = BIRIMLER[birim]
    if tanim["ders_uyarisi"] and eylem in ("yeniden-baslat", "durdur") \
            and tahta_yeniden_baslat.ders_saatinde_mi(simdi):
        return f"Şu an ders saati. {tanim['aciklama']}"
    return None


def ders_saatinde_yasak_mi(birim: str, eylem: str, simdi=None) -> bool:
    return (birim, eylem) in DERS_SAATINDE_YASAK and tahta_yeniden_baslat.ders_saatinde_mi(simdi)


def maskele(satir: str) -> str:
    for desen, yerine in _MASKE:
        satir = desen.sub(yerine, satir)
    return satir


def son_hata(satirlar: list[str]) -> str | None:
    """Son Traceback'in son (istisna) satırı; Traceback yoksa son 'Failed with result' satırı."""
    son_tb = None
    for i, s in enumerate(satirlar):
        if "Traceback (most recent call last)" in s:
            son_tb = i
    if son_tb is not None:
        aday = None
        for s in satirlar[son_tb + 1:]:
            govde = (s.split("]: ", 1)[-1] if "]: " in s else s).strip()
            if re.match(r"^[A-Za-z_][\w.]*(Error|Exception|Exit|Interrupt)\b", govde):
                aday = govde
        if aday:
            return maskele(aday)
    for s in reversed(satirlar):
        if "Failed with result" in s:
            return maskele(s.split("]: ", 1)[-1].strip())
    return None


async def _komut_kos(args: list[str]) -> tuple[int, str, str]:
    surec = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        cikti, hata = await asyncio.wait_for(surec.communicate(), KOMUT_ZAMAN_ASIMI_SN)
    except TimeoutError:
        surec.kill()
        return 124, "", "zaman aşımı"
    return surec.returncode, cikti.decode(errors="replace"), hata.decode(errors="replace")


async def calistir(birim: str, eylem: str) -> dict:
    eylem_dogrula(birim, eylem)
    kod, cikti, hata = await _komut_kos(["sudo", "-n", BETIK, eylem, birim])
    return {"ok": kod == 0, "kod": kod, "mesaj": maskele((hata or cikti).strip())[:500]}


def _show_ayristir(ham: str) -> dict[str, dict]:
    sonuc = {}
    for blok in ham.split("\n\n"):
        oz = dict(s.partition("=")[::2] for s in blok.splitlines() if "=" in s)
        if oz.get("Id"):
            sonuc[oz["Id"]] = oz
    return sonuc


def _birim_adlari() -> list[str]:
    adlar = []
    for birim, t in BIRIMLER.items():
        adlar.append(f"{birim}.service")
        if t["tur"] == "zamanlayici":
            adlar.append(f"{birim}.timer")
    return adlar


async def durumlar() -> list[dict]:
    _, ham, _ = await _komut_kos([
        "systemctl", "show", *_birim_adlari(), "-p", "Id", "-p", "ActiveState", "-p", "SubState",
        "-p", "Result", "-p", "MemoryCurrent", "-p", "ActiveEnterTimestamp",
        "-p", "NextElapseUSecRealtime", "-p", "LastTriggerUSec", "-p", "UnitFileState"])
    oz = _show_ayristir(ham)
    liste = []
    for birim, t in BIRIMLER.items():
        s = oz.get(f"{birim}.service", {})
        z = oz.get(f"{birim}.timer", {})
        bellek = s.get("MemoryCurrent", "")
        liste.append({
            "birim": birim, "ad": t["ad"], "tur": t["tur"], "aciklama": t["aciklama"],
            "eylemler": list(t["eylemler"]), "ders_uyarisi": t["ders_uyarisi"],
            "aktif_durum": s.get("ActiveState", "bilinmiyor"), "alt_durum": s.get("SubState", ""),
            "sonuc": s.get("Result", ""),
            "bellek_mib": round(int(bellek) / 2**20) if bellek.isdigit() else None,
            "baslama": s.get("ActiveEnterTimestamp") or None,
            "zamanlayici_etkin": (z.get("UnitFileState") == "enabled") if z else None,
            "sonraki": z.get("NextElapseUSecRealtime") or None,
            "son_tetik": z.get("LastTriggerUSec") or None,
        })
    return liste


async def log_oku(birim: str, satir: int = 200, yalniz_uyari: bool = False) -> list[str]:
    if birim not in BIRIMLER:
        raise ValueError(f"izin yok: log {birim}")
    args = ["journalctl", "-u", f"{birim}.service", "-n", str(min(max(satir, 10), 1000)),
            "-o", "short-iso", "--no-pager"]
    if yalniz_uyari:
        args += ["-p", "warning"]
    _, cikti, _ = await _komut_kos(args)
    return [maskele(s) for s in cikti.splitlines()]
```

- [ ] **Step 4: Yeşil**

Run: `venv/bin/python -m unittest test_servis_yonetimi test_farabi_servis -v`
Expected: tüm testler PASS (Task 1'in liste eşitliği testi dahil).

- [ ] **Step 5: Commit**

```bash
git add tahtayoklama/dashboard/servis_yonetimi.py tahtayoklama/dashboard/test_servis_yonetimi.py
git commit -m "dashboard: servis_yonetimi çekirdeği (beyaz liste, ders saati kuralı, durum, log maskeleme, son hata)"
```

---

### Task 3: `/servisler` uçları (oturum, Origin, denetim)

**Files:**
- Modify: `tahtayoklama/dashboard/servis_yonetimi.py` (router ekle)
- Modify: `tahtayoklama/dashboard/app.py:103-109` (`app.include_router(servis_yonetimi.router)` + `import servis_yonetimi`)
- Create: `tahtayoklama/dashboard/templates/servisler.html` (iskelet; Task 6 doldurur — bu task'ta yalnız `<div id="servis-sayfasi"></div>` içeren `taban.html` uzantısı)
- Test: `tahtayoklama/dashboard/test_servis_yonetimi.py` (ek sınıf)

**Interfaces:**
- Consumes: Task 2 fonksiyonları; `auth.dogrula(request, conn)`; `uzaktan_yonetim._denetim_yaz(request, eylem, sonuclar, kaynak=)`.
- Produces: `GET /servisler` (HTML), `GET /api/servisler` → `{"birimler": durumlar(), "ders_saati": bool, "kapsam": dict|None}`, `GET /api/servisler/log/{birim}?yalniz_uyari=0|1` → `{"satirlar": [...], "son_hata": str|None}`, `POST /api/servisler/eylem` gövde `{"birim","eylem","onay": bool}` → 200 `{"ok","mesaj"}` | 409 `{"onay_gerekli": str}` | 400/403/401.

- [ ] **Step 1: Failing testler**

`test_servis_yonetimi.py` sonuna:
```python
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import db
from fastapi import HTTPException
from fastapi.requests import Request


def _istek(govde=b"", cerez="gecerli", origin="http://farabi.local:8010", yol="/api/servisler/eylem",
           accept="application/json"):
    headers = [(b"host", b"farabi.local:8010"), (b"accept", accept.encode())]
    if cerez:
        headers.append((b"cookie", f"oturum={cerez}".encode()))
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

    def _eylem(self, govde, **kw):
        return asyncio.run(sy.api_eylem(_istek(json.dumps(govde).encode(), **kw)))

    def _denetim(self):
        conn = db.baglanti()
        try:
            return [dict(r) for r in conn.execute("SELECT * FROM uzaktan_denetim")]
        finally:
            conn.close()

    def test_oturumsuz_401(self):
        with self.assertRaises(HTTPException) as c:
            self._eylem({"birim": "farabi-api", "eylem": "yeniden-baslat"}, cerez=None)
        self.assertEqual(c.exception.status_code, 401)

    def test_yabanci_origin_403(self):
        with self.assertRaises(HTTPException) as c:
            self._eylem({"birim": "farabi-api", "eylem": "yeniden-baslat"}, origin="http://kotu.site")
        self.assertEqual(c.exception.status_code, 403)

    def test_liste_disi_400_betik_cagrilmaz(self):
        sahte = AsyncMock()
        with patch.object(sy, "_komut_kos", sahte):
            with self.assertRaises(HTTPException) as c:
                self._eylem({"birim": "ssh", "eylem": "yeniden-baslat"})
        self.assertEqual(c.exception.status_code, 400)
        sahte.assert_not_awaited()

    def test_ders_saatinde_onaysiz_409_onayli_calisir_ve_denetlenir(self):
        sahte = AsyncMock(return_value=(0, "", ""))
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=True), \
             patch.object(sy, "_komut_kos", sahte):
            yanit = self._eylem({"birim": "farabi-api", "eylem": "yeniden-baslat"})
            self.assertEqual(yanit.status_code, 409)
            sahte.assert_not_awaited()
            yanit = self._eylem({"birim": "farabi-api", "eylem": "yeniden-baslat", "onay": True})
        self.assertEqual(yanit.status_code, 200)
        sahte.assert_awaited_once()
        kayit = self._denetim()
        self.assertEqual(len(kayit), 1)
        self.assertEqual(kayit[0]["eylem"], "servis-yeniden-baslat")
        self.assertEqual(kayit[0]["kaynak"], "servisler")

    def test_ders_saatinde_soru_havuzu_simdi_calistir_403(self):
        with patch("tahta_yeniden_baslat.ders_saatinde_mi", return_value=True), \
             patch.object(sy, "_komut_kos", AsyncMock()) as sahte:
            with self.assertRaises(HTTPException) as c:
                self._eylem({"birim": "soru-havuzu-uret", "eylem": "simdi-calistir", "onay": True})
        self.assertEqual(c.exception.status_code, 403)
        sahte.assert_not_awaited()

    def test_log_ucu_maskeli_ve_son_hata(self):
        cikti = "x: Traceback (most recent call last):\nx: OSError: boom token=gizli\n"
        with patch.object(sy, "_komut_kos", AsyncMock(return_value=(0, cikti, ""))):
            yanit = asyncio.run(sy.api_log(_istek(yol="/api/servisler/log/soru-havuzu-uret"),
                                           "soru-havuzu-uret"))
        govde = json.loads(yanit.body)
        self.assertNotIn("gizli", json.dumps(govde))
        self.assertTrue(govde["son_hata"].startswith("OSError: boom"))
```

Not: `oturumlar` tablosu ve çerez adı `auth.COOKIE_ADI`'dır — testte `oturum=` yerine `f"{auth.COOKIE_ADI}=gecerli"` kullan (`import auth`), kodu okuyup doğrula.

- [ ] **Step 2: Kırmızı** — `venv/bin/python -m unittest test_servis_yonetimi -v` → `api_eylem` yok.

- [ ] **Step 3: Router'ı ekle** — aşağıdaki import'ları `servis_yonetimi.py`'nin BAŞINDAKİ import bloğuna taşı (stdlib / üçüncü taraf / yerel grupları korunarak), geri kalanını dosyanın sonuna ekle:
```python
import json as _json
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import auth
import db
import uzaktan_yonetim

router = APIRouter()
templates = Jinja2Templates(directory="templates")
KAPSAM_JSON = Path("/mnt/farabi-data/farabi/kazanim_testleri/rapor/kapsam.json")


def _oturum(request: Request) -> bool:
    conn = db.baglanti()
    try:
        return auth.dogrula(request, conn)
    finally:
        conn.close()


def _oturum_kontrol(request: Request) -> None:
    if not _oturum(request):
        raise HTTPException(401, "Oturum geçersiz.")


def _origin_kontrol(request: Request) -> None:
    kaynak = request.headers.get("origin") or request.headers.get("referer") or ""
    if urlsplit(kaynak).netloc != request.headers.get("host", ""):
        raise HTTPException(403, "Yalnızca panonun kendi sayfasından.")


def _kapsam_ozeti() -> dict | None:
    """benchmark/kazanim_kapsam çıktısından soru havuzu kartı için yeterli/zayıf/boş."""
    try:
        veri = _json.loads(KAPSAM_JSON.read_text(encoding="utf-8"))
        toplam = {"yeterli": 0, "zayif": 0, "bos": 0, "plan_haftasi": 0}
        for v in veri["sonuc"].values():
            for k in toplam:
                toplam[k] += v.get(k, 0)
        return {**toplam, "uretim": veri.get("uretim")}
    except (OSError, ValueError, KeyError, AttributeError):
        return None


@router.get("/servisler", response_class=HTMLResponse)
async def servisler_sayfa(request: Request):
    if not _oturum(request):
        return RedirectResponse("/giris", status_code=303)
    return templates.TemplateResponse(request, "servisler.html", {})


@router.get("/api/servisler")
async def api_servisler(request: Request):
    _oturum_kontrol(request)
    return JSONResponse({"birimler": await durumlar(),
                         "ders_saati": tahta_yeniden_baslat.ders_saatinde_mi(),
                         "kapsam": _kapsam_ozeti()})


@router.get("/api/servisler/log/{birim}")
async def api_log(request: Request, birim: str, yalniz_uyari: int = 0):
    _oturum_kontrol(request)
    try:
        satirlar = await log_oku(birim, 200, bool(yalniz_uyari))
        tum = satirlar if not yalniz_uyari else await log_oku(birim, 400)
    except ValueError:
        raise HTTPException(400, "Bilinmeyen birim.")
    return JSONResponse({"satirlar": satirlar, "son_hata": son_hata(tum)})


@router.post("/api/servisler/eylem")
async def api_eylem(request: Request):
    _oturum_kontrol(request)
    _origin_kontrol(request)
    try:
        govde = await request.json()
    except ValueError:
        govde = {}
    birim, eylem = str(govde.get("birim", "")), str(govde.get("eylem", ""))
    try:
        eylem_dogrula(birim, eylem)
    except ValueError:
        raise HTTPException(400, "Bu birim için izin verilmeyen eylem.")
    if ders_saatinde_yasak_mi(birim, eylem):
        raise HTTPException(403, "Ders saatinde çalıştırılamaz.")
    uyari = onay_gerekli_mi(birim, eylem)
    if uyari and govde.get("onay") is not True:
        return JSONResponse({"onay_gerekli": uyari}, status_code=409)
    sonuc = await calistir(birim, eylem)
    uzaktan_yonetim._denetim_yaz(request, f"servis-{eylem}",
                                 [{"tahta": birim, "basarili": sonuc["ok"]}], kaynak="servisler")
    return JSONResponse({"ok": sonuc["ok"], "mesaj": sonuc["mesaj"]})
```
`templates/servisler.html` (iskelet):
```html
{% extends "taban.html" %}
{% block baslik_etiketi %}Servis yönetimi — Farabi Panel{% endblock %}
{% block baslik %}Servis yönetimi{% endblock %}
{% block icerik %}<div id="servis-sayfasi"></div>{% endblock %}
```
`app.py`: `import servis_yonetimi` ve `app.include_router(servis_yonetimi.router)` (109. satırdan sonra).

- [ ] **Step 4: Yeşil + tüm paket**

Run: `venv/bin/python -m unittest discover -p 'test_*.py'`
Expected: hepsi OK (önceki 185 + yeniler).

- [ ] **Step 5: Commit**

```bash
git add tahtayoklama/dashboard/servis_yonetimi.py tahtayoklama/dashboard/app.py tahtayoklama/dashboard/templates/servisler.html tahtayoklama/dashboard/test_servis_yonetimi.py
git commit -m "dashboard: /servisler uçları — oturum, Origin, ders saati onayı, denetim kaydı"
```

---

### Task 4: Menü ağacı (`menu.py`) + kabuk şablonu

**Files:**
- Create: `tahtayoklama/dashboard/menu.py`
- Modify: `tahtayoklama/dashboard/templates/taban.html` (tamamı)
- Modify: `tahtayoklama/dashboard/app.py:35-36` (`templates.env.globals["menu_agaci"] = menu.menu_agaci`); aynı satırı `sunucular.py`, `kazanim_rapor.py`, `admin.py`, `uzaktan_yonetim.py`, `servis_yonetimi.py`'deki her `Jinja2Templates(...)` örneğine de ekle (`grep -n "Jinja2Templates(" *.py` ile hepsini bul).
- Modify: `tahtayoklama/dashboard/templates/_ikon_sprite.html` (4 yeni ikon)
- Test: `tahtayoklama/dashboard/test_menu.py`

**Interfaces:**
- Produces: `menu.MENU: list[dict]` — her üst menü `{"ad": str, "kisayol": str (tek harf), "ogeler": list[dict]}`; öğe `{"ad", "href" | "eylem", "ikon"?, "yeni_sekme"?: bool, "ayrac"?: True, "alt"?: list}`. `menu.SERIT: list[dict]` (`ad, href, ikon`). `menu.menu_agaci(yol: str) -> dict` → `{"menu": MENU kopyası (aktif öğe `"aktif": True`), "serit": SERIT kopyası (aktif işaretli)}`. `eylem` değerleri: `"yazdir"`, `"yenile"`, `"bagla-kopyala"`, `"tema:klasik"|"tema:yumusak"|"tema:koyu"`, `"serit"`, `"kisayollar"`, `"hakkinda"`, `"cikis"`.

- [ ] **Step 1: Failing test**

`test_menu.py`:
```python
"""menu.py: menü ağacı her sayfayı içerir, aktif işaretleme, şifresiz dış bağlantı."""
import json
import unittest

import menu
from app import app

DAHILI = {"/", "/admin/tahtalar", "/admin/siniflar", "/admin/rapor", "/kazanim-rapor",
          "/admin/uzaktan", "/servisler", "/sistem-durumu", "/sunucular"}


def _hrefler(ogeler):
    for o in ogeler:
        if o.get("href"):
            yield o["href"]
        yield from _hrefler(o.get("alt", []))


class TestMenu(unittest.TestCase):
    def test_tum_sayfalar_menude(self):
        hrefler = {h.split("#")[0] for ust in menu.MENU for h in _hrefler(ust["ogeler"])}
        self.assertTrue(DAHILI <= hrefler, DAHILI - hrefler)

    def test_menu_route_lari_var(self):
        rotalar = {r.path for r in app.routes}
        for ust in menu.MENU:
            for h in _hrefler(ust["ogeler"]):
                if h.startswith("/") and not h.startswith("//"):
                    self.assertIn(h.split("#")[0], rotalar, h)

    def test_dis_baglantilarda_kimlik_yok(self):
        self.assertNotIn("@", json.dumps(menu.MENU))

    def test_aktif_isaretleme(self):
        agac = menu.menu_agaci("/servisler")
        aktifler = [o["ad"] for u in agac["menu"] for o in u["ogeler"] if o.get("aktif")]
        self.assertEqual(aktifler, ["Servis yönetimi"])
        self.assertEqual([s["ad"] for s in agac["serit"] if s.get("aktif")], ["Servis yönetimi"])
        self.assertFalse(any(o.get("aktif") for u in menu.MENU for o in u["ogeler"]))  # kaynak bozulmaz

    def test_ana_sayfa_yalniz_tam_eslesme(self):
        agac = menu.menu_agaci("/admin/rapor")
        self.assertFalse([s for s in agac["serit"] if s["href"] == "/" and s.get("aktif")])
```

- [ ] **Step 2: Kırmızı** — `venv/bin/python -m unittest test_menu -v` → ImportError.

- [ ] **Step 3: `menu.py`**
```python
"""menu.py — dashboard menü çubuğu, ikon şeridi ve mobil çekmecenin TEK kaynağı (2026-10-08).
taban.html üçünü de bu ağaçtan üretir; menü öğesi başka yerde elle yazılmaz."""

import copy

ZIL_PANELI = "http://192.168.23.230:8090/"   # kimlik gömülmez; tarayıcı Basic Auth sorar

MENU: list[dict] = [
    {"ad": "Dosya", "kisayol": "d", "ogeler": [
        {"ad": "Ana pano", "href": "/", "ikon": "ev"},
        {"ad": "Yazdır", "eylem": "yazdir"},
        {"ayrac": True},
        {"ad": "Çıkış", "eylem": "cikis", "ikon": "cikis"},
    ]},
    {"ad": "Düzen", "kisayol": "z", "ogeler": [
        {"ad": "Sayfayı yenile", "eylem": "yenile", "ikon": "yenile"},
        {"ad": "Bağlantıyı kopyala", "eylem": "bagla-kopyala"},
    ]},
    {"ad": "Yoklama", "kisayol": "y", "ogeler": [
        {"ad": "Pano", "href": "/", "ikon": "ev"},
        {"ad": "Tahtalar", "href": "/admin/tahtalar", "ikon": "monitor"},
        {"ad": "Sınıflar", "href": "/admin/siniflar", "ikon": "kullanicilar"},
        {"ad": "Rapor", "href": "/admin/rapor", "ikon": "grafik"},
        {"ad": "Kazanım raporu", "href": "/kazanim-rapor", "ikon": "hedef"},
    ]},
    {"ad": "Tahtalar", "kisayol": "t", "ogeler": [
        {"ad": "Uzaktan yönetim", "href": "/admin/uzaktan", "ikon": "kaydirici"},
    ]},
    {"ad": "Servisler", "kisayol": "s", "ogeler": [
        {"ad": "Servis yönetimi", "href": "/servisler", "ikon": "sunucu"},
        {"ad": "Zamanlayıcılar", "href": "/servisler#zamanlayicilar", "ikon": "saat"},
        {"ayrac": True},
        {"ad": "Sistem durumu", "href": "/sistem-durumu", "ikon": "nabiz"},
        {"ad": "Sunucular", "href": "/sunucular", "ikon": "katman"},
    ]},
    {"ad": "Uygulamalar", "kisayol": "u", "ogeler": [
        {"ad": "Atos yapay zeka", "href": "atos", "ikon": "yildiz", "yeni_sekme": True},
        {"ad": "SMS sistemi", "href": "/sms-git", "ikon": "zil", "yeni_sekme": True},
        {"ad": "SMS otomasyonu", "href": "/otomasyon-git", "ikon": "kaydirici", "yeni_sekme": True},
        {"ad": "Doğum günleri", "href": "/dogum", "ikon": "pasta", "yeni_sekme": True},
        {"ad": "Zil paneli", "href": ZIL_PANELI, "ikon": "zil", "yeni_sekme": True},
    ]},
    {"ad": "Görünüm", "kisayol": "g", "ogeler": [
        {"ad": "Tema", "alt": [
            {"ad": "Klasik", "eylem": "tema:klasik", "ikon": "gunes"},
            {"ad": "Yumuşak", "eylem": "tema:yumusak", "ikon": "bulut"},
            {"ad": "Koyu", "eylem": "tema:koyu", "ikon": "ay"},
        ]},
        {"ad": "Kenar şeridini gizle/göster", "eylem": "serit"},
    ]},
    {"ad": "Yardım", "kisayol": "r", "ogeler": [
        {"ad": "Klavye kısayolları", "eylem": "kisayollar"},
        {"ad": "Hakkında", "eylem": "hakkinda"},
    ]},
]

SERIT: list[dict] = [
    {"ad": "Ana pano", "href": "/", "ikon": "ev"},
    {"ad": "Uzaktan yönetim", "href": "/admin/uzaktan", "ikon": "kaydirici"},
    {"ad": "Yoklama raporu", "href": "/admin/rapor", "ikon": "grafik"},
    {"ad": "Servis yönetimi", "href": "/servisler", "ikon": "sunucu"},
    {"ad": "Sistem durumu", "href": "/sistem-durumu", "ikon": "nabiz"},
    {"ad": "Atos yapay zeka", "href": "atos", "ikon": "yildiz", "yeni_sekme": True},
]


def _eslesir(href: str, yol: str) -> bool:
    if not href or not href.startswith("/") or "#" in href:
        return False
    return yol == "/" if href == "/" else yol == href or yol.startswith(href + "/")


def menu_agaci(yol: str) -> dict:
    menu, serit = copy.deepcopy(MENU), copy.deepcopy(SERIT)
    ilk_ana_pano = True
    for ust in menu:
        for o in ust["ogeler"]:
            if _eslesir(o.get("href", ""), yol):
                # "/" iki menüde var; yalnız ilk görüleni (Dosya › Ana pano değil, Yoklama › Pano) işaretle
                if o["href"] == "/" and ilk_ana_pano:
                    ilk_ana_pano = False
                    continue
                o["aktif"] = True
    for s in serit:
        if _eslesir(s["href"], yol):
            s["aktif"] = True
    return {"menu": menu, "serit": serit}
```
`"atos"` href'i şablonda `http://{{ request.url.hostname }}/` olarak çözülür (bugünkü davranış).

- [ ] **Step 4: `taban.html` kabuğu** — dosyanın `<body>` içeriğini şu yapıyla değiştir (head aynı kalır, `<script src="/static/menu.js"></script>` eklenir, kenar.js kalır):
```html
{% set agac = menu_agaci(request.url.path) %}
{% macro baglanti(o) -%}
  {%- if o.href == 'atos' -%}http://{{ request.url.hostname }}/{%- else -%}{{ o.href }}{%- endif -%}
{%- endmacro %}
{% macro oge(o) %}
  {% if o.ayrac %}<li role="separator" class="menu-ayrac"></li>
  {% elif o.alt %}
  <li role="none" class="alt-menu-kap">
    <button type="button" role="menuitem" aria-haspopup="true" aria-expanded="false" class="menu-oge">
      {{ o.ad }}<svg class="ikon ikon-kucuk ikon-disa"><use href="#ik-ok-sag"/></svg></button>
    <ul role="menu" class="menu-panel alt-panel" hidden>{% for a in o.alt %}{{ oge(a) }}{% endfor %}</ul>
  </li>
  {% elif o.eylem %}
  <li role="none"><button type="button" role="{{ 'menuitemradio' if o.eylem.startswith('tema:') else 'menuitem' }}"
      class="menu-oge" data-eylem="{{ o.eylem }}">
      {% if o.ikon %}<svg class="ikon"><use href="#ik-{{ o.ikon }}"/></svg>{% endif %}{{ o.ad }}</button></li>
  {% else %}
  <li role="none"><a role="menuitem" class="menu-oge{{ ' aktif' if o.aktif }}" href="{{ baglanti(o) }}"
      {% if o.aktif %}aria-current="page"{% endif %}
      {% if o.yeni_sekme %}target="_blank" rel="noopener"{% endif %}>
      {% if o.ikon %}<svg class="ikon"><use href="#ik-{{ o.ikon }}"/></svg>{% endif %}{{ o.ad }}
      {% if o.yeni_sekme %}<svg class="ikon ikon-kucuk ikon-disa"><use href="#ik-ok-sag"/></svg>{% endif %}</a></li>
  {% endif %}
{% endmacro %}
<div class="kabuk" id="kabuk">
  <header class="menu-cubugu">
    <a class="marka" href="/" title="Ana pano"><span class="marka-simge" aria-hidden="true">◆</span><span class="marka-metin">Farabi</span></a>
    <button type="button" class="menu-ac" id="menu-ac" aria-label="Menüyü aç" aria-controls="cekmece" aria-expanded="false">
      <svg class="ikon"><use href="#ik-menu"/></svg></button>
    <ul role="menubar" class="menubar" aria-label="Ana menü">
      {% for ust in agac.menu %}
      <li role="none" class="ust-menu">
        <button type="button" role="menuitem" aria-haspopup="true" aria-expanded="false"
                class="ust-menu-dugme" data-kisayol="{{ ust.kisayol }}">{{ ust.ad }}</button>
        <ul role="menu" class="menu-panel" aria-label="{{ ust.ad }}" hidden>
          {% for o in ust.ogeler %}{{ oge(o) }}{% endfor %}
        </ul>
      </li>
      {% endfor %}
    </ul>
    <span class="gun-etiketi">{{ gun_adi_buyuk() }}</span>
  </header>
  <nav class="serit" id="serit" aria-label="Sık kullanılanlar">
    {% for s in agac.serit %}
    <a href="{{ baglanti(s) }}" class="serit-oge{{ ' aktif' if s.aktif }}" title="{{ s.ad }}" aria-label="{{ s.ad }}"
       {% if s.aktif %}aria-current="page"{% endif %}{% if s.yeni_sekme %} target="_blank" rel="noopener"{% endif %}>
      <svg class="ikon"><use href="#ik-{{ s.ikon }}"/></svg></a>
    {% endfor %}
    <button type="button" class="mini-durum serit-durum" id="mini-durum" title="Sunucu durumunu yüklemek için tıkla">
      <span class="mini-durum-nokta" id="mini-durum-nokta"></span>
      <span id="mini-durum-sicaklik" class="gorsel-gizli">—</span><span id="mini-durum-servis" class="gorsel-gizli">Durumu göster</span>
    </button>
  </nav>
  <div class="cekmece-ortu" id="cekmece-ortu" hidden></div>
  <aside class="cekmece" id="cekmece" aria-label="Menü" hidden>
    {% for ust in agac.menu %}
    <details class="cekmece-grup"><summary>{{ ust.ad }}</summary>
      <ul class="cekmece-liste">{% for o in ust.ogeler %}{{ oge(o) }}{% endfor %}</ul></details>
    {% endfor %}
  </aside>
  <div class="icerik-alani">
    <header class="sayfa-ust">
      <h1>{% block baslik %}{% endblock %}</h1>
      <div class="ust-sag">{% block ust_sag %}{% endblock %}</div>
    </header>
    <main>{% block icerik %}{% endblock %}</main>
  </div>
</div>
<form method="post" action="/cikis" id="cikis-form" hidden></form>
<dialog class="pencere" id="kisayol-penceresi" aria-labelledby="kisayol-baslik">
  <h2 id="kisayol-baslik">Klavye kısayolları</h2>
  <dl><dt>F10</dt><dd>Menü çubuğuna git</dd><dt>← →</dt><dd>Menüler arasında</dd>
      <dt>↓ ↑</dt><dd>Menü öğeleri arasında</dd><dt>Enter</dt><dd>Seç</dd><dt>Esc</dt><dd>Kapat</dd>
      <dt>?</dt><dd>Bu pencere</dd></dl>
  <form method="dialog"><button class="dugme">Kapat</button></form>
</dialog>
<dialog class="pencere" id="hakkinda-penceresi" aria-labelledby="hakkinda-baslik">
  <h2 id="hakkinda-baslik">Farabi panel</h2>
  <p>Yoklama, tahta ve servis yönetimi — farabi.local:8010.</p>
  <form method="dialog"><button class="dugme">Kapat</button></form>
</dialog>
<div id="toast" class="toast gizli"></div>
```
Eski `.tema-secici` butonları kalkar (tema Görünüm menüsünde); `tema.js` Task 5'te `[data-eylem^="tema:"]`'a uyarlanır. `kenar.js`'teki kenar aç/kapat bloğu silinir (mini durum bölümü kalır).

`_ikon_sprite.html`'e (Lucide `play`, `square`, `scroll-text`, `triangle-alert` çizimleri, mevcut sembol biçimiyle):
```html
<symbol id="ik-oynat" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 3 20 12 6 21 6 3"/></symbol>
<symbol id="ik-durdur" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="1"/></symbol>
<symbol id="ik-log" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 12h-5"/><path d="M15 8h-5"/><path d="M19 17V5a2 2 0 0 0-2-2H4"/><path d="M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3"/></symbol>
<symbol id="ik-uyari" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></symbol>
```
(sprite'taki mevcut `<symbol>` satırlarının biçimini birebir izle — farklıysa onu kopyala.)

- [ ] **Step 5: Yeşil + her sayfa render**

Run: `venv/bin/python -m unittest discover -p 'test_*.py'` → OK.
Ek kontrol (geçici, commit'lenmez): mevcut sayfa testlerinin (ör. `test_sunucular.TestProxyUcu.test_sayfa_render_edilir`) geçmesi şablonun tüm sayfalarda derlendiğini gösterir; ayrıca `venv/bin/python -c "from app import app; from fastapi.testclient import TestClient"` mevcutsa `/giris` dışı sayfaların oturumsuz 303 verdiğini doğrula.

- [ ] **Step 6: Commit**

```bash
git add tahtayoklama/dashboard/menu.py tahtayoklama/dashboard/test_menu.py tahtayoklama/dashboard/templates/taban.html tahtayoklama/dashboard/templates/_ikon_sprite.html tahtayoklama/dashboard/app.py tahtayoklama/dashboard/*.py tahtayoklama/dashboard/static/kenar.js
git commit -m "dashboard: menü çubuğu kabuğu — tek kaynak menu.py, ikon şeridi, mobil çekmece; zil bağlantısında kimlik yok"
```
(`git add *.py` öncesi `git status` ile yalnız bu task'ın dosyalarının değiştiğini doğrula.)

---

### Task 5: Menü davranışı (`menu.js`) + kabuk CSS

**Files:**
- Create: `tahtayoklama/dashboard/static/menu.js`
- Modify: `tahtayoklama/dashboard/static/tema.js`
- Modify: `tahtayoklama/dashboard/static/pano.css` (kabuk bölümü: `.uygulama`…`.ust-cubuk h1` aralığı (≈133-340) yerine yeni kabuk; sona reduced-motion)

**Interfaces:**
- Consumes: Task 4 DOM (`.menubar`, `.ust-menu-dugme`, `.menu-panel`, `[data-eylem]`, `#serit`, `#cekmece`, `#menu-ac`, `#cikis-form`, `#kisayol-penceresi`, `#hakkinda-penceresi`).
- Produces: `window.farabiToast(metin)` (sayfa JS'lerinin kullanabileceği; mevcut `#toast`'u gösterir 3 sn).

- [ ] **Step 1: `menu.js`** (tam içerik):
```javascript
// Menü çubuğu (WAI-ARIA menubar), mobil çekmece, Görünüm/Yardım eylemleri (2026-10-08).
(function () {
  var cubuk = document.querySelector('.menubar');
  if (!cubuk) return;
  var ustler = Array.prototype.slice.call(cubuk.querySelectorAll('.ust-menu-dugme'));
  var acik = null;

  function ogeler(panel) {
    return Array.prototype.slice.call(panel.querySelectorAll(':scope > li > .menu-oge'));
  }
  function kapat(odakDon) {
    if (!acik) return;
    acik.setAttribute('aria-expanded', 'false');
    acik.nextElementSibling.hidden = true;
    acik.nextElementSibling.querySelectorAll('.alt-panel').forEach(function (p) { p.hidden = true; });
    if (odakDon) acik.focus();
    acik = null;
  }
  function ac(dugme, ilkOgeyeOdak) {
    if (acik && acik !== dugme) kapat(false);
    acik = dugme;
    dugme.setAttribute('aria-expanded', 'true');
    var panel = dugme.nextElementSibling;
    panel.hidden = false;
    if (ilkOgeyeOdak) { var o = ogeler(panel); if (o[0]) o[0].focus(); }
  }
  function komsu(dugme, yon) {
    var i = (ustler.indexOf(dugme) + yon + ustler.length) % ustler.length;
    return ustler[i];
  }

  ustler.forEach(function (d) {
    d.addEventListener('click', function () { acik === d ? kapat(true) : ac(d, false); });
    d.addEventListener('mouseenter', function () { if (acik && acik !== d) ac(d, false); });
    d.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        e.preventDefault();
        var k = komsu(d, e.key === 'ArrowRight' ? 1 : -1);
        acik ? ac(k, false) : null; k.focus();
      } else if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault(); ac(d, true);
      } else if (e.key === 'Home' || e.key === 'End') {
        e.preventDefault(); ustler[e.key === 'Home' ? 0 : ustler.length - 1].focus();
      }
    });
  });

  cubuk.addEventListener('keydown', function (e) {
    var hedef = e.target;
    if (!hedef.classList.contains('menu-oge')) return;
    var panel = hedef.closest('[role="menu"]');
    var liste = ogeler(panel);
    var i = liste.indexOf(hedef);
    if (e.key === 'ArrowDown') { e.preventDefault(); liste[(i + 1) % liste.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); liste[(i - 1 + liste.length) % liste.length].focus(); }
    else if (e.key === 'Home') { e.preventDefault(); liste[0].focus(); }
    else if (e.key === 'End') { e.preventDefault(); liste[liste.length - 1].focus(); }
    else if (e.key === 'Escape') { e.preventDefault(); kapat(true); }
    else if (e.key === 'ArrowRight' && hedef.getAttribute('aria-haspopup')) {
      e.preventDefault(); altAc(hedef);
    } else if (e.key === 'ArrowLeft' && panel.classList.contains('alt-panel')) {
      e.preventDefault(); panel.hidden = true; panel.previousElementSibling.focus();
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault(); var k = komsu(acik, e.key === 'ArrowRight' ? 1 : -1); ac(k, true);
    }
  });
  function altAc(dugme) {
    var p = dugme.nextElementSibling; p.hidden = false; dugme.setAttribute('aria-expanded', 'true');
    var o = ogeler(p); if (o[0]) o[0].focus();
  }
  document.querySelectorAll('.alt-menu-kap > .menu-oge').forEach(function (d) {
    d.addEventListener('click', function () { altAc(d); });
    d.parentElement.addEventListener('mouseenter', function () { d.nextElementSibling.hidden = false; });
    d.parentElement.addEventListener('mouseleave', function () { d.nextElementSibling.hidden = true; });
  });
  document.addEventListener('click', function (e) { if (acik && !cubuk.contains(e.target)) kapat(false); });

  // ---- Eylemler ----
  function toast(metin) {
    var t = document.getElementById('toast'); if (!t) return;
    t.textContent = metin; t.classList.remove('gizli');
    setTimeout(function () { t.classList.add('gizli'); }, 3000);
  }
  window.farabiToast = toast;
  function seritUygula(gizli) {
    document.getElementById('kabuk').classList.toggle('serit-gizli', gizli);
    try { localStorage.setItem('farabi_serit_gizli', gizli ? '1' : '0'); } catch (e) {}
  }
  var EYLEMLER = {
    'yazdir': function () { window.print(); },
    'yenile': function () { location.reload(); },
    'bagla-kopyala': function () {
      (navigator.clipboard ? navigator.clipboard.writeText(location.href) : Promise.reject())
        .then(function () { toast('Bağlantı kopyalandı.'); }, function () { toast('Kopyalanamadı.'); });
    },
    'serit': function () { seritUygula(!document.getElementById('kabuk').classList.contains('serit-gizli')); },
    'kisayollar': function () { document.getElementById('kisayol-penceresi').showModal(); },
    'hakkinda': function () { document.getElementById('hakkinda-penceresi').showModal(); },
    'cikis': function () { document.getElementById('cikis-form').submit(); }
  };
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-eylem]'); if (!b) return;
    var ad = b.dataset.eylem;
    if (ad.indexOf('tema:') === 0) { window.farabiTemaUygula && window.farabiTemaUygula(ad.slice(5)); }
    else if (EYLEMLER[ad]) { EYLEMLER[ad](); }
    kapat(false); cekmeceKapat();
  });
  try { seritUygula(localStorage.getItem('farabi_serit_gizli') === '1'); } catch (e) {}

  // ---- Kısayollar ----
  document.addEventListener('keydown', function (e) {
    if (e.key === 'F10') { e.preventDefault(); ustler[0].focus(); }
    var yazi = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
    if (e.key === '?' && !yazi) { e.preventDefault(); EYLEMLER.kisayollar(); }
  });

  // ---- Mobil çekmece ----
  var cek = document.getElementById('cekmece'), ortu = document.getElementById('cekmece-ortu'),
      acDugme = document.getElementById('menu-ac');
  function cekmeceKapat() { if (!cek) return; cek.hidden = true; ortu.hidden = true; acDugme.setAttribute('aria-expanded', 'false'); }
  if (acDugme) acDugme.addEventListener('click', function () {
    cek.hidden = false; ortu.hidden = false; acDugme.setAttribute('aria-expanded', 'true');
    var ilk = cek.querySelector('summary'); if (ilk) ilk.focus();
  });
  if (ortu) ortu.addEventListener('click', cekmeceKapat);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') cekmeceKapat(); });
})();
```

- [ ] **Step 2: `tema.js`** — `temaUygula`'yı `window.farabiTemaUygula = temaUygula;` ile dışa aç; `.tema-secici button` sorgularını `[data-eylem^="tema:"]` ile değiştir; aktif işaretleme `aria-checked` (`buton.setAttribute('aria-checked', buton.dataset.eylem === 'tema:' + tema)`).

- [ ] **Step 3: `pano.css` kabuk bölümü** — `.uygulama` (≈133) ile `.ust-cubuk h1` bloğunun sonu (≈340) arasını sil, yerine:
```css
/* ---------- Kabuk: menü çubuğu + ikon şeridi (2026-10-08) ---------- */
.kabuk { display: grid; grid-template-columns: 56px 1fr; grid-template-rows: auto 1fr; min-height: 100vh; }
.kabuk.serit-gizli { grid-template-columns: 0 1fr; }
.kabuk.serit-gizli .serit { display: none; }
.menu-cubugu { grid-column: 1 / -1; display: flex; align-items: center; gap: 0.25rem; padding: 0 0.75rem;
  height: 40px; background: var(--renk-yuzey); border-bottom: 1px solid var(--renk-kenar); position: sticky; top: 0; z-index: 30; }
.marka { display: flex; align-items: center; gap: 0.4rem; font-weight: 700; color: var(--renk-metin); text-decoration: none; padding: 0 0.5rem 0 0; }
.marka-simge { color: var(--renk-birincil); }
.menubar { display: flex; list-style: none; margin: 0; padding: 0; gap: 0.1rem; }
.ust-menu { position: relative; }
.ust-menu-dugme { font: inherit; font-size: 0.9rem; background: none; border: 0; color: var(--renk-metin);
  padding: 0.35rem 0.6rem; border-radius: 6px; cursor: pointer; transition: background 0.15s; }
.ust-menu-dugme:hover, .ust-menu-dugme[aria-expanded="true"] { background: var(--renk-yuzey-2); }
.ust-menu-dugme:focus-visible, .menu-oge:focus-visible, .serit-oge:focus-visible { outline: 2px solid var(--renk-birincil); outline-offset: 1px; }
.menu-panel { position: absolute; top: calc(100% + 4px); left: 0; min-width: 220px; list-style: none; margin: 0; padding: 0.3rem;
  background: var(--renk-yuzey); border: 1px solid var(--renk-kenar); border-radius: var(--yaricap);
  box-shadow: var(--renk-golge-yukseltilmis); z-index: 40; }
.alt-menu-kap { position: relative; }
.alt-panel { top: -0.3rem; left: calc(100% + 2px); }
.menu-oge { display: flex; align-items: center; gap: 0.55rem; width: 100%; font: inherit; font-size: 0.9rem; text-align: left;
  background: none; border: 0; color: var(--renk-metin); text-decoration: none; padding: 0.45rem 0.6rem; border-radius: 6px;
  cursor: pointer; transition: background 0.15s; }
.menu-oge:hover, .menu-oge:focus { background: var(--renk-birincil-zemin); }
.menu-oge.aktif, .menu-oge[aria-checked="true"] { color: var(--renk-birincil); font-weight: 600; }
.menu-ayrac { height: 1px; margin: 0.3rem 0.2rem; background: var(--renk-kenar); }
.menu-cubugu .gun-etiketi { margin-left: auto; color: var(--renk-metin-soluk); font-size: 0.85rem; }
.menu-ac { display: none; }
.serit { grid-row: 2; display: flex; flex-direction: column; align-items: center; gap: 0.3rem; padding: 0.6rem 0;
  background: var(--renk-yuzey); border-right: 1px solid var(--renk-kenar); position: sticky; top: 40px; height: calc(100vh - 40px); }
.serit-oge { display: grid; place-items: center; width: 40px; height: 40px; border-radius: var(--yaricap);
  color: var(--renk-metin-soluk); transition: background 0.15s, color 0.15s; }
.serit-oge:hover { background: var(--renk-yuzey-2); color: var(--renk-metin); }
.serit-oge.aktif { background: var(--renk-birincil-zemin); color: var(--renk-birincil); }
.serit-durum { margin-top: auto; }
.gorsel-gizli { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.icerik-alani { grid-row: 2; grid-column: 2; min-width: 0; display: flex; flex-direction: column; }
.sayfa-ust { display: flex; align-items: center; gap: 1rem; padding: 1rem 1.5rem 0.5rem; }
.sayfa-ust h1 { margin: 0; font-size: 1.35rem; }
.sayfa-ust .ust-sag { margin-left: auto; display: flex; gap: 0.5rem; }
.cekmece-ortu { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.4); z-index: 49; }
.cekmece { position: fixed; top: 0; left: 0; bottom: 0; width: min(86vw, 320px); overflow-y: auto; padding: 1rem;
  background: var(--renk-yuzey); z-index: 50; box-shadow: var(--renk-golge-yukseltilmis); }
.cekmece-grup summary { font-weight: 600; padding: 0.6rem 0.4rem; cursor: pointer; }
.cekmece-liste { list-style: none; margin: 0; padding: 0 0 0.5rem; }
.cekmece .alt-panel { position: static; box-shadow: none; border: 0; }
.pencere { border: 1px solid var(--renk-kenar); border-radius: var(--yaricap-buyuk); background: var(--renk-yuzey);
  color: var(--renk-metin); padding: 1.25rem 1.5rem; max-width: min(92vw, 460px); }
.pencere::backdrop { background: rgba(15, 23, 42, 0.45); }
.pencere dl { display: grid; grid-template-columns: auto 1fr; gap: 0.35rem 1rem; }
.pencere dt { font-family: ui-monospace, monospace; color: var(--renk-metin-soluk); }
@media (max-width: 720px) {
  .kabuk { grid-template-columns: 1fr; }
  .menubar, .serit, .menu-cubugu .gun-etiketi { display: none; }
  .menu-ac { display: inline-grid; place-items: center; background: none; border: 0; color: var(--renk-metin); padding: 0.4rem; }
  .icerik-alani { grid-column: 1; }
  .sayfa-ust { padding: 0.75rem 1rem 0.25rem; }
}
@media print { .menu-cubugu, .serit, .cekmece { display: none !important; } .kabuk { display: block; } }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.001ms !important; animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important; }
}
```
Eski `@media (max-width: 900px)` vb. bloklarda `.kenar-cubugu`/`.kenar-*`/`.ust-cubuk` geçen kuralları sil (`grep -n "kenar-\|ust-cubuk\|\.uygulama" static/pano.css` boş dönmeli, `.kenar-alt .tema-secici` dahil).
`rgba(15, 23, 42, …)` ham değeri tek başına kalmasın: pano.css'te zaten var olan örtü rengini kullanan kural varsa (`grep -n "rgba(15, 23, 42" static/pano.css`) aynı değeri kullan; yoksa üç temaya `--renk-ortu` token'ı ekleyip ikisini de ona çevir.

- [ ] **Step 4: Elle doğrulama (Chrome, `farabi.local:8010`, yeniden başlatma Task 7'de — bu adımda geçici olarak `venv/bin/uvicorn app:app --port 8011` ile ayrı süreçte aç, sonra kapat)**
  - Üç tema (Görünüm › Tema) — menü paneli, şerit, aktif öğe okunur.
  - Yalnız klavye: F10 → ←/→ → ↓ → Enter; Görünüm › Tema alt menüsü → ile açılır, ← ile kapanır; Esc odağı üst menüye döndürür; `?` kısayol penceresi.
  - Fareyle bir menü açıkken komşu menünün üstüne gelince o açılır; dışarı tıklama kapatır.
  - DevTools 375 px: menü çubuğu yerine ☰, çekmece akordeon, yatay kaydırma yok.
  - Her sayfa (`/`, `/admin/tahtalar`, `/admin/siniflar`, `/admin/rapor`, `/kazanim-rapor`, `/admin/uzaktan`, `/sistem-durumu`, `/sunucular`, `/servisler`) açılır, konsolda hata yok.
  - Yazdır önizlemesinde menü ve şerit yok.

- [ ] **Step 5: Commit**
```bash
git add tahtayoklama/dashboard/static/menu.js tahtayoklama/dashboard/static/tema.js tahtayoklama/dashboard/static/pano.css
git commit -m "dashboard: menubar klavye/fare davranışı, kabuk CSS, prefers-reduced-motion"
```

---

### Task 6: `/servisler` sayfası (kartlar, zamanlayıcılar, log paneli, onay, soru havuzu kartı)

**Files:**
- Modify: `tahtayoklama/dashboard/templates/servisler.html`
- Modify: `tahtayoklama/dashboard/static/pano.css` (servis sayfası bölümü, dosya sonuna)
- Test: `tahtayoklama/dashboard/test_servis_yonetimi.py` (sayfa render testi)

**Interfaces:**
- Consumes: Task 3 JSON uçları; `window.farabiToast`.

- [ ] **Step 1: Failing render testi** (`TestUclar` içine):
```python
    def test_sayfa_render_edilir(self):
        istek = _istek(yol="/servisler", accept="text/html")
        yanit = asyncio.run(sy.servisler_sayfa(istek))
        self.assertEqual(yanit.status_code, 200)
        for parca in (b'id="servis-kartlari"', b'id="zamanlayicilar"', b'id="log-paneli"',
                      b'id="onay-penceresi"', b'id="soru-havuzu-karti"'):
            self.assertIn(parca, yanit.body)
```
Run: `venv/bin/python -m unittest test_servis_yonetimi.TestUclar.test_sayfa_render_edilir -v` → FAIL.

- [ ] **Step 2: `servisler.html`** (tam):
```html
{% extends "taban.html" %}
{% block baslik_etiketi %}Servis yönetimi — Farabi Panel{% endblock %}
{% block baslik %}Servis yönetimi{% endblock %}
{% block ust_sag %}<button type="button" class="dugme" id="yenile"><svg class="ikon"><use href="#ik-yenile"/></svg> Yenile</button>{% endblock %}
{% block icerik %}
<section class="kpi-satir" aria-live="polite">
  <div class="kpi"><span class="kpi-etiket">Çalışan servis</span><strong id="kpi-calisan">—</strong></div>
  <div class="kpi"><span class="kpi-etiket">Sorunlu</span><strong id="kpi-sorunlu">—</strong></div>
  <div class="kpi"><span class="kpi-etiket">Sıradaki zamanlayıcı</span><strong id="kpi-siradaki">—</strong></div>
  <div class="kpi" id="ders-saati-rozeti" hidden><span class="rozet rozet-amber">Ders saati</span></div>
</section>

<h2 class="bolum-baslik">Servisler</h2>
<div class="servis-izgara" id="servis-kartlari">
  <div class="servis-kart iskelet"></div><div class="servis-kart iskelet"></div><div class="servis-kart iskelet"></div>
</div>

<h2 class="bolum-baslik" id="zamanlayicilar-baslik">Zamanlayıcılar</h2>
<div class="kart"><table class="tablo" id="zamanlayicilar" aria-labelledby="zamanlayicilar-baslik">
  <thead><tr><th>Zamanlayıcı</th><th>Sonraki</th><th>Son çalışma</th><th>Etkin</th><th><span class="gorsel-gizli">Eylemler</span></th></tr></thead>
  <tbody><tr><td colspan="5"><div class="iskelet iskelet-satir"></div></td></tr></tbody>
</table></div>

<section class="kart soru-havuzu" id="soru-havuzu-karti" aria-labelledby="sh-baslik">
  <h2 id="sh-baslik" class="bolum-baslik">Soru havuzu</h2>
  <p class="soluk" id="sh-durum">Yükleniyor…</p>
  <div class="kapsam-cubugu" id="sh-kapsam" hidden></div>
</section>

<aside class="log-paneli" id="log-paneli" aria-labelledby="log-baslik" hidden>
  <header><h2 id="log-baslik">Log</h2>
    <label><input type="checkbox" id="log-uyari"> Yalnız uyarı ve hatalar</label>
    <button type="button" class="dugme dugme-ikincil" id="log-kopyala">Kopyala</button>
    <button type="button" class="dugme-ikon" id="log-kapat" aria-label="Log panelini kapat"><svg class="ikon"><use href="#ik-kapat"/></svg></button></header>
  <p class="son-hata" id="log-son-hata" hidden></p>
  <pre id="log-icerik" tabindex="0"></pre>
</aside>

<dialog class="pencere" id="onay-penceresi" aria-labelledby="onay-baslik">
  <h2 id="onay-baslik">Emin misiniz?</h2>
  <p id="onay-metin"></p>
  <p class="uyari-not" id="onay-uyari" hidden><svg class="ikon"><use href="#ik-uyari"/></svg> <span></span></p>
  <form method="dialog" class="pencere-dugmeler">
    <button class="dugme dugme-ikincil" value="iptal">Vazgeç</button>
    <button class="dugme" id="onay-evet" value="evet">Devam</button>
  </form>
</dialog>
{% endblock %}
{% block script %}
<script>
(function () {
  var EYLEM_ADI = {'yeniden-baslat': 'Yeniden başlat', 'durdur': 'Durdur', 'baslat': 'Başlat',
    'zamanlayici-ac': 'Aç', 'zamanlayici-kapat': 'Kapat', 'simdi-calistir': 'Şimdi çalıştır', 'hata-temizle': 'Hatayı temizle'};
  var EYLEM_IKON = {'yeniden-baslat': 'yenile', 'durdur': 'durdur', 'baslat': 'oynat', 'simdi-calistir': 'oynat', 'hata-temizle': 'onay'};
  var veri = null, logBirim = null;

  function el(etiket, sinif, metin) { var e = document.createElement(etiket); if (sinif) e.className = sinif; if (metin != null) e.textContent = metin; return e; }
  function ikon(ad) { var s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('class', 'ikon');
    var u = document.createElementNS('http://www.w3.org/2000/svg', 'use'); u.setAttribute('href', '#ik-' + ad); s.appendChild(u); return s; }
  function rozet(b) {
    var d = b.aktif_durum, m = {active: ['yesil', 'Çalışıyor'], activating: ['amber', 'Başlıyor'],
      deactivating: ['amber', 'Duruyor'], failed: ['kirmizi', 'Hata'], inactive: ['gri', 'Durdu']}[d] || ['gri', d];
    if (b.tur === 'zamanlayici' && d === 'inactive' && b.sonuc === 'success') m = ['gri', 'Bekliyor'];
    return el('span', 'rozet rozet-' + m[0], m[1]);
  }
  function zaman(t) { if (!t) return '—'; var d = new Date(t.replace(' UTC', 'Z').replace(/^\w+ /, '').replace(' ', 'T'));
    return isNaN(d) ? t : d.toLocaleString('tr-TR', {weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'}); }
  function dugme(b, eylem) {
    var x = el('button', 'dugme dugme-kucuk' + (eylem === 'durdur' ? ' dugme-tehlike' : ' dugme-ikincil'));
    x.type = 'button'; if (EYLEM_IKON[eylem]) x.appendChild(ikon(EYLEM_IKON[eylem]));
    x.appendChild(document.createTextNode(' ' + EYLEM_ADI[eylem]));
    x.addEventListener('click', function () { eylemIste(b, eylem, false); });
    return x;
  }
  function logDugme(b) { var x = el('button', 'dugme dugme-kucuk dugme-ikincil'); x.type = 'button';
    x.appendChild(ikon('log')); x.appendChild(document.createTextNode(' Log'));
    x.addEventListener('click', function () { logAc(b.birim); }); return x; }

  function ciz() {
    var kartlar = document.getElementById('servis-kartlari'); kartlar.textContent = '';
    var servisler = veri.birimler.filter(function (b) { return b.tur === 'servis'; });
    var zam = veri.birimler.filter(function (b) { return b.tur === 'zamanlayici'; });
    servisler.forEach(function (b) {
      var k = el('article', 'servis-kart' + (b.aktif_durum === 'failed' ? ' servis-kart-hata' : ''));
      var ust = el('div', 'servis-kart-ust'); ust.appendChild(el('h3', null, b.ad)); ust.appendChild(rozet(b)); k.appendChild(ust);
      k.appendChild(el('p', 'soluk kucuk', b.birim + (b.bellek_mib != null ? ' · ' + b.bellek_mib + ' MiB' : '') +
        (b.baslama ? ' · ' + zaman(b.baslama) + ' tarihinden beri' : '')));
      if (b.aktif_durum === 'failed') { var h = el('p', 'son-hata', 'Son hata yükleniyor…'); k.appendChild(h); sonHataYaz(b.birim, h); }
      var e = el('div', 'servis-eylemler');
      b.eylemler.forEach(function (a) {
        if (a === 'baslat' && b.aktif_durum === 'active') return;
        if (a === 'durdur' && b.aktif_durum !== 'active') return;
        if (a === 'hata-temizle' && b.aktif_durum !== 'failed') return;
        e.appendChild(dugme(b, a));
      });
      e.appendChild(logDugme(b)); k.appendChild(e); kartlar.appendChild(k);
    });
    var tb = document.querySelector('#zamanlayicilar tbody'); tb.textContent = '';
    zam.forEach(function (b) {
      var tr = el('tr'); var ad = el('td'); ad.appendChild(el('strong', null, b.ad)); ad.appendChild(el('div', 'soluk kucuk', b.birim)); tr.appendChild(ad);
      tr.appendChild(el('td', null, b.zamanlayici_etkin ? zaman(b.sonraki) : 'Kapalı'));
      var son = el('td'); son.appendChild(el('span', null, zaman(b.son_tetik) + ' ')); son.appendChild(rozet(b));
      if (b.aktif_durum === 'failed') { var h = el('div', 'son-hata kucuk', '…'); son.appendChild(h); sonHataYaz(b.birim, h); }
      tr.appendChild(son);
      var et = el('td'); var anahtar = el('input'); anahtar.type = 'checkbox'; anahtar.className = 'anahtar';
      anahtar.checked = !!b.zamanlayici_etkin; anahtar.setAttribute('aria-label', b.ad + ' zamanlayıcısı etkin');
      anahtar.addEventListener('change', function () { anahtar.checked = !anahtar.checked;
        eylemIste(b, b.zamanlayici_etkin ? 'zamanlayici-kapat' : 'zamanlayici-ac', false); });
      et.appendChild(anahtar); tr.appendChild(et);
      var ey = el('td', 'eylem-hucre'); ey.appendChild(dugme(b, 'simdi-calistir'));
      if (b.aktif_durum === 'failed') ey.appendChild(dugme(b, 'hata-temizle'));
      ey.appendChild(logDugme(b)); tr.appendChild(ey); tb.appendChild(tr);
    });
    var calisan = servisler.filter(function (b) { return b.aktif_durum === 'active'; }).length;
    var sorunlu = veri.birimler.filter(function (b) { return b.aktif_durum === 'failed'; }).length;
    document.getElementById('kpi-calisan').textContent = calisan + '/' + servisler.length;
    var s = document.getElementById('kpi-sorunlu'); s.textContent = sorunlu; s.className = sorunlu ? 'metin-kirmizi' : '';
    var siradaki = zam.filter(function (b) { return b.zamanlayici_etkin && b.sonraki; })
      .sort(function (a, b2) { return new Date(zaman(a.sonraki)) - new Date(zaman(b2.sonraki)); })[0];
    document.getElementById('kpi-siradaki').textContent = siradaki ? siradaki.ad.replace(/ \(.*\)$/, '') + ' · ' + zaman(siradaki.sonraki) : '—';
    document.getElementById('ders-saati-rozeti').hidden = !veri.ders_saati;
    soruHavuzu(zam.filter(function (b) { return b.birim === 'soru-havuzu-uret'; })[0]);
  }
  function soruHavuzu(b) {
    var d = document.getElementById('sh-durum');
    if (!b) { d.textContent = 'Soru havuzu zamanlayıcısı bulunamadı.'; return; }
    d.textContent = (b.zamanlayici_etkin ? 'Açık — sonraki çalışma ' + zaman(b.sonraki) : 'Kapalı — gece üretimi çalışmaz') +
      (b.aktif_durum === 'active' ? ' · şu an üretiyor' : '') + (b.aktif_durum === 'failed' ? ' · son çalışma hatayla bitti' : '');
    var k = veri.kapsam, c = document.getElementById('sh-kapsam');
    if (!k || !k.plan_haftasi) { c.hidden = true; return; }
    c.hidden = false; c.textContent = '';
    [['yeterli', 'yesil', 'Yeterli'], ['zayif', 'amber', 'Zayıf'], ['bos', 'kirmizi', 'Boş']].forEach(function (p) {
      var dilim = el('span', 'kapsam-dilim kapsam-' + p[1]); dilim.style.flexGrow = k[p[0]];
      dilim.title = p[2] + ': ' + k[p[0]] + ' hafta-kazanım'; c.appendChild(dilim); });
    c.appendChild(el('span', 'kapsam-etiket soluk kucuk', 'Kazanım kapsamı: ' + k.yeterli + ' yeterli · ' + k.zayif + ' zayıf · ' + k.bos + ' boş (' + k.plan_haftasi + ')'));
  }
  function sonHataYaz(birim, hedef) {
    fetch('/api/servisler/log/' + encodeURIComponent(birim)).then(function (r) { return r.json(); })
      .then(function (j) { hedef.textContent = j.son_hata ? 'Son hata: ' + j.son_hata : 'Hata satırı bulunamadı; Log\'a bakın.'; })
      .catch(function () { hedef.textContent = 'Son hata okunamadı.'; });
  }
  function yukle() {
    return fetch('/api/servisler').then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (j) { veri = j; ciz(); })
      .catch(function () { document.getElementById('servis-kartlari').textContent = 'Servis durumu alınamadı. Sayfayı yenileyin.'; });
  }
  function eylemIste(b, eylem, onay) {
    var p = document.getElementById('onay-penceresi');
    document.getElementById('onay-metin').textContent = b.ad + ' — ' + EYLEM_ADI[eylem] + '. ' + (b.aciklama || '');
    var u = document.getElementById('onay-uyari'); u.hidden = true;
    p.returnValue = ''; p.showModal();
    p.onclose = function () {
      if (p.returnValue !== 'evet') return;
      gonder(b, eylem, onay);
    };
  }
  function gonder(b, eylem, onay) {
    fetch('/api/servisler/eylem', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({birim: b.birim, eylem: eylem, onay: onay})})
      .then(function (r) { return r.json().then(function (j) { return {s: r.status, j: j}; }); })
      .then(function (x) {
        if (x.s === 409) {   // ders saati: ikinci onay
          var p = document.getElementById('onay-penceresi'), u = document.getElementById('onay-uyari');
          u.hidden = false; u.querySelector('span').textContent = x.j.onay_gerekli;
          document.getElementById('onay-evet').textContent = 'Yine de ' + EYLEM_ADI[eylem].toLowerCase();
          p.returnValue = ''; p.showModal();
          p.onclose = function () { document.getElementById('onay-evet').textContent = 'Devam';
            if (p.returnValue === 'evet') gonder(b, eylem, true); };
          return;
        }
        if (x.s >= 400) { window.farabiToast((x.j && x.j.detail) || 'İşlem reddedildi.'); return; }
        window.farabiToast(x.j.ok ? b.ad + ': ' + EYLEM_ADI[eylem].toLowerCase() + ' tamam.' : b.ad + ': başarısız — ' + x.j.mesaj);
        if (b.birim === 'farabi-yoklama-dashboard' && x.j.ok) return yenidenBaglan();
        setTimeout(yukle, 1500);
      }).catch(function () { window.farabiToast('Sunucuya ulaşılamadı.'); });
  }
  function yenidenBaglan() {
    window.farabiToast('Pano yeniden başlıyor, bağlantı bekleniyor…');
    var deneme = 0, t = setInterval(function () {
      fetch('/api/servisler').then(function (r) { if (r.ok) { clearInterval(t); location.reload(); } }).catch(function () {});
      if (++deneme > 20) { clearInterval(t); window.farabiToast('Pano geri dönmedi; sayfayı elle yenileyin.'); }
    }, 3000);
  }
  function logAc(birim) {
    logBirim = birim; var p = document.getElementById('log-paneli'); p.hidden = false;
    document.getElementById('log-baslik').textContent = 'Log — ' + birim; logYukle();
    document.getElementById('log-kapat').focus();
  }
  function logYukle() {
    var pre = document.getElementById('log-icerik'); pre.textContent = 'Yükleniyor…';
    var uyari = document.getElementById('log-uyari').checked ? 1 : 0;
    fetch('/api/servisler/log/' + encodeURIComponent(logBirim) + '?yalniz_uyari=' + uyari)
      .then(function (r) { return r.json(); }).then(function (j) {
        pre.textContent = j.satirlar.length ? j.satirlar.join('\n') : 'Bu birim için log satırı yok.';
        var h = document.getElementById('log-son-hata'); h.hidden = !j.son_hata; h.textContent = j.son_hata ? 'Son hata: ' + j.son_hata : '';
        pre.scrollTop = pre.scrollHeight;
      }).catch(function () { pre.textContent = 'Log okunamadı.'; });
  }
  document.getElementById('log-uyari').addEventListener('change', logYukle);
  document.getElementById('log-kapat').addEventListener('click', function () { document.getElementById('log-paneli').hidden = true; });
  document.getElementById('log-kopyala').addEventListener('click', function () {
    navigator.clipboard && navigator.clipboard.writeText(document.getElementById('log-icerik').textContent)
      .then(function () { window.farabiToast('Log kopyalandı.'); }); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') document.getElementById('log-paneli').hidden = true; });
  document.getElementById('yenile').addEventListener('click', yukle);
  yukle(); setInterval(function () { if (!document.hidden) yukle(); }, 30000);
  if (location.hash === '#zamanlayicilar') document.getElementById('zamanlayicilar-baslik').scrollIntoView();
})();
</script>
{% endblock %}
```
Kontrol: `kpi-satir`, `kpi`, `rozet`, `rozet-yesil|amber|kirmizi|gri`, `dugme`, `dugme-ikincil`, `dugme-kucuk`, `tablo`, `kart`, `iskelet`, `soluk`, `kucuk`, `bolum-baslik`, `toast` sınıflarının pano.css'te var olup olmadığını `grep` ile bak; olanı kullan, olmayanı Step 3'te tanımla (ad uydurma — var olan eşdeğer sınıf varsa onu kullan ve şablonu ona göre düzelt).

- [ ] **Step 3: Sayfa CSS'i** (pano.css sonuna; yalnız eksik sınıflar):
```css
/* ---------- Servis yönetimi (2026-10-08) ---------- */
.servis-izgara { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; padding: 0 1.5rem; }
.servis-kart { background: var(--renk-yuzey); border: 1px solid var(--renk-kenar); border-radius: var(--yaricap-buyuk);
  padding: 1rem; box-shadow: var(--renk-golge); display: flex; flex-direction: column; gap: 0.5rem; transition: box-shadow 0.12s; }
.servis-kart:hover { box-shadow: var(--renk-golge-kart); }
.servis-kart-hata { border-color: var(--renk-kirmizi); }
.servis-kart-ust { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
.servis-kart-ust h3 { margin: 0; font-size: 1rem; }
.servis-eylemler, .eylem-hucre { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: auto; }
.son-hata { color: var(--renk-kirmizi); background: var(--renk-kirmizi-zemin); border-radius: 6px; padding: 0.35rem 0.5rem;
  font-family: ui-monospace, monospace; font-size: 0.8rem; overflow-wrap: anywhere; }
.log-paneli { position: fixed; top: 40px; right: 0; bottom: 0; width: min(100vw, 720px); background: var(--renk-yuzey);
  border-left: 1px solid var(--renk-kenar); box-shadow: var(--renk-golge-yukseltilmis); z-index: 45; display: flex; flex-direction: column; }
.log-paneli header { display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem 1rem; border-bottom: 1px solid var(--renk-kenar); }
.log-paneli header h2 { margin: 0 auto 0 0; font-size: 1rem; }
.log-paneli pre { flex: 1; margin: 0; overflow: auto; padding: 0.75rem 1rem; font-size: 0.78rem; line-height: 1.45;
  background: var(--renk-yuzey-2); color: var(--renk-metin); white-space: pre-wrap; overflow-wrap: anywhere; }
.log-paneli .son-hata { margin: 0.5rem 1rem; }
.uyari-not { display: flex; gap: 0.4rem; align-items: flex-start; color: var(--renk-amber); background: var(--renk-amber-zemin);
  border-radius: 6px; padding: 0.5rem 0.6rem; }
.pencere-dugmeler { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem; }
.kapsam-cubugu { display: flex; flex-wrap: wrap; align-items: center; gap: 0; border-radius: 999px; overflow: hidden; }
.kapsam-dilim { height: 10px; min-width: 2px; }
.kapsam-yesil { background: var(--renk-yesil); } .kapsam-amber { background: var(--renk-amber); } .kapsam-kirmizi { background: var(--renk-kirmizi); }
.kapsam-etiket { flex-basis: 100%; margin-top: 0.4rem; }
.anahtar { width: 2.4rem; height: 1.3rem; accent-color: var(--renk-birincil); cursor: pointer; }
@media (max-width: 720px) { .servis-izgara { padding: 0 1rem; } .log-paneli { top: 0; width: 100vw; } }
```

- [ ] **Step 4: Yeşil + elle**

Run: `venv/bin/python -m unittest discover -p 'test_*.py'` → OK.
Elle (8011 geçici süreç; eylemler sudo betiği kurulmadan "izin yok" döner — beklenen): kartlar/tablo/soru havuzu kartı görünür, `soru-havuzu-uret` failed ise "Son hata: …" görünür, Log paneli açılır/kapanır, Esc kapatır, 375 px'te taşma yok, üç tema.

- [ ] **Step 5: Commit**
```bash
git add tahtayoklama/dashboard/templates/servisler.html tahtayoklama/dashboard/static/pano.css tahtayoklama/dashboard/test_servis_yonetimi.py
git commit -m "dashboard: /servisler sayfası — kartlar, zamanlayıcılar, log paneli, ders saati onayı, soru havuzu kartı"
```

---

### Task 7: Kurulum, canlıya alma, belgeler

**Files:**
- Modify: `tahtayoklama/CLAUDE.md` (Frontend standartları: menü çubuğu tek kaynak `menu.py`; ikon sayısı; `prefers-reduced-motion` artık var; §5'e `/servisler`)
- Modify: `DECISIONS.md` (en üste kayıt)
- Modify: `CLAUDE.md` kök (mimari tablosunda dashboard satırına `/servisler` + `farabi-servis`)

- [ ] **Step 1: Betik + sudoers kur (Opus/kullanıcı onayıyla — canlı sistem)**
```bash
cd /home/ata/farabi/tahtayoklama/dashboard
sudo install -o root -g root -m 755 scripts/farabi-servis /usr/local/sbin/farabi-servis
sudo install -o root -g root -m 440 scripts/farabi-servis.sudoers /etc/sudoers.d/farabi-servis
sudo visudo -c -f /etc/sudoers.d/farabi-servis
sudo -n /usr/local/sbin/farabi-servis sil farabi-api; echo "çıkış=$?"   # 2 beklenir
```

- [ ] **Step 2: Dashboard'u yeniden başlat** (kullanıcıya haber ver; ders saati dışında tercih et)
```bash
sudo systemctl restart farabi-yoklama-dashboard.service && sleep 3 && systemctl is-active farabi-yoklama-dashboard.service
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/servisler   # 303 (oturumsuz → /giris)
```

- [ ] **Step 3: Canlı uçtan uca (ders saati dışında)**
  - `/servisler` → `sinif-arena` "Yeniden başlat" → onay → toast "tamam", rozet yeşil; `uzaktan_denetim`'de `servis-yeniden-baslat` satırı:
    `venv/bin/python -c "import db;c=db.baglanti();print([dict(r) for r in c.execute(\"select * from uzaktan_denetim where kaynak='servisler' order by rowid desc limit 1\")])"`
  - `soru-havuzu-uret` zamanlayıcısını kapat → `systemctl is-enabled soru-havuzu-uret.timer` = disabled → tekrar aç → enabled.
  - Pano kendi restart'ı: "Yeniden başlat" → "bağlantı bekleniyor" → sayfa kendiliğinden yenilenir.

- [ ] **Step 4: Belgeler + commit + push**

DECISIONS.md kaydı (format: `## 2026-10-08 - ...` + 2-4 madde: neden betik, liste iki yerde ve test, ders saati kuralı, kapsam dışı).
```bash
git add tahtayoklama/CLAUDE.md DECISIONS.md CLAUDE.md
git commit -m "docs: dashboard menü çubuğu + /servisler (farabi-servis, sudoers)"
git push origin master
```
