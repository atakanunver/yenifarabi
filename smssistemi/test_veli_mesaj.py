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


# --- spam engeli (2026-10-14) ---

def _spam_satirlari(conn):
    return {r["metin"]: r for r in conn.execute("SELECT * FROM veli_mesajlari")}


def test_kural_a_sistem_numarasi_spam(conn):
    mesajlar = [ham(1, "REKLAMX", "indirim"), ham(2, "2020", "kampanya"), ham(3, "08501234567", "reklam3"),
                ham(4, "05550000002", "veli mesajı")]
    assert veli_mesaj.mesajlari_kaydet(conn, mesajlar, set()) == [1, 2, 3, 4]  # spam da DB'de -> modemden silinir
    s = _spam_satirlari(conn)
    for m in ("indirim", "kampanya", "reklam3"):
        assert s[m]["spam"] == 1 and s[m]["spam_neden"] == "sistem numarası"
        assert s[m]["okundu"] == 1 and s[m]["bildirim_durum"] == 2
    assert s["veli mesajı"]["spam"] == 0 and s["veli mesajı"]["okundu"] == 0


def test_kural_b_engelli_numara(conn):
    conn.execute("INSERT INTO engelli_gonderenler (telefon, neden, zaman) VALUES ('05550007777', 'x', 'z')")
    conn.commit()
    veli_mesaj.mesajlari_kaydet(conn, [ham(1, "+905550007777", "yine ben")], set())
    r = _spam_satirlari(conn)["yine ben"]
    assert r["spam"] == 1 and r["spam_neden"] == "engelli" and r["okundu"] == 1 and r["bildirim_durum"] == 2


def test_rehberli_kisi_elle_engellenirse_spam(conn):
    conn.execute("INSERT INTO engelli_gonderenler (telefon) VALUES ('05550000002')")
    conn.commit()
    veli_mesaj.mesajlari_kaydet(conn, [ham(1, "05550000002", "rehberli")], set())
    r = _spam_satirlari(conn)["rehberli"]
    assert r["kisi_id"] is not None and r["spam"] == 1 and r["spam_neden"] == "engelli"


def test_idare_numarasi_asla_spam_olmaz(conn):
    conn.execute("INSERT INTO engelli_gonderenler (telefon) VALUES ('05558888888')")
    conn.commit()
    veli_mesaj.mesajlari_kaydet(conn, [ham(1, "05558888888", "idare"), ham(2, "2021", "kisa idare")],
                                {"05558888888", "2021"})
    s = _spam_satirlari(conn)
    assert s["idare"]["spam"] == 0 and s["kisa idare"]["spam"] == 0


def test_bildirimde_spam_yok(conn, monkeypatch):
    veli_mesaj.mesajlari_kaydet(conn, [ham(1, "REKLAMX", "indirim")], set())
    gonderilen = MagicMock()
    monkeypatch.setattr(veli_mesaj.sms_gonderici, "toplu_gonder", gonderilen)
    assert veli_mesaj.bildirim_gonder(conn, {}, [("Müdür", "05550009999")]) == 0
    gonderilen.assert_not_called()


def test_spam_7_gunden_eskiyi_siler(conn):
    veli_mesaj.mesajlari_kaydet(conn, [ham(1, "REKLAMX", "eski"), ham(2, "2020", "yeni"),
                                       ham(3, "05550000002", "normal")], set())
    conn.execute("UPDATE veli_mesajlari SET alinma = datetime('now', '-8 days')")
    conn.execute("UPDATE veli_mesajlari SET alinma = datetime('now', '-1 days') WHERE metin = 'yeni'")
    conn.commit()
    assert veli_mesaj.spam_temizle(conn) == 1
    assert set(_spam_satirlari(conn)) == {"yeni", "normal"}  # normal mesaj eski olsa da silinmez


def test_spam_modemden_yalniz_dbye_yazildiktan_sonra_silinir(conn, monkeypatch):
    client = MagicMock()
    gelen = {"Messages": {"Message": [ham(7, "REKLAMX", "indirim"), ham(8, "2020", "kampanya")]}}
    client.sms.get_sms_list.side_effect = lambda page=1, box_type=None, **kw: (
        gelen if box_type == sms_gonderici.BoxTypeEnum.LOCAL_INBOX else {"Messages": None}
    )
    monkeypatch.setattr(sms_gonderici, "_baglan", lambda ayarlar: MagicMock())
    monkeypatch.setattr(sms_gonderici, "Client", lambda c: client)

    def kotu(m):  # DB yazımı patlarsa spam da modemde kalır
        raise sqlite3.OperationalError("disk")

    with pytest.raises(sqlite3.OperationalError):
        sms_gonderici.gelen_kutusunu_isle({}, kotu)
    client.sms.delete_sms.assert_not_called()

    def iyi(m):
        return veli_mesaj.mesajlari_kaydet(conn, m, set())

    assert sms_gonderici.gelen_kutusunu_isle({}, iyi) == 2
    assert {c.args[0] for c in client.sms.delete_sms.call_args_list} == {7, 8}
    assert conn.execute("SELECT COUNT(*) FROM veli_mesajlari WHERE spam = 1").fetchone()[0] == 2
