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
