# Tahta Gece/Sabah Bakımı Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Her gün 21:00'de 8 Farabi tahtasının loglarını tarayıp dashboard'a yazan, tahtaları yeniden başlatıp karartma + ekran kapatma + CPU tasarrufu uygulayan; 07:00'de yeniden başlatıp yüksek performansa alan zamanlanmış bakım.

**Architecture:** `tahtayoklama/dashboard/tahta_bakim.py` modülü (saf karar fonksiyonları + SQLite kayıt + asyncio SSH akışı) dashboard'un mevcut `ssh_istemci`/`tahta_kaydi`/`zil`/`uzaktan_yonetim` kodunu yeniden kullanır. `scripts/tahta_bakim.py` CLI'ı iki systemd timer'dan (sunucu UTC, timer `Europe/Istanbul`) çağrılır — dashboard sürecinin içinde KOŞMAZ. Dashboard yalnızca `tahta_bakim` tablosunu okuyup `/sistem-durumu` sayfasında gösterir.

**Tech Stack:** Python 3 stdlib (asyncio, sqlite3, fcntl, argparse), FastAPI (mevcut), Jinja2 şablonu + vanilla JS (mevcut), systemd timer. Yeni kütüphane YOK.

**Spec:** `docs/superpowers/specs/2026-09-28-tahta-gece-sabah-bakim-design.md`

## Global Constraints

- Test çatısı **`unittest`**, pytest DEĞİL (dashboard venv'inde pytest yok). Komutlar `tahtayoklama/dashboard/` içinden: `venv/bin/python -m unittest test_tahta_bakim -v`.
- Dashboard venv'inde **httpx yok** → `TestClient` kullanılamaz; endpoint testleri `test_api_durum.py` desenindeki gibi route fonksiyonunu sahte `Request` ile doğrudan çağırır.
- Hedef tahtalar: `tahta_kaydi.tahtalari_yukle()` çıktısından adı `tahta-` ile başlayanlar HARİÇ (8 tahta: 9-A, 9-B, 10-A, 11-A, 11-B, 12-A, 12-B, fenlab).
- Saatler DB'de UTC (`datetime('now')`), yalnızca gösterimde `Europe/Istanbul`'a çevrilir.
- Timer'lar: `OnCalendar=*-*-* 21:00:00 Europe/Istanbul` ve `*-*-* 07:00:00 Europe/Istanbul`, `Persistent=false`.
- Gece modu: governor `ondemand`, `scaling_max_freq` ← `cpuinfo_min_freq`; `eta-screen-cover` tam ekran; `xset dpms force off`.
- Sabah modu: governor `performance`, `scaling_max_freq` ← `cpuinfo_max_freq`; karartma kaldır; `xset dpms force on`.
- Reboot sonrası bekleme en fazla 360 sn, 5 sn aralık; X oturumu için en fazla 90 sn.
- **`ogretmen` sistem journal'ını OKUYAMAZ** (2026-09-29'da 9-B'de doğrulandı: `adm`/`systemd-journal` grubunda değil). Journal sorguları `etapadmin` + sudo ile koşar. Root komutları: önce `sudo -n`, olmazsa `gizli.json::etapadmin_sifre` ile `sudo -S -p ''`.
- Yeni CSS sınıfı/renk yok; `pano.css` token'ları ve mevcut `servis-tablo`, `durum-rozet`, `bilgi-kart`, `iki-sutun`, `rapor-aciklama` sınıfları kullanılır. Arayüz metni Türkçe, cümle düzeninde.
- Ruff: yalnızca dokunulan dosyalar (`.venv-tools/bin/ruff check <dosya>`), taban çizgisi farkı okunur.
- Kural 3 (tek seferde tek modül): her görev tek sorumluluğa dokunur; `uzaktan_yonetim.py` DEĞİŞTİRİLMEZ, yalnızca iki fonksiyonu çağrılır.

## Review Focus

- **Eski oturuma "geri geldi" sanmak:** reboot komutu döndükten hemen sonra SSH hâlâ eski oturuma cevap verebilir. Beklenen: yalnızca `boot_id` DEĞİŞİNCE "geri geldi" sayılır → Task 3 `test_geri_gelmesini_bekle_ayni_boot_id_geri_gelmis_saymaz`.
- **Teneffüste/okul saatinde elle çalıştırma:** spec'teki "ders sürüyor" kilidi teneffüsü korumuyordu. Beklenen: okul günü 08:10–15:50 arası (zil.json ilk ders başı–son ders sonu) HİÇBİR tahta yeniden başlatılmaz → Task 1 `test_okul_saati_kilidi_teneffuste_de_aktif`, Task 3 `test_okul_saatinde_reboot_atlanir`. (Spec'ten bilinçli sapma: kilit "şu anki ders" yerine "okul saatleri penceresi".)
- **Sudo parolası yok / NOPASSWD yok:** beklenen: CPU adımı `hata` olarak raporlanır ama karartma + DPMS yine denenir, tahta yarım bırakılmaz → Task 3 `test_gece_modu_cpu_basarisiz_karartma_yine_denenir`.
- **X oturumu gelmeyen tahta (9-A, otomatik giriş yok):** beklenen: karartma/DPMS atlanır, detaya not düşülür, durum `hata` DEĞİL → Task 3 `test_gece_modu_x_oturumu_yoksa_not_duser`.
- **Önceki açılış journal'da yok (ilk açılış/journal silinmiş):** beklenen: `bilinmiyor`, kritik bulgu ÜRETİLMEZ → Task 1 `test_onceki_acilis_bilinmiyor`.

---

## File Structure

| Dosya | Durum | Sorumluluk |
|---|---|---|
| `tahtayoklama/dashboard/tahta_bakim.py` | Create | Saf karar fonksiyonları (log sınıflandırma, temiz kapanma, okul saati kilidi, hedef filtre, durum) + `tahta_bakim` tablosu okuma/yazma + SSH akışı (`tahta_isle`, `calistir`) |
| `tahtayoklama/dashboard/test_tahta_bakim.py` | Create | Tüm `tahta_bakim` testleri (unittest) |
| `tahtayoklama/dashboard/db.py` | Modify (`SEMA` sonu) | `tahta_bakim` tablosu |
| `tahtayoklama/dashboard/scripts/tahta_bakim.py` | Create | CLI + `flock` kilidi |
| `tahtayoklama/dashboard/systemd/farabi-tahta-{gece,sabah}.{service,timer}` | Create | Birim dosyalarının repo kopyası |
| `tahtayoklama/dashboard/app.py` | Modify | `GET /api/tahta-bakim` |
| `tahtayoklama/dashboard/templates/sistem_durumu.html` | Modify | "Tahta bakımı" bölümü + JS |
| `tahtayoklama/CLAUDE.md`, kök `CLAUDE.md`, `DECISIONS.md` | Modify | Belgeleme (Task 6) |

---

### Task 1: Saf karar fonksiyonları

**Files:**
- Create: `tahtayoklama/dashboard/tahta_bakim.py`
- Test: `tahtayoklama/dashboard/test_tahta_bakim.py`

**Interfaces:**
- Consumes: `zil.okul_gunu_mu(date) -> bool`, `zil.ilk_ders_saati() -> time | None`, `zil.son_ders_bitis_saati() -> time | None`
- Produces:
  - `log_siniflandir(metin: str) -> tuple[list[str], list[str]]` — (kritik, uyari)
  - `onceki_acilis_durumu(metin: str) -> str` — `"temiz" | "kirli" | "bilinmiyor"`
  - `farabi_log_ayristir(metin: str) -> str | None`
  - `okul_saati_mi(simdi: datetime) -> bool`
  - `hedef_tahtalar(tahtalar: list[dict], tek: str | None = None) -> list[dict]` (bulunamazsa `ValueError`)
  - `durum_belirle(kritik: list[str], hatalar: list[str]) -> str` — `"hata" | "kritik" | "tamam"`
  - `utc_to_istanbul(metin: str | None) -> str | None` — `"YYYY-MM-DD HH:MM:SS"` UTC → `"YYYY-MM-DD HH:MM"` İstanbul

- [ ] **Step 1: Write the failing tests**

`tahtayoklama/dashboard/test_tahta_bakim.py`:

