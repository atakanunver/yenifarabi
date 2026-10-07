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
