# Ekran Özeti (`ekrani_ozetle`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Öğretmen tahtada açık sayfa için "özetle/anlat" deyince ekran görüntüsü → bulut OCR → yerel Ollama özeti → panel + sesli anlatım.

**Architecture:** Sunucuda yeni bir router (`server/ekran_ozet.py`, `POST /api/egitim/ekran_ozet`) iki adımı yürütür: `saglayicilar.gorsel_uret("gorsel", …)` ile OCR, yeni `"ekran_ozet"` görev zinciriyle (`ollama/farabi-qwen3.8:27b` → deepseek → groq) özet. Tahtada yeni arka plan aracı (`client/actions/ekrani_ozetle.py`) ekranı mevcut `_screenshot_sig` yoluyla yakalar, sunucuya yollar, sonucu `show_content("ÖZET", …)` + `speak("[ÖZET] …")` ile iletir.

**Tech Stack:** FastAPI (server, `farabi-api`), PyQt6 + requests (client), mevcut `saglayicilar` sağlayıcı zinciri (OpenAI uyumlu istemci), pytest.

**Spec:** `docs/superpowers/specs/2026-10-03-ekran-ozeti-design.md`

## Global Constraints

- Uç: `POST /api/egitim/ekran_ozet`, `auth.dogrula_tahta`'ya bağlı; `durum["hazir"]`'a (RAG) bağlı DEĞİL.
- Girdi: `resim` (UploadFile, üst sınır **8 MB**) + `mod` ∈ {`"ozet"`, `"anlat"`}, varsayılan `"ozet"`.
- Yanıt: `{status, answer, latency_ms, request_id}`; `status ∈ {ok, okunamadi, mesgul, hata}`. Ham OCR metni ve hata ayrıntısı yanıtta YOK (yalnızca journal).
- OCR eşiği: `OKUNAMADI_ESIK = 80` karakter (boşluklar hariç).
- Zincir: `GOREV_ZINCIRLERI["ekran_ozet"] = [("ollama", "farabi-qwen3.8:27b"), ("deepseek", "deepseek-v4-flash"), ("groq", "openai/gpt-oss-120b")]`, `GOREV_ZAMAN_ASIMI_SN["ekran_ozet"] = 60.0`.
- `ozet` kipi 5–8 madde; `anlat` kipi ~250–400 kelime, madde yok; ikisinde de "yalnızca bu metne dayan, ekleme yapma", Türkçe.
- Sınıf düzeyi `TahtaKimligi.derslik`'in baştaki sayısından (9–12); çözülemezse düzey verilmez.
- Aynı `derslik`'ten süren istek varken ikinci istek → `mesgul`.
- İçerik kalıcı saklanmaz (DB/dosya yok).
- Client POST zaman aşımı **90 sn**; yakalama bekleme 6 sn (`CTX_BEKLEME_SN`).
- Tahtada hiçbir durumda tam ekran hata yok; hata → tek kısa cümle, panel açılmaz (Kural 2).
- Client kodu tahtaya yalnızca GitHub üzerinden gider; client testleri `farabi.local`'da koşmaz (venv yok), tahtada koşulur.
- Push ve servis restart'ı kullanıcı onayıyla (bu oturumda commit onayı var, push onayı yok).

## Review Focus

1. **Sunucu sağlayıcı çağrısı olay döngüsünü kilitlemesin** — OCR+özet 15–30 sn sürer; `async` uçta senkron çağrılırsa `farabi-api` o sürede tüm tahtalara cevap veremez. Beklenen: diğer uçlar (ör. `/health`) bu sürede yanıt verir. → Task 2'de `run_in_threadpool` + test.
2. **Hata sonrası `mesgul` kilidinin bırakılması** — OCR ya da özet istisna fırlatırsa aynı tahta bir daha hiç özet alamamamalı değil. Beklenen: hatadan sonraki istek normal işlenir. → Task 2 testi.
3. **8 MB üstü görüntü** (yüksek çözünürlüklü tahta ekranı) — 500 değil `status="hata"`, sağlayıcıya gidilmez. → Task 2 testi.
4. **Sunucu `ok` ama boş `answer`** ya da JSON olmayan/401 yanıt — tahta paneli boş açmasın, kısa cümle söylesin. → Task 3 testi.
5. **`derslik` biçimleri** — `"10-A"` → 10, `"9-B"` → 9, `"fenlab"` → None, auth kapalı (`kimlik=None`) → None; düzey yoksa istemde "N. sınıf" geçmesin. → Task 2 testi.

---

## Dosya yapısı

| Dosya | Sorumluluk |
|---|---|
| `server/saglayicilar.py` (değişir) | `"ekran_ozet"` zinciri + 60 sn görev zaman aşımı |
| `server/ekran_ozet.py` (yeni) | router: yükleme sınırı, OCR, eşik, sistem istemi, eşzamanlılık kilidi, yanıt |
| `server/main.py` (değişir) | `import ekran_ozet` + `app.include_router(ekran_ozet.router)` |
| `server/tests/test_saglayicilar.py` (değişir) | zincir testi |
| `server/tests/test_ekran_ozet.py` (yeni) | uç testleri (ağsız, sahte sağlayıcı) |
| `client/actions/ekrani_ozetle.py` (yeni) | araç: yakalama, POST, sonuç/hata iletimi |
| `client/tests/test_ekrani_ozetle.py` (yeni) | araç testleri (ağsız) |
| `client/actions/kayit.py` (değişir) | `Arac(ad="ekrani_ozetle", …)` |
| `client/main.py` (değişir) | import + `elif name == "ekrani_ozetle"` arka plan dalı |
| `server/CLAUDE.md`, `client/CLAUDE.md`, `CLAUDE.md`, `DECISIONS.md` | uç tablosu, araç listesi, gizlilik sınırı notu, karar kaydı |

---

### Task 1: `"ekran_ozet"` görev zinciri

