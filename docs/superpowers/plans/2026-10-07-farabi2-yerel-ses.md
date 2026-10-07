# Farabi 2.0 Yerel Ses Hattı — Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pilot sınıfta (9-A) tahta istemcisini Gemini Live yerine bas-konuş + Bilgehan STT/TTS + Farabi Qwen hattıyla çalıştırmak; 20 araç, ders motoru ve v1 kodu korunur.

**Architecture:** Bilgehan'da tek süreçli `farabi2-ses` FastAPI servisi (`/stt` faster-whisper, `/tts` Chatterbox + hızlı T3, kalıp cümle önbelleği). Tahtada `FarabiLive`'dan türeyen `FarabiYerel` sınıfı: Gemini bağlantısı yerine `YerelOturum` (Qwen akışlı + araç döngüsü + cümle bölücü). Araçlar sonucu `speak(metin)` ile geri verdiği için yerel modda `speak` → `YerelOturum.metin_turu`; araç kodlarının hiçbiri değişmez.

**Tech Stack:** Python 3.12 (Bilgehan venv), FastAPI, faster-whisper (CTranslate2), chatterbox-tts 0.1.7 + `hizli_t3.py`; tahta: Python, PyQt6, sounddevice, requests, pytest.

**Spec:** `docs/superpowers/specs/2026-10-07-farabi2-yerel-ses-design.md`

## Global Constraints

