import io
import wave

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
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(np.array([[1000, 3000]] * 10, dtype=np.int16).tobytes())
    y, sr = wav_coz(buf.getvalue())
    assert sr == 16000 and y.ndim == 1 and len(y) == 10
