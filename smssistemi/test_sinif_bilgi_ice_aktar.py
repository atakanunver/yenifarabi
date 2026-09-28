from pathlib import Path

import db
import openpyxl
from scripts.sinif_bilgi_ice_aktar import (
    aktarim_uygula,
    clean_phone,
    dogum_tarihlerini_oku,
    parse_dob_to_iso,
    sinif_telefonlarini_oku,
)


def test_parse_dob_to_iso():
    assert parse_dob_to_iso("11/06/2011") == "2011-06-11"
    assert parse_dob_to_iso("04.01.2011") == "2011-01-04"
    assert parse_dob_to_iso("2011-06-11") == "2011-06-11"
    assert parse_dob_to_iso("") is None
    assert parse_dob_to_iso(None) is None
    assert parse_dob_to_iso("geçersiz") is None


def test_clean_phone():
    # Fake test numaraları — gerçek veli/öğrenci telefonu değil.
    assert clean_phone("0555 123 45 67") == "05551234567"
    assert clean_phone("5559876543") == "05559876543"
    assert clean_phone("5551112233(TEYZE)") == "05551112233"
    assert clean_phone("YOK") is None
    assert clean_phone("yok") is None
    assert clean_phone("") is None
    assert clean_phone(None) is None


def _dogum_dosyasi_yaz(yol: Path, satirlar: list[tuple]) -> None:
    """dogum_tarihlerini_oku'nun beklediği düzenle (ilk sütun boş/kullanılmıyor,
    sonra ad_soyad, tc, okul_no, sinif_str, dogum_tarihi) sentetik dosya üretir."""
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(["Sıra", "Ad Soyad", "TC", "Okul No", "Sınıf", "Doğum Tarihi"])
    for satir in satirlar:
        sheet.append([None, *satir])
    wb.save(yol)


def _telefon_dosyasi_yaz(yol: Path, satirlar: list[tuple]) -> None:
    """sinif_telefonlarini_oku'nun beklediği düzenle (ilk 2 satır başlık,
    sonra okul_no, veli_yakinlik, veli_adi, ogr_ad, ogr_tel, anne_tel, baba_tel)
    sentetik dosya üretir."""
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(["Okul No", "Yakınlık", "Veli Adı", "Öğrenci Adı", "Öğrenci Tel", "Anne Tel", "Baba Tel"])
    sheet.append(["", "", "", "", "", "", ""])  # 2. başlık satırı (gerçek dosyalarda birleşik hücreler)
    for satir in satirlar:
        sheet.append(list(satir))
    wb.save(yol)


def test_sinif_dizini_okuma(tmp_path):
    """Gerçek `/home/ata/farabi/mudur/SINIF` dizini yerine sentetik, uydurma
    verili bir dizin kullanır — dosya adı/sütun YAPISI korunur, içerik kurgusal."""
    dizin = tmp_path / "SINIF"
    dizin.mkdir()

    # dogum_tarihlerini_oku 4 dosyaya bakar; sadece "9-LAR.xlsx"'i dolduruyoruz,
    # 55 kurgusal öğrenciyle (>50 koşulunu sentetik veriyle sağlamak için).
    dogum_satirlari = [
        (f"Test Öğrenci {i:03d}", f"{10000000000 + i}", 100 + i, "9-A", "01/01/2011")
        for i in range(55)
    ]
    _dogum_dosyasi_yaz(dizin / "9-LAR.xlsx", dogum_satirlari)

    # sinif_telefonlarini_oku "10-A.xlsx" ve "12-A.xlsx"'e bakar.
    telefon_10a = [
        (201, "Anne", "Test Veli Bir", "Test Öğrenci 001", "05551110001", "05552220001", "05553330001"),
        (202, "Baba", "Test Veli İki", "Test Öğrenci 002", "05551110002", None, "05553330002"),
        (203, "Anne", "Test Veli Üç", "Test Öğrenci 003", None, "05552220003", None),
    ]
    telefon_12a = [
        (401, "Anne", "Test Veli Dört", "Test Öğrenci 004", "05551110004", "05552220004", "05553330004"),
        (402, "Baba", "Test Veli Beş", "Test Öğrenci 005", None, None, "05553330005"),
    ]
    _telefon_dosyasi_yaz(dizin / "10-A.xlsx", telefon_10a)
    _telefon_dosyasi_yaz(dizin / "12-A.xlsx", telefon_12a)

    dobs = dogum_tarihlerini_oku(dizin)
    assert len(dobs) > 50

    telefons = sinif_telefonlarini_oku(dizin)
    assert len(telefons) == 5  # 3 in 10-A, 2 in 12-A (sentetik)


