# Soru Havuzu Kazanım Eşleşmesi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Soru havuzundaki her soruyu yıllık plan kazanımına bağlamak: mevcut onaylı soruları etiketlemek ve gece üretimini kitap sayfasından değil kazanımdan başlatmak.

**Architecture:** Yeni `kazanim` tablosu `tahtayoklama/data/kazanimlar.json`'dan dolar; `soru` tablosu `kazanim_id/kazanim_skor/kazanim_kaynak` alır. Etiketleme ve kaynak bulma bilgehan bge-m3 (`tekrar._gomucu()`) ile; kaynak parçalar farabi DB `chunk_egitim` (pgvector `<=>`). `calistir.uret` döngüsü `vt.siradaki_kazanim` → `kaynak.bul` → `uretici.uret_kazanim` olur. Denetçi istemi kazanım satırı alır; `kazanimtest.secici` önce `kazanim_id` ile çeker.

**Tech Stack:** Python 3.14 (server/venv), psycopg2, PostgreSQL 18 + pgvector, httpx (Ollama), pytest (`soru_havuzu_test` DB fixture).

**Spec:** `docs/superpowers/specs/2026-10-08-soru-havuzu-kazanim-eslesmesi-design.md`

## Global Constraints

- Komutlar kökten: `server/venv/bin/python -m soruhavuzu.calistir <komut>`; test: `server/venv/bin/python -m pytest soruhavuzu/tests -q` (ve `kazanimtest/tests`).
- Testler gerçek `soru_havuzu`/`farabi` DB'sine ve bilgehan'a GİTMEZ: `soru_havuzu_test` fixture'ı + sahte gömücü + sahte kaynak bulucu.
- Etiket eşiği **0,55** (kapsam ölçümüyle aynı); kaynak eşiği **0,45**; kazanım hedefi **10 onaylı**, `uretildi+onayli ≥ 14` olan atlanır; tur başına kazanım en çok **2** deneme.
- Yalnız yıllık planı olan (sınıf, ders); plansız ders hiç üretilmez.
- Ders saati penceresi (`zaman.uretim_serbest`), kopya eleme (`tekrar.ESIK` 0,92), `denetci.ISTEM_AZAMI_BAYT` korunur.
- Şema değişikliği idempotent (`IF NOT EXISTS`); `kur` komutu canlıda güvenle tekrar koşar.
- Ön koşul: `git status --short soruhavuzu kazanimtest` temiz olmalı (başka oturumun commit'lenmemiş işi varsa DUR, sor).

## Review Focus

- `kazanimlar.json`'da aynı metin birden çok haftada (DEVAM_HAFTALARI) → tek kazanım üretimi, her hafta satırı ayrı ama aynı metin iki kez üretilmez (Task 3 testi).
- Etiketleme `--kuru` hiçbir satır yazmaz (Task 2 testi).
- Kitabı olmayan ya da en iyi parça skoru < 0,45 kazanım → `kaynak_yok`, Ollama çağrılmaz, gece durmaz (Task 4 testi).
- Ders saati başlarsa döngü kazanım ortasında değil kazanım sonunda durur (Task 5 testi).
- `kazanimtest` kazanım_id'li soru yetmezse eski benzerlik aramasına düşer (Task 7 testi).

---

### Task 1: Şema + `kazanim-yukle`

**Files:**
- Modify: `soruhavuzu/sema.sql` (sona ekle)
- Create: `soruhavuzu/kazanimlar.py`
- Modify: `soruhavuzu/vt.py` (`kazanim_upsert`)
- Modify: `soruhavuzu/calistir.py` (`kazanim-yukle [--kuru]` alt komutu)
- Test: `soruhavuzu/tests/test_kazanimlar.py`

**Interfaces:**
- Produces: `kazanimlar.oku(yol: Path) -> list[dict]` — her öğe `{"sinif": int, "ders": str, "hafta": int, "kod": str|None, "metin": str}`, sayılar `{"atlanan_ders": set[str]}` ikinci dönüş değeri: `oku(...) -> tuple[list[dict], set[str]]`. `vt.kazanim_upsert(conn, k: dict) -> int` (id). `kazanimlar.KOD_RE`.

- [ ] **Step 1: Failing test**
```python
"""kazanimlar.json → kazanim satırları."""
import json

from soruhavuzu import kazanimlar, vt

ORNEK = {"haftalar": {"1": "2026-09-14", "2": "2026-09-21"},
         "kazanimlar": {"9": {"kimya": {"1": "KİM.9.1.1. Kimya biliminin katkısı",
                                        "2": "KİM.9.1.1. Kimya biliminin katkısı"},
                              "beden eğitimi": {"1": "Spor"}},
                        "10": {"matematik": {"5": "10.1.3. Üçgenin alanı\n10.1.4. Dörtgenin alanı"}}}}


def test_oku_boler_esler_atlar(tmp_path):
    y = tmp_path / "k.json"
    y.write_text(json.dumps(ORNEK, ensure_ascii=False), encoding="utf-8")
    satirlar, atlanan = kazanimlar.oku(y)
    assert {"beden eğitimi"} == atlanan
    mat = [s for s in satirlar if s["ders"] == "matematik"]
    assert [(s["hafta"], s["kod"]) for s in mat] == [(5, "10.1.3"), (5, "10.1.4")]
    kim = [s for s in satirlar if s["ders"] == "kimya"]
    assert [s["hafta"] for s in kim] == [1, 2] and kim[0]["kod"] == "KİM.9.1.1"


def test_upsert_cogaltmaz(conn):
    k = {"sinif": 9, "ders": "kimya", "hafta": 1, "kod": "KİM.9.1.1", "metin": "KİM.9.1.1. X"}
    a = vt.kazanim_upsert(conn, k)
    b = vt.kazanim_upsert(conn, k)
    assert a == b
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM kazanim")
        assert cur.fetchone()[0] == 1
```
`tests/conftest.py`'deki `TRUNCATE`'e `kazanim` ekle: `"TRUNCATE soru, kaynak_birim, kazanim RESTART IDENTITY CASCADE"`.

- [ ] **Step 2: Run** `server/venv/bin/python -m pytest soruhavuzu/tests/test_kazanimlar.py -q` → FAIL (modül yok).

- [ ] **Step 3: Implementation**

`sema.sql` sonuna:
```sql
CREATE TABLE IF NOT EXISTS kazanim (
    id      serial PRIMARY KEY,
    sinif   smallint NOT NULL,
    ders    text NOT NULL,
    hafta   smallint NOT NULL,
    kod     text,
    metin   text NOT NULL,
    durum   text NOT NULL DEFAULT 'aktif' CHECK (durum IN ('aktif', 'kaynak_yok')),
    UNIQUE (sinif, ders, hafta, metin)
);
ALTER TABLE soru ADD COLUMN IF NOT EXISTS kazanim_id integer REFERENCES kazanim(id);
ALTER TABLE soru ADD COLUMN IF NOT EXISTS kazanim_skor real;
ALTER TABLE soru ADD COLUMN IF NOT EXISTS kazanim_kaynak text CHECK (kazanim_kaynak IN ('uretim', 'etiket'));
CREATE INDEX IF NOT EXISTS soru_kazanim_idx ON soru (kazanim_id, durum);
```
`kazanimlar.py`:
```python
"""soruhavuzu/kazanimlar.py — yıllık plan kazanımları (tahtayoklama/data/kazanimlar.json) → kazanim satırları.
2026-10-08 kullanıcı kararı: her soru bir kazanımla; yalnız planı olan (sınıf, ders)."""

import json
import re
from pathlib import Path

from soruhavuzu import dersler

VARSAYILAN = Path(__file__).resolve().parent.parent / "tahtayoklama" / "data" / "kazanimlar.json"
# "KİM.9.1.1." ya da "10.1.3." — sondaki nokta koddan sayılmaz
KOD_RE = re.compile(r"^\s*((?:[A-ZÇĞİÖŞÜ]{2,6}\.)?\d+(?:\.\d+)+)\.?\s")


def oku(yol: Path = VARSAYILAN) -> tuple[list[dict], set[str]]:
    veri = json.loads(Path(yol).read_text(encoding="utf-8"))["kazanimlar"]
    satirlar, atlanan = [], set()
    for sinif, dersler_ in veri.items():
        for ders_ad, haftalar in dersler_.items():
            anahtar = dersler.ders_anahtari(ders_ad)
            if anahtar is None:
                atlanan.add(ders_ad)
                continue
            for hafta, metin in sorted(haftalar.items(), key=lambda x: int(x[0])):
                for parca in (m.strip() for m in str(metin).split("\n")):
                    if not parca:
                        continue
                    m = KOD_RE.match(parca + " ")
                    satirlar.append({"sinif": int(sinif), "ders": anahtar, "hafta": int(hafta),
                                     "kod": m.group(1) if m else None, "metin": parca})
    return satirlar, atlanan
```
`vt.py`:
```python
def kazanim_upsert(conn, k: dict) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO kazanim (sinif, ders, hafta, kod, metin) VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT (sinif, ders, hafta, metin) DO UPDATE SET kod = EXCLUDED.kod RETURNING id",
            (k["sinif"], k["ders"], k["hafta"], k["kod"], k["metin"]))
        kid = cur.fetchone()[0]
    conn.commit()
    return kid
```
`calistir.py` `main()`: `sub.add_parser("kazanim-yukle").add_argument("--kuru", action="store_true")` ve:
```python
    elif komut == "kazanim-yukle":
        satirlar, atlanan = kazanimlar.oku()
        if not args.kuru:
            for k in satirlar:
                vt.kazanim_upsert(conn, k)
        print(f"[kazanim-yukle] {len(satirlar)} satır{' (kuru)' if args.kuru else ''}; "
              f"eşlenemeyen ders: {sorted(atlanan)}", flush=True)
```
(`from soruhavuzu import kazanimlar` import'a eklenir.)

- [ ] **Step 4: Run** test → PASS; tüm paket `server/venv/bin/python -m pytest soruhavuzu/tests -q` → PASS.
- [ ] **Step 5: Commit** `git commit -m "soruhavuzu: kazanim tablosu + kazanim-yukle (yıllık plan → kazanım satırları)"`

---

### Task 2: Geri doldurma — `etiketle [--kuru]`

**Files:**
- Create: `soruhavuzu/etiketle.py`
- Modify: `soruhavuzu/calistir.py` (`etiketle` alt komutu)
- Test: `soruhavuzu/tests/test_etiketle.py`

**Interfaces:**
- Consumes: `vt.kazanim_upsert`; gömücü arayüzü `encode(list[str], normalize_embeddings=True) -> list[array]` (`tekrar._gomucu()` ile aynı).
- Produces: `etiketle.etiketle(conn, gomucu, kuru: bool = False, esik: float = ESIK) -> dict` → `{"etiketlenen": int, "etiketsiz": int, "dagilim": {(sinif, ders): (etiketlenen, toplam)}}`; `ESIK = 0.55`.

- [ ] **Step 1: Failing test**
```python
import numpy as np

from soruhavuzu import etiketle, vt
from soruhavuzu.tests.conftest import ORNEK_SORU


class SahteGomucu:
    """'alan' içeren metin [1,0], 'açı' içeren [0,1], diğerleri [0.5,0.5] normalize."""
    def encode(self, metinler, normalize_embeddings=True):
        cikti = []
        for m in metinler:
            v = np.array([1.0, 0.0]) if "alan" in m else np.array([0.0, 1.0]) if "açı" in m else np.array([0.6, 0.6])
            cikti.append(v / np.linalg.norm(v))
        return cikti


def _hazirla(conn):
    k1 = vt.kazanim_upsert(conn, {"sinif": 12, "ders": "matematik", "hafta": 1, "kod": "12.1", "metin": "Üçgenin alanı"})
    vt.kazanim_upsert(conn, {"sinif": 12, "ders": "matematik", "hafta": 2, "kod": "12.2", "metin": "Dış açı"})
    bid = vt.birim_ekle(conn, "kitap", "k:1", "matematik", 12, "E", "metin")
    s1 = vt.soru_ekle(conn, bid, {**ORNEK_SORU, "soru": "Üçgenin alanı nedir?"})
    s2 = vt.soru_ekle(conn, bid, {**ORNEK_SORU, "soru": "Logaritma nedir?"})
    with conn.cursor() as cur:
        cur.execute("UPDATE soru SET durum='onayli'")
    conn.commit()
    return k1, s1, s2


def test_esik_ustu_etiketlenir_alti_kalir(conn):
    k1, s1, s2 = _hazirla(conn)
    sonuc = etiketle.etiketle(conn, SahteGomucu())
    assert sonuc["etiketlenen"] == 1
    with conn.cursor() as cur:
        cur.execute("SELECT id, kazanim_id, kazanim_kaynak FROM soru ORDER BY id")
        satirlar = cur.fetchall()
    assert satirlar[0] == (s1, k1, "etiket")
    assert satirlar[1][1] is None   # 0.6/0.6 normalize ≈ 0.707 > 0.55? → test gömücüsü eşik altı olmalı


def test_kuru_yazmaz(conn):
    _hazirla(conn)
    etiketle.etiketle(conn, SahteGomucu(), kuru=True)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM soru WHERE kazanim_id IS NOT NULL")
        assert cur.fetchone()[0] == 0
```
Not: `SahteGomucu`'da "diğerleri" vektörü `[0.6, 0.6]` normalize edilince her iki kazanıma kosinüs ≈ 0,707 (> 0,55) olur ve test yanlış olur. Vektörü `np.array([-1.0, 0.2])` yap (kosinüs < 0) — testi yazarken bu düzeltmeyle yaz; `s2` etiketsiz kalmalı.

- [ ] **Step 2: Run** → FAIL (modül yok).
- [ ] **Step 3: Implementation** `etiketle.py`:
```python
"""soruhavuzu/etiketle.py — mevcut onaylı soruları en yakın kazanıma bağlar (bir kerelik geri doldurma).
Gömme bilgehan bge-m3 (tekrar._gomucu); eşik kapsam ölçümüyle aynı (0,55)."""

import numpy as np

ESIK = 0.55


def etiketle(conn, gomucu, kuru: bool = False, esik: float = ESIK) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT id, sinif, ders, metin FROM kazanim WHERE durum = 'aktif'")
        kazanimlar = cur.fetchall()
        cur.execute("SELECT id, sinif, ders, soru, secenekler, dogru_index FROM soru "
                    "WHERE durum = 'onayli' AND kazanim_id IS NULL")
        sorular = cur.fetchall()
    gruplar: dict = {}
    for kid, sinif, ders, metin in kazanimlar:
        gruplar.setdefault((sinif, ders), []).append((kid, metin))
    kvek = {}
    for anahtar, liste in gruplar.items():
        v = gomucu.encode([m for _, m in liste], normalize_embeddings=True)
        kvek[anahtar] = ([k for k, _ in liste], np.stack([np.asarray(x) for x in v]))
    dagilim, yazilacak = {}, []
    for i in range(0, len(sorular), 64):
        parca = sorular[i:i + 64]
        metinler = []
        for _, _, _, soru, sec, di in parca:
            secenekler = sec if isinstance(sec, list) else []
            dogru = secenekler[di] if 0 <= di < len(secenekler) else ""
            metinler.append(f"{soru} {dogru}")
        vler = gomucu.encode(metinler, normalize_embeddings=True)
        for (sid, sinif, ders, *_), v in zip(parca, vler):
            et, top = dagilim.get((sinif, ders), (0, 0))
            hedef = kvek.get((sinif, ders))
            if hedef is None:
                dagilim[(sinif, ders)] = (et, top + 1)
                continue
            skorlar = hedef[1] @ np.asarray(v)
            j = int(np.argmax(skorlar))
            if float(skorlar[j]) >= esik:
                yazilacak.append((hedef[0][j], float(skorlar[j]), sid))
                et += 1
            dagilim[(sinif, ders)] = (et, top + 1)
    if not kuru and yazilacak:
        with conn.cursor() as cur:
            cur.executemany("UPDATE soru SET kazanim_id=%s, kazanim_skor=%s, kazanim_kaynak='etiket' "
                            "WHERE id=%s AND kazanim_id IS NULL", yazilacak)
        conn.commit()
    toplam = sum(t for _, t in dagilim.values())
    return {"etiketlenen": len(yazilacak), "etiketsiz": toplam - len(yazilacak), "dagilim": dagilim}
```
`calistir.py`: `sub.add_parser("etiketle").add_argument("--kuru", action="store_true")`;
```python
    elif komut == "etiketle":
        s = etiketle.etiketle(conn, tekrar._gomucu(), kuru=args.kuru)
        for (sinif, ders), (et, top) in sorted(s["dagilim"].items()):
            print(f"  {sinif:>2} {ders:<10} {et:>4}/{top:<4}", flush=True)
        print(f"[etiketle] {s['etiketlenen']} etiketlendi, {s['etiketsiz']} etiketsiz"
              f"{' (kuru — yazılmadı)' if args.kuru else ''}", flush=True)
```
- [ ] **Step 4: Run** → PASS; paket PASS.
- [ ] **Step 5: Commit** `"soruhavuzu: etiketle — mevcut onaylı sorular kazanıma (bge-m3 ≥0,55), --kuru"`

---

### Task 3: Kazanım sırası — `vt.siradaki_kazanim`

**Files:** Modify `soruhavuzu/vt.py`; Test `soruhavuzu/tests/test_siradaki_kazanim.py`

**Interfaces:**
- Produces: `vt.siradaki_kazanim(conn, bugun: date, haftalar: dict[int, date], denenen: set[int], hedef_toplam: int = 14) -> dict | None` → `{"id","sinif","ders","hafta","kod","metin"}`. Sıra: (1) `hafta` bugünün plan haftası ile +3 arasında olanlar önce (`haftalar`: plan haftası → pazartesi), (2) `uretildi+onayli` sayısı az olan, (3) id. Aynı metinli satırlardan yalnız en küçük `hafta`'lı aday olur (DISTINCT ON (sinif, ders, metin)). `durum='kaynak_yok'` ve `denenen` id'ler atlanır; sayısı `>= hedef_toplam` olanlar atlanır.
- Produces: `vt.kazanim_isaretle(conn, kid: int, durum: str) -> None`.

- [ ] **Step 1: Failing test**
```python
from datetime import date

from soruhavuzu import vt
from soruhavuzu.tests.conftest import ORNEK_SORU

HAFTALAR = {1: date(2026, 9, 14), 4: date(2026, 10, 5), 5: date(2026, 10, 12), 10: date(2026, 11, 23)}


def _k(conn, hafta, metin, ders="matematik"):
    return vt.kazanim_upsert(conn, {"sinif": 10, "ders": ders, "hafta": hafta, "kod": None, "metin": metin})


def test_yaklasan_hafta_once_ayni_metin_tek(conn):
    uzak = _k(conn, 10, "uzak kazanım")
    yakin = _k(conn, 5, "yakın kazanım")
    _k(conn, 4, "yakın kazanım")          # aynı metin, önceki hafta — tek aday olmalı
    s = vt.siradaki_kazanim(conn, date(2026, 10, 8), HAFTALAR, set())
    assert s["metin"] == "yakın kazanım" and s["hafta"] == 4
    assert vt.siradaki_kazanim(conn, date(2026, 10, 8), HAFTALAR, {s["id"]})["id"] == uzak
    assert yakin != uzak


def test_hedefe_ulasan_ve_kaynak_yok_atlanir(conn):
    a = _k(conn, 4, "a")
    b = _k(conn, 4, "b")
    bid = vt.birim_ekle(conn, "kitap", "k:1", "matematik", 10, "E", "m")
    for i in range(14):
        vt.soru_ekle(conn, bid, {**ORNEK_SORU, "sinif": 10, "soru": f"s{i}"}, kazanim_id=a, kazanim_kaynak="uretim")
    vt.kazanim_isaretle(conn, b, "kaynak_yok")
    assert vt.siradaki_kazanim(conn, date(2026, 10, 8), HAFTALAR, set()) is None
```
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implementation** — `soru_ekle`'ye isteğe bağlı parametreler ekle (geriye uyumlu):
```python
def soru_ekle(conn, birim_id, s: dict, kazanim_id=None, kazanim_skor=None, kazanim_kaynak=None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO soru (birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler, "
            "dogru_index, zorluk, kaynak, kazanim_id, kazanim_skor, kazanim_kaynak) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (birim_id, s["ders"], s["sinif"], s["konu"], s["soru"], s["kisa_cevap"],
             json.dumps(s["secenekler"], ensure_ascii=False), s["dogru_index"], s["zorluk"],
             s["kaynak"], kazanim_id, kazanim_skor, kazanim_kaynak))
        sid = cur.fetchone()[0]
    conn.commit()
    return sid


def kazanim_isaretle(conn, kid: int, durum: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE kazanim SET durum=%s WHERE id=%s", (durum, kid))
    conn.commit()


def siradaki_kazanim(conn, bugun, haftalar: dict, denenen: set, hedef_toplam: int = 14) -> dict | None:
    gecmis = [h for h, pzt in haftalar.items() if pzt <= bugun]
    simdiki = max(gecmis) if gecmis else min(haftalar, default=0)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "WITH tek AS (SELECT DISTINCT ON (sinif, ders, metin) * FROM kazanim WHERE durum='aktif' "
            "  ORDER BY sinif, ders, metin, hafta, id), "
            "sayim AS (SELECT kazanim_id, count(*) AS n FROM soru "
            "  WHERE durum IN ('uretildi','onayli') AND kazanim_id IS NOT NULL GROUP BY kazanim_id) "
            "SELECT t.id, t.sinif, t.ders, t.hafta, t.kod, t.metin, COALESCE(s.n,0) AS n FROM tek t "
            "LEFT JOIN sayim s ON s.kazanim_id = t.id "
            "WHERE COALESCE(s.n,0) < %s AND NOT (t.id = ANY(%s)) "
            "ORDER BY (t.hafta BETWEEN %s AND %s) DESC, COALESCE(s.n,0), t.hafta, t.id LIMIT 1",
            (hedef_toplam, list(denenen) or [0], simdiki, simdiki + 3))
        satir = cur.fetchone()
    return dict(satir) if satir else None
```
Not: aynı metinli farklı hafta satırlarına üretilen sorular DISTINCT ON'un seçtiği (en küçük hafta) satırın `id`'sine yazılır; sayım da o id üzerinden — tutarlı.
- [ ] **Step 4: Run** → PASS; paket PASS (mevcut `soru_ekle` çağrıları değişmeden çalışır).
- [ ] **Step 5: Commit** `"soruhavuzu: siradaki_kazanim (yaklaşan hafta, az sorulu önce, aynı metin tek)"`

---

### Task 4: Kaynak bulucu + kazanım istemi

**Files:** Create `soruhavuzu/kaynak.py`; Modify `soruhavuzu/uretici.py`; Test `soruhavuzu/tests/test_kaynak_uretim.py`

**Interfaces:**
- Produces: `kaynak.bul(farabi_conn, gomucu, sinif: int, ders: str, kazanim_metin: str, k: int = 3) -> dict | None` → `{"etiket": str, "metin": str, "chunk_idler": list[int], "skor": float}`; `None` → kaynak yok (kitap yok ya da en iyi skor < `kaynak.ESIK = 0.45`). `kaynak.kitap_idleri(farabi_conn, sinif, ders) -> list[int]` (`dersler.ders_anahtari(kitap.ders) == ders`).
- Produces: `uretici.istem_kazanim(kazanim: dict, kaynak: dict) -> list[dict]`; `uretici.uret_kazanim(kazanim, kaynak, ollama_url=..., zaman_asimi=180) -> list[dict]` (sorular `ayristir` ile, `ders`/`sinif`/`kaynak` alanları dolu).

- [ ] **Step 1: Failing test**
```python
from unittest.mock import MagicMock

from soruhavuzu import kaynak, uretici

KAZ = {"id": 7, "sinif": 10, "ders": "matematik", "hafta": 5, "kod": "10.1.3", "metin": "10.1.3. Üçgenin alanı"}


def _farabi(kitaplar, parcalar):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.side_effect = [kitaplar, parcalar]
    return conn


class Gomucu:
    def encode(self, metinler, normalize_embeddings=True):
        return [[0.1] * 1024 for _ in metinler]


def test_kitap_yoksa_none():
    assert kaynak.bul(_farabi([(1, "Fizik")], []), Gomucu(), 10, "matematik", "x") is None


def test_dusuk_skor_none_yuksek_skor_birlesik_metin():
    dusuk = _farabi([(10, "Matematik")], [(1, 12, "a", 0.60)])      # mesafe 0.60 → skor 0.40
    assert kaynak.bul(dusuk, Gomucu(), 10, "matematik", "x") is None
    iyi = _farabi([(10, "Matematik")], [(1, 12, "alan formülü", 0.30), (2, 13, "üçgen", 0.35)])
    k = kaynak.bul(iyi, Gomucu(), 10, "matematik", "x")
    assert k["chunk_idler"] == [1, 2] and "alan formülü" in k["metin"] and abs(k["skor"] - 0.70) < 1e-9
    assert k["etiket"] == "Matematik 10, s. 12-13"


def test_istem_kazanimi_icerir():
    istem = uretici.istem_kazanim(KAZ, {"etiket": "Matematik 10, s. 12", "metin": "KAYNAK"})
    kullanici = istem[1]["content"]
    assert "KAZANIM: 10.1.3. Üçgenin alanı" in kullanici and "KAYNAK" in kullanici
    assert "bu kazanımı ölçmeli" in kullanici
```
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implementation** `kaynak.py`:
```python
"""soruhavuzu/kaynak.py — bir kazanım için ders kitabından en ilgili parçaları bulur (farabi DB, pgvector).
Gömme bilgehan bge-m3; RAG ile aynı `embedding <=> vektör` kalıbı (server/rag.py::_ilk_k_getir)."""

from soruhavuzu import dersler

ESIK = 0.45


def kitap_idleri(farabi_conn, sinif: int, ders: str) -> list[int]:
    with farabi_conn.cursor() as cur:
        cur.execute("SELECT id, ders FROM kitap WHERE sinif = %s", (sinif,))
        return [kid for kid, ad in cur.fetchall() if dersler.ders_anahtari(ad) == ders]


def bul(farabi_conn, gomucu, sinif: int, ders: str, kazanim_metin: str, k: int = 3) -> dict | None:
    idler = kitap_idleri(farabi_conn, sinif, ders)
    if not idler:
        return None
    v = list(map(float, gomucu.encode([kazanim_metin], normalize_embeddings=True)[0]))
    vektor = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
    with farabi_conn.cursor() as cur:
        cur.execute("SELECT id, sayfa_no, metin, embedding <=> %s::vector AS mesafe FROM chunk_egitim "
                    "WHERE kitap_id = ANY(%s) ORDER BY mesafe LIMIT %s", (vektor, idler, k))
        parcalar = cur.fetchall()
    if not parcalar or 1 - float(parcalar[0][3]) < ESIK:
        return None
    sayfalar = sorted({p[1] for p in parcalar})
    ad = ders.capitalize() if ders != "cografya" else "Coğrafya"
    aralik = f"{sayfalar[0]}" if len(sayfalar) == 1 else f"{sayfalar[0]}-{sayfalar[-1]}"
    return {"etiket": f"{ad} {sinif}, s. {aralik}", "metin": "\n\n".join(p[2] for p in parcalar),
            "chunk_idler": [p[0] for p in parcalar], "skor": 1 - float(parcalar[0][3])}
```
Not: testteki `_farabi` ilk `fetchall`'da `(id, ders)` döndürür; `kitap_idleri` `SELECT id, ders` sorgusu ile tutarlı. Etiket ders adı: `edebiyat` → "Edebiyat", `din` → "Din" kabul (yalnız görüntü).

`uretici.py`:
```python
def istem_kazanim(kazanim: dict, kaynak: dict) -> list[dict]:
    kullanici = (
        f"Ders: {kazanim['ders']}\nSınıf: {kazanim['sinif']}\nKaynak: {kaynak['etiket']}\n"
        f"KAZANIM: {kazanim['metin']}\n"
        "Görev: Bu kazanımı ölçen 5 çoktan seçmeli soru üret (zorluk 1-4 dağıt). Her soru bu kazanımı ölçmeli; "
        "kaynak metinde geçse de kazanımla ilgisiz bilgiyi sorma. 'konu' alanına kazanımın kısa adını yaz.\n"
        'Biçim: {"sorular": [{"konu": "...", "soru": "...", "kisa_cevap": "...", '
        '"secenekler": ["A", "B", "C", "D"], "dogru_index": 0, "zorluk": 1, "sayfa": 0}]}\n\n'
        f"KAYNAK METİN:\n{kaynak['metin']}"
    )
    return [{"role": "system", "content": SISTEM}, {"role": "user", "content": kullanici}]


def uret_kazanim(kazanim: dict, kaynak: dict, ollama_url: str = "http://127.0.0.1:11434",
                 zaman_asimi: float = 180) -> list[dict]:
    birim = {"tur": "kitap", "ders": kazanim["ders"], "sinif": kazanim["sinif"],
             "etiket": kaynak["etiket"], "metin": kaynak["metin"]}
    govde = {"model": MODEL, "messages": istem_kazanim(kazanim, kaynak), "stream": False,
             "think": False, "format": "json", "options": {"temperature": 0.4, "num_predict": 2048}}
    with httpx.Client(timeout=zaman_asimi, trust_env=False) as c:
        r = c.post(f"{ollama_url}/api/chat", json=govde)
        if r.status_code == 500:
            r = c.post(f"{ollama_url}/api/chat", json=govde)
        r.raise_for_status()
        return ayristir(r.json().get("message", {}).get("content", ""), birim)
```
(`ayristir(ham, birim)` mevcut; `birim` alanlarıyla `ders/sinif/kaynak` doldurduğunu Step 3 öncesi `uretici.ayristir`'i okuyarak doğrula; doldurmuyorsa sözlüğe ekle.)
- [ ] **Step 4: Run** → PASS; paket PASS.
- [ ] **Step 5: Commit** `"soruhavuzu: kazanım için kitap kaynağı bulucu + kazanım istemi"`

---

### Task 5: `calistir.uret` kazanım öncelikli döngü

**Files:** Modify `soruhavuzu/calistir.py:27-70`; Test `soruhavuzu/tests/test_calistir.py` (ek test)

**Interfaces:**
- Consumes: Task 1-4. `kazanimlar.haftalar(yol) -> dict[int, date]` (Task 1 dosyasına ekle: `{int(h): date.fromisoformat(t) for h, t in json["haftalar"].items()}`).
- Produces: `uret(conn, ders_saati_kontrol=True, sinif=None, farabi_conn=None, bulucu=kaynak.bul, ureten=uretici.uret_kazanim, bugun=None) -> None`.

- [ ] **Step 1: Failing test** (`test_calistir.py`'ye):
```python
def test_uret_kazanim_dongusu_kaydeder_ve_kaynak_yok_isaretler(conn, monkeypatch):
    from datetime import date
    from soruhavuzu import calistir, kazanimlar, tekrar, vt
    a = vt.kazanim_upsert(conn, {"sinif": 10, "ders": "matematik", "hafta": 5, "kod": None, "metin": "alan"})
    b = vt.kazanim_upsert(conn, {"sinif": 10, "ders": "matematik", "hafta": 5, "kod": None, "metin": "kaynaksız"})
    monkeypatch.setattr(kazanimlar, "haftalar", lambda *_: {5: date(2026, 10, 12)})
    monkeypatch.setattr(tekrar, "_gomucu", lambda: None)
    monkeypatch.setattr(tekrar.Eleyici, "yukle", lambda self, c: None)
    monkeypatch.setattr(tekrar.Eleyici, "kopya_mi", lambda self, d, s, q: False)
    monkeypatch.setattr(calistir, "denetle", lambda *a, **k: None)
    bulucu = lambda fc, g, sinif, ders, metin: None if metin == "kaynaksız" else {
        "etiket": "Matematik 10, s. 5", "metin": "M", "chunk_idler": [1], "skor": 0.8}
    sorular = [{"ders": "matematik", "sinif": 10, "konu": "alan", "soru": f"q{i}", "kisa_cevap": "x",
                "secenekler": ["a", "b", "c", "d"], "dogru_index": 0, "zorluk": 1,
                "kaynak": "Matematik 10, s. 5"} for i in range(5)]
    cagri = {"n": 0}

    def ureten(k, kay):
        cagri["n"] += 1
        return [dict(s, soru=f"{s['soru']}-{cagri['n']}") for s in sorular]
    calistir.uret(conn, ders_saati_kontrol=False, farabi_conn=object(), bulucu=bulucu, ureten=ureten,
                  bugun=date(2026, 10, 13))
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM soru WHERE kazanim_id=%s AND kazanim_kaynak='uretim'", (a,))
        assert cur.fetchone()[0] >= 10
        cur.execute("SELECT durum FROM kazanim WHERE id=%s", (b,))
        assert cur.fetchone()[0] == "kaynak_yok"
```
- [ ] **Step 2: Run** → FAIL (imza farklı).
- [ ] **Step 3: Implementation** — `uret`'in `while` gövdesini değiştir (eski `vt.siradaki_birim` döngüsü kalkar; `denetle` öncesi/sonrası korunur):
```python
def uret(conn, ders_saati_kontrol: bool = True, sinif: int | None = None, farabi_conn=None,
         bulucu=None, ureten=None, bugun=None) -> None:
    """2026-10-08: kazanım öncelikli — her soru bir kazanımla (spec soru-havuzu-kazanim-eslesmesi)."""
    bulucu = bulucu or kaynak.bul
    ureten = ureten or uretici.uret_kazanim
    gomucu = tekrar._gomucu()
    eleyici = tekrar.Eleyici(gomucu)
    eleyici.yukle(conn)
    farabi_conn = farabi_conn or psycopg2.connect(host="127.0.0.1", dbname="farabi", user="farabi")
    haftalar = kazanimlar.haftalar()
    denenen: dict[int, int] = {}
    if ders_saati_kontrol:
        denetle(conn, DENETIM_AZAMI_PAKET, DENETIM_AZAMI_DK, ders_saati_kontrol=True)
    while not ders_saati_kontrol or zaman.uretim_serbest():
        gun = bugun or zaman.bugun_istanbul()
        k = vt.siradaki_kazanim(conn, gun, haftalar, {i for i, n in denenen.items() if n >= 2})
        if k is not None and sinif is not None and k["sinif"] != sinif:
            denenen[k["id"]] = 2
            continue
        if k is None:
            print("[uret] bütün kazanımlar hedefte ya da denendi — denetim", flush=True)
            denetle(conn, ders_saati_kontrol=ders_saati_kontrol)
            return
        denenen[k["id"]] = denenen.get(k["id"], 0) + 1
        t0 = time.perf_counter()
        try:
            kay = bulucu(farabi_conn, gomucu, k["sinif"], k["ders"], k["metin"])
            if kay is None:
                vt.kazanim_isaretle(conn, k["id"], "kaynak_yok")
                print(f"[uret] kaynak yok: {k['sinif']} {k['ders']} — {k['metin'][:60]}", flush=True)
                continue
            bid = vt.birim_ekle(conn, "kitap", f"kazanim:{k['id']}:{','.join(map(str, kay['chunk_idler']))}",
                                k["ders"], k["sinif"], kay["etiket"], kay["metin"])
            if bid is None:  # aynı anahtar daha önce eklenmiş
                bid = vt.birim_bul(conn, f"kazanim:{k['id']}:{','.join(map(str, kay['chunk_idler']))}")
            eklenen = 0
            for s in ureten(k, kay):
                if not eleyici.kopya_mi(s["ders"], s["sinif"], s["soru"]):
                    vt.soru_ekle(conn, bid, s, kazanim_id=k["id"], kazanim_kaynak="uretim")
                    eklenen += 1
            print(f"[uret] {k['sinif']} {k['ders']} h{k['hafta']}: {eklenen} soru, "
                  f"{time.perf_counter() - t0:.0f} sn — {k['metin'][:50]}", flush=True)
        except Exception as e:  # noqa: BLE001 — tek kazanımın hatası geceyi durdurmasın
            conn.rollback()
            print(f"[uret] HATA kazanım {k['id']}: {type(e).__name__}: {e}", flush=True)
    print("[uret] ders saati penceresi — durduruldu", flush=True)
    if ders_saati_kontrol:
        denetle(conn, DENETIM_AZAMI_PAKET, DENETIM_AZAMI_DK, ders_saati_kontrol=True)
```
Eksik yardımcıları ekle: `zaman.bugun_istanbul()` (yoksa: `datetime.now(ZoneInfo("Europe/Istanbul")).date()`), `vt.birim_bul(conn, anahtar) -> int | None` (`SELECT id FROM kaynak_birim WHERE anahtar=%s`). Önce `zaman.py` ve `vt.birim_ekle`'yi oku (birim_ekle çakışmada None mı döner?) ve ona göre yaz.
- [ ] **Step 4: Run** → PASS; paket PASS.
- [ ] **Step 5: Commit** `"soruhavuzu: gece üretimi kazanım öncelikli (eski kitap-sayfası döngüsü kalktı)"`

---

### Task 6: Denetim istemine kazanım

**Files:** Modify `soruhavuzu/vt.py::DENETLENECEK_SQL`, `soruhavuzu/denetci.py::istem`; Test `soruhavuzu/tests/test_denetci.py`

- [ ] **Step 1: Failing test**
```python
def test_istem_kazanim_satiri_ve_kurali(conn):
    k = vt.kazanim_upsert(conn, {"sinif": 12, "ders": "matematik", "hafta": 1, "kod": "12.1", "metin": "12.1. Logaritma"})
    bid = vt.birim_ekle(conn, "kitap", "k:1", "matematik", 12, "E", "metin")
    vt.soru_ekle(conn, bid, ORNEK_SORU, kazanim_id=k, kazanim_kaynak="uretim")
    vt.soru_ekle(conn, bid, {**ORNEK_SORU, "soru": "eski?"})
    paket = vt.denetlenecekler(conn, 10)
    metin = denetci.istem(paket)
    assert "Kazanım: 12.1. Logaritma" in metin and "kazanım dışı" in metin
    assert metin.count("Kazanım:") == 1
```
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implementation** — `DENETLENECEK_SQL` seçimine `kz.metin AS kazanim_metin` + `LEFT JOIN kazanim kz ON kz.id = s.kazanim_id`; `istem()` soru bloğuna `(f"\n  Kazanım: {s['kazanim_metin']}" if s.get("kazanim_metin") else "")`; kurallara: `"Kazanımı belirtilmiş soru o kazanımı ölçmüyorsa GEÇERSİZ (neden: kazanım dışı). "`.
- [ ] **Step 4: Run** → PASS; paket PASS.
- [ ] **Step 5: Commit** `"soruhavuzu: AGY denetimi kazanım uyumunu da denetler"`

---

### Task 7: `kazanimtest` önce `kazanim_id`

**Files:** Modify `kazanimtest/secici.py::havuz_adaylari`; Test `kazanimtest/tests/test_secici.py` (varsa; yoksa oluştur — mevcut testlerin fixture desenini izle)

**Interfaces:**
- Consumes: `soru.kazanim_id`, `kazanim.metin`.
- Produces: `havuz_adaylari` yanıt şekli DEĞİŞMEZ; önce `kazanim_metin` ile eşleşen kazanımların onaylı soruları (benzerlik 1.0 sayılır, `kaynak="kazanim_id"` notu), eksik kalırsa eski benzerlik araması aynı listeye eklenir (tekrarsız).

- [ ] **Step 1:** Önce `kazanimtest/secici.py` ve testlerini oku; `havuz_adaylari(conn, duzey, ders, kvek, limit, model=None)` imzasını koruyacak failing test yaz: kazanım metniyle birebir eşleşen kazanıma bağlı 3 soru + ilgisiz 2 soru → ilk 3 aday kazanım_id'liler.
- [ ] **Step 2-4:** RED → implementasyon (`kazanim_metni` parametresi `adaylar()`'dan `havuz_adaylari`'na geçirilir; SQL: `SELECT ... FROM soru s JOIN kazanim k ON k.id=s.kazanim_id WHERE s.durum='onayli' AND k.sinif=%s AND k.ders=%s AND k.metin = ANY(%s)`, metinler `kazanim_metni.split("\n")`) → GREEN, `server/venv/bin/python -m pytest kazanimtest/tests -q` PASS.
- [ ] **Step 5: Commit** `"kazanimtest: havuz adayları önce kazanim_id ile"`

---

### Task 8: Canlıya alma + ölçüm + belgeler

- [ ] **Step 1:** `server/venv/bin/python -m soruhavuzu.calistir kur` (şema) → `kazanim-yukle --kuru` (çıktıyı oku: satır sayısı, eşlenemeyen dersler) → `kazanim-yukle`.
- [ ] **Step 2:** `HF_HUB_OFFLINE=1 server/venv/bin/python -m soruhavuzu.calistir etiketle --kuru` → çıktıyı (sınıf/ders başına etiketlenen/toplam) **kullanıcıya göster, onay al** → `etiketle`.
- [ ] **Step 3:** Ders saati DIŞINDA kısa deneme: `timeout 600 server/venv/bin/python -m soruhavuzu.calistir uret --sinif 10` → log'da `[uret] 10 matematik hX: N soru` satırları; `SELECT count(*) FROM soru WHERE kazanim_kaynak='uretim'` > 0.
- [ ] **Step 4:** `HF_HUB_OFFLINE=1 server/venv/bin/python -m benchmark.kazanim_kapsam` → "yeterli" sayısını 44 ile karşılaştır, kullanıcıya raporla.
- [ ] **Step 5:** `soruhavuzu/CLAUDE.md` (kazanım öncelikli üretim, yeni komutlar), kök `CLAUDE.md` zamanlanmış işler satırı, `DECISIONS.md` kaydı; commit + `git push origin master`.
