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
    db.semayi_kur()
    conn = db.baglanti()
    siniflar = [s["ad"] for s in db.siniflar_listele(conn)]
    conn.close()
    assert siniflar == ["9-A", "9-B", "10-A", "10-B", "11-A", "11-B", "12-A", "12-B"]


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
