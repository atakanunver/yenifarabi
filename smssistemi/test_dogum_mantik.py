"""dogum_mantik.py için birim testleri."""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import db
import dogum_mantik
import openpyxl
import pytest

_ISTANBUL = ZoneInfo("Europe/Istanbul")


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Geçici bir DB oluşturur ve db modülüne bağlar."""
    db_yolu = tmp_path / "test_smssistemi.db"
    yedek_dizini = tmp_path / "yedek"
    monkeypatch.setattr(db, "DB_YOLU", db_yolu)
    monkeypatch.setattr(db, "YEDEK_DIZINI", yedek_dizini)
    db.semayi_kur()
    conn = db.baglanti()
    yield conn
    conn.close()


def _sentetik_dogum_xlsx(yol: Path, satirlar: list[tuple]) -> Path:
    """dogum_mantik.excel_analiz_et'in beklediği sütun düzeniyle (Ad, Soyad,
    Doğum Tarihi, Gün, Ay) sentetik bir Dogum.xlsx üretir — gerçek dosyanın
    yapısını taklit eder, içeriği tamamen kurgusaldır."""
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "Sayfa1"
    sheet.append(["Ad", "Soyad", "Doğum Tarihi", "Gün", "Ay"])
    for satir in satirlar:
        sheet.append(list(satir))
    wb.save(yol)
    return yol


def test_excel_analiz_et_sentetik_dosya(test_db, tmp_path):
    yil_once = datetime.now(_ISTANBUL).year

    # 2 kişi DB'de zaten öğrenci olarak eşleşecek, 3 kişi personel yaşında
    # (>19), 4 kişi ayrılan/eski öğrenci adayı (13-19 yaş, DB'de yok) olacak.
    satirlar = [
        ("Elif", "Çağlayan", date(yil_once - 15, 3, 10), 10, 3),
        ("Mert", "Öztürk", date(yil_once - 16, 7, 20), 20, 7),
        ("Örnek", "Personel Bir", date(yil_once - 30, 1, 1), 1, 1),
        ("Örnek", "Personel İki", date(yil_once - 45, 5, 5), 5, 5),
        ("Örnek", "Personel Üç", date(yil_once - 50, 8, 8), 8, 8),
        ("Ayrılan", "Öğrenci Bir", date(yil_once - 14, 2, 2), 2, 2),
        ("Ayrılan", "Öğrenci İki", date(yil_once - 15, 4, 4), 4, 4),
        ("Ayrılan", "Öğrenci Üç", date(yil_once - 16, 6, 6), 6, 6),
        ("Ayrılan", "Öğrenci Dört", date(yil_once - 17, 9, 9), 9, 9),
    ]
    dosya = _sentetik_dogum_xlsx(tmp_path / "sentetik_dogum.xlsx", satirlar)

    # Henüz öğrenci eklenmemişken: Elif/Mert de DB'de olmadığından "ayrılan
    # öğrenci adayı" sayılır (13-19 yaş, listede yok) — eşleşen 0 kalır.
    analiz = dogum_mantik.excel_analiz_et(dosya, conn=test_db)
    assert analiz["ozet"]["toplam_okunan"] == 9
    assert analiz["ozet"]["eslesen"] == 0  # DB boş olduğundan eşleşen 0
    assert analiz["ozet"]["personel"] == 3
    assert analiz["ozet"]["ayrilan"] == 6  # 4 kurgusal + Elif/Mert henüz eşleşmedi

    # Birkaç öğrenci ekleyelim (fixture'da olanlardan)
    s9a = db.sinif_ekle(test_db, "9-A")
    db.kisi_ekle(test_db, "Elif Çağlayan", "05551111111", s9a, "ogrenci")
    db.kisi_ekle(test_db, "Mert Öztürk", "05552222222", s9a, "ogrenci")

    analiz2 = dogum_mantik.excel_analiz_et(dosya, conn=test_db)
    assert analiz2["ozet"]["eslesen"] == 2
    eslesen_adlar = {o["ad_soyad"] for o in analiz2["eslesen_ogrenciler"]}
    assert "Elif Çağlayan" in eslesen_adlar
    assert "Mert Öztürk" in eslesen_adlar


def test_aktarim_uygula(test_db, tmp_path):
    yil_once = datetime.now(_ISTANBUL).year

    satirlar = [
        ("Elif", "Çağlayan", date(yil_once - 15, 12, 2), 2, 12),
        ("Örnek", "Personel Bir", date(yil_once - 45, 10, 11), 11, 10),
        ("Örnek", "Personel İki", date(yil_once - 50, 1, 1), 1, 1),
        ("Örnek", "Personel Üç", date(yil_once - 60, 3, 3), 3, 3),
        ("Ayrılan", "Öğrenci Bir", date(yil_once - 15, 12, 1), 1, 12),
        ("Ayrılan", "Öğrenci İki", date(yil_once - 14, 3, 3), 3, 3),
    ]
    dosya = _sentetik_dogum_xlsx(tmp_path / "sentetik_dogum.xlsx", satirlar)

    s9a = db.sinif_ekle(test_db, "9-A")
    ogr1_id = db.kisi_ekle(test_db, "Elif Çağlayan", "05551111111", s9a, "ogrenci")

    # Personellerden sadece 2 tanesini seçelim, ayrılanlardan 1 tanesini seçelim
    secilen_personeller = ["Örnek Personel Bir", "Örnek Personel İki"]
    secilen_ayrilanlar = ["Ayrılan Öğrenci Bir"]

    sonuc = dogum_mantik.aktarim_uygula(
        test_db,
        secilen_personeller=secilen_personeller,
        secilen_ayrilanlar=secilen_ayrilanlar,
        dosya_yolu=dosya,
    )

    assert sonuc["eslesen_guncellendi"] == 1
    assert sonuc["personel_eklendi"] == 2
    assert sonuc["ayrilan_eklendi"] == 1
    assert sonuc["atlanan_personel"] == 1
    assert sonuc["atlanan_ayrilan"] == 1

    # DB kontrolü
    ogr1 = test_db.execute("SELECT * FROM kisiler WHERE id = ?", (ogr1_id,)).fetchone()
    assert ogr1["dogum_tarihi"] == f"{yil_once - 15}-12-02"

    p1 = db.kisi_bul_isimle_sinifsiz(test_db, "Örnek Personel Bir", "personel")
    assert p1 is not None
    assert p1["dogum_tarihi"] == f"{yil_once - 45}-10-11"
    assert p1["tur"] == "personel"

    ayrilan_bir = db.kisi_bul_isimle_sinifsiz(test_db, "Ayrılan Öğrenci Bir", "ogrenci")
    assert ayrilan_bir is not None
    assert ayrilan_bir["dogum_tarihi"] == f"{yil_once - 15}-12-01"

    # Seçilmeyen personel veya öğrenci eklenmemiş olmalı
    assert db.kisi_bul_isimle_sinifsiz(test_db, "Örnek Personel Üç", "personel") is None
    assert db.kisi_bul_isimle_sinifsiz(test_db, "Ayrılan Öğrenci İki", "ogrenci") is None


def test_yaklasan_dogum_gunleri(test_db):
    s9a = db.sinif_ekle(test_db, "9-A")
    k1 = db.kisi_ekle(test_db, "Test Öğrenci 1", None, s9a, "ogrenci")
    k2 = db.kisi_ekle(test_db, "Test Öğrenci 2", None, s9a, "ogrenci")

    bugun = datetime.now(_ISTANBUL).date()
    # Yarınki doğum günü
    yarin_ay = bugun.month
    yarin_gun = bugun.day + 1
    if yarin_gun > 28:  # Ay sonu taşması olmasın diye basit koruma
        yarin_ay = (bugun.month % 12) + 1
        yarin_gun = 1

    iso_yarin = f"2008-{yarin_ay:02d}-{yarin_gun:02d}"
    iso_uzak = f"2008-{(bugun.month + 6) % 12 or 12:02d}-15"

    db.kisi_dogum_tarihi_guncelle(test_db, k1, iso_yarin)
    db.kisi_dogum_tarihi_guncelle(test_db, k2, iso_uzak)

    yaklasanlar = dogum_mantik.yaklasan_dogum_gunleri(test_db, gun_sayisi=7)
    adlar = [y["ad_soyad"] for y in yaklasanlar]
    assert "Test Öğrenci 1" in adlar
    assert "Test Öğrenci 2" not in adlar


def test_dogum_gunu_istatistikleri(test_db):
    s9a = db.sinif_ekle(test_db, "9-A")
    k1 = db.kisi_ekle(test_db, "Öğrenci 1", None, s9a, "ogrenci")
    k2 = db.kisi_ekle(test_db, "Öğrenci 2", None, s9a, "ogrenci")
    db.kisi_dogum_tarihi_guncelle(test_db, k1, "2009-05-10")

    ist = dogum_mantik.dogum_gunu_istatistikleri(test_db)
    assert ist["toplam"] == 2
    assert ist["tanimli"] == 1
    assert ist["eksik"] == 1
    assert ist["ogrenci_sayisi"] == 2
    assert ist["personel_sayisi"] == 0
