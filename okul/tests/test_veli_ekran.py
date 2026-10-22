"""Veli ana ekranı (Şimdi / Yapılması gerekenler / Bugün-yarın), onay belgeleri ve okula mesaj."""

import json
import sqlite3
from datetime import datetime

import auth
import duyurular
import onay
import pytest
import veli_bugun
import zaman
from ayarlar import AYAR
from fastapi.testclient import TestClient
from kaynaklar import kazanim


@pytest.fixture
def istemci(monkeypatch, ornek, saat):
    monkeypatch.setattr(kazanim, "form_sonuclari", lambda okul_no: [])
    AYAR.program_yolu.write_text(json.dumps({"siniflar": {"9-A": {
        "pazartesi": {"1": "matematik", "2": "fizik"}, "sali": {"1": "kimya"}}}}), encoding="utf-8")
    AYAR.zil_yolu.write_text(json.dumps({"dersler": [
        {"no": 1, "baslangic": "08:10", "bitis": "08:50"}, {"no": 2, "baslangic": "09:00", "bitis": "09:40"}]}), encoding="utf-8")
    AYAR.takvim_yolu.write_text(json.dumps({"tatiller": []}), encoding="utf-8")
    from app import app

    with TestClient(app) as c:
        yield c


def veli(c, conn, ornek):
    c.cookies.clear()
    token = auth.oturum_ac(conn, ornek["veli1"])
    c.cookies.set(auth.COOKIE_ADI, token)
    return auth.csrf_token(token)


def cocuk(conn, ornek):
    return conn.execute("SELECT * FROM ogrenci WHERE id = ?", (ornek["ogr1"],)).fetchone()


# --- Şimdi / akış ---


def test_simdi_ders_ve_teneffus(istemci, saat, conn, ornek):
    c = cocuk(conn, ornek)
    saat["an"] = datetime(2026, 10, 12, 8, 30)
    s = veli_bugun.simdi(c)
    assert s["tur"] == "ders" and "1. ders: Matematik" in s["baslik"] and s["alt"] == "08:10 - 08:50"
    saat["an"] = datetime(2026, 10, 12, 8, 55)
    assert veli_bugun.simdi(c)["tur"] == "teneffus"
    saat["an"] = datetime(2026, 10, 12, 12, 0)
    assert veli_bugun.simdi(c)["tur"] == "bitti"
    saat["an"] = datetime(2026, 10, 11, 10, 0)  # pazar
    assert veli_bugun.simdi(c)["tur"] == "tatil"


def test_akis_bugun_ve_yarin(istemci, saat, conn, ornek):
    c = cocuk(conn, ornek)
    saat["an"] = datetime(2026, 10, 12, 8, 30)  # pazartesi
    a = veli_bugun.akis(c)
    assert [d["ders"] for d in a["bugun"]] == ["matematik", "fizik"] and a["bugun"][0]["simdi"] and not a["bugun"][1]["gecti"]
    assert a["yarin"]["etiket"] == "Yarın" and a["yarin"]["dersler"][0]["ders"] == "kimya"
    saat["an"] = datetime(2026, 10, 16, 17, 0)  # cuma akşamı: sonraki okul günü
    a = veli_bugun.akis(c)
    assert a["bugun"] == [] and a["yarin"]["etiket"] == "Pazartesi"


def test_ana_ekran_buyuk_sade(istemci, saat, conn, ornek):
    saat["an"] = datetime(2026, 10, 12, 8, 30)
    veli(istemci, conn, ornek)
    h = istemci.get("/veli").text
    assert 'class="veli"' in h and "veli.css" in h and 'data-tema="harita"' in h
    assert "Şu an 1. ders: Matematik" in h and "Yapılması gerekenler" in h and "Ders programı" in h
    assert 'href="/kutu"' in h and "Okula mesaj yazın" in h


def test_yapilacaklar_onay_duyuru_oncelik(istemci, saat, conn, ornek):
    saat["an"] = datetime(2026, 10, 12, 12, 0)
    veli(istemci, conn, ornek)
    assert "Şu an sizi bekleyen bir şey yok" in istemci.get("/veli").text
    duyurular.duyuru_ekle(conn, ornek["yonetici"], "Veli toplantısı", "Cuma 17:00", "okul", None, None)
    onay.olustur(conn, conn.execute("SELECT * FROM kullanici WHERE id = ?", (ornek["yonetici"],)).fetchone(), "Müze gezisi", "28 Ekim", "okul", None, "2026-10-20")
    h = istemci.get("/veli").text
    assert "Onayınız bekleniyor: Müze gezisi" in h and "Yeni duyuru: Veli toplantısı" in h
    assert h.index("Müze gezisi") < h.index("Veli toplantısı")  # onay önce


