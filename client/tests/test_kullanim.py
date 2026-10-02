"""core/kullanim.py — Gemini Live token ayrıştırma ve toplama. Ağ/SDK yok."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import kullanim


class _Mod:
    """SDK enum'unu taklit eder (`.name` taşır)."""

    def __init__(self, name):
        self.name = name


def _det(modality, n):
    return SimpleNamespace(modality=modality, token_count=n)


def _usage(**kw):
    return SimpleNamespace(**kw)


def test_ayristir_modalite_ve_alanlar():
    u = _usage(
        prompt_token_count=18430,
        prompt_tokens_details=[_det(_Mod("AUDIO"), 2100), _det("MediaModality.TEXT", 16330),
                               _det(_Mod("IMAGE"), 7)],
        response_token_count=410,
        response_tokens_details=[_det("modality.audio", 400), _det("TEXT", 10)],
        tool_use_prompt_token_count=5,
        thoughts_token_count=3,
        cached_content_token_count=9,
        total_token_count=18840,
    )
    d = kullanim.ayristir(u)
    assert d == {
        "girdi": 18430, "girdi_ses": 2100, "girdi_metin": 16330,
        "yanit": 410, "yanit_ses": 400, "yanit_metin": 10,
        "arac": 5, "dusunce": 3, "onbellek": 9, "toplam": 18840,
    }


def test_ayristir_none_ve_eksik_alanlar_sifir():
    d = kullanim.ayristir(_usage(prompt_token_count=None, prompt_tokens_details=None,
                                 total_token_count=None))
    assert set(d.values()) == {0}
    assert set(kullanim.ayristir(SimpleNamespace()).values()) == {0}


def test_sayac_toplar_ve_sifirlar():
    s = kullanim.Sayac()
    assert s.bos
    d1 = s.ekle(_usage(prompt_token_count=100, response_token_count=10, total_token_count=110))
    s.ekle(_usage(prompt_token_count=300, response_token_count=20, total_token_count=320))
    assert d1["girdi"] == 100
    assert not s.bos
    assert s.mesaj == 2
    assert s.toplam["girdi"] == 400
    assert s.toplam["yanit"] == 30
    assert s.toplam["toplam"] == 430
    assert s.en_buyuk_girdi == 300
    s.ekle(_usage(prompt_token_count=50))
    assert s.en_buyuk_girdi == 300
    s.sifirla()
    assert s.bos and s.en_buyuk_girdi == 0 and s.toplam["girdi"] == 0


def test_binlik_ayraci_ve_satir_ozet():
    assert kullanim._bin(0) == "0"
    assert kullanim._bin(410) == "410"
    assert kullanim._bin(18430) == "18.430"
    assert kullanim._bin(1234567) == "1.234.567"
    d = kullanim.ayristir(_usage(
        prompt_token_count=18430,
        prompt_tokens_details=[_det("AUDIO", 2100), _det("TEXT", 16330)],
        response_token_count=410, total_token_count=18840))
    assert kullanim.satir(d) == (
        "girdi=18.430 (ses 2.100 / metin 16.330) yanit=410 arac=0 toplam=18.840")
    s = kullanim.Sayac()
    s.ekle(_usage(prompt_token_count=19800, total_token_count=20000))
    assert s.ozet() == (
        "mesaj=1 girdi=19.800 (ses 0 / metin 0) yanit=0 arac=0 "
        "toplam=20.000 en_buyuk_baglam=19.800")
