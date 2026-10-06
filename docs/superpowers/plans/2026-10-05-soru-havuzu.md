# Soru Havuzu (soru_havuzu) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ders kitapları, kazanım testleri ve YKS çıkmış sorularından gece Ollama (qwen3.8:27b) ile binlerce soru üretip ayrı bir PostgreSQL veritabanında (`soru_havuzu`) saklamak, her soruyu AGY ile denetlemek ve Sınıf Arenası + HexaFetih'in soruları bu havuzdan anında çekmesini sağlamak.

**Architecture:** Farabi'de yeni bir paket `/home/ata/farabi/soruhavuzu/` (server venv'ini kullanır: psycopg2, pymupdf, httpx, pytest hazır). Kaynak birimleri (`kaynak_birim`) bir kez kataloglanır; üretici systemd timer'ıyla 17:15'te başlar, her birimden önce ders saati kontrolü yapar (hafta içi 07:30–17:05 arası durur, hafta sonu serbest), kaldığı yerden devam eder. Soruları YALNIZCA yerel Ollama üretir. Denetim tek seferliktir: bütün kaynak birimleri işlenince üretici AGY denetimini bir kez başlatır ve AGY tüm `uretildi` soruları tek çalıştırmada (içeride 100'lük paketlerle) kontrol eder (bulut, GPU kullanmaz). Elle de başlatılabilir: `calistir denetle`. Kopyalar bilgehan'daki bge-m3 gömme servisiyle elenir. Arena/Hexa havuzu doğrudan okur (psycopg2), havuz boşsa mevcut davranışa düşer.

**Tech Stack:** Python 3, PostgreSQL 18 (jsonb), psycopg2, PyMuPDF, httpx, Ollama `/api/chat` (`think:false`, `format:"json"`), Antigravity CLI `agy`, pytest, systemd timer.

**Spec:** Bu oturumdaki kullanıcı kararları (2026-10-05): üretim = Farabi 27B gece; üretim = yalnızca yerel Ollama; denetim = üretim bitince AGY tüm havuzu TEK SEFERDE kontrol eder (zamanlayıcı yok); kaynaklar = 30 kitap (`chunk_egitim`) + 209 kazanım testi (`/mnt/farabi-data/farabi/kazanim_test`) + YKS çıkmış (`/mnt/farabi-data/farabi/yks`); oyun entegrasyonu bu planda.

## Global Constraints

- Ollama'ya giden her çağrı: `"model": "qwen3.8:27b"`, `"think": false`, `"stream": false`. Ollama servisi restart EDİLMEZ, ayarı değiştirilmez.
- GPU üretimi yalnızca ders saati DIŞINDA: hafta içi TR 07:30–17:05 arası üretim yapılmaz (`Europe/Istanbul`). Farabi saati UTC'dir.
- Yeni veritabanı adı tam olarak `soru_havuzu`, sahibi `farabi` rolü, bağlantı `host=127.0.0.1 user=farabi` (farabi-api ile aynı desen).
- Sorular yalnızca verilen kaynak metne dayanır; kaynak etiketi biçimi `"<Ders> <Sınıf>, s. <sayfa>"` (kitap) / `"Kazanım Testi: <dosya>, s. <sayfa>"` / `"YKS <dosya>, s. <sayfa>"`.
- Ders anahtarları (arena `KAPSAM_ESLEME` değerleriyle aynı): `matematik, fizik, kimya, biyoloji, edebiyat, tarih, cografya, din, felsefe, ingilizce, almanca`.
- Şekil/grafik/tablo gerektiren sorular (metinde "şekil", "grafik", "tabloda", "görsel" geçen) havuza alınmaz.
- Kod stili: mevcut Farabi deseni — Türkçe adlar, kısa docstring, `# noqa: BLE001` ile gerekçeli geniş except.
- Testler: `cd /home/ata/farabi && server/venv/bin/python -m pytest -q soruhavuzu/tests`. Test DB'si `soru_havuzu_test` (gerçek DB'ye test yazılmaz).

## Dosya Yapısı

| Dosya | Sorumluluk |
|---|---|
| `soruhavuzu/sema.sql` | Tablolar + indeksler (idempotent) |
| `soruhavuzu/vt.py` | Bağlantı, şema kurulumu, birim/soru yazma-okuma |
| `soruhavuzu/dersler.py` | Ders adı → ders anahtarı, dosya adından sınıf/ders çözme |
| `soruhavuzu/kaynaklar.py` | Kataloglama: kitap chunk grupları + PDF sayfa grupları → `kaynak_birim` |
| `soruhavuzu/uretici.py` | Ollama istemi, JSON ayrıştırma, soru doğrulama |
| `soruhavuzu/tekrar.py` | bilgehan bge-m3 ile kopya eleme |
| `soruhavuzu/denetci.py` | AGY paket denetimi |
| `soruhavuzu/zaman.py` | Ders saati penceresi |
| `soruhavuzu/calistir.py` | CLI: `kur`, `katalog`, `uret`, `denetle`, `durum` |
| `soruhavuzu/systemd/*.service,*.timer` | Gece üretimi + denetim zamanlaması |
| `arenasinif/havuz.py` | Havuzdan Jeopardy seti / Hexa petek soruları |
| `arenasinif/server.py`, `arenasinif/fetih_motoru.py` | Havuz-öncelikli soru akışı + Hexa sınıf parametresi |

---

### Task 1: Veritabanı ve şema

**Files:**
- Create: `soruhavuzu/__init__.py` (boş), `soruhavuzu/sema.sql`, `soruhavuzu/vt.py`, `soruhavuzu/tests/__init__.py` (boş), `soruhavuzu/tests/conftest.py`, `soruhavuzu/tests/test_vt.py`

**Interfaces:**
- Produces: `vt.baglan(dbname="soru_havuzu") -> psycopg2 connection`; `vt.sema_kur(conn) -> None`; `vt.birim_ekle(conn, tur, anahtar, ders, sinif, etiket, metin) -> int | None` (zaten varsa None); `vt.siradaki_birim(conn) -> dict | None`; `vt.birim_isaretle(conn, birim_id, durum, hata=None)`; `vt.soru_ekle(conn, birim_id, s: dict) -> int`; `vt.denetlenecekler(conn, limit) -> list[dict]`; `vt.denetim_yaz(conn, soru_id, durum, not_)`.

- [ ] **Step 1: Veritabanını oluştur (bir kez, elle)**

