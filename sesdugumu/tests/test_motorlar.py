import pytest

from sesdugumu.motorlar import halusinasyon_mu


@pytest.mark.parametrize("metin", [
    "", "   ", ".", "Altyazı M.K.", "İzlediğiniz için teşekkürler.",
    "Abone olmayı unutmayın", "Altyazılar: Topluluk", "...", "Hmm.",
])
def test_halusinasyon(metin):
    assert halusinasyon_mu(metin)


@pytest.mark.parametrize("metin", [
    "Mitoz bölünme nedir?", "Ekrandaki soruyu oku.", "Evet.", "Teşekkürler Farabi.",
])
def test_gercek_konusma(metin):
    assert not halusinasyon_mu(metin)
