"""voice_node/stt_paylasimli.py — Faz 1b: süreç genelinde paylaşımlı Whisper.

`WhisperSTTService.__init__` her örnekte `self._load()` çağırıp YENİ bir
`faster_whisper.WhisperModel` yüklüyor (`services/whisper/stt.py:316` —
`__init__` içinde doğrudan çağrı, ve `:337-349` — `_load` gövdesi). Çok
tahtalı bir kurulumda (Faz 1c) her oturum kendi modelini yüklerse GPU0'daki
VRAM oturum sayısıyla ÇARPILIR (ölçüm: tek yükleme ~1.18 GB, bkz. bitiş
raporu). `SttPaylasimli`, `_load`'u EZEREK süreç genelinde TEK bir
`WhisperModel`'i (modül seviyesi, kilitli) paylaşır; `faster-whisper`'ın
`WhisperModel.transcribe()` çağrısı zaten iş parçacığı güvenli (GIL altında,
`num_workers` CTranslate2'nin kendi iç thread pool'u) — tek modelin birden
çok oturumdan eşzamanlı çağrılması güvenli.
"""

from __future__ import annotations

import threading

from faster_whisper import WhisperModel
from pipecat.services.whisper.stt import WhisperSTTService

_KILIT = threading.Lock()
_PAYLASIMLI_MODEL: WhisperModel | None = None
_PAYLASIMLI_ANAHTAR: tuple[str, str, str] | None = None
_ISINDI = False


def _model_al(model_dir: str, device: str, compute_type: str) -> WhisperModel:
    global _PAYLASIMLI_MODEL, _PAYLASIMLI_ANAHTAR
    anahtar = (model_dir, device, compute_type)
    with _KILIT:
        if _PAYLASIMLI_MODEL is None:
            _PAYLASIMLI_MODEL = WhisperModel(
                model_dir, device=device, compute_type=compute_type, num_workers=2
            )
            _PAYLASIMLI_ANAHTAR = anahtar
        elif _PAYLASIMLI_ANAHTAR != anahtar:
            raise RuntimeError(
                f"SttPaylasimli: farklı model parametreleriyle ikinci bir "
                f"yükleme istendi ({anahtar} != {_PAYLASIMLI_ANAHTAR}) — süreç "
                f"genelinde TEK model paylaşılıyor, bu desteklenmiyor."
            )
        return _PAYLASIMLI_MODEL


def isindir(model_dir: str, device: str, compute_type: str) -> None:
    """Süreç başına BİR kez 1 sn sessizlikle ön-ısıtma (plan) — ilk gerçek
    basışta CUDA/cuBLAS kernel derleme gecikmesi yaşanmasın diye."""
    global _ISINDI
    with _KILIT:
        if _ISINDI:
            return
        _ISINDI = True
    model = _model_al(model_dir, device, compute_type)
    sessizlik = b"\x00\x00" * (16000 * 1)  # 1 sn, 16 kHz, 16-bit mono sessizlik
    import numpy as np

    audio_float = np.frombuffer(sessizlik, dtype="int16").astype("float32") / 32768.0
    list(model.transcribe(audio_float, language="tr")[0])


class SttPaylasimli(WhisperSTTService):
    """`WhisperSTTService` alt sınıfı — `_load`'u ezerek süreç genelinde
    paylaşımlı modeli kullanır (plan `stt_paylasimli.py`)."""

    def _load(self):
        model_name = self._settings.model
        if not model_name:
            raise ValueError("SttPaylasimli: model dizini (settings.model) boş")
        self._model = _model_al(str(model_name), self._device, self._compute_type)
        unsupported = self._unsupported_language()
        if unsupported:
            raise ValueError(unsupported)
