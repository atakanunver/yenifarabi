"""Kütüphane rotaları: rol yetkisi (sunucu tarafı, yetkisiz = 404), CSRF, ver/al JSON akışı, Kütüphanem, veli, Excel."""

import io

import auth
import kutuphane
import openpyxl
import pytest
from fastapi.testclient import TestClient
from test_web import istemci  # noqa: F401  (dış kaynak taklitleri)

ORNEK = {"isbn": "9786052793978", "demirbas": "03244", "baski_yili": "2025", "baslik": "Bahadır : Sirius’un seçimi",
         "basim_sayisi": "3.Basim", "yayinevi": "Can Yayınları"}


@pytest.fixture
def c():
    from app import app

    return TestClient(app)


def _oturum(c, conn, kid) -> str:
    token = auth.oturum_ac(conn, kid)
    c.cookies.clear()
    c.cookies.set(auth.COOKIE_ADI, token)
    return auth.csrf_token(token)


def test_yetkisiz_404_yetkili_ogretmen_erisir(c, conn, ornek):
    yollar = ["/kutuphane/ver", "/kutuphane/al", "/kutuphane/ekle", "/kutuphane/oduncte", "/kutuphane/rapor",
              "/kutuphane/rapor.xlsx", "/kutuphane/ice-aktar", "/kutuphane/etiket", "/kutuphane/api/kod?kod=1",
              "/kutuphane/api/ogrenci?q=a"]
    _oturum(c, conn, ornek["ogretmen"])  # yetkisiz öğretmen: yalnızca katalog
    assert all(c.get(y).status_code == 404 for y in yollar)
    assert c.get("/kutuphane/katalog").status_code == 200
    assert c.get("/kutuphane", follow_redirects=False).headers["location"] == "/kutuphane/katalog"
    _oturum(c, conn, ornek["ogr1_k"])
    assert all(c.get(y).status_code == 404 for y in yollar)
    assert c.get("/kutuphane/ayarlar").status_code == 404
    conn.execute("INSERT INTO kutuphane_yetkili (kullanici_id, olusturma) VALUES (?, '2026-11-06 10:00:00')", (ornek["ogretmen"],))
    conn.commit()
    _oturum(c, conn, ornek["ogretmen"])
    assert all(c.get(y).status_code == 200 for y in yollar)
    assert c.get("/kutuphane/ayarlar").status_code == 404  # ayarlar yalnızca yönetici
    _oturum(c, conn, ornek["veli1"])
    assert c.get("/kutuphane/katalog").status_code == 404 and c.get("/kutuphane/ver").status_code == 404


def test_kamera_akisi_ver_al_json(c, conn, ornek, saat):
    kutuphane.nusha_ekle(conn, **ORNEK)
    kutuphane.nusha_ekle(conn, **{**ORNEK, "demirbas": "03245"})
    csrf = _oturum(c, conn, ornek["yonetici"])
    v = c.get("/kutuphane/api/kod", params={"kod": "9786052793978"}).json()
    assert [n["demirbas"] for n in v["isbn"]] == ["03244", "03245"] and v["demirbas"] == []
    nid = v["isbn"][0]["id"]
    o = c.get("/kutuphane/api/ogrenci", params={"q": "ali"}).json()
    assert o["limit"] == 2 and [x["okul_no"] for x in o["ogrenciler"]] == [101]
    assert c.post("/kutuphane/ver", data={"nusha_id": nid, "ogrenci_id": ornek["ogr1"]}).status_code == 400  # CSRF yok
    r = c.post("/kutuphane/ver", data={"csrf": csrf, "nusha_id": nid, "ogrenci_id": ornek["ogr1"]})
    assert r.status_code == 200 and r.json()["kayit"]["son_tarih"] == "2026-10-26"
    r = c.post("/kutuphane/ver", data={"csrf": csrf, "nusha_id": nid, "ogrenci_id": ornek["ogr2"]})  # çift okutma
    assert r.status_code == 409 and r.json()["mesaj"] == "Bu nüsha zaten ödünçte."
    assert "Ali Veli" in c.get("/kutuphane/oduncte").text
    r = c.post("/kutuphane/al", data={"csrf": csrf, "nusha_id": nid})
    assert r.status_code == 200 and r.json()["kayit"]["iade"]
    assert c.post("/kutuphane/al", data={"csrf": csrf, "nusha_id": nid}).status_code == 409
    assert conn.execute("SELECT COUNT(*) FROM erisim_log WHERE eylem = 'kutuphane_oduncte'").fetchone()[0] == 1


