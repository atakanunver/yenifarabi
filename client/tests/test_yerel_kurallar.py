from core.yerel_ayar import YEREL_KURALLAR


def test_sohbet_ornekleri_kuralda():
    # Uçtan uca ölçümde bu iki sohbet cümlesi gereksiz araç çağırdı (yoklama_al, yks_sorulari).
    assert "derse başlayalım mı" in YEREL_KURALLAR
    assert "kim cevap vermek ister" in YEREL_KURALLAR


def test_yerel_main_ayni_kurali_kullanir():
    import yerel_main
    assert yerel_main._YEREL_KURALLAR is YEREL_KURALLAR
