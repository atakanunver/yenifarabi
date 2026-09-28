"""Yoklama SMS iş mantığı birim testleri.

Sahte bir yoklama panosu veritabanı kurup `yoklama_kaynak.YOKLAMA_DB_YOLU`'nu
ona yönlendirir — gerçek pano DB'sine hiç dokunulmaz.
"""

import json
import sqlite3

import db
import pytest
import yoklama_kaynak
import yoklama_mantik

# Panonun `yoklama_onbellek` şemasının test için gereken alt kümesi
# (tahtayoklama/dashboard/db.py:48-60 ile alan adları birebir aynı).
_PANO_SEMA = """
CREATE TABLE yoklama_onbellek (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarih TEXT NOT NULL,
    sinif TEXT NOT NULL,
    ders_no INTEGER NOT NULL,
    durum TEXT NOT NULL,
    yok_isimleri TEXT,
    izinli_isimleri TEXT,
    kaynak_tahta TEXT,
    kaydedilme_saati TEXT,
    UNIQUE(tarih, sinif, ders_no)
);
"""

TARIH = "2026-09-23"


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Geçici smssistemi DB'si — test_dogum_mantik.py'deki desenin eşi
    (bilinçli tekrar: projede conftest.py yok)."""
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_smssistemi.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    db.semayi_kur()
    conn = db.baglanti()
    yield conn
    conn.close()


@pytest.fixture
def pano(tmp_path, monkeypatch):
    """Sahte yoklama panosu DB'si. `ekle(sinif, ders_no, durum, yok, izinli)`
    döndürür."""
    yol = tmp_path / "yoklama_pano.db"
    conn = sqlite3.connect(yol)
    conn.executescript(_PANO_SEMA)
    conn.commit()
    monkeypatch.setattr(yoklama_kaynak, "YOKLAMA_DB_YOLU", yol)

    def ekle(sinif, ders_no, durum="alindi", yok=(), izinli=(), tarih=TARIH):
        conn.execute(
            "INSERT INTO yoklama_onbellek (tarih, sinif, ders_no, durum, "
            "yok_isimleri, izinli_isimleri) VALUES (?, ?, ?, ?, ?, ?)",
            (tarih, sinif, ders_no, durum, json.dumps(list(yok)), json.dumps(list(izinli))),
        )
        conn.commit()

    yield ekle
    conn.close()


def _sinif_id(conn, ad):
    return next(s["id"] for s in db.siniflar_listele(conn) if s["ad"] == ad)


def _ogrenci_ekle(conn, ad_soyad, sinif_ad):
    return db.kisi_ekle(conn, ad_soyad, None, _sinif_id(conn, sinif_ad), "ogrenci")


def _veli_ekle(conn, ad_soyad, telefon, sinif_ad, ogrenci_id):
    return db.kisi_ekle(
        conn, ad_soyad, telefon, _sinif_id(conn, sinif_ad), "veli", ogrenci_kisi_id=ogrenci_id
    )


def _ogrenci(ozet, ad_soyad):
    return next(o for o in ozet["ogrenciler"] if o["ad_soyad"] == ad_soyad)


# --- Eşik -------------------------------------------------------------------


def test_esik_altindaki_ogrenci_listeye_girmez(test_db, pano):
    ogr = _ogrenci_ekle(test_db, "Ayşe Yılmaz", "9-A")
    _veli_ekle(test_db, "Ayşe Yılmaz Annesi", "05551112233", "9-A", ogr)
    for ders in range(1, 9):
        pano("9-A", ders, yok=["Ayşe Yılmaz"] if ders <= 3 else [])

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=4)
    assert ozet["ogrenciler"] == []
    assert ozet["devamsiz_sayisi"] == 0


def test_esige_ulasan_ogrenci_listeye_girer(test_db, pano):
    ogr = _ogrenci_ekle(test_db, "Ayşe Yılmaz", "9-A")
    _veli_ekle(test_db, "Ayşe Yılmaz Annesi", "05551112233", "9-A", ogr)
    for ders in range(1, 9):
        pano("9-A", ders, yok=["Ayşe Yılmaz"] if ders <= 4 else [])

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=4)
    kayit = _ogrenci(ozet, "Ayşe Yılmaz")
    assert kayit["yok_sayisi"] == 4
    assert kayit["alinan_sayisi"] == 8
    assert kayit["eslesme_durumu"] == yoklama_mantik.ESLESME_TAMAM
    assert [v["telefon"] for v in kayit["veliler"]] == ["05551112233"]
    assert ozet["ulasilabilir_sayisi"] == 1
    assert ozet["veli_sayisi"] == 1


def test_esik_sinirlari_kirpilir(test_db, pano):
    pano("9-A", 1, yok=[])
    assert yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=99)["esik"] == yoklama_mantik.ESIK_MAX
    assert yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=0)["esik"] == yoklama_mantik.ESIK_MIN
    assert yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik="abc")["esik"] == yoklama_mantik.ESIK_VARSAYILAN


# --- Yoklaması eksik sınıflar ----------------------------------------------


def test_yoklamasi_alinmamis_sinif_haric_tutulur(test_db, pano):
    _ogrenci_ekle(test_db, "Mehmet Demir", "9-B")
    for ders in range(1, 9):
        pano("9-B", ders, durum="alinmadi")

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=1)
    assert ozet["ogrenciler"] == []
    haric = next(h for h in ozet["haric_siniflar"] if h["sinif"] == "9-B")
    assert haric["sebep"] == "alinmadi"
    assert haric["aciklama"] == "Yoklama alınmamış"
    assert "9-B" not in {o["sinif"] for o in ozet["ogrenciler"]}


def test_tahta_ulasilamaz_sinif_haric_tutulur(test_db, pano):
    # 12-A'nın 2026-09-22'de DHCP kirası bozulunca yaşadığı gerçek vaka.
    for ders in range(1, 9):
        pano("12-A", ders, durum="tahta_ulasilamaz")

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=1)
    haric = next(h for h in ozet["haric_siniflar"] if h["sinif"] == "12-A")
    assert haric["sebep"] == "tahta_ulasilamaz"
    assert ozet["dahil_sinif_sayisi"] == 0


def test_kismi_yoklama_sadece_alinan_dersleri_sayar(test_db, pano):
    """Tahta öğleden sonra düşerse payda da küçülür — 3 alınan dersin 3'ünde
    yok olan öğrenci eşik 3'te listeye girer, 8 ders varmış gibi davranılmaz."""
    ogr = _ogrenci_ekle(test_db, "Ali Kaya", "10-A")
    _veli_ekle(test_db, "Ali Kaya Babası", "05559998877", "10-A", ogr)
    for ders in (1, 2, 3):
        pano("10-A", ders, yok=["Ali Kaya"])
    for ders in (4, 5, 6, 7, 8):
        pano("10-A", ders, durum="tahta_ulasilamaz")

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=3)
    kayit = _ogrenci(ozet, "Ali Kaya")
    assert (kayit["yok_sayisi"], kayit["alinan_sayisi"]) == (3, 3)
    assert ozet["haric_siniflar"] == [] or "10-A" not in {h["sinif"] for h in ozet["haric_siniflar"]}


