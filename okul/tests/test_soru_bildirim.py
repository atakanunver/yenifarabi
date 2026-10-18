"""Soru bildirimi: görmediği soruyu bildirememe, tek kayıt, eşikte gizleme, yetki, API anahtarı."""

import json

import pytest
import soru_bildirim
from ayarlar import AYAR

from tests.test_web_belge_sinav import giris, istemci  # noqa: F401


def _maraton_sorusu(conn, kullanici_id, soru_id=500):
    cur = conn.execute(
        "INSERT INTO maraton (kullanici_id, sinif, duzey, ders, basla, bitis) VALUES (?, '9-A', 9, 'fizik', '2026-10-18 10:00:00', '2026-10-18 10:05:00')",
        (kullanici_id,),
    )
    conn.execute(
        "INSERT INTO maraton_soru (maraton_id, sira, soru_id, soru, secenekler, dogru_index) VALUES (?, 1, ?, 's', ?, 0)",
        (cur.lastrowid, soru_id, json.dumps(["a", "b", "c", "d"])),
    )
    conn.commit()
    return cur.lastrowid


def test_gormedigi_soruyu_bildiremez(conn, ornek):
    with pytest.raises(soru_bildirim.BildirimHatasi):
        soru_bildirim.bildir(conn, ornek["ogr1_k"], 999, "sekil")


def test_bildirim_tek_kayit_ve_gecersiz_tur(conn, ornek):
    _maraton_sorusu(conn, ornek["ogr1_k"])
    assert soru_bildirim.bildir(conn, ornek["ogr1_k"], 500, "sekil") is True
    assert soru_bildirim.bildir(conn, ornek["ogr1_k"], 500, "cevap") is False  # aynı öğrenci aynı soru
    assert conn.execute("SELECT count(*) FROM soru_bildirim").fetchone()[0] == 1
    with pytest.raises(soru_bildirim.BildirimHatasi):
        soru_bildirim.bildir(conn, ornek["ogr1_k"], 500, "hakaret")


def test_esikte_gizlenir(conn, ornek):
    _maraton_sorusu(conn, ornek["ogr1_k"])
    _maraton_sorusu(conn, ornek["ogr2_k"])
    soru_bildirim.bildir(conn, ornek["ogr1_k"], 500, "sekil")
    assert soru_bildirim.gizli_idler(conn) == []
    soru_bildirim.bildir(conn, ornek["ogr2_k"], 500, "sekil")
    assert soru_bildirim.gizli_idler(conn) == [500]
    assert soru_bildirim.ozet(conn)[0]["turler"] == {"sekil": 2}


def test_gunluk_limit(conn, ornek, monkeypatch):
    monkeypatch.setattr(soru_bildirim, "GUNLUK_LIMIT", 2)
    for i in range(3):
        _maraton_sorusu(conn, ornek["ogr1_k"], 600 + i)
    soru_bildirim.bildir(conn, ornek["ogr1_k"], 600, "sekil")
    soru_bildirim.bildir(conn, ornek["ogr1_k"], 601, "sekil")
    with pytest.raises(soru_bildirim.BildirimHatasi):
        soru_bildirim.bildir(conn, ornek["ogr1_k"], 602, "sekil")


def test_web_bildirim_yetki_ve_acik_yonlendirme(istemci, conn, ornek):
    c = istemci
    mid = _maraton_sorusu(conn, ornek["ogr1_k"])
    csrf = giris(c, "101", "ali-sifre")
    r = c.post("/ogrenci/soru-bildir", data={"csrf": csrf, "soru_id": 500, "tur": "sekil", "geri": "//kotu.example"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/ogrenci"  # açık yönlendirme yok
    r = c.post("/ogrenci/soru-bildir", data={"csrf": csrf, "soru_id": 777, "tur": "sekil"})
    assert r.status_code == 400
    csrf = giris(c, "201", "ayse-sifre")
    assert c.post("/ogrenci/soru-bildir", data={"csrf": csrf, "soru_id": 500, "tur": "sekil"}).status_code == 400
    csrf = giris(c, "hoca", "hoca-sifre")  # öğretmen bildiremez
    assert c.post("/ogrenci/soru-bildir", data={"csrf": csrf, "soru_id": 500, "tur": "sekil"}).status_code == 404
    assert c.get("/yonetici/soru-bildirimleri").status_code == 404
    assert mid


def test_yonetici_listesi(istemci, conn, ornek, monkeypatch):
    from kaynaklar import soru as havuz

    monkeypatch.setattr(havuz, "getir", lambda ids: {i: {"soru": "Şekildeki cisim?", "ders": "fizik", "sinif": 9, "durum": "onayli"} for i in ids})
    _maraton_sorusu(conn, ornek["ogr1_k"])
    soru_bildirim.bildir(conn, ornek["ogr1_k"], 500, "sekil")
    giris(istemci, "mudur", "mudur-sifre")
    r = istemci.get("/yonetici/soru-bildirimleri")
    assert r.status_code == 200 and "#500" in r.text and "Şekil / grafik görünmüyor" in r.text


def test_api_anahtar_ve_tunel(istemci, conn, ornek, monkeypatch):
    monkeypatch.setattr(AYAR, "soru_anahtar", "gizli-anahtar")
    _maraton_sorusu(conn, ornek["ogr1_k"])
    soru_bildirim.bildir(conn, ornek["ogr1_k"], 500, "sekil")
    assert istemci.get("/api/soru-bildirim").status_code == 404
    assert istemci.get("/api/soru-bildirim", headers={"X-Soru-Anahtar": "yanlis"}).status_code == 404
    assert istemci.get("/api/soru-bildirim", headers={"X-Soru-Anahtar": "gizli-anahtar", "CF-Ray": "x"}).status_code == 404
    r = istemci.get("/api/soru-bildirim", headers={"X-Soru-Anahtar": "gizli-anahtar"})
    assert r.status_code == 200
    assert r.json()["sorular"] == [{"soru_id": 500, "kisi": 1, "turler": {"sekil": 1}, "son": r.json()["sorular"][0]["son"]}]
    monkeypatch.setattr(AYAR, "soru_anahtar", "")  # anahtar tanımsızsa uç kapalı
    assert istemci.get("/api/soru-bildirim", headers={"X-Soru-Anahtar": ""}).status_code == 404
