"""Gerçek ses motorları. Ağır importlar sınıf içinde — saf testler GPU'suz koşsun."""
import os
import re
import threading

os.environ.setdefault("CUDA_DEVICE_ORDER", "PCI_BUS_ID")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")

from .sesler import wav_coz, wav_kodla  # noqa: E402

# Whisper'ın sessizlik/gürültüde uydurduğu bilinen kalıplar (YouTube altyazı artığı).
_HALUSINASYON = re.compile(
    r"altyaz|izlediğiniz için|abone ol|beğenmeyi unutma|kanalıma|teşekkürler izlediğiniz",
    re.IGNORECASE,
)
_ANLAMLI = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]{2,}")
_DOLGU = {"hmm", "hı", "ıı", "eee", "aa"}


def halusinasyon_mu(metin: str) -> bool:
    m = (metin or "").strip()
    if not _ANLAMLI.search(m):
        return True
    if m.lower().strip(".!? ") in _DOLGU:
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
