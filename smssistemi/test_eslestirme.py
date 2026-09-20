import db
import gonderim


def test_veli_ogrenci_eslestirme_otomatik_baglar(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_esles.db")
    db.semayi_kur()
    conn = db.baglanti()

    sinif_id = db.sinif_ekle(conn, "9-A")
    ali_id = db.kisi_ekle(conn, "Ali Çimen", "05551111111", sinif_id, "ogrenci")

    csv_icerik = "Veli Adı,Öğrenci Adı,Telefon\nFatma Çimen,Ali Çimen,05552222222\n".encode("utf-8-sig")
    satirlar = gonderim.rehber_dosyasindan_oku("veliler.csv", csv_icerik, tur="veli")

    assert len(satirlar) == 1
    assert satirlar[0]["ad_soyad"] == "Fatma Çimen"
    assert satirlar[0]["ogrenci_adi"] == "Ali Çimen"

    # Eşleştirme simülasyonu (app.py rehber_yukle mantığı)
    ogr = db.kisi_bul_isimle(conn, satirlar[0]["ogrenci_adi"], sinif_id, "ogrenci")
    assert ogr is not None
    assert ogr["id"] == ali_id

    veli_id = db.kisi_ekle(
        conn,
        satirlar[0]["ad_soyad"],
        satirlar[0]["telefon"],
        sinif_id,
        "veli",
        ogrenci_kisi_id=ogr["id"],
    )

    veliler = db.kisiler_listele(conn, sinif_id=sinif_id, tur="veli")
    assert len(veliler) == 1
    assert veliler[0]["id"] == veli_id
    assert veliler[0]["ogrenci_kisi_id"] == ali_id
    assert veliler[0]["ogrenci_ad"] == "Ali Çimen"
    conn.close()


def test_veli_ogrenci_bulunamazsa_baglantisiz_ekler(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_esles_yok.db")
    db.semayi_kur()
    conn = db.baglanti()

    sinif_id = db.sinif_ekle(conn, "9-A")
    db.kisi_ekle(conn, "Ali Çimen", "05551111111", sinif_id, "ogrenci")

    csv_icerik = "Veli Adı,Öğrenci Adı,Telefon\nKemal Demir,Mehmet Demir,05553333333\n".encode("utf-8-sig")
    satirlar = gonderim.rehber_dosyasindan_oku("veliler.csv", csv_icerik, tur="veli")

    eslesmedi = 0
    ogr = db.kisi_bul_isimle(conn, satirlar[0]["ogrenci_adi"], sinif_id, "ogrenci")
    if ogr is not None:
        ogr_id = ogr["id"]
    else:
        eslesmedi += 1
        ogr_id = None

    assert eslesmedi == 1
    assert ogr_id is None

    veli_id = db.kisi_ekle(
        conn, satirlar[0]["ad_soyad"], satirlar[0]["telefon"], sinif_id, "veli", ogrenci_kisi_id=None
    )

    veliler = db.kisiler_listele(conn, sinif_id=sinif_id, tur="veli")
    assert len(veliler) == 1
    assert veliler[0]["id"] == veli_id
    assert veliler[0]["ogrenci_kisi_id"] is None
    assert veliler[0]["ogrenci_ad"] is None

    # Elle bağlama testi
    db.kisi_ogrenci_bagla(conn, veli_id, ali_id := 1)
    veliler_guncel = db.kisiler_listele(conn, sinif_id=sinif_id, tur="veli")
    assert veliler_guncel[0]["ogrenci_kisi_id"] == 1
    assert veliler_guncel[0]["ogrenci_ad"] == "Ali Çimen"
    conn.close()


def test_turkce_karakter_duyarsiz_isim_eslesmesi(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_tr.db")
    db.semayi_kur()
    conn = db.baglanti()

    sinif_id = db.sinif_ekle(conn, "10-A")
    db.kisi_ekle(conn, "İSMAİL IŞIK", "05551111111", sinif_id, "ogrenci")

    bulunan = db.kisi_bul_isimle(conn, "ismail ışık", sinif_id, "ogrenci")
    assert bulunan is not None
    assert bulunan["ad_soyad"] == "İSMAİL IŞIK"

    bulunan2 = db.kisi_bul_isimle(conn, "  İSMAİL  IŞIK  ", sinif_id, "ogrenci")
    assert bulunan2 is not None
    conn.close()


def test_kisisellestirme_veli_ve_ogrenci_senaryosu(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_kisisel.db")
    db.semayi_kur()
    conn = db.baglanti()

    sinif_id = db.sinif_ekle(conn, "9-A")
    ogr_id = db.kisi_ekle(conn, "Ali Çimen", "05551111111", sinif_id, "ogrenci")
    veli_id = db.kisi_ekle(
        conn, "Fatma Çimen", "05552222222", sinif_id, "veli", ogrenci_kisi_id=ogr_id
    )
    veli_baglantisiz_id = db.kisi_ekle(
        conn, "Ahmet Yılmaz", "05553333333", sinif_id, "veli", ogrenci_kisi_id=None
    )

    sablon = "Sayın {isim}, öğrencimiz {ogrenci_adi} yarın sınava girecektir."

    kisiler = db.kisiler_id_ile(conn, [ogr_id, veli_id, veli_baglantisiz_id])
    kisi_map = {k["id"]: k for k in kisiler}

    # 1. Veli için: bağlı öğrencinin adını kullanır
    k_veli = kisi_map[veli_id]
    ogr_ad = k_veli["ogrenci_ad"] if k_veli["tur"] == "veli" else k_veli["ad_soyad"]
    mesaj_veli = gonderim.kisisellestir(sablon, k_veli["ad_soyad"], ogr_ad or "")
    assert mesaj_veli == "Sayın Fatma Çimen, öğrencimiz Ali Çimen yarın sınava girecektir."

    # 2. Öğrenci için: kendi adını kullanır
    k_ogr = kisi_map[ogr_id]
    ogr_ad = k_ogr["ogrenci_ad"] if k_ogr["tur"] == "veli" else k_ogr["ad_soyad"]
    mesaj_ogr = gonderim.kisisellestir(sablon, k_ogr["ad_soyad"], ogr_ad or "")
    assert mesaj_ogr == "Sayın Ali Çimen, öğrencimiz Ali Çimen yarın sınava girecektir."

    # 3. Bağlantısız veli için: {ogrenci_adi} boş kalır
    k_baglantisiz = kisi_map[veli_baglantisiz_id]
    ogr_ad = k_baglantisiz["ogrenci_ad"] if k_baglantisiz["tur"] == "veli" else k_baglantisiz["ad_soyad"]
    mesaj_baglantisiz = gonderim.kisisellestir(sablon, k_baglantisiz["ad_soyad"], ogr_ad or "")
    assert mesaj_baglantisiz == "Sayın Ahmet Yılmaz, öğrencimiz  yarın sınava girecektir."

    conn.close()
