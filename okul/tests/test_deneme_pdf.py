"""Deneme PDF okuyucu: saf ayrıştırma işlevleri. Tüm veri sahte."""

from scripts import deneme_pdf_oku as o


def test_cevap_durumlari_buyuk_dogru_kucuk_yanlis_bosluk_bos():
    assert o.cevap_durumlari("AcC ", "ABCD") == ["d", "y", "d", "b"]


def test_cevap_durumlari_uyumsuz_anahtar_none():
    # büyük harf anahtarla uyuşmuyor -> güvenilmez
    assert o.cevap_durumlari("AXC", "ABC") is None
    # küçük harf anahtarla aynı -> güvenilmez
    assert o.cevap_durumlari("aBC", "ABC") is None


def test_cevap_durumlari_kisa_cevap_sag_bos_doldurulur():
    assert o.cevap_durumlari("AB", "ABC") == ["d", "d", "b"]


def test_kurum_bolumleri_a_indeksi_sifirlaninca_yeni_bolum():
    satirlar = [
        ["A-1\nB-2", "Okuma\nbecerisi", "B"],
        ["A-2\nB-1", "Dil bilgisi", "D"],
        ["A-1\nB-1", "Eski Çağ", "E"],
    ]
    b = o.kurum_bolumleri([[["Soru", "Kazanım"], r] for r in satirlar])
    assert [len(x) for x in b] == [2, 1]
    assert b[0][0] == {"a": 1, "b": 2, "kazanim": "Okuma becerisi", "dc": "B"}


def test_beklenen_anahtar_kitapcik_b():
    bolum = [
        {"a": 1, "b": 2, "kazanim": "X", "dc": "B"},
        {"a": 2, "b": 1, "kazanim": "Y", "dc": "D"},
    ]
    assert o.beklenen_anahtar(bolum, "B") == "DB"
    assert o.beklenen_anahtar(bolum, "A") == "BD"


def test_kazanim_ozeti_kazanima_gore_toplar():
    bolum = [
        {"a": 1, "b": 1, "kazanim": "Paragraf", "dc": "A"},
        {"a": 2, "b": 2, "kazanim": "Paragraf", "dc": "B"},
        {"a": 3, "b": 3, "kazanim": "Dil", "dc": "C"},
    ]
    ozet = o.kazanim_ozeti(bolum, "A", ["d", "y", "b"], ders_araliklari=[("Türkçe", 1, 3)])
    assert ozet == [
        {"ders": "Türkçe", "kazanim": "Paragraf", "d": 1, "y": 1, "b": 0},
        {"ders": "Türkçe", "kazanim": "Dil", "d": 0, "y": 0, "b": 1},
    ]


def test_ogrenci_basligi_sinif_no_ad_ve_toplam():
    metin = "x\n11-A - 7\nAYŞE DENEME 120 67 17 36 62,75 Sizin yeriniz\n(1.)"
    b = o.ogrenci_basligi(metin)
    assert b == {
        "sinif": "11-A",
        "okul_no": 7,
        "ad_soyad": "AYŞE DENEME",
        "toplam_net": 62.75,
    }
    assert o.ogrenci_basligi("alakasız metin") is None


def test_ders_satiri_virgullu_net():
    assert o.ders_satiri(["Tarih-1", "", "5", "3", "2", "0", "2,50", "% 50"]) == (
        "Tarih-1",
        {"d": 3, "y": 2, "b": 0, "net": 2.5},
    )
    assert o.ders_satiri(["Cevap Anahtarı", "B", "ABC"]) is None


def test_ders_satiri_bozuk_hucre_none():
    assert o.ders_satiri(["a", "1", "2", "3", "4", "Matematik-1", "% 5"]) is None


