"""Anket rotaları: yetki (404), CSRF, yönetici akışı, katılımcı akışı, sonuç ekranı gizlilik."""

import anket
import auth
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def istemci():
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def _anket_kur(c, csrf):
    r = c.post("/yonetici/anketler", data={"csrf": csrf, "baslik": "Memnuniyet", "aciklama": "Kısa"}, follow_redirects=False)
    assert r.status_code == 303
    aid = int(r.headers["location"].rsplit("/", 1)[1])
    for veri in (
        {"tur": "olcek", "metin": "Memnuniyet?", "roller": ["ogrenci", "veli", "ogretmen"], "zorunlu": "1"},
        {"tur": "metin", "metin": "Eklemek istediğin", "roller": ["ogrenci", "veli"], "zorunlu": ""},
    ):
        assert c.post(f"/yonetici/anketler/{aid}/soru", data={"csrf": csrf, **veri}, follow_redirects=False).status_code == 303
    return aid


def test_yonetici_akisi(istemci, ornek, conn):
    csrf = giris(istemci, "mudur", "mudur-sifre")
    assert istemci.get("/yonetici/anketler").status_code == 200
    aid = _anket_kur(istemci, csrf)
    d = istemci.get(f"/yonetici/anketler/{aid}")
    assert d.status_code == 200 and "Memnuniyet?" in d.text and "gönder" in d.text
    # geçersiz soru: sayfa 400 ve neden yazılı
    r = istemci.post(f"/yonetici/anketler/{aid}/soru", data={"csrf": csrf, "tur": "tek", "metin": "x", "secenekler": "a", "roller": ["ogrenci"]})
    assert r.status_code == 400 and "2–10" in r.text
    r = istemci.post(f"/yonetici/anketler/{aid}/dagit", data={"csrf": csrf, "rol": "ogrenci", "sinif": "9-A"}, follow_redirects=False)
    assert r.status_code == 303
    assert istemci.post(f"/yonetici/anketler/{aid}/dagit", data={"csrf": csrf, "rol": "ogrenci"}).status_code == 400
    r = istemci.post(f"/yonetici/anketler/{aid}/soru", data={"csrf": csrf, "tur": "metin", "metin": "geç", "roller": ["ogrenci"]})
    assert r.status_code == 400 and "değiştirilemez" in r.text
    assert istemci.get(f"/yonetici/anketler/{aid}/sonuc").status_code == 200
    assert set(anket.hedefler(conn, aid)) == {"ogrenci"}


