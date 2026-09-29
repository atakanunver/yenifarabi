import sqlite3

import db


def test_semayi_kur_ve_gonderim_kaydet(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test.db")
    db.semayi_kur()
    conn = db.baglanti()
    db.gonderim_kaydet(conn, "batch1", "Ahmet", "05551234567", "merhaba", "gonderildi")
    db.gonderim_kaydet(conn, "batch1", "Ayse", "05551234568", "merhaba", "hata", "baglanti hatasi")
    satirlar = db.gonderim_satirlari(conn, "batch1")
    conn.close()
    assert len(satirlar) == 2
    assert satirlar[0]["isim"] == "Ahmet"
    assert satirlar[0]["durum"] == "gonderildi"
    assert satirlar[1]["hata_metni"] == "baglanti hatasi"


def test_utc_str_to_istanbul_str_donusturur():
    # Istanbul UTC+3 (DST yok, 2026 itibariyle sabit) — gün taşması dahil.
    assert db.utc_str_to_istanbul_str("2026-09-28 22:30:00") == "2026-09-29 01:30:00"
    assert db.utc_str_to_istanbul_str("2026-09-28 07:00:00") == "2026-09-28 10:00:00"


def test_utc_str_to_istanbul_str_bos_ve_gecersiz_degeri_oldugu_gibi_dondurur():
    assert db.utc_str_to_istanbul_str(None) is None
    assert db.utc_str_to_istanbul_str("") == ""
    assert db.utc_str_to_istanbul_str("gecersiz-tarih") == "gecersiz-tarih"


def test_gonderim_satirlari_zamani_istanbula_cevirir(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_zaman.db")
    db.semayi_kur()
    conn = db.baglanti()
    conn.execute(
        "INSERT INTO gonderimler (gonderim_id, isim, telefon, mesaj, durum, zaman) "
        "VALUES ('b1', 'A', '0555', 'm', 'gonderildi', '2026-09-28 07:00:00')"
    )
    conn.commit()
    satirlar = db.gonderim_satirlari(conn, "b1")
    conn.close()
    assert satirlar[0]["zaman"] == "2026-09-28 10:00:00"


def test_gonderim_ozetleri_ilk_zamani_istanbula_cevirir_siralama_utc_kalir(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_zaman2.db")
    db.semayi_kur()
    conn = db.baglanti()
    conn.execute(
        "INSERT INTO gonderimler (gonderim_id, isim, telefon, mesaj, durum, zaman) "
        "VALUES ('eski', 'A', '0555', 'm', 'gonderildi', '2026-09-28 06:00:00')"
    )
    conn.execute(
        "INSERT INTO gonderimler (gonderim_id, isim, telefon, mesaj, durum, zaman) "
        "VALUES ('yeni', 'B', '0556', 'm', 'gonderildi', '2026-09-28 08:00:00')"
    )
    conn.commit()
    ozetler = db.gonderim_ozetleri(conn)
    conn.close()
    # ORDER BY ilk_zaman DESC (ham UTC) — en yeni (yeni) önce gelmeli.
    assert [o["gonderim_id"] for o in ozetler] == ["yeni", "eski"]
    assert ozetler[0]["ilk_zaman"] == "2026-09-28 11:00:00"
    assert ozetler[1]["ilk_zaman"] == "2026-09-28 09:00:00"


def test_gonderim_ozetleri_gruplar_ve_sayar(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test2.db")
    db.semayi_kur()
    conn = db.baglanti()
    db.gonderim_kaydet(conn, "b1", "A", "0555", "m", "gonderildi")
    db.gonderim_kaydet(conn, "b1", "B", "0556", "m", "hata", "x")
    db.gonderim_kaydet(conn, "b2", "C", "0557", "m", "gonderildi")
    ozetler = db.gonderim_ozetleri(conn)
    conn.close()
    ozet_by_id = {o["gonderim_id"]: o for o in ozetler}
    assert ozet_by_id["b1"]["toplam"] == 2
    assert ozet_by_id["b1"]["basarili"] == 1
    assert ozet_by_id["b1"]["hatali"] == 1
    assert ozet_by_id["b2"]["toplam"] == 1


def test_gonderim_basarisizlari_sadece_hatali_ve_telefonlu_satirlari_doner(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test3.db")
    db.semayi_kur()
    conn = db.baglanti()
    db.gonderim_kaydet(conn, "b1", "A", "0555", "merhaba A", "gonderildi")
    db.gonderim_kaydet(conn, "b1", "B", "0556", "merhaba B", "hata", "modem hata kodu")
    db.gonderim_kaydet(conn, "b1", "", "", "merhaba C", "hata", "BAĞLANTI HATASI: timeout")
    basarisizlar = db.gonderim_basarisizlari(conn, "b1")
    conn.close()
    assert basarisizlar == [("B", "0556", "merhaba B")]


def test_semayi_kur_varsayilan_siniflari_doldurur(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_siniflar.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    db.semayi_kur()
    conn = db.baglanti()
    siniflar = [s["ad"] for s in db.siniflar_listele(conn)]
    conn.close()
    # "Personel" ve "Bilinmeyen Sınıf" — gerçek sınıf değil, doğum günleri
    # modülünün FK'sini NOT NULL tutmak için her kurulumda seed edilen
    # sahte satırlar (bkz. db.py::_PERSONEL_SINIF_ADI).
    assert siniflar == [
        "9-A", "9-B", "10-A", "10-B", "11-A", "11-B", "12-A", "12-B",
        "Bilinmeyen Sınıf", "Personel",
    ]


def test_sinif_ekle_ve_sil(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_sinif2.db")
    db.semayi_kur()
    conn = db.baglanti()
    yeni_id = db.sinif_ekle(conn, "13-A")
    assert any(s["id"] == yeni_id and s["ad"] == "13-A" for s in db.siniflar_listele(conn))
    assert db.sinif_sil(conn, yeni_id) is True
    conn.close()


def test_sinif_sil_kullanimda_ise_reddeder(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_sinif3.db")
    db.semayi_kur()
    conn = db.baglanti()
    sinif_id = db.sinif_ekle(conn, "13-B")
    db.kisi_ekle(conn, "Ahmet Yılmaz", "05551234567", sinif_id, "ogrenci")
    basarili = db.sinif_sil(conn, sinif_id)
    conn.close()
    assert basarili is False


def test_kisi_ekle_guncelle_sil(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_kisi1.db")
    db.semayi_kur()
    conn = db.baglanti()
    sinif_id = db.sinif_ekle(conn, "9-A")
    kisi_id = db.kisi_ekle(conn, "Ahmet Yılmaz", "05551234567", sinif_id, "ogrenci")
    liste = db.kisiler_listele(conn, sinif_id=sinif_id, tur="ogrenci")
    assert len(liste) == 1
    assert liste[0]["ad_soyad"] == "Ahmet Yılmaz"
    assert liste[0]["sinif_ad"] == "9-A"

    db.kisi_guncelle(conn, kisi_id, "Ahmet Yılmaz", "05559999999", sinif_id, "ogrenci")
    liste = db.kisiler_listele(conn, sinif_id=sinif_id)
    assert liste[0]["telefon"] == "05559999999"

    db.kisi_sil(conn, kisi_id)
    conn.close()
    conn = db.baglanti()
    assert db.kisiler_listele(conn, sinif_id=sinif_id) == []
    conn.close()


def test_kisi_bul_isimle_buyuk_kucuk_harf_ve_bosluk_gozetmez(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_kisi2.db")
    db.semayi_kur()
    conn = db.baglanti()
    sinif_id = db.sinif_ekle(conn, "9-A")
    db.kisi_ekle(conn, "Ahmet Yılmaz", None, sinif_id, "ogrenci")
    bulunan = db.kisi_bul_isimle(conn, "  ahmet yılmaz  ", sinif_id, "ogrenci")
    conn.close()
    assert bulunan is not None
    assert bulunan["telefon"] is None


def test_kisiler_telefonlu_sadece_dolu_telefonlari_doner(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_kisi3.db")
    db.semayi_kur()
    conn = db.baglanti()
    sinif_id = db.sinif_ekle(conn, "9-A")
    db.kisi_ekle(conn, "Telefonsuz Kisi", None, sinif_id, "veli")
    db.kisi_ekle(conn, "Ahmet Yılmaz", "05551234567", sinif_id, "veli")
    sonuc = db.kisiler_telefonlu(conn, sinif_id, "veli")
    conn.close()
    assert sonuc == [("Ahmet Yılmaz", "05551234567")]


def test_ogrenci_kisi_id_baglama_ve_listeleme(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_kisi_bagla.db")
    db.semayi_kur()
    conn = db.baglanti()
    sinif_id = db.sinif_ekle(conn, "9-A")
    ogr_id = db.kisi_ekle(conn, "Ali Çimen", "05551111111", sinif_id, "ogrenci")
    # Çoklu veli desteği: anne ve baba aynı öğrenciye bağlanabilir
    veli1_id = db.kisi_ekle(conn, "Ayşe Çimen", "05552222222", sinif_id, "veli", ogrenci_kisi_id=ogr_id)
    veli2_id = db.kisi_ekle(conn, "Hasan Çimen", "05553333333", sinif_id, "veli", ogrenci_kisi_id=ogr_id)

    veliler = db.kisiler_listele(conn, sinif_id=sinif_id, tur="veli")
    assert len(veliler) == 2
    assert veliler[0]["ogrenci_kisi_id"] == ogr_id
    assert veliler[0]["ogrenci_ad"] == "Ali Çimen"
    assert veliler[1]["ogrenci_kisi_id"] == ogr_id
    assert veliler[1]["ogrenci_ad"] == "Ali Çimen"

    # Öğrenci silinince velinin ogrenci_kisi_id'si NULL olur
    db.kisi_sil(conn, ogr_id)
    veliler_sonrasi = db.kisiler_listele(conn, sinif_id=sinif_id, tur="veli")
    assert veliler_sonrasi[0]["ogrenci_kisi_id"] is None
    assert veliler_sonrasi[0]["ogrenci_ad"] is None
    conn.close()


def test_sinif_bazli_ogrenciler_ve_kisiler_id_ile(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_kisi_sorgular.db")
    db.semayi_kur()
    conn = db.baglanti()
    s1 = db.sinif_ekle(conn, "9-A")
    s2 = db.sinif_ekle(conn, "9-B")
    o1 = db.kisi_ekle(conn, "Ali", "05551111111", s1, "ogrenci")
    o2 = db.kisi_ekle(conn, "Veli", "05552222222", s1, "ogrenci")
    o3 = db.kisi_ekle(conn, "Can", "05553333333", s2, "ogrenci")

    harita = db.sinif_bazli_ogrenciler(conn)
    assert len(harita[s1]) == 2
    assert len(harita[s2]) == 1

    secilenler = db.kisiler_id_ile(conn, [o1, o3])
    assert len(secilenler) == 2
    ids = {r["id"] for r in secilenler}
    assert ids == {o1, o3}
    conn.close()


# --- Doğum günleri modülü (2026-09-20) ------------------------------------


def test_semayi_kur_personel_turunu_ekler_ve_veriyi_korur(tmp_path, monkeypatch):
    """Eski (personel'siz) şemadan başlayıp migration'ın veriyi bozmadan
    tur='personel' değerini kabul eder hale getirdiğini doğrular."""
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_migration.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")

    # Eski şemayı elle kur (personel'siz) — semayi_kur()'un migration'ı
    # tetiklemesi için başlangıç noktası budur.
    conn = sqlite3.connect(db.DB_YOLU)
    conn.execute("""
        CREATE TABLE siniflar (id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT NOT NULL UNIQUE)
    """)
    conn.execute("""
        CREATE TABLE kisiler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_soyad TEXT NOT NULL,
            telefon TEXT,
            sinif_id INTEGER NOT NULL REFERENCES siniflar (id),
            tur TEXT NOT NULL CHECK (tur IN ('ogrenci', 'veli')),
            ogrenci_kisi_id INTEGER REFERENCES kisiler (id)
        )
    """)
    conn.execute("INSERT INTO siniflar (ad) VALUES ('9-A')")
    conn.execute(
        "INSERT INTO kisiler (ad_soyad, telefon, sinif_id, tur) VALUES ('Ali Çimen', '05551111111', 1, 'ogrenci')"
    )
    conn.commit()
    conn.close()

    db.semayi_kur()

    conn = db.baglanti()
    # Veri korunmuş mu?
    kisi = conn.execute("SELECT * FROM kisiler WHERE ad_soyad = 'Ali Çimen'").fetchone()
    assert kisi["telefon"] == "05551111111"
    assert kisi["dogum_tarihi"] is None

    # 'personel' artık kabul ediliyor mu?
    yeni_id = db.kisi_ekle(conn, "Test Personel", None, 1, "personel")
    assert yeni_id is not None

    # Geçersiz tur hâlâ reddediliyor mu?
    try:
        conn.execute(
            "INSERT INTO kisiler (ad_soyad, sinif_id, tur) VALUES ('X', 1, 'hatali')"
        )
        conn.commit()
        raise AssertionError("CHECK kısıtı geçersiz tur'u reddetmeliydi")
    except sqlite3.IntegrityError:
        pass

    # Yedek dosyası oluştu mu?
    yedekler = list((tmp_path / "yedek").glob("*.db"))
    assert len(yedekler) == 1
    conn.close()


def test_semayi_kur_migration_idempotan(tmp_path, monkeypatch):
    """İkinci semayi_kur() çağrısı tabloyu tekrar yeniden kurmamalı (yedek
    dosyası çoğalmamalı, satır sayısı değişmemeli)."""
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_idempotan.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")

    db.semayi_kur()
    conn = db.baglanti()
    sinif_id = db.sinif_ekle(conn, "9-A")
    db.kisi_ekle(conn, "Ali", "05551111111", sinif_id, "ogrenci")
    onceki_sayim = conn.execute("SELECT COUNT(*) FROM kisiler").fetchone()[0]
    conn.close()

    db.semayi_kur()  # ikinci çağrı — migration zaten uygulanmış olmalı

    conn = db.baglanti()
    sonraki_sayim = conn.execute("SELECT COUNT(*) FROM kisiler").fetchone()[0]
    conn.close()
    assert sonraki_sayim == onceki_sayim
    # Bu senaryoda hiç migration tetiklenmedi (tablo baştan personel'li
    # kuruldu) — yedek dizini hiç oluşmamalı.
    assert not (tmp_path / "yedek").exists()


def test_semayi_kur_personel_ve_bilinmeyen_sinif_olusturur(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_sahte_siniflar.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    db.semayi_kur()
    conn = db.baglanti()
    adlar = [s["ad"] for s in db.siniflar_listele(conn)]
    conn.close()
    assert "Personel" in adlar
    assert "Bilinmeyen Sınıf" in adlar


def test_ayar_oku_yaz(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_ayar.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    db.semayi_kur()
    conn = db.baglanti()
    assert db.ayar_oku(conn, "sms_otomatik") == "0"
    db.ayar_yaz(conn, "sms_otomatik", "1")
    assert db.ayar_oku(conn, "sms_otomatik") == "1"
    assert db.ayar_oku(conn, "olmayan_anahtar") is None
    conn.close()


def test_kisi_bul_isimle_sinifsiz(tmp_path, monkeypatch):
    """Sınıf bilgisi olmayan Dogum.xlsx gibi kaynaklardan eşleştirme için —
    çağıran hangi sınıfta olduğunu bilmeden, yalnızca ad+tür ile bulabilmeli."""
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_sinifsiz.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    db.semayi_kur()
    conn = db.baglanti()
    s1 = db.sinif_ekle(conn, "9-A")
    db.kisi_ekle(conn, "Ali Çimen", None, s1, "ogrenci")

    bulunan = db.kisi_bul_isimle_sinifsiz(conn, "ALİ ÇİMEN", "ogrenci")
    assert bulunan is not None
    assert bulunan["sinif_id"] == s1

    bulunmayan = db.kisi_bul_isimle_sinifsiz(conn, "Olmayan Kişi", "ogrenci")
    assert bulunmayan is None
    conn.close()


def test_kisi_dogum_tarihi_guncelle(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_dogum_guncelle.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    db.semayi_kur()
    conn = db.baglanti()
    sinif_id = db.sinif_ekle(conn, "9-A")
    kisi_id = db.kisi_ekle(conn, "Ali Çimen", None, sinif_id, "ogrenci")
    db.kisi_dogum_tarihi_guncelle(conn, kisi_id, "2010-05-12")
    kisi = db.kisiler_listele(conn, sinif_id=sinif_id)[0]
    assert kisi["dogum_tarihi"] == "2010-05-12"
    conn.close()


def test_dogum_gunu_olanlar(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_dogum_bugun.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    db.semayi_kur()
    conn = db.baglanti()
    sinif_id = db.sinif_ekle(conn, "9-A")
    ali_id = db.kisi_ekle(conn, "Ali Çimen", "05551111111", sinif_id, "ogrenci")
    db.kisi_dogum_tarihi_guncelle(conn, ali_id, "2010-05-12")
    veli_id = db.kisi_ekle(conn, "Veli Anne", "05552222222", sinif_id, "veli")
    db.kisi_dogum_tarihi_guncelle(conn, veli_id, "2010-05-12")  # aynı gün ama veli — hariç tutulmalı

    bugun = db.dogum_gunu_olanlar(conn, 5, 12)
    assert len(bugun) == 1
    assert bugun[0]["ad_soyad"] == "Ali Çimen"

    yarin = db.dogum_gunu_olanlar(conn, 5, 13)
    assert yarin == []
    conn.close()


def test_dogum_gunu_olanlar_29_subat_28_subatta_da_eslesir(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_29subat.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    db.semayi_kur()
    conn = db.baglanti()
    sinif_id = db.sinif_ekle(conn, "9-A")
    kisi_id = db.kisi_ekle(conn, "Artık Yıl Çocuğu", None, sinif_id, "ogrenci")
    db.kisi_dogum_tarihi_guncelle(conn, kisi_id, "2008-02-29")

    sonuc = db.dogum_gunu_olanlar(conn, 2, 28)
    assert len(sonuc) == 1
    assert sonuc[0]["ad_soyad"] == "Artık Yıl Çocuğu"
    conn.close()


def test_dogum_tarihli_kisiler_yalnizca_dolu_olanlari_doner(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_dogum_tarihli.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    db.semayi_kur()
    conn = db.baglanti()
    sinif_id = db.sinif_ekle(conn, "9-A")
    ali_id = db.kisi_ekle(conn, "Ali Çimen", None, sinif_id, "ogrenci")
    db.kisi_ekle(conn, "Tarihsiz Kişi", None, sinif_id, "ogrenci")
    db.kisi_dogum_tarihi_guncelle(conn, ali_id, "2010-05-12")

    sonuc = db.dogum_tarihli_kisiler(conn)
    assert len(sonuc) == 1
    assert sonuc[0]["ad_soyad"] == "Ali Çimen"
    conn.close()