**Files:**
- Modify: `server/saglayicilar.py` (`GOREV_ZINCIRLERI` sözlüğü, `"ders_plani"` girdisinden sonra; `GOREV_ZAMAN_ASIMI_SN` sözlüğü)
- Test: `server/tests/test_saglayicilar.py`

**Interfaces:**
- Produces: `saglayicilar.GOREV_ZINCIRLERI["ekran_ozet"]`, `saglayicilar.GOREV_ZAMAN_ASIMI_SN["ekran_ozet"] == 60.0`. Task 2 bunu `saglayicilar.metin_uret("ekran_ozet", istem, sistem=...)` ile kullanır.

- [ ] **Step 1: Failing test** — `server/tests/test_saglayicilar.py` sonuna:

```python
class TestEkranOzetZinciri:
    """2026-10-03 ekran özeti: yerel model birinci (kitap metni, ücretsiz),
    Ollama düşerse bulut metin yedeği; OCR+özet uzun sürdüğü için 60 sn."""

    def test_ollama_birinci_bulut_yedekli(self):
        zincir = sg.GOREV_ZINCIRLERI["ekran_ozet"]
        assert zincir[0] == ("ollama", "farabi-qwen3.8:27b")
        assert ("deepseek", "deepseek-v4-flash") in zincir
        assert ("groq", "openai/gpt-oss-120b") in zincir

    def test_zaman_asimi_60_sn(self):
        assert sg.GOREV_ZAMAN_ASIMI_SN["ekran_ozet"] == 60.0
```

- [ ] **Step 2: Fail doğrula** — Run: `cd server && venv/bin/python -m pytest tests/test_saglayicilar.py::TestEkranOzetZinciri -q` → Expected: FAIL (`KeyError: 'ekran_ozet'`).

- [ ] **Step 3: Uygula** — `GOREV_ZINCIRLERI`'de `"ders_plani": [...]` girdisinin kapanışından sonra:

```python
    "ekran_ozet": [
        # 2026-10-03 (docs/superpowers/specs/2026-10-03-ekran-ozeti-design.md):
        # tahtadaki sayfanın OCR metnini özetler. Yerel model birinci (kitap
        # metni ücretsiz işlensin), Ollama düşerse bulut metin yedeği.
        ("ollama",   "farabi-qwen3.8:27b"),
        ("deepseek", "deepseek-v4-flash"),
        ("groq",     "openai/gpt-oss-120b"),
    ],
```

`GOREV_ZAMAN_ASIMI_SN`'ye:

```python
    "ekran_ozet": 60.0,  # "anlat" kipi ~400 kelime; Ollama 27-31 tok/s + ilk istem işleme
```

- [ ] **Step 4: Geç doğrula** — Run: `cd server && venv/bin/python -m pytest tests/test_saglayicilar.py -q` → Expected: hepsi PASS.

- [ ] **Step 5: Commit**

```bash
git add server/saglayicilar.py server/tests/test_saglayicilar.py
git commit -m "server: ekran_ozet gorev zinciri (ollama > deepseek > groq, 60 sn)"
```

---

### Task 2: `POST /api/egitim/ekran_ozet` router'ı

**Files:**
- Create: `server/ekran_ozet.py`
- Modify: `server/main.py` (import bloğu ~satır 25-35; `app.include_router(...)` bloğu ~satır 113-123)
- Test: `server/tests/test_ekran_ozet.py`
- Docs: `server/CLAUDE.md` uç tablosuna satır

**Interfaces:**
- Consumes: `saglayicilar.gorsel_uret(gorev, istem, resim_bytes, mime) -> str`, `saglayicilar.metin_uret(gorev, istem, sistem=None) -> str` (Task 1 zinciri), `auth.dogrula_tahta`, `auth.TahtaKimligi(derslik: str)`.
- Produces: HTTP `POST /api/egitim/ekran_ozet` (multipart `resim`, form `mod`) → JSON `{status, answer, latency_ms, request_id}`. Modül fonksiyonları: `duzey_coz(derslik: str | None) -> int | None`, `sistem_istemi(mod: str, duzey: int | None) -> str`.

- [ ] **Step 1: Failing tests** — `server/tests/test_ekran_ozet.py`:

