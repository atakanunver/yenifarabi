# Ders Planı Hattı (Faz A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kitap sayfalarından, ücretsiz bulut LLM'le (DeepSeek → Groq → Cohere), öğretmenin uygulayacağı 40 dakikalık ders planı üreten server endpoint'i + CLI; çıktılar Atakan'ın insan kontrolünden geçtikten sonra görüntüleme yüzeyi (Faz B) ayrı planla eklenecek.

**Architecture:** Yeni `server/ders_plani.py` modülü `icerik.py`'nin mevcut kitap/bölüm/sayfa çözümleme yardımcılarını yeniden kullanır, sayfa metnini toplar, `saglayicilar.metin_uret("ders_plani", ...)` ile yeni bir görev zincirinden plan ister, sonucu diskte önbelleğe alır. Kitaptan gelmesi gereken bölümlerde (1–2) kaynakta geçmeyen sayılar engellenmez, `kontrol_uyarilari` olarak döner. Client'a DOKUNULMAZ (Kural 3: tek modül — server).

**Tech Stack:** FastAPI (mevcut), `saglayicilar.py` OpenAI-uyumlu istemci (mevcut), pytest (server venv'inde kurulu). Yeni kütüphane YOK.

**Spec:** Bu dosyanın "Karar özeti" bölümü + `DECISIONS.md` 2026-09-29 "Kitap metni buluta gidebilir; …; ders planı için Ollama vs bulut ölçümü".

## Karar özeti (spec yerine)

- Kitap metni buluta gidebilir (kullanıcı kararı 2026-09-29). RAG soru-cevabı YEREL kalır — `rag.py`'ye dokunulmaz.
- Ölçüm (Fizik 10, PDF s. 14–22): qwen2.5:14b yetersiz (fizik hataları, 8k context'e sıkışma); deepseek-v4-flash en iyi (25,9 sn, 5873 çıktı token'ı, atıflar doğru); groq gpt-oss-120b iyi ve hızlı (6,2 sn); cohere yüzeysel; mistral ücretsiz katmanda 429.
- Bu hat RAG soru-cevabı DEĞİL: "≤3 cümle / sıcaklık ≤0,2 / kaynakta olmayan sayıyı gizle" kuralları burada geçerli değil. Onların yerine: atıf zorunlu, üretilen örnek etiketli, 1–2. bölümdeki kaynak dışı sayılar uyarı olarak döner.
- Grafik DEĞERLERİ ücretsiz görsel modellere okutulmaz (ölçüldü: pixtral doğrusal grafiğe "parabolik" dedi). Plan grafikleri kitap metnindeki anlatımdan tarif eder; değer için "kitaptaki grafikten kontrol edin".

## Global Constraints

- Sunucu venv'ine paket kurulmaz; yeni bağımlılık yok (Kural 8).
- `server/config/api_keys.json` anahtar kaynağıdır (`apikeys.env` değil); testler gerçek ağa/anahtara gitmez — `saglayicilar.metin_uret` / `_istemci` monkeypatch'lenir.
- Endpoint hiçbir koşulda 500 dönmez; hata `status="hata"` ile döner (mevcut `proxy.py` sözleşmesi).
- Router `auth.dogrula_tahta`'ya bağlı (her `/api/egitim/*` gibi).
- Sayfa numaraları **PDF sayfasıdır** (kitabın basılı numarası değil; fizik-10'da basılı = PDF − 1). Planda "(PDF s. N)" yazılır.
- Mevcut `saglayicilar` testlerindeki sahte istemcinin `create(model, messages)` imzası bozulmamalı: `timeout` yalnızca yeni görev için `create`'e geçer.
- Test komutu: `cd server && venv/bin/python -m pytest tests/ -q`.
- Kural 11: bu plan Opus'la yazıldı; uygulama Sonnet'le yapılır.

## Review Focus

1. **Konu, ünite adıyla eşleşmiyor** (ör. "Sabit Hızlı Hareket" vs ünite "KUVVET VE HAREKET") → `tema` verilmezse `bulunamadi` + "tema veya ilk_sayfa/son_sayfa verin" mesajı; 500 yok. (Task 2 testi: `test_tema_eslesmezse_bulunamadi_ve_llm_cagrilmaz`)
2. **Sağlayıcı zaman aşımı / 429 / hepsi düşer** → zincir sıradakine geçer, sonunda `status="hata"`, önbelleğe yazılmaz. (Task 2: `test_saglayici_hatasi_hata_doner_onbellege_yazmaz`)
3. **Elle verilen çok geniş sayfa aralığı** (ör. 20–200) → en fazla 12 sayfa alınır. (Task 2: `test_elle_aralik_12_sayfaya_kirpilir`)
4. **Model kitapta olmayan sayı yazıyor (1–2. bölüm)** → engellenmez, `kontrol_uyarilari`'na düşer; sayfa atıflarındaki sayılar uyarı üretmez. (Task 2: `TestKaynaktaOlmayanSayilar`)
5. **Aynı istek tekrar** → önbellekten, LLM çağrılmadan; `zorla=True` yeniden üretir. (Task 2: `test_onbellek_ve_zorla`)

Bilinen ve bu fazda ÇÖZÜLMEYEN sınır (insan kontrolünde görünecek): `yontem: gorsel` ünitelerde (ör. matematik_9 "Sayılar") metin katmanı kesir/üsleri dağıtıyor (`2\n1\n2\n1…`). Faz A bu ünitelerde zayıf plan üretebilir; çözüm (sayfa PNG → pixtral ile formül çıkarımı) insan kontrolü sonucuna göre ayrı planda.

---

### Task 1: `ders_plani` sağlayıcı zinciri + görev bazlı zaman aşımı

**Files:**
- Modify: `server/saglayicilar.py` (`GOREV_ZINCIRLERI` sözlüğüne ekleme; `_zinciri_dene` içinde `ekstra` satırı, ~satır 200)
- Test: `server/tests/test_saglayicilar.py` (dosya sonuna yeni sınıf)

**Interfaces:**
- Produces: `saglayicilar.GOREV_ZINCIRLERI["ders_plani"]` (Ollama İÇERMEZ), `saglayicilar.GOREV_ZAMAN_ASIMI_SN: dict[str, float]` (`{"ders_plani": 120.0}`); `metin_uret("ders_plani", istem, sistem) -> str` (imza değişmez).

- [ ] **Step 1: Failing test yaz** — `server/tests/test_saglayicilar.py` sonuna:

```python
class TestDersPlaniZinciri:
    """2026-09-29 ölçümü: qwen2.5:14b ders planında yetersiz (8k context'e
    sıkışıyor, fizik hataları) — zincirde BİLEREK yok. DeepSeek bir planı
    ~26 sn'de üretiyor; varsayılan 30 sn istemci zaman aşımı sınırda, bu
    görev 120 sn alır. Diğer görevlerin çağrı imzası değişmemeli."""

    def test_zincir_bulutla_baslar_ollama_icermez(self):
        zincir = sg.GOREV_ZINCIRLERI["ders_plani"]
        assert zincir[0] == ("deepseek", "deepseek-v4-flash")
        assert all(s != "ollama" for s, _ in zincir)

    def test_ders_plani_120_sn_zaman_asimi_gecirir(self, monkeypatch):
        gorulen = {}

        class _Kayitci:
            def __init__(self):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

            def _create(self, model, messages, **kw):
                gorulen.update(kw)
                return _sahte_yanit("plan")

        monkeypatch.setattr(sg, "_istemci", lambda saglayici: _Kayitci())
        assert sg.metin_uret("ders_plani", "istem", "sistem") == "plan"
        assert gorulen.get("timeout") == 120.0

    def test_diger_gorevlere_timeout_gecmez(self, monkeypatch):
        gorulen = {}

        class _Kayitci:
            def __init__(self):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

            def _create(self, model, messages, **kw):
                gorulen.update(kw)
                return _sahte_yanit("ok")

        monkeypatch.setitem(sg.GOREV_ZINCIRLERI, "test_gorev", [("groq", "m")])
        monkeypatch.setattr(sg, "_istemci", lambda saglayici: _Kayitci())
        sg.metin_uret("test_gorev", "istem")
        assert "timeout" not in gorulen
```

- [ ] **Step 2: Çalıştır, düştüğünü gör**

Run: `cd server && venv/bin/python -m pytest tests/test_saglayicilar.py::TestDersPlaniZinciri -v`
Expected: FAIL — `KeyError: 'ders_plani'` ve `timeout` yok.

- [ ] **Step 3: Minimal uygulama** — `GOREV_ZINCIRLERI` sözlüğünde `"soru_taslak"` girdisinden sonra:

```python
    "ders_plani": [
        # 2026-09-29 (DECISIONS.md): Fizik 10 s.14-22 ölçümü — deepseek en
        # iyi (25,9 sn, atıflar doğru), groq iyi+hızlı (6,2 sn), cohere
        # yüzeysel ama çalışıyor. Ollama BİLEREK yok: qwen2.5:14b 8k
        # context'e sıkışıp yarım ve fizik hatalı plan üretti; yanlış plan
        # hiç plandan kötü (status="hata" döner, öğretmen tekrar dener).
        ("deepseek", "deepseek-v4-flash"),
        ("groq",     "openai/gpt-oss-120b"),
        ("cohere",   "command-a-03-2025"),
    ],
```

Sözlüğün kapanışından hemen sonra:

```python
# Görev bazlı istek zaman aşımı (sn). `_istemci`'nin 30 sn varsayılanı kısa
# yanıtlar için ölçüldü; uzun çıktı üreten görevler burada genişletilir.
# `create(..., timeout=)` YALNIZCA listedeki görevlere geçer — diğer
# görevlerin çağrı imzası (ve test sahteleri) değişmez.
GOREV_ZAMAN_ASIMI_SN: dict[str, float] = {
    "ders_plani": 120.0,  # deepseek ölçülen 25,9 sn / ~5,9k çıktı token'ı
}
```

`_zinciri_dene` içinde `ekstra = {"temperature": 0.2} if saglayici == "ollama" else {}` satırının hemen altına:

```python
            if gorev in GOREV_ZAMAN_ASIMI_SN:
                ekstra["timeout"] = GOREV_ZAMAN_ASIMI_SN[gorev]
```

- [ ] **Step 4: Testleri çalıştır**

Run: `cd server && venv/bin/python -m pytest tests/test_saglayicilar.py -q`
Expected: tümü PASS (eski testler dahil).

- [ ] **Step 5: Ruff (yalnızca dokunulan dosya) + commit**

```bash
.venv-tools/bin/ruff check server/saglayicilar.py   # önceki bulgu sayısıyla karşılaştır, yeni bulgu olmamalı
git add server/saglayicilar.py server/tests/test_saglayicilar.py
git commit -m "server: ders_plani saglayici zinciri (deepseek>groq>cohere, ollama yok) + gorev bazli 120 sn zaman asimi"
```

---

### Task 2: `server/ders_plani.py` — kaynak toplama, istem, sayı kontrolü, önbellek, endpoint

**Files:**
- Create: `server/ders_plani.py`
- Modify: `server/main.py` (import listesine `import ders_plani`, router satırlarına `app.include_router(ders_plani.router)` — `proxy.router` satırının altına)
- Test: `server/tests/test_ders_plani.py`

**Interfaces:**
- Consumes (mevcut, `server/icerik.py`): `DATA_DIR`, `KITAP_PATH`, `_json_oku(Path)`, `_bolum_bul(kitaplar, tema, ders, sinif) -> (kitap, bolum) | None`, `_kitap_bul(ders, sinif, tercih_dosya=None) -> dict | None`, `_kitap_yolu_coz(kitap) -> Path`, `_ilgili_sayfalar(pdf, ilk, son, konu, adet) -> list[int]`, `_metin_cikar(pdf, sayfalar) -> (str, int)` (sayfaları `[s.N]` ile etiketler). Task 1'den: `saglayicilar.metin_uret("ders_plani", istem, sistem)`.
- Produces: `POST /api/egitim/ders_plani` (`PlanIstek` → `PlanYanit`), `ders_plani.kaynakta_olmayan_sayilar(plan: str, kaynak: str) -> list[str]`, `ders_plani.ders_plani_uret(istek: PlanIstek) -> PlanYanit` (Task 3'ün CLI'ı bunu çağırır).

- [ ] **Step 1: Failing testleri yaz** — `server/tests/test_ders_plani.py`:

```python
"""server/ders_plani.py — kitap sayfalarından 40 dk ders planı.

Ağ yok, gerçek sağlayıcı yok: `saglayicilar.metin_uret` monkeypatch'lenir.
Kitap indeksi/metni tmp_path'te sahte (test_icerik.py::TestPdfSayfaMetni
deseni). `icerik.SAYFA_ONBELLEK` ve `ders_plani.PLAN_ONBELLEK` de tmp_path'e
yönlendirilir — gerçek /mnt/farabi-data önbelleğine yazılmamalı."""

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ders_plani as dp  # noqa: E402
import icerik as ic  # noqa: E402
import saglayicilar  # noqa: E402

SAYFALAR = {
    "20": {"metin": "Sabit hızlı hareket: eşit zamanda eşit yer değiştirme. Hız 12 m/s.", "supheli": 0},
    "21": {"metin": "Sabit hızlı harekette ivme sıfırdır. x-t grafiği doğrudur.", "supheli": 0},
    "22": {"metin": "Örnek: 12 m / 4 s = 3 m/s. Sabit hızlı hareket.", "supheli": 1},
}


@pytest.fixture
def kitap(tmp_path, monkeypatch):
    (tmp_path / "kitaplar.json").write_text(json.dumps({"kitaplar": [{
        "dosya": "fizik-10.pdf", "ders": "fizik", "sinif": 10,
        "yol": str(tmp_path / "fizik-10.pdf"),
        "bolumler": [{"no": 1, "tur": "Ünite", "ad": "KUVVET VE HAREKET",
                      "ilk_sayfa": 20, "son_sayfa": 40, "yontem": "metin"}],
    }]}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "fizik-10.pdf").write_bytes(b"")
    (tmp_path / "fizik-10.json").write_text(json.dumps({"sayfalar": SAYFALAR}, ensure_ascii=False),
                                            encoding="utf-8")
    (tmp_path / "eslemeler").mkdir()
    monkeypatch.setattr(ic, "KITAP_PATH", tmp_path / "kitaplar.json")
    monkeypatch.setattr(ic, "METIN_DIZINI", tmp_path)
    monkeypatch.setattr(ic, "ESLEME_DIR", tmp_path / "eslemeler")
    monkeypatch.setattr(ic, "SAYFA_ONBELLEK", tmp_path / "_sayfa_secimi.json")
    monkeypatch.setattr(dp, "PLAN_ONBELLEK", tmp_path / "ders_plani")
    ic._METIN_ONBELLEK.clear()
    return tmp_path


@pytest.fixture
def llm(monkeypatch):
    cagrilar = []
    davranis = {"sonuc": "1. KAVRAMLAR\nHız 12 m/s (PDF s. 20)\n3. AKIŞ\n[ÜRETİLMİŞ ÖRNEK] 77 m"}

    def _sahte(gorev, istem, sistem=None):
        cagrilar.append((gorev, istem, sistem))
        if isinstance(davranis["sonuc"], Exception):
            raise davranis["sonuc"]
        return davranis["sonuc"]

    monkeypatch.setattr(saglayicilar, "metin_uret", _sahte)
    return cagrilar, davranis


def _istek(**kw):
    varsayilan = dict(ders="fizik", sinif="10", konu="Sabit Hızlı Hareket", tema="Kuvvet ve Hareket")
    varsayilan.update(kw)
    return dp.PlanIstek(**varsayilan)


class TestDersPlaniUret:
    def test_ok_kaynak_istemde_gorev_ders_plani(self, kitap, llm):
        cagrilar, _ = llm
        y = dp.ders_plani_uret(_istek())
        assert y.status == "ok"
        assert y.kitap == "fizik-10.pdf"
        assert y.sayfalar and all(20 <= s <= 40 for s in y.sayfalar)
        assert y.supheli_sembol == 1
        gorev, istem, sistem = cagrilar[0]
        assert gorev == "ders_plani"
        assert "eşit zamanda eşit yer değiştirme" in istem
        assert "[ÜRETİLMİŞ ÖRNEK]" in sistem

    def test_tema_eslesmezse_bulunamadi_ve_llm_cagrilmaz(self, kitap, llm):
        cagrilar, _ = llm
        y = dp.ders_plani_uret(_istek(tema=""))  # "Sabit Hızlı Hareket" ≠ "KUVVET VE HAREKET"
        assert y.status == "bulunamadi"
        assert "ilk_sayfa" in y.mesaj
        assert cagrilar == []

    def test_elle_aralik_12_sayfaya_kirpilir(self, kitap, llm):
        y = dp.ders_plani_uret(_istek(tema="", ilk_sayfa=20, son_sayfa=200))
        assert y.sayfalar == list(range(20, 32))

    def test_ters_aralik_bulunamadi(self, kitap, llm):
        y = dp.ders_plani_uret(_istek(ilk_sayfa=30, son_sayfa=20))
        assert y.status == "bulunamadi"

    def test_onbellek_ve_zorla(self, kitap, llm):
        cagrilar, _ = llm
        assert dp.ders_plani_uret(_istek()).onbellekten is False
        ikinci = dp.ders_plani_uret(_istek())
        assert ikinci.onbellekten is True and ikinci.status == "ok"
        assert len(cagrilar) == 1
        assert dp.ders_plani_uret(_istek(zorla=True)).onbellekten is False
        assert len(cagrilar) == 2

    def test_saglayici_hatasi_hata_doner_onbellege_yazmaz(self, kitap, llm):
        _, davranis = llm
        davranis["sonuc"] = RuntimeError("'ders_plani' görevi için hiçbir sağlayıcı yanıt vermedi")
        y = dp.ders_plani_uret(_istek())
        assert y.status == "hata" and "sağlayıcı" in y.mesaj
        assert not list((kitap / "ders_plani").rglob("*.json"))

    def test_kontrol_uyarilari_doner(self, kitap, llm):
        _, davranis = llm
        davranis["sonuc"] = "1. KAVRAMLAR\nHız 99 m/s (PDF s. 20)\n3. AKIŞ\n[ÜRETİLMİŞ ÖRNEK] 77"
        y = dp.ders_plani_uret(_istek())
        assert any("99" in u for u in y.kontrol_uyarilari)
        assert not any("77" in u for u in y.kontrol_uyarilari)


class TestKaynaktaOlmayanSayilar:
    def test_yalnizca_1_2_bolumdeki_kaynak_disi_sayilar(self):
        plan = ("# 1. KAVRAMLAR\nHız 12 m/s (PDF s. 22), ivme 0\n"
                "## 2. TAHTA TASARIMI\n| 99 | 3,6 |\n"
                "# 3. 40 DAKİKALIK AKIŞ\n00–05 ... [ÜRETİLMİŞ ÖRNEK] 77 m")
        kaynak = "[s.22]\n12 m / 4 s = 3 m/s, ortalama 3,6 m/s, ivme 0"
        assert dp.kaynakta_olmayan_sayilar(plan, kaynak) == ["99"]

    def test_bolum_3_yoksa_tum_plan_denetlenir(self):
        assert dp.kaynakta_olmayan_sayilar("Hız 5 m/s", "hız 12") == ["5"]


class TestEndpoint:
    def test_router_200_ve_auth_bagli(self, kitap, llm, monkeypatch):
        monkeypatch.setenv("FARABI_AUTH_REQUIRED", "0")
        app = FastAPI()
        app.include_router(dp.router)
        y = TestClient(app).post("/api/egitim/ders_plani", json={
            "ders": "fizik", "sinif": "10", "konu": "Sabit Hızlı Hareket", "tema": "Kuvvet ve Hareket"})
        assert y.status_code == 200 and y.json()["status"] == "ok"
        assert dp.router.dependencies, "router auth.dogrula_tahta'ya bağlı olmalı"
```

- [ ] **Step 2: Çalıştır, düştüğünü gör**

Run: `cd server && venv/bin/python -m pytest tests/test_ders_plani.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ders_plani'`.

- [ ] **Step 3: Uygulama** — `server/ders_plani.py`:

```python
"""server/ders_plani.py — kitap sayfalarından 40 dakikalık ders planı.

Karar ve ölçüm: DECISIONS.md 2026-09-29 (kitap metni buluta gidebilir;
Fizik 10 s.14-22'de qwen2.5:14b yetersiz, deepseek en iyi). Plan:
docs/superpowers/plans/2026-09-29-ders-plani-hatti.md.

RAG soru-cevabı (rag.py) DEĞİL: orada cevap ≤3 cümle, sıcaklık ≤0,2 ve
kaynakta olmayan sayı gizlenir. Bir ders planı çözümlü örnek içerdiği için
bu kurallar burada uygulanamaz; yerine:
  - kitaptan gelen her bilgi "(PDF s. N)" atıflı,
  - modelin ürettiği her örnek "[ÜRETİLMİŞ ÖRNEK]" etiketli,
  - kitaptan gelmesi gereken 1.–2. bölümde kaynakta geçmeyen sayılar
    ENGELLENMEZ, `kontrol_uyarilari` olarak öğretmene/insan kontrolüne döner.

Kitap/bölüm/sayfa çözümü icerik.py'nin yardımcılarıyla yapılır (ders_icerigi
ile aynı eşleşme — iki ayrı eşleştirme mantığı olmasın).
"""

import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import auth
import icerik
import saglayicilar

router = APIRouter(dependencies=[Depends(auth.dogrula_tahta)])

PLAN_ONBELLEK = icerik.DATA_DIR / "icerik" / "ders_plani"
MAX_SAYFA = 12
KAYNAK_MAX_KARAKTER = 40_000  # ölçülen 9 sayfa ≈ 15,6k karakter; deepseek context'i geniş
ISTEM_SURUMU = "1"            # SISTEM/GOREV değişince artır → eski önbellek kullanılmaz

SISTEM = """Sen Türkiye'de MEB müfredatıyla ders veren deneyimli bir öğretmen ve ders planı yazarısın. Yalnızca Türkçe yaz.
KURALLAR:
1. Kavram, tanım, formül ve sayısal değerleri YALNIZCA <kaynak> içindeki kitap metninden al; her birinin yanına (PDF s. N) yaz. Kaynaktaki [s.N] etiketleri PDF sayfa numarasıdır.
2. Kaynakta olmayan bir formül veya tanım gerekiyorsa yazma; "Kitapta yok — öğretmen ekleyebilir" de.
3. Kendi ürettiğin her örnek soru ve sayının başına [ÜRETİLMİŞ ÖRNEK] yaz.
4. Kaynak metin PDF'ten çıkarıldı; semboller bozuk olabilir (ör. hız sembolü ϑ yerine 'c', kesir ve üsler satırlara dağılmış). Emin olmadığın sembolü veya formülü tahmin etme, "sembolü kitaptan kontrol edin" yaz.
5. Grafikleri kitap metnindeki anlatımdan tarif et; grafik üzerindeki sayısal değerleri metinde yoksa uydurma, "değerleri kitaptaki grafikten kontrol edin" yaz.
6. Formülleri LaTeX ($...$), tabloları Markdown ile yaz."""

GOREV = """<kaynak kitap="{kitap}" sayfalar="{sayfalar}" supheli_sembol="{supheli}">
{metin}
</kaynak>
Ders / sınıf: {ders} {sinif}
Konu: {konu}
Kazanım(lar): {kazanim}
Öğretmen taslağı: {taslak}

Aşağıdaki 4 başlığı AYNEN bu sırayla ve bu numaralarla üret:
1. KAVRAMLAR VE FORMÜL ANALİZİ — terim: tanım (PDF s. N); formüller $LaTeX$ + birim analizi (SI).
2. TAHTA TASARIMI — (a) Markdown tablo; (b) grafik: X/Y ekseni+birim, eğri türü, eğimin/alanın fiziksel anlamı.
3. 40 DAKİKALIK AKIŞ — 00–05 giriş sorusu | 05–20 kavramsal inşa, formülün adım adım çıkarılışı | 20–30 grafik yorumu + 1–2 aşamalı [ÜRETİLMİŞ ÖRNEK] çözüm | 30–37 sınıf içi pratik + en az 2 kavram yanılgısı | 37–40 iki cümlelik özet + sonraki derse ipucu sorusu.
4. REDAKSİYON — taslak varsa düzeltilmiş metin + kritik iyileştirmeler listesi; yoksa "Taslak verilmedi."
"""


class PlanIstek(BaseModel):
    ders: str = Field(..., min_length=1, max_length=60)
    sinif: str | None = None
    konu: str = Field(..., min_length=2, max_length=200)
    # Ünite/tema adı — konu ünite adıyla eşleşmiyorsa (ör. "Sabit Hızlı
    # Hareket" ⊂ "KUVVET VE HAREKET") kitap bölümü bununla bulunur.
    tema: str = Field(default="", max_length=200)
    kazanim: str = Field(default="", max_length=2000)
    taslak: str = Field(default="", max_length=20_000)
    ilk_sayfa: int | None = Field(default=None, ge=1)
    son_sayfa: int | None = Field(default=None, ge=1)
    sayfa_adedi: int = Field(default=9, ge=1, le=MAX_SAYFA)
    zorla: bool = False


class PlanYanit(BaseModel):
    status: str  # "ok" | "bulunamadi" | "hata"
    plan: str | None = None
    mesaj: str | None = None
    kitap: str | None = None
    sayfalar: list[int] = []
    supheli_sembol: int = 0
    kontrol_uyarilari: list[str] = []
    onbellekten: bool = False
    latency_ms: int
    request_id: str


_SAYI_RE = re.compile(r"\d+(?:[.,]\d+)?")
_BOLUM3_RE = re.compile(r"^\W*3\s*\.\s", re.MULTILINE)
_BASLIK_RE = re.compile(r"^\W*[12]\s*\.\s.*$", re.MULTILINE)
_ATIF_RE = re.compile(r"(?:PDF\s*)?s\.\s*\d+(?:\s*[-–]\s*\d+)?")


def kaynakta_olmayan_sayilar(plan: str, kaynak: str) -> list[str]:
    """1.–2. bölümde (kitaptan gelmesi gereken kısım) kaynakta geçmeyen
    sayılar. Başlık numaraları ve sayfa atıfları sayılmaz. Engellemez —
    yalnızca insan kontrolü için listeler (rag.py'nin sayı kontrolünün
    ders planına uyarlanmış, yumuşak hâli)."""
    m = _BOLUM3_RE.search(plan)
    kitap_kismi = plan[:m.start()] if m else plan
    kitap_kismi = _ATIF_RE.sub(" ", _BASLIK_RE.sub(" ", kitap_kismi))
    kaynak_sayilari = {n.replace(",", ".") for n in _SAYI_RE.findall(_ATIF_RE.sub(" ", kaynak))}
    eksik: list[str] = []
    for n in _SAYI_RE.findall(kitap_kismi):
        k = n.replace(",", ".")
        if k not in kaynak_sayilari and n not in eksik:
            eksik.append(n)
    return eksik


def _kaynak_topla(istek: PlanIstek) -> tuple[dict, list[int], str, int] | str:
    """(kitap, sayfalar, metin, supheli) ya da kullanıcıya dönecek mesaj."""
    kitaplar = icerik._json_oku(icerik.KITAP_PATH)
    if kitaplar is None:
        return "Kitap indeksi bulunamadı (icerik/kitaplar.json)."
    ders = istek.ders.strip() or None
    sinif = istek.sinif.strip() if istek.sinif else None

    if istek.ilk_sayfa is not None and istek.son_sayfa is not None:
        if istek.son_sayfa < istek.ilk_sayfa:
            return "son_sayfa, ilk_sayfa'dan küçük olamaz."
        kitap = icerik._kitap_bul(ders, sinif)
        if not kitap:
            return f"Kitap bulunamadı: {istek.ders} {sinif or ''}".strip()
        son = min(istek.son_sayfa, istek.ilk_sayfa + MAX_SAYFA - 1)
        sayfalar = list(range(istek.ilk_sayfa, son + 1))
        pdf = icerik._kitap_yolu_coz(kitap)
    else:
        eslesme = icerik._bolum_bul(kitaplar, istek.tema.strip() or istek.konu, ders, sinif)
        if not eslesme:
            return (f"Kitap bölümü eşleşmedi: {istek.tema or istek.konu}. "
                    "Ünite adını 'tema' ile ya da sayfa aralığını ilk_sayfa/son_sayfa ile verin.")
        kitap, bolum = eslesme
        pdf = icerik._kitap_yolu_coz(kitap)
        sayfalar = icerik._ilgili_sayfalar(pdf, bolum["ilk_sayfa"], bolum["son_sayfa"],
                                           istek.konu, istek.sayfa_adedi)

    if not pdf.exists():
        return f"Kitap dosyası bulunamadı: {pdf.name}."
    metin, supheli = icerik._metin_cikar(pdf, sayfalar)
    if not metin.strip():
        return f"{pdf.name} s.{sayfalar[0]}-{sayfalar[-1]} boş döndü."
    if len(metin) > KAYNAK_MAX_KARAKTER:
        metin = metin[:KAYNAK_MAX_KARAKTER].rsplit("\n", 1)[0] + "\n…(kesildi)"
    return kitap, sayfalar, metin, supheli


def _onbellek_yolu(kitap_dosya: str, sayfalar: list[int], istek: PlanIstek) -> Path:
    anahtar = json.dumps([ISTEM_SURUMU, kitap_dosya, sayfalar, istek.konu,
                          istek.kazanim, istek.taslak], ensure_ascii=False)
    ozet = hashlib.sha256(anahtar.encode("utf-8")).hexdigest()[:16]
    return PLAN_ONBELLEK / Path(kitap_dosya).stem / f"{ozet}.json"


def ders_plani_uret(istek: PlanIstek) -> PlanYanit:
    t0 = time.perf_counter()
    request_id = str(uuid.uuid4())

    def _bitir(status: str, **alanlar) -> PlanYanit:
        return PlanYanit(status=status, latency_ms=int((time.perf_counter() - t0) * 1000),
                         request_id=request_id, **alanlar)

    try:
        kaynak = _kaynak_topla(istek)
    except Exception as e:
        return _bitir("hata", mesaj=f"Kitap içeriği okunamadı ({type(e).__name__}: {e}).")
    if isinstance(kaynak, str):
        return _bitir("bulunamadi", mesaj=kaynak)
    kitap, sayfalar, metin, supheli = kaynak
    ortak = {"kitap": kitap.get("dosya"), "sayfalar": sayfalar, "supheli_sembol": supheli}

    yol = _onbellek_yolu(kitap.get("dosya", ""), sayfalar, istek)
    if not istek.zorla and yol.exists():
        try:
            k = json.loads(yol.read_text(encoding="utf-8"))
            return _bitir("ok", plan=k["plan"], kontrol_uyarilari=k.get("kontrol_uyarilari", []),
                          onbellekten=True, **ortak)
        except Exception:
            pass  # bozuk önbellek → yeniden üret

    istem = GOREV.format(kitap=kitap.get("dosya"), sayfalar=f"{sayfalar[0]}-{sayfalar[-1]}",
                         supheli=supheli, metin=metin, ders=istek.ders, sinif=istek.sinif or "",
                         konu=istek.konu, kazanim=istek.kazanim or "belirtilmedi",
                         taslak=istek.taslak or "yok")
    try:
        plan = saglayicilar.metin_uret("ders_plani", istem, SISTEM)
    except Exception as e:
        return _bitir("hata", mesaj=f"Plan üretilemedi ({type(e).__name__}: {e}).", **ortak)

    uyarilar = [f"Kaynakta geçmeyen sayı (1.–2. bölüm): {n}"
                for n in kaynakta_olmayan_sayilar(plan, metin)]
    try:
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(json.dumps({
            "plan": plan, "kontrol_uyarilari": uyarilar, "sayfalar": sayfalar,
            "konu": istek.konu, "olusturma": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass  # önbellek yazılamazsa plan yine döner
    return _bitir("ok", plan=plan, kontrol_uyarilari=uyarilar, **ortak)


@router.post("/api/egitim/ders_plani", response_model=PlanYanit)
def ders_plani_endpoint(istek: PlanIstek) -> PlanYanit:
    return ders_plani_uret(istek)
```

Not — `icerik._kitap_bul(ders, sinif, tercih_dosya=None)` (`server/icerik.py:465`) `KITAP_PATH`'i kendisi okur (2026-09-29 doğrulandı). Çok ciltli derste (`matematik_9.pdf` / `matematik_9_2.pdf`) elle aralık verilince İLK cildi seçer; cilt seçimi Faz A'da yok, konu ile `tema` yolu (`_bolum_bul`) doğru cildi bulur.

`server/main.py`'de: `import proxy` satırının altına `import ders_plani`; `app.include_router(proxy.router)` satırının altına `app.include_router(ders_plani.router)`.

- [ ] **Step 4: Testleri çalıştır**

Run: `cd server && venv/bin/python -m pytest tests/test_ders_plani.py -v && venv/bin/python -m pytest tests/ -q`
Expected: yeni testler PASS; tüm paket PASS (önceki sayı + yeni testler).

- [ ] **Step 5: Ruff + commit**

```bash
.venv-tools/bin/ruff check server/ders_plani.py server/main.py
git add server/ders_plani.py server/main.py server/tests/test_ders_plani.py
git commit -m "server: POST /api/egitim/ders_plani - kitap sayfalarindan 40 dk ders plani (bulut), onbellek, kaynak disi sayi uyarisi"
```

---

### Task 3: CLI, üretime alma, insan kontrolü için örnek planlar, belgeler

**Files:**
- Modify: `server/ders_plani.py` (dosya sonuna `__main__` bloğu)
- Modify: `CLAUDE.md` (`server/` bölümüne endpoint satırı), `DECISIONS.md` (yeni kayıt)

**Interfaces:**
- Consumes: Task 2'den `PlanIstek`, `ders_plani_uret`.
- Produces: `cd server && venv/bin/python ders_plani.py --ders ... --konu ... [--tema ...] [--kazanim ...] [--ilk N --son M] [--zorla] [--cikti yol.md]`.

- [ ] **Step 1: CLI ekle** — `server/ders_plani.py` sonuna:

```python
if __name__ == "__main__":
    # İnsan kontrolü için elle üretim: auth'u atlar (router bağımlılığı değil,
    # fonksiyon doğrudan çağrılır), anahtarları config/api_keys.json'dan okur.
    import argparse

    ap = argparse.ArgumentParser(description="Kitap sayfalarından 40 dk ders planı üret.")
    ap.add_argument("--ders", required=True)
    ap.add_argument("--sinif")
    ap.add_argument("--konu", required=True)
    ap.add_argument("--tema", default="")
    ap.add_argument("--kazanim", default="")
    ap.add_argument("--ilk", type=int)
    ap.add_argument("--son", type=int)
    ap.add_argument("--zorla", action="store_true")
    ap.add_argument("--cikti", type=Path, help="Planı bu .md dosyasına da yaz")
    a = ap.parse_args()
    y = ders_plani_uret(PlanIstek(ders=a.ders, sinif=a.sinif, konu=a.konu, tema=a.tema,
                                  kazanim=a.kazanim, ilk_sayfa=a.ilk, son_sayfa=a.son, zorla=a.zorla))
    print(f"status={y.status} kitap={y.kitap} sayfalar={y.sayfalar} supheli={y.supheli_sembol} "
          f"onbellekten={y.onbellekten} sure={y.latency_ms} ms")
    for u in y.kontrol_uyarilari:
        print("UYARI:", u)
    if y.status != "ok":
        print(y.mesaj)
        raise SystemExit(1)
    if a.cikti:
        baslik = f"<!-- {y.kitap} PDF s.{y.sayfalar[0]}-{y.sayfalar[-1]} | {a.konu} -->\n\n"
        a.cikti.write_text(baslik + y.plan, encoding="utf-8")
        print("yazıldı:", a.cikti)
    else:
        print(y.plan)
```

- [ ] **Step 2: Testler + üretime alma**

```bash
cd server && venv/bin/python -m pytest tests/ -q
sudo systemctl restart farabi-api.service
sleep 20 && curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/health   # 200 beklenir
journalctl -u farabi-api.service -n 30 --no-pager | grep -iE "error|traceback" || echo "temiz"
```

- [ ] **Step 3: İnsan kontrolü için 3 örnek plan üret** (çıktılar `docs/ders_plani_ornek/`, commit'lenir — kitap alıntısı içerir, kitaplar halka açık kararı gereği sorun değil):

```bash
mkdir -p docs/ders_plani_ornek && cd server
# 1) Ölçümle aynı aralık — karşılaştırma için
venv/bin/python ders_plani.py --ders fizik --sinif 10 --konu "Sabit Hızlı Hareket" \
  --kazanim "Yatay doğrultuda sabit hızlı hareketi açıklar; konum-zaman ve hız-zaman grafiklerini yorumlar." \
  --ilk 14 --son 22 --cikti ../docs/ders_plani_ornek/fizik10-sabit-hizli-hareket-elle.md
# 2) Otomatik sayfa seçimi (tema ile)
venv/bin/python ders_plani.py --ders fizik --sinif 10 --konu "Serbest Düşme" --tema "Kuvvet ve Hareket" \
  --cikti ../docs/ders_plani_ornek/fizik10-serbest-dusme-otomatik.md
# 3) Bozuk metin katmanı stres testi (yontem: gorsel ünite)
venv/bin/python ders_plani.py --ders matematik --sinif 9 --konu "Gerçek Sayıların Üslü Gösterimleri" \
  --tema "Sayılar" --cikti ../docs/ders_plani_ornek/matematik9-uslu-gosterimler.md
```

Her komutun `status=ok` ve `sayfalar=` çıktısını kaydet. `status=bulunamadi` dönerse mesajdaki öneriyle (`--ilk/--son`) tekrar dene ve bunu rapora yaz.

- [ ] **Step 4: Belgeler + commit**

`CLAUDE.md` → `### server/` altında `saglayicilar.py + proxy.py` maddesinden sonra:

```markdown
- `ders_plani.py` — `POST /api/egitim/ders_plani` (+ CLI: `venv/bin/python
  ders_plani.py --ders fizik --sinif 10 --konu ... [--tema ...|--ilk N --son M]`).
  Kitap sayfalarından 40 dk ders planı; `ders_plani` zinciri (deepseek →
  groq → cohere, Ollama BİLEREK yok), görev zaman aşımı 120 sn. RAG DEĞİL:
  atıf zorunlu, üretilen örnek etiketli, 1.–2. bölümdeki kaynak dışı sayılar
  `kontrol_uyarilari`. Önbellek `icerik/ders_plani/`. Görüntüleme yüzeyi
  (Faz B) insan kontrolünden sonra.
```

`DECISIONS.md` başına:

```markdown
## 2026-09-29 - Ders planı hattı (Faz A): POST /api/egitim/ders_plani
- Ne yapıldı: server/ders_plani.py + saglayicilar `ders_plani` zinciri (deepseek>groq>cohere, Ollama yok) + görev bazlı 120 sn zaman aşımı; CLI; örnekler docs/ders_plani_ornek/.
- Neden: 2026-09-29 ölçümünde qwen2.5:14b yetersiz; RAG kurallarıyla (≤3 cümle, sayı gizleme) çözümlü örnekli plan üretilemez → ayrı hat, yumuşak sayı kontrolü. Bilinen sınır: `yontem: gorsel` ünitelerde metin katmanı bozuk (matematik_9); Faz B/C kararı insan kontrolüne göre.
```

```bash
git add server/ders_plani.py CLAUDE.md DECISIONS.md docs/ders_plani_ornek/
git commit -m "server: ders_plani CLI, ornek planlar (insan kontrolu), belgeler"
git push origin master
```

- [ ] **Step 5: İNSAN KONTROLÜ KAPISI — burada DUR.** Atakan `docs/ders_plani_ornek/` altındaki 3 planı okur ve şunlara karar verir:
  1. Fizik planları doğru ve uygulanabilir mi? (atıflar, formüller, kavram yanılgıları)
  2. Matematik 9 planı kullanılabilir mi, yoksa `gorsel` ünitelerde sayfa PNG → pixtral formül çıkarımı (Faz C) gerekli mi?
  3. Faz B görüntüleme yüzeyi: (a) tahta panelinde "DERS PLANI" düğmesi, (b) öğretmen paneli (dashboard, HTTP+HMAC köprüsü), (c) yazdırılabilir çıktı. Tahta arayüzü LaTeX/Markdown göstermiyor — seçim buna göre.

Faz B/C ayrı plan olarak yazılır; bu plan burada biter.