```python
"""tahta_bakim.py testleri — unittest (dashboard venv'inde pytest yok).
Çalıştırma: venv/bin/python -m unittest test_tahta_bakim -v"""

import asyncio
import importlib.util
import json
import unittest
from datetime import datetime, time as dtime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import db
import ssh_istemci
import tahta_bakim

IST = ZoneInfo("Europe/Istanbul")


class TestLogSiniflandir(unittest.TestCase):
    def test_kritik_kaliplar_etiketlenir_ve_sayilir(self):
        metin = (
            "2026-09-28T10:00:00+0300 vestel9b kernel: watchdog: BUG: soft lockup - CPU#1 stuck for 22s!\n"
            "2026-09-28T10:00:05+0300 vestel9b kernel: watchdog: BUG: soft lockup - CPU#1 stuck for 48s!\n"
            "2026-09-28T11:00:00+0300 vestel9b kernel: blk_update_request: I/O error, dev sda, sector 123\n"
        )
        kritik, uyari = tahta_bakim.log_siniflandir(metin)
        self.assertEqual(len(kritik), 2)
        self.assertTrue(kritik[0].startswith("CPU soft lockup (donma) (2×): "))
        self.assertTrue(kritik[1].startswith("Disk G/Ç hatası (1×): "))
        self.assertEqual(uyari, [])

    def test_eslesmeyen_satir_uyari_olur(self):
        kritik, uyari = tahta_bakim.log_siniflandir("2026-09-28T10:00:00+0300 h kernel: ACPI Error: AE_NOT_FOUND\n")
        self.assertEqual(kritik, [])
        self.assertEqual(len(uyari), 1)
        self.assertIn("ACPI Error", uyari[0])

    def test_tekrarlanan_satir_bir_kez_sayilir(self):
        satir = "2026-09-28T10:00:00+0300 h kernel: ACPI Error: AE_NOT_FOUND"
        _, uyari = tahta_bakim.log_siniflandir(f"{satir}\n{satir}\n")
        self.assertEqual(len(uyari), 1)

    def test_uyari_sayisi_sinirlanir(self):
        metin = "\n".join(f"2026-09-28T10:00:{i:02d}+0300 h x: hata {i}" for i in range(20))
        _, uyari = tahta_bakim.log_siniflandir(metin)
        self.assertEqual(len(uyari), tahta_bakim.MAKS_UYARI_ORNEK + 1)
        self.assertEqual(uyari[-1], "… ve 15 satır daha")

    def test_bos_ve_bilgi_satirlari_atlanir(self):
        kritik, uyari = tahta_bakim.log_siniflandir("\n-- No entries --\nHint: bir şey\n")
        self.assertEqual((kritik, uyari), ([], []))

    def test_cinnamon_segfault_kritik_diger_segfault_uyari(self):
        kritik, uyari = tahta_bakim.log_siniflandir(
            "t h kernel: cinnamon[1234]: segfault at 0 ip 00007f sp 00007f error 4\n"
            "t h kernel: foo[99]: segfault at 0 ip 1 sp 2 error 4\n"
        )
        self.assertEqual(len(kritik), 1)
        self.assertIn("Masaüstü çöktü", kritik[0])
        self.assertEqual(len(uyari), 1)


class TestOncekiAcilis(unittest.TestCase):
    def test_temiz_kapanma(self):
        metin = (
            "Eyl 28 23:13:03 vestel9b systemd[1]: Reached target reboot.target - System Reboot.\n"
            "Eyl 28 23:13:03 vestel9b systemd-shutdown[1]: Syncing filesystems and block devices.\n"
        )
        self.assertEqual(tahta_bakim.onceki_acilis_durumu(metin), "temiz")

    def test_kirli_kapanma(self):
        metin = "Eyl 28 12:00:00 vestel9b cinnamon[900]: bir şey oldu\nEyl 28 12:00:01 vestel9b kernel: usb 1-1: new device\n"
        self.assertEqual(tahta_bakim.onceki_acilis_durumu(metin), "kirli")

    def test_onceki_acilis_bilinmiyor(self):
        self.assertEqual(tahta_bakim.onceki_acilis_durumu(""), "bilinmiyor")
        self.assertEqual(
            tahta_bakim.onceki_acilis_durumu("Data from the specified boot (-1) is not available: No such boot ID in journal\n"),
            "bilinmiyor",
        )


class TestFarabiLog(unittest.TestCase):
    def test_log_yok(self):
        self.assertIsNone(tahta_bakim.farabi_log_ayristir("YOK\n"))

    def test_sifir_hata(self):
        self.assertIsNone(tahta_bakim.farabi_log_ayristir("0\n"))

    def test_hata_var(self):
        ozet = tahta_bakim.farabi_log_ayristir("3\n2026-09-28 10:00:00 | ERROR   | farabi.main | bağlantı koptu\n")
        self.assertEqual(ozet, "Farabi client: bugün 3 ERROR satırı (son: 2026-09-28 10:00:00 | ERROR   | farabi.main | bağlantı koptu)")

    def test_bozuk_cikti(self):
        self.assertIsNone(tahta_bakim.farabi_log_ayristir("bash: hata\n"))


class TestOkulSaati(unittest.TestCase):
    def _zil(self):
        return (
            patch.object(tahta_bakim.zil, "okul_gunu_mu", side_effect=lambda g: g.isoweekday() <= 5),
            patch.object(tahta_bakim.zil, "ilk_ders_saati", return_value=dtime(8, 10)),
            patch.object(tahta_bakim.zil, "son_ders_bitis_saati", return_value=dtime(15, 50)),
        )

    def _kontrol(self, simdi):
        a, b, c = self._zil()
        with a, b, c:
            return tahta_bakim.okul_saati_mi(simdi)

    def test_gece_21_kilit_yok(self):
        self.assertFalse(self._kontrol(datetime(2026, 9, 29, 21, 0, tzinfo=IST)))

    def test_sabah_07_kilit_yok(self):
        self.assertFalse(self._kontrol(datetime(2026, 9, 29, 7, 0, tzinfo=IST)))

    def test_okul_saati_kilidi_teneffuste_de_aktif(self):
        # 08:50–09:00 arası teneffüs: simdiki_ders None olur ama kilit yine aktif.
        self.assertTrue(self._kontrol(datetime(2026, 9, 29, 8, 55, tzinfo=IST)))

    def test_hafta_sonu_kilit_yok(self):
        self.assertFalse(self._kontrol(datetime(2026, 10, 3, 10, 0, tzinfo=IST)))  # Cumartesi


class TestHedefVeDurum(unittest.TestCase):
    TAHTALAR = [
        {"ad": "9-A", "ip": "1", "kullanici": "ogretmen", "admin": "etapadmin"},
        {"ad": "fenlab", "ip": "2", "kullanici": "ogretmen", "admin": "etapadmin"},
        {"ad": "tahta-234", "ip": "3", "kullanici": "ogretmen", "admin": "etapadmin"},
    ]

    def test_tahta_nnn_haric(self):
        self.assertEqual([t["ad"] for t in tahta_bakim.hedef_tahtalar(self.TAHTALAR)], ["9-A", "fenlab"])

    def test_tek_tahta(self):
        self.assertEqual([t["ad"] for t in tahta_bakim.hedef_tahtalar(self.TAHTALAR, "fenlab")], ["fenlab"])

    def test_tek_tahta_bilinmiyor(self):
        with self.assertRaises(ValueError):
            tahta_bakim.hedef_tahtalar(self.TAHTALAR, "tahta-234")

    def test_durum_belirle(self):
        self.assertEqual(tahta_bakim.durum_belirle([], []), "tamam")
        self.assertEqual(tahta_bakim.durum_belirle(["x"], []), "kritik")
        self.assertEqual(tahta_bakim.durum_belirle(["x"], ["y"]), "hata")

    def test_utc_to_istanbul(self):
        self.assertEqual(tahta_bakim.utc_to_istanbul("2026-09-29 18:00:05"), "2026-09-29 21:00")
        self.assertIsNone(tahta_bakim.utc_to_istanbul(None))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run (`tahtayoklama/dashboard/` içinde): `venv/bin/python -m unittest test_tahta_bakim -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tahta_bakim'`

- [ ] **Step 3: Write minimal implementation**

`tahtayoklama/dashboard/tahta_bakim.py`:

```python
"""Tahta gece/sabah bakımı — bkz. docs/superpowers/specs/
2026-09-28-tahta-gece-sabah-bakim-design.md.

systemd timer'larından (farabi-tahta-{gece,sabah}.timer) scripts/
tahta_bakim.py üzerinden çağrılır; dashboard sürecinin İÇİNDE koşmaz.
Dashboard yalnızca tahta_bakim tablosunu okur (son_calismalar).

Journal sorguları etapadmin+sudo ile yapılır: ogretmen adm/systemd-journal
grubunda değil, sistem journal'ını göremiyor (2026-09-29, 9-B'de doğrulandı).
"""

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import zil

ISTANBUL = ZoneInfo("Europe/Istanbul")

MAKS_UYARI_ORNEK = 5
_ORNEK_UZUNLUK = 160

KRITIK_KALIPLAR: list[tuple[re.Pattern, str]] = [
    (re.compile(r"soft lockup", re.I), "CPU soft lockup (donma)"),
    (re.compile(r"blocked for more than \d+ seconds", re.I), "Görev takıldı (hung task)"),
    (re.compile(r"Machine Check|mce: \[Hardware Error\]", re.I), "Donanım hatası (MCE)"),
    (re.compile(r"I/O error", re.I), "Disk G/Ç hatası"),
    (re.compile(r"EXT4-fs error", re.I), "Dosya sistemi hatası"),
    (re.compile(r"Out of memory|oom-kill", re.I), "Bellek tükendi (OOM)"),
    (re.compile(r"GPU HANG|i915.*(hang|reset)", re.I), "GPU takıldı"),
    (re.compile(r"(Xorg|cinnamon|muffin)\[\d+\]: segfault", re.I), "Masaüstü çöktü (segfault)"),
]

_KAPANIS_RE = re.compile(
    r"systemd-shutdown\[1\]|Reached target (reboot|poweroff|halt|shutdown)\.target"
    r"|System is (rebooting|powering down)",
    re.I,
)


def log_siniflandir(metin: str) -> tuple[list[str], list[str]]:
    """journalctl çıktısını kritik/uyarı listelerine ayırır. Aynı satır
    (kernel sorgusu + sistem sorgusu iki kez getirebilir) bir kez sayılır;
    kritikler etiket başına tek örnek + adet, uyarılar ilk MAKS_UYARI_ORNEK."""
    kritik_sayac: dict[str, list] = {}
    uyarilar: list[str] = []
    gorulen: set[str] = set()
    for satir in metin.splitlines():
        satir = satir.strip()
        if not satir or satir.startswith("--") or satir.startswith("Hint:") or satir in gorulen:
            continue
        gorulen.add(satir)
        for kalip, etiket in KRITIK_KALIPLAR:
            if kalip.search(satir):
                kayit = kritik_sayac.setdefault(etiket, [0, satir[:_ORNEK_UZUNLUK]])
                kayit[0] += 1
                break
        else:
            uyarilar.append(satir[:_ORNEK_UZUNLUK])
    kritik = [f"{etiket} ({sayi}×): {ornek}" for etiket, (sayi, ornek) in kritik_sayac.items()]
    if len(uyarilar) > MAKS_UYARI_ORNEK:
        fazla = len(uyarilar) - MAKS_UYARI_ORNEK
        uyarilar = uyarilar[:MAKS_UYARI_ORNEK] + [f"… ve {fazla} satır daha"]
    return kritik, uyarilar


def onceki_acilis_durumu(metin: str) -> str:
    """`journalctl -b -1 -n 80` çıktısı: kapanış izi varsa 'temiz', yoksa
    'kirli' (donma/elektrik kesintisi şüphesi). Önceki açılış journal'da
    yoksa 'bilinmiyor' — kritik sayılmaz."""
    if not metin.strip() or "not available" in metin or "No entries" in metin:
        return "bilinmiyor"
    return "temiz" if _KAPANIS_RE.search(metin) else "kirli"


def farabi_log_ayristir(metin: str) -> str | None:
    """FARABI_LOG_KOMUTU çıktısı: 1. satır bugünkü ERROR/CRITICAL sayısı
    (ya da 'YOK'), 2. satır son hata satırı."""
    satirlar = metin.strip().splitlines()
    if not satirlar or satirlar[0].strip() == "YOK":
        return None
    try:
        sayi = int(satirlar[0].strip())
    except ValueError:
        return None
    if sayi == 0:
        return None
    son = satirlar[1].strip()[:_ORNEK_UZUNLUK] if len(satirlar) > 1 else ""
    return f"Farabi client: bugün {sayi} ERROR satırı" + (f" (son: {son})" if son else "")


def okul_saati_mi(simdi: datetime) -> bool:
    """Okul günü ilk ders başı – son ders sonu arası (teneffüsler DAHİL) —
    bu pencerede hiçbir tahta yeniden başlatılmaz (Kural 2). 21:00 ve 07:00
    bu pencerenin dışında; kilit elle çalıştırmaya/saat kaymasına karşı."""
    if not zil.okul_gunu_mu(simdi.date()):
        return False
    ilk, son = zil.ilk_ders_saati(), zil.son_ders_bitis_saati()
    if ilk is None or son is None:
        return False
    return ilk <= simdi.time() < son


def hedef_tahtalar(tahtalar: list[dict], tek: str | None = None) -> list[dict]:
    """Sınıfı atanmamış `tahta-NNN` kayıtları hariç (Farabi client'ı yok)."""
    hedefler = [t for t in tahtalar if not t["ad"].startswith("tahta-")]
    if tek is None:
        return hedefler
    secilen = [t for t in hedefler if t["ad"] == tek]
    if not secilen:
        raise ValueError(f"'{tek}' bakım hedefi değil (server/tahtalar.json'da yok ya da tahta-NNN).")
    return secilen


def durum_belirle(kritik: list[str], hatalar: list[str]) -> str:
    if hatalar:
        return "hata"
    return "kritik" if kritik else "tamam"


def utc_to_istanbul(metin: str | None) -> str | None:
    if not metin:
        return None
    utc = datetime.strptime(metin, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return utc.astimezone(ISTANBUL).strftime("%Y-%m-%d %H:%M")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m unittest test_tahta_bakim -v`
