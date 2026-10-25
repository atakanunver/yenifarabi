"""Teşekkür Kartı: yetki (yalnız kendi sınıfı, 404), günde 1 kart/öğrenci, XP sınırı, yarışa sayılmama, öğrenci+veli görünümü, push."""

import auth
import oduller
import push
import pytest
import tesekkur
from fastapi.testclient import TestClient


def _istemci():
    from app import app

    return TestClient(app)


def _oturum(c, conn, kid):
    c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, kid))


def _csrf(c, yol="/ogretmen/tesekkur"):
    return c.get(yol).text.split('name="csrf" value="')[1].split('"')[0]


def _ogretmen(conn, ornek):
    return conn.execute("SELECT * FROM kullanici WHERE id = ?", (ornek["ogretmen"],)).fetchone()


def _xp(conn, kid):
    return conn.execute("SELECT COALESCE(SUM(miktar), 0) FROM bilgi_xp WHERE kullanici_id = ? AND kaynak = 'tesekkur'", (kid,)).fetchone()[0]


def test_kendi_sinifina_gonderir_baska_sinifa_404(conn, ornek, saat):
    h = _ogretmen(conn, ornek)
    assert tesekkur.gonder(conn, h, [ornek["ogr1"]], "gayret") == [ornek["ogr1"]]
    with pytest.raises(tesekkur.TesekkurHatasi) as e:
        tesekkur.gonder(conn, h, [ornek["ogr1"], ornek["ogr2"]], "gayret")  # ogr2 9-B: yetkisiz
    assert e.value.kod == 404
    with pytest.raises(tesekkur.TesekkurHatasi):
        tesekkur.gonder(conn, h, [ornek["ogr1"]], "serbest metin")
    assert conn.execute("SELECT COUNT(*) FROM tesekkur").fetchone()[0] == 1


def test_gunde_bir_kart_ve_xp_siniri(conn, ornek, yeni_kullanici, saat):
    h = _ogretmen(conn, ornek)
    kid = ornek["ogr1_k"]
    assert tesekkur.gonder(conn, h, [ornek["ogr1"]], "gayret") == [ornek["ogr1"]]
    assert tesekkur.gonder(conn, h, [ornek["ogr1"]], "yardim") == []  # aynı öğretmen aynı gün tekrar yazamaz
    hocalar = []
    for i in range(4):
        hid = yeni_kullanici(conn, "ogretmen", f"Hoca {i}", f"hoca{i}")
        conn.execute("INSERT INTO ogretmen_gorev (ogretmen_id, sinif, ders) VALUES (?, '9-A', 'tarih')", (hid,))
        conn.commit()
        hocalar.append(conn.execute("SELECT * FROM kullanici WHERE id = ?", (hid,)).fetchone())
    for hh in hocalar:
        tesekkur.gonder(conn, hh, [ornek["ogr1"]], "katilim")
    assert conn.execute("SELECT COUNT(*) FROM tesekkur WHERE ogrenci_id = ?", (ornek["ogr1"],)).fetchone()[0] == 5
    assert _xp(conn, kid) == tesekkur.GUNLUK_XP  # 5 kart ama günlük sınır
    saat["an"] = saat["an"].replace(day=13)
    assert tesekkur.gonder(conn, h, [ornek["ogr1"]], "gayret") == [ornek["ogr1"]]
    assert _xp(conn, kid) == tesekkur.GUNLUK_XP + tesekkur.KART_XP


def test_xp_avatara_sayilir_yarisa_sayilmaz(conn, ornek, saat):
    import arena

    tesekkur.gonder(conn, _ogretmen(conn, ornek), [ornek["ogr1"]], "gayret")
    assert arena.toplam_xp(conn, ornek["ogr1_k"]) == tesekkur.KART_XP
    assert oduller.liderlik(conn, oduller.hafta_basi(), ornek["ogr1_k"])["xp"]["ben"] is None
    assert oduller.liderlik(conn, None, ornek["ogr1_k"])["xp"]["ben"] is None


