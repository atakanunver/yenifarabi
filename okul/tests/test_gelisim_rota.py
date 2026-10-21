"""Akademik gelişim rotaları: yetki (404), KVKK erişim kaydı, kaynak erişilemezse açık uyarı, küçük grup, dil."""

import auth
import pytest
from fastapi.testclient import TestClient
from kaynaklar import KaynakHatasi, form_toplu
from kaynaklar.kazanim import TestSonucu


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setattr(form_toplu, "sonuclar", lambda nolar: {})
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303


def test_yonetici_okul_gelisim(istemci, ornek):
    giris(istemci, "mudur", "mudur-sifre")
    r = istemci.get("/yonetici/gelisim")
    assert r.status_code == 200 and "Akademik gelişim" in r.text and "0 / 2 öğrencinin" in r.text
    assert "risk" not in r.text.lower()


@pytest.mark.parametrize("kadi,sifre", [("hoca", "hoca-sifre"), ("101", "ali-sifre")])
def test_yonetici_ekrani_baskalarina_404(istemci, ornek, kadi, sifre):
    giris(istemci, kadi, sifre)
    assert istemci.get("/yonetici/gelisim").status_code == 404


def test_veli_hicbirini_goremez(istemci, ornek, conn):
    istemci.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, ornek["veli1"]))
    for yol in ("/yonetici/gelisim", "/ogretmen/gelisim/9-A", f"/ogretmen/ogrenci/{ornek['ogr1']}/gelisim", "/ogrenci/gelisim"):
        assert istemci.get(yol).status_code == 404


def test_ogretmen_sinif_yetkisi_ve_erisim_kaydi(istemci, ornek, conn):
    giris(istemci, "hoca", "hoca-sifre")  # 9-A öğretmeni
    r = istemci.get("/ogretmen/gelisim/9-A")
    assert r.status_code == 200 and "gelişim raporu" in r.text
    assert istemci.get("/ogretmen/gelisim/9-B").status_code == 404
    assert istemci.get(f"/ogretmen/ogrenci/{ornek['ogr1']}/gelisim").status_code == 200
    assert istemci.get(f"/ogretmen/ogrenci/{ornek['ogr2']}/gelisim").status_code == 404  # 9-B öğrencisi
    eylemler = [r[0] for r in conn.execute("SELECT eylem FROM erisim_log ORDER BY id")]
    assert eylemler == ["sinif_gelisim:9-A", "ogrenci_gelisim"]  # reddedilenler kayıt oluşturmaz


def test_ogrenci_kendi_gelisimi(istemci, ornek):
    giris(istemci, "101", "ali-sifre")
    r = istemci.get("/ogrenci/gelisim")
    assert r.status_code == 200 and "Gelişimim" in r.text and "Henüz test sonucun yok" in r.text
    assert istemci.get("/ogretmen/gelisim/9-A").status_code == 404
    assert istemci.get(f"/ogretmen/ogrenci/{ornek['ogr1']}/gelisim").status_code == 404


def test_ogrenci_ekrani_destekleyici_dil(istemci, ornek, monkeypatch):
    monkeypatch.setattr(form_toplu, "sonuclar", lambda nolar: {101: [TestSonucu("matematik", 1, "ZAYIF", 1, 5, "2026-10-01")]})
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci/gelisim").text
    assert "Tekrar edebileceğin kazanımlar" in t and "ZAYIF" in t and "yargı değil" in t
    for yasak in ("risk", "başarısız", "zayıf öğrenci", "sıralama"):
        assert yasak not in t.lower()


def test_kaynak_erisilemezse_uyari(istemci, ornek, monkeypatch):
    def patla(nolar):
        raise KaynakHatasi("pg")

    monkeypatch.setattr(form_toplu, "sonuclar", patla)
    giris(istemci, "hoca", "hoca-sifre")
    assert "ulaşılamıyor" in istemci.get("/ogretmen/gelisim/9-A").text
    giris(istemci, "mudur", "mudur-sifre")
    assert "ulaşılamıyor" in istemci.get("/yonetici/gelisim").text


def test_kucuk_grup_ekranda_gizli(istemci, ornek, monkeypatch):
    form = {101: [TestSonucu("matematik", 1, "K1", 3, 6, "2026-10-01")]}  # tek öğrencinin verisi
    monkeypatch.setattr(form_toplu, "sonuclar", lambda nolar: form)
    giris(istemci, "mudur", "mudur-sifre")
    t = istemci.get("/yonetici/gelisim").text
    assert "yeterli öğrenci verisi yok" in t and "%50" not in t
    giris(istemci, "hoca", "hoca-sifre")
    t = istemci.get("/ogretmen/gelisim/9-A").text
    assert "grup sonucu gizlendi" in t and "K1" not in t.split("Öğrenciler")[0]


def test_gelisim_raporlarinda_yazdir_dugmesi(istemci, ornek):
    giris(istemci, "hoca", "hoca-sifre")
    for yol in ("/ogretmen/gelisim/9-A", f"/ogretmen/ogrenci/{ornek['ogr1']}/gelisim"):
        t = istemci.get(yol).text
        assert 'onclick="window.print()"' in t and "yazdirma-gizle" in t
