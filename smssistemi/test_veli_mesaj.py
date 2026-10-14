"""veli_mesaj.py testleri — sahte modem istemcisi, sahte (0555…) numaralar."""

import sqlite3
import threading
from unittest.mock import MagicMock

import pytest

import db
import sms_gonderici
import veli_mesaj


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "t.db")
    db.semayi_kur()
    c = db.baglanti()
    sid = c.execute("SELECT id FROM siniflar WHERE ad='9-A'").fetchone()["id"]
    c.execute("INSERT INTO kisiler (ad_soyad, telefon, sinif_id, tur) VALUES ('Test Ogrenci', '05550000001', ?, 'ogrenci')", (sid,))
    ogr = c.execute("SELECT id FROM kisiler").fetchone()["id"]
    c.execute("INSERT INTO kisiler (ad_soyad, telefon, sinif_id, tur, ogrenci_kisi_id) VALUES ('Test Veli', '0555 000 00 02', ?, 'veli', ?)", (sid, ogr))
    c.commit()
    yield c
    c.close()


def ham(index, tel, metin, zaman="2026-10-14 09:00:00", tur="1"):
    return {"Index": str(index), "Phone": tel, "Content": metin, "Date": zaman, "SmsType": tur}


@pytest.mark.parametrize("metin,beklenen", [
    ("Beni listeden ÇIKARIN", True), ("LÜTFEN GÖNDERMEYİN", True), ("cikarin lutfen", True),
    ("Rahatsız oluyorum", True), ("STOP", True), ("İPTAL", True), ("abonelik iptali", True),
    ("Teşekkürler, bilgi için sağ olun", False), ("yarın gelecek", False), ("", False),
])
def test_cikis_talebi(metin, beklenen):
    assert veli_mesaj.cikis_talebi_mi(metin) is beklenen


def test_eslestirme_veli_ve_bilinmeyen(conn):
    e = veli_mesaj.rehber_eslestir(conn, "05550000002")
    assert e["kisi_tur"] == "veli" and "veli — Test Ogrenci" in e["kisi_ad"] and e["sinif"] == "9-A"
    assert veli_mesaj.rehber_eslestir(conn, "05559999999")["kisi_ad"] is None


def test_kaydet_dogrular_tekrarda_mukerrer_yok(conn):
    mesajlar = [ham(3, "+905550000002", "Merhaba hocam"), ham(4, "05559999999", "durdurun")]
    assert veli_mesaj.mesajlari_kaydet(conn, mesajlar, set()) == [3, 4]
    assert veli_mesaj.mesajlari_kaydet(conn, mesajlar, set()) == [3, 4]  # tekrar: aynı doğrulama, mükerrer satır yok
    satirlar = conn.execute("SELECT * FROM veli_mesajlari ORDER BY id").fetchall()
    assert len(satirlar) == 2
    assert satirlar[0]["kisi_tur"] == "veli" and satirlar[0]["cikis_talebi"] == 0
    assert satirlar[1]["kisi_ad"] is None and satirlar[1]["cikis_talebi"] == 1


def test_teslim_raporu_ve_idare_numarasi(conn):
    sonuc = veli_mesaj.mesajlari_kaydet(
        conn, [ham(1, "05550000002", "rapor", tur="7"), ham(2, "05558888888", "selam")], {"05558888888"}
    )
    assert sonuc == [2]  # teslim raporu atlandı (modemde kalır)
    assert conn.execute("SELECT bildirim_durum FROM veli_mesajlari").fetchone()[0] == 2


def test_bildirim_metni_sinirlari():
    uzun = "x" * 500
    m = veli_mesaj.bildirim_metni([{"kisi_ad": "Ad", "telefon": "05550001234", "metin": uzun}, {}, {}])
    assert m.startswith("Veli mesajı: Ad: " + "x" * 100) and m.endswith("+2 yeni mesaj") and len(m) <= 300
    assert "numara 1234" in veli_mesaj.bildirim_metni([{"kisi_ad": None, "telefon": "05550001234", "metin": "a"}])


def _bildirim_hazirla(conn):
    veli_mesaj.mesajlari_kaydet(conn, [ham(1, "05550000002", "merhaba")], set())