- Tüm iş `~/farabi-v2` (dal `v2-yerel-ses`); `~/farabi` (canlı, master) DEĞİŞMEZ. `git push` yalnızca kullanıcı isteyince.
- Bilgehan: `CUDA_DEVICE_ORDER=PCI_BUS_ID`, `CUDA_VISIBLE_DEVICES=1` (RTX 3060). `farabi-embed` (GPU0, :8040, `/opt/farabi-embed`) ve Debian 192.168.23.251'e DOKUNULMAZ.
- Servis adı `farabi2-ses`, port **8060**, venv `~/chatterbox-tts/.venv`, kod `~/farabi2-ses/` (repo `sesdugumu/` dizininden kopyalanır).
- Ses: referans `~/chatterbox-tts/voices/adaylar/nisan_kumru_2.wav`, `exaggeration=0.7`, `cfg_weight=0.3`, `temperature=0.75`, çıkış 24 kHz mono 16-bit.
- STT: faster-whisper `large-v3-turbo`, `compute_type="int8_float16"`, `language="tr"`; girdi 16 kHz mono WAV.
- LLM: `http://192.168.23.252:11434/api/chat`, model `qwen3.8:27b`, `stream: true`, `think: false`.
- İstemci ayarı (`client/config/api_keys.json`, gitignore'lu): `ses_modu` (`"gemini"` varsayılan | `"yerel"`), `ses_dugumu_url` (varsayılan `http://bilgehan.local:8060`), `ollama_url` (varsayılan `http://192.168.23.252:11434`).
- Ses servisi kapalıysa **Gemini'ye düşülmez**; tam ekran OLMAYAN uyarı + log; tahta normal çalışır (Kural 2).
- Riskli araçlar: `yoklama_al`, `youtube_video`, `shutdown_farabi` → onay sorusu.
- Turda en fazla 3 araç; ilk token için 8 sn; `/stt` 5 sn; `/tts` 10 sn zaman aşımı; 0,4 sn'den kısa kayıt yok sayılır.
- Farabi sunucusunun `server/version.py::VERSION` ana sürümü DEĞİŞMEZ.
- Yeni dış bağımlılıklar yalnızca: `faster-whisper` (Bilgehan), `pytest` (Bilgehan venv ve Farabi'deki geliştirme test venv'i). Başka paket eklenmez (Kural 8).
- İstemci saf modül testleri Farabi'de `client/.venv-test` ile (yalnızca `pytest requests numpy`); tüm istemci paketi 9-A'da koşulur. Commit mesajları `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` ile biter.

## Review Focus

1. Öğretmen düğmeye basıp hiçbir şey söylemeden bırakır / sınıf gürültüsü → boş ya da halüsinasyon metin ("Altyazı M.K.", "İzlediğiniz için teşekkürler") Qwen'e GİTMEMELİ (Task 10 testi + Task 3 filtre).
2. Farabi konuşurken öğretmen tekrar basar → çalan ses ve bekleyen üretim anında kesilmeli, yeni kayıt başlamalı; eski turun cümleleri sonradan çalmamalı (Task 10 nesil sayacı testi).
3. Qwen araç argümanını string-JSON olarak ya da hiç vermeden döner → araç yine çağrılmalı ya da Qwen'e hata sonucu dönmeli, döngü çökmemeli (Task 9 testi).
4. Cevap içinde "Dr.", "vb.", "3.5", "12." gibi noktalar → cümle yarıda bölünmemeli, "on iki." gibi okunmamalı (Task 6/7 testleri).
5. Ders ortasında Bilgehan yeniden başlar → ilk istekler hata verir; tahta donmamalı, metin ekranda kalmalı, servis dönünce kendiliğinden toparlanmalı (Task 10 testi).

---

## Dosya yapısı

**Bilgehan servisi — repo `sesdugumu/`** (yeni dizin; Bilgehan'a `~/farabi2-ses/` olarak kopyalanır)
- `sesdugumu/kaliplar.py` — kalıp cümle listesi (istemci ile paylaşılan anahtarlar).
- `sesdugumu/onbellek.py` — metin → WAV bayt önbelleği (bellek içi, normalize anahtar).
- `sesdugumu/sesler.py` — WAV kodlama/çözme yardımcıları (saf numpy).
- `sesdugumu/motorlar.py` — `TTSMotoru` (Chatterbox + hızlı T3 + trim + kuyruk temizliği), `STTMotoru` (faster-whisper + halüsinasyon filtresi).
- `sesdugumu/app.py` — FastAPI uygulama fabrikası `uygulama_kur(tts, stt)`; `/tts`, `/stt`, `/saglik`.
- `sesdugumu/calistir.py` — gerçek motorlarla uvicorn giriş noktası.
- `sesdugumu/hizli_t3.py` — `~/chatterbox-tts/hiz/hizli_t3.py`'nin repo kopyası (değiştirilmeden).
- `sesdugumu/kuyruk.py` — Debian `/opt/chatterbox-tts/kuyruk.py`'nin kopyası (değiştirilmeden).
- `sesdugumu/farabi2-ses.service`, `sesdugumu/kur.sh`, `sesdugumu/CLAUDE.md`.
- `sesdugumu/tests/test_onbellek.py`, `test_sesler.py`, `test_app.py`, `test_motorlar_gercek.py` (yalnızca Bilgehan'da, `-m gpu`).

**Tahta istemcisi — `client/`**
- `client/core/metin_duzelt.py` — seslendirme öncesi temizlik + Türkçe sıra sayısı.
- `client/core/cumle_bolucu.py` — akan metinden cümle çıkarma.
- `client/core/yerel_ayar.py` — `ses_modu()`, `ses_dugumu_url()`, `ollama_url()`.
- `client/core/ses_istemci.py` — `SesIstemci` (`saglik`, `stt`, `tts`).
- `client/core/qwen_istemci.py` — `araclari_donustur`, `QwenIstemci.akis`.
- `client/core/yerel_oturum.py` — `YerelOturum` (tur mantığı, iptal, riskli onay).
- `client/yerel_main.py` — `FarabiYerel(FarabiLive)`: run, bas-konuş kaydı, speak yönlendirmesi.
- Modify `client/main.py:2504-2522` (`main()`): `ses_modu` → `FarabiYerel` ya da `FarabiLive`.
- Modify `client/ui.py`: bas-konuş düğmesi + `FarabiUI.on_ptt_bas/on_ptt_birak`, `uyari_goster`.
- Tests: `client/tests/test_metin_duzelt.py`, `test_cumle_bolucu.py`, `test_ses_istemci.py`, `test_qwen_istemci.py`, `test_yerel_oturum.py`, `test_ses_modu_secimi.py`.

**Ölçüm** — `benchmark/v2_uctan_uca.py`.

---

### Task 1: Bilgehan'da faster-whisper kurulumu ve fizibilite ölçümü (Opus)

Canlı makine — Opus kendisi yapar. Kapı: VRAM ve süre hedefleri tutmazsa Task 3'te model `medium` seçilir.

**Files:** yok (yalnızca Bilgehan venv'i)

- [ ] **Step 1: Önce durumu kaydet**

Run: `ssh ata@bilgehan.local 'nvidia-smi --query-gpu=index,memory.used --format=csv,noheader; free -m | sed -n 2p'`
Expected: `0, 5356 MiB` (değişmemeli), `1, ~2831 MiB`.

- [ ] **Step 2: Paketleri kur (proxy yalnızca bu komutta)**

```bash
ssh ata@bilgehan.local 'source /etc/profile.d/okul-proxy.sh 2>/dev/null; cd ~/chatterbox-tts && ~/.local/bin/uv pip install --python .venv/bin/python faster-whisper pytest'
```
Expected: kurulum biter; `torch` sürümü DEĞİŞMEMELİ (`.venv/bin/python -c "import torch;print(torch.__version__)"` → `2.6.0+cu124`).

- [ ] **Step 3: Modeli indir ve ölç**

`~/chatterbox-tts/stt_olcum.py`:
```python
import os, time
os.environ.update(CUDA_DEVICE_ORDER="PCI_BUS_ID", CUDA_VISIBLE_DEVICES="1")
import glob, torch
from faster_whisper import WhisperModel
t = time.time()
m = WhisperModel("large-v3-turbo", device="cuda", compute_type="int8_float16")
print(f"yükleme {time.time()-t:.1f}s")
for f in sorted(glob.glob("/home/ata/chatterbox-tts/nisan_test/*.wav"))[:6]:
    t = time.time()
    segs, _ = m.transcribe(f, language="tr", beam_size=1, vad_filter=True)
    metin = " ".join(s.text.strip() for s in segs)
    print(f"{(time.time()-t)*1000:.0f} ms | {metin}")
```
Run: `ssh ata@bilgehan.local 'cd ~/chatterbox-tts && source /etc/profile.d/okul-proxy.sh; .venv/bin/python stt_olcum.py; nvidia-smi --query-gpu=index,memory.used --format=csv,noheader'`
Expected: her dosya < 800 ms (ısınma sonrası), metinler Chatterbox'a verilen cümlelere yakın, GPU0 `5356 MiB`.

- [ ] **Step 4: Birlikte VRAM**

Chatterbox (hızlı T3 ile) + Whisper aynı süreçte yüklenip `torch.cuda.max_memory_allocated` ve `nvidia-smi` GPU1 ölçülür. Kapı: GPU1 < 11.500 MiB. Aşılırsa `large-v3-turbo` yerine `medium` ile tekrar.

- [ ] **Step 5: Sonucu kaydet** — `~/farabi-v2/DECISIONS.md`'ye tek satır (model, ms, VRAM), commit:

```bash
cd ~/farabi-v2 && git add DECISIONS.md && git commit -m "v2: Bilgehan faster-whisper ölçümü

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Ses servisi saf modülleri — kalıplar, önbellek, WAV yardımcıları

**Files:**
- Create: `sesdugumu/kaliplar.py`, `sesdugumu/onbellek.py`, `sesdugumu/sesler.py`, `sesdugumu/__init__.py` (boş), `sesdugumu/tests/__init__.py` (boş)
- Test: `sesdugumu/tests/test_onbellek.py`, `sesdugumu/tests/test_sesler.py`

**Interfaces:**
- Produces: `kaliplar.KALIPLAR: dict[str, str]` (anahtar → metin); `onbellek.anahtar(metin: str) -> str`; `onbellek.Onbellek` (`al(metin) -> bytes | None`, `koy(metin, wav: bytes) -> None`, `__len__`); `sesler.wav_kodla(ornekler: np.ndarray, sr: int) -> bytes` (float32 [-1,1] → 16-bit PCM WAV), `sesler.wav_coz(veri: bytes) -> tuple[np.ndarray, int]` (mono float32, sr).

- [ ] **Step 1: Failing tests**

`sesdugumu/tests/test_onbellek.py`:
```python
from sesdugumu.onbellek import Onbellek, anahtar
from sesdugumu.kaliplar import KALIPLAR


def test_anahtar_bosluk_ve_buyuk_harf_duyarsiz():
    assert anahtar("  Hemen  bakıyorum hocam. ") == anahtar("hemen bakıyorum hocam.")


def test_anahtar_turkce_i_dogru_kucultulur():
    assert anahtar("İYİ") == anahtar("iyi")
    assert anahtar("IŞIK") == anahtar("ışık")


def test_al_koy():
    o = Onbellek()
    assert o.al("Tamam.") is None
    o.koy("Tamam.", b"RIFF...")
    assert o.al("  tamam. ") == b"RIFF..."
    assert len(o) == 1


def test_kaliplar_bos_degil_ve_noktalama_ile_biter():
    assert len(KALIPLAR) >= 20
    for metin in KALIPLAR.values():
        assert metin.strip()[-1] in ".?!"
```

`sesdugumu/tests/test_sesler.py`:
```python
import numpy as np
from sesdugumu.sesler import wav_coz, wav_kodla


def test_gidis_donus():
    x = (np.sin(np.linspace(0, 100, 24000)) * 0.5).astype(np.float32)
    veri = wav_kodla(x, 24000)
    assert veri[:4] == b"RIFF"
    y, sr = wav_coz(veri)
    assert sr == 24000 and len(y) == len(x)
    assert np.max(np.abs(y - x)) < 1e-3


def test_kirpma_disari_tasmaz():
    veri = wav_kodla(np.array([2.0, -2.0], dtype=np.float32), 16000)
    y, _ = wav_coz(veri)
    assert np.all(np.abs(y) <= 1.0)


def test_stereo_mono_yapilir():
    import io, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(np.array([[1000, 3000]] * 10, dtype=np.int16).tobytes())
    y, sr = wav_coz(buf.getvalue())
    assert sr == 16000 and y.ndim == 1 and len(y) == 10
```

- [ ] **Step 2: Run — fail**

Run (Bilgehan'a kopyalayıp): `rsync -a --delete ~/farabi-v2/sesdugumu/ ata@bilgehan.local:farabi2-ses/sesdugumu/ && ssh ata@bilgehan.local 'cd ~/farabi2-ses && ~/chatterbox-tts/.venv/bin/python -m pytest sesdugumu/tests -q -m "not gpu"'`
Expected: FAIL (`ModuleNotFoundError: sesdugumu.onbellek`).

- [ ] **Step 3: Implement**

`sesdugumu/kaliplar.py`:
```python
"""Kalıp cümleler — servis açılışında bir kez sentezlenip önbelleğe alınır.

Anahtarlar istemcide (client/core/yerel_oturum.py) aynen kullanılır; metin
değişirse ikisi birlikte değişir (istemci metni gönderir, eşleşme metinle).
"""

KALIPLAR: dict[str, str] = {
    "bakiyorum": "Hemen bakıyorum hocam.",
    "kitap": "Bir saniye, kitaba bakıyorum.",
    "ekran": "Ekrana bakıyorum.",
    "hazirliyorum": "Hemen hazırlıyorum.",
    "aciyorum": "Hemen açıyorum.",
    "tamam": "Tamam.",
    "peki": "Peki hocam.",
    "anlamadim": "Sizi tam anlayamadım hocam, tekrar söyler misiniz?",
    "duyamadim": "Sizi duyamadım hocam, tekrar söyler misiniz?",
    "yogunum": "Şu an biraz yoğunum, birazdan tekrar sorar mısınız?",
    "hata": "Bir sorun çıktı hocam, tekrar dener misiniz?",
    "servis_kapali": "Ses servisine ulaşamıyorum hocam.",
    "iptal": "Tamam, vazgeçtim.",
    "onay_yoklama": "Yoklama alayım mı hocam?",
    "onay_video": "Videoyu açayım mı hocam?",
    "onay_kapat": "Farabi'yi kapatayım mı hocam?",
    "onay_bekliyorum": "Onaylamak için düğmeye basıp evet deyin hocam.",
    "harika_soru": "Harika bir soru!",
    "dusunelim": "Güzel, birlikte düşünelim.",
    "gunaydin": "Günaydın çocuklar!",
    "merhaba": "Merhaba çocuklar!",
    "tesekkur": "Rica ederim hocam.",
    "devam": "Devam ediyorum.",
    "durdum": "Durdum hocam.",
    "dinliyorum": "Dinliyorum hocam.",
}
```

`sesdugumu/onbellek.py`:
```python
"""Metin → WAV bayt önbelleği (bellek içi). Anahtar boşluk/büyük-küçük harf duyarsız."""
import threading

_TR_BUYUK = str.maketrans("İIÇĞÖŞÜ", "iıçğöşü")


def anahtar(metin: str) -> str:
    return " ".join(metin.translate(_TR_BUYUK).lower().split())


class Onbellek:
    def __init__(self) -> None:
        self._veri: dict[str, bytes] = {}
        self._kilit = threading.Lock()

    def al(self, metin: str) -> bytes | None:
        with self._kilit:
            return self._veri.get(anahtar(metin))

    def koy(self, metin: str, wav: bytes) -> None:
        with self._kilit:
            self._veri[anahtar(metin)] = wav

    def __len__(self) -> int:
        return len(self._veri)
```

`sesdugumu/sesler.py`:
```python
"""WAV kodlama/çözme (saf numpy + stdlib wave)."""
import io
import wave

import numpy as np


def wav_kodla(ornekler: np.ndarray, sr: int) -> bytes:
    x = np.clip(np.asarray(ornekler, dtype=np.float32), -1.0, 1.0)
    pcm = (x * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def wav_coz(veri: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(veri), "rb") as w:
        sr, kanal, genislik = w.getframerate(), w.getnchannels(), w.getsampwidth()
        ham = w.readframes(w.getnframes())
    if genislik != 2:
        raise ValueError(f"yalnızca 16-bit PCM desteklenir (gelen: {8 * genislik}-bit)")
    x = np.frombuffer(ham, dtype="<i2").astype(np.float32) / 32768.0
    if kanal > 1:
        x = x.reshape(-1, kanal).mean(axis=1)
    return x, sr
```

`sesdugumu/tests/conftest.py`:
```python
def pytest_configure(config):
    config.addinivalue_line("markers", "gpu: gerçek modelle, yalnızca Bilgehan GPU1'de")
```

- [ ] **Step 4: Run — pass** (Step 2 komutu). Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/farabi-v2 && git add sesdugumu && git commit -m "sesdugumu: kalıp cümleler, önbellek, WAV yardımcıları

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Ses motorları — Chatterbox hızlı TTS ve faster-whisper STT

**Files:**
- Create: `sesdugumu/hizli_t3.py` (kopya: `scp ata@bilgehan.local:chatterbox-tts/hiz/hizli_t3.py sesdugumu/`), `sesdugumu/kuyruk.py` (kopya: `scp ata@bilgehan.local:chatterbox-tts/kuyruk.py sesdugumu/`), `sesdugumu/motorlar.py`
- Test: `sesdugumu/tests/test_motorlar.py` (saf), `sesdugumu/tests/test_motorlar_gercek.py` (`gpu`)

**Interfaces:**
- Consumes: `sesler.wav_kodla`, `sesler.wav_coz`.
- Produces:
  - `motorlar.halusinasyon_mu(metin: str) -> bool`
  - `motorlar.TTSMotoru(referans: str, exaggeration: float, cfg_weight: float, temperature: float)` → `.sr: int` (24000), `.sentezle(metin: str) -> bytes` (WAV), `.bogulma_sayisi: int`
  - `motorlar.STTMotoru(model_adi: str, compute_type: str)` → `.coz(wav: bytes) -> str` (halüsinasyon/boş → `""`)

- [ ] **Step 1: Failing test (saf filtre)**

`sesdugumu/tests/test_motorlar.py`:
```python
import pytest
from sesdugumu.motorlar import halusinasyon_mu


@pytest.mark.parametrize("metin", [
    "", "   ", ".", "Altyazı M.K.", "İzlediğiniz için teşekkürler.",
    "Abone olmayı unutmayın", "Altyazılar: Topluluk", "...", "Hmm.",
])
def test_halusinasyon(metin):
    assert halusinasyon_mu(metin)


@pytest.mark.parametrize("metin", [
    "Mitoz bölünme nedir?", "Ekrandaki soruyu oku.", "Evet.", "Teşekkürler Farabi.",
])
def test_gercek_konusma(metin):
    assert not halusinasyon_mu(metin)
```

- [ ] **Step 2: Run — fail** (Task 2 Step 2 komutu). Expected: FAIL import error.

- [ ] **Step 3: Implement `sesdugumu/motorlar.py`**

```python
"""Gerçek ses motorları. Ağır importlar sınıf içinde — saf testler GPU'suz koşsun."""
import io
import os
import re
import threading

os.environ.setdefault("CUDA_DEVICE_ORDER", "PCI_BUS_ID")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")

from .sesler import wav_coz, wav_kodla

# Whisper'ın sessizlik/gürültüde uydurduğu bilinen kalıplar (YouTube altyazı artığı).
_HALUSINASYON = re.compile(
    r"altyaz|izlediğiniz için|abone ol|beğenmeyi unutma|kanalıma|teşekkürler izlediğiniz",
    re.IGNORECASE,
)
_ANLAMLI = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]{2,}")


def halusinasyon_mu(metin: str) -> bool:
    m = (metin or "").strip()
    if not _ANLAMLI.search(m):
        return True
    if m.lower().strip(".!? ") in {"hmm", "hı", "ıı", "eee", "aa"}:
        return True
    return bool(_HALUSINASYON.search(m))


class TTSMotoru:
    def __init__(self, referans: str, exaggeration: float, cfg_weight: float,
                 temperature: float) -> None:
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        from .hizli_t3 import hizlandir

        self._torch = torch
        self.model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
        hizlandir(self.model)
        self.model.prepare_conditionals(referans, exaggeration=exaggeration)
        self.sr = self.model.sr
        self._ayar = dict(exaggeration=exaggeration, cfg_weight=cfg_weight,
                          temperature=temperature)
        self._kilit = threading.Lock()
        self.bogulma_sayisi = 0

    def sentezle(self, metin: str) -> bytes:
        import librosa
        import numpy as np

        from .kuyruk import kuyruk_temizle

        with self._kilit, self._torch.inference_mode():
            # audio_prompt_path verilmez: koşullar açılışta hazırlandı (model.conds).
            wav = self.model.generate(metin, language_id="tr", **self._ayar)
        x = wav.squeeze(0).cpu().numpy().astype(np.float32)
        x, _ = librosa.effects.trim(x, top_db=35)
        x, kesildi = kuyruk_temizle(x, self.sr)
        if kesildi:
            self.bogulma_sayisi += 1
        return wav_kodla(x, self.sr)


class STTMotoru:
    def __init__(self, model_adi: str = "large-v3-turbo",
                 compute_type: str = "int8_float16") -> None:
        from faster_whisper import WhisperModel

        self.model = WhisperModel(model_adi, device="cuda", compute_type=compute_type)
        self._kilit = threading.Lock()

    def coz(self, wav: bytes) -> str:
        x, sr = wav_coz(wav)
        if sr != 16000:
            import librosa
            x = librosa.resample(x, orig_sr=sr, target_sr=16000)
        with self._kilit:
            parcalar, _ = self.model.transcribe(
                x, language="tr", beam_size=1, vad_filter=True,
                condition_on_previous_text=False,
            )
            metin = " ".join(p.text.strip() for p in parcalar).strip()
        return "" if halusinasyon_mu(metin) else metin
```

Not: `hizlandir(model)`'in `model.t3.inference`'ı değiştirdiği ve `prepare_conditionals` sonrası çağrılabildiği Bilgehan'daki `~/chatterbox-tts/hiz/olcum.py`'den doğrulanır (orada sıra: yükle → `hizlandir` → `generate(audio_prompt_path=...)`). `generate` `audio_prompt_path` verilmezse `self.conds`'u kullanır — `chatterbox/mtl_tts.py::generate` içinde `assert self.conds is not None` satırıyla doğrula.

`sesdugumu/tests/test_motorlar_gercek.py`:
```python
import time

import pytest

pytestmark = pytest.mark.gpu
REF = "/home/ata/chatterbox-tts/voices/adaylar/nisan_kumru_2.wav"


@pytest.fixture(scope="module")
def tts():
    from sesdugumu.motorlar import TTSMotoru
    return TTSMotoru(REF, 0.7, 0.3, 0.75)


@pytest.fixture(scope="module")
def stt():
    from sesdugumu.motorlar import STTMotoru
    return STTMotoru()


def test_tts_hizli_ve_24k(tts):
    from sesdugumu.sesler import wav_coz
    tts.sentezle("Isınma cümlesi.")
    t = time.time()
    wav = tts.sentezle("Harika bir soru! Mitoz bölünmede hücre önce kromozomlarını eşler.")
    sure = time.time() - t
    x, sr = wav_coz(wav)
    assert sr == 24000
    assert sure / (len(x) / sr) < 0.6


def test_stt_tts_gidis_donus(tts, stt):
    wav = tts.sentezle("Dokuzuncu sınıf biyoloji kitabında mitoz neydi?")
    metin = stt.coz(wav).lower()
    assert "mitoz" in metin and "biyoloji" in metin


def test_stt_sessizlik_bos(stt):
    from sesdugumu.sesler import wav_kodla
    import numpy as np
    assert stt.coz(wav_kodla(np.zeros(16000, dtype=np.float32), 16000)) == ""
```

- [ ] **Step 4: Run saf + gpu**

Run: `rsync -a --delete ~/farabi-v2/sesdugumu/ ata@bilgehan.local:farabi2-ses/sesdugumu/ && ssh ata@bilgehan.local 'cd ~/farabi2-ses && HF_HOME=/home/ata/chatterbox-tts/.cache/huggingface HF_HUB_OFFLINE=1 ~/chatterbox-tts/.venv/bin/python -m pytest sesdugumu/tests -q'`
Expected: hepsi PASS. `test_tts_hizli_ve_24k` başarısızsa hızlı yol devreye girmemiştir — `hizlandir` dönüş değerini/log'unu kontrol et.

- [ ] **Step 5: Commit**

```bash
cd ~/farabi-v2 && git add sesdugumu && git commit -m "sesdugumu: Chatterbox hızlı TTS ve faster-whisper STT motorları

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: FastAPI uygulaması — /tts, /stt, /saglik

**Files:**
- Create: `sesdugumu/app.py`, `sesdugumu/calistir.py`
- Test: `sesdugumu/tests/test_app.py`

**Interfaces:**
- Consumes: `Onbellek`, `KALIPLAR`, motorların `.sentezle(str)->bytes`, `.coz(bytes)->str`, `.sr`, `.bogulma_sayisi`.
- Produces (HTTP, istemci Task 8 bunlara bağlı):
  - `GET /saglik` → 200 `{"ok": true, "tts": bool, "stt": bool, "onbellek": int, "bogulma": int, "istek": int}`
  - `POST /tts` JSON `{"metin": str}` → 200 `audio/wav`, başlık `X-Onbellek: 1|0`, `X-Uretim-Ms`; boş/2000+ karakter → 400
  - `POST /stt` gövde ham WAV (`Content-Type: audio/wav`) → 200 `{"metin": str, "sure_ms": int}`; 16-bit PCM değilse 400

- [ ] **Step 1: Failing tests**

`sesdugumu/tests/test_app.py`:
```python
import numpy as np
from fastapi.testclient import TestClient

from sesdugumu.app import uygulama_kur
from sesdugumu.kaliplar import KALIPLAR
from sesdugumu.sesler import wav_kodla


class SahteTTS:
    sr = 24000
    bogulma_sayisi = 0

    def __init__(self):
        self.cagri = []

    def sentezle(self, metin):
        self.cagri.append(metin)
        return wav_kodla(np.zeros(240, dtype=np.float32), 24000)


class SahteSTT:
    def coz(self, wav):
        from sesdugumu.sesler import wav_coz
        wav_coz(wav)  # gerçek motor gibi bozuk veride hata verir
        return "mitoz nedir"


def istemci():
    tts = SahteTTS()
    return TestClient(uygulama_kur(tts, SahteSTT(), kaliplari_isit=True)), tts


def test_saglik_ve_kalip_isitma():
    c, tts = istemci()
    r = c.get("/saglik").json()
    assert r["ok"] and r["tts"] and r["stt"]
    assert r["onbellek"] == len(KALIPLAR)
    assert len(tts.cagri) == len(KALIPLAR)


def test_kalip_onbellekten_doner():
    c, tts = istemci()
    once = len(tts.cagri)
    r = c.post("/tts", json={"metin": KALIPLAR["bakiyorum"]})
    assert r.status_code == 200 and r.headers["X-Onbellek"] == "1"
    assert len(tts.cagri) == once


def test_yeni_metin_sentezlenir():
    c, tts = istemci()
    r = c.post("/tts", json={"metin": "Mitoz dört evreden oluşur."})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert r.headers["X-Onbellek"] == "0"
    assert tts.cagri[-1] == "Mitoz dört evreden oluşur."


def test_tts_bos_ve_uzun_400():
    c, _ = istemci()
    assert c.post("/tts", json={"metin": "  "}).status_code == 400
    assert c.post("/tts", json={"metin": "a" * 2001}).status_code == 400


def test_stt():
    c, _ = istemci()
    wav = wav_kodla(np.zeros(16000, dtype=np.float32), 16000)
    r = c.post("/stt", content=wav, headers={"Content-Type": "audio/wav"})
    assert r.status_code == 200 and r.json()["metin"] == "mitoz nedir"


def test_stt_bozuk_400():
    c, _ = istemci()
    assert c.post("/stt", content=b"bozuk", headers={"Content-Type": "audio/wav"}).status_code == 400
```

- [ ] **Step 2: Run — fail.** Expected: `ModuleNotFoundError: sesdugumu.app`.

- [ ] **Step 3: Implement**

`sesdugumu/app.py`:
```python
"""farabi2-ses HTTP uygulaması. Motorlar enjekte edilir (testte sahte, üretimde gerçek)."""
import asyncio
import logging
import time

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from .kaliplar import KALIPLAR
from .onbellek import Onbellek

log = logging.getLogger("farabi2-ses")
AZAMI_KARAKTER = 2000


class TTSIstek(BaseModel):
    metin: str


def uygulama_kur(tts, stt, kaliplari_isit: bool = True) -> FastAPI:
    app = FastAPI(title="farabi2-ses")
    onbellek = Onbellek()
    sayac = {"istek": 0}

    if kaliplari_isit:
        for metin in KALIPLAR.values():
            onbellek.koy(metin, tts.sentezle(metin))
        log.info("Kalıp cümleler hazır: %d", len(onbellek))

    @app.get("/saglik")
    async def saglik():
        return {"ok": True, "tts": tts is not None, "stt": stt is not None,
                "onbellek": len(onbellek), "bogulma": getattr(tts, "bogulma_sayisi", 0),
                "istek": sayac["istek"]}

    @app.post("/tts")
    async def tts_uc(istek: TTSIstek):
        metin = istek.metin.strip()
        if not metin or len(metin) > AZAMI_KARAKTER:
            raise HTTPException(400, "metin boş ya da çok uzun")
        sayac["istek"] += 1
        t = time.perf_counter()
        wav = onbellek.al(metin)
        isabet = wav is not None
        if not isabet:
            wav = await asyncio.to_thread(tts.sentezle, metin)
        ms = (time.perf_counter() - t) * 1000
        log.info("tts %s %.0f ms %r", "önbellek" if isabet else "üretim", ms, metin[:60])
        return Response(wav, media_type="audio/wav",
                        headers={"X-Onbellek": "1" if isabet else "0", "X-Uretim-Ms": f"{ms:.0f}"})

    @app.post("/stt")
    async def stt_uc(request: Request):
        veri = await request.body()
        sayac["istek"] += 1
        t = time.perf_counter()
        try:
            metin = await asyncio.to_thread(stt.coz, veri)
        except Exception as e:  # noqa: BLE001 — bozuk WAV ve wave.Error vb.
            raise HTTPException(400, f"ses çözülemedi: {e}") from e
        ms = int((time.perf_counter() - t) * 1000)
        log.info("stt %d ms %r", ms, metin[:60])
        return {"metin": metin, "sure_ms": ms}

    return app
```

`sesdugumu/calistir.py`:
```python
"""Üretim giriş noktası: gerçek motorlarla uvicorn (systemd buradan başlatır)."""
import logging
import os

import uvicorn

from sesdugumu.app import uygulama_kur
from sesdugumu.motorlar import STTMotoru, TTSMotoru

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

REFERANS = os.environ.get("FARABI2_SES_REFERANS",
                          "/home/ata/chatterbox-tts/voices/adaylar/nisan_kumru_2.wav")

if __name__ == "__main__":
    tts = TTSMotoru(REFERANS, float(os.environ.get("FARABI2_SES_EXAGGERATION", "0.7")),
                    float(os.environ.get("FARABI2_SES_CFG", "0.3")),
                    float(os.environ.get("FARABI2_SES_TEMPERATURE", "0.75")))
    stt = STTMotoru(os.environ.get("FARABI2_STT_MODEL", "large-v3-turbo"))
    uvicorn.run(uygulama_kur(tts, stt), host="0.0.0.0",
                port=int(os.environ.get("FARABI2_SES_PORT", "8060")), workers=1)
```

- [ ] **Step 4: Run — pass** (`-m "not gpu"`). Expected: 6 + önceki testler PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/farabi-v2 && git add sesdugumu && git commit -m "sesdugumu: /tts /stt /saglik FastAPI uygulaması

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: systemd birimi ve Bilgehan'a kurulum (Opus — canlı makine, sudo)

**Files:**
- Create: `sesdugumu/farabi2-ses.service`, `sesdugumu/kur.sh`, `sesdugumu/CLAUDE.md`

- [ ] **Step 1: Birim dosyası** `sesdugumu/farabi2-ses.service`:

```ini
[Unit]
Description=Farabi 2.0 ses dugumu (STT + TTS, RTX 3060)
After=network-online.target

[Service]
User=ata
WorkingDirectory=/home/ata/farabi2-ses
Environment=CUDA_DEVICE_ORDER=PCI_BUS_ID
Environment=CUDA_VISIBLE_DEVICES=1
Environment=HF_HOME=/home/ata/chatterbox-tts/.cache/huggingface
Environment=HF_HUB_OFFLINE=1
Environment=TQDM_DISABLE=1
ExecStart=/home/ata/chatterbox-tts/.venv/bin/python -m sesdugumu.calistir
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Kurulum betiği** `sesdugumu/kur.sh` (Farabi'den çalıştırılır):

```bash
#!/usr/bin/env bash
# Farabi'den: sesdugumu/'nu Bilgehan'a kopyalar ve servisi (yeniden) başlatır.
set -euo pipefail
HEDEF=ata@bilgehan.local
cd "$(dirname "$0")/.."
rsync -a --delete --exclude tests --exclude __pycache__ sesdugumu/ "$HEDEF:farabi2-ses/sesdugumu/"
ssh -t "$HEDEF" 'sudo install -m 644 ~/farabi2-ses/sesdugumu/farabi2-ses.service /etc/systemd/system/farabi2-ses.service && sudo systemctl daemon-reload && sudo systemctl enable --now farabi2-ses && sudo systemctl restart farabi2-ses'
echo "Bekleniyor (model yükleme + kalıp ısıtma ~90 sn)..."
for i in $(seq 1 30); do curl -sf http://bilgehan.local:8060/saglik && exit 0; sleep 5; done
echo "HATA: /saglik yanıt vermedi"; exit 1
```

`ssh -t` sudo şifresi ister — kullanıcı `! sesdugumu/kur.sh` ile kendisi çalıştırır.

- [ ] **Step 3: `sesdugumu/CLAUDE.md`** — servis amacı, port 8060, GPU1 sabiti, yasaklar (farabi-embed, Debian), kurulum `sesdugumu/kur.sh`, log `journalctl -u farabi2-ses`, test komutları (Task 2/3).

- [ ] **Step 4: Kurulum + doğrulama**

Run: kullanıcı `! ~/farabi-v2/sesdugumu/kur.sh`; sonra Opus:
```bash
curl -s http://bilgehan.local:8060/saglik
curl -s -o /tmp/claude-1000/k.wav -w '%{time_total}\n' -D - http://bilgehan.local:8060/tts -H 'Content-Type: application/json' -d '{"metin":"Hemen bakıyorum hocam."}' | grep -i onbellek
ssh ata@bilgehan.local 'nvidia-smi --query-gpu=index,memory.used --format=csv,noheader; sudo -n true 2>/dev/null; systemctl is-active farabi2-ses farabi-embed'
```
Expected: `/saglik` `onbellek: 25`; kalıp `X-Onbellek: 1`, süre < 0,05 sn; GPU0 `5356 MiB`; GPU1 < 11.500 MiB; iki servis `active`. Ardından `ssh -t ata@bilgehan.local sudo systemctl restart farabi2-ses` → 2 dk içinde `/saglik` tekrar ok.

- [ ] **Step 5: Commit**

```bash
cd ~/farabi-v2 && git add sesdugumu && git commit -m "sesdugumu: systemd birimi, kurulum betiği, CLAUDE.md

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: İstemci — `core/metin_duzelt.py`

**Files:**
- Create: `client/core/metin_duzelt.py`
- Test: `client/tests/test_metin_duzelt.py`
- Önce bir kez: `cd ~/farabi-v2/client && python3 -m venv .venv-test && .venv-test/bin/pip install -q pytest requests numpy` (`.venv-test/` → `client/.gitignore`'a eklenir, bu task'ın commit'ine dahil).

**Interfaces:**
- Produces: `metin_duzelt.seslendirme_icin(metin: str) -> str`

- [ ] **Step 1: Failing test**

`client/tests/test_metin_duzelt.py`:
```python
import pytest
from core.metin_duzelt import seslendirme_icin


@pytest.mark.parametrize("girdi,beklenen", [
    ("**Mitoz** bölünme", "Mitoz bölünme"),
    ("## Evreler", "Evreler"),
    ("- profaz\n- metafaz", "profaz, metafaz"),
    ("1) Profaz 2) Metafaz", "Profaz, Metafaz"),
    ("12. sınıf", "on ikinci sınıf"),
    ("9. sınıf biyoloji", "dokuzuncu sınıf biyoloji"),
    ("3. soru", "üçüncü soru"),
    ("1. ünite", "birinci ünite"),
    ("2. Dünya Savaşı", "ikinci Dünya Savaşı"),
    ("40. sayfa", "kırkıncı sayfa"),
    ("Cevap 12.", "Cevap 12."),
    ("x = `a+b`", "x = a+b"),
    ("Merhaba 😊 çocuklar", "Merhaba çocuklar"),
])
def test_seslendirme_icin(girdi, beklenen):
    assert seslendirme_icin(girdi) == beklenen
```

- [ ] **Step 2: Run — fail**

Run: `cd ~/farabi-v2/client && .venv-test/bin/python -m pytest tests/test_metin_duzelt.py -q`
Expected: FAIL `ModuleNotFoundError: core.metin_duzelt`.

- [ ] **Step 3: Implement** `client/core/metin_duzelt.py`:

```python
"""Seslendirme öncesi metin düzeltme: biçimlendirme temizliği + Türkçe sıra sayıları.

Chatterbox'un kendi metin düzelticisi "12. sınıf"ı "on iki. sınıf" okuyor
(2026-10-07 ölçümü); yıl/sayı/ek okumasını ise doğru yapıyor — bu yüzden
burada YALNIZCA sıra sayısı + biçim temizliği var.
"""
import re

_BIRLER = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_ONLAR = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
_SIRA = {
    "bir": "birinci", "iki": "ikinci", "üç": "üçüncü", "dört": "dördüncü", "beş": "beşinci",
    "altı": "altıncı", "yedi": "yedinci", "sekiz": "sekizinci", "dokuz": "dokuzuncu",
    "on": "onuncu", "yirmi": "yirminci", "otuz": "otuzuncu", "kırk": "kırkıncı",
    "elli": "ellinci", "altmış": "altmışıncı", "yetmiş": "yetmişinci",
    "seksen": "sekseninci", "doksan": "doksanıncı", "yüz": "yüzüncü",
}
# "12. sınıf", "2. Dünya" — sayı + nokta + boşluk + harf; cümle sonu ("Cevap 12.") eşleşmez.
_SIRA_RE = re.compile(r"\b([1-9]\d?|100)\.(?=\s+[^\W\d_])")
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def _sira(n: int) -> str:
    if n == 100:
        return _SIRA["yüz"]
    on, bir = divmod(n, 10)
    kelimeler = [k for k in (_ONLAR[on], _BIRLER[bir]) if k]
    kelimeler[-1] = _SIRA[kelimeler[-1]]
    return " ".join(kelimeler)


def seslendirme_icin(metin: str) -> str:
    m = re.sub(r"\*\*|__|`", "", metin)
    m = re.sub(r"^\s*#+\s*", "", m, flags=re.MULTILINE)       # başlık
    m = re.sub(r"^\s*[-*•]\s+", "", m, flags=re.MULTILINE)    # madde imi
    m = re.sub(r"(?:^|\s)\d+\)\s*", "\n", m)                  # "1) a 2) b" → satırlar
    m = _EMOJI_RE.sub("", m)
    m = _SIRA_RE.sub(lambda e: _sira(int(e.group(1))), m)
    satirlar = [" ".join(s.split()) for s in m.splitlines()]
    return ", ".join(s for s in satirlar if s)
```

Bu kod plan yazılırken 13 testin tamamını geçti (2026-10-07).

- [ ] **Step 4: Run — pass.** Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/farabi-v2 && git add client/core/metin_duzelt.py client/tests/test_metin_duzelt.py client/.gitignore && git commit -m "client: seslendirme öncesi metin düzeltme (biçim + Türkçe sıra sayısı)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: İstemci — `core/cumle_bolucu.py`

**Files:**
- Create: `client/core/cumle_bolucu.py`
- Test: `client/tests/test_cumle_bolucu.py`

**Interfaces:**
- Produces: `CumleBolucu` → `.ekle(parca: str) -> list[str]` (tamamlanan cümleler), `.bitir() -> list[str]` (kalan). İlk cümle için `ilk_en_az=12` karakter (çok kısa ilk parçayı bir sonrakiyle birleştirmez — "Harika!" tek başına gider), sonrakiler `en_az=25` karakter (kısa cümleler birleştirilir, TTS çağrısı azalır).

- [ ] **Step 1: Failing test**

```python
from core.cumle_bolucu import CumleBolucu


def parca_parca(metin, boyut=3):
    b = CumleBolucu()
    cikti = []
    for i in range(0, len(metin), boyut):
        cikti += b.ekle(metin[i:i + boyut])
    return cikti + b.bitir()


def test_temel():
    assert parca_parca("Harika bir soru! Mitoz dört evreden oluşur. Önce profaz gelir.") == [
        "Harika bir soru!", "Mitoz dört evreden oluşur.", "Önce profaz gelir."]


def test_kisaltma_ve_ondalik_bolunmez():
    c = parca_parca("Dr. Ahmet 3.5 saat çalıştı vb. şeyler yaptı. Sonra gitti ve uyudu sonunda.")
    assert c[0] == "Dr. Ahmet 3.5 saat çalıştı vb. şeyler yaptı."


def test_sira_sayisi_bolunmez():
    c = parca_parca("Bugün 12. sınıf konusuna bakacağız. Hazır mısınız çocuklar?")
    assert c[0] == "Bugün 12. sınıf konusuna bakacağız."


def test_soru_ve_unlem():
    assert parca_parca("Anladınız mı? Çok güzel!") == ["Anladınız mı?", "Çok güzel!"]


def test_bitir_noktasiz_kalan():
    assert parca_parca("Noktasız bir cümle") == ["Noktasız bir cümle"]


def test_bos():
    b = CumleBolucu()
    assert b.ekle("") == [] and b.bitir() == []
```

- [ ] **Step 2: Run — fail.** `.venv-test/bin/python -m pytest tests/test_cumle_bolucu.py -q` → ModuleNotFoundError.

- [ ] **Step 3: Implement** `client/core/cumle_bolucu.py`:

```python
"""Akan LLM metninden seslendirilecek cümleleri çıkarır."""
import re

_KISALTMA = {"dr", "prof", "vb", "vs", "örn", "bkz", "sn", "av", "doç", "yrd", "no", "s", "sf"}
_SON = re.compile(r"[.!?…]+")


class CumleBolucu:
    """`ekle` tamamlanan cümleleri döner. İlk cümle `ilk_en_az`, sonrakiler
    `en_az` karakterden kısaysa bir sonrakiyle birleştirilir (TTS çağrısı azalır)."""

    def __init__(self, ilk_en_az: int = 12, en_az: int = 25) -> None:
        self._tampon = ""
        self._ilk = True
        self._ilk_en_az, self._en_az = ilk_en_az, en_az

    @staticmethod
    def _sinir_mi(metin: str, son: int) -> bool:
        if metin[son - 1] != ".":
            return True
        onceki = metin[:son].rstrip(".")
        kelime = onceki.split()[-1] if onceki.split() else ""
        return not (kelime.lower() in _KISALTMA or kelime.isdigit())

    def ekle(self, parca: str) -> list[str]:
        self._tampon += parca
        cikti: list[str] = []
        bas = 0
        for m in _SON.finditer(self._tampon):
            son = m.end()
            if son >= len(self._tampon) or not self._tampon[son].isspace():
                continue  # devamı gelmeden ya da "3.5" gibi: karar verme
            if not self._sinir_mi(self._tampon, son):
                continue
            aday = self._tampon[bas:son].strip()
            if len(aday) >= (self._ilk_en_az if self._ilk else self._en_az):
                cikti.append(aday)
                bas = son
                self._ilk = False
        self._tampon = self._tampon[bas:]
        return cikti

    def bitir(self) -> list[str]:
        kalan = " ".join(self._tampon.split())
        self._tampon, self._ilk = "", True
        return [kalan] if kalan else []
```

Bu kod plan yazılırken 6 testin tamamını geçti. `kelime.isdigit()` kuralı "Cevap 12." cümle sonunu da bölmez; kalan `bitir()` ile gelir (kabul edilir).

- [ ] **Step 4: Run — pass.** Expected: 6 passed.
- [ ] **Step 5: Commit**

```bash
cd ~/farabi-v2 && git add client/core/cumle_bolucu.py client/tests/test_cumle_bolucu.py && git commit -m "client: akan metin için cümle bölücü

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: İstemci — ayarlar ve `SesIstemci`

**Files:**
- Create: `client/core/yerel_ayar.py`, `client/core/ses_istemci.py`
- Modify: `client/config/api_keys.example.json` (üç yeni alan)
- Test: `client/tests/test_ses_istemci.py`

**Interfaces:**
- Produces:
  - `yerel_ayar.ses_modu() -> str` (`"gemini"`|`"yerel"`, bilinmeyen/eksik → `"gemini"`), `yerel_ayar.ses_dugumu_url() -> str`, `yerel_ayar.ollama_url() -> str` (sonda `/` yok)
  - `ses_istemci.SesServisiHatasi(Exception)`
  - `ses_istemci.SesIstemci(taban_url: str, oturum=None)` → `.saglik() -> bool` (hata yutar, 3 sn), `.stt(wav: bytes) -> str` (5 sn; ağ/HTTP hatası → `SesServisiHatasi`), `.tts(metin: str) -> bytes` (10 sn; hata → `SesServisiHatasi`). `oturum` requests.Session benzeri (test için enjekte).

- [ ] **Step 1: Failing test**

```python
import json

import pytest
import requests

from core import yerel_ayar
from core.ses_istemci import SesIstemci, SesServisiHatasi


class Yanit:
    def __init__(self, durum=200, govde=b"", js=None):
        self.status_code, self.content, self._js = durum, govde, js

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class SahteOturum:
    def __init__(self, yanit=None, hata=None):
        self.yanit, self.hata, self.cagri = yanit, hata, []

    def _cagir(self, *a, **k):
        self.cagri.append((a, k))
        if self.hata:
            raise self.hata
        return self.yanit

    get = post = _cagir


def test_ayar_varsayilanlari(tmp_path, monkeypatch):
    yol = tmp_path / "api_keys.json"
    yol.write_text("{}")
    monkeypatch.setattr(yerel_ayar, "CONFIG_PATH", yol)
    assert yerel_ayar.ses_modu() == "gemini"
    assert yerel_ayar.ses_dugumu_url() == "http://bilgehan.local:8060"
    assert yerel_ayar.ollama_url() == "http://192.168.23.252:11434"


def test_ayar_yerel_ve_bozuk(tmp_path, monkeypatch):
    yol = tmp_path / "api_keys.json"
    monkeypatch.setattr(yerel_ayar, "CONFIG_PATH", yol)
    yol.write_text(json.dumps({"ses_modu": "yerel", "ses_dugumu_url": "http://x:1/"}))
    assert yerel_ayar.ses_modu() == "yerel"
    assert yerel_ayar.ses_dugumu_url() == "http://x:1"
    yol.write_text(json.dumps({"ses_modu": "baska"}))
    assert yerel_ayar.ses_modu() == "gemini"
    yol.write_text("bozuk{")
    assert yerel_ayar.ses_modu() == "gemini"


def test_saglik():
    assert SesIstemci("http://x", SahteOturum(Yanit(js={"ok": True}))).saglik() is True
    assert SesIstemci("http://x", SahteOturum(hata=requests.ConnectionError())).saglik() is False
    assert SesIstemci("http://x", SahteOturum(Yanit(500))).saglik() is False


def test_stt_ve_hata():
    o = SahteOturum(Yanit(js={"metin": "mitoz nedir", "sure_ms": 300}))
    assert SesIstemci("http://x", o).stt(b"RIFF") == "mitoz nedir"
    assert o.cagri[0][1]["timeout"] == 5
    with pytest.raises(SesServisiHatasi):
        SesIstemci("http://x", SahteOturum(hata=requests.Timeout())).stt(b"RIFF")


def test_tts():
    o = SahteOturum(Yanit(govde=b"RIFFwav"))
    assert SesIstemci("http://x", o).tts("Merhaba.") == b"RIFFwav"
    assert o.cagri[0][1]["json"] == {"metin": "Merhaba."}
    with pytest.raises(SesServisiHatasi):
        SesIstemci("http://x", SahteOturum(Yanit(400))).tts("")
```

- [ ] **Step 2: Run — fail.**

- [ ] **Step 3: Implement**

`client/core/yerel_ayar.py`:
```python
"""Farabi 2.0 yerel ses ayarları (config/api_keys.json; core/tahta.py ile aynı okuma deseni)."""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _oku(alan: str, varsayilan: str) -> str:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            ham = str(json.load(f).get(alan, "") or "").strip()
    except Exception:  # noqa: BLE001 — eksik/bozuk config varsayılana düşer
        return varsayilan
    return ham or varsayilan


def ses_modu() -> str:
    m = _oku("ses_modu", "gemini").lower()
    return m if m in {"gemini", "yerel"} else "gemini"


def ses_dugumu_url() -> str:
    return _oku("ses_dugumu_url", "http://bilgehan.local:8060").rstrip("/")


def ollama_url() -> str:
    return _oku("ollama_url", "http://192.168.23.252:11434").rstrip("/")
```

`client/core/ses_istemci.py`:
```python
"""Bilgehan farabi2-ses servisine ince HTTP istemcisi."""
import requests


class SesServisiHatasi(Exception):
    pass


class SesIstemci:
    def __init__(self, taban_url: str, oturum=None) -> None:
        self.url = taban_url.rstrip("/")
        self._o = oturum or requests.Session()

    def saglik(self) -> bool:
        try:
            r = self._o.get(f"{self.url}/saglik", timeout=3)
            r.raise_for_status()
            return bool(r.json().get("ok"))
        except Exception:  # noqa: BLE001 — sağlık denetimi asla patlamaz
            return False

    def stt(self, wav: bytes) -> str:
        try:
            r = self._o.post(f"{self.url}/stt", data=wav,
                             headers={"Content-Type": "audio/wav"}, timeout=5)
            r.raise_for_status()
            return str(r.json().get("metin", "")).strip()
        except (requests.RequestException, ValueError) as e:
            raise SesServisiHatasi(f"stt: {e}") from e

    def tts(self, metin: str) -> bytes:
        try:
            r = self._o.post(f"{self.url}/tts", json={"metin": metin}, timeout=10)
            r.raise_for_status()
            return r.content
        except requests.RequestException as e:
            raise SesServisiHatasi(f"tts: {e}") from e
```

`client/config/api_keys.example.json`'a ekle: `"ses_modu": "gemini"`, `"ses_dugumu_url": "http://bilgehan.local:8060"`, `"ollama_url": "http://192.168.23.252:11434"`.

- [ ] **Step 4: Run — pass.** Expected: 5 passed.
- [ ] **Step 5: Commit** (`client/core/yerel_ayar.py client/core/ses_istemci.py client/tests/test_ses_istemci.py client/config/api_keys.example.json`, mesaj `client: yerel ses ayarları ve farabi2-ses HTTP istemcisi`).

---

### Task 9: İstemci — `core/qwen_istemci.py`

**Files:**
- Create: `client/core/qwen_istemci.py`
- Test: `client/tests/test_qwen_istemci.py`

**Interfaces:**
- Produces:
  - `araclari_donustur(bildirimler: list[dict]) -> list[dict]` — `kayit.bildirimler(kip)` çıktısını (`{"name","description","parameters"}`, Gemini tipleri büyük harfli olabilir) Ollama formatına (`{"type":"function","function":{...}}`, tipler küçük harf) çevirir.
  - `AracCagrisi` (dataclass: `ad: str`, `argumanlar: dict`)
  - `QwenIstemci(taban_url: str, model: str = "qwen3.8:27b", satir_akisi=None)` → `.akis(mesajlar: list[dict], araclar: list[dict], iptal: threading.Event) -> Iterator[str | AracCagrisi]` — metin parçalarını str olarak, araç çağrılarını `AracCagrisi` olarak sırayla üretir; `iptal` set edilince yanıtı kapatıp durur. İlk çıktı 8 sn'de gelmezse `QwenZamanAsimi` fırlatır. `satir_akisi(govde: dict, zaman_asimi: float) -> Iterator[bytes]` test için enjekte edilir (varsayılan: `requests.post(..., stream=True).iter_lines()`).
  - `QwenZamanAsimi(Exception)`, `QwenHatasi(Exception)`

- [ ] **Step 1: Failing test**

```python
import json
import threading

import pytest

from core.qwen_istemci import AracCagrisi, QwenIstemci, QwenZamanAsimi, araclari_donustur


def satirlar(*olaylar):
    def akis(govde, zaman_asimi):
        akis.govde = govde
        for o in olaylar:
            yield json.dumps(o).encode()
    return akis


def test_donustur_tip_kucuk_harf():
    b = [{"name": "kitap_sorusu", "description": "d",
          "parameters": {"type": "OBJECT", "properties": {"soru": {"type": "STRING"},
                         "n": {"type": "INTEGER"}}, "required": ["soru"]}}]
    a = araclari_donustur(b)[0]
    assert a["type"] == "function" and a["function"]["name"] == "kitap_sorusu"
    p = a["function"]["parameters"]
    assert p["type"] == "object" and p["properties"]["soru"]["type"] == "string"
    assert p["properties"]["n"]["type"] == "integer" and p["required"] == ["soru"]


def test_donustur_parametresiz():
    a = araclari_donustur([{"name": "x", "description": "d", "parameters": None}])[0]
    assert a["function"]["parameters"] == {"type": "object", "properties": {}}


def test_metin_akisi():
    q = QwenIstemci("http://x", satir_akisi=satirlar(
        {"message": {"content": "Mer"}}, {"message": {"content": "haba."}}, {"done": True}))
    assert list(q.akis([{"role": "user", "content": "selam"}], [], threading.Event())) == ["Mer", "haba."]
    assert q._satir_akisi.govde["think"] is False and q._satir_akisi.govde["stream"] is True


def test_arac_cagrisi_dict_ve_string_arguman():
    q = QwenIstemci("http://x", satir_akisi=satirlar(
        {"message": {"tool_calls": [
            {"function": {"name": "kitap_sorusu", "arguments": {"soru": "mitoz"}}},
            {"function": {"name": "ekrandaki_soruyu_oku", "arguments": '{"talimat": "oku"}'}},
            {"function": {"name": "yoklama_al"}}]}},
        {"done": True}))
    c = list(q.akis([], [], threading.Event()))
    assert c == [AracCagrisi("kitap_sorusu", {"soru": "mitoz"}),
                 AracCagrisi("ekrandaki_soruyu_oku", {"talimat": "oku"}),
                 AracCagrisi("yoklama_al", {})]


def test_bozuk_string_arguman_bos_dict():
    q = QwenIstemci("http://x", satir_akisi=satirlar(
        {"message": {"tool_calls": [{"function": {"name": "a", "arguments": "{bozuk"}}]}}))
    assert list(q.akis([], [], threading.Event())) == [AracCagrisi("a", {})]


def test_iptal():
    iptal = threading.Event()

    def akis(govde, zaman_asimi):
        yield json.dumps({"message": {"content": "Bir."}}).encode()
        iptal.set()
        yield json.dumps({"message": {"content": "İki."}}).encode()

    assert list(QwenIstemci("http://x", satir_akisi=akis).akis([], [], iptal)) == ["Bir."]


def test_zaman_asimi():
    def akis(govde, zaman_asimi):
        raise TimeoutError("yok")
        yield b""

    with pytest.raises(QwenZamanAsimi):
        list(QwenIstemci("http://x", satir_akisi=akis).akis([], [], threading.Event()))
```

- [ ] **Step 2: Run — fail.**

- [ ] **Step 3: Implement** `client/core/qwen_istemci.py`:

```python
"""Farabi Ollama (qwen3.8:27b) akışlı sohbet + araç çağrısı istemcisi."""
import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field

import requests

ILK_CIKTI_SN = 8.0


class QwenHatasi(Exception):
    pass


class QwenZamanAsimi(QwenHatasi):
    pass


@dataclass
class AracCagrisi:
    ad: str
    argumanlar: dict = field(default_factory=dict)


def _sema(s):
    if isinstance(s, dict):
        return {k: (v.lower() if k == "type" and isinstance(v, str) else _sema(v))
                for k, v in s.items()}
    if isinstance(s, list):
        return [_sema(x) for x in s]
    return s


def araclari_donustur(bildirimler: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {
        "name": b["name"], "description": b.get("description", ""),
        "parameters": _sema(b.get("parameters")) or {"type": "object", "properties": {}},
    }} for b in bildirimler]


def _arguman(ham) -> dict:
    if isinstance(ham, dict):
        return ham
    if isinstance(ham, str):
        try:
            v = json.loads(ham)
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}
    return {}


class QwenIstemci:
    def __init__(self, taban_url: str, model: str = "qwen3.8:27b", satir_akisi=None) -> None:
        self.url = taban_url.rstrip("/")
        self.model = model
        self._satir_akisi = satir_akisi or self._http_akisi

    def _http_akisi(self, govde: dict, zaman_asimi: float):
        with requests.post(f"{self.url}/api/chat", json=govde, stream=True,
                           timeout=(3, zaman_asimi)) as r:
            r.raise_for_status()
            yield from r.iter_lines()

    def akis(self, mesajlar: list[dict], araclar: list[dict],
             iptal: threading.Event) -> Iterator["str | AracCagrisi"]:
        govde = {"model": self.model, "messages": mesajlar, "stream": True,
                 "think": False, "keep_alive": -1}
        if araclar:
            govde["tools"] = araclar
        try:
            for satir in self._satir_akisi(govde, ILK_CIKTI_SN):
                if iptal.is_set():
                    return
                if not satir:
                    continue
                olay = json.loads(satir)
                if olay.get("error"):
                    raise QwenHatasi(olay["error"])
                m = olay.get("message") or {}
                if m.get("content"):
                    yield m["content"]
                for c in m.get("tool_calls") or []:
                    f = c.get("function") or {}
                    yield AracCagrisi(f.get("name", ""), _arguman(f.get("arguments")))
                if olay.get("done"):
                    return
        except (TimeoutError, requests.Timeout) as e:
            raise QwenZamanAsimi(str(e)) from e
        except requests.RequestException as e:
            raise QwenHatasi(str(e)) from e
```

Not: `requests` okuma zaman aşımı (8 sn) iki satır arasındaki bekleme için geçerli — ilk çıktı + akış sırasında takılma ikisini de kapsar.

- [ ] **Step 4: Run — pass.** Expected: 7 passed.
- [ ] **Step 5: Commit** (`client: Qwen akışlı sohbet + araç çağrısı istemcisi`).

---

### Task 10: İstemci — `core/yerel_oturum.py` (tur mantığı)

**Files:**
- Create: `client/core/yerel_oturum.py`
- Test: `client/tests/test_yerel_oturum.py`

**Interfaces:**
- Consumes: `SesIstemci`/`SesServisiHatasi` (Task 8), `QwenIstemci`/`AracCagrisi`/`QwenHatasi`/`QwenZamanAsimi` (Task 9), `CumleBolucu` (Task 7), `seslendirme_icin` (Task 6), kalıp metinleri `client/core/kaliplar.py` (bu task'ta `sesdugumu/kaliplar.py`'nin BİREBİR kopyası olarak oluşturulur; test ikisinin eşitliğini denetler).
- Produces:
  - `RISKLI = {"yoklama_al": "onay_yoklama", "youtube_video": "onay_video", "shutdown_farabi": "onay_kapat"}`
  - `YerelOturum(ses, qwen, sistem_metni: Callable[[], str], araclar: Callable[[], list[dict]], arac_calistir: Callable[[str, dict], Awaitable[str]], cal: Callable[[bytes], None], metin_goster: Callable[[str, str], None], azami_gecmis: int = 12)`:
    - `async def ses_turu(self, wav: bytes) -> None` — STT → `metin_turu`
    - `async def metin_turu(self, metin: str, kaynak: str = "ogretmen") -> None` — bir tur; `kaynak="arac"|"sistem"` speak/ders motoru yönlendirmesi içindir (kullanıcı mesajı olarak eklenir, onay mantığına girmez)
    - `def iptal(self) -> None` — süren turu keser (nesil sayacı artar; eski nesilin `cal` çağrıları yapılmaz)
    - `gecmis: list[dict]` (Ollama mesaj formatı)
    - `cal(wav)` WAV baytlarını oynatma kuyruğuna koyar (FarabiYerel sağlar); `metin_goster(kim, metin)` dökümüne/ekrana yazar (`kim` ∈ `"ogretmen","farabi","sistem"`).

Davranış (spec "Konuşma turu" + "Hata durumları"):
1. `ses_turu`: `SesServisiHatasi` → kalıp `duyamadim` çal (o da hata verirse `metin_goster("sistem", "Sizi duyamadım — ses servisi yanıt vermiyor.")`); boş metin → hiçbir şey yapma (Qwen'e gitme).
2. Bekleyen onay varsa (`self._bekleyen`): metin "evet/tamam/olur/aç/al" içeriyorsa araç çalışır, değilse kalıp `iptal`; her durumda bekleyen temizlenir ve tur biter.
3. Mesajlar: `[{"role":"system","content": sistem_metni()}] + gecmis[-azami_gecmis:] + [user]`.
4. Akış: metin parçaları `CumleBolucu`'ya; her cümle `seslendirme_icin` → `ses.tts` → `cal`. TTS hatası: metin `metin_goster("farabi", cümle)` ile gösterilir; 3 ardışık hatada `ses.saglik()` çağrılır, False ise `metin_goster("sistem", "Ses servisi kapalı (Bilgehan)")`.
5. `AracCagrisi`: önce kalıp çal (`kitap_sorusu`/`ders_icerigi`/`pdf_sayfa` → `kitap`, `ekrandaki_soruyu_oku`/`ekran_goruntusu_al` → `ekran`, diğer → `bakiyorum`); riskli ise kalıp onay sorusu çal, `self._bekleyen = cagri`, tur biter. Değilse `sonuc = await arac_calistir(ad, args)`; geçmişe `{"role":"assistant","content":"", "tool_calls":[...]}` ve `{"role":"tool","content": sonuc}` eklenir; Qwen yeniden çağrılır. Turda 3 araçtan sonra araçlar listesi boş gönderilir (model metinle bitirir).
6. `QwenZamanAsimi` → kalıp `yogunum`; `QwenHatasi` → kalıp `hata`. Log `log.warning`.
7. `iptal()` → `self._iptal` Event set + nesil++; akış döngüsü çıkar; yarım cevap geçmişe `+ " (kesildi)"` ile yazılır.
8. Tüm TTS/STT/Qwen çağrıları `asyncio.to_thread` ile (bloklayıcı requests).

- [ ] **Step 1: Failing tests**

```python
import asyncio
import threading

import pytest

from core import kaliplar as istemci_kaliplar
from core.qwen_istemci import AracCagrisi, QwenZamanAsimi
from core.ses_istemci import SesServisiHatasi
from core.yerel_oturum import RISKLI, YerelOturum


class SahteSes:
    def __init__(self, stt_metin="mitoz nedir", stt_hata=False, tts_hata=False):
        self.stt_metin, self.stt_hata, self.tts_hata = stt_metin, stt_hata, tts_hata
        self.tts_cagri = []

    def stt(self, wav):
        if self.stt_hata:
            raise SesServisiHatasi("x")
        return self.stt_metin

    def tts(self, metin):
        self.tts_cagri.append(metin)
        if self.tts_hata:
            raise SesServisiHatasi("x")
        return b"WAV:" + metin.encode()

    def saglik(self):
        return not self.tts_hata


class SahteQwen:
    """Her akis() çağrısında senaryodaki sıradaki listeyi üretir."""

    def __init__(self, *senaryo, hata=None):
        self.senaryo, self.hata, self.cagri = list(senaryo), hata, []

    def akis(self, mesajlar, araclar, iptal):
        self.cagri.append((mesajlar, araclar))
        if self.hata:
            raise self.hata
        for x in self.senaryo.pop(0) if self.senaryo else []:
            if iptal.is_set():
                return
            yield x


def kur(ses=None, qwen=None, arac_sonuc="Kitapta: mitoz dört evre."):
    calinan, gosterilen, araclar = [], [], []

    async def arac_calistir(ad, args):
        araclar.append((ad, args))
        return arac_sonuc

    o = YerelOturum(ses or SahteSes(), qwen or SahteQwen(["Merhaba çocuklar."]),
                    sistem_metni=lambda: "SİSTEM", araclar=lambda: [{"type": "function"}],
                    arac_calistir=arac_calistir, cal=calinan.append,
                    metin_goster=lambda k, m: gosterilen.append((k, m)))
    return o, calinan, gosterilen, araclar


def calistir(c):
    return asyncio.run(c)


def test_kaliplar_sunucuyla_ayni():
    from pathlib import Path
    import importlib.util
    yol = Path(__file__).resolve().parents[2] / "sesdugumu" / "kaliplar.py"
    spec = importlib.util.spec_from_file_location("sk", yol)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    assert m.KALIPLAR == istemci_kaliplar.KALIPLAR


def test_sohbet_turu():
    o, calinan, gosterilen, _ = kur(qwen=SahteQwen(["Harika bir ", "soru! Mitoz dört evreden oluşur."]))
    calistir(o.ses_turu(b"RIFF"))
    assert calinan == [b"WAV:Harika bir soru!", b"WAV:Mitoz dört evreden oluşur."]
    assert ("ogretmen", "mitoz nedir") in gosterilen
    assert o.gecmis[-1] == {"role": "assistant", "content": "Harika bir soru! Mitoz dört evreden oluşur."}


def test_bos_stt_qwene_gitmez():
    q = SahteQwen(["x."])
    o, calinan, _, _ = kur(ses=SahteSes(stt_metin=""), qwen=q)
    calistir(o.ses_turu(b"RIFF"))
    assert q.cagri == [] and calinan == []


def test_stt_hatasi_kalip():
    o, calinan, _, _ = kur(ses=SahteSes(stt_hata=True))
    calistir(o.ses_turu(b"RIFF"))
    assert calinan == [b"WAV:" + istemci_kaliplar.KALIPLAR["duyamadim"].encode()]


def test_aracli_tur():
    q = SahteQwen([AracCagrisi("kitap_sorusu", {"soru": "mitoz"})], ["Mitoz dört evreden oluşur."])
    o, calinan, _, araclar = kur(qwen=q)
    calistir(o.metin_turu("kitapta mitoz neydi"))
    assert araclar == [("kitap_sorusu", {"soru": "mitoz"})]
    assert calinan[0] == b"WAV:" + istemci_kaliplar.KALIPLAR["kitap"].encode()
    assert calinan[-1] == b"WAV:Mitoz dört evreden oluşur."
    assert any(m.get("role") == "tool" for m in q.cagri[1][0])


def test_uc_arac_siniri():
    a = [AracCagrisi("web_search", {"q": "x"})]
    q = SahteQwen(a, a, a, ["Bitti."])
    o, _, _, araclar = kur(qwen=q)
    calistir(o.metin_turu("ara"))
    assert len(araclar) == 3
    assert q.cagri[3][1] == []


def test_riskli_arac_onay_evet():
    q = SahteQwen([AracCagrisi("yoklama_al", {})], ["Yoklama alındı."])
    o, calinan, _, araclar = kur(qwen=q)
    calistir(o.metin_turu("yoklama al"))
    assert araclar == [] and calinan[-1] == b"WAV:" + istemci_kaliplar.KALIPLAR[RISKLI["yoklama_al"]].encode()
    calistir(o.metin_turu("evet"))
    assert araclar == [("yoklama_al", {})]


def test_riskli_arac_onay_hayir():
    o, calinan, _, araclar = kur(qwen=SahteQwen([AracCagrisi("yoklama_al", {})]))
    calistir(o.metin_turu("derse başlayalım mı"))
    calistir(o.metin_turu("hayır"))
    assert araclar == [] and calinan[-1] == b"WAV:" + istemci_kaliplar.KALIPLAR["iptal"].encode()


def test_qwen_zaman_asimi():
    o, calinan, _, _ = kur(qwen=SahteQwen(hata=QwenZamanAsimi("x")))
    calistir(o.metin_turu("soru"))
    assert calinan == [b"WAV:" + istemci_kaliplar.KALIPLAR["yogunum"].encode()]


def test_tts_hatasi_metin_gosterilir_ve_servis_kapali_uyarisi():
    o, calinan, gosterilen, _ = kur(ses=SahteSes(tts_hata=True),
                                    qwen=SahteQwen(["Bir cümle burada var. İki cümle de burada var. Üç cümle burada son."]))
    calistir(o.metin_turu("anlat"))
    assert calinan == []
    assert ("farabi", "Bir cümle burada var.") in gosterilen
    assert ("sistem", "Ses servisi kapalı (Bilgehan)") in gosterilen


def test_iptal_eski_cumleler_calmaz():
    async def senaryo():
        bekle = threading.Event()

        class YavasQwen(SahteQwen):
            def akis(self, mesajlar, araclar, iptal):
                yield "Birinci cümle buradadır uzun. "
                bekle.wait(2)
                yield "İkinci cümle de buradadır uzun."

        o, calinan, _, _ = kur(qwen=YavasQwen())
        gorev = asyncio.create_task(o.metin_turu("anlat"))
        await asyncio.sleep(0.2)
        o.iptal()
        bekle.set()
        await gorev
        return o, calinan

    o, calinan = asyncio.run(senaryo())
    assert b"WAV:\xc4\xb0kinci" not in b"".join(calinan)
    assert o.gecmis[-1]["content"].endswith("(kesildi)")


def test_gecmis_siniri():
    q = SahteQwen(*[["Tamam."]] * 20)
    o, _, _, _ = kur(qwen=q)
    for i in range(20):
        calistir(o.metin_turu(f"soru {i}"))
    mesajlar = q.cagri[-1][0]
    assert mesajlar[0] == {"role": "system", "content": "SİSTEM"}
    assert len(mesajlar) <= 1 + 12 + 1
```

- [ ] **Step 2: Run — fail.** `.venv-test/bin/python -m pytest tests/test_yerel_oturum.py -q`

- [ ] **Step 3: Implement**

`client/core/kaliplar.py`: `sesdugumu/kaliplar.py`'nin birebir kopyası (`cp ../sesdugumu/kaliplar.py core/kaliplar.py`; modül docstring'ine "kaynak: sesdugumu/kaliplar.py, test eşitliği denetler" satırı eklenebilir, sözlük AYNI kalır).

`client/core/yerel_oturum.py`:
```python
"""Farabi 2.0 yerel konuşma turu: STT → Qwen (araçlı, akışlı) → cümle → TTS → çal.

Gemini Live'ın yerine geçer; araçların kendisi değişmez (FarabiYerel
`arac_calistir` olarak mevcut `_execute_tool`'u verir). Bkz. spec
docs/superpowers/specs/2026-10-07-farabi2-yerel-ses-design.md.
"""
import asyncio
import logging
import re
import threading

from core.cumle_bolucu import CumleBolucu
from core.kaliplar import KALIPLAR
from core.metin_duzelt import seslendirme_icin
from core.qwen_istemci import AracCagrisi, QwenHatasi, QwenZamanAsimi
from core.ses_istemci import SesServisiHatasi

log = logging.getLogger("farabi.yerel")

AZAMI_ARAC = 3
RISKLI = {"yoklama_al": "onay_yoklama", "youtube_video": "onay_video",
          "shutdown_farabi": "onay_kapat"}
_BEKLEME_KALIBI = {"kitap_sorusu": "kitap", "ders_icerigi": "kitap", "pdf_sayfa": "kitap",
                   "ekrandaki_soruyu_oku": "ekran", "ekran_goruntusu_al": "ekran"}
_EVET = re.compile(r"\b(evet|tamam|olur|aç|al|kapat|onaylıyorum)\b", re.IGNORECASE)


class YerelOturum:
    def __init__(self, ses, qwen, sistem_metni, araclar, arac_calistir, cal, metin_goster,
                 azami_gecmis: int = 12) -> None:
        self.ses, self.qwen = ses, qwen
        self._sistem, self._araclar = sistem_metni, araclar
        self._arac_calistir, self._cal, self._goster = arac_calistir, cal, metin_goster
        self._azami = azami_gecmis
        self.gecmis: list[dict] = []
        self._iptal = threading.Event()
        self._nesil = 0
        self._bekleyen: AracCagrisi | None = None
        self._tts_hata_serisi = 0
        self._kilit = asyncio.Lock()

    def iptal(self) -> None:
        self._nesil += 1
        self._iptal.set()

    async def _seslendir(self, metin: str, nesil: int) -> None:
        if nesil != self._nesil:
            return
        try:
            wav = await asyncio.to_thread(self.ses.tts, seslendirme_icin(metin))
            self._tts_hata_serisi = 0
        except SesServisiHatasi as e:
            log.warning("TTS hatası: %s", e)
            self._goster("farabi", metin)
            self._tts_hata_serisi += 1
            if self._tts_hata_serisi == 3 and not await asyncio.to_thread(self.ses.saglik):
                self._goster("sistem", "Ses servisi kapalı (Bilgehan)")
            return
        if nesil == self._nesil:
            self._cal(wav)

    async def _kalip(self, anahtar: str, nesil: int) -> None:
        await self._seslendir(KALIPLAR[anahtar], nesil)

    async def ses_turu(self, wav: bytes) -> None:
        nesil = self._nesil
        try:
            metin = await asyncio.to_thread(self.ses.stt, wav)
        except SesServisiHatasi as e:
            log.warning("STT hatası: %s", e)
            await self._kalip("duyamadim", nesil)
            return
        if metin:
            await self.metin_turu(metin)

    async def metin_turu(self, metin: str, kaynak: str = "ogretmen") -> None:
        async with self._kilit:
            self._iptal.clear()
            nesil = self._nesil
            if kaynak == "ogretmen":
                self._goster("ogretmen", metin)
                if self._bekleyen is not None:
                    cagri, self._bekleyen = self._bekleyen, None
                    if _EVET.search(metin):
                        await self._araci_calistir(cagri, nesil)
                    else:
                        await self._kalip("iptal", nesil)
                    return
            self.gecmis.append({"role": "user", "content": metin})
            await self._model_dongusu(nesil)

    async def _araci_calistir(self, cagri: AracCagrisi, nesil: int) -> str:
        await self._kalip(_BEKLEME_KALIBI.get(cagri.ad, "bakiyorum"), nesil)
        try:
            return str(await self._arac_calistir(cagri.ad, cagri.argumanlar))
        except Exception as e:  # noqa: BLE001 — araç hatası Qwen'e sonuç olarak döner
            log.exception("Araç hatası: %s", cagri.ad)
            return f"Araç hatası ({cagri.ad}): {str(e)[:120]}"

    async def _model_dongusu(self, nesil: int) -> None:
        arac_sayisi = 0
        while True:
            mesajlar = ([{"role": "system", "content": self._sistem()}]
                        + self.gecmis[-self._azami:])
            araclar = self._araclar() if arac_sayisi < AZAMI_ARAC else []
            bolucu, metin, cagrilar = CumleBolucu(), "", []
            kuyruk: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def uret():
                try:
                    for x in self.qwen.akis(mesajlar, araclar, self._iptal):
                        loop.call_soon_threadsafe(kuyruk.put_nowait, x)
                except Exception as e:  # noqa: BLE001 — ana döngüye taşınır
                    loop.call_soon_threadsafe(kuyruk.put_nowait, e)
                loop.call_soon_threadsafe(kuyruk.put_nowait, None)

            uretici = asyncio.create_task(asyncio.to_thread(uret))
            try:
                while (x := await kuyruk.get()) is not None:
                    if isinstance(x, QwenZamanAsimi):
                        await self._kalip("yogunum", nesil)
                        return
                    if isinstance(x, (QwenHatasi, Exception)):
                        log.warning("Qwen hatası: %s", x)
                        await self._kalip("hata", nesil)
                        return
                    if isinstance(x, AracCagrisi):
                        cagrilar.append(x)
                        continue
                    metin += x
                    for c in bolucu.ekle(x):
                        await self._seslendir(c, nesil)
            finally:
                await uretici
            if nesil != self._nesil:
                if metin:
                    self.gecmis.append({"role": "assistant", "content": metin + " (kesildi)"})
                return
            for c in bolucu.bitir():
                await self._seslendir(c, nesil)
            if not cagrilar:
                self.gecmis.append({"role": "assistant", "content": metin})
                return
            self.gecmis.append({"role": "assistant", "content": metin, "tool_calls": [
                {"function": {"name": c.ad, "arguments": c.argumanlar}} for c in cagrilar]})
            for c in cagrilar:
                if c.ad in RISKLI:
                    self._bekleyen = c
                    await self._kalip(RISKLI[c.ad], nesil)
                    self.gecmis.append({"role": "tool", "content": "Öğretmenin onayı bekleniyor."})
                    return
                sonuc = await self._araci_calistir(c, nesil)
                self.gecmis.append({"role": "tool", "content": sonuc})
                arac_sayisi += 1
```

`test_iptal_eski_cumleler_calmaz`: iptal sonrası `uret` thread'i `iptal.is_set()` görünce `SahteQwen` döngüsünden çıkar; `YavasQwen` kontrol etmez — bu yüzden `_seslendir`'deki nesil kontrolü korur. Test geçmezse `_seslendir`'i değil testi okuyup akışı izle; testi zayıflatma.

- [ ] **Step 4: Run — pass.** Expected: 13 passed. Ardından tüm saf paket: `.venv-test/bin/python -m pytest tests/test_metin_duzelt.py tests/test_cumle_bolucu.py tests/test_ses_istemci.py tests/test_qwen_istemci.py tests/test_yerel_oturum.py -q`.
- [ ] **Step 5: Commit** (`client/core/kaliplar.py client/core/yerel_oturum.py client/tests/test_yerel_oturum.py`, mesaj `client: YerelOturum — STT/Qwen/araç/TTS tur mantığı`).

---

### Task 11: İstemci entegrasyonu — `FarabiYerel`, bas-konuş düğmesi, mod seçimi

**Files:**
- Create: `client/yerel_main.py`
- Modify: `client/main.py` (`main()` içinde `farabi = FarabiLive(ui)` satırı), `client/ui.py` (bas-konuş düğmesi, `FarabiUI` köprüleri)
- Test: `client/tests/test_ses_modu_secimi.py`

**Interfaces:**
- Consumes: `FarabiLive` (`_execute_tool(fc)`, `_build_config()`, `_play_audio()`, `_sesi_sustur()`, `audio_in_queue`, `_turn_done_event`, `set_speaking`, `etkinlik_bildir`, `_oturum_izni`, `oturum_baslat`, `_cerceveye_plan_kazanimi_ekle`, `_programdan_cerceve`, `_ders_kipi`, `kayit.bildirimler(kip)`), `YerelOturum`, `SesIstemci`, `QwenIstemci`, `araclari_donustur`, `yerel_ayar.*`.
- Produces: `yerel_main.FarabiYerel(ui)`; `yerel_main.siniflari_sec(ses_modu: str) -> type` (`"yerel"` → `FarabiYerel`, aksi `FarabiLive`); `FarabiUI.on_ptt_bas`, `FarabiUI.on_ptt_birak` (callable özellikler), `FarabiUI.ptt_goster(acik: bool)`, `FarabiUI.uyari_goster(metin: str)` (tam ekran olmayan, log satırı + durum çubuğu).

- [ ] **Step 1: Failing test** `client/tests/test_ses_modu_secimi.py` (yalnızca 9-A'da koşar — PyQt6/genai gerekir):

```python
import importlib

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("google.genai")


def test_secim():
    yerel_main = importlib.import_module("yerel_main")
    main = importlib.import_module("main")
    assert yerel_main.siniflari_sec("yerel") is yerel_main.FarabiYerel
    assert yerel_main.siniflari_sec("gemini") is main.FarabiLive
    assert yerel_main.siniflari_sec("bilinmeyen") is main.FarabiLive
    assert issubclass(yerel_main.FarabiYerel, main.FarabiLive)


def test_fc_sarmalayici():
    yerel_main = importlib.import_module("yerel_main")
    fc = yerel_main._Fc("kitap_sorusu", {"soru": "x"})
    assert fc.name == "kitap_sorusu" and fc.args == {"soru": "x"} and fc.id
```

- [ ] **Step 2: Implement `client/yerel_main.py`**

Tasarım: v1'de modele metin giden HER yol (`speak`, `_on_text_command`, `_ders_motoru_dongusu`, `_oturum_devam_notu`) `self.session.send_client_content(turns=..., turn_complete=True)` çağırır. Yerel modda `self.session` = `_OturumAdaptoru`: metin parçalarını `YerelOturum.metin_turu(..., kaynak="sistem")`'e yönlendirir, görsel içeren turu reddeder (→ `ekrani_modele_gonder` False döner, araç OCR yoluna düşer). Böylece ders motoru, boşta gözcüsü ve araçların `speak`'i v1 kodu değişmeden çalışır.

```python
"""Farabi 2.0 — Gemini Live yerine yerel ses hattı (bas-konuş).

FarabiLive'dan türer; araç yürütme, ses çalma, ders motoru, boşta gözcüsü,
susturma FarabiLive'ınkidir. Değişen: `self.session` bir adaptör — modele
giden metin YerelOturum'a metin turu olarak gider; görsel tur reddedilir
(ekrandaki_soruyu_oku OCR yoluna düşer — görsel okuma bulutta, spec kararı).
"""
import asyncio
import io
import uuid
import wave
from dataclasses import dataclass, field

import sounddevice as sd

from actions import kayit
from core import tahta, transcript, yerel_ayar
from core.ders_motoru import DersMotoru
from core.logger import get_logger
from core.qwen_istemci import QwenIstemci, araclari_donustur
from core.ses_istemci import SesIstemci
from core.yerel_oturum import YerelOturum
from main import CHANNELS, SEND_SAMPLE_RATE, FarabiLive, _ders_kipi

log = get_logger("farabi.yerel_main")
EN_KISA_KAYIT_SN = 0.4

_YEREL_KURALLAR = (
    "\n\n[YEREL SES KURALLARI] Konuşma diliyle, en fazla 2-3 kısa cümleyle cevap ver. "
    "Yıldız, liste, başlık, numaralandırma, emoji KULLANMA — metin seslendirilecek. "
    "Selamlaşma, hal hatır, teşekkür ve genel sohbette HİÇBİR ARAÇ ÇAĞIRMA; doğrudan cevap ver. "
    "Araç yalnızca öğretmen açıkça bir iş istediğinde (kitaba bak, ekrandaki soruyu oku, video aç, "
    "yoklama al) çağrılır."
)


@dataclass
class _Fc:
    name: str
    args: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex)


def siniflari_sec(ses_modu: str) -> type:
    return FarabiYerel if ses_modu == "yerel" else FarabiLive


def _wav_ayir(wav: bytes) -> bytes:
    """24 kHz mono 16-bit WAV → ham PCM (oynatma kuyruğu ham int16 bekler)."""
    with wave.open(io.BytesIO(wav), "rb") as w:
        return w.readframes(w.getnframes())


def _wav_yap(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)
        w.setframerate(SEND_SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


class _OturumAdaptoru:
    """Gemini `session` arayüzünün yerel karşılığı (yalnızca kullanılan kısım)."""

    def __init__(self, oturum: YerelOturum) -> None:
        self._oturum = oturum

    async def send_client_content(self, turns=None, turn_complete=True):
        parcalar = (turns or {}).get("parts", [])
        if any("inline_data" in p for p in parcalar):
            raise RuntimeError("yerel modda görsel tur yok — OCR yoluna düş")
        metin = " ".join(p.get("text", "") for p in parcalar).strip()
        if metin:
            asyncio.get_running_loop().create_task(
                self._oturum.metin_turu(metin, kaynak="sistem"))


class FarabiYerel(FarabiLive):
    def __init__(self, ui) -> None:
        super().__init__(ui)
        self.ses = SesIstemci(yerel_ayar.ses_dugumu_url())
        self.oturum: YerelOturum | None = None
        self._kayit: list[bytes] = []
        self._kayit_akisi = None
        ui.on_ptt_bas = self._ptt_bas
        ui.on_ptt_birak = self._ptt_birak

    # ── Bas-konuş (UI iş parçacığından çağrılır) ────────────────────────
    def _ptt_bas(self) -> None:
        if self.oturum:
            self.oturum.iptal()
        if self._loop:
            self._loop.call_soon_threadsafe(self._sesi_sustur)
        self._kayit = []

        def cb(indata, frames, t, status):
            self._kayit.append(bytes(indata))

        self._kayit_akisi = sd.RawInputStream(samplerate=SEND_SAMPLE_RATE, channels=CHANNELS,
                                              dtype="int16", callback=cb)
        self._kayit_akisi.start()
        self.ui.set_state("LISTENING")

    def _ptt_birak(self) -> None:
        akis, self._kayit_akisi = self._kayit_akisi, None
        if akis is None:
            return
        akis.stop()
        akis.close()
        pcm = b"".join(self._kayit)
        if len(pcm) / 2 / SEND_SAMPLE_RATE < EN_KISA_KAYIT_SN or not (self._loop and self.oturum):
            return
        self.ui.set_state("THINKING")
        self.etkinlik_bildir()
        asyncio.run_coroutine_threadsafe(self.oturum.ses_turu(_wav_yap(pcm)), self._loop)

    # ── YerelOturum'a verilen geri çağrılar ─────────────────────────────
    async def _arac_calistir(self, ad: str, args: dict) -> str:
        yanit = await self._execute_tool(_Fc(ad, args))
        return str((getattr(yanit, "response", None) or {}).get("result", "Tamam."))

    def _cal(self, wav: bytes) -> None:
        self._turn_done_event.set()
        self.audio_in_queue.put_nowait(_wav_ayir(wav))

    def _goster(self, kim: str, metin: str) -> None:
        if kim == "ogretmen":
            self.ui.write_log(f"You: {metin}")
            transcript.log_line("ogrenci", metin)
            self.etkinlik_bildir()
        elif kim == "farabi":
            self.ui.write_log(f"Farabi: {metin}")
            transcript.log_line("farabi", metin)
        else:
            self.ui.uyari_goster(metin)

    async def _ders_bitti_bekle(self) -> None:
        while not self._ders_bitti_istendi:
            await asyncio.sleep(0.5)

    # ── Ana döngü ───────────────────────────────────────────────────────
    async def run(self):
        self._loop = asyncio.get_event_loop()
        self._oturum_izni = asyncio.Event()
        self.ui.on_session_start = self.oturum_baslat
        self.ui.on_ders_bitir = self._on_ders_bitir
        self._log_startup_banner()
        while True:
            self.ui.set_state("SLEEPING")
            self.ui.write_log("SYS: Ders bekleniyor — DERSİ BAŞLAT'a çift tıklayın.")
            await self._oturum_izni.wait()
            if not await asyncio.to_thread(self.ses.saglik):
                log.error("Ses servisi kapalı: %s", self.ses.url)
                self.ui.uyari_goster("Ses servisi kapalı (Bilgehan) — Farabi başlatılamadı.")
                self._oturum_izni.clear()
                continue
            # v1 run()'ın ders başı hazırlığının aynısı (main.py, "ZAMANA BAĞLI durum" bloğu)
            self._program_slotu = None
            try:
                from core import program
                self._program_slotu = program.simdiki_ders()
            except Exception as e:  # noqa: BLE001
                log.error("Ders programı okunamadı: %s", e)
            self._current_lesson = (self._programdan_cerceve(self._program_slotu)
                                    if self._program_slotu else None)
            await self._cerceveye_plan_kazanimi_ekle()
            self._ders_kipi_taban = self._ders_kipi = _ders_kipi()
            self.motor = DersMotoru(kip=self._ders_kipi_taban, cerceve=self._current_lesson,
                                    sinif=tahta.derslik(), enjekte=True)
            self.audio_in_queue = asyncio.Queue()
            self._turn_done_event = asyncio.Event()
            self.oturum = YerelOturum(
                self.ses, QwenIstemci(yerel_ayar.ollama_url()),
                sistem_metni=lambda: self._build_config().system_instruction + _YEREL_KURALLAR,
                araclar=lambda: araclari_donustur(kayit.bildirimler(self._ders_kipi)),
                arac_calistir=self._arac_calistir, cal=self._cal, metin_goster=self._goster)
            self.session = _OturumAdaptoru(self.oturum)
            self.ui.ptt_goster(True)
            self.ui.set_state("LISTENING")
            try:
                async with asyncio.TaskGroup() as tg:
                    oynat = tg.create_task(self._play_audio())
                    motor = tg.create_task(self._ders_motoru_dongusu())
                    bosta = tg.create_task(self._boşta_gozcusu())
                    await self._ders_bitti_bekle()
                    for g in (oynat, motor, bosta):
                        g.cancel()
            except* asyncio.CancelledError:
                pass
            finally:
                self.ui.ptt_goster(False)
                self.session = None
                self.oturum = None
                self._ders_bitti_istendi = False
                self._ders_bitiriliyor = False
                self._oturum_izni.clear()
```

Koddan doğrula (Kural 4) ve gerekirse düzelt — testi değil:
- `grep -n "FunctionResponse(" client/main.py` → `response={...}` anahtarı `"result"` mı; değilse `_arac_calistir`'ı düzelt.
- `_ders_kipi` modül düzeyinde fonksiyon mu (`grep -n "^def _ders_kipi" client/main.py`); `_boşta_gozcusu` ders bitişini `_dersi_bitir` ile yapıyor — o da `_ders_bitti_istendi`'yi set ediyorsa `_ders_bitti_bekle` döner; değilse `_dersi_bitir`'in sonundaki bayrağı oku ve `_ders_bitti_bekle`'yi ona bağla.
- `_on_ders_bitir` → `_ogretmen_dersi_bitirir` → `_dersi_bitir` zinciri Gemini oturumunu kapatmaya çalışıyorsa (`self.session.close` vb.), adaptöre aynı adlı boş `async def` ekle.

- [ ] **Step 3: `main.py` değişikliği** — yalnızca `main()` içinde:

```python
        from core import yerel_ayar
        from yerel_main import siniflari_sec
        farabi = siniflari_sec(yerel_ayar.ses_modu())(ui)
```
(`farabi = FarabiLive(ui)` satırının yerine; import'lar fonksiyon içinde — `yerel_main` `main`'i import ettiği için döngüsel import olmasın.)

- [ ] **Step 4: `ui.py` değişikliği**

`MainWindow`'a: `_ptt_sig = pyqtSignal(bool)` ve `_uyari_sig = pyqtSignal(str)`; `_mute_btn` bloğundan hemen önce:

```python
        self._ptt_btn = QPushButton("🎤  BAS-KONUŞ  (basılı tut)")
        self._ptt_btn.setFixedHeight(54)
        self._ptt_btn.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self._ptt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ptt_btn.pressed.connect(lambda: self.on_ptt_bas and self.on_ptt_bas())
        self._ptt_btn.released.connect(lambda: self.on_ptt_birak and self.on_ptt_birak())
        self._ptt_btn.setVisible(False)
        lay.addWidget(self._ptt_btn)
        self._ptt_sig.connect(self._ptt_btn.setVisible)
        self._uyari_sig.connect(lambda m: self._log.append_log(f"⚠ {m}"))
```
`MainWindow.__init__` içinde `self.on_ptt_bas = None; self.on_ptt_birak = None`.
`FarabiUI`'ye:
```python
    @property
    def on_ptt_bas(self):
        return self._win.on_ptt_bas

    @on_ptt_bas.setter
    def on_ptt_bas(self, cb):
        self._win.on_ptt_bas = cb

    @property
    def on_ptt_birak(self):
        return self._win.on_ptt_birak

    @on_ptt_birak.setter
    def on_ptt_birak(self, cb):
        self._win.on_ptt_birak = cb

    def ptt_goster(self, acik: bool):
        self._win._ptt_sig.emit(bool(acik))

    def uyari_goster(self, metin: str):
        self._win._uyari_sig.emit(metin)
```
`pressed/released` callback'leri UI iş parçacığında çalışır; `_ptt_bas` içindeki `sd.RawInputStream` kısa sürer (bloklamaz).

- [ ] **Step 5: 9-A'da test** (9-A'yı dala geçirmeden ÖNCE tahtada ayrı bir klasörde): kullanıcı onayıyla Opus:

```bash
server/tahta-ssh.sh 9-A "rm -rf /tmp/v2test && git clone -q --branch v2-yerel-ses --depth 1 https://github.com/atakanunver/yenifarabi /tmp/v2test && cd /tmp/v2test/client && ~/farabi/repo/client/venv/bin/python -m pytest tests/ -q"
```
(önce `git push origin v2-yerel-ses` gerekir — kullanıcı onayı.) Expected: mevcut testler + yeni testler PASS; `test_ses_modu_secimi` PASS.

- [ ] **Step 6: Commit** (`client/yerel_main.py client/main.py client/ui.py client/tests/test_ses_modu_secimi.py`, mesaj `client: FarabiYerel — bas-konuş ve ses_modu seçimi`).

---

### Task 12: Uçtan uca ölçüm betiği

**Files:**
- Create: `benchmark/v2_uctan_uca.py`

**Interfaces:**
- Consumes: `benchmark/v2_arac_testi.py` (`TEST_CUMLELERI`, `PROMPTLAR`, `build_tools_payload`), `farabi2-ses` `/tts` `/stt`, Ollama.

- [ ] **Step 1: Betik** — her test cümlesi için: `/tts` ile Nisan Kumru sesinde "öğretmen sesi" üret (16 kHz'e indir), `/stt` → metin, Qwen akışı (`stream`, araçlar `PROMPTLAR[kip]` + `_YEREL_KURALLAR` metni), ilk cümle tamamlanınca `/tts` (araç çağrısıysa kalıp `/tts`). Kaydet: `stt_ms`, `ilk_token_ms`, `ilk_ses_ms` (STT başı → ilk TTS bitişi), `arac_dogru`, `stt_metin`. Çıktı `benchmark/reports/v2_uctan_uca_<zaman>.json` + özet satırı: medyan/p90 `ilk_ses_ms` (sohbet ve araçlı ayrı), araç doğruluğu.

```python
"""Farabi 2.0 uçtan uca gecikme ölçümü (ses → STT → Qwen → TTS). Sınıfa gitmeden önce."""
import io, json, statistics, sys, time, urllib.request, wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import v2_arac_testi as t  # noqa: E402

SES = "http://bilgehan.local:8060"
OLLAMA = "http://localhost:11434"
YEREL_KURALLAR = ("\n\n[YEREL SES KURALLARI] Konuşma diliyle, en fazla 2-3 kısa cümleyle cevap ver. "
                  "Selamlaşma ve sohbette HİÇBİR ARAÇ ÇAĞIRMA.")


def post(url, veri, tip):
    r = urllib.request.Request(url, data=veri, headers={"Content-Type": tip})
    with urllib.request.urlopen(r, timeout=30) as y:
        return y.read()


def tts(metin):
    return post(f"{SES}/tts", json.dumps({"metin": metin}).encode(), "application/json")


def yeniden_ornekle_16k(wav24):
    with wave.open(io.BytesIO(wav24)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32)
    y = np.interp(np.arange(0, len(x), 1.5), np.arange(len(x)), x).astype("<i2")
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(y.tobytes())
    return b.getvalue()


def bir_tur(cumle, kip, beklenen, araclar):
    ogretmen = yeniden_ornekle_16k(tts(cumle))
    t0 = time.perf_counter()
    metin = json.loads(post(f"{SES}/stt", ogretmen, "audio/wav"))["metin"]
    stt_ms = (time.perf_counter() - t0) * 1000
    govde = {"model": "qwen3.8:27b", "stream": True, "think": False, "tools": araclar,
             "messages": [{"role": "system", "content": t.PROMPTLAR[kip] + YEREL_KURALLAR},
                          {"role": "user", "content": metin}]}
    r = urllib.request.Request(f"{OLLAMA}/api/chat", data=json.dumps(govde).encode(),
                               headers={"Content-Type": "application/json"})
    ilk_token = ilk_ses = None
    tampon, secilen = "", None
    with urllib.request.urlopen(r, timeout=120) as y:
        for satir in y:
            o = json.loads(satir)
            m = o.get("message") or {}
            if (m.get("content") or m.get("tool_calls")) and ilk_token is None:
                ilk_token = (time.perf_counter() - t0) * 1000
            if m.get("tool_calls") and ilk_ses is None:
                secilen = m["tool_calls"][0]["function"]["name"]
                tts("Hemen bakıyorum hocam.")
                ilk_ses = (time.perf_counter() - t0) * 1000
            tampon += m.get("content") or ""
            if ilk_ses is None and any(p in tampon for p in ".!?") and len(tampon) >= 12:
                tts(tampon.strip())
                ilk_ses = (time.perf_counter() - t0) * 1000
            if o.get("done"):
                break
    if ilk_ses is None and tampon.strip():
        tts(tampon.strip()); ilk_ses = (time.perf_counter() - t0) * 1000
    return {"cumle": cumle, "stt_metin": metin, "stt_ms": round(stt_ms), "ilk_token_ms": round(ilk_token or -1),
            "ilk_ses_ms": round(ilk_ses or -1), "beklenen": beklenen, "secilen": secilen,
            "dogru": secilen == beklenen}


def main():
    araclar = {k: t.build_tools_payload(k) for k in ("ogretmenli", "talimat")}
    sonuc = []
    for test in t.TEST_CUMLELERI:
        cumle, kip, beklenen = test[0], test[1], test[2]
        r = bir_tur(cumle, kip, beklenen, araclar[kip])
        print(json.dumps(r, ensure_ascii=False), flush=True)
        sonuc.append(r)
    sohbet = [r["ilk_ses_ms"] for r in sonuc if r["beklenen"] is None]
    aracli = [r["ilk_ses_ms"] for r in sonuc if r["beklenen"] is not None]
    ozet = {"sohbet_medyan_ms": statistics.median(sohbet), "aracli_medyan_ms": statistics.median(aracli),
            "dogruluk": sum(r["dogru"] for r in sonuc) / len(sonuc)}
    print(ozet)
    yol = Path(__file__).parent / "reports" / f"v2_uctan_uca_{time.strftime('%Y%m%d_%H%M%S')}.json"
    yol.write_text(json.dumps({"ozet": ozet, "sonuc": sonuc}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

`TEST_CUMLELERI` elemanlarının yapısını önce oku (`sed -n 126,160p benchmark/v2_arac_testi.py`); ilk üç alan (cümle, kip, beklenen) değilse `main()`'deki ayrıştırmayı ona göre düzelt.

- [ ] **Step 2: Çalıştır** — `cd ~/farabi-v2/benchmark && ~/farabi/benchmark/venv/bin/python v2_uctan_uca.py`
Expected (spec hedefleri): sohbet medyan `ilk_ses_ms` ≤ 3000; araçlı turda kalıp ≤ 1000 ms sonra (STT+araç kararı süresi raporlanır); doğruluk ≥ 0,90. Tutmazsa sonuç DECISIONS.md'ye yazılır, pilot öncesi kullanıcıya sunulur.

- [ ] **Step 3: Commit** (`benchmark/v2_uctan_uca.py` + rapor JSON, mesaj `benchmark: Farabi 2.0 uçtan uca gecikme ölçümü`).

---

### Task 13: Pilot — 9-A (Opus + kullanıcı)

- [ ] **Step 1:** Kullanıcı onayıyla `git push origin v2-yerel-ses`.
- [ ] **Step 2:** 9-A'nın günlük `farabiguncelle.sh`'i master'a `reset --hard` yapar — pilot süresince 9-A'da dalı izleyecek şekilde ayarlanır: `server/tahta-ssh.sh 9-A "cat ~/farabi/farabiguncelle.sh"` ile betiği oku, dal adını değişkenleştiren minimal değişikliği kullanıcıya sun (bu adım 9-A'ya özel, master betiği değişmez).
- [ ] **Step 3:** 9-A `config/api_keys.json`'a `"ses_modu": "yerel"` (SSH, `config_dagit.sh` değil — tek tahta, tek alan; önce yedek `api_keys.json.v1-yedek`).
- [ ] **Step 4:** Öğretmen eşliğinde 1 ders. Sonra: `server/tahta-ssh.sh 9-A "grep -E 'yerel|TTS|STT|Qwen' ~/farabi/repo/client/logs/farabi.log | tail -200"` + ders transkripti; `journalctl -u farabi2-ses` (Bilgehan). Tur gecikmesi, araç seçimi, hatalar DECISIONS.md'ye.
- [ ] **Step 5:** Geri dönüş provası: `"ses_modu": "gemini"` → Farabi Gemini ile açılıyor mu (aynı ders gününde, ders dışında).

---

## Self-review notları

- Spec kapsamı: bas-konuş (T11), STT/TTS servisi (T1-5), Qwen araçlı akış (T9-10), metin düzeltme (T6), cümle bölücü (T7), servis kapalı uyarısı (T10 testi + T11 run), riskli araç onayı (T10), 3 araç sınırı (T10), zaman aşımları (T8/T9), kalıp cümleler (T2/T10), görsel okuma bulutta (T11 `ekrani_modele_gonder → False` ile mevcut OCR yolu), v1 korunur (T11 varsayılan `gemini`, alt sınıf), testler (T2-12), pilot (T13). Uyandırma kelimesi, söz kesme, yerel görsel, merkezi kapı: kapsam dışı.
- Review Focus → testler: (1) T3 `test_halusinasyon` + T10 `test_bos_stt_qwene_gitmez`; (2) T10 `test_iptal_eski_cumleler_calmaz`; (3) T9 `test_arac_cagrisi_dict_ve_string_arguman`, `test_bozuk_string_arguman_bos_dict`; (4) T6 sıra sayısı + T7 kısaltma testleri; (5) T10 `test_tts_hatasi_metin_gosterilir_ve_servis_kapali_uyarisi`.