```python
"""
server/ekran_ozet.py — ekran görüntüsü → OCR → özet hattının sözleşmesi.

Ağ yok: `saglayicilar.gorsel_uret`/`metin_uret` monkeypatch'lenir. Yalnızca
ekran_ozet router'ı bağlı küçük bir app (main.app lifespan'ı tetiklenmesin —
test_proxy.py ile aynı desen).
"""

import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth
import ekran_ozet
import saglayicilar

OCR_METNI = "Hücre zarı fosfolipit çift katmandan oluşur. " * 5  # > 80 karakter


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setenv("FARABI_AUTH_REQUIRED", "1")
    monkeypatch.setattr(auth, "_board_keys", lambda: {"10-A": "a10", "fenlab": "afen"})
    ekran_ozet._SURENLER.clear()
    app = FastAPI()
    app.include_router(ekran_ozet.router)

    @app.get("/health")
    def _health():
        return {"status": "ok"}

    return TestClient(app)


def _sahtele(monkeypatch, ocr=OCR_METNI, ozet="- Madde bir\n- Madde iki"):
    kayit = {"ocr": [], "ozet": []}

    def _gorsel(gorev, istem, veri, mime):
        kayit["ocr"].append((gorev, istem, len(veri), mime))
        if isinstance(ocr, Exception):
            raise ocr
        return ocr

    def _metin(gorev, istem, sistem=None):
        kayit["ozet"].append((gorev, istem, sistem))
        if isinstance(ozet, Exception):
            raise ozet
        return ozet

    monkeypatch.setattr(saglayicilar, "gorsel_uret", _gorsel)
    monkeypatch.setattr(saglayicilar, "metin_uret", _metin)
    return kayit


def _gonder(istemci, anahtar="a10", mod="ozet", veri=b"\x89PNG-sahte"):
    return istemci.post(
        "/api/egitim/ekran_ozet",
        files={"resim": ("ekran.png", veri, "image/png")},
        data={"mod": mod},
        headers={"X-Farabi-Board-Key": anahtar},
    )


class TestBasariliHat:
    def test_ok_ozet_doner_ham_ocr_donmez(self, istemci, monkeypatch):
        kayit = _sahtele(monkeypatch)
        r = _gonder(istemci)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert d["answer"] == "- Madde bir\n- Madde iki"
        assert set(d) == {"status", "answer", "latency_ms", "request_id"}
        assert OCR_METNI.strip() not in r.text
        assert kayit["ocr"][0][0] == "gorsel"
        assert kayit["ocr"][0][3] == "image/png"
        gorev, istem, sistem = kayit["ozet"][0]
        assert gorev == "ekran_ozet"
        assert OCR_METNI.strip() in istem

    def test_ozet_kipi_madde_ve_duzey(self, istemci, monkeypatch):
        kayit = _sahtele(monkeypatch)
        _gonder(istemci, mod="ozet")
        sistem = kayit["ozet"][0][2]
        assert "5-8 madde" in sistem
        assert "10. sınıf" in sistem

    def test_anlat_kipi_uzun_anlatim(self, istemci, monkeypatch):
        kayit = _sahtele(monkeypatch)
        _gonder(istemci, mod="anlat")
        sistem = kayit["ozet"][0][2]
        assert "250-400 kelime" in sistem
        assert "madde" in sistem.lower()  # "madde işareti kullanma"

    def test_bilinmeyen_kip_ozete_duser(self, istemci, monkeypatch):
        kayit = _sahtele(monkeypatch)
        _gonder(istemci, mod="saçma")
        assert "5-8 madde" in kayit["ozet"][0][2]

    def test_fenlab_duzeysiz(self, istemci, monkeypatch):
        kayit = _sahtele(monkeypatch)
        _gonder(istemci, anahtar="afen")
        assert ". sınıf" not in kayit["ozet"][0][2]


class TestDuzeyCoz:
    @pytest.mark.parametrize("derslik,beklenen", [
        ("10-A", 10), ("9-B", 9), ("12-B", 12), ("fenlab", None), (None, None), ("", None), ("7-A", None),
    ])
    def test_duzey(self, derslik, beklenen):
        assert ekran_ozet.duzey_coz(derslik) == beklenen


class TestHatalar:
    def test_auth_zorunlu(self, istemci, monkeypatch):
        _sahtele(monkeypatch)
        assert _gonder(istemci, anahtar="yanlis").status_code == 401

    def test_kisa_ocr_okunamadi_ozete_gitmez(self, istemci, monkeypatch):
        kayit = _sahtele(monkeypatch, ocr="  Menü   Dosya  ")
        d = _gonder(istemci).json()
        assert d["status"] == "okunamadi"
        assert d["answer"] is None
        assert kayit["ozet"] == []

    def test_ocr_hatasi_hata(self, istemci, monkeypatch):
        _sahtele(monkeypatch, ocr=RuntimeError("tüm görsel zincir öldü"))
        d = _gonder(istemci).json()
        assert d["status"] == "hata"
        assert "zincir" not in str(d)

    def test_ozet_hatasi_hata(self, istemci, monkeypatch):
        _sahtele(monkeypatch, ozet=RuntimeError("özet zinciri öldü"))
        assert _gonder(istemci).json()["status"] == "hata"

    def test_bos_ozet_hata(self, istemci, monkeypatch):
        _sahtele(monkeypatch, ozet="   ")
        assert _gonder(istemci).json()["status"] == "hata"

    def test_8mb_ustu_hata_saglayiciya_gitmez(self, istemci, monkeypatch):
        kayit = _sahtele(monkeypatch)
        buyuk = b"0" * (ekran_ozet.RESIM_LIMIT_MB * 1024 * 1024 + 1)
        d = _gonder(istemci, veri=buyuk).json()
        assert d["status"] == "hata"
        assert kayit["ocr"] == []


class TestEszamanlilik:
    def test_ayni_derslik_mesgul(self, istemci, monkeypatch):
        _sahtele(monkeypatch)
        ekran_ozet._SURENLER.add("10-A")
        assert _gonder(istemci).json()["status"] == "mesgul"

    def test_hata_sonrasi_kilit_birakilir(self, istemci, monkeypatch):
        _sahtele(monkeypatch, ocr=RuntimeError("geçici"))
        assert _gonder(istemci).json()["status"] == "hata"
        _sahtele(monkeypatch)
        assert _gonder(istemci).json()["status"] == "ok"
        assert "10-A" not in ekran_ozet._SURENLER

    def test_uzun_islem_olay_dongusunu_kilitlemez(self, istemci, monkeypatch):
        """Sağlayıcı çağrısı thread havuzunda: OCR sürerken /health cevap verir."""
        basladi = threading.Event()

        def _yavas(gorev, istem, veri, mime):
            basladi.set()
            time.sleep(1.5)
            return OCR_METNI

        monkeypatch.setattr(saglayicilar, "gorsel_uret", _yavas)
        monkeypatch.setattr(saglayicilar, "metin_uret", lambda g, i, sistem=None: "- tamam")
        sonuc = {}
        t = threading.Thread(target=lambda: sonuc.setdefault("r", _gonder(istemci)))
        t.start()
        assert basladi.wait(2)
        t0 = time.perf_counter()
        assert istemci.get("/health").status_code == 200
        assert time.perf_counter() - t0 < 1.0
        t.join(5)
        assert sonuc["r"].json()["status"] == "ok"
```