# --- onay belgeleri ---


def yonetici_k(conn, ornek):
    return conn.execute("SELECT * FROM kullanici WHERE id = ?", (ornek["yonetici"],)).fetchone()


def test_onay_yanitla_degistir_ve_sure(istemci, saat, conn, ornek):
    saat["an"] = datetime(2026, 10, 12, 12, 0)
    t = onay.olustur(conn, yonetici_k(conn, ornek), "Gezi izni", "", "sinif", "9-A", "2026-10-14")
    csrf = veli(istemci, conn, ornek)
    assert "Gezi izni" in istemci.get("/veli/onaylar").text
    r = istemci.post(f"/veli/onay/{t}", data={"csrf": csrf, "ogr": ornek["ogr1"], "yanit": "evet"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Onayladınız" in istemci.get("/veli/onaylar").text
    istemci.post(f"/veli/onay/{t}", data={"csrf": csrf, "ogr": ornek["ogr1"], "yanit": "hayir"})  # değiştir
    assert conn.execute("SELECT yanit FROM onay_yanit WHERE talep_id = ?", (t,)).fetchone()[0] == "hayir"
    assert conn.execute("SELECT count(*) FROM onay_yanit").fetchone()[0] == 1
    saat["an"] = datetime(2026, 10, 15, 9, 0)  # süre doldu
    r = istemci.post(f"/veli/onay/{t}", data={"csrf": csrf, "ogr": ornek["ogr1"], "yanit": "evet"}, follow_redirects=False)
    assert r.status_code == 303 and "hata=sure" in r.headers["location"]
    assert conn.execute("SELECT yanit FROM onay_yanit WHERE talep_id = ?", (t,)).fetchone()[0] == "hayir"
    assert "yanıt süresi dolmuş" in istemci.get("/veli/onaylar?hata=sure").text
    assert "SAHTEMESAJ" not in istemci.get("/veli/onaylar?hata=SAHTEMESAJ").text  # URL'den gelen metin yansıtılmaz


def test_onay_baska_cocuk_ve_sinif_404(istemci, saat, conn, ornek):
    saat["an"] = datetime(2026, 10, 12, 12, 0)
    diger_sinif = onay.olustur(conn, yonetici_k(conn, ornek), "Sadece 9-B", "", "sinif", "9-B", "2026-10-20")
    csrf = veli(istemci, conn, ornek)
    assert "Sadece 9-B" not in istemci.get("/veli/onaylar").text
    assert istemci.post(f"/veli/onay/{diger_sinif}", data={"csrf": csrf, "ogr": ornek["ogr1"], "yanit": "evet"}).status_code == 404
    t = onay.olustur(conn, yonetici_k(conn, ornek), "Herkes", "", "okul", None, "2026-10-20")
    # başkasının çocuğu için yanıt / geçersiz yanıt / csrf yok
    assert istemci.post(f"/veli/onay/{t}", data={"csrf": csrf, "ogr": ornek["ogr2"], "yanit": "evet"}).status_code == 404
    assert istemci.post(f"/veli/onay/{t}", data={"csrf": csrf, "ogr": ornek["ogr1"], "yanit": "belki"}, follow_redirects=False).status_code == 303
    assert istemci.post(f"/veli/onay/{t}", data={"ogr": ornek["ogr1"], "yanit": "evet"}).status_code == 400
    assert conn.execute("SELECT count(*) FROM onay_yanit").fetchone()[0] == 0


def test_onay_olusturma_yetkileri(conn, ornek, saat):
    saat["an"] = datetime(2026, 10, 12, 12, 0)
    hoca = conn.execute("SELECT * FROM kullanici WHERE id = ?", (ornek["ogretmen"],)).fetchone()
    assert onay.olustur(conn, hoca, "Kendi sınıfım", "", "sinif", "9-A", "2026-10-20")
    for hedef_tur, hedef in (("sinif", "9-B"), ("okul", None)):  # görevli olmadığı sınıf / tüm okul
        with pytest.raises(onay.OnayHatasi) as e:
            onay.olustur(conn, hoca, "x", "", hedef_tur, hedef, "2026-10-20")
        assert e.value.kod == 404
    with pytest.raises(onay.OnayHatasi):
        onay.olustur(conn, hoca, "Geçmiş", "", "sinif", "9-A", "2026-10-01")
    with pytest.raises(onay.OnayHatasi):
        onay.olustur(conn, hoca, " ", "", "sinif", "9-A", "2026-10-20")


def test_onay_sonuc_yazar_ve_yonetici(istemci, saat, conn, ornek, yeni_kullanici):
    saat["an"] = datetime(2026, 10, 12, 12, 0)
    csrf_v = veli(istemci, conn, ornek)
    hoca = conn.execute("SELECT * FROM kullanici WHERE id = ?", (ornek["ogretmen"],)).fetchone()
    t = onay.olustur(conn, hoca, "Sınıf gezisi", "", "sinif", "9-A", "2026-10-20")
    istemci.post(f"/veli/onay/{t}", data={"csrf": csrf_v, "ogr": ornek["ogr1"], "yanit": "evet"})
    c = istemci
    c.cookies.clear(); c.post("/giris", data={"kullanici_adi": "hoca", "sifre": "hoca-sifre"})
    h = c.get(f"/ogretmen/onay/{t}").text
    assert "Ali Veli" in h and "Onayladı" in h and "Onaylayan: 1" in h
    diger = yeni_kullanici(conn, "ogretmen", "Diğer Hoca", "diger", sifre="diger-sifre")
    assert diger
    c.cookies.clear(); c.post("/giris", data={"kullanici_adi": "diger", "sifre": "diger-sifre"})
    assert c.get(f"/ogretmen/onay/{t}").status_code == 404
    c.cookies.clear(); c.post("/giris", data={"kullanici_adi": "mudur", "sifre": "mudur-sifre"})
    assert c.get(f"/ogretmen/onay/{t}").status_code == 200 and "Sınıf gezisi" in c.get("/ogretmen/onay").text
    c.cookies.clear(); veli(c, conn, ornek)
    assert c.get(f"/ogretmen/onay/{t}").status_code == 404 and c.get("/ogretmen/onay").status_code == 404


def test_onay_formu_ile_olustur_ve_push_sablonu(istemci, saat, conn, ornek, monkeypatch):
    import push

    saat["an"] = datetime(2026, 10, 12, 12, 0)
    cagrilar = []
    monkeypatch.setattr(push, "onay_bildir", lambda *a: cagrilar.append(a))
    istemci.post("/giris", data={"kullanici_adi": "hoca", "sifre": "hoca-sifre"})
    csrf = auth.csrf_token(istemci.cookies.get(auth.COOKIE_ADI))
    r = istemci.post("/ogretmen/onay", data={"csrf": csrf, "baslik": "Müze", "aciklama": "x", "hedef_tur": "sinif", "hedef": "9-A", "son_tarih": "2026-10-20"}, follow_redirects=False)
    assert r.status_code == 303 and cagrilar and cagrilar[0][0:2] == ("sinif", "9-A")
    assert "Onayınızı bekleyen bir belge var." == push.SABLONLAR["onay"][1]  # sabit metin: ad/ders yok
    r = istemci.post("/ogretmen/onay", data={"csrf": csrf, "baslik": "Tüm okul", "hedef_tur": "okul", "son_tarih": "2026-10-20"})
    assert r.status_code == 404


def test_onay_push_alicilari(conn, ornek):
    import push

    conn.execute("INSERT INTO push_abonelik (kullanici_id, uc_nokta, p256dh, auth, olusturma) VALUES (?, 'https://x/1', 'k', 'a', '2026-10-12 00:00:00')", (ornek["veli1"],))
    conn.commit()
    assert push.onay_alicilari(conn, "sinif", "9-A", ornek["ogretmen"]) == [ornek["veli1"]]
    assert push.onay_alicilari(conn, "sinif", "9-B", ornek["ogretmen"]) == []
    assert push.onay_alicilari(conn, "okul", None, ornek["ogretmen"]) == [ornek["veli1"]]


def test_gocu_29_geri_alma():
    import importlib.util
    import pathlib

    import db

    assert len(db.GOCLER) >= 29
    s = importlib.util.spec_from_file_location("geri_al", pathlib.Path("scripts/geri_al.py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    assert "onay_yanit" in m.GERI[29] and "onay_talep" in m.GERI[29]
    assert sqlite3  # noqa: B018
