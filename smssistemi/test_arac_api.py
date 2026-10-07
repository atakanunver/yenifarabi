"""arac_api.py — gerçek modem yok (gonder yamalanır), geçici SQLite.
Uç fonksiyonları doğrudan çağrılır (venv'de httpx/TestClient yok, bkz. requirements-dev.txt)."""

import json
from datetime import datetime

import arac_api as aa
import db
import pytest
from fastapi import HTTPException

ANAHTAR = "arac-test"
SIMDI = datetime(2026, 10, 5, 18, 0)


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "t.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    ayar = tmp_path / "arac.json"
    ayar.write_text(
        json.dumps(
            {
                "anahtar": ANAHTAR,
                "yonetim": [
                    {"ad": "Atakan Ünver", "telefon": "05559990011"},
                    {"ad": "Arzu Oral", "telefon": "5559990022"},
                ],
            }
        )
    )
    monkeypatch.setattr(aa, "AYAR_YOLU", ayar)
    db.semayi_kur()
    aa.sema_kur()
    saat = {"an": SIMDI}
    monkeypatch.setattr(aa, "simdi", lambda: saat["an"])
    giden = []

    def sahte_gonder(kisiler):
        giden.append(kisiler)
        return f"g{len(giden)}"

    monkeypatch.setattr(aa, "gonder", sahte_gonder)
    return giden, saat


def _kod(fonk, *a):
    with pytest.raises(HTTPException) as e:
        fonk(*a)
    return e.value.status_code


def _hat(metin="x", tarih="2026-10-14", saat=None):
    return aa.hatirlatma_kur(aa.HatirlatmaIstek(metin=metin, tarih=tarih, saat=saat))


def test_anahtar(ortam):
    assert _kod(aa.anahtar_dogrula, "yanlis") == 401
    assert _kod(aa.anahtar_dogrula, None) == 401
    aa.anahtar_dogrula(ANAHTAR)


def test_hatirlatma_saatsiz_10_00_ve_yonetime(ortam):
    y = _hat("Yarın kermes var.")
    assert y["zaman"] == "2026-10-14 10:00" and y["alicilar"] == [
        "Atakan Ünver",
        "Arzu Oral",
    ]


def test_hatirlatma_120_karakter_gecmis_ve_bicim(ortam):
    assert _kod(_hat, "x" * 121) == 422
    assert _kod(_hat, "x", "2026-10-05", "17:59") == 422
    assert _kod(_hat, "x", "14.10.2026") == 422
    assert _kod(_hat, "   ") == 422


def test_vadesi_gelen_gonderilir_bir_kez(ortam):
    giden, _ = ortam
    _hat("Toplantı 09:00.", "2026-10-17", "08:00")
    assert aa.vadesi_gelenleri_gonder(datetime(2026, 10, 17, 7, 59)) == 0
    assert aa.vadesi_gelenleri_gonder(datetime(2026, 10, 17, 8, 0)) == 1
    assert aa.vadesi_gelenleri_gonder(datetime(2026, 10, 17, 8, 1)) == 0
    assert giden == [
        [
            ("Atakan Ünver", "05559990011", "Toplantı 09:00."),
            ("Arzu Oral", "05559990022", "Toplantı 09:00."),
        ]
    ]


def test_cok_gec_kalan_kacirildi_sayilir(ortam):
    giden, _ = ortam
    _hat("x", "2026-10-06")
    assert aa.vadesi_gelenleri_gonder(datetime(2026, 10, 6, 17, 0)) == 0 and giden == []


def test_liste_ve_iptal(ortam):
    hid = _hat()["id"]
    assert [h["id"] for h in aa.hatirlatmalar()["hatirlatmalar"]] == [hid]
    assert aa.hatirlatma_iptal(hid)["durum"] == "iptal"
    assert _kod(aa.hatirlatma_iptal, hid) == 404
    assert aa.vadesi_gelenleri_gonder(datetime(2026, 10, 14, 10, 0)) == 0


def test_acil_hemen_yonetime(ortam):
    giden, _ = ortam
    y = aa.acil(aa.AcilIstek(metin="Okulda elektrik kesik."))
    assert y["gonderim_id"] == "g1" and len(giden[0]) == 2


def test_yonetim_tanimsizsa_503(ortam, tmp_path):
    (tmp_path / "arac.json").write_text(json.dumps({"anahtar": ANAHTAR}))
    assert _kod(_hat) == 503


@pytest.mark.parametrize("yazim", ["9-A", "9a", "9/A", " 9 A ", "9-a sınıfı"])
def test_sinif_yazimlari(yazim):
    assert aa._sinif_normalize(yazim) == "9-A"


def _veli_ekle(telefonlar):
    conn = db.baglanti()
    sid = next(s["id"] for s in db.siniflar_listele(conn) if s["ad"] == "9-A")
    for i, tel in enumerate(telefonlar):
        conn.execute(
            "INSERT INTO kisiler (ad_soyad, telefon, sinif_id, tur) VALUES (?, ?, ?, 'veli')",
            (f"Veli {i}", tel, sid),
        )
    conn.commit()
    conn.close()


def _taslak(sinif="9a", metin="Kermesimiz 15 Ekim'de."):
    return aa.veli_taslak(aa.VeliTaslakIstek(sinif=sinif, metin=metin))


def _gonder(tid):
    return aa.veli_gonder(aa.VeliGonderIstek(taslak_id=tid))


