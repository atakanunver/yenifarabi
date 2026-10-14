"""Yeni öğrenci ana ekranı: görev listesi, hedef, hızlı çalışma, korunan okul bilgisi, 12. sınıf, boş durum."""

import auth
import kisisel
import maraton
import pytest
from fastapi.testclient import TestClient
from kaynaklar import arena_soru, kazanim
from kaynaklar import soru as havuz


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setattr(maraton, "kilit", lambda: None)
    monkeypatch.setattr(havuz, "dersler", lambda s: [("matematik", 40)])
    monkeypatch.setattr(arena_soru, "sorular", lambda *a, **k: [])
    monkeypatch.setattr(kazanim, "form_sonuclari", lambda okul_no: [])
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303


def test_ana_ekran_bolumleri(istemci, ornek, conn, saat):
    conn.execute("INSERT INTO odev (ogretmen_id, sinif, ders, tur, baslik, teslim, olusturma) VALUES (?, '9-A', 'matematik', 'klasik', 'Limit çalışması', '2026-10-13 09:00:00', 't')", (ornek["ogretmen"],))
    conn.commit()
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci").text
    assert "Merhaba" in t and "Ali" in t
    assert "Bugün ne yapacağım?" in t and "Limit çalışması" in t and 'href="/ogrenci/odev/1"' in t
    assert "Haftalık hedefim" in t and "Hedef koy" in t and "/ogrenci/hedefim" in t
    assert "Hızlı çalışma" in t and 'href="/ogrenci/maraton"' in t and "Hızlı Mod" in t
    assert "Gelişimim" in t and "/ogrenci/gelisim" in t
    # okul bilgisi korunur
    for korunan in ("Bugünkü dersler", "Yaklaşan sınavlar", "Duyurular"):
        assert korunan in t


def test_seviye_ve_hedef_ilerlemesi(istemci, ornek, conn, saat):
    o = conn.execute("SELECT * FROM ogrenci WHERE id = ?", (ornek["ogr1"],)).fetchone()
    kisisel.hedef_koy(conn, o, 4)
    conn.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (?, 'arena_bonus', '1', 60, '2026-10-12', 'z')", (ornek["ogr1_k"],))
    conn.commit()
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci").text
    assert "Seviye 2 · 60 XP" in t and "0</b> / 4 etkinlik" in t and 'aria-valuenow="0"' in t
    assert "Bu hafta için hedef koy" not in t  # hedef konduğu için görev yok


def test_12_sinif_arena_yok_ama_ekran_calisir(istemci, ornek, conn, saat):
    conn.execute("UPDATE ogrenci SET sinif = '12-A' WHERE id = ?", (ornek["ogr1"],))
    conn.commit()
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci").text
    assert "Günlük Görev" not in t and "Seviye" not in t and "Hızlı Mod" in t


def test_bos_durum_uydurma_gorev_yok(istemci, ornek, conn, saat):
    conn.execute("UPDATE ogrenci SET sinif = '12-A' WHERE id = ?", (ornek["ogr1"],))
    o = conn.execute("SELECT * FROM ogrenci WHERE id = ?", (ornek["ogr1"],)).fetchone()
    conn.commit()
    kisisel.hedef_koy(conn, o, 3)
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci").text
    assert "Bugün için bekleyen bir şeyin yok." in t


def test_diger_roller_ana_ekrani_goremez(istemci, ornek, conn):
    giris(istemci, "hoca", "hoca-sifre")
    assert istemci.get("/ogrenci").status_code == 404
    istemci.cookies.clear()
    istemci.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, ornek["veli1"]))
    assert istemci.get("/ogrenci").status_code == 404
