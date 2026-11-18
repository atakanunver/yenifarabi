import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import auth
import cografya_oyun as oyun
import db
from scripts import geri_al


@pytest.fixture
def istemci():
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, ad="101", sifre="ali-sifre"):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": ad, "sifre": sifre}, follow_redirects=False).status_code == 303
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def basla(c, csrf, sayi=20):
    return c.post("/ogrenci/cografya/basla", data={"csrf": csrf, "mod": "bayrak", "yanit": "secmeli",
                                                   "bolge": "dunya", "soru_sayisi": sayi})


def bitir(c, csrf, oid, dogru=20, yanlis=0):
    return c.post(f"/ogrenci/cografya/{oid}/bitir", data={"csrf": csrf, "dogru": dogru, "yanlis": yanlis})


def test_akisi_xp_tavan_ve_tekrar(istemci, conn, ornek, saat):
    csrf = giris(istemci)
    for beklenen in (10, 10, 0):
        oid = basla(istemci, csrf).json()["oyun_id"]
        saat["an"] += timedelta(seconds=40)
        r = bitir(istemci, csrf, oid)
        assert r.status_code == 200 and r.json() == {"puan": 240, "sure_sn": 40, "xp": beklenen, "kaydedildi": True}
        assert bitir(istemci, csrf, oid).status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM cografya_oyun WHERE puan = 240").fetchone()[0] == 3
    assert conn.execute("SELECT SUM(miktar) FROM bilgi_xp WHERE kaynak = 'cografya'").fetchone()[0] == 20


def test_12_sinif_xp_yok(istemci, conn, ornek, saat):
    conn.execute("UPDATE ogrenci SET sinif='12-A' WHERE kullanici_id=?", (ornek["ogr1_k"],))
    conn.commit()
    csrf = giris(istemci)
    oid = basla(istemci, csrf).json()["oyun_id"]
    saat["an"] += timedelta(seconds=40)
    assert bitir(istemci, csrf, oid).json()["xp"] == 0
    assert conn.execute("SELECT COUNT(*) FROM bilgi_xp WHERE kaynak='cografya'").fetchone()[0] == 0


def test_limit_ve_hatalar(istemci, conn, ornek, saat):
    csrf = giris(istemci)
    oid = basla(istemci, csrf).json()["oyun_id"]
    saat["an"] += timedelta(seconds=5)
    assert bitir(istemci, csrf, oid).status_code == 400
    assert conn.execute("SELECT bitis, puan FROM cografya_oyun WHERE id=?", (oid,)).fetchone()[1] is None
    oid = basla(istemci, csrf).json()["oyun_id"]
    saat["an"] += timedelta(seconds=40)
    assert bitir(istemci, csrf, oid, 20, 1).status_code == 400
    for _ in range(28):
        assert basla(istemci, csrf).status_code == 200
    assert basla(istemci, csrf).status_code == 429
    assert istemci.post("/ogrenci/cografya/basla", data={}).status_code in (400, 403)


def test_yetki(istemci, conn, ornek, saat):
    csrf = giris(istemci)
    oid = basla(istemci, csrf).json()["oyun_id"]
    csrf2 = giris(istemci, "201", "ayse-sifre")
    assert bitir(istemci, csrf2, oid).status_code == 404
    giris(istemci, "hoca", "hoca-sifre")
    assert istemci.get("/ogrenci/cografya/liderlik").status_code == 404
    istemci.cookies.clear()
    istemci.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, ornek["veli1"]))
    assert istemci.get("/ogrenci/cografya/liderlik").status_code == 404


def test_liderlik(conn, ornek, saat, yeni_kullanici):
    kid = ornek["ogr1_k"]
    oid = oyun.baslat(conn, kid, "bayrak", "secmeli", "dunya", 20)
    saat["an"] += timedelta(seconds=60)
    oyun.bitir(conn, kid, oid, 5, 0, True)
    saat["an"] += timedelta(days=7)
    for i in range(12):
        k = yeni_kullanici(conn, "ogrenci", f"Deniz Soyad{i}", f"k{i}")
        conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (?, ?, '9-A', ?)",
                     (1000 + i, f"Deniz Soyad{i}", k))
        oid = oyun.baslat(conn, k, "bayrak", "secmeli", "dunya", 20)
        saat["an"] += timedelta(seconds=40)
        oyun.bitir(conn, k, oid, 20, 0, True)
    haftalik = oyun.liderlik(conn, kid, "bayrak", "secmeli", "dunya", "hafta", "okul", "9-A")
    assert len(haftalik["liste"]) == 10 and haftalik["ben"] is None
    genel = oyun.liderlik(conn, kid, "bayrak", "secmeli", "dunya", "genel", "sinif", "9-A")
    assert len(genel["liste"]) == 10 and genel["ben"]["sira"] == 13 and genel["ben"]["ad"] == "Ali V."
    assert all(x["ad"] == "Deniz S." for x in genel["liste"])