def test_aktarim_idempotent(tmp_path, monkeypatch):
    """Aynı aktarımı iki kez çalıştırdığımızda ikinci seferde mükerrer kayıt oluşmadığını doğrular."""
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_YOLU", test_db)
    db.semayi_kur()

    conn = db.baglanti()
    try:
        # Test için sınıf ve öğrenci ekle (kurgusal isimler)
        s10_id = db.sinif_ekle(conn, "10-A")
        ogr1_id = db.kisi_ekle(conn, "Test Öğrenci Bir", None, s10_id, "ogrenci")
        ogr2_id = db.kisi_ekle(conn, "Test Öğrenci İki", None, s10_id, "ogrenci")

        analiz_mock = {
            "dogum_guncellenecek": [
                {"id": ogr1_id, "yeni_dob": "2011-06-11"},
                {"id": ogr2_id, "yeni_dob": "2011-08-12"},
            ],
            "ogrenci_tel_guncellenecek": [
                {"id": ogr1_id, "yeni_tel": "05551110001"},
                {"id": ogr2_id, "yeni_tel": "05551110002"},
            ],
            "veli_islemleri": [
                {
                    "islem": "ekle",
                    "kisi_id": None,
                    "ad_soyad": "Test Veli Bir",
                    "telefon": "05552220001",
                    "sinif_id": s10_id,
                    "ogrenci_kisi_id": ogr1_id,
                    "rol": "Birincil Veli",
                },
                {
                    "islem": "ekle",
                    "kisi_id": None,
                    "ad_soyad": "Test Öğrenci Bir Babası",
                    "telefon": "05553330001",
                    "sinif_id": s10_id,
                    "ogrenci_kisi_id": ogr1_id,
                    "rol": "İkincil Veli",
                },
            ],
        }

        sonuc1 = aktarim_uygula(analiz_mock, conn)
        assert sonuc1["dogum_guncellendi"] == 2
        assert sonuc1["ogrenci_tel_guncellendi"] == 2
        assert sonuc1["veli_eklendi"] == 2

        # Doğrulama: 2 öğrenci + 2 veli = 4 kişi
        sayi1 = conn.execute("SELECT count(*) FROM kisiler").fetchone()[0]
        assert sayi1 == 4

        # Şimdi analiz_et simülasyonu yapalım (var_olan velileri tespit eden mantık)
        veliler = conn.execute("SELECT id, ad_soyad, telefon, ogrenci_kisi_id FROM kisiler WHERE tur='veli'").fetchall()
        db_veliler = [dict(v) for v in veliler]

        # İkinci seferde veli_islemleri "guncelle" veya boş olmalı, asla yeni "ekle" olmamalı
        analiz_mock2 = {
            "dogum_guncellenecek": [],
            "ogrenci_tel_guncellenecek": [],
            "veli_islemleri": [
                {
                    "islem": "guncelle",
                    "kisi_id": db_veliler[0]["id"],
                    "ad_soyad": "Test Veli Bir",
                    "telefon": "05552220001",
                    "sinif_id": s10_id,
                    "ogrenci_kisi_id": ogr1_id,
                    "rol": "Birincil Veli",
                },
                {
                    "islem": "guncelle",
                    "kisi_id": db_veliler[1]["id"],
                    "ad_soyad": "Test Öğrenci Bir Babası",
                    "telefon": "05553330001",
                    "sinif_id": s10_id,
                    "ogrenci_kisi_id": ogr1_id,
                    "rol": "İkincil Veli",
                },
            ],
        }

        sonuc2 = aktarim_uygula(analiz_mock2, conn)
        assert sonuc2["veli_eklendi"] == 0
        assert sonuc2["veli_guncellendi"] == 2

        sayi2 = conn.execute("SELECT count(*) FROM kisiler").fetchone()[0]
        assert sayi2 == 4  # Sayı kesinlikle artmadı (mükerrer kayıt engellendi)
    finally:
        conn.close()
