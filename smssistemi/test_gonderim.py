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


def test_kisisellestir_yer_tutuculari_degistirir():
    assert (
        gonderim.kisisellestir("Sayın {isim}, {ogrenci_adi} bugün gelmedi.", "Fatma Hanım", "Ali Çimen")
        == "Sayın Fatma Hanım, Ali Çimen bugün gelmedi."
    )
    # Geriye uyumluluk: ogrenci_adi verilmezse sadece {isim}
    assert gonderim.kisisellestir("Merhaba {isim}", "Ahmet") == "Merhaba Ahmet"
    # {ogrenci_adi} boş string ile değiştirilir
    assert gonderim.kisisellestir("Öğr: {ogrenci_adi}", "Ali") == "Öğr: "


def test_rehber_dosyasindan_oku_csv_gecnis_baslik_taniz():
    icerik = "Öğrenci Adı Soyadı;Cep Telefonu\nAhmet Yılmaz;05551234567\nAyşe Kaya;5551234568\n".encode(
        "utf-8-sig"
    )
    sonuc = gonderim.rehber_dosyasindan_oku("liste.csv", icerik)
    assert sonuc == [
        {"ad_soyad": "Ahmet Yılmaz", "telefon": "05551234567", "sinif": None, "ogrenci_adi": None},
        {"ad_soyad": "Ayşe Kaya", "telefon": "05551234568", "sinif": None, "ogrenci_adi": None},
    ]


def test_rehber_dosyasindan_oku_sinif_sutununu_yakalar():
    icerik = "Ad Soyad,Telefon,Sınıf\nAhmet Yılmaz,05551234567,9-A\n".encode("utf-8-sig")
    sonuc = gonderim.rehber_dosyasindan_oku("liste.csv", icerik)
    assert sonuc == [
        {"ad_soyad": "Ahmet Yılmaz", "telefon": "05551234567", "sinif": "9-A", "ogrenci_adi": None}
    ]


def test_rehber_dosyasindan_oku_baslik_eslesmezse_ilk_iki_sutunu_kullanir():
    icerik = "Ahmet Yılmaz,05551234567\nAyşe Kaya,5551234568\n".encode("utf-8-sig")
    sonuc = gonderim.rehber_dosyasindan_oku("liste.csv", icerik)
    assert sonuc == [
        {"ad_soyad": "Ahmet Yılmaz", "telefon": "05551234567", "sinif": None, "ogrenci_adi": None},
        {"ad_soyad": "Ayşe Kaya", "telefon": "05551234568", "sinif": None, "ogrenci_adi": None},
    ]


def test_rehber_dosyasindan_oku_xlsx_calisir():
    import io

    import openpyxl

    calisma_kitabi = openpyxl.Workbook()
    sayfa = calisma_kitabi.active
    sayfa.append(["Adı Soyadı", "Telefon Numarası"])
    sayfa.append(["Ahmet Yılmaz", "05551234567"])
    tampon = io.BytesIO()
    calisma_kitabi.save(tampon)

    sonuc = gonderim.rehber_dosyasindan_oku("liste.xlsx", tampon.getvalue())
    assert sonuc == [
        {"ad_soyad": "Ahmet Yılmaz", "telefon": "05551234567", "sinif": None, "ogrenci_adi": None}
    ]


def test_rehber_dosyasindan_oku_ogrenci_adi_sutununu_tanir():
    icerik = "Veli Adı,Öğrenci Adı,Telefon\nFatma Çimen,Ali Çimen,05551234567\n".encode("utf-8-sig")
    sonuc = gonderim.rehber_dosyasindan_oku("liste.csv", icerik, tur="veli")
    assert sonuc == [
        {
            "ad_soyad": "Fatma Çimen",
            "telefon": "05551234567",
            "sinif": None,
            "ogrenci_adi": "Ali Çimen",
        }
    ]


def test_rehber_dosyasindan_oku_ogrenci_sutun_basligi_ile_ogrenciyi_alir():
    icerik = "Veli Adı,Öğrenci,Telefon\nMehmet Kaya,Zeynep Kaya,05559876543\n".encode("utf-8-sig")
    sonuc = gonderim.rehber_dosyasindan_oku("liste.csv", icerik, tur="veli")
    assert sonuc == [
        {
            "ad_soyad": "Mehmet Kaya",
            "telefon": "05559876543",
            "sinif": None,
            "ogrenci_adi": "Zeynep Kaya",
        }
    ]


def test_rehber_dosyasindan_oku_veli_yuklemesinde_veli_adi_yoksa_turetir():
    icerik = "Öğrenci Adı,Telefon\nAli Çimen,05551234567\n".encode("utf-8-sig")
    sonuc = gonderim.rehber_dosyasindan_oku("liste.csv", icerik, tur="veli")
    assert sonuc == [
        {
            "ad_soyad": "Ali Çimen Velisi",
            "telefon": "05551234567",
            "sinif": None,
            "ogrenci_adi": "Ali Çimen",
        }
    ]


def test_metinden_ayristir_3_parametre_ogrenci_adi():
    metin = "Fatma Çimen,05551234567,Ali Çimen\nAhmet Yılmaz,05551234568"
    gecerli, gecersiz = gonderim.metinden_ayristir(metin)
    assert gecerli == [
        ("Fatma Çimen", "05551234567", "Ali Çimen"),
        ("Ahmet Yılmaz", "05551234568"),
    ]
    assert gecersiz == []