def test_veli_taslak_onay_sonra_gonderir_kardes_tek_sms(ortam):
    giden, _ = ortam
    _veli_ekle(["05551112233", "05551112233", "05554445566", ""])
    t = _taslak()
    assert t["sinif"] == "9-A" and t["alici_sayisi"] == 2 and giden == []
    assert _gonder(t["taslak_id"])["alici_sayisi"] == 2 and len(giden[0]) == 2
    assert _kod(_gonder, t["taslak_id"]) == 404  # ikinci kez gitmez


def test_veli_taslak_suresi_dolar(ortam):
    giden, saat = ortam
    _veli_ekle(["05551112233"])
    tid = _taslak(metin="x")["taslak_id"]
    saat["an"] = datetime(2026, 10, 5, 18, 31)
    assert _kod(_gonder, tid) == 410 and giden == []


def test_veli_bulunamazsa_404(ortam):
    assert _kod(_taslak, "13-Z", "x") == 404


def _ogrenci_ekle(telefonlar):
    conn = db.baglanti()
    sid = next(s["id"] for s in db.siniflar_listele(conn) if s["ad"] == "9-A")
    for i, tel in enumerate(telefonlar):
        conn.execute(
            "INSERT INTO kisiler (ad_soyad, telefon, sinif_id, tur) VALUES (?, ?, ?, 'ogrenci')",
            (f"Ogr {i}", tel, sid),
        )
    conn.commit()
    conn.close()


def _o_taslak(sinif="9a", metin="Yarin deneme sinavi var."):
    return aa.ogrenci_taslak(aa.VeliTaslakIstek(sinif=sinif, metin=metin))


def _o_gonder(tid):
    return aa.ogrenci_gonder(aa.VeliGonderIstek(taslak_id=tid))


def test_ogrenci_taslak_onay_sonra_gonderir_tekilleştirir(ortam):
    giden, _ = ortam
    _ogrenci_ekle(["05551112233", "05551112233", "05554445566", "", "123"])
    _veli_ekle(["05557778899"])  # veliler öğrenci alıcısına karışmaz
    t = _o_taslak()
    assert t["sinif"] == "9-A" and t["alici_sayisi"] == 2 and giden == []
    assert _o_gonder(t["taslak_id"])["alici_sayisi"] == 2
    assert {tel for _, tel, _ in giden[0]} == {"05551112233", "05554445566"}
    assert _kod(_o_gonder, t["taslak_id"]) == 404  # ikinci kez gitmez


def test_ogrenci_taslak_suresi_dolar_ve_bulunamazsa_404(ortam):
    giden, saat = ortam
    _ogrenci_ekle(["05551112233"])
    tid = _o_taslak()["taslak_id"]
    saat["an"] = datetime(2026, 10, 5, 18, 31)
    assert _kod(_o_gonder, tid) == 410 and giden == []
    assert _kod(_o_taslak, "13-Z", "x") == 404
    assert _kod(_o_taslak, "9a", "") == 422
    assert _kod(_o_taslak, "9a", "x" * (aa.VELI_AZAMI + 1)) == 422


def test_veli_ve_ogrenci_taslagi_capraz_gonderilemez(ortam):
    giden, _ = ortam
    _veli_ekle(["05551112233"])
    _ogrenci_ekle(["05554445566"])
    v, o = _taslak()["taslak_id"], _o_taslak()["taslak_id"]
    assert _kod(_o_gonder, v) == 404 and _kod(_gonder, o) == 404 and giden == []
    assert _gonder(v)["alici_sayisi"] == 1 and _o_gonder(o)["alici_sayisi"] == 1
    assert giden[0][0][1] == "05551112233" and giden[1][0][1] == "05554445566"


def test_eski_db_tur_kolonu_migration(ortam):
    conn = db.baglanti()
    conn.execute("DROP TABLE veli_taslaklari")
    conn.execute(
        "CREATE TABLE veli_taslaklari (id TEXT PRIMARY KEY, sinif TEXT NOT NULL, metin TEXT NOT NULL, "
        "alici_sayisi INTEGER NOT NULL, olusturma TEXT NOT NULL, "
        "durum TEXT NOT NULL DEFAULT 'taslak', gonderim_id TEXT)"
    )
    conn.execute("INSERT INTO veli_taslaklari VALUES ('eski','9-A','m',1,'2026-10-05 18:00','taslak',NULL)")
    conn.commit()
    conn.close()
    aa.sema_kur()
    aa.sema_kur()  # tekrar çalıştırmak güvenli
    conn = db.baglanti()
    assert conn.execute("SELECT tur FROM veli_taslaklari WHERE id='eski'").fetchone()["tur"] == "veli"
    conn.close()


def test_ogrenci_test_telefonu_yalnizca_o_numaraya_gider(ortam):
    giden, _ = ortam
    _ogrenci_ekle(["05551112233", "05554445566"])
    t = aa.ogrenci_taslak(
        aa.OgrenciTaslakIstek(sinif="9a", metin="deneme", test_telefon="05559998877")
    )
    assert t["test"] is True and t["alici_sayisi"] == 1
    assert _o_gonder(t["taslak_id"])["alici_sayisi"] == 1
    assert [tel for _, tel, _ in giden[0]] == ["05559998877"]
    assert _o_taslak()["test"] is False  # alan yoksa sınıfa gider
    assert _kod(
        aa.ogrenci_taslak,
        aa.OgrenciTaslakIstek(sinif="9a", metin="x", test_telefon="123"),
    ) == 422