Expected: PASS (22 test)

- [ ] **Step 5: Lint + commit**

```bash
cd /home/ata/farabi
.venv-tools/bin/ruff check tahtayoklama/dashboard/tahta_bakim.py tahtayoklama/dashboard/test_tahta_bakim.py
git add tahtayoklama/dashboard/tahta_bakim.py tahtayoklama/dashboard/test_tahta_bakim.py
git commit -m "tahtayoklama/dashboard: tahta bakimi - log siniflandirma ve karar fonksiyonlari"
```

---

### Task 2: `tahta_bakim` tablosu ve kayıt fonksiyonları

**Files:**
- Modify: `tahtayoklama/dashboard/db.py` (`SEMA` string'inin sonu, `oturumlar` tablosundan sonra)
- Modify: `tahtayoklama/dashboard/tahta_bakim.py`
- Test: `tahtayoklama/dashboard/test_tahta_bakim.py`

**Interfaces:**
- Consumes: `db.baglanti()`, `db.semayi_kur()`, `db.DB_YOLU`, Task 1'deki `utc_to_istanbul`
- Produces:
  - `kayit_ac(calisma_id: str, mod: str, tahta_adi: str) -> int`
  - `kayit_guncelle(kayit_id: int, *, durum: str, kritik: list[str], uyari: list[str], detay: str, bitti: bool) -> None`
  - `son_calismalar() -> dict` — `{"gece": dict | None, "sabah": dict | None}`; her biri `{"calisma_id": str, "mod": str, "kuru": bool, "baslangic": str, "tahtalar": [{"tahta_adi", "durum", "kritik": list, "uyari": list, "detay", "baslangic", "bitis"}]}`

- [ ] **Step 1: Write the failing tests** — `test_tahta_bakim.py` sonuna (`if __name__` bloğundan önce) ekle:

```python
class TestKayit(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._eski_db_yolu = db.DB_YOLU
        db.DB_YOLU = Path(self._tmp.name) / "test.db"
        db.semayi_kur()

    def tearDown(self):
        db.DB_YOLU = self._eski_db_yolu
        self._tmp.cleanup()

    def test_ac_guncelle_ve_oku(self):
        kid = tahta_bakim.kayit_ac("c1", "gece", "9-B")
        tahta_bakim.kayit_guncelle(kid, durum="kritik", kritik=["Disk G/Ç hatası (1×): x"], uyari=["u"], detay="d", bitti=True)
        sonuc = tahta_bakim.son_calismalar()
        self.assertIsNone(sonuc["sabah"])
        gece = sonuc["gece"]
        self.assertEqual(gece["calisma_id"], "c1")
        self.assertFalse(gece["kuru"])
        satir = gece["tahtalar"][0]
        self.assertEqual(satir["tahta_adi"], "9-B")
        self.assertEqual(satir["durum"], "kritik")
        self.assertEqual(satir["kritik"], ["Disk G/Ç hatası (1×): x"])
        self.assertEqual(satir["uyari"], ["u"])
        self.assertIsNotNone(satir["bitis"])

    def test_yeni_kayit_calisiyor_durumunda_acilir(self):
        tahta_bakim.kayit_ac("c1", "sabah", "fenlab")
        satir = tahta_bakim.son_calismalar()["sabah"]["tahtalar"][0]
        self.assertEqual(satir["durum"], "calisiyor")
        self.assertIsNone(satir["bitis"])

    def test_en_son_calisma_secilir_kuru_isaretlenir(self):
        tahta_bakim.kayit_ac("eski", "gece", "9-A")
        tahta_bakim.kayit_ac("yeni", "gece_kuru", "9-A")
        gece = tahta_bakim.son_calismalar()["gece"]
        self.assertEqual(gece["calisma_id"], "yeni")
        self.assertTrue(gece["kuru"])
        self.assertEqual(gece["mod"], "gece_kuru")

    def test_saat_istanbul_gosterilir(self):
        conn = db.baglanti()
        conn.execute(
            "INSERT INTO tahta_bakim (calisma_id, mod, tahta_adi, baslangic_utc, durum) VALUES (?,?,?,?,?)",
            ("c9", "gece", "9-A", "2026-09-29 18:00:03", "tamam"),
        )
        conn.commit()
        conn.close()
        self.assertEqual(tahta_bakim.son_calismalar()["gece"]["baslangic"], "2026-09-29 21:00")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m unittest test_tahta_bakim.TestKayit -v`
Expected: FAIL — `sqlite3.OperationalError: no such table: tahta_bakim` / `AttributeError: ... 'kayit_ac'`

- [ ] **Step 3: Write minimal implementation**

`db.py` — `SEMA` string'inde `oturumlar` tablosunun kapanışından (`);`) sonra, kapanış `"""`'dan önce ekle:

```sql

-- Tahta gece/sabah bakımı (tahta_bakim.py, systemd timer'ından yazılır;
-- dashboard yalnızca okur). Zaman UTC, gösterimde İstanbul. Otomatik silme yok.
CREATE TABLE IF NOT EXISTS tahta_bakim (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    calisma_id    TEXT NOT NULL,
    mod           TEXT NOT NULL,
    tahta_adi     TEXT NOT NULL,
    baslangic_utc TEXT NOT NULL DEFAULT (datetime('now')),
    bitis_utc     TEXT,
    durum         TEXT NOT NULL DEFAULT 'calisiyor',
    kritik_json   TEXT NOT NULL DEFAULT '[]',
    uyari_json    TEXT NOT NULL DEFAULT '[]',
    detay         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_tahta_bakim_mod ON tahta_bakim (mod, id);
```

`tahta_bakim.py` — import bloğuna `import json` ve `import db` ekle, dosya sonuna:

```python
# --------------------------------------------------------------------
# Kayıt (dashboard SQLite'ı, tahta_bakim tablosu)
# --------------------------------------------------------------------

_MOD_GRUPLARI = {"gece": ("gece", "gece_kuru"), "sabah": ("sabah", "sabah_kuru")}


def kayit_ac(calisma_id: str, mod: str, tahta_adi: str) -> int:
    conn = db.baglanti()
    try:
        imlec = conn.execute(
            "INSERT INTO tahta_bakim (calisma_id, mod, tahta_adi) VALUES (?, ?, ?)",
            (calisma_id, mod, tahta_adi),
        )
        conn.commit()
        return imlec.lastrowid
    finally:
        conn.close()


def kayit_guncelle(kayit_id: int, *, durum: str, kritik: list[str], uyari: list[str], detay: str, bitti: bool) -> None:
    conn = db.baglanti()
    try:
        conn.execute(
            "UPDATE tahta_bakim SET durum = ?, kritik_json = ?, uyari_json = ?, detay = ?, "
            "bitis_utc = CASE WHEN ? THEN datetime('now') ELSE bitis_utc END WHERE id = ?",
            (durum, json.dumps(kritik, ensure_ascii=False), json.dumps(uyari, ensure_ascii=False),
             detay, 1 if bitti else 0, kayit_id),
        )
        conn.commit()
    finally:
        conn.close()


def son_calismalar() -> dict:
    """Her grup (gece/sabah, kuru çalışmalar dahil) için en son çalışmanın
    tahta satırları. Kuru çalışma `kuru: True` ile işaretlenir."""
    conn = db.baglanti()
    try:
        sonuc: dict = {}
        for grup, modlar in _MOD_GRUPLARI.items():
            son = conn.execute(
                "SELECT calisma_id, mod FROM tahta_bakim WHERE mod IN (?, ?) ORDER BY id DESC LIMIT 1",
                modlar,
            ).fetchone()
            if son is None:
                sonuc[grup] = None
                continue
            satirlar = conn.execute(
                "SELECT * FROM tahta_bakim WHERE calisma_id = ? ORDER BY id", (son["calisma_id"],)
            ).fetchall()
            sonuc[grup] = {
                "calisma_id": son["calisma_id"],
                "mod": son["mod"],
                "kuru": son["mod"].endswith("_kuru"),
                "baslangic": utc_to_istanbul(satirlar[0]["baslangic_utc"]),
                "tahtalar": [
                    {
                        "tahta_adi": s["tahta_adi"],
                        "durum": s["durum"],
                        "kritik": json.loads(s["kritik_json"]),
                        "uyari": json.loads(s["uyari_json"]),
                        "detay": s["detay"],
                        "baslangic": utc_to_istanbul(s["baslangic_utc"]),
                        "bitis": utc_to_istanbul(s["bitis_utc"]),
                    }
                    for s in satirlar
                ],
            }
        return sonuc
    finally:
        conn.close()
```

- [ ] **Step 4: Run all dashboard tests**

Run: `venv/bin/python -m unittest test_tahta_bakim -v && venv/bin/python -m unittest discover -p 'test_*.py'`
Expected: tümü PASS (şema değişikliği mevcut testleri bozmamalı)

- [ ] **Step 5: Lint + commit**

```bash
cd /home/ata/farabi
.venv-tools/bin/ruff check tahtayoklama/dashboard/tahta_bakim.py tahtayoklama/dashboard/db.py tahtayoklama/dashboard/test_tahta_bakim.py
git add tahtayoklama/dashboard/tahta_bakim.py tahtayoklama/dashboard/db.py tahtayoklama/dashboard/test_tahta_bakim.py
git commit -m "tahtayoklama/dashboard: tahta_bakim tablosu ve kayit fonksiyonlari"
```

---

### Task 3: SSH akışı (tarama, reboot, bekleme, gece/sabah modu, `calistir`)

**Files:**
- Modify: `tahtayoklama/dashboard/tahta_bakim.py`
- Test: `tahtayoklama/dashboard/test_tahta_bakim.py`

**Interfaces:**
- Consumes: `ssh_istemci.komut_calistir(ip, kullanici, komut, stdin_bytes=None, zaman_asimi=15) -> SSHSonuc` (`.basarili`, `.stdout`, `.stderr`), `ssh_istemci.x_ortamini_kesfet(ip, kullanici) -> tuple[str, str, str] | None`, `uzaktan_yonetim._ekran_karart_tek(t, form) -> dict` ve `uzaktan_yonetim._ekran_kaldir_tek(t, form) -> dict` (`{"tahta", "basarili", "detay"}`; `form` kullanılmıyor, `None` geçilir), `tahta_kaydi.tahtalari_yukle() -> list[dict]` (`ad`, `ip`, `kullanici`, `admin`), Task 1 + Task 2 fonksiyonları
- Produces:
  - `sudo_sifresi() -> str | None`
  - `async root_calistir(t: dict, komut: str, sifre: str | None, zaman_asimi: float = 30) -> SSHSonuc`
  - `async boot_id_al(t: dict) -> str | None`
  - `async reboot_et(t: dict, sifre: str | None) -> SSHSonuc`
  - `async geri_gelmesini_bekle(t: dict, eski_boot_id: str, sure: float = GERI_GELME_SURESI_SN) -> bool`
  - `async x_oturumunu_bekle(t: dict, sure: float = X_OTURUMU_SURESI_SN) -> tuple[str, str, str] | None`
  - `async log_tara(t: dict, sifre: str | None) -> tuple[list[str], list[str], list[str]]` — (kritik, uyari, hatalar)
  - `async gece_modu_uygula(t: dict, sifre: str | None) -> tuple[list[str], list[str]]` — (hatalar, notlar)
  - `async sabah_modu_uygula(t: dict, sifre: str | None) -> tuple[list[str], list[str]]`
  - `async tahta_isle(t: dict, mod: str, calisma_id: str, sifre: str | None, kuru: bool) -> str` — son durum
  - `async calistir(mod: str, kuru: bool = False, tek: str | None = None) -> dict[str, str]` — `{tahta_adi: durum}`

- [ ] **Step 1: Write the failing tests** — `test_tahta_bakim.py` sonuna (`if __name__` bloğundan önce) ekle:

```python
def _ok(stdout: bytes = b"") -> ssh_istemci.SSHSonuc:
    return ssh_istemci.SSHSonuc(True, stdout, b"")


def _hata(stderr: bytes = b"hata") -> ssh_istemci.SSHSonuc:
    return ssh_istemci.SSHSonuc(False, b"", stderr)


TAHTA = {"ad": "9-B", "ip": "192.168.23.239", "kullanici": "ogretmen", "admin": "etapadmin"}


class TestRootCalistir(unittest.TestCase):
    def test_nopasswd_basariliysa_tek_cagri(self):
        async def run():
            with patch.object(tahta_bakim.ssh_istemci, "komut_calistir", new_callable=AsyncMock, return_value=_ok(b"x")) as m:
                sonuc = await tahta_bakim.root_calistir(TAHTA, "echo x", "parola")
                self.assertTrue(sonuc.basarili)
                self.assertEqual(m.await_count, 1)
                self.assertEqual(m.await_args.args[1], "etapadmin")
                self.assertTrue(m.await_args.args[2].startswith("sudo -n bash -c "))
        asyncio.run(run())

    def test_nopasswd_yoksa_parolayla_tekrar(self):
        async def run():
            with patch.object(tahta_bakim.ssh_istemci, "komut_calistir", new_callable=AsyncMock, side_effect=[_hata(), _ok()]) as m:
                sonuc = await tahta_bakim.root_calistir(TAHTA, "echo x", "parola")
                self.assertTrue(sonuc.basarili)
                self.assertTrue(m.await_args.args[2].startswith("sudo -S -p '' bash -c "))
                self.assertEqual(m.await_args.kwargs["stdin_bytes"], b"parola\n")
        asyncio.run(run())

    def test_parola_yoksa_ilk_sonuc_doner(self):
        async def run():
            with patch.object(tahta_bakim.ssh_istemci, "komut_calistir", new_callable=AsyncMock, return_value=_hata()) as m:
                sonuc = await tahta_bakim.root_calistir(TAHTA, "echo x", None)
                self.assertFalse(sonuc.basarili)
                self.assertEqual(m.await_count, 1)
        asyncio.run(run())


class TestBekleme(unittest.TestCase):
    def test_geri_gelmesini_bekle_ayni_boot_id_geri_gelmis_saymaz(self):
        async def run():
            with patch.object(tahta_bakim, "boot_id_al", new_callable=AsyncMock, side_effect=["eski", None, "eski", "yeni"]) as m, \
                 patch.object(tahta_bakim, "_uyu", new_callable=AsyncMock):
                self.assertTrue(await tahta_bakim.geri_gelmesini_bekle(TAHTA, "eski", sure=1000))
                self.assertEqual(m.await_count, 4)
        asyncio.run(run())

    def test_geri_gelmesini_bekle_zaman_asimi(self):
        async def run():
            with patch.object(tahta_bakim, "boot_id_al", new_callable=AsyncMock, return_value=None), \
                 patch.object(tahta_bakim, "_uyu", new_callable=AsyncMock), \
                 patch.object(tahta_bakim, "_simdi", side_effect=[0, 10, 400]):
                self.assertFalse(await tahta_bakim.geri_gelmesini_bekle(TAHTA, "eski", sure=360))
        asyncio.run(run())


class TestLogTara(unittest.TestCase):
    def test_kirli_onceki_acilis_ve_farabi_hatasi(self):
        journal = (
            b"t h kernel: watchdog: BUG: soft lockup - CPU#0 stuck\n"
            b"___AYRAC___\n"
            b"___AYRAC___\n"
            b"Eyl 28 12:00:00 vestel9b cinnamon[900]: bir sey\n"
        )
        async def run():
            with patch.object(tahta_bakim, "root_calistir", new_callable=AsyncMock, return_value=_ok(journal)), \
                 patch.object(tahta_bakim.ssh_istemci, "komut_calistir", new_callable=AsyncMock, return_value=_ok(b"2\nson hata\n")):
                kritik, uyari, hatalar = await tahta_bakim.log_tara(TAHTA, None)
                self.assertEqual(hatalar, [])
                self.assertTrue(kritik[0].startswith("Önceki açılış temiz kapanmadı"))
                self.assertTrue(kritik[1].startswith("CPU soft lockup"))
                self.assertEqual(uyari, ["Farabi client: bugün 2 ERROR satırı (son: son hata)"])
        asyncio.run(run())

    def test_journal_okunamazsa_hata(self):
        async def run():
            with patch.object(tahta_bakim, "root_calistir", new_callable=AsyncMock, return_value=_hata(b"sudo: a password is required")), \
                 patch.object(tahta_bakim.ssh_istemci, "komut_calistir", new_callable=AsyncMock, return_value=_ok(b"YOK\n")):
                kritik, uyari, hatalar = await tahta_bakim.log_tara(TAHTA, None)
                self.assertEqual((kritik, uyari), ([], []))
                self.assertIn("Journal okunamadı", hatalar[0])
        asyncio.run(run())


class TestModlar(unittest.TestCase):
    def test_gece_modu_cpu_basarisiz_karartma_yine_denenir(self):
        async def run():
            with patch.object(tahta_bakim, "root_calistir", new_callable=AsyncMock, return_value=_hata(b"sudo yok")), \
                 patch.object(tahta_bakim, "x_oturumunu_bekle", new_callable=AsyncMock, return_value=(":0", "/x", "1001")), \
                 patch.object(tahta_bakim.uzaktan_yonetim, "_ekran_karart_tek", new_callable=AsyncMock,
                              return_value={"tahta": "9-B", "basarili": True, "detay": "ok"}) as karart, \
                 patch.object(tahta_bakim.ssh_istemci, "komut_calistir", new_callable=AsyncMock, return_value=_ok()) as ssh:
                hatalar, notlar = await tahta_bakim.gece_modu_uygula(TAHTA, None)
                self.assertEqual(len(hatalar), 1)
                self.assertIn("CPU tasarruf ayarı uygulanamadı", hatalar[0])
                karart.assert_awaited_once()
                self.assertIn("xset dpms force off", ssh.await_args.args[2])
        asyncio.run(run())

    def test_gece_modu_x_oturumu_yoksa_not_duser(self):
        async def run():
            with patch.object(tahta_bakim, "root_calistir", new_callable=AsyncMock, return_value=_ok()), \
                 patch.object(tahta_bakim, "x_oturumunu_bekle", new_callable=AsyncMock, return_value=None), \
                 patch.object(tahta_bakim.uzaktan_yonetim, "_ekran_karart_tek", new_callable=AsyncMock) as karart:
                hatalar, notlar = await tahta_bakim.gece_modu_uygula(TAHTA, None)
                self.assertEqual(hatalar, [])
                self.assertIn("Masaüstü oturumu açılmadı", notlar[0])
                karart.assert_not_awaited()
        asyncio.run(run())

    def test_sabah_modu_performance_ve_karartma_kaldirilir(self):
        async def run():
            with patch.object(tahta_bakim, "root_calistir", new_callable=AsyncMock, return_value=_ok()) as root, \
                 patch.object(tahta_bakim, "x_oturumunu_bekle", new_callable=AsyncMock, return_value=(":0", "/x", "1001")), \
                 patch.object(tahta_bakim.uzaktan_yonetim, "_ekran_kaldir_tek", new_callable=AsyncMock,
                              return_value={"tahta": "9-B", "basarili": True, "detay": "ok"}) as kaldir, \
                 patch.object(tahta_bakim.ssh_istemci, "komut_calistir", new_callable=AsyncMock, return_value=_ok()) as ssh:
                hatalar, notlar = await tahta_bakim.sabah_modu_uygula(TAHTA, None)
                self.assertEqual(hatalar, [])
                self.assertIn("performance", root.await_args.args[1])
                kaldir.assert_awaited_once()
                self.assertIn("xset dpms force on", ssh.await_args.args[2])
        asyncio.run(run())


class TestTahtaIsle(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._eski_db_yolu = db.DB_YOLU
        db.DB_YOLU = Path(self._tmp.name) / "test.db"
        db.semayi_kur()

    def tearDown(self):
        db.DB_YOLU = self._eski_db_yolu
        self._tmp.cleanup()

    def _satir(self):
        return tahta_bakim.son_calismalar()

    def test_kapali_tahta(self):
        async def run():
            with patch.object(tahta_bakim, "boot_id_al", new_callable=AsyncMock, return_value=None), \
                 patch.object(tahta_bakim, "reboot_et", new_callable=AsyncMock) as reboot:
                self.assertEqual(await tahta_bakim.tahta_isle(TAHTA, "gece", "c1", None, False), "kapali")
                reboot.assert_not_awaited()
        asyncio.run(run())
        self.assertEqual(self._satir()["gece"]["tahtalar"][0]["durum"], "kapali")

    def test_gece_tam_akis_sirasi(self):
        sira = []
        def kaydet(ad, deger):
            async def f(*a, **k):
                sira.append(ad)
                return deger
            return f
        async def run():
            with patch.object(tahta_bakim, "boot_id_al", side_effect=kaydet("boot_id", "eski")), \
                 patch.object(tahta_bakim, "log_tara", side_effect=kaydet("log_tara", (["K"], ["U"], []))), \
                 patch.object(tahta_bakim, "okul_saati_mi", return_value=False), \
                 patch.object(tahta_bakim, "reboot_et", side_effect=kaydet("reboot", _ok())), \
                 patch.object(tahta_bakim, "geri_gelmesini_bekle", side_effect=kaydet("bekle", True)), \
                 patch.object(tahta_bakim, "gece_modu_uygula", side_effect=kaydet("gece_modu", ([], ["not"]))):
                self.assertEqual(await tahta_bakim.tahta_isle(TAHTA, "gece", "c1", None, False), "kritik")
        asyncio.run(run())
        self.assertEqual(sira, ["boot_id", "log_tara", "reboot", "bekle", "gece_modu"])
        satir = self._satir()["gece"]["tahtalar"][0]
        self.assertEqual((satir["kritik"], satir["uyari"], satir["detay"]), (["K"], ["U"], "not"))

    def test_kuru_calisma_reboot_etmez(self):
        async def run():
            with patch.object(tahta_bakim, "boot_id_al", new_callable=AsyncMock, return_value="eski"), \
                 patch.object(tahta_bakim, "log_tara", new_callable=AsyncMock, return_value=([], [], [])), \
                 patch.object(tahta_bakim, "reboot_et", new_callable=AsyncMock) as reboot:
                self.assertEqual(await tahta_bakim.tahta_isle(TAHTA, "gece", "c1", None, True), "tamam")
                reboot.assert_not_awaited()
        asyncio.run(run())
        self.assertEqual(self._satir()["gece"]["mod"], "gece_kuru")

    def test_okul_saatinde_reboot_atlanir(self):
        async def run():
            with patch.object(tahta_bakim, "boot_id_al", new_callable=AsyncMock, return_value="eski"), \
                 patch.object(tahta_bakim, "okul_saati_mi", return_value=True), \
                 patch.object(tahta_bakim, "reboot_et", new_callable=AsyncMock) as reboot:
                self.assertEqual(await tahta_bakim.tahta_isle(TAHTA, "sabah", "c1", None, False), "tamam")
                reboot.assert_not_awaited()
        asyncio.run(run())
        self.assertIn("Okul saati", self._satir()["sabah"]["tahtalar"][0]["detay"])

    def test_geri_gelmedi(self):
        async def run():
            with patch.object(tahta_bakim, "boot_id_al", new_callable=AsyncMock, return_value="eski"), \
                 patch.object(tahta_bakim, "okul_saati_mi", return_value=False), \
                 patch.object(tahta_bakim, "reboot_et", new_callable=AsyncMock, return_value=_ok()), \
                 patch.object(tahta_bakim, "geri_gelmesini_bekle", new_callable=AsyncMock, return_value=False), \
                 patch.object(tahta_bakim, "sabah_modu_uygula", new_callable=AsyncMock) as mod:
                self.assertEqual(await tahta_bakim.tahta_isle(TAHTA, "sabah", "c1", None, False), "geri_gelmedi")
                mod.assert_not_awaited()
        asyncio.run(run())

    def test_beklenmeyen_istisna_hata_olarak_kaydedilir(self):
        async def run():
            with patch.object(tahta_bakim, "boot_id_al", new_callable=AsyncMock, side_effect=RuntimeError("patladı")):
                self.assertEqual(await tahta_bakim.tahta_isle(TAHTA, "gece", "c1", None, False), "hata")
        asyncio.run(run())
        self.assertIn("patladı", self._satir()["gece"]["tahtalar"][0]["detay"])

    def test_calistir_bir_tahtanin_hatasi_digerini_durdurmaz(self):
        tahtalar = [dict(TAHTA, ad="9-A"), dict(TAHTA, ad="9-B"), dict(TAHTA, ad="tahta-234")]
        async def isle(t, mod, calisma_id, sifre, kuru):
            if t["ad"] == "9-A":
                raise RuntimeError("beklenmedik")
            return "tamam"
        async def run():
            with patch.object(tahta_bakim.tahta_kaydi, "tahtalari_yukle", return_value=tahtalar), \
                 patch.object(tahta_bakim, "sudo_sifresi", return_value=None), \
                 patch.object(tahta_bakim, "tahta_isle", side_effect=isle):
                return await tahta_bakim.calistir("gece")
        self.assertEqual(asyncio.run(run()), {"9-A": "hata", "9-B": "tamam"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m unittest test_tahta_bakim -v`
Expected: yeni sınıflar FAIL — `AttributeError: module 'tahta_bakim' has no attribute 'root_calistir'` vb.; Task 1–2 testleri PASS

- [ ] **Step 3: Write minimal implementation**

`tahta_bakim.py` import bloğunu şöyle genişlet (mevcutlarla birleştir, alfabetik):

```python
import asyncio
import json
import re
import shlex
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import db
import ssh_istemci
import tahta_kaydi
import uzaktan_yonetim
import zil
```

Sabitler (`_ORNEK_UZUNLUK`'un altına):

```python
GERI_GELME_SURESI_SN = 360
YOKLAMA_ARALIGI_SN = 5
X_OTURUMU_SURESI_SN = 90

# tahtaayar/tahta_fix_uygula.py::GIZLI_JSON_ADAYLARI ile aynı sıra — parola
# tek yerde (dashboard/config/gizli.json), kopyalanmaz.
GIZLI_JSON_ADAYLARI = (
    Path(__file__).resolve().parents[2] / "tahtaayar" / "config" / "gizli.json",
    Path(__file__).resolve().parent / "config" / "gizli.json",
)

AYRAC = "___AYRAC___"
LOG_KOMUTU = (
    "journalctl -b 0 -k -p 0..3 --no-pager -q -o short-iso | tail -n 300; "
    f"echo {AYRAC}; "
    "journalctl -b 0 -p 0..2 --no-pager -q -o short-iso | tail -n 300; "
    f"echo {AYRAC}; "
    "journalctl -b -1 -n 80 --no-pager -q 2>&1 | tail -n 80"
)

# 9-A tam klon yapısında (~/farabi/repo/client), diğerleri ~/farabi/client.
FARABI_LOG_KOMUTU = (
    'F=; for f in ~/farabi/client/logs/farabi.log ~/farabi/repo/client/logs/farabi.log; do '
    'if [ -f "$f" ]; then F="$f"; break; fi; done; '
    'if [ -z "$F" ]; then echo YOK; exit 0; fi; '
    'G=$(date +%F); '
    'H=$(cat "$F" "$F.1" 2>/dev/null | grep -E "^$G .*\\| (ERROR|CRITICAL)"); '
    'if [ -z "$H" ]; then echo 0; else printf "%s\\n" "$H" | wc -l; printf "%s\\n" "$H" | tail -n 1; fi'
)

_CPUFREQ = "/sys/devices/system/cpu/cpu[0-9]*/cpufreq"
CPU_GECE_KOMUTU = (
    f"for c in {_CPUFREQ}; do echo ondemand > $c/scaling_governor && "
    "cat $c/cpuinfo_min_freq > $c/scaling_max_freq || exit 1; done"
)
CPU_SABAH_KOMUTU = (
    f"for c in {_CPUFREQ}; do echo performance > $c/scaling_governor && "
    "cat $c/cpuinfo_max_freq > $c/scaling_max_freq || exit 1; done"
)

# Arka planda 2 sn gecikmeli: SSH oturumu reboot'tan önce temiz kapansın,
# komut başarı dönsün.
REBOOT_KOMUTU = "nohup sh -c 'sleep 2; systemctl reboot' >/dev/null 2>&1 &"
```

Dosya sonuna:

```python
# --------------------------------------------------------------------
# SSH akışı
# --------------------------------------------------------------------

def _kisa(b: bytes) -> str:
    return b.decode("utf-8", errors="replace").strip()[:200]


def _simdi() -> float:
    """Testlerde yamalanır — time.monotonic'i doğrudan yamamak asyncio
    olay döngüsünü de bozar."""
    return time.monotonic()


async def _uyu(saniye: float) -> None:
    await asyncio.sleep(saniye)


def sudo_sifresi() -> str | None:
    """NOPASSWD'li tahtalarda gerekmez; yalnızca `sudo -n` başarısızsa kullanılır."""
    for yol in GIZLI_JSON_ADAYLARI:
        if yol.exists():
            sifre = json.loads(yol.read_text(encoding="utf-8")).get("etapadmin_sifre")
            if sifre:
                return sifre
    return None


async def root_calistir(t: dict, komut: str, sifre: str | None, zaman_asimi: float = 30) -> ssh_istemci.SSHSonuc:
    """etapadmin + sudo. Önce `sudo -n`; başarısızsa ve parola varsa `sudo -S`.
    Not: `sudo -n` komutun KENDİSİ başarısız olduğu için de düşebilir, o zaman
    komut parolayla bir kez daha koşar — buradaki tüm komutlar idempotent."""
    admin = t.get("admin") or "etapadmin"
    ic = shlex.quote(komut)
    sonuc = await ssh_istemci.komut_calistir(t["ip"], admin, f"sudo -n bash -c {ic}", zaman_asimi=zaman_asimi)
    if sonuc.basarili or not sifre:
        return sonuc
    return await ssh_istemci.komut_calistir(
        t["ip"], admin, f"sudo -S -p '' bash -c {ic}",
        stdin_bytes=(sifre + "\n").encode(), zaman_asimi=zaman_asimi,
    )


async def boot_id_al(t: dict) -> str | None:
    sonuc = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], "cat /proc/sys/kernel/random/boot_id", zaman_asimi=10)
    if not sonuc.basarili:
        return None
    return sonuc.stdout.decode("utf-8", errors="replace").strip() or None


async def reboot_et(t: dict, sifre: str | None) -> ssh_istemci.SSHSonuc:
    return await root_calistir(t, REBOOT_KOMUTU, sifre, zaman_asimi=15)


async def geri_gelmesini_bekle(t: dict, eski_boot_id: str, sure: float = GERI_GELME_SURESI_SN) -> bool:
    """Yalnızca boot_id DEĞİŞİNCE geri gelmiş sayılır — reboot'tan hemen
    sonra SSH hâlâ eski oturuma cevap verebilir."""
    bitis = _simdi() + sure
    while _simdi() < bitis:
        simdiki = await boot_id_al(t)
        if simdiki and simdiki != eski_boot_id:
            return True
        await _uyu(YOKLAMA_ARALIGI_SN)
    return False


async def x_oturumunu_bekle(t: dict, sure: float = X_OTURUMU_SURESI_SN) -> tuple[str, str, str] | None:
    """Otomatik girişli tahtada açılıştan sonra masaüstü birkaç saniyede gelir;
    9-A'da otomatik giriş yok → None."""
    bitis = _simdi() + sure
    while _simdi() < bitis:
        ortam = await ssh_istemci.x_ortamini_kesfet(t["ip"], t["kullanici"])
        if ortam is not None:
            return ortam
        await _uyu(YOKLAMA_ARALIGI_SN)
    return None


async def log_tara(t: dict, sifre: str | None) -> tuple[list[str], list[str], list[str]]:
    kritik: list[str] = []
    uyari: list[str] = []
    hatalar: list[str] = []
    sonuc = await root_calistir(t, LOG_KOMUTU, sifre, zaman_asimi=60)
    if not sonuc.basarili:
        hatalar.append("Journal okunamadı: " + _kisa(sonuc.stderr))
    else:
        parcalar = sonuc.stdout.decode("utf-8", errors="replace").split(AYRAC)
        kritik, uyari = log_siniflandir("\n".join(parcalar[:2]))
        onceki = parcalar[2] if len(parcalar) > 2 else ""
        if onceki_acilis_durumu(onceki) == "kirli":
            kritik.insert(0, "Önceki açılış temiz kapanmadı (donma ya da elektrik kesintisi şüphesi)")
    farabi = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], FARABI_LOG_KOMUTU, zaman_asimi=20)
    if farabi.basarili:
        ozet = farabi_log_ayristir(farabi.stdout.decode("utf-8", errors="replace"))
        if ozet:
            uyari.append(ozet)
    return kritik, uyari, hatalar


def _x_env(ortam: tuple[str, str, str]) -> str:
    display, xauthority, _uid = ortam
    return f"env DISPLAY={shlex.quote(display)} XAUTHORITY={shlex.quote(xauthority)}"


async def gece_modu_uygula(t: dict, sifre: str | None) -> tuple[list[str], list[str]]:
    hatalar: list[str] = []
    notlar: list[str] = []
    cpu = await root_calistir(t, CPU_GECE_KOMUTU, sifre)
    if not cpu.basarili:
        hatalar.append("CPU tasarruf ayarı uygulanamadı: " + _kisa(cpu.stderr))
    ortam = await x_oturumunu_bekle(t)
    if ortam is None:
        notlar.append("Masaüstü oturumu açılmadı, karartma ve ekran kapatma atlandı.")
        return hatalar, notlar
    karart = await uzaktan_yonetim._ekran_karart_tek(t, None)
    if not karart["basarili"]:
        hatalar.append("Karartma başarısız: " + karart["detay"])
    dpms = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], f"{_x_env(ortam)} xset dpms force off")
    if not dpms.basarili:
        hatalar.append("Ekran kapatılamadı: " + _kisa(dpms.stderr))
    return hatalar, notlar


async def sabah_modu_uygula(t: dict, sifre: str | None) -> tuple[list[str], list[str]]:
    hatalar: list[str] = []
    notlar: list[str] = []
    cpu = await root_calistir(t, CPU_SABAH_KOMUTU, sifre)
    if not cpu.basarili:
        hatalar.append("CPU yüksek performans ayarı uygulanamadı: " + _kisa(cpu.stderr))
    ortam = await x_oturumunu_bekle(t)
    if ortam is None:
        notlar.append("Masaüstü oturumu açılmadı, ekran ayarı atlandı.")
        return hatalar, notlar
    kaldir = await uzaktan_yonetim._ekran_kaldir_tek(t, None)
    if not kaldir["basarili"]:
        hatalar.append("Karartma kaldırılamadı: " + kaldir["detay"])
    dpms = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], f"{_x_env(ortam)} xset dpms force on")
    if not dpms.basarili:
        hatalar.append("Ekran açılamadı: " + _kisa(dpms.stderr))
    return hatalar, notlar


async def tahta_isle(t: dict, mod: str, calisma_id: str, sifre: str | None, kuru: bool) -> str:
    kayit_id = kayit_ac(calisma_id, f"{mod}_kuru" if kuru else mod, t["ad"])
    kritik: list[str] = []
    uyari: list[str] = []
    hatalar: list[str] = []
    notlar: list[str] = []

    def bitir(durum: str) -> str:
        kayit_guncelle(kayit_id, durum=durum, kritik=kritik, uyari=uyari,
                       detay=" · ".join(hatalar + notlar), bitti=True)
        return durum

    try:
        eski_boot_id = await boot_id_al(t)
        if eski_boot_id is None:
            notlar.append("SSH ile ulaşılamadı (tahta kapalı olabilir).")
            return bitir("kapali")
        if mod == "gece":
            k, u, h = await log_tara(t, sifre)
            kritik.extend(k)
            uyari.extend(u)
            hatalar.extend(h)
            # Reboot'tan ÖNCE yaz — tahta geri gelmese bile rapor kalır.
            kayit_guncelle(kayit_id, durum="calisiyor", kritik=kritik, uyari=uyari,
                           detay=" · ".join(hatalar), bitti=False)
        if kuru:
            return bitir(durum_belirle(kritik, hatalar))
        if okul_saati_mi(zil.simdi_istanbul()):
            notlar.append("Okul saati içinde, reboot atlandı.")
            return bitir(durum_belirle(kritik, hatalar))
        reboot = await reboot_et(t, sifre)
        if not reboot.basarili:
            hatalar.append("Reboot komutu başarısız: " + _kisa(reboot.stderr))
            return bitir("hata")
        if not await geri_gelmesini_bekle(t, eski_boot_id):
            notlar.append(f"Reboot sonrası {GERI_GELME_SURESI_SN} sn içinde geri gelmedi.")
            return bitir("geri_gelmedi")
        uygula = gece_modu_uygula if mod == "gece" else sabah_modu_uygula
        h, n = await uygula(t, sifre)
        hatalar.extend(h)
        notlar.extend(n)
        return bitir(durum_belirle(kritik, hatalar))
    except Exception as e:  # noqa: BLE001 — bir tahtanın hatası diğerlerini durdurmamalı
        hatalar.append(f"Beklenmeyen hata: {e!r}"[:300])
        return bitir("hata")


async def calistir(mod: str, kuru: bool = False, tek: str | None = None) -> dict[str, str]:
    if mod not in ("gece", "sabah"):
        raise ValueError(f"Geçersiz mod: {mod!r}")
    db.semayi_kur()
    tahtalar = hedef_tahtalar(tahta_kaydi.tahtalari_yukle(), tek)
    sifre = sudo_sifresi()
    calisma_id = uuid.uuid4().hex[:12]
    sonuclar = await asyncio.gather(
        *(tahta_isle(t, mod, calisma_id, sifre, kuru) for t in tahtalar),
        return_exceptions=True,
    )
    return {
        t["ad"]: (s if isinstance(s, str) else "hata")
        for t, s in zip(tahtalar, sonuclar)
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m unittest test_tahta_bakim -v && venv/bin/python -m unittest discover -p 'test_*.py'`
Expected: tümü PASS

- [ ] **Step 5: Lint + commit**

```bash
cd /home/ata/farabi
.venv-tools/bin/ruff check tahtayoklama/dashboard/tahta_bakim.py tahtayoklama/dashboard/test_tahta_bakim.py
git add tahtayoklama/dashboard/tahta_bakim.py tahtayoklama/dashboard/test_tahta_bakim.py
git commit -m "tahtayoklama/dashboard: tahta bakimi SSH akisi (tarama, reboot, gece/sabah modu)"
```

---

### Task 4: CLI ve systemd birim dosyaları

**Files:**
- Create: `tahtayoklama/dashboard/scripts/tahta_bakim.py`
- Create: `tahtayoklama/dashboard/systemd/farabi-tahta-gece.service`, `farabi-tahta-gece.timer`, `farabi-tahta-sabah.service`, `farabi-tahta-sabah.timer`
- Test: `tahtayoklama/dashboard/test_tahta_bakim.py`

**Interfaces:**
- Consumes: `tahta_bakim.calistir(mod, kuru, tek) -> dict[str, str]`
- Produces: `scripts/tahta_bakim.py::main(argv: list[str] | None = None) -> int` (0 = çalıştı, 2 = kilit dolu, 1 = geçersiz tahta)

- [ ] **Step 1: Write the failing tests** — `test_tahta_bakim.py` sonuna (`if __name__` bloğundan önce) ekle:

```python
# (importlib.util Task 1'de dosya başına eklendi)
_CLI_YOLU = Path(__file__).resolve().parent / "scripts" / "tahta_bakim.py"


def _cli():
    spec = importlib.util.spec_from_file_location("tahta_bakim_cli", _CLI_YOLU)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


class TestCli(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.cli = _cli()
        self.cli.KILIT_DOSYASI = Path(self._tmp.name) / "kilit"

    def tearDown(self):
        self._tmp.cleanup()

    def test_argumanlar_calistira_gecer(self):
        with patch.object(self.cli.tahta_bakim, "calistir", new_callable=AsyncMock, return_value={"fenlab": "tamam"}) as m:
            self.assertEqual(self.cli.main(["gece", "--kuru", "--tahta", "fenlab"]), 0)
            m.assert_awaited_once_with("gece", kuru=True, tek="fenlab")

    def test_kilit_doluysa_calismaz(self):
        import fcntl
        with open(self.cli.KILIT_DOSYASI, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(self.cli.tahta_bakim, "calistir", new_callable=AsyncMock) as m:
                self.assertEqual(self.cli.main(["sabah"]), 2)
                m.assert_not_awaited()

    def test_gecersiz_tahta(self):
        with patch.object(self.cli.tahta_bakim, "calistir", new_callable=AsyncMock, side_effect=ValueError("yok")):
            self.assertEqual(self.cli.main(["gece", "--tahta", "tahta-234"]), 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m unittest test_tahta_bakim.TestCli -v`
Expected: FAIL — `FileNotFoundError` (`scripts/tahta_bakim.py` yok)

- [ ] **Step 3: Write implementation**

`tahtayoklama/dashboard/scripts/tahta_bakim.py`:

```python
"""Tahta gece/sabah bakımı CLI — systemd timer'ları bunu çağırır
(systemd/farabi-tahta-{gece,sabah}.service). Elle:

    venv/bin/python scripts/tahta_bakim.py gece --kuru            # yalnızca tarama, 8 tahta
    venv/bin/python scripts/tahta_bakim.py gece --tahta fenlab    # tek tahtada GERÇEK reboot
    venv/bin/python scripts/tahta_bakim.py sabah --tahta fenlab

Okul saatinde (08:10–15:50, okul günü) reboot kendiliğinden atlanır.
Aynı anda iki çalışma flock ile engellenir.
"""

import argparse
import asyncio
import fcntl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tahta_bakim  # noqa: E402

KILIT_DOSYASI = Path(__file__).resolve().parent.parent / "veri" / "tahta_bakim.lock"


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Tahta gece/sabah bakımı")
    ayristirici.add_argument("mod", choices=["gece", "sabah"])
    ayristirici.add_argument("--kuru", action="store_true", help="yalnızca tarama/kayıt; reboot ve ayar değişikliği yok")
    ayristirici.add_argument("--tahta", help="yalnızca bu tahta (ör. fenlab)")
    arg = ayristirici.parse_args(argv)

    KILIT_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
    with open(KILIT_DOSYASI, "w") as kilit:
        try:
            fcntl.flock(kilit, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Başka bir bakım çalışması sürüyor, çıkılıyor.", file=sys.stderr)
            return 2
        try:
            sonuclar = asyncio.run(tahta_bakim.calistir(arg.mod, kuru=arg.kuru, tek=arg.tahta))
        except ValueError as e:
            print(f"HATA: {e}", file=sys.stderr)
            return 1
    for ad, durum in sonuclar.items():
        print(f"{ad}: {durum}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`tahtayoklama/dashboard/systemd/farabi-tahta-gece.service`:

```ini
[Unit]
Description=Farabi tahta gece bakımı (log tara, reboot, karartma + tasarruf)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=ata
WorkingDirectory=/home/ata/farabi/tahtayoklama/dashboard
ExecStart=/home/ata/farabi/tahtayoklama/dashboard/venv/bin/python scripts/tahta_bakim.py gece
TimeoutStartSec=20min
```

`tahtayoklama/dashboard/systemd/farabi-tahta-gece.timer`:

```ini
[Unit]
Description=Farabi tahta gece bakımı — her gün 21:00 (İstanbul)

[Timer]
OnCalendar=*-*-* 21:00:00 Europe/Istanbul
# Kaçırılan çalışma sonradan TEKRARLANMAZ: sunucu 21:00'de kapalıysa
# gece yarısı tahtaları yeniden başlatmasın.
Persistent=false

[Install]
WantedBy=timers.target
```

`tahtayoklama/dashboard/systemd/farabi-tahta-sabah.service`:

```ini
[Unit]
Description=Farabi tahta sabah bakımı (reboot + yüksek performans)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=ata
WorkingDirectory=/home/ata/farabi/tahtayoklama/dashboard
ExecStart=/home/ata/farabi/tahtayoklama/dashboard/venv/bin/python scripts/tahta_bakim.py sabah
TimeoutStartSec=20min
```

`tahtayoklama/dashboard/systemd/farabi-tahta-sabah.timer`:

```ini
[Unit]
Description=Farabi tahta sabah bakımı — her gün 07:00 (İstanbul)

[Timer]
OnCalendar=*-*-* 07:00:00 Europe/Istanbul
Persistent=false

[Install]
WantedBy=timers.target
```

- [ ] **Step 4: Run tests + validate unit files**

Run:
```bash
venv/bin/python -m unittest test_tahta_bakim -v
systemd-analyze verify systemd/farabi-tahta-gece.service systemd/farabi-tahta-sabah.service
systemd-analyze calendar "*-*-* 21:00:00 Europe/Istanbul" "*-*-* 07:00:00 Europe/Istanbul"
```
Expected: testler PASS; `verify` hata yok; `calendar` çıktısında "Next elapse" UTC karşılığı 18:00 ve 04:00.

- [ ] **Step 5: Lint + commit**

```bash
cd /home/ata/farabi
.venv-tools/bin/ruff check tahtayoklama/dashboard/scripts/tahta_bakim.py tahtayoklama/dashboard/test_tahta_bakim.py
git add tahtayoklama/dashboard/scripts/tahta_bakim.py tahtayoklama/dashboard/systemd/ tahtayoklama/dashboard/test_tahta_bakim.py
git commit -m "tahtayoklama/dashboard: tahta bakimi CLI ve systemd timer birimleri"
```

---

### Task 5: Dashboard — `/api/tahta-bakim` ve durum sayfası kartı

**Files:**
- Modify: `tahtayoklama/dashboard/app.py` (import bloğu; `/sistem-durumu` route'undan sonra yeni endpoint)
- Modify: `tahtayoklama/dashboard/templates/sistem_durumu.html` (`<h2>Ağ ve dış makineler</h2>`'den ÖNCE yeni bölüm; `<script>` sonunda JS)
- Test: `tahtayoklama/dashboard/test_tahta_bakim.py`

**Interfaces:**
- Consumes: `tahta_bakim.son_calismalar() -> dict`, `app._oturum_gerekli(request, conn) -> bool`, şablondaki `kacis()`, `rozet(durum, metin)`
- Produces: `GET /api/tahta-bakim` → `son_calismalar()` JSON'u; oturumsuz 401

- [ ] **Step 1: Write the failing tests** — `test_tahta_bakim.py` sonuna ekle:

```python
class TestApiTahtaBakim(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._eski_db_yolu = db.DB_YOLU
        db.DB_YOLU = Path(self._tmp.name) / "test.db"
        db.semayi_kur()

    def tearDown(self):
        db.DB_YOLU = self._eski_db_yolu
        self._tmp.cleanup()

    def _istek(self):
        from fastapi.requests import Request
        return Request({"type": "http", "method": "GET", "path": "/api/tahta-bakim", "headers": [], "query_string": b""})

    def test_oturumla_json_doner(self):
        import app
        kid = tahta_bakim.kayit_ac("c1", "gece", "fenlab")
        tahta_bakim.kayit_guncelle(kid, durum="tamam", kritik=[], uyari=[], detay="", bitti=True)
        async def run():
            with patch.object(app, "_oturum_gerekli", return_value=True):
                yanit = await app.api_tahta_bakim(self._istek())
                govde = json.loads(yanit.body.decode())
                self.assertEqual(govde["gece"]["tahtalar"][0]["tahta_adi"], "fenlab")
                self.assertIsNone(govde["sabah"])
        asyncio.run(run())

    def test_oturumsuz_401(self):
        import app
        from fastapi import HTTPException
        async def run():
            with patch.object(app, "_oturum_gerekli", return_value=False):
                with self.assertRaises(HTTPException) as ctx:
                    await app.api_tahta_bakim(self._istek())
                self.assertEqual(ctx.exception.status_code, 401)
        asyncio.run(run())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m unittest test_tahta_bakim.TestApiTahtaBakim -v`
Expected: FAIL — `AttributeError: module 'app' has no attribute 'api_tahta_bakim'`

- [ ] **Step 3: Implement endpoint**

`app.py` import bloğuna (diğer yerel modül import'larının yanına, alfabetik) `import tahta_bakim` ekle. `sistem_durumu_sayfa` fonksiyonundan sonra:

```python
@app.get("/api/tahta-bakim")
async def api_tahta_bakim(request: Request):
    """Salt okunur — tahta gece/sabah bakımının son sonuçları (tahta_bakim
    tablosunu systemd timer'ı yazar, bkz. tahta_bakim.py)."""
    conn = db.baglanti()
    try:
        if not _oturum_gerekli(request, conn):
            raise HTTPException(401, "Oturum geçersiz.")
    finally:
        conn.close()
    return JSONResponse(tahta_bakim.son_calismalar())
```

- [ ] **Step 4: Implement card** — `sistem_durumu.html`'de `<h2>Ağ ve dış makineler</h2>` satırından HEMEN ÖNCE:

```html
<h2>Tahta bakımı</h2>
<p class="rapor-aciklama">Her gün 21:00'de açık tahtaların hata/donma/donanım
   logları taranır, tahtalar yeniden başlatılır, ekran karartılıp kapatılır ve
   işlemci tasarrufa alınır. 07:00'de yeniden başlatılıp yüksek performansa
   alınır. Kapalı tahtalar atlanır.</p>
<div class="iki-sutun">
  <section>
    <h3>Son gece bakımı</h3>
    <div class="bilgi-kart" id="bakim-gece"><p class="rapor-aciklama">Okunuyor…</p></div>
  </section>
  <section>
    <h3>Son sabah bakımı</h3>
    <div class="bilgi-kart" id="bakim-sabah"><p class="rapor-aciklama">Okunuyor…</p></div>
  </section>
</div>
```

Aynı dosyada `setInterval(durumGuncelle, 15000);` satırından SONRA (aynı `<script>` içinde):

```js
// ---- Tahta bakımı (21:00 / 07:00) ----
const BAKIM_ROZET = {
  tamam: ['ok', 'Tamam'], kritik: ['hata', 'Kritik bulgu'], hata: ['hata', 'Hata'],
  geri_gelmedi: ['hata', 'Geri gelmedi'], kapali: ['uyari', 'Kapalıydı'], calisiyor: ['yavas', 'Sürüyor'],
};
function bakimKartCiz(id, c) {
  const el = document.getElementById(id);
  if (!c) { el.innerHTML = '<p class="rapor-aciklama">Henüz çalışma yok.</p>'; return; }
  const baslik = `<p class="rapor-aciklama">${kacis(c.baslangic)}${c.kuru ? ' · deneme çalışması (yeniden başlatma yok)' : ''}</p>`;
  const satirlar = c.tahtalar.map(t => {
    const [sinif, etiket] = BAKIM_ROZET[t.durum] || ['uyari', t.durum];
    const kritik = t.kritik.length ? `<ul>${t.kritik.map(k => `<li>${kacis(k)}</li>`).join('')}</ul>` : '';
    const uyari = t.uyari.length
      ? `<details><summary>Uyarılar (${t.uyari.length})</summary><ul>${t.uyari.map(u => `<li>${kacis(u)}</li>`).join('')}</ul></details>` : '';
    const detay = t.detay ? `<div class="rapor-aciklama">${kacis(t.detay)}</div>` : '';
    return `<tr><td>${kacis(t.tahta_adi)}</td><td>${rozet(sinif, etiket)}</td><td>${kritik}${uyari}${detay}</td></tr>`;
  }).join('');
  el.innerHTML = baslik + `<div class="tablo-sarici"><table class="servis-tablo"><thead><tr><th>Tahta</th><th>Durum</th><th>Bulgular</th></tr></thead><tbody>${satirlar}</tbody></table></div>`;
}
async function bakimGuncelle() {
  if (document.hidden) return;
  try {
    const yanit = await fetch('/api/tahta-bakim');
    if (!yanit.ok) return;
    const veri = await yanit.json();
    bakimKartCiz('bakim-gece', veri.gece);
    bakimKartCiz('bakim-sabah', veri.sabah);
  } catch (e) { /* bir sonraki turda yeniden denenir */ }
}
bakimGuncelle();
setInterval(bakimGuncelle, 60000);
```

- [ ] **Step 5: Run all tests**

Run: `venv/bin/python -m unittest test_tahta_bakim -v && venv/bin/python -m unittest discover -p 'test_*.py'`
Expected: tümü PASS

- [ ] **Step 6: Deploy + görsel kontrol**

```bash
sudo systemctl restart farabi-yoklama-dashboard.service
systemctl is-active farabi-yoklama-dashboard.service     # active
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8010/api/tahta-bakim   # 401 (oturumsuz)
```
Tarayıcıda `/sistem-durumu`: "Tahta bakımı" bölümü "Henüz çalışma yok." göstermeli, üç temada (klasik/yumuşak/koyu) okunur olmalı.

- [ ] **Step 7: Lint + commit**

```bash
cd /home/ata/farabi
.venv-tools/bin/ruff check tahtayoklama/dashboard/app.py tahtayoklama/dashboard/test_tahta_bakim.py
git add tahtayoklama/dashboard/app.py tahtayoklama/dashboard/templates/sistem_durumu.html tahtayoklama/dashboard/test_tahta_bakim.py
git commit -m "tahtayoklama/dashboard: sistem durumu sayfasina tahta bakimi karti"
```

---

### Task 6: Canlı prova, devreye alma, belgeleme

> ⚠️ Bu görev gerçek tahtaları yeniden başlatır. **Her adımdan önce Atakan'dan açık onay alınır**; alt ajana devredilmez, ana oturum yürütür. Okul saatinde (08:10–15:50) YAPILMAZ.

**Files:**
- Modify: `tahtayoklama/CLAUDE.md` (yeni "Tahta gece/sabah bakımı" bölümü)
- Modify: `CLAUDE.md` (kök — "Mimari" altındaki uzaktan yönetim maddesinin yanına tek satır)
- Modify: `DECISIONS.md` (en üste kayıt)

- [ ] **Step 1: Kuru çalışma, 8 tahta** (reboot YOK)

```bash
cd /home/ata/farabi/tahtayoklama/dashboard
venv/bin/python scripts/tahta_bakim.py gece --kuru
```
Expected: her tahta için `tamam`/`kritik`/`hata`/`kapali` satırı; `/sistem-durumu` kartında "deneme çalışması" etiketiyle görünür. `hata` varsa detayını oku (ör. "Journal okunamadı" → o tahtada sudo durumu). Bulguları Atakan'a göster.

- [ ] **Step 2: Birimleri kur (ETKİNLEŞTİRMEDEN)**

```bash
sudo cp /home/ata/farabi/tahtayoklama/dashboard/systemd/farabi-tahta-*.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
systemctl list-unit-files 'farabi-tahta-*'    # disabled olmalı
```

- [ ] **Step 3: fenlab'da gerçek gece çalışması** (Atakan onayından sonra)

```bash
venv/bin/python scripts/tahta_bakim.py gece --tahta fenlab
server/tahta-ssh.sh fenlab "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq; pgrep -f '[e]ta-screen-cover' && echo karartma_acik"
```
Expected: `fenlab: tamam` (ya da `kritik` + bulgular); `ondemand`, `1400000`, `karartma_acik`. Atakan fiziksel tahtada ekranın kapalı/karartılmış olduğunu doğrular.

- [ ] **Step 4: fenlab'da gerçek sabah çalışması** (Atakan onayından sonra)

```bash
venv/bin/python scripts/tahta_bakim.py sabah --tahta fenlab
server/tahta-ssh.sh fenlab "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq; pgrep -f '[e]ta-screen-cover' || echo karartma_yok"
```
Expected: `performance`, `2500000`, `karartma_yok`. Atakan tahtada Farabi client + yoklamanın normal açıldığını doğrular (Kural 12).

- [ ] **Step 5: Timer'ları etkinleştir** (yalnızca Step 3–4 fiziksel kabulünden sonra)

```bash
sudo systemctl enable --now farabi-tahta-gece.timer farabi-tahta-sabah.timer
systemctl list-timers 'farabi-tahta-*'
```
Expected: NEXT sütununda gece için bugün/yarın 18:00 UTC (= 21:00 +03), sabah için 04:00 UTC (= 07:00 +03).

- [ ] **Step 6: Belgeleme**

`tahtayoklama/CLAUDE.md`'ye bölüm ekle (içerik: iki timer ve saatleri, `scripts/tahta_bakim.py` komutları ve `--kuru`/`--tahta`, okul saati kilidi, ogretmen'in journal okuyamaması → etapadmin+sudo, 9-A'da otomatik giriş olmadığı için karartmanın atlanması, `tahta_bakim` tablosu UTC, birim dosyalarının repo kopyası `dashboard/systemd/`, tahtadaki mevcut `ekran-kapat.timer` (18:00 DPMS off, 9-B'de görüldü, repoda kaydı yok) ile çakışmadığı).

Kök `CLAUDE.md` "Uzaktan yönetim" maddesinin altına:

```markdown
- **Tahta gece/sabah bakımı** (2026-09-29): `farabi-tahta-{gece,sabah}.timer`
  (21:00 / 07:00 İstanbul) → `tahtayoklama/dashboard/scripts/tahta_bakim.py`;
  log tarama + reboot + karartma/CPU tasarrufu, sabah reboot + performance.
  Sonuç `/sistem-durumu` → "Tahta bakımı". Ayrıntı `tahtayoklama/CLAUDE.md`.
```

`DECISIONS.md` en üstüne:

```markdown
## 2026-09-29 - Tahta gece/sabah bakımı: sunucudan systemd timer + SSH, okul saati kilidi
- 21:00'de açık 8 tahtanın journal'ı (etapadmin+sudo; ogretmen journal okuyamıyor) ve Farabi client logu taranıp `tahta_bakim` tablosuna yazılır, tahtalar yeniden başlatılır, açılışta eta-screen-cover + `xset dpms force off` + governor `ondemand`/max_freq=min; 07:00'de reboot + `performance`/max_freq=max. Timer'lar `Europe/Istanbul` (sunucu UTC), `Persistent=false`. "Geri geldi" = boot_id değişti.
- Neden: tahtalarda power-profiles-daemon/tlp yok, yalnızca cpufreq; ayar reboot'ta sıfırlandığı için her açılıştan sonra sunucudan uygulanıyor (tahtaya yeni birim kurmak yerine — provizyon yükü, 9-A'da otomatik giriş yok). Reboot kilidi spec'teki "ders sürüyor" yerine okul saatleri penceresi (08:10–15:50), çünkü teneffüste `simdiki_ders` None dönüyor ve elle çalıştırma tahtaları teneffüste yeniden başlatabilirdi. Spec: `docs/superpowers/specs/2026-09-28-tahta-gece-sabah-bakim-design.md`.
```

- [ ] **Step 7: Commit**

```bash
cd /home/ata/farabi
git add tahtayoklama/CLAUDE.md CLAUDE.md DECISIONS.md
git commit -m "docs: tahta gece/sabah bakimi - CLAUDE.md ve DECISIONS kaydi"
```
