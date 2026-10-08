"""kazanim_test_parse.py testleri — gerçek PDF'lerden kopyalanmış kısa metin
örnekleri (PDF/DB/ağ yok). Çalıştırma: pytest benchmark/test_kazanim_test_parse.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from kazanim_test_parse import (
    baslik_bilgisi_cikar,
    ders_dosya_adindan,
    sorulari_ayir,
)

TARIH_ILK = (
    "12. Sınıf\n12. Sınıf\nT.C. İnkılap Tarihi ve\nT.C. İnkılap Tarihi ve\n"
    "Atatürkçülük\nAtatürkçülük\n"
    "MEB    ●    Ölçme, Değerlendirme ve Sınav Hizmetleri Genel Müdürlüğü\n"
    "1.  Aşağıdakilerden hangisi doğrudur?\nA) a\nB) b\nC) c\nD) d\nE) e\n"
)
INGILIZCE_ILK = (
    "12th Grade\n12th Grade\nEnglish\nEnglish\n"
    "MEB    ●    Ölçme, Değerlendirme ve Sınav Hizmetleri Genel Müdürlüğü\n"
    "Music - 1\n1\nFor questions 1-4, choose the best word.\n"
    "1.  Judith\t\n: What was the jazz concert like?\nA) by\nB) so\n"
)
FIZIK_ILK = "1122.. SSıınnııff\nFFiizziikk\nMEB ● Ölçme\nÇembersel Hareketler – 1\n1. Soru\n"


def test_tarih_basligi():
    assert baslik_bilgisi_cikar(TARIH_ILK)[0] == 12
    assert ders_dosya_adindan("12sinif_tarih_1.pdf") == "Tarih"


def test_ingilizce_basligi():
    assert baslik_bilgisi_cikar(INGILIZCE_ILK) == (12, "İngilizce")
    assert ders_dosya_adindan("12sinif_ingilizce_7.pdf") == "İngilizce"


def test_ders_dosya_adi_digerleri():
    assert ders_dosya_adindan("12sinif_biyoloji_3.pdf") == "Biyoloji"
    assert ders_dosya_adindan("12sinif_cografya_cog_ca_mayis.pdf") == "Coğrafya"
    assert ders_dosya_adindan("1.pdf") is None
    assert ders_dosya_adindan("202582695425908-tarih.pdf") is None


def test_fizik_regresyon():
    assert baslik_bilgisi_cikar(FIZIK_ILK) == (12, "Fizik")


KIMYA = (
    "1.\t\nBirinci soru metni\nA) a\nB) b\nC) c\nD) d\nE) e\n"
    "2.\t\nAşağıdaki pil sisteminde\nCu(k)\n1. kap\n25°C 1M\n2. kap\nKNO3\n"
    "A) x\nB) y\nC) z\nD) t\nE) u\n"
    "3.\t\nÜçüncü\nA) 1\nB) 2\nC) 3\nD) 4\nE) 5\n"
)


def test_kimya_alt_madde_soru_basi_degil():
    s = sorulari_ayir(KIMYA)
    assert [x["soru_no"] for x in s] == [1, 2, 3]
    assert "1. kap" in s[1]["soru_metni"] and "2. kap" in s[1]["soru_metni"]
    assert list(s[1]["secenekler"]) == list("ABCDE")


def test_konu_basligi_20_yuzyil_soru_sanilmaz():
    metin = (
        "6.  Altinci\nA) a\nB) b\nC) c\nD) d\nE) e\n"
        "20. Yüzyıl Başlarında Osmanlı Devleti ve Dünya - 1\n1\n"
        "MEB    ●    Ölçme\n12. Sınıf\n12. Sınıf\n"
        "7.  Yedinci\nA) a\nB) b\nC) c\nD) d\nE) e\n"
    )
    s = sorulari_ayir(metin)
    assert [x["soru_no"] for x in s] == [6, 7]
    assert list(s[1]["secenekler"]) == list("ABCDE")


def test_ingilizce_sorular_bes_sik():
    metin = (
        "For questions 1-4, choose the best word.\n"
        "1.  Judith\t\n: What was it like?\nSamantha\t : I disagree, - - - -.\n"
        "A) by\nB) so\nC) but\nD) and\nE) however\n"
        "2.  Learning to play\nA) one\nB) two\nC) three\nD) four\nE) five\n"
    )
    s = sorulari_ayir(metin)
    assert [x["soru_no"] for x in s] == [1, 2]
    assert s[0]["secenekler"]["E"] == "however"
    assert "disagree" in s[0]["soru_metni"]


def test_ingilizce_ortak_metin_ve_tek_basina_numara():
    metin = (
        "7.\t\nMark: Have you watched it?\n"
        "A) a\nB) b\nC) c\nD) d\nE) e\n"
        "For questions 8-9, choose the best word.\n"
        "Keep them (8) ---- mind.\n"
        "8.\nA) at\nB) in\nC) on\nD) over\nE) about\n"
        "9.\t\nA) if\nB) so\nC) but\nD) before\nE) even though\n"
    )
    s = sorulari_ayir(metin)
    assert [x["soru_no"] for x in s] == [7, 8, 9]
    assert s[0]["secenekler"]["E"] == "e"  # ortak metin 7'nin E şıkkına yapışmadı
    assert "Keep them (8)" in s[1]["soru_metni"]
    assert list(s[2]["secenekler"]) == list("ABCDE")
