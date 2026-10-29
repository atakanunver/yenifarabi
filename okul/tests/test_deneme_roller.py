"""Deneme: öğretmen/yönetici/öğrenci/veli yetkileri, PDF sunma, adlı görüntüleme kaydı. Tüm veri sahte."""

import json

import denemeler
import dosyalar
import pytest
from fastapi.testclient import TestClient
from kaynaklar import sms


@pytest.fixture
def istemci():
    from app import app

    with TestClient(app) as c:
        yield c


def _giris(c, kadi, sifre):
    assert (
        c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code
        == 303
    )


def _veli_giris(c, monkeypatch):
    giden = []
    monkeypatch.setattr(sms, "kod_gonder", lambda tel, metin: giden.append(metin))
    c.post("/veli-giris", data={"telefon": "05321112233"})
    c.post("/veli-kod", data={"telefon": "05321112233", "kod": giden[0].split(": ")[1][:6]})


@pytest.fixture
def veri(conn, ornek):
    """9-A: 101 (öğretmenin sınıfı) + 5 ek öğrenci; 9-B: 201. Deneme yayında, 101 ve 201'in PDF'i var."""
    for i in range(5):
        conn.execute(
            "INSERT INTO ogrenci (okul_no, ad_soyad, sinif) VALUES (?, ?, '9-A')", (300 + i, f"Ekstra {i}")
        )
    did = conn.execute("INSERT INTO deneme (ad, yayinda, olusturma) VALUES ('Aktif', 1, 'x')").lastrowid
    kaz = [{"ders": "Türkçe", "kazanim": "ZAYIFKAZANIM", "d": 0, "y": 2, "b": 1}]
    for no in (101, 300, 301, 302, 303, 304, 201):
        conn.execute(
            "INSERT INTO deneme_ogrenci (deneme_id, okul_no, veri, analiz) VALUES (?, ?, ?, ?)",
            (did, no, json.dumps({"toplam_net": 40.0, "dersler": {"Türkçe": 20.0}, "kazanimlar": kaz}), f"ANALIZ{no}"),
        )
    for no, icerik in ((101, b"%PDF-1.4 ALIPDF"), (201, b"%PDF-1.4 AYSEPDF")):
        denemeler.pdf_bagla(conn, did, no, dosyalar.deneme_pdf_kaydet(icerik).depo_adi)
    denemeler.yorum_yaz(conn, did, "9-A", "SINIFYORUMU")
    denemeler.yorum_yaz(conn, did, "", "OKULYORUMU")
    conn.commit()
    return did


def test_ogrenci_kendi_pdfini_alir_baskasininkini_alamaz(istemci, veri):
    _giris(istemci, "101", "ali-sifre")
    r = istemci.get(f"/ogrenci/deneme/{veri}/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and b"ALIPDF" in r.content
    assert f"/ogrenci/deneme/{veri}/pdf" in istemci.get("/ogrenci/deneme").text
    assert "ZAYIFKAZANIM" in istemci.get("/ogrenci/deneme").text


def test_ogrenci_yayinda_olmayan_pdf_404(istemci, veri, conn):
    conn.execute("UPDATE deneme SET yayinda = 0")
    conn.commit()
    _giris(istemci, "101", "ali-sifre")
    assert istemci.get(f"/ogrenci/deneme/{veri}/pdf").status_code == 404


def test_veli_yalniz_cocugunun_pdfi(istemci, veri, monkeypatch, ornek):
    _veli_giris(istemci, monkeypatch)
    r = istemci.get(f"/veli/deneme/{veri}/pdf?ogr={ornek['ogr1']}")
    assert r.status_code == 200 and b"ALIPDF" in r.content
    assert istemci.get(f"/veli/deneme/{veri}/pdf?ogr={ornek['ogr2']}").status_code == 404


def test_ogretmen_kendi_sinifini_gorur_baskasini_goremez(istemci, veri, conn):
    _giris(istemci, "hoca", "hoca-sifre")
    r = istemci.get(f"/ogretmen/deneme/{veri}/9-A")
    assert r.status_code == 200
    assert "SINIFYORUMU" in r.text and "ZAYIFKAZANIM" in r.text and "Ekstra 0" in r.text
    assert "OKULYORUMU" not in r.text
    assert "sıra" not in r.text.lower().replace("sıralama yok", "")
    assert istemci.get(f"/ogretmen/deneme/{veri}/9-B").status_code == 404
    # adlı görüntüleme kaydı
    assert conn.execute("SELECT COUNT(*) FROM erisim_log WHERE eylem = 'deneme:9-A'").fetchone()[0] == 1


def test_ogretmen_ogrenci_pdfi_yalniz_kendi_sinifi(istemci, veri):
    _giris(istemci, "hoca", "hoca-sifre")
    assert b"ALIPDF" in istemci.get(f"/ogretmen/deneme/{veri}/9-A/101/pdf").content
    assert istemci.get(f"/ogretmen/deneme/{veri}/9-A/201/pdf").status_code == 404  # 201, 9-B öğrencisi
    assert istemci.get(f"/ogretmen/deneme/{veri}/9-B/201/pdf").status_code == 404  # sınıf yetkisiz


def test_ogretmen_liste_ve_ogrenci_rolu_404(istemci, veri):
    _giris(istemci, "101", "ali-sifre")
    assert istemci.get("/ogretmen/deneme").status_code == 404
    assert istemci.get(f"/ogretmen/deneme/{veri}/9-A").status_code == 404
    assert istemci.get(f"/yonetici/deneme/{veri}").status_code == 404


def test_ogretmen_listede_kendi_sinifi(istemci, veri):
    _giris(istemci, "hoca", "hoca-sifre")
    t = istemci.get("/ogretmen/deneme").text
    assert "Aktif" in t and f"/ogretmen/deneme/{veri}/9-A" in t and "9-B" not in t


def test_yonetici_okul_ozeti_ve_her_sinif(istemci, veri, conn):
    _giris(istemci, "mudur", "mudur-sifre")
    r = istemci.get(f"/yonetici/deneme/{veri}")
    assert r.status_code == 200 and "OKULYORUMU" in r.text and "9-A" in r.text and "9-B" in r.text
    assert istemci.get(f"/ogretmen/deneme/{veri}/9-B").status_code == 200
    assert b"AYSEPDF" in istemci.get(f"/ogretmen/deneme/{veri}/9-B/201/pdf").content


def test_yonetici_yayinda_olmayan_denemeyi_gorur_ogretmen_gormez(istemci, veri, conn):
    conn.execute("UPDATE deneme SET yayinda = 0")
    conn.commit()
    _giris(istemci, "hoca", "hoca-sifre")
    assert istemci.get(f"/ogretmen/deneme/{veri}/9-A").status_code == 404
    istemci.cookies.clear()
    _giris(istemci, "mudur", "mudur-sifre")
    assert istemci.get(f"/yonetici/deneme/{veri}").status_code == 200