- [ ] **Step 2: Fail doğrula** — Run: `cd server && venv/bin/python -m pytest tests/test_ekran_ozet.py -q` → Expected: FAIL (`ModuleNotFoundError: No module named 'ekran_ozet'`).

- [ ] **Step 3: Uygula** — `server/ekran_ozet.py`:

```python
"""server/ekran_ozet.py — tahtadaki sayfanın ekran görüntüsünden özet/anlatım.

Spec: docs/superpowers/specs/2026-10-03-ekran-ozeti-design.md. Öğretmen
kitabı kendi PDF okuyucusunda/EBA'da açıyor — hangi kitap/sayfa olduğu
bilinmiyor, bu yüzden: ekran görüntüsü → bulut OCR (`gorsel` zinciri,
ücretsiz katman) → özet (`ekran_ozet` zinciri: yerel Ollama, bulut yedek).

Yanıt `{status, answer, latency_ms, request_id}`; ham OCR metni ve hata
ayrıntısı DÖNMEZ (yalnızca journal). İçerik saklanmaz.
"""

import logging
import re
import threading
import time
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import auth
import saglayicilar

log = logging.getLogger("farabi.ekran_ozet")

router = APIRouter(dependencies=[Depends(auth.dogrula_tahta)])

RESIM_LIMIT_MB = 8
_OKUMA_PARCASI = 1 << 20  # 1 MB — proxy.py/dosya.py ile aynı
OKUNAMADI_ESIK = 80       # boşluksuz karakter; altı "ekranda yeterli yazı yok"

OCR_ISTEMI = (
    "Bu, bir ders kitabı ya da ders materyali sayfasının ekran görüntüsü. "
    "Sayfadaki metni okuma sırasıyla, olduğu gibi çıkar. Başlıkları ve "
    "formülleri koru. Yorum, açıklama ya da özet ekleme. Yalnızca metni döndür."
)

_ORTAK_KURAL = (
    "Yalnızca verilen sayfa metnine dayan; metinde olmayan bilgi, sayı ya da "
    "tarih ekleme. Menü, düğme, pencere başlığı gibi ders dışı ekran "
    "yazılarını yok say. Türkçe yaz."
)

# Aynı derslik'ten süren istekler — server/CLAUDE.md "derslik anahtarlı
# durum" kuralı (tek süreç tüm tahtalara hizmet ediyor).
_SURENLER: set[str] = set()
_KILIT = threading.Lock()


class EkranOzetYanit(BaseModel):
    status: str                 # ok | okunamadi | mesgul | hata
    answer: str | None = None
    latency_ms: int
    request_id: str


def duzey_coz(derslik: str | None) -> int | None:
    """`"10-A"` → 10; lise dışı ya da sayısız (`"fenlab"`) → None."""
    m = re.match(r"\s*(\d{1,2})", derslik or "")
    if not m:
        return None
    duzey = int(m.group(1))
    return duzey if 9 <= duzey <= 12 else None


def sistem_istemi(mod: str, duzey: int | None) -> str:
    hedef = f"{duzey}. sınıf öğrencilerine" if duzey else "öğrencilere"
    if mod == "anlat":
        return (
            f"Sen bir öğretmensin. Verilen ders kitabı sayfası metnini {hedef} "
            "uygun, 250-400 kelime uzunluğunda, akıcı bir ders anlatımına "
            f"dönüştür. Madde işareti kullanma. {_ORTAK_KURAL}"
        )
    return (
        f"Verilen ders kitabı sayfası metnini {hedef} uygun, 5-8 maddelik kısa "
        f"bir özete dönüştür. Her madde tek cümle olsun. {_ORTAK_KURAL}"
    )


def _hat(veri: bytes, mime: str, mod: str, duzey: int | None) -> tuple[str, str | None]:
    """Senkron OCR + özet — thread havuzunda koşar (olay döngüsü kilitlenmesin)."""
    ocr = (saglayicilar.gorsel_uret("gorsel", OCR_ISTEMI, veri, mime) or "").strip()
    if len(re.sub(r"\s+", "", ocr)) < OKUNAMADI_ESIK:
        return "okunamadi", None
    ozet = (saglayicilar.metin_uret(
        "ekran_ozet", f"Sayfa metni:\n\n{ocr}", sistem=sistem_istemi(mod, duzey)) or "").strip()
    if not ozet:
        raise RuntimeError("özet zinciri boş metin döndürdü")
    return "ok", ozet


@router.post("/api/egitim/ekran_ozet", response_model=EkranOzetYanit)
async def ekran_ozet_endpoint(
    resim: UploadFile = File(...),
    mod: str = Form("ozet"),
    kimlik: auth.TahtaKimligi | None = Depends(auth.dogrula_tahta),
) -> EkranOzetYanit:
    t0 = time.perf_counter()
    request_id = str(uuid.uuid4())

    def _bitir(status: str, answer: str | None = None) -> EkranOzetYanit:
        return EkranOzetYanit(status=status, answer=answer, request_id=request_id,
                              latency_ms=int((time.perf_counter() - t0) * 1000))

    mod = mod if mod in ("ozet", "anlat") else "ozet"
    derslik = kimlik.derslik if kimlik else None
    anahtar = derslik or "_"

    with _KILIT:
        if anahtar in _SURENLER:
            return _bitir("mesgul")
        _SURENLER.add(anahtar)
    try:
        sinir = RESIM_LIMIT_MB * 1024 * 1024
        parcalar: list[bytes] = []
        boyut = 0
        while True:
            parca = await resim.read(_OKUMA_PARCASI)
            if not parca:
                break
            boyut += len(parca)
            if boyut > sinir:
                log.warning("ekran_ozet %s: görüntü %d MB sınırını aşıyor", derslik, RESIM_LIMIT_MB)
                return _bitir("hata")
            parcalar.append(parca)
        mime = resim.content_type or "image/png"
        status, ozet = await run_in_threadpool(
            _hat, b"".join(parcalar), mime, mod, duzey_coz(derslik))
        log.info("ekran_ozet %s mod=%s status=%s %d ms", derslik, mod, status,
                 int((time.perf_counter() - t0) * 1000))
        return _bitir(status, ozet)
    except Exception as e:  # noqa: BLE001 — Kural 2: her hata temiz "hata" durumu
        log.warning("ekran_ozet %s hata: %s: %s", derslik, type(e).__name__, e)
        return _bitir("hata")
    finally:
        with _KILIT:
            _SURENLER.discard(anahtar)
```

