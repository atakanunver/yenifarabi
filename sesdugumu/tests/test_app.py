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
    r = c.post("/stt", content=b"bozuk", headers={"Content-Type": "audio/wav"})
    assert r.status_code == 400
