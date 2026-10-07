from sesdugumu.onbellek import Onbellek, anahtar
from sesdugumu.kaliplar import KALIPLAR


def test_anahtar_bosluk_ve_buyuk_harf_duyarsiz():
    assert anahtar("  Hemen  bakıyorum hocam. ") == anahtar("hemen bakıyorum hocam.")


def test_anahtar_turkce_i_dogru_kucultulur():
    assert anahtar("İYİ") == anahtar("iyi")
    assert anahtar("IŞIK") == anahtar("ışık")


def test_al_koy():
    o = Onbellek()
    assert o.al("Tamam.") is None
    o.koy("Tamam.", b"RIFF...")
    assert o.al("  tamam. ") == b"RIFF..."
    assert len(o) == 1


def test_kaliplar_bos_degil_ve_noktalama_ile_biter():
    assert len(KALIPLAR) >= 20
    for metin in KALIPLAR.values():
        assert metin.strip()[-1] in ".?!"
