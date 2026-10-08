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


def test_ilk_parca_uzun_virgulde_kesilir():
    # Sohbette ilk ses gecikmesi: ilk tam cümlenin TTS'i ~2,5 sn sürüyordu.
    assert parca_parca("Günaydın sevgili çocuklarım, bugün mitoz bölünmeyi işleyeceğiz.") == [
        "Günaydın sevgili çocuklarım,", "bugün mitoz bölünmeyi işleyeceğiz."]


def test_kisa_virgulde_kesilmez():
    assert parca_parca("Evet, mitoz vücut hücrelerinde görülür.") == [
        "Evet, mitoz vücut hücrelerinde görülür."]


def test_yalniz_ilk_parca_virgulde_kesilir():
    c = parca_parca("Çok güzel bir soru sordun. Mitoz bölünmede kromozomlar eşlenir, sonra ayrılır.")
    assert c == ["Çok güzel bir soru sordun.", "Mitoz bölünmede kromozomlar eşlenir, sonra ayrılır."]


def test_ondalik_virgulde_kesilmez():
    assert parca_parca("Suyun yoğunluğu yaklaşık 1,5 değil tam bir gram.") == [
        "Suyun yoğunluğu yaklaşık 1,5 değil tam bir gram."]


def test_sayiyla_biten_cumle_bolunur():
    assert parca_parca("Cevap tam olarak 12. Şimdi ikinci soruya geçelim hep birlikte.") == [
        "Cevap tam olarak 12.", "Şimdi ikinci soruya geçelim hep birlikte."]


def test_buyuk_harfli_sira_sayisi_bolunmez():
    c = parca_parca("Bugün 2. Dünya Savaşı konusunu işleyeceğiz. Hazır mısınız?")
    assert c[0] == "Bugün 2. Dünya Savaşı konusunu işleyeceğiz."
