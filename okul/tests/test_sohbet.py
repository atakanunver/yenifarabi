"""Sohbet odası: yetki, yalnızca metin, 30 gün saklama, silme yetkileri, okunmamış sayacı, bildirim sıklığı."""

import json
from datetime import timedelta

import auth
import push
import pytest
import sohbet
import zaman
from ayarlar import AYAR
from fastapi.testclient import TestClient

JSON = {"Accept": "application/json"}


def _istemci():
    from app import app

    return TestClient(app)


def _kisi(conn, yeni_kullanici, rol, kadi):
    return yeni_kullanici(conn, rol, kadi.title(), kadi, sifre="Parola123")


def _oturum(c, conn, kid):
    c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, kid))


def _csrf(c):
    return c.get("/sohbet").text.split('data-csrf="')[1].split('"')[0]


def _gonder(c, metin, csrf=None):
    return c.post("/sohbet/gonder", data={"csrf": csrf or _csrf(c), "metin": metin}, headers=JSON)


def _satir_ekle(conn, yazar, metin, gun_once=0):
    t = (zaman.simdi() - timedelta(days=gun_once)).strftime(zaman.BICIM)
    cur = conn.execute("INSERT INTO sohbet_mesaj (yazar_id, metin, olusturma) VALUES (?, ?, ?)", (yazar, metin, t))
    conn.commit()
    return cur.lastrowid


@pytest.mark.parametrize("rol", ["ogrenci", "veli"])
def test_yalniz_ogretmen_ve_yonetici_girer(conn, yeni_kullanici, rol):
    k = _kisi(conn, yeni_kullanici, rol, "x" + rol)
    if rol == "ogrenci":
        conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (5, 'T', '9-A', ?)", (k,))
        conn.commit()
    with _istemci() as c:
        _oturum(c, conn, k)
        assert c.get("/sohbet").status_code == 404
        assert c.get("/sohbet/mesajlar").status_code == 404
        assert c.post("/sohbet/gonder", data={"metin": "x"}).status_code in (400, 404)
    assert conn.execute("SELECT COUNT(*) FROM sohbet_mesaj").fetchone()[0] == 0


def test_girissiz_yonlendirir():
    with _istemci() as c:
        assert c.get("/sohbet", follow_redirects=False).status_code == 303
        assert c.get("/sohbet/mesajlar", follow_redirects=False).status_code == 303


@pytest.mark.parametrize("rol", ["ogretmen", "yonetici"])
def test_uyeler_gorur_ve_uyari_gosterilir(conn, yeni_kullanici, rol):
    k = _kisi(conn, yeni_kullanici, rol, "u" + rol)
    with _istemci() as c:
        _oturum(c, conn, k)
        r = c.get("/sohbet")
    assert r.status_code == 200
    assert "yöneticiler de tüm mesajları görebilir" in r.text and "30 gün sonra silinir" in r.text


def test_gonder_ve_karsi_taraf_gorur(conn, yeni_kullanici):
    a = _kisi(conn, yeni_kullanici, "ogretmen", "ogta")
    y = _kisi(conn, yeni_kullanici, "yonetici", "yon")
    with _istemci() as ca, _istemci() as cy:
        _oturum(ca, conn, a)
        _oturum(cy, conn, y)
        assert _gonder(ca, "Merhaba ortak oda").status_code == 200
        liste = cy.get("/sohbet/mesajlar?sonra=0").json()["mesajlar"]
        assert [m["metin"] for m in liste] == ["Merhaba ortak oda"]
        assert liste[0]["yazar"] == "Ogta" and liste[0]["benim"] is False and liste[0]["silinebilir"] is True  # yönetici siler
        assert "Merhaba ortak oda" in cy.get("/sohbet").text
        assert cy.get(f"/sohbet/mesajlar?sonra={liste[0]['id']}").json()["mesajlar"] == []


def test_csrf_zorunlu(conn, yeni_kullanici):
    a = _kisi(conn, yeni_kullanici, "ogretmen", "ogta")
    with _istemci() as c:
        _oturum(c, conn, a)
        assert c.post("/sohbet/gonder", data={"metin": "x"}, headers=JSON).status_code == 400
        assert c.post("/sohbet/1/sil", data={}, headers=JSON).status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM sohbet_mesaj").fetchone()[0] == 0