def test_secmeli_ayikla_secilmeyen_ders_dusurulur():
    din = {"d": 3, "y": 1, "b": 1, "net": 2.75}
    bos = {"d": 0, "y": 0, "b": 5, "net": 0.0}
    sec = {"d": 2, "y": 2, "b": 1, "net": 1.5}
    assert o.secmeli_ayikla({"Din Kül. ve Ahl. Bil.": din, "Felsefe (Seçmeli)": bos}) == {"Felsefe (Seçmeli)"}
    assert o.secmeli_ayikla({"Din Kül. ve Ahl. Bil.": bos, "Felsefe (Seçmeli)": sec}) == {"Din Kül. ve Ahl. Bil."}
    # ikisi de boşsa yalnız seçmeli düşer; ikisi de doluysa ikisi de kalır
    assert o.secmeli_ayikla({"Din Kül. ve Ahl. Bil.": bos, "Felsefe (Seçmeli)": bos}) == {"Felsefe (Seçmeli)"}
    assert o.secmeli_ayikla({"Din Kül. ve Ahl. Bil.": din, "Felsefe (Seçmeli)": sec}) == set()
    assert o.secmeli_ayikla({"Fizik": din}) == set()


def _tablo_satiri(ad, soru, d, y, b, net):
    return [ad, "", str(soru), str(d), str(y), str(b), net, "% 50"]


def test_sayfa_ogrencisi_turkceyi_tutar_toplam_satirlarini_atar_secilmeyeni_dusurur():
    metin = "11-A - 7\nAYŞE DENEME 120 67 17 36 62,75 Sizin yeriniz"
    tablolar = [
        [_tablo_satiri("TYT Türkçe", 40, 31, 4, 5, "30,00")],
        [_tablo_satiri("TYT Sosyal", 20, 12, 6, 2, "10,50"), _tablo_satiri("Tarih-1", 5, 3, 2, 0, "2,50")],
        [_tablo_satiri("Din Kül. ve Ahl. Bil.", 5, 4, 1, 0, "3,75"), _tablo_satiri("Felsefe (Seçmeli)", 5, 0, 0, 5, "0,00")],
    ]
    k = o.sayfa_ogrencisi(metin, tablolar, [])
    dersler = k["veri"]["dersler"]
    assert dersler == {"Türkçe": 30.0, "Tarih-1": 2.5, "Din Kül. ve Ahl. Bil.": 3.75}
    assert k["veri"]["ders_dyb"]["Türkçe"] == [31, 4, 5]
    assert "Felsefe (Seçmeli)" not in k["veri"]["ders_dyb"]


def test_sayfa_ogrencisi_matematik_tamamen_bossa_alt_satirlar_sifir_eklenir():
    metin = "11-B - 7\nAYŞE DENEME 120 40 10 70 30,00 Sizin yeriniz"
    tablolar = [[_tablo_satiri("TYT Türkçe", 40, 31, 4, 5, "30,00")], [_tablo_satiri("TYT Matematik", 40, 0, 0, 40, "0,00")]]
    d = o.sayfa_ogrencisi(metin, tablolar, [])["veri"]
    assert d["dersler"]["Matematik-1"] == 0.0 and d["dersler"]["Geometri"] == 0.0
    assert d["ders_dyb"]["Matematik-1"] == [0, 0, 30] and d["ders_dyb"]["Geometri"] == [0, 0, 10]


def test_sayfa_ogrencisi_matematik_cevaplanmissa_toplam_satirindan_eklenmez():
    metin = "11-B - 7\nAYŞE DENEME 120 40 10 70 30,00 Sizin yeriniz"
    tablolar = [[_tablo_satiri("TYT Matematik", 40, 12, 4, 24, "11,00"), _tablo_satiri("Matematik-1", 30, 8, 4, 18, "7,00")]]
    d = o.sayfa_ogrencisi(metin, tablolar, [])["veri"]
    assert d["ders_dyb"]["Matematik-1"] == [8, 4, 18] and "Geometri" not in d["ders_dyb"]


def test_siralama_sube_kurum_genel_ve_yuzdelik():
    metin = "Şube Kurum İlçe İl Genel\nÖğrenci Sıra No 3 6 6 6 5045 % 51,02\nSınava Katılan Öğrenci Sayısı 7 22 22 22 9889\n"
    sr = o.siralama(metin)
    assert sr["sube"] == [3, 7] and sr["kurum"] == [6, 22] and sr["genel"] == [5045, 9889]
    assert sr["yuzdelik"] == 51.02


def test_siralama_yoksa_none():
    assert o.siralama("Sizin yeriniz") is None