`server/main.py`: import bloğuna (alfabetik değil, mevcut sıraya uyarak `import dosya` satırından sonra) `import ekran_ozet` ekle; `app.include_router(dosya.router)` satırından sonra:

```python
app.include_router(ekran_ozet.router)  # 2026-10-03 ekran özeti — RAG'a (durum["hazir"]) bağlı değil
```

- [ ] **Step 4: Geç doğrula** — Run: `cd server && venv/bin/python -m pytest tests/ -q` → Expected: tüm paket PASS (121 + Task 1'in 2 + bu dosyanın testleri).

- [ ] **Step 5: Lint** — Run: `.venv-tools/bin/ruff check server/ekran_ozet.py server/main.py --select F` → Expected: `All checks passed!`

- [ ] **Step 6: Doküman** — `server/CLAUDE.md` uç tablosuna `dosya.py` satırından sonra:

```markdown
| `ekran_ozet.py` | `POST /api/egitim/ekran_ozet` — tahtadaki sayfanın ekran görüntüsü → bulut OCR (`gorsel` zinciri) → özet (`ekran_ozet` zinciri: Ollama > deepseek > groq); `mod` ozet/anlat, derslik başına tek istek (`mesgul`), 8 MB sınır, içerik saklanmaz |
```

- [ ] **Step 7: Commit**

```bash
git add server/ekran_ozet.py server/main.py server/tests/test_ekran_ozet.py server/CLAUDE.md
git commit -m "server: POST /api/egitim/ekran_ozet - ekran goruntusu -> bulut OCR -> Ollama ozet"
```

- [ ] **Step 8: Canlıya al + uçtan uca ölç** (restart kullanıcı onaylı adım):

```bash
sudo systemctl restart farabi-api.service
for i in $(seq 1 60); do curl -sf http://127.0.0.1:8000/ready >/dev/null && break; sleep 1; done
```

Gerçek bir kitap sayfasını PNG olarak al ve uca gönder (anahtar dosyadan okunur, ekrana basılmaz):

```bash
cd /home/ata/farabi && server/venv/bin/python - <<'EOF'
import json, time, requests
k = next(iter(json.load(open("server/config/api_keys.json"))["board_keys"].items()))
h = {"X-Farabi-Board-Key": k[1]}
png = requests.get("http://127.0.0.1:8000/api/egitim/pdf_sayfa",
                   params={"ders": "biyoloji", "sinif": "9", "sayfa": 40}, headers=h, timeout=60).content
for mod in ("ozet", "anlat"):
    t = time.time()
    d = requests.post("http://127.0.0.1:8000/api/egitim/ekran_ozet", headers=h,
                      files={"resim": ("s.png", png, "image/png")}, data={"mod": mod}, timeout=120).json()
    print(mod, d["status"], f"{time.time()-t:.1f}s", (d["answer"] or "")[:400])
EOF
```

Expected: iki kipte de `ok`, toplam süre ≤ 60 sn, metin Türkçe ve sayfa içeriğine sadık. `pdf_sayfa`'nın parametre adları farklıysa `server/icerik.py::pdf_sayfa_endpoint` imzasına bak. Süreleri DECISIONS.md kaydına (Task 4) yaz.

---

### Task 3: Client aracı `ekrani_ozetle`

**Files:**
- Create: `client/actions/ekrani_ozetle.py`
- Test: `client/tests/test_ekrani_ozetle.py`

**Interfaces:**
- Consumes: `player._win._screenshot_sig.emit(ctx)` (ctx: `{"event": threading.Event, "path": str, "gizli": bool}`), `player.show_content(title: str, text: str)`, `player.write_log(str)`, `core.tahta.auth_headers()`, `core.tahta.sunucu_url()`, Task 2'nin HTTP ucu.
- Produces: `ekrani_ozetle(parameters: dict | None = None, player=None, speak=None, **_) -> str` — Task 4 `main.py`'de `self._arkaplan(lambda: ekrani_ozetle(parameters=args, player=self.ui, speak=self.speak))` ile çağırır. Modül sabitleri `MESAJLAR: dict[str, str]`, `ZAMAN_ASIMI_POST = 90.0`.

- [ ] **Step 1: Failing tests** — `client/tests/test_ekrani_ozetle.py`:

```python
"""
actions/ekrani_ozetle.py — ağsız test: yakalama dalları (gizlilik, zaman
aşımı, boş yol), sunucu yanıtları (ok, okunamadi, mesgul, hata, boş answer,
HTTP/JSON hatası). `requests.post` monkeypatch'lenir — gerçek sunucuya hiç
gidilmez (tests/conftest.py ağsız test ilkesi).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import actions.ekrani_ozetle as m


class _SahteWin:
    def __init__(self, ctx_sonuc: dict | None):
        class _Sinyal:
            def emit(_self, ctx):
                if ctx_sonuc is None:   # GUI hiç cevap vermiyor → zaman aşımı
                    return
                ctx.update(ctx_sonuc)
                ctx["event"].set()

        self._screenshot_sig = _Sinyal()


class _SahteOyuncu:
    def __init__(self, ctx_sonuc):
        self._win = _SahteWin(ctx_sonuc)
        self.loglar, self.paneller = [], []

    def write_log(self, metin):
        self.loglar.append(metin)

    def show_content(self, baslik, metin):
        self.paneller.append((baslik, metin))


class _Yanit:
    def __init__(self, veri=None, kod=200, json_hatasi=False):
        self._veri, self.status_code, self._json_hatasi = veri, kod, json_hatasi

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._json_hatasi:
            raise ValueError("JSON değil")
        return self._veri


@pytest.fixture
def ekran(tmp_path):
    yol = tmp_path / "ekran.png"
    yol.write_bytes(b"\x89PNG-sahte")
    return str(yol)


@pytest.fixture
def sunucu(monkeypatch):
    monkeypatch.setattr(m, "_sunucu_url", lambda: "http://sunucu")
    monkeypatch.setattr(m, "_auth_headers", lambda: {"X-Farabi-Board-Key": "k"})
    cagrilar = []

    def ayarla(yanit):
        def _post(url, **kw):
            cagrilar.append((url, kw))
            if isinstance(yanit, Exception):
                raise yanit
            return yanit
        monkeypatch.setattr(m.requests, "post", _post)
        return cagrilar

    return ayarla


def _calistir(oyuncu, mod="ozet"):
    soylenen = []
    sonuc = m.ekrani_ozetle({"mod": mod}, player=oyuncu, speak=soylenen.append)
    return sonuc, soylenen


def test_ok_panel_ve_ozet_etiketiyle_iletir(ekran, sunucu):
    cagrilar = sunucu(_Yanit({"status": "ok", "answer": "- Hücre zarı seçici geçirgendir."}))
    oyuncu = _SahteOyuncu({"path": ekran, "gizli": False})
    _, soylenen = _calistir(oyuncu, mod="anlat")
    url, kw = cagrilar[0]
    assert url == "http://sunucu/api/egitim/ekran_ozet"
    assert kw["data"] == {"mod": "anlat"}
    assert kw["timeout"] == m.ZAMAN_ASIMI_POST
    assert kw["headers"] == {"X-Farabi-Board-Key": "k"}
    assert oyuncu.paneller == [("ÖZET", "- Hücre zarı seçici geçirgendir.")]
    assert len(soylenen) == 1 and soylenen[0].startswith("[ÖZET]")
    assert "Hücre zarı seçici geçirgendir" in soylenen[0]


def test_bilinmeyen_kip_ozet_gider(ekran, sunucu):
    cagrilar = sunucu(_Yanit({"status": "ok", "answer": "- a"}))
    _calistir(_SahteOyuncu({"path": ekran, "gizli": False}), mod="xyz")
    assert cagrilar[0][1]["data"] == {"mod": "ozet"}


def test_gizlilik_sunucuya_gitmez(ekran, sunucu):
    cagrilar = sunucu(_Yanit({"status": "ok", "answer": "x"}))
    oyuncu = _SahteOyuncu({"path": ekran, "gizli": True})
    _, soylenen = _calistir(oyuncu)
    assert cagrilar == []
    assert soylenen == [m.MESAJLAR["gizli"]]
    assert oyuncu.paneller == []


def test_yakalama_zaman_asimi(sunucu, monkeypatch):
    monkeypatch.setattr(m, "CTX_BEKLEME_SN", 0.05)
    cagrilar = sunucu(_Yanit({"status": "ok", "answer": "x"}))
    oyuncu = _SahteOyuncu(None)
    _, soylenen = _calistir(oyuncu)
    assert cagrilar == []
    assert soylenen == [m.MESAJLAR["yakalanamadi"]]


def test_bos_yol_yakalanamadi(sunucu):
    sunucu(_Yanit({"status": "ok", "answer": "x"}))
    _, soylenen = _calistir(_SahteOyuncu({"path": "", "gizli": False}))
    assert soylenen == [m.MESAJLAR["yakalanamadi"]]


@pytest.mark.parametrize("yanit,anahtar", [
    (_Yanit({"status": "okunamadi", "answer": None}), "okunamadi"),
    (_Yanit({"status": "mesgul", "answer": None}), "mesgul"),
    (_Yanit({"status": "hata", "answer": None}), "hata"),
    (_Yanit({"status": "ok", "answer": "   "}), "hata"),
    (_Yanit({"status": "bilinmeyen"}), "hata"),
    (_Yanit(None, kod=401), "hata"),
    (_Yanit(None, json_hatasi=True), "hata"),
    (ConnectionError("sunucu yok"), "hata"),
])
def test_hata_durumlari_tek_cumle_panel_yok(ekran, sunucu, yanit, anahtar):
    sunucu(yanit)
    oyuncu = _SahteOyuncu({"path": ekran, "gizli": False})
    _, soylenen = _calistir(oyuncu)
    assert soylenen == [m.MESAJLAR[anahtar]]
    assert oyuncu.paneller == []


def test_arayuz_yoksa_kisa_cumle(sunucu):
    sunucu(_Yanit({"status": "ok", "answer": "x"}))
    soylenen = []
    m.ekrani_ozetle({}, player=None, speak=soylenen.append)
    assert soylenen == [m.MESAJLAR["yakalanamadi"]]
```

- [ ] **Step 2: Fail doğrula** — Client testleri `farabi.local`'da koşmaz (venv yok). Bu aşamada yalnızca sözdizimini doğrula: `python3 -m py_compile client/tests/test_ekrani_ozetle.py`. Gerçek koşum Task 4 Step 6'da tahtada.

- [ ] **Step 3: Uygula** — `client/actions/ekrani_ozetle.py`:

```python
"""
actions/ekrani_ozetle.py — Tahtanın KENDİ ekranındaki sayfayı (öğretmenin
kendi PDF okuyucusunda/EBA'da açtığı kitap sayfası) özetler ya da anlatır.

Spec: docs/superpowers/specs/2026-10-03-ekran-ozeti-design.md. Ekran
`ekrandaki_soruyu_oku` ile aynı yoldan yakalanır (`_screenshot_sig`, gizlilik
filtresi ui.py'de); görüntü sunucuya (`/api/egitim/ekran_ozet`) gider, OCR +
özet orada yapılır ("Brain karar verir, Client görüntüler").

`calisma="arkaplan"` (bkz. actions/kayit.py): model hemen bir onay alır;
sonuç `speak("[ÖZET] …")` ile AYRI bir turda gelir, panelde de gösterilir.
Her hata tek kısa cümleye düşer, panel açılmaz — Farabi asla dersi bozmaz.
"""

import threading

import requests
from core.tahta import auth_headers as _auth_headers
from core.tahta import sunucu_url as _sunucu_url

CTX_BEKLEME_SN = 6.0      # ekrandaki_soruyu_oku ile aynı gerekçe (gizleme + grabWindow)
ZAMAN_ASIMI_POST = 90.0   # sunucu: OCR ~8-14 sn + özet zinciri 60 sn sınırı

MESAJLAR = {
    "gizli": ("Ekranda kişisel veri olabileceği için görüntüyü alamadım efendim — "
              "o pencereyi kapatıp tekrar isteyebilirsiniz."),
    "yakalanamadi": "Ekran görüntüsünü alamadım efendim, derse devam edelim.",
    "okunamadi": "Ekranda özetlenecek yeterli yazı göremedim efendim.",
    "mesgul": "Hâlâ önceki sayfayı okuyorum efendim, birazdan hazır olacak.",
    "hata": "Özeti şu an hazırlayamadım efendim, derse böyle devam edelim.",
}

_TALIMAT = {
    "ozet": ("Öğretmenin ekranındaki sayfanın özeti aşağıda, panelde de gösteriliyor. "
             "Sınıfa kısaca özetle; metinde olmayan bilgi ekleme."),
    "anlat": ("Öğretmenin ekranındaki sayfanın anlatımı aşağıda, panelde de gösteriliyor. "
              "Buna dayanarak konuyu sınıfa anlat; metinde olmayan bilgi ekleme."),
}


def ekrani_ozetle(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    log = getattr(player, "write_log", None) or (lambda *_a: None)
    say = speak or (lambda *_a: None)
    mod = (parameters or {}).get("mod") or "ozet"
    mod = mod if mod in ("ozet", "anlat") else "ozet"

    def _bildir(anahtar: str) -> str:
        say(MESAJLAR[anahtar])
        return MESAJLAR[anahtar]

    if player is None or not hasattr(player, "_win"):
        return _bildir("yakalanamadi")

    ctx = {"event": threading.Event(), "path": "", "gizli": False}
    try:
        player._win._screenshot_sig.emit(ctx)
        if not ctx["event"].wait(timeout=CTX_BEKLEME_SN):
            log("[Ekran Özeti] Zaman aşımı — ekran yakalanamadı.")
            return _bildir("yakalanamadi")
        if ctx.get("gizli"):
            log("[Ekran Özeti] Gizlilik filtresi — yakalanmadı.")
            return _bildir("gizli")
        if not ctx.get("path"):
            return _bildir("yakalanamadi")

        log(f"[Ekran Özeti] Yakalandı, sunucuya gönderiliyor (mod={mod}).")
        with open(ctx["path"], "rb") as f:
            r = requests.post(
                f"{_sunucu_url()}/api/egitim/ekran_ozet",
                files={"resim": ("ekran.png", f, "image/png")},
                data={"mod": mod},
                headers=_auth_headers(),
                timeout=ZAMAN_ASIMI_POST,
            )
        r.raise_for_status()
        veri = r.json() or {}
    except Exception as e:  # noqa: BLE001 — Kural 2: her hata kısa cümleye düşer
        log(f"[Ekran Özeti] Hata: {type(e).__name__}: {e}")
        return _bildir("hata")

    durum = veri.get("status")
    metin = (veri.get("answer") or "").strip()
    log(f"[Ekran Özeti] {durum} · {veri.get('latency_ms')}ms")
    if durum == "ok" and metin:
        if hasattr(player, "show_content"):
            player.show_content("ÖZET", metin)
        say(f"[ÖZET] {_TALIMAT[mod]}\n\n{metin}")
        return metin
    if durum in ("okunamadi", "mesgul"):
        return _bildir(durum)
    return _bildir("hata")
```

- [ ] **Step 4: Sözdizimi + lint** — Run: `python3 -m py_compile client/actions/ekrani_ozetle.py client/tests/test_ekrani_ozetle.py && .venv-tools/bin/ruff check client/actions/ekrani_ozetle.py client/tests/test_ekrani_ozetle.py --select F` → Expected: hata yok, `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add client/actions/ekrani_ozetle.py client/tests/test_ekrani_ozetle.py
git commit -m "client: ekrani_ozetle araci - ekran -> /api/egitim/ekran_ozet -> panel + [OZET]"
```

---

### Task 4: Aracı kaydet, dağıt, belgele

**Files:**
- Modify: `client/actions/kayit.py` (`ekrandaki_soruyu_oku` `Arac(...)` girdisinden hemen sonra)
- Modify: `client/main.py` (import bloğu ~satır 42; `elif name == "ekrandaki_soruyu_oku":` dalından sonra)
- Docs: `client/CLAUDE.md` (araç listesi), `CLAUDE.md` ("Gizlilik" bölümü), `DECISIONS.md`

**Interfaces:**
- Consumes: Task 3 `ekrani_ozetle(parameters, player, speak)`; `self._arkaplan(islev)` (client/main.py:1152).
- Produces: Gemini araç bildirimi `ekrani_ozetle(mod?: "ozet"|"anlat")`.

- [ ] **Step 1: Kayıt** — `client/actions/kayit.py`'de `ekrandaki_soruyu_oku` girdisinin kapanışından (`cikti="metin",\n    ),`) sonra:

```python
    Arac(
        ad="ekrani_ozetle",
        aciklama=(
            "Reads the textbook/material page CURRENTLY OPEN on the board's "
            "own screen (the teacher opened it in their own PDF reader, EBA "
            "or browser — not via ders_icerigi/pdf_sayfa) and prepares a "
            "summary or a lesson-style explanation of it. Call when the "
            "teacher says things like 'bu sayfayı özetle', 'ekrandakini "
            "özetle', 'bu sayfayı anlat', 'açtığım sayfayı anlat'. Use "
            "mod='ozet' for a short bullet summary, mod='anlat' for a "
            "lesson-style explanation. For a QUESTION on screen use "
            "ekrandaki_soruyu_oku instead. This call returns IMMEDIATELY — "
            "say only 'Sayfayı okuyorum' and do NOT guess the content; the "
            "result arrives as a separate message tagged [ÖZET] (it is also "
            "shown in the panel), then explain it to the class using only "
            "that text. Only what is visible right now (1-2 pages) is read; "
            "for more pages the teacher scrolls and asks again. Personal/"
            "administrative screens (attendance, e-Okul, MEBBİS) are never "
            "captured — say so plainly if told."
        ),
        parametreler={
            "type": "OBJECT",
            "properties": {
                "mod": {"type": "STRING", "enum": ["ozet", "anlat"],
                        "description": "'ozet' = short bullet summary (default), 'anlat' = lesson-style explanation."},
            },
            "required": [],
        },
        izin="ekran.yakala",
        maliyet="dusuk",
        # arkaplan: _isci'nin wait_for'ı UYGULAMAZ; aracın kendi sınırları:
        # yakalama 6 sn + sunucu POST 90 sn (actions/ekrani_ozetle.py).
        zaman_asimi=96.0,
        calisma="arkaplan",
        kip=KIP_HEPSI + (KIP_TALIMAT,),
        cikti="metin",
    ),
```

- [ ] **Step 2: Dağıtım dalı** — `client/main.py` import bloğunda `from actions.ekrandaki_soruyu_oku  import ekrandaki_soruyu_oku` satırından sonra:

```python
from actions.ekrani_ozetle      import ekrani_ozetle
```

`elif name == "ekrandaki_soruyu_oku":` dalının `result = (...)` bloğundan sonra:

```python
            elif name == "ekrani_ozetle":
                # arkaplan (2026-10-03): ekran yakalama + sunucuda OCR + özet
                # 15-30 sn sürer. Model hemen onay alır; özet (ya da kısa
                # hata cümlesi) `speak()` ile [ÖZET] etiketli AYRI turda gelir.
                self._arkaplan(lambda: ekrani_ozetle(
                    parameters=args, player=self.ui, speak=self.speak))
                result = (
                    "Ekrandaki sayfa okunuyor; özet sana birazdan [ÖZET] "
                    "etiketiyle ayrı bir mesajla gelecek. Gelene kadar sayfada "
                    "ne yazdığını tahmin etme, yalnızca 'Sayfayı okuyorum' de."
                )
```

- [ ] **Step 3: Lint** — Run: `.venv-tools/bin/ruff check client/main.py client/actions/kayit.py client/actions/ekrani_ozetle.py --select F821,F811,F632,F401` → Expected: yeni bulgu yok (önce/sonra farkı sıfır).

- [ ] **Step 4: Dokümanlar**
  - `client/CLAUDE.md` araç bölümüne: "`ekrani_ozetle` (2026-10-03): öğretmenin kendi okuyucusunda açtığı sayfayı özetler/anlatır — ekran → `/api/egitim/ekran_ozet` → panel `ÖZET` + `[ÖZET]` turu; `ekrandaki_soruyu_oku` soru içindir, bu sayfa özeti içindir."
  - Kök `CLAUDE.md` "Gizlilik" bölümüne madde: "**Ekran özeti** (`ekrani_ozetle`, 2026-10-03): tahta ekran görüntüsü bulut OCR'a (Mistral, gerekirse NVIDIA) gider. Gizlilik filtresi yalnızca pencere başlığına bakar — öğrenci listesi bir PDF içinde açıkken 'özetle' denirse o görüntü buluta gider (bilinen, kabul edilen sınır)."
  - `DECISIONS.md` en üste `## 2026-10-03 - Ekran özeti (ekrani_ozetle)` kaydı: ne yapıldı (uç + araç), neden (RAG kapalı, öğretmen kendi okuyucusunu kullanıyor), Task 2 Step 8'de ölçülen süreler, gizlilik sınırı.

- [ ] **Step 5: Commit**

```bash
git add client/actions/kayit.py client/main.py client/CLAUDE.md CLAUDE.md DECISIONS.md
git commit -m "client: ekrani_ozetle araci kaydedildi ve main.py'de arka plan dali; dokumanlar"
```

- [ ] **Step 6: Push + tahtada test** (kullanıcı onayıyla):

```bash
git push origin master
server/tahta-ssh.sh 10-A "~/.local/bin/farabiguncelle.sh >/dev/null 2>&1; cd ~/farabi/client && venv/bin/python -m pytest tests/test_ekrani_ozetle.py tests/test_arac_kaydi.py -q"
```

Expected: tüm testler PASS. Güncelleme betiğinin yolu `server/farabi-kurulum.sh::SYNC_SCRIPT` (`$HOME/.local/bin/farabiguncelle.sh`); 9-A'da client `~/farabi/repo/client`. Tahtalar zaten her gün 20:00'de çeker. Uygulama çalışırken (ders saatinde) güncelleme betiği client'ı yeniden başlatabilir — ders dışı saatte koş.

- [ ] **Step 7: Son kabul** — Atakan fiziksel tahtada: PDF okuyucuda bir kitap sayfası aç → "bu sayfayı özetle" → panelde ÖZET + sesli özet; "bu sayfayı anlat" → uzun anlatım; yoklama penceresi öndeyken → gizlilik cümlesi (Kural 12, otomatikleştirilmez).