def test_kitap_ekle_formu_ve_sifir(c, conn, ornek):
    csrf = _oturum(c, conn, ornek["yonetici"])
    r = c.post("/kutuphane/ekle", data={"csrf": csrf, **ORNEK}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/kutuphane/ekle?eklendi=03244"
    assert "03244" in c.get(r.headers["location"]).text
    r = c.post("/kutuphane/ekle", data={"csrf": csrf, **ORNEK})
    assert r.status_code == 409 and "zaten kayıtlı" in r.text and "Sirius" in r.text  # form değerleri korunur
    assert c.get("/kutuphane/api/isbn", params={"isbn": "978-605-279-397-8"}).json()["kitap"]["yayinevi"] == "Can Yayınları"


def test_ogrenci_katalog_ayirt_kutuphanem(c, conn, ornek, saat):
    nid = kutuphane.nusha_ekle(conn, **ORNEK)
    kitap_id = kutuphane.demirbas_bul(conn, "03244")["kitap_id"]
    kutuphane.odunc_ver(conn, nid, ornek["ogr2"], ornek["yonetici"])
    csrf = _oturum(c, conn, ornek["ogr1_k"])
    t = c.get("/kutuphane/katalog", params={"q": "sirius"}).text
    assert "Bahadır" in t and "Ödünçte" in t
    t = c.get(f"/kutuphane/kitap/{kitap_id}").text
    assert "Ayşe Kaya" not in t and "Ayırt" in t  # öğrenci kimin aldığını görmez
    assert c.post(f"/kutuphane/ayirt/{kitap_id}", data={"csrf": csrf}, follow_redirects=False).status_code == 303
    r = c.post(f"/kutuphane/ayirt/{kitap_id}", data={"csrf": csrf}, follow_redirects=False)
    assert r.headers["location"].endswith("?hata=zaten")
    assert "Bu kitabı zaten ayırttın." in c.get(r.headers["location"]).text
    assert "Bu kitabı zaten" not in c.get(f"/kutuphane/kitap/{kitap_id}?hata=<script>").text  # URL metni yansımaz
    assert "Sırada 1." in c.get("/kutuphane/benim").text
    kutuphane.iade_al(conn, nid, ornek["yonetici"])
    assert "için ayrıldı" in c.get("/kutuphane/benim").text


def test_ayirtma_iptal_baskasinin_404(c, conn, ornek, saat):
    nid = kutuphane.nusha_ekle(conn, **ORNEK)
    kitap_id = kutuphane.demirbas_bul(conn, "03244")["kitap_id"]
    kutuphane.odunc_ver(conn, nid, ornek["ogr2"], ornek["yonetici"])
    aid = kutuphane.ayirt(conn, kitap_id, ornek["ogr1"])
    csrf = _oturum(c, conn, ornek["ogr2_k"])
    assert c.post(f"/kutuphane/ayirtma/{aid}/iptal", data={"csrf": csrf}).status_code == 404
    csrf = _oturum(c, conn, ornek["ogr1_k"])
    assert c.post(f"/kutuphane/ayirtma/{aid}/iptal", data={"csrf": csrf}, follow_redirects=False).status_code == 303
    assert kutuphane.ayirtmalar(conn, ornek["ogr1"]) == []


def test_veli_yalnizca_kendi_cocugu(c, conn, ornek, saat):
    nid = kutuphane.nusha_ekle(conn, **ORNEK)
    kutuphane.odunc_ver(conn, nid, ornek["ogr1"], ornek["yonetici"])
    _oturum(c, conn, ornek["veli1"])
    assert "Bahadır" in c.get("/kutuphane/benim").text
    assert c.get(f"/kutuphane/benim?ogr={ornek['ogr2']}").status_code == 404
    assert conn.execute("SELECT ogrenci_id FROM erisim_log WHERE eylem = 'kutuphane'").fetchone()[0] == ornek["ogr1"]


def test_ogrenci_ana_ekraninda_kutuphanem_ve_hatirlatma(istemci, conn, ornek, saat):  # noqa: F811
    from datetime import timedelta

    nid = kutuphane.nusha_ekle(conn, **ORNEK)
    kutuphane.odunc_ver(conn, nid, ornek["ogr1"], ornek["yonetici"])
    _oturum(istemci, conn, ornek["ogr1_k"])
    t = istemci.get("/ogrenci").text
    assert "Kütüphanem" in t and "Bahadır" in t and "Teslime" not in t
    saat["an"] += timedelta(days=12)
    assert "Teslime 2 gün kaldı" in istemci.get("/ogrenci").text
    saat["an"] += timedelta(days=3)
    assert "1 gün gecikti" in istemci.get("/ogrenci").text


def test_ayarlar_yonetici(c, conn, ornek):
    csrf = _oturum(c, conn, ornek["yonetici"])
    r = c.post("/kutuphane/ayarlar", data={"csrf": csrf, "odunc_gun": "21", "ogrenci_limit": "3", "yetkili": [str(ornek["ogretmen"]), "99999", "x"]},
               follow_redirects=False)
    assert r.status_code == 303
    assert kutuphane.ayarlar(conn) == {"odunc_gun": 21, "ogrenci_limit": 3, "hatirlatma": 0}
    assert [o["id"] for o in kutuphane.ogretmenler(conn) if o["yetkili"]] == [ornek["ogretmen"]]
    assert c.post("/kutuphane/ayarlar", data={"csrf": csrf, "odunc_gun": "500", "ogrenci_limit": "2"}).status_code == 400


def test_excel_yukle_indir_ve_etiket(c, conn, ornek, saat):
    csrf = _oturum(c, conn, ornek["yonetici"])
    sablon = c.get("/kutuphane/sablon.xlsx")
    assert sablon.status_code == 200 and sablon.headers["content-type"].startswith("application/vnd.openxmlformats")
    r = c.post("/kutuphane/ice-aktar", data={"csrf": csrf}, files={"dosya": ("k.xlsx", sablon.content)})
    assert r.status_code == 200 and "<b>1</b> nüsha eklendi" in r.text
    assert kutuphane.demirbas_bul(conn, "03244")["baslik"] == "Bahadır : Sirius’un seçimi"
    assert c.post("/kutuphane/ice-aktar", data={"csrf": csrf}, files={"dosya": ("k.xlsx", b"x")}).status_code == 400
    wb = openpyxl.load_workbook(io.BytesIO(c.get("/kutuphane/rapor.xlsx").content))
    assert wb["Nüshalar"]["A2"].value == "03244"
    t = c.get("/kutuphane/etiket", params={"bas": "03244"}).text
    assert 'data-kod="KTP-03244"' in t
    kutuphane.nusha_ekle(conn, demirbas="03244-2", baslik="B")
    assert 'data-kod="KTP-03244-2"' in c.get("/kutuphane/etiket", params={"ek": 1}).text
    assert "okunduğunu göstermez" in c.get("/kutuphane/rapor").text


def test_ana_sayfa_suresi_dolan_ayirtma_temizligiyle_bozulmaz(istemci, conn, ornek, saat):  # noqa: F811
    """Başka öğrencinin 'hazır' ayırtmasının süresi dolmuşken /ogrenci açılır: temizlik yapılır, sayfa 200."""
    from datetime import timedelta

    nid = kutuphane.nusha_ekle(conn, **ORNEK)
    kitap_id = kutuphane.demirbas_bul(conn, "03244")["kitap_id"]
    kutuphane.odunc_ver(conn, nid, ornek["ogr1"], ornek["yonetici"])
    kutuphane.ayirt(conn, kitap_id, ornek["ogr2"])
    kutuphane.iade_al(conn, nid, ornek["yonetici"])  # ogr2 için hazır
    saat["an"] += timedelta(days=kutuphane.HAZIR_GUN, hours=1)
    _oturum(istemci, conn, ornek["ogr1_k"])
    assert istemci.get("/ogrenci").status_code == 200
    assert conn.execute("SELECT durum FROM ayirtma").fetchone()[0] == "doldu"


def test_temizlik_acik_islem_icinde_atlanir(conn, ornek, saat):
    from datetime import timedelta

    nid = kutuphane.nusha_ekle(conn, **ORNEK)
    kitap_id = kutuphane.demirbas_bul(conn, "03244")["kitap_id"]
    kutuphane.odunc_ver(conn, nid, ornek["ogr1"], ornek["yonetici"])
    kutuphane.ayirt(conn, kitap_id, ornek["ogr2"])
    kutuphane.iade_al(conn, nid, ornek["yonetici"])
    saat["an"] += timedelta(days=kutuphane.HAZIR_GUN, hours=1)
    conn.execute("UPDATE kullanici SET ad_soyad = ad_soyad WHERE id = ?", (ornek["ogr1_k"],))  # commit edilmemiş yazma
    assert conn.in_transaction
    kutuphane.kutuphanem(conn, ornek["ogr1"])  # hata vermez
    conn.commit()
    kutuphane.ayirtma_temizle(conn)
    assert conn.execute("SELECT durum FROM ayirtma").fetchone()[0] == "doldu"