def test_panoda_hic_kaydi_olmayan_sinif_uyarida_gorunur(test_db, pano):
    pano("9-A", 1, yok=[])
    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=1)
    eksikler = {h["sinif"]: h["sebep"] for h in ozet["haric_siniflar"]}
    assert eksikler.get("12-B") == "veri_yok"
    # 'Personel' / 'Bilinmeyen Sınıf' sahte sınıfları uyarıya karışmamalı.
    assert "Personel" not in eksikler
    assert "Bilinmeyen Sınıf" not in eksikler


# --- İzinli -----------------------------------------------------------------


def test_izinli_ders_yok_sayilmaz(test_db, pano):
    ogr = _ogrenci_ekle(test_db, "Zeynep Ak", "9-A")
    _veli_ekle(test_db, "Zeynep Ak Annesi", "05551110000", "9-A", ogr)
    for ders in range(1, 9):
        # Aynı isim hem yok hem izinli listesinde: izinli önceliklidir.
        pano("9-A", ders, yok=["Zeynep Ak"], izinli=["Zeynep Ak"])

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=1)
    assert ozet["ogrenciler"] == []


def test_gun_icinde_izinli_gorunen_ogrenci_isaretlenir(test_db, pano):
    ogr = _ogrenci_ekle(test_db, "Zeynep Ak", "9-A")
    _veli_ekle(test_db, "Zeynep Ak Annesi", "05551110000", "9-A", ogr)
    for ders in range(1, 6):
        pano("9-A", ders, yok=["Zeynep Ak"])
    pano("9-A", 6, izinli=["Zeynep Ak"])

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=4)
    kayit = _ogrenci(ozet, "Zeynep Ak")
    assert kayit["yok_sayisi"] == 5
    assert kayit["izinli_mi"] is True
    assert ozet["izinli_sayisi"] == 1


