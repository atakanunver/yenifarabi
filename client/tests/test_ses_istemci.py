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
    assert o.cagri[0][1]["timeout"] == (2, 5)
    with pytest.raises(SesServisiHatasi):
        SesIstemci("http://x", SahteOturum(hata=requests.Timeout())).stt(b"RIFF")


def test_tts():
    o = SahteOturum(Yanit(govde=b"RIFFwav"))
    assert SesIstemci("http://x", o).tts("Merhaba.") == b"RIFFwav"
    assert o.cagri[0][1]["json"] == {"metin": "Merhaba."}
    with pytest.raises(SesServisiHatasi):
        SesIstemci("http://x", SahteOturum(Yanit(400))).tts("")


def test_baglanti_zaman_asimi_kisa():
    # Bilgehan tamamen kapalıyken (RST yok) her cümle 10 sn kilitlemesin.
    o = SahteOturum(Yanit(govde=b"WAV"))
    SesIstemci("http://x", oturum=o).tts("merhaba")
    assert o.cagri[-1][1]["timeout"] == (2, 10)
