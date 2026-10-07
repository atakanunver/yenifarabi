from core.cumle_bolucu import CumleBolucu


def parca_parca(metin, boyut=3):
    b = CumleBolucu()
    cikti = []
    for i in range(0, len(metin), boyut):
        cikti += b.ekle(metin[i:i + boyut])
    return cikti + b.bitir()


def test_temel():
    assert parca_parca("Harika bir soru! Mitoz dört evreden oluşur. Önce profaz gelir.") == [
        "Harika bir soru!", "Mitoz dört evreden oluşur.", "Önce profaz gelir."]


def test_kisaltma_ve_ondalik_bolunmez():
    c = parca_parca("Dr. Ahmet 3.5 saat çalıştı vb. şeyler yaptı. Sonra gitti ve uyudu sonunda.")
    assert c[0] == "Dr. Ahmet 3.5 saat çalıştı vb. şeyler yaptı."


def test_sira_sayisi_bolunmez():
    c = parca_parca("Bugün 12. sınıf konusuna bakacağız. Hazır mısınız çocuklar?")
    assert c[0] == "Bugün 12. sınıf konusuna bakacağız."


def test_soru_ve_unlem():
    assert parca_parca("Anladınız mı? Çok güzel!") == ["Anladınız mı?", "Çok güzel!"]


def test_bitir_noktasiz_kalan():
    assert parca_parca("Noktasız bir cümle") == ["Noktasız bir cümle"]


def test_bos():
    b = CumleBolucu()
    assert b.ekle("") == [] and b.bitir() == []