# --- Eşleşme ----------------------------------------------------------------


def test_cozulmemis_no_ismi_eslesmedi_sayilir(test_db, pano):
    # Panonun roster'ında numarası bulunmayan öğrenci: yoklayici.py:56
    for ders in range(1, 9):
        pano("9-A", ders, yok=["No 237"])

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=4)
    kayit = _ogrenci(ozet, "No 237")
    assert kayit["eslesme_durumu"] == yoklama_mantik.ESLESME_YOK
    assert kayit["veliler"] == []
    assert ozet["eslesmeyen_sayisi"] == 1
    assert ozet["ulasilabilir_sayisi"] == 0


def test_rehberde_olmayan_isim_listede_kalir(test_db, pano):
    for ders in range(1, 9):
        pano("9-A", ders, yok=["Kayıtsız Öğrenci"])

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=4)
    assert _ogrenci(ozet, "Kayıtsız Öğrenci")["eslesme_durumu"] == yoklama_mantik.ESLESME_YOK
    assert ozet["devamsiz_sayisi"] == 1


def test_telefonlu_velisi_olmayan_ogrenci_telefonsuz_isaretlenir(test_db, pano):
    ogr = _ogrenci_ekle(test_db, "Emre Şahin", "9-A")
    _veli_ekle(test_db, "Emre Şahin Velisi", "", "9-A", ogr)  # telefon boş
    for ders in range(1, 9):
        pano("9-A", ders, yok=["Emre Şahin"])

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=4)
    kayit = _ogrenci(ozet, "Emre Şahin")
    assert kayit["eslesme_durumu"] == yoklama_mantik.ESLESME_TELEFONSUZ
    assert kayit["veliler"] == []
    assert ozet["telefonsuz_sayisi"] == 1
    assert ozet["ulasilabilir_sayisi"] == 0


def test_turkce_buyuk_i_farkiyla_yazilmis_isim_eslesir(test_db, pano):
    ogr = _ogrenci_ekle(test_db, "İlknur Işık", "9-A")
    _veli_ekle(test_db, "İlknur Işık Annesi", "05553334455", "9-A", ogr)
    for ders in range(1, 9):
        pano("9-A", ders, yok=["ilknur ışık"])

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=4)
    assert _ogrenci(ozet, "ilknur ışık")["eslesme_durumu"] == yoklama_mantik.ESLESME_TAMAM


