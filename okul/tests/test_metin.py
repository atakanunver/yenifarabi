import metin


def test_tr_kucuk():
    assert metin.tr_kucuk("İSMAİL IŞIK") == "ismail ışık"


def test_normalize_isim_bosluk_ve_harf():
    assert metin.normalize_isim("  Ensar   AYGENOĞLU ") == "ensar aygenoğlu"


def test_ilk_sifre_turkce_ve_cok_isimli():
    assert metin.ilk_sifre("Ayşe Nur Yılmaz") == "ayse123"
    assert metin.ilk_sifre("ÇAĞLA Öz") == "cagla123"
    assert metin.ilk_sifre("İbrahim Güneş") == "ibrahim123"
    assert metin.ilk_sifre("Ülkü Işık") == "ulku123"


def test_normalize_telefon():
    assert metin.normalize_telefon("0532 123 45 67") == "05321234567"
    assert metin.normalize_telefon("+90 532 123 4567") == "05321234567"
    assert metin.normalize_telefon("5321234567") == "05321234567"
    assert metin.normalize_telefon("905321234567") == "05321234567"
    assert metin.normalize_telefon("0212 123 45 67") is None
    assert metin.normalize_telefon("") is None
    assert metin.normalize_telefon(None) is None


def test_sinif_seviyesi():
    assert metin.sinif_seviyesi("9-A") == 9
    assert metin.sinif_seviyesi("12-B") == 12
