"""Denemeler: yetki (404), yükleyici (kuru/idempotent/uyuşmazlık), göç. Tüm veri sahte."""

import json
import sqlite3

import db
import denemeler
import pytest
from fastapi.testclient import TestClient
from kaynaklar import sms
from scripts import deneme_yukle

SATIR1 = {
    "okul_no": 101,
    "ad_soyad": "ali veli",
    "sinif": "9-A",
    "girdi": 1,
    "veri": {"toplam_net": 55.5, "dersler": {"Türkçe": 19.25, "Matematik": 12}},
    "analiz": "Güçlü yön ALIPAR\nikinci satır",
    "tavsiye": "Tekrar çöz",
}
SATIR2 = {
    "okul_no": 201,
    "ad_soyad": "Ayşe Kaya",
    "sinif": "9-B",
    "veri": {"toplam_net": 40, "dersler": {"Türkçe": 10}},
    "analiz": "AYSEANALIZ",
    "tavsiye": "",
}


def belge(*satirlar, ad="Deneme 1"):
    return {"ad": ad, "tarih": "2026-10-10", "ozet": "özet", "ogrenciler": list(satirlar)}


def test_goc_tablolari_kurar(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.GOCLER)
    for t in ("deneme", "deneme_ogrenci"):
        conn.execute(f"SELECT * FROM {t}")


def test_yukle_kuru_hicbir_sey_yazmaz(conn, ornek):
    s = denemeler.yukle(conn, belge(SATIR1, SATIR2), kuru=True)
    assert (s["eslesen"], s["eslesmeyen"], s["uyusmayan"]) == (2, 0, 0)
    assert conn.execute("SELECT COUNT(*) FROM deneme").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM deneme_ogrenci").fetchone()[0] == 0


def test_yukle_uyusmazlik_uygulanmaz(conn, ornek):
    yanlis_ad = {**SATIR1, "ad_soyad": "Başka Kişi"}
    yanlis_sinif = {**SATIR2, "sinif": "9-A"}
    yok = {**SATIR1, "okul_no": 999}
    s = denemeler.yukle(conn, belge(yanlis_ad, yanlis_sinif, yok))
    assert (s["eslesen"], s["eslesmeyen"], s["uyusmayan"]) == (0, 1, 2)
    assert conn.execute("SELECT COUNT(*) FROM deneme_ogrenci").fetchone()[0] == 0


def test_yukle_idempotent_varsayilan_yayinda_degil(conn, ornek):
    denemeler.yukle(conn, belge(SATIR1))
    denemeler.yukle(conn, belge({**SATIR1, "analiz": "güncel"}, SATIR2))
    assert conn.execute("SELECT COUNT(*) FROM deneme").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM deneme_ogrenci").fetchone()[0] == 2
    assert conn.execute("SELECT yayinda FROM deneme").fetchone()[0] == 0
    assert (
        conn.execute("SELECT analiz FROM deneme_ogrenci WHERE okul_no = 101").fetchone()[0]
        == "güncel"
    )
    # yeniden yükleme yayını geri almaz; --yayinla açar
    denemeler.yukle(conn, belge(SATIR1), yayinla=True)
    denemeler.yukle(conn, belge(SATIR1))
    assert conn.execute("SELECT yayinda FROM deneme").fetchone()[0] == 1


def test_script_kuru_salt_okunur(ornek, tmp_path, capsys):
    conn = db.baglanti()
    conn.close()
    yol = tmp_path / "d.json"
    yol.write_text(json.dumps(belge(SATIR1)), encoding="utf-8")
    assert deneme_yukle.main([str(yol), "--kuru"]) == 0
    assert "eşleşen=1" in capsys.readouterr().out
    c = sqlite3.connect(db.AYAR.db_yolu)
    assert c.execute("SELECT COUNT(*) FROM deneme").fetchone()[0] == 0
    c.close()
    assert deneme_yukle.main([str(yol), "--yayinla"]) == 0
    c = sqlite3.connect(db.AYAR.db_yolu)
    assert c.execute("SELECT yayinda FROM deneme").fetchone()[0] == 1
    c.close()


@pytest.fixture
def istemci():
    from app import app

    with TestClient(app) as c:
        yield c


def _giris(c, kadi, sifre):
    r = c.post(
        "/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False
    )
    assert r.status_code == 303


def _veli_giris(c, monkeypatch):
    giden = []
    monkeypatch.setattr(sms, "kod_gonder", lambda tel, metin: giden.append(metin))
    c.post("/veli-giris", data={"telefon": "05321112233"})
    c.post(
        "/veli-kod",
        data={"telefon": "05321112233", "kod": giden[0].split(": ")[1][:6]},
    )


def _id(conn):
    return conn.execute("SELECT id FROM deneme").fetchone()[0]


def test_ogrenci_yalniz_kendi_yayindaki_denemesi(istemci, ornek, conn):
    denemeler.yukle(conn, belge(SATIR1, SATIR2))
    did = _id(conn)
    _giris(istemci, "101", "ali-sifre")
    # yayında=0 -> 404
    assert istemci.get(f"/ogrenci/deneme/{did}").status_code == 404
    assert "ALIPAR" not in istemci.get("/ogrenci/deneme").text
    conn.execute("UPDATE deneme SET yayinda = 1")
    conn.commit()
    r = istemci.get(f"/ogrenci/deneme/{did}")
    assert r.status_code == 200
    assert "ALIPAR" in r.text and "19.25" in r.text and "55.5" in r.text
    assert "AYSEANALIZ" not in istemci.get("/ogrenci/deneme").text
    assert "/ogrenci/deneme" in istemci.get("/ogrenci").text


def test_ogrenci_baskasinin_denemesi_404(istemci, ornek, conn):
    denemeler.yukle(conn, belge(SATIR2), yayinla=True)  # yalnız öğrenci 201
    did = _id(conn)
    _giris(istemci, "101", "ali-sifre")
    assert istemci.get(f"/ogrenci/deneme/{did}").status_code == 404
    assert "Yayınlanmış deneme sonucu yok" in istemci.get("/ogrenci/deneme").text


def test_veli_yalniz_cocugu(istemci, ornek, conn, monkeypatch):
    denemeler.yukle(conn, belge(SATIR1, SATIR2), yayinla=True)
    did = _id(conn)
    _veli_giris(istemci, monkeypatch)
    assert istemci.get(f"/veli/deneme?ogr={ornek['ogr2']}").status_code == 404
    assert istemci.get(f"/veli/deneme/{did}?ogr={ornek['ogr2']}").status_code == 404
    r = istemci.get(f"/veli/deneme?ogr={ornek['ogr1']}")
    assert r.status_code == 200 and "ALIPAR" in r.text and "AYSEANALIZ" not in r.text
    assert istemci.get(f"/veli/deneme/{did}?ogr={ornek['ogr1']}").status_code == 200
    assert "/veli/deneme?ogr=" in istemci.get("/veli").text
    n = conn.execute(
        "SELECT COUNT(*) FROM erisim_log WHERE eylem = 'veli_deneme'"
    ).fetchone()[0]
    assert n >= 2
    # yayından kalkınca 404
    conn.execute("UPDATE deneme SET yayinda = 0")
    conn.commit()
    assert istemci.get(f"/veli/deneme/{did}?ogr={ornek['ogr1']}").status_code == 404


def test_rol_ayrimi(istemci, ornek):
    _giris(istemci, "hoca", "hoca-sifre")
    assert istemci.get("/ogrenci/deneme").status_code == 404
    assert istemci.get("/veli/deneme").status_code == 404
