import pytest

from core.metin_duzelt import seslendirme_icin


@pytest.mark.parametrize("girdi,beklenen", [
    ("**Mitoz** bölünme", "Mitoz bölünme"),
    ("## Evreler", "Evreler"),
    ("- profaz\n- metafaz", "profaz, metafaz"),
    ("1) Profaz 2) Metafaz", "Profaz, Metafaz"),
    ("12. sınıf", "on ikinci sınıf"),
    ("9. sınıf biyoloji", "dokuzuncu sınıf biyoloji"),
    ("3. soru", "üçüncü soru"),
    ("1. ünite", "birinci ünite"),
    ("2. Dünya Savaşı", "ikinci Dünya Savaşı"),
    ("40. sayfa", "kırkıncı sayfa"),
    ("Cevap 12.", "Cevap 12."),
    ("x = `a+b`", "x = a+b"),
    ("Merhaba 😊 çocuklar", "Merhaba çocuklar"),
])
def test_seslendirme_icin(girdi, beklenen):
    assert seslendirme_icin(girdi) == beklenen


def test_cumle_sonundaki_sayi_sira_sayisi_olmaz():
    # Matematik cevabı: "x eşittir 5. Kontrol edelim." → "beşinci Kontrol" OKUNMAMALI.
    assert seslendirme_icin("Bu soruda x eşittir 5. Kontrol edelim.") == \
        "Bu soruda x eşittir 5. Kontrol edelim."
    assert seslendirme_icin("Cevap 12. Şimdi bakalım.") == "Cevap 12. Şimdi bakalım."


def test_buyuk_harfli_bilinen_sira_sayilari():
    assert seslendirme_icin("2. Dünya Savaşı") == "ikinci Dünya Savaşı"
