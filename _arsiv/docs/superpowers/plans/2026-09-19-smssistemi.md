# SMS Sistemi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the Müdür PC desktop bulk-SMS tool (`C:\Users\exa\Desktop\sms sistemi\app.py`, Tkinter + `huawei_lte_api`) into a standalone web project (`smssistemi`) on the Farabi server, reachable through a Müdür-PC network bridge (no app code on Müdür PC), with a single nav link from the existing Yoklama Panosu dashboard.

**Architecture:** FastAPI + Jinja2 web app at `/home/ata/farabi/smssistemi/`, fully independent of `tahtayoklama/dashboard` (own venv, own SQLite DB, own systemd service, own auth — code duplicated by pattern, not shared). It talks to the Huawei HiLink modem (`192.168.8.1`, only reachable from Müdür PC's Wi-Fi network) through a `netsh interface portproxy` TCP forward on Müdür PC (`192.168.23.243:18080` → `192.168.8.1:80`), which is pure OS-level network config — no Python runs on Müdür PC for this feature.

**Tech Stack:** Python 3.14, FastAPI 0.118, Jinja2, SQLite (stdlib `sqlite3`), `huawei-lte-api` 2.0.1, pytest (dev only), uvicorn, systemd.

**Spec:** `docs/superpowers/specs/2026-09-19-smssistemi-design.md` (Farabi repo)

## Global Constraints

- `smssistemi` must not import anything from `tahtayoklama/dashboard` — independent project, verified by `grep -r "tahtayoklama" smssistemi/*.py` returning nothing.
- No SPA/fetch framework beyond plain `fetch()` polling — matches dashboard's "keep it light" rule from the spec.
- Modem credentials (`config/modem.json`) and the shared-password hash (`config/gizli.json`) are never committed — add to root `.gitignore` before either file is created.
- Müdür PC gets zero application code for this feature — only a `netsh portproxy` rule and a firewall rule scoped to Farabi's IP (`192.168.23.252`).
- Port assignments (fixed, from the spec): Müdür PC portproxy listens on `192.168.23.243:18080`; `smssistemi` web service runs on Farabi port `8020`.
- Test phone number for the end-to-end send: `5059399303`.

---

### Task 1: Müdür PC — network bridge to the modem

**Files:** none (OS-level network configuration only, on Müdür PC — this machine).

**Interfaces:**
- Produces: a TCP endpoint `192.168.23.243:18080` that transparently forwards to the modem's `192.168.8.1:80`, reachable from Farabi (`192.168.23.252`) only. Task 6/7 depend on this being reachable.

- [ ] **Step 1: Add the portproxy rule**

Run (Bash tool, calls the native Windows executable directly):
```bash
netsh interface portproxy add v4tov4 listenaddress=192.168.23.243 listenport=18080 connectaddress=192.168.8.1 connectport=80
```
If this fails with an access-denied/permission error (this machine has a documented history of UAC blocking non-elevated `netsh`/firewall changes — see `WifiHttpProxyForLan` note in the global CLAUDE.md), stop and ask the user to run the same command in an elevated PowerShell window, then continue.

- [ ] **Step 2: Verify the rule is registered**

Run: `netsh interface portproxy show v4tov4`
Expected: a row showing `192.168.23.243  18080  192.168.8.1  80`.

- [ ] **Step 3: Add a scoped firewall rule**

```bash
netsh advfirewall firewall add rule name="SmsSistemiModemKoprusu" dir=in action=allow protocol=TCP localport=18080 remoteip=192.168.23.252
```
Same elevation caveat as Step 1 applies.

- [ ] **Step 4: Verify firewall rule**

Run: `netsh advfirewall firewall show rule name="SmsSistemiModemKoprusu"`
Expected: rule listed, `RemoteIP: 192.168.23.252`, `LocalPort: 18080`, `Action: Allow`.

- [ ] **Step 5: Verify reachability from Farabi**

Run (Bash tool, SSH to Farabi):
```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "curl -s -m 5 -o /dev/null -w 'HTTP:%{http_code}\n' http://192.168.23.243:18080/"
```
Expected: `HTTP:200` (or any non-`000` code — `000` means the TCP connection itself failed; any real HTTP response confirms the bridge works). If `000`, re-check Steps 1–4 before moving on — nothing past this point can be tested without this working.

---

### Task 2: Farabi — project scaffold

**Files:**
- Create: `/home/ata/farabi/smssistemi/` (directory tree: `config/`, `scripts/`, `templates/`, `static/`, `veri/`)
- Create: `/home/ata/farabi/smssistemi/requirements.txt`
- Create: `/home/ata/farabi/smssistemi/requirements-dev.txt`
- Create: `/home/ata/farabi/smssistemi/config/modem.json` (not committed)
- Modify: `/home/ata/farabi/.gitignore`

**Interfaces:**
- Produces: `venv/bin/python`, `venv/bin/pip`, `venv/bin/pytest`, `venv/bin/uvicorn` for all later tasks. `config/modem.json` schema: `{"host": str, "port": int, "user": str, "pass": str}`, consumed by Task 6's `sms_gonderici.modem_ayarlarini_yukle()`.

- [ ] **Step 1: Create directories and venv**

```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "mkdir -p /home/ata/farabi/smssistemi/{config,scripts,templates,static,veri} && cd /home/ata/farabi/smssistemi && python3 -m venv venv"
```

- [ ] **Step 2: Write requirements.txt**

```
fastapi==0.118.0
uvicorn[standard]==0.38.0
jinja2==3.1.4
python-multipart==0.0.12
huawei-lte-api==2.0.1
```
Write this locally then `pscp` to `/home/ata/farabi/smssistemi/requirements.txt` (same pattern as the spec doc: `Write` tool locally, `pscp -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" <local> ata@farabi.local:<remote>`).

- [ ] **Step 3: Write requirements-dev.txt**

```
pytest==8.3.4
```
Same local-write + `pscp` pattern, to `/home/ata/farabi/smssistemi/requirements-dev.txt`.

- [ ] **Step 4: Install dependencies**

```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi/smssistemi && venv/bin/pip install -r requirements.txt -r requirements-dev.txt"
```
Expected: all five packages (plus transitive deps) install without error.

- [ ] **Step 5: Add gitignore entries before any secret file exists**

Modify `/home/ata/farabi/.gitignore` — append:
```
smssistemi/config/gizli.json
smssistemi/config/modem.json
smssistemi/veri/
```
Fetch current `.gitignore`, append via Edit locally, `pscp` back — or append directly over SSH:
```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "printf '\nsmssistemi/config/gizli.json\nsmssistemi/config/modem.json\nsmssistemi/veri/\n' >> /home/ata/farabi/.gitignore"
```

- [ ] **Step 6: Write config/modem.json (migrated credentials, not committed)**

The modem credentials are the ones already in `C:\Users\exa\Desktop\sms sistemi\sifre.json` (`user: admin`, `pass: 115115115`); only `host`/`port` differ here (point at the Task 1 bridge, not the modem's own LAN IP):
```json
{
  "host": "192.168.23.243",
  "port": 18080,
  "user": "admin",
  "pass": "115115115"
}
```
Write locally, `pscp` to `/home/ata/farabi/smssistemi/config/modem.json`. Confirm it did NOT get committed in Task 2's final commit (Step 7) — `git status` should not list it (it's gitignored as of Step 5).

- [ ] **Step 7: Commit the scaffold**

```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi && git add .gitignore smssistemi/requirements.txt smssistemi/requirements-dev.txt && git -c user.email='atakanunver1@gmail.com' -c user.name='Atakan' commit -m 'smssistemi: proje iskeleti' && git status"
```
Expected: commit succeeds; `git status` shows `config/modem.json` and `veri/` NOT tracked (ignored), `venv/` not tracked (covered by root `**/venv/`).

---

### Task 3: `db.py` — SQLite schema and connection helpers

**Files:**
- Create: `/home/ata/farabi/smssistemi/db.py`
- Test: `/home/ata/farabi/smssistemi/test_db.py`

**Interfaces:**
- Produces: `db.baglanti() -> sqlite3.Connection`, `db.semayi_kur() -> None`, `db.gonderim_kaydet(conn, gonderim_id: str, isim: str, telefon: str, mesaj: str, durum: str, hata_metni: str | None = None) -> None`, `db.gonderim_satirlari(conn, gonderim_id: str) -> list[dict]`, `db.gonderim_ozetleri(conn, limit: int = 30) -> list[dict]`, `db.gonderim_basarisizlari(conn, gonderim_id: str) -> list[tuple[str, str, str]]` (returns `(isim, telefon, mesaj)` for rows with `durum='hata'` and a non-empty `telefon` — excludes the whole-batch connection-error placeholder row, which has an empty `telefon`). Task 7 (`app.py`) and Task 4 (`auth.py`, via `oturumlar` table) depend on these.

- [ ] **Step 1: Write the failing test**

`test_db.py`:
```python
import db


def test_semayi_kur_ve_gonderim_kaydet(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test.db")
    db.semayi_kur()
    conn = db.baglanti()
    db.gonderim_kaydet(conn, "batch1", "Ahmet", "05551234567", "merhaba", "gonderildi")
    db.gonderim_kaydet(conn, "batch1", "Ayse", "05551234568", "merhaba", "hata", "baglanti hatasi")
    satirlar = db.gonderim_satirlari(conn, "batch1")
    conn.close()
    assert len(satirlar) == 2
    assert satirlar[0]["isim"] == "Ahmet"
    assert satirlar[0]["durum"] == "gonderildi"
    assert satirlar[1]["hata_metni"] == "baglanti hatasi"


def test_gonderim_ozetleri_gruplar_ve_sayar(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test2.db")
    db.semayi_kur()
    conn = db.baglanti()
    db.gonderim_kaydet(conn, "b1", "A", "0555", "m", "gonderildi")
    db.gonderim_kaydet(conn, "b1", "B", "0556", "m", "hata", "x")
    db.gonderim_kaydet(conn, "b2", "C", "0557", "m", "gonderildi")
    ozetler = db.gonderim_ozetleri(conn)
    conn.close()
    ozet_by_id = {o["gonderim_id"]: o for o in ozetler}
    assert ozet_by_id["b1"]["toplam"] == 2
    assert ozet_by_id["b1"]["basarili"] == 1
    assert ozet_by_id["b1"]["hatali"] == 1
    assert ozet_by_id["b2"]["toplam"] == 1


def test_gonderim_basarisizlari_sadece_hatali_ve_telefonlu_satirlari_doner(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test3.db")
    db.semayi_kur()
    conn = db.baglanti()
    db.gonderim_kaydet(conn, "b1", "A", "0555", "merhaba A", "gonderildi")
    db.gonderim_kaydet(conn, "b1", "B", "0556", "merhaba B", "hata", "modem hata kodu")
    db.gonderim_kaydet(conn, "b1", "", "", "merhaba C", "hata", "BAĞLANTI HATASI: timeout")
    basarisizlar = db.gonderim_basarisizlari(conn, "b1")
    conn.close()
    assert basarisizlar == [("B", "0556", "merhaba B")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi/smssistemi && venv/bin/python -m pytest test_db.py -v"`
Expected: FAIL — `ModuleNotFoundError: No module named 'db'` (file doesn't exist yet). Write and `pscp` the test file first, then run this.

- [ ] **Step 3: Write db.py**

```python
"""SQLite bağlantı yardımcıları ve şema — smssistemi'nin tek durum kaynağı.
tahtayoklama/dashboard'un db.py deseninin bağımsız kopyası (kod paylaşımı
yok, bkz. docs/superpowers/specs/2026-09-19-smssistemi-design.md)."""

import sqlite3
from pathlib import Path

DB_YOLU = Path(__file__).resolve().parent / "veri" / "smssistemi.db"

SEMA = """
CREATE TABLE IF NOT EXISTS gonderimler (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    gonderim_id   TEXT NOT NULL,
    isim          TEXT,
    telefon       TEXT NOT NULL,
    mesaj         TEXT NOT NULL,
    durum         TEXT NOT NULL,
    hata_metni    TEXT,
    zaman         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS oturumlar (
    token             TEXT PRIMARY KEY,
    olusturma_zamani  TEXT NOT NULL DEFAULT (datetime('now')),
    son_gorulme       TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def baglanti() -> sqlite3.Connection:
    DB_YOLU.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_YOLU)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def semayi_kur() -> None:
    conn = baglanti()
    try:
        conn.executescript(SEMA)
        conn.commit()
    finally:
        conn.close()


def gonderim_kaydet(
    conn: sqlite3.Connection,
    gonderim_id: str,
    isim: str,
    telefon: str,
    mesaj: str,
    durum: str,
    hata_metni: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO gonderimler (gonderim_id, isim, telefon, mesaj, durum, hata_metni) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (gonderim_id, isim, telefon, mesaj, durum, hata_metni),
    )
    conn.commit()


def gonderim_satirlari(conn: sqlite3.Connection, gonderim_id: str) -> list[dict]:
    satirlar = conn.execute(
        "SELECT isim, telefon, durum, hata_metni, zaman FROM gonderimler "
        "WHERE gonderim_id = ? ORDER BY id",
        (gonderim_id,),
    ).fetchall()
    return [dict(r) for r in satirlar]


def gonderim_ozetleri(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    satirlar = conn.execute(
        "SELECT gonderim_id, "
        "MIN(zaman) AS ilk_zaman, "
        "COUNT(*) AS toplam, "
        "SUM(CASE WHEN durum = 'gonderildi' THEN 1 ELSE 0 END) AS basarili, "
        "SUM(CASE WHEN durum = 'hata' THEN 1 ELSE 0 END) AS hatali "
        "FROM gonderimler GROUP BY gonderim_id ORDER BY ilk_zaman DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in satirlar]


def gonderim_basarisizlari(conn: sqlite3.Connection, gonderim_id: str) -> list[tuple[str, str, str]]:
    satirlar = conn.execute(
        "SELECT isim, telefon, mesaj FROM gonderimler "
        "WHERE gonderim_id = ? AND durum = 'hata' AND telefon != '' "
        "ORDER BY id",
        (gonderim_id,),
    ).fetchall()
    return [(r["isim"], r["telefon"], r["mesaj"]) for r in satirlar]
```
Write locally, `pscp` to `/home/ata/farabi/smssistemi/db.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi/smssistemi && venv/bin/python -m pytest test_db.py -v"`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi && git add smssistemi/db.py smssistemi/test_db.py && git -c user.email='atakanunver1@gmail.com' -c user.name='Atakan' commit -m 'smssistemi: db.py + testler'"
```

---

### Task 4: `gonderim.py` — phone parsing, validation, CSV import, personalization

**Files:**
- Create: `/home/ata/farabi/smssistemi/gonderim.py`
- Test: `/home/ata/farabi/smssistemi/test_gonderim.py`

**Interfaces:**
- Produces: `gonderim.normalize_phone(raw: str) -> str`, `gonderim.is_valid_phone(tel: str) -> bool`, `gonderim.is_ascii(text: str) -> bool`, `gonderim.metinden_ayristir(numaralar_metni: str) -> tuple[list[tuple[str, str]], list[str]]`, `gonderim.csv_ayristir(icerik: bytes) -> list[tuple[str, str]]`, `gonderim.kisisellestir(mesaj_sablonu: str, isim: str) -> str`. Task 6 (`sms_gonderici.py`) consumes `is_ascii`; Task 7 (`app.py`) consumes all of them.

- [ ] **Step 1: Write the failing tests**

`test_gonderim.py`:
```python
import gonderim


def test_normalize_phone_ulusal_format_degistirmez():
    assert gonderim.normalize_phone("05551234567") == "05551234567"


def test_normalize_phone_10_haneliyi_sifirla_tamamlar():
    assert gonderim.normalize_phone("5551234567") == "05551234567"


def test_normalize_phone_uluslararasi_00_prefiksini_artiya_cevirir():
    assert gonderim.normalize_phone("00905551234567") == "+905551234567"


def test_is_valid_phone_gecerli_ulusal():
    assert gonderim.is_valid_phone("05551234567") is True


def test_is_valid_phone_gecersiz_kisa():
    assert gonderim.is_valid_phone("0555123456") is False


def test_is_ascii_turkce_karakterde_false_doner():
    assert gonderim.is_ascii("merhaba İ") is False
    assert gonderim.is_ascii("merhaba") is True


def test_metinden_ayristir_karisik_satirlari_ayirir():
    metin = "Ahmet,05551234567\n123\nAyse,05551234568"
    gecerli, gecersiz = gonderim.metinden_ayristir(metin)
    assert gecerli == [("Ahmet", "05551234567"), ("Ayse", "05551234568")]
    assert gecersiz == ["123"]


def test_csv_ayristir_baslik_satirini_atlar():
    icerik = "isim,telefon\nAhmet Yilmaz,05551234567\n".encode("utf-8-sig")
    sonuc = gonderim.csv_ayristir(icerik)
    assert sonuc == [("Ahmet Yilmaz", "05551234567")]


def test_kisisellestir_yer_tutucuyu_degistirir():
    assert gonderim.kisisellestir("Merhaba {isim}", "Ahmet") == "Merhaba Ahmet"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi/smssistemi && venv/bin/python -m pytest test_gonderim.py -v"`
Expected: FAIL — `ModuleNotFoundError: No module named 'gonderim'`.

- [ ] **Step 3: Write gonderim.py**

```python
"""Numara ayrıştırma/doğrulama + CSV içe aktarma + mesaj kişiselleştirme.

C:\\Users\\exa\\Desktop\\sms sistemi\\app.py'deki normalize_phone/
is_valid_phone/_load_csv mantığının web sürümü — Tkinter'a özgü hiçbir şey
yok, saf fonksiyonlar, app.py tarafından çağrılır.
"""

import csv
import io
import re

_TELEFON_RE_ULUSAL = re.compile(r"05\d{9}")
_TELEFON_RE_ULUSLARARASI = re.compile(r"\+905\d{9}")


def normalize_phone(raw: str) -> str:
    raw = raw.strip()
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("0090"):
        digits = "+90" + digits[4:]
    if digits.startswith("90") and len(digits) == 12:
        digits = "+" + digits
    if digits.startswith("5") and len(digits) == 10:
        digits = "0" + digits
    return digits


def is_valid_phone(tel: str) -> bool:
    if tel.startswith("+90"):
        return bool(_TELEFON_RE_ULUSLARARASI.fullmatch(tel))
    return bool(_TELEFON_RE_ULUSAL.fullmatch(tel))


def is_ascii(text: str) -> bool:
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def metinden_ayristir(numaralar_metni: str) -> tuple[list[tuple[str, str]], list[str]]:
    gecerli: list[tuple[str, str]] = []
    gecersiz: list[str] = []
    for satir in numaralar_metni.splitlines():
        satir = satir.strip()
        if not satir:
            continue
        if "," in satir:
            isim, tel_ham = satir.split(",", 1)
        else:
            isim, tel_ham = "", satir
        tel = normalize_phone(tel_ham)
        if tel and is_valid_phone(tel):
            gecerli.append((isim.strip(), tel))
        else:
            gecersiz.append(satir)
    return gecerli, gecersiz


def csv_ayristir(icerik: bytes) -> list[tuple[str, str]]:
    metin = icerik.decode("utf-8-sig")
    ornek = metin[:2048]
    ayirici = ";" if ornek.count(";") > ornek.count(",") else ","
    okuyucu = csv.reader(io.StringIO(metin), delimiter=ayirici)
    sonuc: list[tuple[str, str]] = []
    for satir in okuyucu:
        satir = [c.strip() for c in satir if c.strip()]
        if not satir:
            continue
        if satir[0].lower() in ("isim", "ad", "name", "telefon", "phone"):
            continue
        if len(satir) >= 2:
            sonuc.append((satir[0], satir[1]))
        else:
            sonuc.append(("", satir[0]))
    return sonuc


def kisisellestir(mesaj_sablonu: str, isim: str) -> str:
    return mesaj_sablonu.replace("{isim}", isim or "")
```
Write locally, `pscp` to `/home/ata/farabi/smssistemi/gonderim.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi/smssistemi && venv/bin/python -m pytest test_gonderim.py -v"`
Expected: `9 passed`.

- [ ] **Step 5: Commit**

```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi && git add smssistemi/gonderim.py smssistemi/test_gonderim.py && git -c user.email='atakanunver1@gmail.com' -c user.name='Atakan' commit -m 'smssistemi: gonderim.py + testler'"
```

---

### Task 5: `auth.py` — shared-password login + session cookies

**Files:**
- Create: `/home/ata/farabi/smssistemi/auth.py`
- Create: `/home/ata/farabi/smssistemi/scripts/sifre_belirle.py`
- Test: `/home/ata/farabi/smssistemi/test_auth.py`

**Interfaces:**
- Produces: `auth.COOKIE_ADI: str`, `auth.sifre_hashle(sifre: str, tuz: bytes | None = None) -> str`, `auth.sifre_dogrula(sifre: str, hash_str: str) -> bool`, `auth.giris_dene(sifre: str) -> bool`, `auth.oturum_olustur(conn) -> str`, `auth.oturum_sil(conn, token: str) -> None`, `auth.oturum_gecerli_mi(conn, token: str | None) -> bool`. Task 7 (`app.py`) depends on all of these.
- Consumes: `db.baglanti`/`oturumlar` table from Task 3 (only at call sites in Task 7, not inside `auth.py` itself).

- [ ] **Step 1: Write the failing tests**

`test_auth.py` (only the pure hash/verify functions — `giris_dene`/`oturum_*` need a live `config/gizli.json` or DB connection and are covered by manual verification in Step 5 of this task and in Task 7):
```python
import auth


def test_sifre_hashle_dogru_sifreyle_dogrulanir():
    hash_str = auth.sifre_hashle("gizliSifre123")
    assert auth.sifre_dogrula("gizliSifre123", hash_str) is True


def test_sifre_dogrula_yanlis_sifreyi_reddeder():
    hash_str = auth.sifre_hashle("gizliSifre123")
    assert auth.sifre_dogrula("baskaSifre", hash_str) is False


def test_sifre_dogrula_bozuk_hash_formatinda_false_doner():
    assert auth.sifre_dogrula("herhangi", "gecersiz-format") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi/smssistemi && venv/bin/python -m pytest test_auth.py -v"`
Expected: FAIL — `ModuleNotFoundError: No module named 'auth'`.

- [ ] **Step 3: Write auth.py**

```python
"""Tek ortak şifreyle giriş — dashboard'un auth.py deseninin bağımsız
kopyası (bkz. docs/superpowers/specs/2026-09-19-smssistemi-design.md
"Güvenlik" bölümü — kod paylaşımı kasıtlı olarak yok)."""

import hashlib
import hmac
import json
import secrets
from pathlib import Path

from fastapi import HTTPException

GIZLI_YOLU = Path(__file__).resolve().parent / "config" / "gizli.json"
COOKIE_ADI = "smssistemi_oturum"


def sifre_hashle(sifre: str, tuz: bytes | None = None) -> str:
    tuz = tuz or secrets.token_bytes(16)
    dk = hashlib.scrypt(sifre.encode("utf-8"), salt=tuz, n=2**14, r=8, p=1)
    return f"{tuz.hex()}${dk.hex()}"


def sifre_dogrula(sifre: str, hash_str: str) -> bool:
    try:
        tuz_hex, dk_hex = hash_str.split("$", 1)
    except ValueError:
        return False
    tuz = bytes.fromhex(tuz_hex)
    beklenen = hashlib.scrypt(sifre.encode("utf-8"), salt=tuz, n=2**14, r=8, p=1)
    return hmac.compare_digest(beklenen, bytes.fromhex(dk_hex))


def _gizli_yukle() -> dict:
    if not GIZLI_YOLU.exists():
        raise HTTPException(
            500,
            "config/gizli.json yok — önce 'venv/bin/python scripts/sifre_belirle.py' çalıştırın.",
        )
    return json.loads(GIZLI_YOLU.read_text(encoding="utf-8"))


def giris_dene(sifre: str) -> bool:
    gizli = _gizli_yukle()
    return sifre_dogrula(sifre, gizli["sifre_hash"])


def oturum_olustur(conn) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO oturumlar (token) VALUES (?)", (token,))
    conn.commit()
    return token


def oturum_sil(conn, token: str) -> None:
    conn.execute("DELETE FROM oturumlar WHERE token = ?", (token,))
    conn.commit()


def oturum_gecerli_mi(conn, token: str | None) -> bool:
    if not token:
        return False
    satir = conn.execute("SELECT token FROM oturumlar WHERE token = ?", (token,)).fetchone()
    if satir is None:
        return False
    conn.execute("UPDATE oturumlar SET son_gorulme = datetime('now') WHERE token = ?", (token,))
    conn.commit()
    return True
```
Write locally, `pscp` to `/home/ata/farabi/smssistemi/auth.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi/smssistemi && venv/bin/python -m pytest test_auth.py -v"`
Expected: `3 passed`.

- [ ] **Step 5: Write scripts/sifre_belirle.py and set the shared password**

```python
"""smssistemi'nin ortak giriş şifresini belirler, hash'ini config/gizli.json'a yazar.

Kullanım: smssistemi/ dizininden `venv/bin/python scripts/sifre_belirle.py`
"""

import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth import sifre_hashle  # noqa: E402

GIZLI_YOLU = Path(__file__).resolve().parent.parent / "config" / "gizli.json"


def main() -> None:
    sifre = getpass.getpass("Yeni SMS sistemi şifresi: ")
    tekrar = getpass.getpass("Tekrar: ")
    if sifre != tekrar:
        print("Şifreler eşleşmiyor.", file=sys.stderr)
        sys.exit(1)
    if len(sifre) < 6:
        print("Şifre en az 6 karakter olmalı.", file=sys.stderr)
        sys.exit(1)

    GIZLI_YOLU.parent.mkdir(parents=True, exist_ok=True)
    GIZLI_YOLU.write_text(
        json.dumps({"sifre_hash": sifre_hashle(sifre)}, indent=2),
        encoding="utf-8",
    )
    print(f"Yazıldı: {GIZLI_YOLU}")


if __name__ == "__main__":
    main()
```
Write locally, `pscp` to `/home/ata/farabi/smssistemi/scripts/sifre_belirle.py`. This is the canonical way to set the password later (e.g. to change it), but it prompts on a TTY (`getpass`), which a scripted SSH call can't drive — for this initial setup, ask the user for a password to use (or confirm reusing the dashboard's own shared password), then write `config/gizli.json` directly with the same JSON shape the script produces:
```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi/smssistemi && venv/bin/python -c \"import json,pathlib; from auth import sifre_hashle; pathlib.Path('config/gizli.json').write_text(json.dumps({'sifre_hash': sifre_hashle('<KULLANICIDAN_ALINAN_SIFRE>')}, indent=2))\""
```
Replace `<KULLANICIDAN_ALINAN_SIFRE>` with the actual password the user chose — do not proceed with a placeholder value.

- [ ] **Step 6: Commit (gizli.json stays untracked)**

```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi && git add smssistemi/auth.py smssistemi/test_auth.py smssistemi/scripts/sifre_belirle.py && git -c user.email='atakanunver1@gmail.com' -c user.name='Atakan' commit -m 'smssistemi: auth.py + sifre_belirle.py + testler' && git status"
```
Expected: `config/gizli.json` not listed in `git status` (ignored per Task 2 Step 5).

---

### Task 6: `sms_gonderici.py` — Huawei modem bridge client

**Files:**
- Create: `/home/ata/farabi/smssistemi/sms_gonderici.py`

**Interfaces:**
- Consumes: `gonderim.is_ascii` (Task 4), `config/modem.json` (Task 2 Step 6).
- Produces: `sms_gonderici.modem_ayarlarini_yukle() -> dict`, `sms_gonderici.baglantiyi_test_et(ayarlar: dict) -> dict`, `sms_gonderici.toplu_gonder(ayarlar: dict, kisiler: list[tuple[str, str, str]], sonuc_callback: Callable[[str, str, str, str, str | None], None], durdur_bayragi: threading.Event, bekleme_sn: float) -> None` — `sonuc_callback` receives `(isim, telefon, mesaj, durum, hata_metni)` per contact. Task 7 (`app.py`) depends on this exact signature.

No automated test here — this module makes real HTTP calls to a physical modem over the Task 1 bridge; there is nothing meaningful to unit-test without mocking `huawei_lte_api` (low value, no existing precedent for it in this codebase — `admin.py`/`ssh_istemci.py` in the dashboard don't mock SSH either). Verified manually in Step 2 below and end-to-end in Task 10.

- [ ] **Step 1: Write sms_gonderici.py**

```python
"""Huawei HiLink modem köprüsü — Müdür PC'deki netsh portproxy üzerinden
(bkz. docs/superpowers/specs/2026-09-19-smssistemi-design.md "Mimari").
huawei_lte_api'nin gerçek ağ çağrılarını yapan tek yer; app.py bunu
threading.Thread içinde çağırır (senkron/bloklayan kütüphane).
"""

import json
import time
from pathlib import Path
from threading import Event
from typing import Callable

from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from huawei_lte_api.enums.sms import TextModeEnum

from gonderim import is_ascii

MODEM_CONFIG_YOLU = Path(__file__).resolve().parent / "config" / "modem.json"


def modem_ayarlarini_yukle() -> dict:
    veri = json.loads(MODEM_CONFIG_YOLU.read_text(encoding="utf-8"))
    return {"host": veri["host"], "port": veri["port"], "user": veri["user"], "pass": veri["pass"]}


def _baglanti_url(ayarlar: dict) -> str:
    return f"http://{ayarlar['user']}:{ayarlar['pass']}@{ayarlar['host']}:{ayarlar['port']}/"


def baglantiyi_test_et(ayarlar: dict) -> dict:
    with Connection(_baglanti_url(ayarlar)) as connection:
        client = Client(connection)
        info = client.device.information()
        signal = client.device.signal()
    return {"cihaz": info.get("DeviceName", "?"), "sinyal": signal.get("rssi", "?")}


def toplu_gonder(
    ayarlar: dict,
    kisiler: list[tuple[str, str, str]],
    sonuc_callback: Callable[[str, str, str, str, str | None], None],
    durdur_bayragi: Event,
    bekleme_sn: float,
) -> None:
    try:
        with Connection(_baglanti_url(ayarlar)) as connection:
            client = Client(connection)
            for i, (isim, telefon, mesaj) in enumerate(kisiler):
                if durdur_bayragi.is_set():
                    break
                mode = TextModeEnum.SEVEN_BIT if is_ascii(mesaj) else TextModeEnum.UCS2
                try:
                    client.sms.send_sms([telefon], mesaj, text_mode=mode)
                    sonuc_callback(isim, telefon, mesaj, "gonderildi", None)
                except Exception as exc:  # noqa: BLE001 - modem API'si spesifik olmayan hatalar fırlatabiliyor
                    sonuc_callback(isim, telefon, mesaj, "hata", str(exc))
                if i < len(kisiler) - 1 and not durdur_bayragi.is_set():
                    time.sleep(bekleme_sn)
    except Exception as exc:  # noqa: BLE001 - bağlantı hatası, tüm batch için
        sonuc_callback("", "", "", "hata", f"BAĞLANTI HATASI: {exc}")
```
Write locally, `pscp` to `/home/ata/farabi/smssistemi/sms_gonderici.py`.

- [ ] **Step 2: Manually verify modem connectivity through the bridge**

Run:
```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi/smssistemi && venv/bin/python -c \"import sms_gonderici; print(sms_gonderici.baglantiyi_test_et(sms_gonderici.modem_ayarlarini_yukle()))\""
```
Expected: prints a dict like `{'cihaz': 'B535-232', 'sinyal': '...'}` — no exception. If it raises a connection/auth error, re-check Task 1's bridge and `config/modem.json` credentials before continuing.

- [ ] **Step 3: Commit**

```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi && git add smssistemi/sms_gonderici.py && git -c user.email='atakanunver1@gmail.com' -c user.name='Atakan' commit -m 'smssistemi: sms_gonderici.py (modem koprusu)'"
```

---

### Task 7: `app.py` + templates + static — the web UI

**Files:**
- Create: `/home/ata/farabi/smssistemi/app.py`
- Create: `/home/ata/farabi/smssistemi/templates/taban.html`
- Create: `/home/ata/farabi/smssistemi/templates/giris.html`
- Create: `/home/ata/farabi/smssistemi/templates/gonder.html`
- Create: `/home/ata/farabi/smssistemi/templates/durum.html`
- Create: `/home/ata/farabi/smssistemi/templates/kayitlar.html`
- Create: `/home/ata/farabi/smssistemi/static/stil.css`

**Interfaces:**
- Consumes: `db.*` (Task 3, including `gonderim_basarisizlari` for the retry route), `gonderim.*` (Task 4), `auth.*` (Task 5), `sms_gonderici.*` (Task 6).
- Produces: the running FastAPI app object `app`, consumed by Task 8's uvicorn/systemd invocation (`uvicorn app:app`). Routes include `POST /tekrar-gonder/{gonderim_id}` (retries only the failed contacts from a prior batch under a new `gonderim_id`).

- [ ] **Step 1: Write app.py**

```python
"""SMS Sistemi — FastAPI giriş noktası.

Çalıştırma: `uvicorn app:app --host 0.0.0.0 --port 8020` (smssistemi/
dizininden, kendi venv'i içinde). tahtayoklama/dashboard'dan BAĞIMSIZ —
bkz. docs/superpowers/specs/2026-09-19-smssistemi-design.md.
"""

import threading
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import auth
import db
import gonderim
import sms_gonderici

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

_DURDUR_BAYRAKLARI: dict[str, threading.Event] = {}


@app.on_event("startup")
def _baslangic() -> None:
    db.semayi_kur()


def _oturum_sarti(request: Request, conn) -> None:
    if not auth.oturum_gecerli_mi(conn, request.cookies.get(auth.COOKIE_ADI)):
        raise HTTPException(401, "Oturum geçersiz.")


@app.get("/giris", response_class=HTMLResponse)
async def giris_formu(request: Request):
    return templates.TemplateResponse(request, "giris.html", {"hata": None})


@app.post("/giris")
async def giris_gonder(request: Request, sifre: str = Form(...)):
    if not auth.giris_dene(sifre):
        return templates.TemplateResponse(
            request, "giris.html", {"hata": "Şifre yanlış."}, status_code=401
        )
    conn = db.baglanti()
    try:
        token = auth.oturum_olustur(conn)
    finally:
        conn.close()
    yanit = RedirectResponse("/", status_code=303)
    yanit.set_cookie(auth.COOKIE_ADI, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return yanit


@app.post("/cikis")
async def cikis(request: Request):
    token = request.cookies.get(auth.COOKIE_ADI)
    conn = db.baglanti()
    try:
        if token:
            auth.oturum_sil(conn, token)
    finally:
        conn.close()
    yanit = RedirectResponse("/giris", status_code=303)
    yanit.delete_cookie(auth.COOKIE_ADI)
    return yanit


@app.get("/", response_class=HTMLResponse)
async def anasayfa(request: Request):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "gonder.html", {"hata": None, "onizleme_numaralar": ""})


@app.post("/gonder")
async def gonder(
    request: Request,
    numaralar: str = Form(""),
    mesaj: str = Form(...),
    bekleme_sn: float = Form(2.0),
    csv_dosya: UploadFile | None = File(None),
):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
    finally:
        conn.close()

    satirlar = numaralar
    if csv_dosya is not None and csv_dosya.filename:
        icerik = await csv_dosya.read()
        yuklenen = gonderim.csv_ayristir(icerik)
        satirlar = "\n".join(f"{isim},{tel}" if isim else tel for isim, tel in yuklenen)

    gecerli, _gecersiz = gonderim.metinden_ayristir(satirlar)
    if not gecerli:
        return templates.TemplateResponse(
            request,
            "gonder.html",
            {"hata": "Gönderilecek geçerli numara yok.", "onizleme_numaralar": satirlar},
            status_code=400,
        )

    gonderim_id = uuid.uuid4().hex[:12]
    kisiler = [(isim, tel, gonderim.kisisellestir(mesaj, isim)) for isim, tel in gecerli]
    thread = threading.Thread(
        target=_gonderim_calistir, args=(gonderim_id, kisiler, bekleme_sn), daemon=True
    )
    thread.start()
    return RedirectResponse(f"/durum/{gonderim_id}", status_code=303)


def _gonderim_calistir(gonderim_id: str, kisiler: list[tuple[str, str, str]], bekleme_sn: float) -> None:
    bayrak = threading.Event()
    _DURDUR_BAYRAKLARI[gonderim_id] = bayrak
    conn = db.baglanti()

    def kaydet(isim: str, telefon: str, mesaj: str, durum: str, hata_metni: str | None) -> None:
        db.gonderim_kaydet(conn, gonderim_id, isim, telefon, mesaj, durum, hata_metni)

    try:
        ayarlar = sms_gonderici.modem_ayarlarini_yukle()
        sms_gonderici.toplu_gonder(ayarlar, kisiler, kaydet, bayrak, bekleme_sn)
    finally:
        conn.close()
        _DURDUR_BAYRAKLARI.pop(gonderim_id, None)


@app.post("/durdur/{gonderim_id}")
async def durdur(request: Request, gonderim_id: str):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
    finally:
        conn.close()
    bayrak = _DURDUR_BAYRAKLARI.get(gonderim_id)
    if bayrak is not None:
        bayrak.set()
    return JSONResponse({"durduruldu": bayrak is not None})


@app.post("/tekrar-gonder/{gonderim_id}")
async def tekrar_gonder(request: Request, gonderim_id: str, bekleme_sn: float = Form(2.0)):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        basarisizlar = db.gonderim_basarisizlari(conn, gonderim_id)
    finally:
        conn.close()

    if not basarisizlar:
        return RedirectResponse(f"/durum/{gonderim_id}", status_code=303)

    yeni_gonderim_id = uuid.uuid4().hex[:12]
    thread = threading.Thread(
        target=_gonderim_calistir, args=(yeni_gonderim_id, basarisizlar, bekleme_sn), daemon=True
    )
    thread.start()
    return RedirectResponse(f"/durum/{yeni_gonderim_id}", status_code=303)


@app.get("/durum/{gonderim_id}", response_class=HTMLResponse)
async def durum_sayfasi(request: Request, gonderim_id: str):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "durum.html", {"gonderim_id": gonderim_id})


@app.get("/api/durum/{gonderim_id}")
async def durum_api(request: Request, gonderim_id: str):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        satirlar = db.gonderim_satirlari(conn, gonderim_id)
    finally:
        conn.close()
    devam_ediyor = gonderim_id in _DURDUR_BAYRAKLARI
    return JSONResponse({"satirlar": satirlar, "devam_ediyor": devam_ediyor})


@app.get("/kayitlar", response_class=HTMLResponse)
async def kayitlar(request: Request):
    conn = db.baglanti()
    try:
        _oturum_sarti(request, conn)
        ozetler = db.gonderim_ozetleri(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "kayitlar.html", {"ozetler": ozetler})
```
Write locally, `pscp` to `/home/ata/farabi/smssistemi/app.py`.

- [ ] **Step 2: Write templates/taban.html**

```html
<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block baslik_etiketi %}SMS Sistemi{% endblock %}</title>
<link rel="stylesheet" href="/static/stil.css">
</head>
<body>
<header class="ust-cubuk">
  <a href="/" class="marka">📨 SMS Sistemi</a>
  <nav>
    <a href="/" class="{{ 'aktif' if request.url.path == '/' else '' }}">Gönder</a>
    <a href="/kayitlar" class="{{ 'aktif' if request.url.path == '/kayitlar' else '' }}">Kayıtlar</a>
  </nav>
  <form method="post" action="/cikis" class="cikis-form">
    <button type="submit">Çıkış</button>
  </form>
</header>
<main>
{% block icerik %}{% endblock %}
</main>
</body>
</html>
```

- [ ] **Step 3: Write templates/giris.html**

```html
<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Giriş — SMS Sistemi</title>
<link rel="stylesheet" href="/static/stil.css">
</head>
<body>
<main class="giris-sarici">
  <form method="post" action="/giris" class="giris-form">
    <h1>SMS Sistemi</h1>
    {% if hata %}<p class="hata">{{ hata }}</p>{% endif %}
    <label>Şifre <input type="password" name="sifre" autofocus required></label>
    <button type="submit">Giriş</button>
  </form>
</main>
</body>
</html>
```

- [ ] **Step 4: Write templates/gonder.html**

```html
{% extends "taban.html" %}
{% block baslik_etiketi %}Gönder — SMS Sistemi{% endblock %}
{% block icerik %}
<h1>Toplu SMS Gönder</h1>
{% if hata %}<p class="hata">{{ hata }}</p>{% endif %}
<form method="post" action="/gonder" enctype="multipart/form-data" class="gonder-form">
  <label>Numaralar (bir satıra bir kişi: "isim,telefon" ya da sadece telefon)
    <textarea name="numaralar" rows="8">{{ onizleme_numaralar }}</textarea>
  </label>
  <label>ya da CSV yükle
    <input type="file" name="csv_dosya" accept=".csv">
  </label>
  <label>Mesaj (kişiselleştirme için {isim} kullanabilirsiniz)
    <textarea name="mesaj" rows="4" required></textarea>
  </label>
  <label>Gönderimler arası bekleme (sn)
    <input type="number" name="bekleme_sn" value="2" min="0.5" step="0.5">
  </label>
  <button type="submit">Gönder</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Write templates/durum.html**

```html
{% extends "taban.html" %}
{% block baslik_etiketi %}Gönderim Durumu — SMS Sistemi{% endblock %}
{% block icerik %}
<h1>Gönderim Durumu</h1>
<button type="button" id="durdur-btn">Durdur</button>
<form method="post" id="tekrar-form" action="/tekrar-gonder/{{ gonderim_id }}" style="display:inline">
  <button type="submit" id="tekrar-btn" disabled>Başarısızları Tekrar Gönder</button>
</form>
<table id="durum-tablo">
  <thead><tr><th>İsim</th><th>Telefon</th><th>Durum</th><th>Hata</th><th>Zaman</th></tr></thead>
  <tbody id="durum-govde"></tbody>
</table>
<script>
const GONDERIM_ID = {{ gonderim_id | tojson }};
const GOVDE = document.getElementById('durum-govde');
const DURDUR_BTN = document.getElementById('durdur-btn');
const TEKRAR_BTN = document.getElementById('tekrar-btn');

async function yenile() {
  const yanit = await fetch(`/api/durum/${GONDERIM_ID}`);
  const veri = await yanit.json();
  GOVDE.innerHTML = veri.satirlar.map(s => `<tr class="${s.durum}">
    <td>${s.isim || ''}</td><td>${s.telefon || ''}</td>
    <td>${s.durum}</td><td>${s.hata_metni || ''}</td><td>${s.zaman}</td>
  </tr>`).join('');
  DURDUR_BTN.disabled = !veri.devam_ediyor;
  const hataliVarMi = veri.satirlar.some(s => s.durum === 'hata' && s.telefon);
  TEKRAR_BTN.disabled = veri.devam_ediyor || !hataliVarMi;
  if (veri.devam_ediyor) setTimeout(yenile, 1500);
}

DURDUR_BTN.addEventListener('click', async () => {
  await fetch(`/durdur/${GONDERIM_ID}`, { method: 'POST' });
});

yenile();
</script>
{% endblock %}
```

- [ ] **Step 6: Write templates/kayitlar.html**

```html
{% extends "taban.html" %}
{% block baslik_etiketi %}Kayıtlar — SMS Sistemi{% endblock %}
{% block icerik %}
<h1>Geçmiş Gönderimler</h1>
<table>
  <thead><tr><th>Tarih</th><th>Toplam</th><th>Başarılı</th><th>Hatalı</th><th></th></tr></thead>
  <tbody>
    {% for o in ozetler %}
    <tr>
      <td>{{ o.ilk_zaman }}</td>
      <td>{{ o.toplam }}</td>
      <td>{{ o.basarili }}</td>
      <td>{{ o.hatali }}</td>
      <td><a href="/durum/{{ o.gonderim_id }}">Detay</a></td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 7: Write static/stil.css**

```css
:root { font-family: system-ui, sans-serif; }
body { margin: 0; background: #f5f5f7; color: #1a1a1a; }
.ust-cubuk { display: flex; align-items: center; gap: 16px; padding: 12px 20px; background: #fff; border-bottom: 1px solid #ddd; }
.ust-cubuk .marka { font-weight: 700; text-decoration: none; color: inherit; }
.ust-cubuk nav { display: flex; gap: 12px; flex: 1; }
.ust-cubuk nav a { text-decoration: none; color: #555; padding: 4px 8px; border-radius: 6px; }
.ust-cubuk nav a.aktif { background: #eef; color: #226; }
main { padding: 20px; max-width: 720px; margin: 0 auto; }
form label { display: block; margin-bottom: 12px; font-weight: 600; }
textarea, input[type=text], input[type=password], input[type=number], input[type=file] { width: 100%; box-sizing: border-box; padding: 8px; font-family: inherit; font-size: 1rem; margin-top: 4px; }
button { padding: 8px 16px; border: none; border-radius: 6px; background: #226; color: #fff; cursor: pointer; }
.hata { color: #b00020; font-weight: 600; }
table { width: 100%; border-collapse: collapse; margin-top: 16px; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #ddd; }
tr.hata td { color: #b00020; }
.giris-sarici { display: flex; justify-content: center; align-items: center; min-height: 100vh; }
.giris-form { background: #fff; padding: 32px; border-radius: 10px; box-shadow: 0 2px 12px rgba(0,0,0,.08); width: 280px; }
```
Write and `pscp` all of Steps 2–7 to their respective paths under `/home/ata/farabi/smssistemi/`.

- [ ] **Step 8: Manual smoke test (app not yet running as a service)**

```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi/smssistemi && timeout 5 venv/bin/uvicorn app:app --host 127.0.0.1 --port 8020 & sleep 2 && curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:8020/giris; wait"
```
Expected: `HTTP:200` (login page loads without a stack trace).

- [ ] **Step 9: Commit**

```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi && git add smssistemi/app.py smssistemi/templates smssistemi/static && git -c user.email='atakanunver1@gmail.com' -c user.name='Atakan' commit -m 'smssistemi: app.py + web arayuzu'"
```

---

### Task 8: systemd service

**Files:**
- Create (remote, root-owned): `/etc/systemd/system/farabi-smssistemi.service`

**Interfaces:**
- Produces: `smssistemi` reachable at `http://farabi.local:8020/` and `http://192.168.23.252:8020/`, consumed by Task 9's dashboard link and Task 10's end-to-end test.

- [ ] **Step 1: Write and install the unit file**

```ini
[Unit]
Description=SMS Sistemi — bagimsiz web modulu (smssistemi)
After=network.target

[Service]
Type=simple
User=ata
Group=ata
WorkingDirectory=/home/ata/farabi/smssistemi
ExecStart=/home/ata/farabi/smssistemi/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8020
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
Write locally, then install (Farabi's `ata` user has passwordless sudo):
```bash
pscp -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" <local-tmp-path> ata@farabi.local:/tmp/farabi-smssistemi.service
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "sudo -S mv /tmp/farabi-smssistemi.service /etc/systemd/system/farabi-smssistemi.service <<< '1' && sudo -S systemctl daemon-reload <<< '1' && sudo -S systemctl enable --now farabi-smssistemi <<< '1'"
```

- [ ] **Step 2: Verify service is running**

Run: `plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "systemctl is-active farabi-smssistemi && curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:8020/giris"`
Expected: `active` then `HTTP:200`.

- [ ] **Step 3: Confirm the shared login password is set**

Run: `plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "test -f /home/ata/farabi/smssistemi/config/gizli.json && echo VAR"`
Expected: `VAR` — `config/gizli.json` was already written in Task 5 Step 5. If missing, go back and complete that step (it needs the password chosen with the user) before continuing.

---

### Task 9: Dashboard nav link

**Files:**
- Modify: `/home/ata/farabi/tahtayoklama/dashboard/templates/taban.html`

**Interfaces:** none (pure template edit, no code coupling — satisfies the spec's "dashboard only gets a link" requirement).

- [ ] **Step 1: Download the current file locally**

```bash
pscp -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local:/home/ata/farabi/tahtayoklama/dashboard/templates/taban.html C:\Users\exa\Desktop\taban.html
```

- [ ] **Step 2: Insert the new nav group**

Using the Edit tool on the local `C:\Users\exa\Desktop\taban.html`, find this exact existing block (the "Zil Servisi" group):
```html
      <div class="kenar-grup">
        <span class="kenar-baslik">Zil Servisi</span>
        <a href="http://admin:midnight@192.168.23.230:8090/" target="_blank" rel="noopener">
          <svg class="ikon"><use href="#ik-zil"/></svg> Zil Sistemi <svg class="ikon ikon-kucuk ikon-disa"><use href="#ik-ok-sag"/></svg>
        </a>
      </div>
```
Replace it with the same block plus a new group right after it:
```html
      <div class="kenar-grup">
        <span class="kenar-baslik">Zil Servisi</span>
        <a href="http://admin:midnight@192.168.23.230:8090/" target="_blank" rel="noopener">
          <svg class="ikon"><use href="#ik-zil"/></svg> Zil Sistemi <svg class="ikon ikon-kucuk ikon-disa"><use href="#ik-ok-sag"/></svg>
        </a>
      </div>
      <div class="kenar-grup">
        <span class="kenar-baslik">SMS Sistemi</span>
        <a href="http://farabi.local:8020/" target="_blank" rel="noopener">
          <svg class="ikon"><use href="#ik-zil"/></svg> SMS Sistemi <svg class="ikon ikon-kucuk ikon-disa"><use href="#ik-ok-sag"/></svg>
        </a>
      </div>
```

- [ ] **Step 3: Upload it back**

```bash
pscp -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" C:\Users\exa\Desktop\taban.html ata@farabi.local:/home/ata/farabi/tahtayoklama/dashboard/templates/taban.html
```
No service restart needed — `Jinja2Templates` re-reads template files from disk per request.

- [ ] **Step 4: Verify in the dashboard**

Run: `plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "curl -s http://127.0.0.1:8010/giris | grep -c 'SMS Sistemi'"`
Expected: `0` (the nav only renders on authenticated pages, not `/giris` — this just confirms the page still loads without a template error; a non-crashing `200` is what matters). Better check: `curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:8010/giris` → `HTTP:200`.

- [ ] **Step 5: Commit**

```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi && git add tahtayoklama/dashboard/templates/taban.html && git -c user.email='atakanunver1@gmail.com' -c user.name='Atakan' commit -m 'dashboard: SMS Sistemi nav linki eklendi'"
```

---

### Task 10: End-to-end test + decision log

**Files:**
- Modify: `/home/ata/farabi/DECISIONS.md`

**Interfaces:** none (verification + documentation task, closes out the plan).

- [ ] **Step 1: Send a real test SMS**

Log into `http://farabi.local:8020/` (or `http://192.168.23.252:8020/`) with the shared password from Task 8 Step 3, submit the form with `numaralar` = `Atakan,5059399303` and a short test `mesaj` (e.g. `Test mesaji {isim} - smssistemi calisiyor`).

- [ ] **Step 2: Verify delivery end-to-end**

Confirm three things: (a) the `/durum/<gonderim_id>` page shows `gonderildi` for the row, (b) the phone `5059399303` actually receives the SMS, (c) `venv/bin/python -c "import db; conn = db.baglanti(); print(db.gonderim_ozetleri(conn))"` (run over SSH from `/home/ata/farabi/smssistemi`) lists the batch with `basarili: 1`.

- [ ] **Step 3: Add the DECISIONS.md entry**

Append to `/home/ata/farabi/DECISIONS.md`:
```
## 2026-09-19 - SMS Sistemi: bağımsız web modülü + Müdür PC ağ köprüsü
- Müdür PC masaüstündeki Tkinter toplu-SMS aracı, Farabi'de
  tahtayoklama/dashboard'dan tamamen bağımsız yeni bir proje
  (smssistemi, port 8020) olarak web'e taşındı. Dashboard'a sadece bir
  nav linki eklendi, kod paylaşımı yok.
- Farabi modeme (192.168.8.1, Müdür PC'nin ayrı Wi-Fi ağı) doğrudan
  ulaşamadığından (doğrulandı: curl/ping başarısız), Müdür PC'de
  `netsh interface portproxy` ile TCP köprüsü kuruldu
  (192.168.23.243:18080 → 192.168.8.1:80), Farabi IP'sine
  (192.168.23.252) kısıtlı bir firewall kuralıyla korunuyor. Müdür
  PC'de bu özellik için hiç uygulama kodu çalışmıyor — sadece OS
  seviyesinde yönlendirme, WifiHttpProxy'den daha basit bir desen.
```
Append via SSH: `plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cat >> /home/ata/farabi/DECISIONS.md"` with the text piped in, then commit:
```bash
plink -ssh -pw 1 -hostkey "SHA256:SoyR9Hmyyat06vv9wg144GIbcu1iiVOJCYz64G7oTCE" ata@farabi.local "cd /home/ata/farabi && git add DECISIONS.md && git -c user.email='atakanunver1@gmail.com' -c user.name='Atakan' commit -m 'DECISIONS: smssistemi mimari karari'"
```
