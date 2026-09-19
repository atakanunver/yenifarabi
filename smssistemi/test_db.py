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
