"""PDF öğrencisini DB öğrencisine eşleme kuralları. Tüm veri sahte."""

from scripts import deneme_eslestir as e

DB = [
    {"okul_no": 10, "ad_soyad": "Ayşe Nur Kaya", "sinif": "11-A"},
    {"okul_no": 20, "ad_soyad": "Alperen Mevlüt Demir", "sinif": "11-B"},
    {"okul_no": 30, "ad_soyad": "Zeynep Su Aydın", "sinif": "11-A"},
    {"okul_no": 31, "ad_soyad": "Zeynep Su Aydın", "sinif": "11-C"},
    {"okul_no": 40, "ad_soyad": "Esila İrem Mayda", "sinif": "11-B"},
    {"okul_no": 50, "ad_soyad": "Kübra Nur Emekli", "sinif": "11-B"},
]


def s(no, ad, sinif):
    return {"okul_no": no, "ad_soyad": ad, "sinif": sinif, "veri": {}}


def test_tam_eslesme_aynen_kalir():
    yeni, r = e.eslestir([s(10, "AYŞE NUR KAYA", "11-A")], DB)
    assert yeni[0]["okul_no"] == 10 and r["tam"] == 1


def test_no_sifir_tek_tam_ad_eslesmesi_dbden_kimlik_alir():
    yeni, r = e.eslestir([s(0, "AYŞE NUR KAYA", "11-A")], DB)
    assert (yeni[0]["okul_no"], yeni[0]["ad_soyad"], yeni[0]["sinif"]) == (10, "Ayşe Nur Kaya", "11-A")
    assert r["adla"] == 1


def test_no_sifir_xx_sube_tek_ad_yine_eslesir():
    yeni, _ = e.eslestir([s(0, "AYŞE NUR KAYA", "12-XX")], DB)
    assert yeni[0]["okul_no"] == 10 and yeni[0]["sinif"] == "11-A"


def test_no_sifir_ad_birden_cok_ogrenciyle_eslesirse_atlanir():
    yeni, r = e.eslestir([s(0, "ZEYNEP SU AYDIN", "11-A")], DB)
    assert yeni == [] and len(r["eslesmeyen"]) == 1


def test_no_sifir_ad_dbde_yoksa_atlanir():
    yeni, r = e.eslestir([s(0, "EYMEN", "12-A")], DB)
    assert yeni == [] and len(r["eslesmeyen"]) == 1


def test_bozuk_ad_ayni_no_ve_sube_benzer_ise_eslesir():
    for ad in ("ALP", "ESİLAİREMMAYDA", "KÜBRANUR EMEKLI"):
        no = {"ALP": 20, "ESİLAİREMMAYDA": 40, "KÜBRANUR EMEKLI": 50}[ad]
        sinif = {20: "11-B", 40: "11-B", 50: "11-B"}[no]
        yeni, r = e.eslestir([s(no, ad, sinif)], DB)
        assert len(yeni) == 1 and yeni[0]["okul_no"] == no, ad
        assert r["benzer"] == 1


def test_xx_sube_no_ve_ad_ayniysa_eslesir_sinif_dbden():
    yeni, _ = e.eslestir([s(40, "ESİLA İREM MAYDA", "11-XX")], DB)
    assert yeni[0]["sinif"] == "11-B"


def test_ayni_no_ama_baska_sube_ve_benzer_degil_atlanir():
    yeni, r = e.eslestir([s(20, "ALP", "11-A")], DB)  # şube çelişiyor
    assert yeni == [] and len(r["eslesmeyen"]) == 1
    yeni, r = e.eslestir([s(20, "MEHMET YILMAZ", "11-B")], DB)  # ad ilgisiz
    assert yeni == [] and len(r["eslesmeyen"]) == 1


def test_dbde_olmayan_no_ve_ad_atlanir():
    yeni, r = e.eslestir([s(901, "YUSUF DOĞAN", "11-B")], DB)
    assert yeni == [] and len(r["eslesmeyen"]) == 1
