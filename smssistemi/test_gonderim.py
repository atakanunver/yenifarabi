import gonderim


def test_normalize_phone_ulusal_format_degistirmez():
    assert gonderim.normalize_phone("05551234567") == "05551234567"


def test_normalize_phone_10_haneliyi_sifirla_tamamlar():
    assert gonderim.normalize_phone("5551234567") == "05551234567"


def test_normalize_phone_uluslararasi_00_prefiksini_artiya_cevirir():
    assert gonderim.normalize_phone("00905551234567") == "+905551234567"


def test_is_valid_phone_gecerli_ulusal():
    assert gonderim.is_valid_phone("05551234567") is True


def test_is_valid_phone_gecersiz_kisa():
    assert gonderim.is_valid_phone("0555123456") is False


def test_is_ascii_turkce_karakterde_false_doner():
    assert gonderim.is_ascii("merhaba İ") is False
    assert gonderim.is_ascii("merhaba") is True


def test_metinden_ayristir_karisik_satirlari_ayirir():
    metin = "Ahmet,05551234567\n123\nAyse,05551234568"
    gecerli, gecersiz = gonderim.metinden_ayristir(metin)
    assert gecerli == [("Ahmet", "05551234567"), ("Ayse", "05551234568")]
    assert gecersiz == ["123"]


def test_csv_ayristir_baslik_satirini_atlar():
    icerik = "isim,telefon\nAhmet Yilmaz,05551234567\n".encode("utf-8-sig")
    sonuc = gonderim.csv_ayristir(icerik)
    assert sonuc == [("Ahmet Yilmaz", "05551234567")]


def test_kisisellestir_yer_tutucuyu_degistirir():
    assert gonderim.kisisellestir("Merhaba {isim}", "Ahmet") == "Merhaba Ahmet"