def test_html_kacislanir_xss_yok(conn, yeni_kullanici):
    a = _kisi(conn, yeni_kullanici, "ogretmen", "ogta")
    with _istemci() as c:
        _oturum(c, conn, a)
        assert _gonder(c, "<script>alert(1)</script>").status_code == 200
        h = c.get("/sohbet").text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in h and "<script>alert(1)" not in h


def test_bos_ve_cok_uzun_reddedilir(conn, yeni_kullanici):
    a = _kisi(conn, yeni_kullanici, "ogretmen", "ogta")
    with _istemci() as c:
        _oturum(c, conn, a)
        csrf = _csrf(c)
        assert _gonder(c, "   \n  ", csrf).status_code == 400
        r = _gonder(c, "a" * (sohbet.AZAMI_METIN + 1), csrf)
        assert r.status_code == 400 and "hata" in r.json()
        assert _gonder(c, "a" * sohbet.AZAMI_METIN, csrf).status_code == 200


def test_metin_duzenleme_kontrol_karakter_ve_bos_satir():
    assert sohbet.metin_duzenle("  a\x00b\r\n\n\n\n\nc \x07") == "ab\n\nc"


def test_hiz_siniri(conn, yeni_kullanici):
    a = _kisi(conn, yeni_kullanici, "ogretmen", "ogta")
    for i in range(sohbet.DAKIKA_AZAMI):
        sohbet.mesaj_ekle(conn, a, f"m{i}")
    with pytest.raises(sohbet.SohbetHatasi) as e:
        sohbet.mesaj_ekle(conn, a, "fazla")
    assert e.value.kod == 429
    b = _kisi(conn, yeni_kullanici, "ogretmen", "ogtb")
    sohbet.mesaj_ekle(conn, b, "başkası serbest")


def test_otuz_gunden_eski_gorunmez_ve_temizlenir(conn, yeni_kullanici):
    a = _kisi(conn, yeni_kullanici, "ogretmen", "ogta")
    _satir_ekle(conn, a, "çok eski", gun_once=sohbet.SAKLAMA_GUN + 1)
    _satir_ekle(conn, a, "sınırda yeni", gun_once=sohbet.SAKLAMA_GUN - 1)
    k = conn.execute("SELECT * FROM kullanici WHERE id = ?", (a,)).fetchone()
    assert [m["metin"] for m in sohbet.mesajlar(conn, k)] == ["sınırda yeni"]  # silinmeden de görünmez
    assert conn.execute("SELECT COUNT(*) FROM sohbet_mesaj").fetchone()[0] == 2
    assert sohbet.temizle(conn) == 1
    assert conn.execute("SELECT metin FROM sohbet_mesaj").fetchall()[0][0] == "sınırda yeni"


def test_silme_yetkileri(conn, yeni_kullanici):
    a = _kisi(conn, yeni_kullanici, "ogretmen", "ogta")
    b = _kisi(conn, yeni_kullanici, "ogretmen", "ogtb")
    y = _kisi(conn, yeni_kullanici, "yonetici", "yon")
    m1 = _satir_ekle(conn, a, "a'nın")
    m2 = _satir_ekle(conn, a, "a'nın ikinci")
    with _istemci() as cb, _istemci() as ca, _istemci() as cy:
        _oturum(cb, conn, b)
        _oturum(ca, conn, a)
        _oturum(cy, conn, y)
        csrf_b = _csrf(cb)
        assert cb.post(f"/sohbet/{m1}/sil", data={"csrf": csrf_b}, headers=JSON).status_code == 404  # başkasının
        assert cb.post("/sohbet/9999/sil", data={"csrf": csrf_b}, headers=JSON).status_code == 404
        assert ca.post(f"/sohbet/{m1}/sil", data={"csrf": _csrf(ca)}, headers=JSON).status_code == 200  # kendi
        assert cy.post(f"/sohbet/{m2}/sil", data={"csrf": _csrf(cy)}, headers=JSON).status_code == 200  # yönetici
    assert conn.execute("SELECT COUNT(*) FROM sohbet_mesaj").fetchone()[0] == 0


