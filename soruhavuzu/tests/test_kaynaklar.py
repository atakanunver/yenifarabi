from soruhavuzu import dersler, kaynaklar


def test_ders_anahtari():
    assert dersler.ders_anahtari("Türk Dili ve Edebiyatı") == "edebiyat"
    assert dersler.ders_anahtari("Temel Matematik") == "matematik"
    assert dersler.ders_anahtari("İnkılap Tarihi ve Atatürkçülük") == "tarih"
    assert dersler.ders_anahtari("Din Kültürü ve Ahlak Bilgisi") == "din"
    assert dersler.ders_anahtari("Beden Eğitimi") is None


def test_dosyadan_cozumle():
    assert dersler.dosyadan_cozumle("12sinif_fizik_8.pdf") == (12, "fizik")
    assert dersler.dosyadan_cozumle("12.sınıf.fizik.00_Cevap_Anahtari.pdf") == (
        12,
        "fizik",
    )
    assert dersler.dosyadan_cozumle("12.edebiyat.41_Cevap_Anahtari.pdf") == (
        12,
        "edebiyat",
    )
    assert dersler.dosyadan_cozumle("202582694327111-biyoloji.pdf") == (
        None,
        "biyoloji",
    )
    assert dersler.dosyadan_cozumle("13.pdf") == (None, None)


class SahteImlec:
    def __init__(self, satirlar):
        self.satirlar = satirlar

    def execute(self, *a):
        pass

    def fetchall(self):
        return self.satirlar

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class SahteBaglanti:
    def __init__(self, satirlar):
        self.satirlar = satirlar

    def cursor(self, **k):
        return SahteImlec(self.satirlar)


def test_kitap_gruplari_sayfa_araligi_ve_sinir():
    # (kitap_id, sinif, ders, sayfa_no, metin)
    satirlar = [
        (36, 12, "Matematik", 10, "a" * 1000),
        (36, 12, "Matematik", 11, "b" * 1000),
        (36, 12, "Matematik", 12, "c" * 500),
        (5, 10, "Biyoloji", 3, "d" * 300),
    ]
    g = list(kaynaklar.kitap_gruplari(SahteBaglanti(satirlar), grup_karakter=1800))
    assert [x["anahtar"] for x in g] == [
        "kitap:36:10-10",
        "kitap:36:11-12",
        "kitap:5:3-3",
    ]
    assert g[0]["etiket"] == "Matematik 12, s. 10" and g[0]["ders"] == "matematik"
    assert g[2]["sinif"] == 10