def test_katilimci_akisi_ve_sonuc_gizli(istemci, ornek, conn):
    csrf = giris(istemci, "mudur", "mudur-sifre")
    aid = _anket_kur(istemci, csrf)
    istemci.post(f"/yonetici/anketler/{aid}/dagit", data={"csrf": csrf, "rol": "ogrenci", "sinif": "9-A"})
    sid = conn.execute("SELECT id FROM anket_soru WHERE anket_id = ? AND sira = 1", (aid,)).fetchone()[0]
    c2 = giris(istemci, "101", "ali-sifre")
    assert "Memnuniyet" in istemci.get("/anket").text
    f = istemci.get(f"/anket/{aid}")
    assert f.status_code == 200 and "anonim" in f.text and f'name="s{sid}"' in f.text
    # zorunlu boş → 400, hiçbir şey yazılmaz
    assert istemci.post(f"/anket/{aid}", data={"csrf": c2}).status_code == 400
    assert conn.execute("SELECT count(*) FROM anket_katilim").fetchone()[0] == 0
    r = istemci.post(f"/anket/{aid}", data={"csrf": c2, f"s{sid}": "4"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/anket?tamam=1"
    assert "teşekkürler" in istemci.get("/anket?tamam=1").text
    # ikinci gönderim: ek yanıt yok
    istemci.post(f"/anket/{aid}", data={"csrf": c2, f"s{sid}": "5"}, follow_redirects=False)
    assert conn.execute("SELECT count(*) FROM anket_yanit").fetchone()[0] == 1
    assert istemci.get(f"/anket/{aid}", follow_redirects=False).status_code == 303
    giris(istemci, "mudur", "mudur-sifre")
    s = istemci.get(f"/yonetici/anketler/{aid}/sonuc").text
    assert "sonuç gizlendi" in s and "1 / " in s and "Ali" not in s


def test_yetkisiz_erisimler_404(istemci, ornek, conn):
    csrf = giris(istemci, "mudur", "mudur-sifre")
    aid = _anket_kur(istemci, csrf)
    istemci.post(f"/yonetici/anketler/{aid}/dagit", data={"csrf": csrf, "rol": "ogrenci", "sinif": "9-A"})
    # öğrenci/öğretmen yönetici ekranlarını göremez
    for kadi, sifre in (("101", "ali-sifre"), ("hoca", "hoca-sifre")):
        c = giris(istemci, kadi, sifre)
        for yol in ("/yonetici/anketler", f"/yonetici/anketler/{aid}", f"/yonetici/anketler/{aid}/sonuc"):
            assert istemci.get(yol).status_code == 404
        assert istemci.post("/yonetici/anketler", data={"csrf": c, "baslik": "x"}).status_code == 404
        assert istemci.post(f"/yonetici/anketler/{aid}/dagit", data={"csrf": c, "rol": "ogretmen"}).status_code == 404
    # kapsam dışı: 9-B öğrencisi, öğretmen (öğrencilere gönderildi), yönetici
    giris(istemci, "201", "ayse-sifre")
    assert istemci.get(f"/anket/{aid}").status_code == 404
    giris(istemci, "hoca", "hoca-sifre")
    assert istemci.get(f"/anket/{aid}").status_code == 404
    giris(istemci, "mudur", "mudur-sifre")
    assert istemci.get("/anket").status_code == 404 and istemci.get(f"/anket/{aid}").status_code == 404
    assert istemci.get("/yonetici/anketler/9999").status_code == 404


def test_csrf_zorunlu(istemci, ornek):
    giris(istemci, "mudur", "mudur-sifre")
    assert istemci.post("/yonetici/anketler", data={"baslik": "x"}).status_code == 400
    csrf = giris(istemci, "mudur", "mudur-sifre")
    aid = _anket_kur(istemci, csrf)
    assert istemci.post(f"/yonetici/anketler/{aid}/dagit", data={"rol": "ogrenci"}).status_code == 400


def test_veli_ve_ogretmen_ayri_gonderim(istemci, ornek, conn):
    csrf = giris(istemci, "mudur", "mudur-sifre")
    aid = _anket_kur(istemci, csrf)
    istemci.post(f"/yonetici/anketler/{aid}/dagit", data={"csrf": csrf, "rol": "ogretmen"})
    giris(istemci, "hoca", "hoca-sifre")
    assert istemci.get(f"/anket/{aid}").status_code == 200
    # veli: telefon+SMS girişi yok; oturumu doğrudan aç
    istemci.cookies.clear()
    istemci.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, ornek["veli1"]))
    assert istemci.get(f"/anket/{aid}").status_code == 404  # veliye gönderilmedi
    csrf = giris(istemci, "mudur", "mudur-sifre")
    assert istemci.post(f"/yonetici/anketler/{aid}/dagit", data={"csrf": csrf, "rol": "veli"}, follow_redirects=False).status_code == 303
    istemci.cookies.clear()
    istemci.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, ornek["veli1"]))
    sayfa = istemci.get(f"/anket/{aid}")
    assert sayfa.status_code == 200 and "Eklemek istediğin" in sayfa.text


def test_kapatilan_anket_404(istemci, ornek, conn):
    csrf = giris(istemci, "mudur", "mudur-sifre")
    aid = _anket_kur(istemci, csrf)
    istemci.post(f"/yonetici/anketler/{aid}/dagit", data={"csrf": csrf, "rol": "ogrenci"})
    istemci.post(f"/yonetici/anketler/{aid}/kapat", data={"csrf": csrf, "rol": "ogrenci"})
    giris(istemci, "101", "ali-sifre")
    assert istemci.get(f"/anket/{aid}").status_code == 404
    assert istemci.get("/anket").status_code == 200


def test_analitik_olayi(istemci, ornek, conn):
    import analitik

    csrf = giris(istemci, "mudur", "mudur-sifre")
    aid = _anket_kur(istemci, csrf)
    istemci.post(f"/yonetici/anketler/{aid}/dagit", data={"csrf": csrf, "rol": "ogrenci"})
    sid = conn.execute("SELECT id FROM anket_soru WHERE anket_id = ? AND sira = 1", (aid,)).fetchone()[0]
    c2 = giris(istemci, "101", "ali-sifre")
    istemci.post(f"/anket/{aid}", data={"csrf": c2, f"s{sid}": "3"})
    analitik.bosalt()
    assert conn.execute("SELECT count(*) FROM olay WHERE tur = 'anket_yanitla'").fetchone()[0] == 1