def test_okunmamis_sayaci_ve_ana_sayfa_karti(conn, yeni_kullanici):
    a = _kisi(conn, yeni_kullanici, "ogretmen", "ogta")
    y = _kisi(conn, yeni_kullanici, "yonetici", "yon")
    _satir_ekle(conn, a, "bir")
    _satir_ekle(conn, a, "iki")
    assert sohbet.okunmamis_sayisi(conn, y) == 2
    assert sohbet.okunmamis_sayisi(conn, a) == 0  # kendi mesajı okunmamış sayılmaz
    with _istemci() as c:
        _oturum(c, conn, y)
        h = c.get("/yonetici").text
        assert 'href="/sohbet"' in h and "2 yeni" in h
        c.get("/sohbet")
        assert "2 yeni" not in c.get("/yonetici").text


def test_sohbet_karti_yalniz_uyelerin_ana_sayfasinda(conn, yeni_kullanici):
    y = _kisi(conn, yeni_kullanici, "yonetici", "yon")
    with _istemci() as c:
        _oturum(c, conn, y)
        assert 'class="kart sohbet-kart"' in c.get("/yonetici").text
        assert 'class="kart sohbet-kart"' not in c.get("/duyurular").text


# --- bildirim ---

@pytest.fixture
def etkin(monkeypatch):
    monkeypatch.setattr(AYAR, "vapid_ozel", "ozel")
    monkeypatch.setattr(AYAR, "vapid_acik", "acik")
    monkeypatch.setattr(AYAR, "vapid_konu", "mailto:a@b.c")


def test_bildirim_alicilari_yazar_haric_ve_aralikli(conn, yeni_kullanici):
    a = _kisi(conn, yeni_kullanici, "ogretmen", "ogta")
    b = _kisi(conn, yeni_kullanici, "ogretmen", "ogtb")
    y = _kisi(conn, yeni_kullanici, "yonetici", "yon")
    ogr = _kisi(conn, yeni_kullanici, "ogrenci", "ogr")
    for i, kid in enumerate((a, b, y, ogr)):
        push.abone_ol(conn, kid, f"https://x.example/{i}", "p", "a")
    ilk = set(sohbet.bildirim_alicilari(conn, a))
    assert ilk == {b, y}  # yazar ve öğrenci yok
    assert sohbet.bildirim_alicilari(conn, a) == []  # 10 dk içinde tekrar yok
    eski = (zaman.simdi() - timedelta(minutes=sohbet.PUSH_ARALIK_DK + 1)).strftime(zaman.BICIM)
    conn.execute("UPDATE sohbet_okuma SET son_push = ? WHERE kullanici_id = ?", (eski, b))
    conn.commit()
    assert sohbet.bildirim_alicilari(conn, a) == [b]


def test_mesaj_gonderince_sabit_metinli_bildirim_gider(conn, yeni_kullanici, etkin, monkeypatch):
    a = _kisi(conn, yeni_kullanici, "ogretmen", "ogta")
    y = _kisi(conn, yeni_kullanici, "yonetici", "yon")
    push.abone_ol(conn, a, "https://x.example/a", "p", "a")
    push.abone_ol(conn, y, "https://x.example/y", "p", "a")
    alinan = []
    monkeypatch.setattr(push, "_webpush_gonder", lambda ab, veri: alinan.append((ab["endpoint"], json.loads(veri))))
    with _istemci() as c:
        _oturum(c, conn, a)
        assert _gonder(c, "GİZLİ ÖZEL METİN").status_code == 200
    assert [e for e, _ in alinan] == ["https://x.example/y"]
    assert alinan[0][1] == {"baslik": "Dijital Okul", "govde": "Yeni bir sohbet mesajı var.", "url": "/sohbet"}
    assert "GİZLİ" not in json.dumps(alinan)


def test_gocu_ve_geri_alma():
    import db
    from scripts import geri_al

    assert len(db.GOCLER) >= 12 and "sohbet_mesaj" in db.GOCLER[11] and "sohbet_okuma" in db.GOCLER[11]
    assert "sohbet_mesaj" in geri_al.GERI[12]