def test_ayni_isim_farkli_siniflar_karismaz(test_db, pano):
    ogr_a = _ogrenci_ekle(test_db, "Ali Kaya", "9-A")
    _veli_ekle(test_db, "9-A Velisi", "05551111111", "9-A", ogr_a)
    _ogrenci_ekle(test_db, "Ali Kaya", "9-B")  # 9-B'dekinin velisi yok
    for ders in range(1, 9):
        pano("9-A", ders, yok=["Ali Kaya"])
        pano("9-B", ders, yok=["Ali Kaya"])

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=4)
    durumlar = {o["sinif"]: o["eslesme_durumu"] for o in ozet["ogrenciler"]}
    assert durumlar["9-A"] == yoklama_mantik.ESLESME_TAMAM
    assert durumlar["9-B"] == yoklama_mantik.ESLESME_TELEFONSUZ


def test_iki_velisi_olan_ogrenci_ikisine_de_gonderilir(test_db, pano):
    ogr = _ogrenci_ekle(test_db, "Deniz Yurt", "9-A")
    _veli_ekle(test_db, "Deniz Yurt Annesi", "05551111111", "9-A", ogr)
    _veli_ekle(test_db, "Deniz Yurt Babası", "05552222222", "9-A", ogr)
    for ders in range(1, 9):
        pano("9-A", ders, yok=["Deniz Yurt"])

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=4)
    assert len(_ogrenci(ozet, "Deniz Yurt")["veliler"]) == 2
    assert ozet["veli_sayisi"] == 2
    assert ozet["ulasilabilir_sayisi"] == 1


# --- Şablon ve kaynak -------------------------------------------------------


def test_sablon_ayarlardan_okunur(test_db, pano):
    pano("9-A", 1, yok=[])
    assert yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH)["sablon"] == yoklama_mantik.SABLON_VARSAYILAN

    db.ayar_yaz(test_db, yoklama_mantik.AYAR_SABLON, "Özel metin {ogrenci_adi}")
    assert yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH)["sablon"] == "Özel metin {ogrenci_adi}"


def test_pano_veritabani_yoksa_hata_firlatir(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(yoklama_kaynak, "YOKLAMA_DB_YOLU", tmp_path / "olmayan.db")
    with pytest.raises(yoklama_kaynak.YoklamaKaynakYok):
        yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH)


def test_bozuk_json_listeyi_cokertmez(test_db, tmp_path, monkeypatch, pano):
    pano("9-A", 1, yok=["Ali Kaya"])
    conn = sqlite3.connect(yoklama_kaynak.YOKLAMA_DB_YOLU)
    conn.execute("UPDATE yoklama_onbellek SET yok_isimleri = '{bozuk'")
    conn.commit()
    conn.close()

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=1)
    assert ozet["ogrenciler"] == []


def test_kaynak_baglantisi_salt_okunur(test_db, pano):
    pano("9-A", 1, yok=[])
    conn = yoklama_kaynak._baglan()
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM yoklama_onbellek")
    finally:
        conn.close()


def test_baska_sinifta_kayitli_ogrenci_icin_sebep_yazilir(test_db, pano):
    """Panoda 11-A, rehberde 11-B görünen öğrenci — 2026-09-23'te canlı veride
    bulunan gerçek uyuşmazlık. SMS gönderilmez ama sebebi söylenir."""
    _ogrenci_ekle(test_db, "Kerem Su Aydemir", "11-B")
    for ders in range(1, 9):
        pano("11-A", ders, yok=["Kerem Su Aydemir"])

    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=4)
    kayit = _ogrenci(ozet, "Kerem Su Aydemir")
    assert kayit["eslesme_durumu"] == yoklama_mantik.ESLESME_YOK
    assert kayit["eslesme_notu"] == "Rehberde 11-B sınıfında kayıtlı"
    assert kayit["veliler"] == []


def test_cozulmemis_no_ismine_sebep_yazilir(test_db, pano):
    for ders in range(1, 9):
        pano("9-A", ders, yok=["No 237"])
    ozet = yoklama_mantik.devamsiz_ozet(test_db, tarih=TARIH, esik=4)
    assert _ogrenci(ozet, "No 237")["eslesme_notu"] == "Panoda öğrenci numarası çözülememiş"