```bash
sudo -u postgres psql -c "CREATE DATABASE soru_havuzu OWNER farabi"
sudo -u postgres psql -c "CREATE DATABASE soru_havuzu_test OWNER farabi"
psql -h 127.0.0.1 -U farabi -d soru_havuzu -c "select 1"
```
Expected: son komut `1` döner (farabi rolü 127.0.0.1'den şifresiz bağlanabiliyor — farabi-api ile aynı). Bağlanamazsa `pg_hba.conf`'u DEĞİŞTİRME, kullanıcıya sor.

- [ ] **Step 2: `sema.sql` yaz**

```sql
CREATE TABLE IF NOT EXISTS kaynak_birim (
    id          serial PRIMARY KEY,
    tur         text NOT NULL CHECK (tur IN ('kitap', 'kazanim', 'yks')),
    anahtar     text NOT NULL UNIQUE,          -- örn. "kitap:36:12-14", "kazanim:12sinif_fizik_8.pdf:3"
    ders        text,                           -- ders anahtarı; yks'de NULL (soru başına gelir)
    sinif       smallint NOT NULL,
    etiket      text NOT NULL,                  -- kaynak etiketi önü, örn. "Matematik 12, s. 12"
    metin       text NOT NULL,
    durum       text NOT NULL DEFAULT 'bekliyor' CHECK (durum IN ('bekliyor', 'islendi', 'hata')),
    hata        text,
    islendi_at  timestamptz
);
CREATE TABLE IF NOT EXISTS soru (
    id               bigserial PRIMARY KEY,
    birim_id         int NOT NULL REFERENCES kaynak_birim(id),
    ders             text NOT NULL,
    sinif            smallint NOT NULL,
    konu             text NOT NULL,
    soru             text NOT NULL,
    kisa_cevap       text NOT NULL,
    secenekler       jsonb NOT NULL,            -- 4 metin
    dogru_index      smallint NOT NULL CHECK (dogru_index BETWEEN 0 AND 3),
    zorluk           smallint NOT NULL CHECK (zorluk BETWEEN 1 AND 4),
    kaynak           text NOT NULL,
    durum            text NOT NULL DEFAULT 'uretildi'
                     CHECK (durum IN ('uretildi', 'onayli', 'red', 'kopya')),
    denetim_notu     text,
    olusturma        timestamptz NOT NULL DEFAULT now(),
    denetim_at       timestamptz,
    kullanim_sayisi  int NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS soru_oyun_idx ON soru (ders, sinif, durum, zorluk);
CREATE INDEX IF NOT EXISTS birim_durum_idx ON kaynak_birim (durum, id);
```

- [ ] **Step 3: Failing test yaz** — `tests/conftest.py`:

```python
import pytest

from soruhavuzu import vt


@pytest.fixture
def conn():
    c = vt.baglan("soru_havuzu_test")
    vt.sema_kur(c)
    with c.cursor() as cur:
        cur.execute("TRUNCATE soru, kaynak_birim RESTART IDENTITY CASCADE")
    c.commit()
    yield c
    c.close()


ORNEK_SORU = {"ders": "matematik", "sinif": 12, "konu": "Logaritma", "soru": "log2(8) kaçtır?",
              "kisa_cevap": "3", "secenekler": ["2", "3", "4", "8"], "dogru_index": 1,
              "zorluk": 1, "kaynak": "Matematik 12, s. 40"}
```

`tests/test_vt.py`:

```python
from soruhavuzu import vt
from soruhavuzu.tests.conftest import ORNEK_SORU


def test_birim_bir_kez_eklenir(conn):
    a = vt.birim_ekle(conn, "kitap", "kitap:36:1-3", "matematik", 12, "Matematik 12, s. 1", "metin")
    b = vt.birim_ekle(conn, "kitap", "kitap:36:1-3", "matematik", 12, "Matematik 12, s. 1", "metin")
    assert a is not None and b is None


def test_siradaki_birim_ve_isaretleme(conn):
    bid = vt.birim_ekle(conn, "kitap", "k:1", "matematik", 12, "E", "m")
    assert vt.siradaki_birim(conn)["id"] == bid
    vt.birim_isaretle(conn, bid, "islendi")
    assert vt.siradaki_birim(conn) is None


def test_soru_ekle_ve_denetim(conn):
    bid = vt.birim_ekle(conn, "kitap", "k:1", "matematik", 12, "E", "kaynak metin")
    sid = vt.soru_ekle(conn, bid, ORNEK_SORU)
    paket = vt.denetlenecekler(conn, 20)
    assert [p["id"] for p in paket] == [sid] and paket[0]["birim_metin"] == "kaynak metin"
    vt.denetim_yaz(conn, sid, "onayli", "doğru")
    assert vt.denetlenecekler(conn, 20) == []
```

- [ ] **Step 4: Çalıştır, FAIL gör** — `server/venv/bin/python -m pytest -q soruhavuzu/tests/test_vt.py` → `ImportError` / `AttributeError`.

- [ ] **Step 5: `vt.py` yaz**

```python
"""soruhavuzu/vt.py — soru_havuzu PostgreSQL erişimi (farabi-api ile aynı bağlantı deseni)."""

import json
from pathlib import Path

import psycopg2
import psycopg2.extras

SEMA = Path(__file__).with_name("sema.sql")


def baglan(dbname: str = "soru_havuzu"):
    return psycopg2.connect(host="127.0.0.1", dbname=dbname, user="farabi")


def sema_kur(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SEMA.read_text(encoding="utf-8"))
    conn.commit()


def birim_ekle(conn, tur, anahtar, ders, sinif, etiket, metin) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin) "
            "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (anahtar) DO NOTHING RETURNING id",
            (tur, anahtar, ders, sinif, etiket, metin))
        satir = cur.fetchone()
    conn.commit()
    return satir[0] if satir else None


def siradaki_birim(conn) -> dict | None:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM kaynak_birim WHERE durum = 'bekliyor' ORDER BY id LIMIT 1")
        return cur.fetchone()


def birim_isaretle(conn, birim_id, durum, hata=None) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE kaynak_birim SET durum=%s, hata=%s, islendi_at=now() WHERE id=%s",
                    (durum, hata, birim_id))
    conn.commit()


def soru_ekle(conn, birim_id, s: dict) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO soru (birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler, "
            "dogru_index, zorluk, kaynak) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (birim_id, s["ders"], s["sinif"], s["konu"], s["soru"], s["kisa_cevap"],
             json.dumps(s["secenekler"], ensure_ascii=False), s["dogru_index"], s["zorluk"], s["kaynak"]))
        sid = cur.fetchone()[0]
    conn.commit()
    return sid


def denetlenecekler(conn, limit: int) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT s.*, b.metin AS birim_metin FROM soru s JOIN kaynak_birim b ON b.id = s.birim_id "
            "WHERE s.durum = 'uretildi' ORDER BY s.birim_id, s.id LIMIT %s", (limit,))
        return list(cur.fetchall())


def denetim_yaz(conn, soru_id, durum, not_) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE soru SET durum=%s, denetim_notu=%s, denetim_at=now() WHERE id=%s",
                    (durum, not_, soru_id))
    conn.commit()
```

- [ ] **Step 6: PASS gör** — aynı komut → `3 passed`.
- [ ] **Step 7: Gerçek DB'ye şemayı kur** — `server/venv/bin/python -c "from soruhavuzu import vt; vt.sema_kur(vt.baglan())"`.
- [ ] **Step 8: Commit** — `git add soruhavuzu && git commit -m "soruhavuzu: soru_havuzu veritabanı şeması ve erişim katmanı"`

---

### Task 2: Ders/sınıf çözümleme ve kaynak kataloğu

**Files:**
- Create: `soruhavuzu/dersler.py`, `soruhavuzu/kaynaklar.py`, `soruhavuzu/tests/test_kaynaklar.py`

**Interfaces:**
- Consumes: `vt.birim_ekle`
- Produces: `dersler.ders_anahtari(ad: str) -> str | None`; `dersler.dosyadan_cozumle(dosya_adi: str) -> tuple[int | None, str | None]` (sınıf, ders); `kaynaklar.kitap_gruplari(farabi_conn, grup_karakter=1800) -> Iterator[dict]`; `kaynaklar.pdf_gruplari(yol: Path, tur: str) -> Iterator[dict]`; `kaynaklar.katalogla(havuz_conn, farabi_conn, kazanim_dizin, yks_dizin) -> dict[str, int]` (tur → eklenen sayısı). Grup dict anahtarları: `tur, anahtar, ders, sinif, etiket, metin`.

- [ ] **Step 1: Failing test yaz** — `tests/test_kaynaklar.py`:

```python
from soruhavuzu import dersler, kaynaklar


def test_ders_anahtari():
    assert dersler.ders_anahtari("Türk Dili ve Edebiyatı") == "edebiyat"
    assert dersler.ders_anahtari("Temel Matematik") == "matematik"
    assert dersler.ders_anahtari("İnkılap Tarihi ve Atatürkçülük") == "tarih"
    assert dersler.ders_anahtari("Din Kültürü ve Ahlak Bilgisi") == "din"
    assert dersler.ders_anahtari("Beden Eğitimi") is None


def test_dosyadan_cozumle():
    assert dersler.dosyadan_cozumle("12sinif_fizik_8.pdf") == (12, "fizik")
    assert dersler.dosyadan_cozumle("12.sınıf.fizik.00_Cevap_Anahtari.pdf") == (12, "fizik")
    assert dersler.dosyadan_cozumle("12.edebiyat.41_Cevap_Anahtari.pdf") == (12, "edebiyat")
    assert dersler.dosyadan_cozumle("202582694327111-biyoloji.pdf") == (None, "biyoloji")
    assert dersler.dosyadan_cozumle("13.pdf") == (None, None)


class SahteImlec:
    def __init__(self, satirlar): self.satirlar = satirlar
    def execute(self, *a): pass
    def fetchall(self): return self.satirlar
    def __enter__(self): return self
    def __exit__(self, *a): pass


class SahteBaglanti:
    def __init__(self, satirlar): self.satirlar = satirlar
    def cursor(self, **k): return SahteImlec(self.satirlar)


def test_kitap_gruplari_sayfa_araligi_ve_sinir():
    # (kitap_id, sinif, ders, sayfa_no, metin)
    satirlar = [(36, 12, "Matematik", 10, "a" * 1000), (36, 12, "Matematik", 11, "b" * 1000),
                (36, 12, "Matematik", 12, "c" * 500), (5, 10, "Biyoloji", 3, "d" * 300)]
    g = list(kaynaklar.kitap_gruplari(SahteBaglanti(satirlar), grup_karakter=1800))
    assert [x["anahtar"] for x in g] == ["kitap:36:10-11", "kitap:36:12-12", "kitap:5:3-3"]
    assert g[0]["etiket"] == "Matematik 12, s. 10" and g[0]["ders"] == "matematik"
    assert g[2]["sinif"] == 10
```

- [ ] **Step 2: FAIL gör** — `pytest -q soruhavuzu/tests/test_kaynaklar.py`.

- [ ] **Step 3: `dersler.py` yaz**

```python
"""soruhavuzu/dersler.py — ders adı/dosya adı → (sınıf, ders anahtarı)."""

import re

_ESLEME = [  # (anahtar kelime, ders anahtarı) — sıra önemli: "temel matematik" → matematik
    ("edebiyat", "edebiyat"), ("matematik", "matematik"), ("fizik", "fizik"), ("kimya", "kimya"),
    ("biyoloji", "biyoloji"), ("inkılap", "tarih"), ("tarih", "tarih"), ("coğrafya", "cografya"),
    ("cografya", "cografya"), ("din", "din"), ("dkab", "din"), ("felsefe", "felsefe"),
    ("ingilizce", "ingilizce"), ("waymark", "ingilizce"), ("almanca", "almanca"),
]


def _kucuk(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def ders_anahtari(ad: str) -> str | None:
    k = _kucuk(ad)
    for kelime, anahtar in _ESLEME:
        if kelime in k:
            return anahtar
    return None


def dosyadan_cozumle(dosya_adi: str) -> tuple[int | None, str | None]:
    k = _kucuk(dosya_adi)
    m = re.match(r"^(9|10|11|12)(?=[^0-9])", k)
    sinif = int(m.group(1)) if m else None
    return sinif, ders_anahtari(k)
```

- [ ] **Step 4: `kaynaklar.py` yaz**

```python
"""soruhavuzu/kaynaklar.py — kaynak birimlerini (soru üretilecek metin parçaları) kataloglar.

Kitaplar: farabi DB'sindeki chunk_egitim, ardışık sayfalar ~grup_karakter'e kadar birleştirilir.
PDF'ler (kazanım testi / YKS): sayfa başına bir birim (PyMuPDF metni)."""

from collections.abc import Iterator
from pathlib import Path

import fitz

from soruhavuzu import dersler, vt

PDF_AZAMI_KARAKTER = 6000


def kitap_gruplari(farabi_conn, grup_karakter: int = 1800) -> Iterator[dict]:
    with farabi_conn.cursor() as cur:
        cur.execute("SELECT k.id, k.sinif, k.ders, c.sayfa_no, c.metin FROM chunk_egitim c "
                    "JOIN kitap k ON k.id = c.kitap_id ORDER BY k.id, c.sayfa_no, c.id")
        satirlar = cur.fetchall()
    grup = None
    for kid, sinif, ders, sayfa, metin in satirlar:
        if grup and (grup["kid"] != kid or len(grup["metin"]) + len(metin) > grup_karakter):
            yield _bitir(grup)
            grup = None
        if grup is None:
            grup = {"kid": kid, "sinif": sinif, "ders_ad": ders, "ilk": sayfa, "son": sayfa, "metin": ""}
        grup["son"] = sayfa
        grup["metin"] += ("\n" if grup["metin"] else "") + metin
    if grup:
        yield _bitir(grup)


def _bitir(g: dict) -> dict:
    return {"tur": "kitap", "anahtar": f"kitap:{g['kid']}:{g['ilk']}-{g['son']}",
            "ders": dersler.ders_anahtari(g["ders_ad"]), "sinif": g["sinif"],
            "etiket": f"{g['ders_ad']} {g['sinif']}, s. {g['ilk']}", "metin": g["metin"]}


def pdf_gruplari(yol: Path, tur: str) -> Iterator[dict]:
    sinif, ders = dersler.dosyadan_cozumle(yol.name)
    if tur == "yks":
        sinif, ders = 12, None  # YKS: ders soru başına modelden gelir
    with fitz.open(yol) as belge:
        for i, sayfa in enumerate(belge, start=1):
            metin = sayfa.get_text().strip()
            if len(metin) < 200:
                continue
            onek = "Kazanım Testi" if tur == "kazanim" else "YKS"
            yield {"tur": tur, "anahtar": f"{tur}:{yol.name}:{i}", "ders": ders, "sinif": sinif,
                   "etiket": f"{onek}: {yol.stem}, s. {i}", "metin": metin[:PDF_AZAMI_KARAKTER]}


def katalogla(havuz_conn, farabi_conn, kazanim_dizin: Path, yks_dizin: Path) -> dict[str, int]:
    sayac = {"kitap": 0, "kazanim": 0, "yks": 0, "atlanan_pdf": 0}
    gruplar = list(kitap_gruplari(farabi_conn))
    for tur, dizin in (("kazanim", kazanim_dizin), ("yks", yks_dizin)):
        for yol in sorted(dizin.glob("*.pdf")):
            try:
                gruplar.extend(pdf_gruplari(yol, tur))
            except Exception as e:  # noqa: BLE001 — bozuk PDF kataloğu durdurmasın
                print(f"[katalog] {yol.name} okunamadı: {type(e).__name__}: {e}")
                sayac["atlanan_pdf"] += 1
    for g in gruplar:
        if g["sinif"] is None or (g["tur"] != "yks" and g["ders"] is None):
            continue  # sınıfı/dersi çözülemeyen kazanım PDF'i — `durum` raporunda listelenir
        if vt.birim_ekle(havuz_conn, g["tur"], g["anahtar"], g["ders"], g["sinif"], g["etiket"], g["metin"]):
            sayac[g["tur"]] += 1
    return sayac
```

- [ ] **Step 5: PASS gör** — `pytest -q soruhavuzu/tests/test_kaynaklar.py` → `3 passed`.
- [ ] **Step 6: Commit** — `git commit -m "soruhavuzu: ders çözümleme ve kaynak kataloğu"`

---

### Task 3: Ollama soru üretici

**Files:**
- Create: `soruhavuzu/uretici.py`, `soruhavuzu/tests/test_uretici.py`

**Interfaces:**
- Produces: `uretici.istem(birim: dict) -> list[dict]` (Ollama messages); `uretici.ayristir(ham: str, birim: dict) -> list[dict]` (doğrulanmış, `vt.soru_ekle` biçiminde); `uretici.uret(birim: dict, ollama_url="http://127.0.0.1:11434", zaman_asimi=180) -> list[dict]`.

- [ ] **Step 1: Failing test yaz**

```python
import json

from soruhavuzu import uretici

BIRIM = {"tur": "kitap", "ders": "matematik", "sinif": 12, "etiket": "Matematik 12, s. 40",
         "metin": "Logaritma üstel fonksiyonun tersidir..."}
IYI = {"konu": "Logaritma", "soru": "log2(8) kaçtır?", "kisa_cevap": "3",
       "secenekler": ["2", "3", "4", "8"], "dogru_index": 1, "zorluk": 1, "sayfa": 41}


def test_gecerli_soru_alinir_ve_kaynak_sayfasi_yazilir():
    s = uretici.ayristir(json.dumps({"sorular": [IYI]}), BIRIM)
    assert len(s) == 1
    assert s[0]["ders"] == "matematik" and s[0]["sinif"] == 12
    assert s[0]["kaynak"] == "Matematik 12, s. 41"


def test_bozuk_ve_sekilli_sorular_elenir():
    kotu = [{**IYI, "dogru_index": 7}, {**IYI, "secenekler": ["a", "b"]},
            {**IYI, "soru": "Şekildeki üçgenin alanı?"}, {**IYI, "soru": ""}]
    assert uretici.ayristir(json.dumps({"sorular": kotu}), BIRIM) == []
    assert uretici.ayristir("json değil", BIRIM) == []


def test_yks_dersi_sorudan_gelir_bilinmeyen_elenir():
    yks = {**BIRIM, "tur": "yks", "ders": None, "etiket": "YKS: AYT_SAY, s. 3"}
    s = uretici.ayristir(json.dumps({"sorular": [{**IYI, "ders": "fizik"}, {**IYI, "ders": "beden"}]}), yks)
    assert [x["ders"] for x in s] == ["fizik"]
```

- [ ] **Step 2: FAIL gör.**

- [ ] **Step 3: `uretici.py` yaz**

```python
"""soruhavuzu/uretici.py — bir kaynak biriminden Ollama (qwen3.8:27b) ile çoktan seçmeli sorular."""

import json
import re

import httpx

MODEL = "qwen3.8:27b"
DERSLER = {"matematik", "fizik", "kimya", "biyoloji", "edebiyat", "tarih", "cografya",
           "din", "felsefe", "ingilizce", "almanca"}
SEKIL = re.compile(r"şekil|grafik|tablo(da|daki|ya)|görsel", re.IGNORECASE)

SISTEM = (
    "Sen MEB lise öğretmenisin ve sınıf içi yarışma oyunları için soru hazırlıyorsun. "
    "YALNIZCA verilen kaynak metne dayan; metinde olmayan bilgiyi soru veya cevap yapma. "
    "Şekil, grafik, tablo veya görsel gerektiren soru yazma. Her soru tek başına anlaşılır olsun. "
    "4 şıktan yalnızca biri doğru olsun, çeldiriciler makul olsun. Kısa cevap 1-6 kelime. "
    "Zorluk 1 (hatırlama) ile 4 (çok adımlı akıl yürütme) arası. "
    "Yalnızca JSON döndür: {\"sorular\": [...]}.")


def istem(birim: dict) -> list[dict]:
    if birim["tur"] == "kitap":
        gorev = ("Bu ders kitabı metninden farklı alt konulara yayılan 4 soru üret "
                 "(zorluk 1, 2, 3, 4 birer tane).")
    else:
        gorev = ("Bu sayfa hazır test sorusu içeriyor. Cevap anahtarı/çözümü sayfada varsa ya da "
                 "doğru cevap metinden kesin çıkıyorsa her soruyu AYNI içerikle yaz (en fazla 6); "
                 "cevabı kesin değilse o soruyu ATLA.")
    ders_satiri = (f"Ders: {birim['ders']}" if birim.get("ders")
                   else f"Her soruya 'ders' alanı ekle; şunlardan biri: {', '.join(sorted(DERSLER))}")
    sema = ('{"sorular": [{"konu": "kısa konu adı", "soru": "...", "kisa_cevap": "...", '
            '"secenekler": ["A", "B", "C", "D"], "dogru_index": 0, "zorluk": 1, "sayfa": 0'
            + (', "ders": "fizik"' if not birim.get("ders") else "") + "}]}")
    kullanici = (f"{ders_satiri}\nSınıf: {birim['sinif']}\nKaynak: {birim['etiket']}\n"
                 f"Görev: {gorev}\n'sayfa' alanına sorunun dayandığı sayfa numarasını yaz.\n"
                 f"Biçim: {sema}\n\nKAYNAK METİN:\n{birim['metin']}")
    return [{"role": "system", "content": SISTEM}, {"role": "user", "content": kullanici}]


def _gecerli(s: dict) -> bool:
    try:
        return (isinstance(s.get("soru"), str) and s["soru"].strip()
                and isinstance(s.get("kisa_cevap"), str) and s["kisa_cevap"].strip()
                and isinstance(s.get("secenekler"), list) and len(s["secenekler"]) == 4
                and all(isinstance(x, str) and x.strip() for x in s["secenekler"])
                and len({x.strip() for x in s["secenekler"]}) == 4
                and int(s.get("dogru_index")) in range(4)
                and int(s.get("zorluk")) in range(1, 5)
                and not SEKIL.search(s["soru"]))
    except (TypeError, ValueError):
        return False


def ayristir(ham: str, birim: dict) -> list[dict]:
    try:
        veri = json.loads(ham)
    except (json.JSONDecodeError, TypeError):
        return []
    sorular = veri.get("sorular") if isinstance(veri, dict) else None
    cikti = []
    for s in sorular if isinstance(sorular, list) else []:
        if not isinstance(s, dict) or not _gecerli(s):
            continue
        ders = birim.get("ders") or s.get("ders")
        if ders not in DERSLER:
            continue
        etiket = birim["etiket"]
        sayfa = s.get("sayfa")
        if birim["tur"] == "kitap" and isinstance(sayfa, int) and sayfa > 0 and ", s. " in etiket:
            etiket = etiket.rsplit(", s. ", 1)[0] + f", s. {sayfa}"
        cikti.append({"ders": ders, "sinif": birim["sinif"],
                      "konu": str(s.get("konu") or "Genel").strip()[:80],
                      "soru": s["soru"].strip(), "kisa_cevap": s["kisa_cevap"].strip(),
                      "secenekler": [x.strip() for x in s["secenekler"]],
                      "dogru_index": int(s["dogru_index"]), "zorluk": int(s["zorluk"]),
                      "kaynak": etiket})
    return cikti


def uret(birim: dict, ollama_url: str = "http://127.0.0.1:11434", zaman_asimi: float = 180) -> list[dict]:
    govde = {"model": MODEL, "messages": istem(birim), "stream": False, "think": False,
             "format": "json", "options": {"temperature": 0.4}}
    with httpx.Client(timeout=zaman_asimi, trust_env=False) as c:
        r = c.post(f"{ollama_url}/api/chat", json=govde)
        r.raise_for_status()
        return ayristir(r.json().get("message", {}).get("content", ""), birim)
```

Not: kitap birimlerinde `sayfa` modelden gelir ve `etiket`teki ilk sayfanın yerine yazılır; model uydurursa AGY denetimi kaynak metinle karşılaştırır.

- [ ] **Step 4: PASS gör** — `3 passed`.
- [ ] **Step 5: Duman testi (YALNIZCA 17:05 TR sonrası)** — `server/venv/bin/python -c "from soruhavuzu import uretici; import json; print(json.dumps(uretici.uret({'tur':'kitap','ders':'biyoloji','sinif':10,'etiket':'Biyoloji 10, s. 20','metin':open('/dev/stdin').read()}), ensure_ascii=False, indent=1))" <<< "<chunk_egitim'den bir fotosentez parçası>"` → 3-4 geçerli soru, süre < 60 sn.
- [ ] **Step 6: Commit** — `git commit -m "soruhavuzu: Ollama soru üretici ve doğrulama"`

---

### Task 4: Kopya eleme (bilgehan bge-m3)

**Files:**
- Create: `soruhavuzu/tekrar.py`, `soruhavuzu/tests/test_tekrar.py`

**Interfaces:**
- Consumes: `server/uzak_model.py`: `ayar_oku() -> (url, anahtar)`, `olustur(url, anahtar)` — Step 1'de dönüş tipini oku (`UzakEmbed` nesnesi veya `(UzakEmbed, UzakReranker)` demeti) ve `_gomucu()`'yü ona göre yaz; `UzakEmbed.encode(metinler, normalize_embeddings=True)` → numpy dizi.
- Produces: `tekrar.Eleyici(gomucu)` → `.kopya_mi(ders: str, sinif: int, soru: str) -> bool` (aynı ders+sınıfta kosinüs ≥ 0.92 olan önceki soru varsa True, yoksa kaydeder). Bellek içi; süreç başında `yukle(conn)` ile DB'deki onaylı/üretilmiş sorular yüklenir.

- [ ] **Step 1: `uzak_model.olustur` dönüşünü oku** — `sed -n 129,146p server/uzak_model.py`.

- [ ] **Step 2: Failing test yaz**

```python
import numpy as np

from soruhavuzu import tekrar


class SahteGomucu:
    def encode(self, metinler, normalize_embeddings=True):
        tablo = {"log2(8) kaçtır?": [1, 0], "log2 8 kaçtır?": [0.99, 0.14], "Fotosentez nedir?": [0, 1]}
        v = np.array([tablo[m] for m in metinler], dtype=float)
        return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_benzer_soru_kopya_sayilir_farkli_ders_sayilmaz():
    e = tekrar.Eleyici(SahteGomucu())
    assert e.kopya_mi("matematik", 12, "log2(8) kaçtır?") is False
    assert e.kopya_mi("matematik", 12, "log2 8 kaçtır?") is True
    assert e.kopya_mi("biyoloji", 10, "log2 8 kaçtır?") is False
    assert e.kopya_mi("matematik", 12, "Fotosentez nedir?") is False
```

- [ ] **Step 3: FAIL gör.**

- [ ] **Step 4: `tekrar.py` yaz**

```python
"""soruhavuzu/tekrar.py — aynı ders+sınıfta neredeyse aynı soruları eler (bilgehan bge-m3)."""

import sys
from pathlib import Path

import numpy as np

ESIK = 0.92


class Eleyici:
    def __init__(self, gomucu):
        self.gomucu = gomucu
        self.vektorler: dict[tuple[str, int], list[np.ndarray]] = {}

    def _ekle(self, ders: str, sinif: int, v: np.ndarray) -> None:
        self.vektorler.setdefault((ders, sinif), []).append(v)

    def yukle(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute("SELECT ders, sinif, soru FROM soru WHERE durum IN ('uretildi','onayli')")
            satirlar = cur.fetchall()
        for i in range(0, len(satirlar), 64):
            parca = satirlar[i:i + 64]
            for (ders, sinif, _), v in zip(parca, self.gomucu.encode([s[2] for s in parca],
                                                                     normalize_embeddings=True)):
                self._ekle(ders, sinif, np.asarray(v))

    def kopya_mi(self, ders: str, sinif: int, soru: str) -> bool:
        v = np.asarray(self.gomucu.encode([soru], normalize_embeddings=True)[0])
        onceki = self.vektorler.get((ders, sinif), [])
        if onceki and float(np.max(np.stack(onceki) @ v)) >= ESIK:
            return True
        self._ekle(ders, sinif, v)
        return False


def _gomucu():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
    import uzak_model  # noqa: PLC0415 — server/ paket değil, yol eklenerek alınır
    sonuc = uzak_model.olustur(*uzak_model.ayar_oku())
    return sonuc[0] if isinstance(sonuc, tuple) else sonuc  # Step 1'de doğrulanan tipe göre sadeleştir
```

- [ ] **Step 5: PASS gör.**
- [ ] **Step 6: Canlı kontrol** — `server/venv/bin/python -c "from soruhavuzu import tekrar; g=tekrar._gomucu(); print(g.encode(['deneme']).shape)"` → `(1, 1024)`. (bilgehan zaten gündüz RAG için çalışıyor; bu çağrı hafif.)
- [ ] **Step 7: Commit** — `git commit -m "soruhavuzu: bilgehan bge-m3 ile kopya eleme"`

---

### Task 5: AGY denetçisi

**Files:**
- Create: `soruhavuzu/denetci.py`, `soruhavuzu/agy_sema.json`, `soruhavuzu/tests/test_denetci.py`

**Interfaces:**
- Consumes: `vt.denetlenecekler(conn, limit) -> list[dict]` (soru alanları + `birim_metin`), `vt.denetim_yaz(conn, soru_id, durum, not_)`
- Produces: `denetci.istem(paket: list[dict]) -> str`; `denetci.yaniti_coz(cikti: str, paket_idleri: set[int]) -> dict[int, tuple[bool, str]]`; `denetci.agy_cagir(istem: str, zaman_asimi_sn=900) -> str` (agy JSON çıktısı); `denetci.paket_denetle(conn, boyut=100, cagir=agy_cagir) -> int` (yazılan karar sayısı; 0 = iş yok).

- [ ] **Step 1: `agy_sema.json` yaz**

```json
{"type": "object", "required": ["kararlar"], "properties": {"kararlar": {"type": "array", "items": {
  "type": "object", "required": ["id", "gecerli", "neden"],
  "properties": {"id": {"type": "integer"}, "gecerli": {"type": "boolean"}, "neden": {"type": "string"}}}}}}
```

- [ ] **Step 2: Failing test yaz**

```python
import json

from soruhavuzu import denetci, vt
from soruhavuzu.tests.conftest import ORNEK_SORU


def _agy_cikti(kararlar):
    return json.dumps({"status": "SUCCESS", "response": json.dumps({"kararlar": kararlar})})


def test_yanit_cozulur_bilinmeyen_id_yok_sayilir():
    c = _agy_cikti([{"id": 1, "gecerli": True, "neden": "ok"}, {"id": 99, "gecerli": False, "neden": "x"}])
    assert denetci.yaniti_coz(c, {1, 2}) == {1: (True, "ok")}


def test_bozuk_cikti_bos_doner():
    assert denetci.yaniti_coz("agy hata verdi", {1}) == {}


def test_paket_denetle_kararlari_yazar_eksik_olan_bekler(conn):
    bid = vt.birim_ekle(conn, "kitap", "k:1", "matematik", 12, "E", "metin")
    a = vt.soru_ekle(conn, bid, ORNEK_SORU)
    b = vt.soru_ekle(conn, bid, {**ORNEK_SORU, "soru": "log3(9) kaçtır?"})
    istemler = []

    def sahte(istem, zaman_asimi_sn=900):
        istemler.append(istem)
        return _agy_cikti([{"id": a, "gecerli": False, "neden": "cevap yanlış"}])
    assert denetci.paket_denetle(conn, 20, cagir=sahte) == 1
    assert "log3(9)" in istemler[0] and "metin" in istemler[0]
    assert [s["id"] for s in vt.denetlenecekler(conn, 20)] == [b]
```

- [ ] **Step 3: FAIL gör.**

- [ ] **Step 4: `denetci.py` yaz**

```python
"""soruhavuzu/denetci.py — üretilen her soruyu AGY (Antigravity CLI) ile kaynak metne karşı denetler.

Kullanıcı kararı (2026-10-05): sorular yerel Ollama'da üretilir, üretim bitince AGY tüm havuzu tek
seferde denetler. Çağrı başına ~12k token sabit AGY maliyeti olduğu için tek çalıştırma içinde
sorular 100'lük paketler hâlinde, kaynak metinleriyle birlikte gönderilir."""

import json
import subprocess
from pathlib import Path

from soruhavuzu import vt

AGY = "/home/ata/.local/bin/agy"
SEMA = Path(__file__).with_name("agy_sema.json")
CALISMA_DIZINI = Path("/tmp/soruhavuzu-agy")
METIN_AZAMI = 2500


def istem(paket: list[dict]) -> str:
    bloklar, goruldu = [], set()
    for s in paket:
        if s["birim_id"] not in goruldu:
            goruldu.add(s["birim_id"])
            bloklar.append(f"\n### KAYNAK {s['birim_id']}\n{s['birim_metin'][:METIN_AZAMI]}")
        secenekler = " | ".join(f"{'ABCD'[i]}) {x}" for i, x in enumerate(s["secenekler"]))
        bloklar.append(f"- id={s['id']} (kaynak {s['birim_id']}, {s['ders']} {s['sinif']}. sınıf, "
                       f"zorluk {s['zorluk']}): {s['soru']}\n  Şıklar: {secenekler}\n"
                       f"  Doğru: {'ABCD'[s['dogru_index']]} / kısa cevap: {s['kisa_cevap']}")
    return ("Sen bir MEB lise soru denetçisisin. Aşağıdaki her soruyu ilgili KAYNAK metne göre denetle. "
            "Geçerli sayılması için: işaretli şık ve kısa cevap doğru, tek doğru şık var, soru açık ve "
            "tek başına anlaşılır, kaynak metinle uyumlu, sınıf düzeyine uygun. Dosya oluşturma, araç "
            "kullanma; yalnızca her id için bir karar içeren JSON döndür: "
            '{"kararlar": [{"id": 1, "gecerli": true, "neden": "kısa gerekçe"}]}\n' + "\n".join(bloklar))


def yaniti_coz(cikti: str, paket_idleri: set[int]) -> dict[int, tuple[bool, str]]:
    try:
        dis = json.loads(cikti)
        ic = dis.get("response", "") if isinstance(dis, dict) else ""
        ic = ic.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        kararlar = json.loads(ic).get("kararlar", [])
    except (json.JSONDecodeError, AttributeError, TypeError):
        return {}
    sonuc = {}
    for k in kararlar if isinstance(kararlar, list) else []:
        if isinstance(k, dict) and k.get("id") in paket_idleri and isinstance(k.get("gecerli"), bool):
            sonuc[k["id"]] = (k["gecerli"], str(k.get("neden", ""))[:500])
    return sonuc


def agy_cagir(istem: str, zaman_asimi_sn: int = 900) -> str:
    CALISMA_DIZINI.mkdir(exist_ok=True)
    r = subprocess.run([AGY, "-p", istem, "--output-format", "json", "--json-schema", str(SEMA),
                        "--mode", "plan", "--print-timeout", f"{zaman_asimi_sn}s"],
                       cwd=CALISMA_DIZINI, capture_output=True, text=True, timeout=zaman_asimi_sn + 30)
    return r.stdout


def paket_denetle(conn, boyut: int = 100, cagir=agy_cagir) -> int:
    paket = vt.denetlenecekler(conn, boyut)
    if not paket:
        return 0
    for s in paket:
        if isinstance(s["secenekler"], str):
            s["secenekler"] = json.loads(s["secenekler"])
    kararlar = yaniti_coz(cagir(istem(paket)), {s["id"] for s in paket})
    for sid, (gecerli, neden) in kararlar.items():
        vt.denetim_yaz(conn, sid, "onayli" if gecerli else "red", f"agy: {neden}")
    return len(kararlar)
```

- [ ] **Step 5: PASS gör** — `3 passed`.
- [ ] **Step 6: Canlı AGY denemesi (GPU kullanmaz, gündüz olabilir)** — test DB'sine 3 soru ekleyip `paket_denetle(vt.baglan("soru_havuzu_test"))` → 3 karar. `--json-schema`/`--mode plan` bayrakları hata verirse ilgili bayrağı kaldır ve not et (istem zaten JSON istiyor).
- [ ] **Step 7: Commit** — `git commit -m "soruhavuzu: AGY paket denetçisi"`

---

### Task 6: Zaman penceresi + CLI + systemd

**Files:**
- Create: `soruhavuzu/zaman.py`, `soruhavuzu/calistir.py`, `soruhavuzu/tests/test_zaman.py`, `soruhavuzu/systemd/soru-havuzu-uret.service`, `soruhavuzu/systemd/soru-havuzu-uret.timer`

**Interfaces:**
- Consumes: Task 1–5'in tamamı.
- Produces: `zaman.uretim_serbest(an: datetime | None = None) -> bool`; CLI `server/venv/bin/python -m soruhavuzu.calistir {kur|katalog|uret|denetle|durum}`.

- [ ] **Step 1: Failing test yaz**

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from soruhavuzu import zaman

TR = ZoneInfo("Europe/Istanbul")


def test_ders_saati_penceresi():
    assert zaman.uretim_serbest(datetime(2026, 10, 5, 17, 10, tzinfo=TR)) is True   # Pzt akşam
    assert zaman.uretim_serbest(datetime(2026, 10, 5, 7, 29, tzinfo=TR)) is True
    assert zaman.uretim_serbest(datetime(2026, 10, 5, 7, 30, tzinfo=TR)) is False
    assert zaman.uretim_serbest(datetime(2026, 10, 5, 12, 0, tzinfo=TR)) is False
    assert zaman.uretim_serbest(datetime(2026, 10, 10, 12, 0, tzinfo=TR)) is True   # Cumartesi
```

- [ ] **Step 2: FAIL gör.**

- [ ] **Step 3: `zaman.py` yaz**

```python
"""soruhavuzu/zaman.py — GPU üretimi yalnızca ders saati dışında (hafta içi 07:30–17:05 yasak)."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

TR = ZoneInfo("Europe/Istanbul")
BASLA, BITIS = time(7, 30), time(17, 5)


def uretim_serbest(an: datetime | None = None) -> bool:
    an = (an or datetime.now(TR)).astimezone(TR)
    if an.isoweekday() >= 6:
        return True
    return not (BASLA <= an.time() < BITIS)
```

- [ ] **Step 4: PASS gör.**

- [ ] **Step 5: `calistir.py` yaz**

```python
"""soruhavuzu/calistir.py — soru havuzu komutları.

  kur      şemayı kurar          katalog  kaynak birimlerini ekler
  uret     ders saati dışında birimleri işler (pencere kapanınca çıkar);
           bütün birimler bitince AGY denetimini BİR KEZ başlatır
  denetle  AGY ile tüm 'uretildi' soruları tek seferde denetler (elle de çalıştırılabilir)
  durum    özet sayılar"""

import sys
import time
from pathlib import Path

import psycopg2

from soruhavuzu import denetci, kaynaklar, tekrar, uretici, vt, zaman

VERI = Path("/mnt/farabi-data/farabi")


def uret(conn) -> None:
    eleyici = tekrar.Eleyici(tekrar._gomucu())
    eleyici.yukle(conn)
    while zaman.uretim_serbest():
        birim = vt.siradaki_birim(conn)
        if birim is None:
            print("[uret] bütün birimler işlendi — AGY tek seferlik denetim başlıyor", flush=True)
            denetle(conn)
            return
        t0 = time.perf_counter()
        try:
            sorular = uretici.uret(birim)
            eklenen = 0
            for s in sorular:
                if not eleyici.kopya_mi(s["ders"], s["sinif"], s["soru"]):
                    vt.soru_ekle(conn, birim["id"], s); eklenen += 1
            vt.birim_isaretle(conn, birim["id"], "islendi")
            print(f"[uret] {birim['anahtar']}: {eklenen}/{len(sorular)} soru, "
                  f"{time.perf_counter() - t0:.0f} sn", flush=True)
        except Exception as e:  # noqa: BLE001 — tek birimin hatası geceyi durdurmasın
            vt.birim_isaretle(conn, birim["id"], "hata", f"{type(e).__name__}: {e}"[:500])
            print(f"[uret] HATA {birim['anahtar']}: {type(e).__name__}: {e}", flush=True)
    print("[uret] ders saati penceresi — durduruldu")


def denetle(conn) -> None:
    ardisik_bos = 0
    while True:
        n = denetci.paket_denetle(conn)
        if n == 0 and not vt.denetlenecekler(conn, 1):
            print("[denetle] denetlenecek soru kalmadı"); return
        ardisik_bos = ardisik_bos + 1 if n == 0 else 0
        if ardisik_bos >= 3:
            print("[denetle] AGY art arda 3 pakette karar dönmedi — çıkılıyor"); return
        print(f"[denetle] {n} karar", flush=True)


def durum(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT tur, durum, count(*) FROM kaynak_birim GROUP BY 1,2 ORDER BY 1,2")
        for satir in cur.fetchall(): print("birim", *satir)
        cur.execute("SELECT ders, sinif, durum, count(*) FROM soru GROUP BY 1,2,3 ORDER BY 1,2,3")
        for satir in cur.fetchall(): print("soru", *satir)


def main() -> int:
    komut = sys.argv[1] if len(sys.argv) > 1 else "durum"
    conn = vt.baglan()
    if komut == "kur":
        vt.sema_kur(conn)
    elif komut == "katalog":
        farabi = psycopg2.connect(host="127.0.0.1", dbname="farabi", user="farabi")
        print(kaynaklar.katalogla(conn, farabi, VERI / "kazanim_test", VERI / "yks"))
    elif komut == "uret":
        uret(conn)
    elif komut == "denetle":
        denetle(conn)
    else:
        durum(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Katalog (gündüz güvenli, GPU yok)** — `cd /home/ata/farabi && server/venv/bin/python -m soruhavuzu.calistir katalog` → yaklaşık `{'kitap': ~5000, 'kazanim': ~2000, 'yks': ~800, ...}`; ardından `... durum`. Sınıfı çözülemeyen kazanım PDF'lerini (`1.pdf`, `13.pdf`, `202582...-biyoloji.pdf` gibi) listeleyip kullanıcıya sor — elle eşleme gerekebilir.

- [ ] **Step 7: systemd dosyaları yaz**

`soru-havuzu-uret.service`:
```ini
[Unit]
Description=Soru havuzu gece üretimi (Ollama qwen3.8:27b) — ders saatinde kendiliğinden durur
After=ollama.service postgresql.service

[Service]
Type=simple
User=ata
WorkingDirectory=/home/ata/farabi
ExecStart=/home/ata/farabi/server/venv/bin/python -m soruhavuzu.calistir uret
Nice=10
```
`soru-havuzu-uret.timer`:
```ini
[Unit]
Description=Soru havuzu üretimi — her gün 17:15 TR (14:15 UTC), hafta sonu 08:00 TR da başlar

[Timer]
OnCalendar=*-*-* 14:15:00 UTC
OnCalendar=Sat,Sun *-*-* 05:00:00 UTC
Persistent=false

[Install]
WantedBy=timers.target
```
AGY denetimi için ayrı zamanlayıcı YOK (kullanıcı kararı: tek seferde) — `uret` iş bitince kendisi başlatır.

- [ ] **Step 8: Kur ve etkinleştir**

```bash
sudo cp soruhavuzu/systemd/soru-havuzu-* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now soru-havuzu-uret.timer
systemctl list-timers 'soru-havuzu-*'
```
Expected: timer listede; `uret` bir sonraki 14:15 UTC'de. (Not: `daemon-reload` ollama.service'i yeniden başlatmaz.)

- [ ] **Step 9: Tüm testler** — `pytest -q soruhavuzu/tests` → hepsi PASS. Commit: `git commit -m "soruhavuzu: CLI, ders saati penceresi ve systemd zamanlayıcıları"`

---

### Task 7: Arena ve HexaFetih havuz entegrasyonu

**Files:**
- Create: `/home/ata/arenasinif/havuz.py`, `/home/ata/arenasinif/test_havuz.py`
- Modify: `/home/ata/arenasinif/server.py` (`soru_uret` ~satır 300, `fetih_oturum` ~satır 507), `/home/ata/arenasinif/fetih_motoru.py:1604` (`haritayi_hazirla`)

**Interfaces:**
- Consumes: `soru_havuzu.soru` tablosu (yalnızca `durum='onayli'`).
- Produces: `havuz.jeopardy_seti(ders: str, sinif: int, konu: str = "", sorgu=None) -> list[dict] | None` — `ollama_soru_uret` ile aynı biçim (4 kategori × 4 soru, `points` 100–400, `q`, `a`, `kaynak`, `answered`); `havuz.petek_sorulari(ders: str, sinif: int, adet: int, sorgu=None) -> list[dict] | None` — `{konu, q, secenekler, a, kaynak}` (`a` = doğru şık metni). `sorgu` testte sahte veri vermek için: `sorgu(sql, parametreler) -> list[tuple]`. `fetih_motoru.haritayi_hazirla(ders_adi: str, sinif: int = 9)`.

- [ ] **Step 1: Bağımlılık** — `HTTPS_PROXY=http://wifi:vodafone@192.168.23.243:8080 /home/ata/arenasinif/venv/bin/pip install psycopg2-binary` (okul LAN'ı PyPI'yi engelleyebilir).

- [ ] **Step 2: Failing test yaz** — `test_havuz.py`:

```python
import havuz


def _sahte(satirlar):
    return lambda sql, p: satirlar


def _satir(konu, zorluk, i):
    # id, konu, zorluk, soru, kisa_cevap, secenekler, dogru_index, kaynak
    return (i, konu, zorluk, f"S{i}", f"C{i}", ["a", "b", "c", "d"], 2, "Matematik 12, s. 5")


def test_jeopardy_dort_konu_dort_zorluk():
    satirlar = [_satir(k, z, i) for i, (k, z) in enumerate(
        (k, z) for k in ("Log", "Türev", "İntegral", "Limit", "Fazla") for z in (1, 2, 3, 4))]
    s = havuz.jeopardy_seti("matematik", 12, sorgu=_sahte(satirlar))
    assert len(s) == 4 and all(len(k["questions"]) == 4 for k in s)
    assert [q["points"] for q in s[0]["questions"]] == [100, 200, 300, 400]
    assert s[0]["questions"][0]["answered"] is False


def test_jeopardy_yetersizse_none():
    assert havuz.jeopardy_seti("matematik", 12, sorgu=_sahte([_satir("Log", 1, 1)])) is None


def test_petekler_benzersiz_ve_dogru_sik_metni():
    satirlar = [_satir("Log", 1 + i % 4, i) for i in range(25)]
    p = havuz.petek_sorulari("matematik", 12, 19, sorgu=_sahte(satirlar))
    assert len(p) == 19 and len({x["q"] for x in p}) == 19 and p[0]["a"] == "c"


def test_db_hatasinda_none():
    def patla(sql, p): raise RuntimeError("db yok")
    assert havuz.jeopardy_seti("matematik", 12, sorgu=patla) is None
```

- [ ] **Step 3: FAIL gör** — `cd /home/ata/arenasinif && venv/bin/python -m pytest -q test_havuz.py`.

- [ ] **Step 4: `havuz.py` yaz**

```python
"""havuz.py — soru_havuzu veritabanından (yalnızca AGY onaylı) anında soru çeker.
Havuz boş/erişilemezse None döner; çağıran mevcut RAG+Ollama / statik akışa düşer."""

import logging
import random

log = logging.getLogger("arena.havuz")
SUTUNLAR = "id, konu, zorluk, soru, kisa_cevap, secenekler, dogru_index, kaynak"
RENKLER = [("from-blue-600 to-indigo-600", "text-blue-400 bg-blue-500/20 border-blue-500/40"),
           ("from-emerald-600 to-teal-600", "text-emerald-400 bg-emerald-500/20 border-emerald-500/40"),
           ("from-amber-600 to-orange-600", "text-amber-400 bg-amber-500/20 border-amber-500/40"),
           ("from-purple-600 to-pink-600", "text-purple-400 bg-purple-500/20 border-purple-500/40")]


def _db_sorgu(sql, parametreler):
    import psycopg2  # noqa: PLC0415 — testlerde gerekmesin
    with psycopg2.connect(host="127.0.0.1", dbname="soru_havuzu", user="farabi", connect_timeout=3) as c:
        with c.cursor() as cur:
            cur.execute(sql, parametreler)
            satirlar = cur.fetchall() if cur.description else []
            ids = [s[0] for s in satirlar]
            if ids:
                cur.execute("UPDATE soru SET kullanim_sayisi = kullanim_sayisi + 1 WHERE id = ANY(%s)", (ids,))
            return satirlar


def _cek(ders, sinif, konu, sorgu, limit=400):
    sql = (f"SELECT {SUTUNLAR} FROM soru WHERE durum = 'onayli' AND ders = %s AND sinif = %s "
           + ("AND konu ILIKE %s " if konu else "")
           + "ORDER BY kullanim_sayisi, random() LIMIT %s")
    p = (ders, sinif) + ((f"%{konu}%",) if konu else ()) + (limit,)
    try:
        return (sorgu or _db_sorgu)(sql, p)
    except Exception as e:  # noqa: BLE001 — havuz yardımcı; hata = eski akış
        log.warning("havuz okunamadı: %s", e)
        return None


def jeopardy_seti(ders: str, sinif: int, konu: str = "", sorgu=None) -> list[dict] | None:
    satirlar = _cek(ders, sinif, konu, sorgu)
    if not satirlar:
        return None
    konular: dict[str, dict[int, tuple]] = {}
    for s in satirlar:
        konular.setdefault(s[1], {}).setdefault(s[2], s)
    tam = [k for k, z in konular.items() if len(z) == 4]
    if len(tam) < 4:
        return None
    random.shuffle(tam)
    cikti = []
    for i, k in enumerate(tam[:4]):
        renk, rozet = RENKLER[i]
        cikti.append({"id": f"havuz_kat_{i + 1}", "name": k, "color": renk, "badgeColor": rozet,
                      "questions": [{"points": z * 100, "q": konular[k][z][3], "a": konular[k][z][4],
                                     "kaynak": konular[k][z][7], "answered": False} for z in (1, 2, 3, 4)]})
    return cikti


def petek_sorulari(ders: str, sinif: int, adet: int, sorgu=None) -> list[dict] | None:
    satirlar = _cek(ders, sinif, "", sorgu)
    if not satirlar or len(satirlar) < adet:
        return None
    return [{"konu": s[1], "q": s[3], "secenekler": list(s[5]), "a": s[5][s[6]], "kaynak": s[7]}
            for s in satirlar[:adet]]
```

- [ ] **Step 5: PASS gör** — `4 passed`.

- [ ] **Step 6: `server.py` `soru_uret` — havuzu önce dene.** `t0 = time.perf_counter()` satırından hemen sonra ekle:

```python
    ders_anahtari = soru_uretici.KAPSAM_ESLEME.get(istek.ders.strip().lower(), istek.ders.strip().lower())
    havuz_seti = havuz.jeopardy_seti(ders_anahtari, sinif_duzeyi, istek.konu)
    if havuz_seti:
        gecen_sn = time.perf_counter() - t0
        logger.log_soru_uret(ip=istemci_ip, sinif=istek.sinif, ders=istek.ders, konu=istek.konu,
                             kaynak="soru_havuzu", sure_sn=gecen_sn, durum="ok")
        return {"durum": "ok", "kaynak": "soru_havuzu", "sure_sn": round(gecen_sn, 1), "sorular": havuz_seti}
```
ve dosya başındaki importlara `import havuz` ekle.

- [ ] **Step 7: `fetih_motoru.haritayi_hazirla(ders_adi, sinif=9)`** — imzayı değiştir; `soru_listesi` belirlendikten sonra (mevcut `# 2. Soru listesini al` bloğunun ardından) ekle:

```python
    havuzdan = havuz.petek_sorulari(ders_key, sinif, len(piksel_koordinatlari()))
    if havuzdan:
        soru_listesi = havuzdan
```
Havuz kayıtları statik kayıtlarla aynı anahtarları taşır (`konu`, `q`, `secenekler`, `a`, `kaynak`), döngünün geri kalanı değişmez. `fetih_motoru.py` başına `import havuz`. `server.py:507`: `fetih_motoru.haritayi_hazirla(ders_adi, sinif_duzeyi_coz(secilen_sinif))`.

- [ ] **Step 8: Testler** — `venv/bin/python -m pytest -q test_arena.py test_havuz.py` → yalnızca bilinen eski hata (`test_yoklama_ve_ogrenciler`, 2026-10-05 öncesinden kırık) kalmalı.

- [ ] **Step 9: Canlıya al (17:00 sonrası)** — `cp server.py server.py.bak-<tarih>` (arenasinif git değil), `sudo systemctl restart sinif-arena`, `curl -s -X POST localhost:8030/api/arena/soru-uret -H 'Content-Type: application/json' -d '{"sinif":"fenlab","ders":"Matematik"}' | head -c 400` → havuz dolduğunda `"kaynak":"soru_havuzu"` ve `sure_sn` < 1.

---

### Task 8: Belgeleme

- [ ] `DECISIONS.md`'ye ekle:
```
## 2026-10-05 - Oyunlar için soru_havuzu veritabanı
- Ayrı PostgreSQL DB `soru_havuzu`; gece (ders saati dışı) qwen3.8:27b ile kitap/kazanım/YKS kaynaklı çoktan seçmeli sorular (yalnızca yerel Ollama), üretim bitince AGY tüm havuzu tek seferde denetler, kopyalar bilgehan bge-m3 ile elenir; arena/Hexa yalnızca onaylı soruları anında çeker.
- Neden: canlı 16 soruluk üretim 45–65 sn sürüyordu, hazır havuz 9. sınıfa kilitliydi, Hexa'da sınıf düzeyi ve soru çeşitliliği yoktu.
```
- [ ] `llm-cluster-wiki/nodes/farabi.md` (Müdür PC'de, yerel): yeni DB + iki timer satırı.
- [ ] Commit: `git commit -m "docs: soru havuzu kararı"`
