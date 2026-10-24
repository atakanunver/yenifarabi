import json
import sqlite3

import pytest
from ayarlar import AYAR
from kaynaklar import KaynakHatasi, yoklama


@pytest.fixture
def pano():
    c = sqlite3.connect(AYAR.pano_db_yolu)
    c.executescript(
        """
        CREATE TABLE siniflar (id INTEGER PRIMARY KEY, ad TEXT UNIQUE, aktif INTEGER DEFAULT 1);
        CREATE TABLE ogrenciler (id INTEGER PRIMARY KEY, sinif_id INTEGER, no INTEGER,
            ad_soyad TEXT, cinsiyet TEXT, aktif INTEGER DEFAULT 1);
        CREATE TABLE yoklama_onbellek (id INTEGER PRIMARY KEY, tarih TEXT, sinif TEXT,
            ders_no INTEGER, durum TEXT, yok_isimleri TEXT, izinli_isimleri TEXT,
            yok_nolari TEXT, izinli_nolari TEXT);
        INSERT INTO siniflar (id, ad) VALUES (1, '9-A'), (2, '9-B');
        INSERT INTO ogrenciler (sinif_id, no, ad_soyad) VALUES
            (1, 101, 'Ali Veli'), (1, 102, 'Can Demir'),
            (1, 103, 'Ece Su'), (1, 104, 'ECE  SU'),
            (2, 201, 'Ayşe Kaya'), (2, 999, 'Panoda Tek');
        """
    )

    def ekle(tarih, sinif, ders_no, durum, yok=(), izinli=(), yok_nolari=None, izinli_nolari=None):
        c.execute(
            "INSERT INTO yoklama_onbellek (tarih, sinif, ders_no, durum, yok_isimleri,"
            " izinli_isimleri, yok_nolari, izinli_nolari) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tarih,
                sinif,
                ders_no,
                durum,
                json.dumps(list(yok)),
                json.dumps(list(izinli)),
                json.dumps(list(yok_nolari)) if yok_nolari is not None else None,
                json.dumps(list(izinli_nolari)) if izinli_nolari is not None else None,
            ),
        )
        c.commit()

    ekle("2026-10-05", "9-A", 1, "alindi", yok=["ALİ VELİ"])
    ekle("2026-10-05", "9-A", 2, "alindi", izinli=["Ali  Veli"])
    ekle("2026-10-06", "9-A", 1, "alindi", yok=["Can Demir", "Bilinmeyen Kişi"])
    ekle("2026-10-06", "9-A", 2, "alinmadi", yok=["Ali Veli"])
    ekle("2026-10-07", "9-A", 3, "alindi", yok=["Ali Veli", "Ece Su"])
    ekle("2026-10-07", "9-B", 1, "alindi", yok=["Ayşe Kaya"])
    yield ekle
    c.close()


def test_ogrencinin_devamsizligi_isimden_eslesir(pano):
    d = yoklama.devamsizlik(101, "9-A")
    assert [(x.tarih, x.ders_no, x.tur) for x in d] == [
        ("2026-10-07", 3, "yok"),
        ("2026-10-05", 1, "yok"),
        ("2026-10-05", 2, "izinli"),
    ]


def test_baslangic_tarihi_filtresi(pano):
    assert [x.tarih for x in yoklama.devamsizlik(101, "9-A", "2026-10-06")] == [
        "2026-10-07"
    ]


def test_alinmamis_yoklama_sayilmaz(pano):
    assert all(x.tarih != "2026-10-06" for x in yoklama.devamsizlik(101, "9-A"))


def test_ayni_isimli_ogrenciler_icin_veri_gosterilmez(pano):
    assert yoklama.devamsizlik(103, "9-A") == []
    assert yoklama.devamsizlik(104, "9-A") == []


def test_okul_no_ile_dogrudan_eslesir(pano):
    """yok_nolari ve izinli_nolari dolu olduğunda aynı isimli iki öğrenci bile
    okul_no üzerinden karışmadan eşleşir."""
    pano(
        "2026-10-08",
        "9-A",
        1,
        "alindi",
        yok=["Ece Su"],
        yok_nolari=[103],
        izinli_nolari=[],
    )
    assert [(x.tarih, x.ders_no, x.tur) for x in yoklama.devamsizlik(103, "9-A")] == [
        ("2026-10-08", 1, "yok")
    ]
    assert yoklama.devamsizlik(104, "9-A") == []


def test_panoda_olmayan_ogrenci_bos_doner(pano):
    assert yoklama.devamsizlik(555, "9-A") == []


def test_sinif_yok_sayilari(pano):
    assert yoklama.sinif_yok_sayilari("2026-10-01") == {"9-A": 5, "9-B": 1}


def test_eslesmeyenler(pano):
    platform = {101: "9-A", 102: "9-A", 103: "9-A", 104: "9-A", 201: "9-A"}
    sonuc = yoklama.eslesmeyenler(platform, "2026-10-01")
    turler = {(s["tur"], s["sinif"], s["isim"]) for s in sonuc}
    assert not any(t[0] == "yoklamada_var_listede_yok" for t in turler)
    assert ("ayni_isim", "9-A", "Ece Su") in turler
    assert ("platformda_yok", "9-B", "Panoda Tek") in turler
    assert ("sinif_farkli", "9-B", "Ayşe Kaya") in turler


def test_pano_db_yoksa_kaynak_hatasi():
    with pytest.raises(KaynakHatasi):
        yoklama.devamsizlik(101, "9-A")


def test_pano_db_salt_okunur_acilir(pano):
    with yoklama._baglan() as c, pytest.raises(sqlite3.OperationalError):
        c.execute("DELETE FROM ogrenciler")


def test_sinif_devamsizlik_ve_ozet(pano):
    k = yoklama.sinif_devamsizlik("9-A", "2026-10-01")
    assert set(k) == {101, 102, 103, 104}
    assert len(k[101]) == 3 and k[103] == [] and k[104] == []  # 103/104 aynı isim: gösterilmez
    o = yoklama.ozet(k, "2026-10-07", esik_gun=2)
    assert o["bugun"] == [(101, 1)]
    assert o["tekrar"] == [(101, 2)]  # 05'te yok + 07'de yok (izinli sayılmaz)
    assert yoklama.ozet(k, "2026-10-07")["tekrar"] == []


def test_sinif_devamsizlik_kaynak_yoksa_hata():
    with pytest.raises(KaynakHatasi):
        yoklama.sinif_devamsizlik("9-A", "2026-10-01")
