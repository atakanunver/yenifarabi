import asyncio
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


def test_oturum_adaptoru_metni_yerel_tura_yonlendirir():
    yerel_main = importlib.import_module("yerel_main")

    class SahteOturum:
        def __init__(self):
            self.turlar = []

        async def metin_turu(self, metin, kaynak="ogretmen"):
            self.turlar.append((metin, kaynak))

    async def senaryo():
        o = SahteOturum()
        a = yerel_main._OturumAdaptoru(o)
        await a.send_client_content(turns={"parts": [{"text": "[DERS] 10 dk kaldı"}]},
                                    turn_complete=True)
        await asyncio.sleep(0)
        return o.turlar

    assert asyncio.run(senaryo()) == [("[DERS] 10 dk kaldı", "sistem")]


def test_oturum_adaptoru_gorsel_turu_reddeder():
    yerel_main = importlib.import_module("yerel_main")
    a = yerel_main._OturumAdaptoru(object())
    with pytest.raises(RuntimeError):
        asyncio.run(a.send_client_content(
            turns={"role": "user", "parts": [{"text": "x"}, {"inline_data": {"data": b""}}]}))


def test_wav_donusumleri():
    yerel_main = importlib.import_module("yerel_main")
    pcm = b"\x01\x00\x02\x00" * 100
    assert yerel_main._wav_ayir(yerel_main._wav_yap(pcm)) == pcm
