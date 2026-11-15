"""Coğrafya giriş kartlarının öğrenci ekranlarında görünürlüğü."""

from fastapi.testclient import TestClient


def test_dokuzuncu_sinif_cografya_kartlari(ornek):
    from app import app

    with TestClient(app) as istemci:
        assert istemci.post("/giris", data={"kullanici_adi": "101", "sifre": "ali-sifre"}, follow_redirects=False).status_code == 303
        for yol in ("/ogrenci", "/ogrenci/arena"):
            yanit = istemci.get(yol)
            assert yanit.status_code == 200
            assert 'href="/ogrenci/cografya"' in yanit.text


def test_on_ikinci_sinif_oyun_kutulari_gizli(conn, yeni_kullanici):
    from app import app

    kid = yeni_kullanici(conn, "ogrenci", "Test Öğrenci", "1201", sifre="test-sifre")
    conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (?, ?, ?, ?)", (1201, "Test Öğrenci", "12-A", kid))
    conn.commit()
    with TestClient(app) as istemci:
        assert istemci.post("/giris", data={"kullanici_adi": "1201", "sifre": "test-sifre"}, follow_redirects=False).status_code == 303
        yanit = istemci.get("/ogrenci")
        assert yanit.status_code == 200
        assert 'class="oyun-kutulari"' not in yanit.text
        assert 'href="/ogrenci/cografya"' not in yanit.text
