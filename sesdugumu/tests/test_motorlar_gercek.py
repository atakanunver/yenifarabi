import time

import numpy as np
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
    assert stt.coz(wav_kodla(np.zeros(16000, dtype=np.float32), 16000)) == ""