def test_liderlik_rota(istemci, ornek):
    giris(istemci)
    yol = "/ogrenci/cografya/liderlik?mod=bayrak&yanit=secmeli&bolge=dunya"
    assert istemci.get(yol).json() == {"liste": [], "ben": None}
    assert istemci.get(yol + "&donem=yanlis").status_code == 400


def test_sayfa(istemci, ornek):
    if not Path("templates/ogrenci/cografya.html").exists():
        pytest.skip("Şablon P1 paketinde")
    giris(istemci)
    assert istemci.get("/ogrenci/cografya").status_code == 200


def test_geri_al_42():
    c = sqlite3.connect(":memory:")
    c.executescript("\n".join(db.GOCLER))
    c.execute("INSERT INTO kullanici (id, rol, ad_soyad, olusturma) VALUES (1, 'ogrenci', 'Test', '2026')")
    for kaynak in ("cografya", "bilmece"):
        c.execute("INSERT INTO bilgi_xp (kullanici_id,kaynak,ref,miktar,gun,zaman) VALUES (1,?,'x',1,'2026','2026')", (kaynak,))
    c.executescript(geri_al.GERI[42])
    assert c.execute("SELECT kaynak FROM bilgi_xp").fetchall() == [("bilmece",)]
    assert not c.execute("SELECT name FROM sqlite_master WHERE name='cografya_oyun'").fetchall()
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO bilgi_xp (kullanici_id,kaynak,ref,miktar,gun,zaman) VALUES (1,'cografya','x',1,'2026','2026')")


def test_ogretmen_deneme_sayfasi_ve_yetki(istemci, conn, ornek):
    giris(istemci, "hoca", "hoca-sifre")
    r = istemci.get("/ogretmen/cografya")
    assert r.status_code == 200
    assert "Deneme modu: puan ve XP kaydedilmez." in r.text and 'data-deneme="1"' in r.text
    assert 'href="/ogretmen/cografya"' in istemci.get("/ogretmen").text
    giris(istemci, "mudur", "mudur-sifre")
    assert istemci.get("/ogretmen/cografya").status_code == 200
    giris(istemci)
    assert istemci.get("/ogretmen/cografya").status_code == 404


def test_veli_ogretmen_cografyasini_goremez(istemci, conn, ornek):
    istemci.cookies.clear()
    istemci.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, ornek["veli1"]))
    assert istemci.get("/ogretmen/cografya").status_code == 404


def test_ogrenci_sayfasi_deneme_degil(istemci, ornek):
    giris(istemci)
    r = istemci.get("/ogrenci/cografya")
    assert r.status_code == 200 and "data-deneme" not in r.text and "Deneme modu" not in r.text


def test_ogretmen_oyunu_xp_ve_liderlige_girmez(istemci, conn, ornek, saat):
    # Deneme modunda öğretmen sunucuya hiçbir uç çağırmaz; öğrenci uçları öğretmene kapalıdır (404), DB değişmez.
    xp_once = conn.execute("SELECT COUNT(*) FROM bilgi_xp").fetchone()[0]
    csrf = giris(istemci, "hoca", "hoca-sifre")
    assert basla(istemci, csrf).status_code == 404
    assert bitir(istemci, csrf, 1).status_code == 404
    assert istemci.get("/ogrenci/cografya/liderlik").status_code == 404
    assert conn.execute("SELECT COUNT(*) FROM cografya_oyun").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM bilgi_xp").fetchone()[0] == xp_once
    csrf = giris(istemci)
    oid = basla(istemci, csrf).json()["oyun_id"]
    saat["an"] += timedelta(seconds=40)
    assert bitir(istemci, csrf, oid).json()["xp"] == 10
    r = istemci.get("/ogrenci/cografya/liderlik?mod=bayrak&yanit=secmeli&bolge=dunya&donem=genel&kapsam=okul").json()
    assert [x["ad"] for x in r["liste"]] == ["Ali V."]