def test_12_sinif_kart_alir_xp_almaz(conn, ornek, saat):
    conn.execute("UPDATE ogrenci SET sinif = '12-A' WHERE id = ?", (ornek["ogr1"],))
    conn.execute("INSERT INTO ogretmen_gorev (ogretmen_id, sinif, ders) VALUES (?, '12-A', 'matematik')", (ornek["ogretmen"],))
    conn.commit()
    assert tesekkur.gonder(conn, _ogretmen(conn, ornek), [ornek["ogr1"]], "gayret") == [ornek["ogr1"]]
    assert _xp(conn, ornek["ogr1_k"]) == 0


def test_ogretmen_formu_ve_gonderim(conn, ornek, saat, monkeypatch):
    bildirilen = []
    monkeypatch.setattr(push, "tesekkur_bildir", lambda idler: bildirilen.append(idler))
    with _istemci() as c:
        _oturum(c, conn, ornek["ogretmen"])
        s = c.get("/ogretmen/tesekkur").text
        assert "Ali Veli" in s and "Ayşe Kaya" not in s
        assert c.get("/ogretmen/tesekkur?sinif=9-B").status_code == 404
        csrf = _csrf(c)
        r = c.post("/ogretmen/tesekkur", data={"csrf": csrf, "sinif": "9-A", "sablon": "yardim", "ogrenci": [str(ornek["ogr1"])]},
                   follow_redirects=False)
        assert r.status_code == 303 and "gonderildi=1" in r.headers["location"]
        assert c.post("/ogretmen/tesekkur", data={"csrf": csrf, "sinif": "9-A", "sablon": "yardim", "ogrenci": [str(ornek["ogr2"])]}).status_code == 404
        assert c.post("/ogretmen/tesekkur", data={"csrf": csrf, "sinif": "9-A", "sablon": "yardim"}).status_code == 400
        assert c.post("/ogretmen/tesekkur", data={"csrf": "yanlis", "sinif": "9-A", "sablon": "yardim", "ogrenci": [str(ornek["ogr1"])]}).status_code == 400
        assert "bugün aldı" in c.get("/ogretmen/tesekkur").text
    assert bildirilen == [[ornek["ogr1"]]]


def test_ogrenci_ve_veli_gorur_baskasi_goremez(conn, ornek, saat):
    tesekkur.gonder(conn, _ogretmen(conn, ornek), [ornek["ogr1"]], "yardim")
    metin = tesekkur.SABLONLAR["yardim"][1]
    with _istemci() as c:
        _oturum(c, conn, ornek["ogr1_k"])
        assert metin in c.get("/ogrenci").text and metin in c.get("/tesekkurler").text
    with _istemci() as c:
        _oturum(c, conn, ornek["veli1"])
        assert metin in c.get("/veli").text and metin in c.get(f"/tesekkurler?ogr={ornek['ogr1']}").text
        assert c.get(f"/tesekkurler?ogr={ornek['ogr2']}").status_code == 404
    assert conn.execute("SELECT COUNT(*) FROM erisim_log WHERE eylem = 'tesekkurler'").fetchone()[0] == 1
    with _istemci() as c:
        _oturum(c, conn, ornek["ogr2_k"])
        assert metin not in c.get("/tesekkurler").text
    for rol in ("ogretmen", "yonetici"):
        with _istemci() as c:
            _oturum(c, conn, ornek[rol])
            assert c.get("/tesekkurler").status_code == 404
    with _istemci() as c:
        _oturum(c, conn, ornek["yonetici"])
        assert c.get("/ogretmen/tesekkur").status_code == 404  # yalnızca öğretmen gönderir


def test_push_alicilari_ve_sabit_metin(conn, ornek):
    for kid in (ornek["ogr1_k"], ornek["veli1"], ornek["ogr2_k"]):
        push.abone_ol(conn, kid, f"https://push.example/{kid}", "p", "a")
    assert push.tesekkur_alicilari(conn, [ornek["ogr1"]], veli=False) == [ornek["ogr1_k"]]
    assert push.tesekkur_alicilari(conn, [ornek["ogr1"]], veli=True) == [ornek["veli1"]]
    for anahtar in ("tesekkur", "tesekkur_veli"):
        assert "Ali" not in push.SABLONLAR[anahtar][1] and push.SABLONLAR[anahtar][2] == "/tesekkurler"