def test_bildirim_basarili(conn, monkeypatch):
    _bildirim_hazirla(conn)

    def sahte(ayarlar, kisiler, cb, bayrak, bekleme):
        for i, t, m in kisiler:
            cb(i, t, m, "gonderildi", None)

    monkeypatch.setattr(sms_gonderici, "toplu_gonder", sahte)
    assert veli_mesaj.bildirim_gonder(conn, {}, [("Yonetici", "05551112233")]) == 1
    assert conn.execute("SELECT bildirim_durum FROM veli_mesajlari").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM gonderimler").fetchone()[0] == 1
    assert veli_mesaj.bildirim_gonder(conn, {}, [("Yonetici", "05551112233")]) == 0  # tekrar gitmez


def test_bildirim_basarisiz_3_denemede_vazgecer(conn, monkeypatch):
    _bildirim_hazirla(conn)
    monkeypatch.setattr(
        sms_gonderici, "toplu_gonder",
        lambda a, k, cb, b, s: [cb(i, t, m, "hata", "x") for i, t, m in k],
    )
    for beklenen_durum in (0, 0, 2):
        veli_mesaj.bildirim_gonder(conn, {}, [("Y", "05551112233")])
        assert conn.execute("SELECT bildirim_durum FROM veli_mesajlari").fetchone()[0] == beklenen_durum
    assert conn.execute("SELECT bildirim_deneme FROM veli_mesajlari").fetchone()[0] == 3


def test_bildirim_kilit_doluysa_atlanir(conn, monkeypatch):
    _bildirim_hazirla(conn)
    cagrildi = []
    monkeypatch.setattr(sms_gonderici, "toplu_gonder", lambda *a: cagrildi.append(1))
    sonuc = []
    with sms_gonderici.modem_kilidi:
        t = threading.Thread(target=lambda: sonuc.append(veli_mesaj.bildirim_gonder(conn2(conn), {}, [("Y", "05551112233")])))
        t.start(); t.join()
    assert sonuc == [0] and not cagrildi


def conn2(c):  # sqlite nesnesi thread'e bağlı; aynı DB için yeni bağlantı
    return db.baglanti()


def test_gelen_kutusu_isle_yalniz_dogrulananlari_siler(monkeypatch):
    client = MagicMock()
    gelen = {"Messages": {"Message": [ham(7, "05550000002", "a"), ham(8, "05550000002", "b")]}}
    client.sms.get_sms_list.side_effect = lambda page=1, box_type=None, **kw: (
        gelen if box_type == sms_gonderici.BoxTypeEnum.LOCAL_INBOX else {"Messages": None}
    )
    monkeypatch.setattr(sms_gonderici, "_baglan", lambda ayarlar: MagicMock())
    monkeypatch.setattr(sms_gonderici, "Client", lambda c: client)
    assert sms_gonderici.gelen_kutusunu_isle({}, lambda m: [8]) == 1
    client.sms.delete_sms.assert_called_once_with(8)
    # kaydedilemezse hiçbiri silinmez
    client.sms.delete_sms.reset_mock()
    assert sms_gonderici.gelen_kutusunu_isle({}, lambda m: []) == 0
    client.sms.delete_sms.assert_not_called()


def test_isleyici_hata_verirse_modemde_kalir(monkeypatch):
    client = MagicMock()
    gelen = {"Messages": {"Message": [ham(7, "05550000002", "a")]}}
    client.sms.get_sms_list.side_effect = lambda page=1, box_type=None, **kw: (
        gelen if box_type == sms_gonderici.BoxTypeEnum.LOCAL_INBOX else {"Messages": None}
    )
    monkeypatch.setattr(sms_gonderici, "_baglan", lambda ayarlar: MagicMock())
    monkeypatch.setattr(sms_gonderici, "Client", lambda c: client)

    def kotu(m):
        raise sqlite3.OperationalError("disk")

    with pytest.raises(sqlite3.OperationalError):
        sms_gonderici.gelen_kutusunu_isle({}, kotu)
    client.sms.delete_sms.assert_not_called()
    assert sms_gonderici.modem_kilidi.acquire(blocking=False)  # kilit serbest kaldı
    sms_gonderici.modem_kilidi.release()


def test_ulusal_bicimler_esit():
    for t in ("+905550000002", "905550000002", "05550000002", "0555 000 00 02", "5550000002"):
        assert veli_mesaj.ulusal(t) == "05550000002"
