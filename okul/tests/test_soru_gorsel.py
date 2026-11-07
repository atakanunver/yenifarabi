"""Görseller yalnız ilgili öğrenciye gösterilir; cevabı istemciye taşımaz."""
import auth
from fastapi.testclient import TestClient
from app import app
from rotalar import soru_gorsel


def test_maraton_gorseli_sahiplik_ve_gosterim(conn, ornek, monkeypatch):
    kid, diger = ornek['ogr1_k'], ornek['ogr2_k']
    mid = conn.execute("INSERT INTO maraton(kullanici_id,sinif,duzey,ders,basla) VALUES(?, '9-A', 9, 'fizik', '2026-11-07 08:00:00')", (kid,)).lastrowid
    conn.execute("INSERT INTO maraton_soru(maraton_id,sira,soru_id,soru,secenekler,dogru_index,gosterim) VALUES (?,1,100,'Soru','[\"A\",\"B\"]',1,'2026-11-07 08:00:00')", (mid,))
    conn.execute("INSERT INTO maraton_soru(maraton_id,sira,soru_id,soru,secenekler,dogru_index) VALUES (?,2,101,'Gelecek','[\"A\",\"B\"]',0)", (mid,))
    conn.commit()
    monkeypatch.setattr(soru_gorsel, '_gorsel', lambda n: (b'png-ornek', 'image/png'))
    with TestClient(app) as c:
        assert c.get('/soru-gorsel/100', follow_redirects=False).status_code == 303
        c.cookies.clear()
        c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, diger))
        assert c.get('/soru-gorsel/100').status_code == 404
        c.cookies.clear()
        c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, kid))
        assert c.get('/soru-gorsel/101').status_code == 404
        r = c.get('/soru-gorsel/100')
        assert r.status_code == 200 and r.content == b'png-ornek'
        assert r.headers['content-type'].startswith('image/png')


def test_olmayan_gorsel_404(conn, ornek, monkeypatch):
    kid=ornek['ogr1_k']
    conn.execute("INSERT INTO calisma_soru(kullanici_id,kaynak,soru_id,soru,secenekler,dogru_index,gosterim) VALUES (?, 'serbest', 201, 'S', '[\"A\",\"B\"]', 1, '2026-11-07 08:00:00')", (kid,))
    conn.commit()
    monkeypatch.setattr(soru_gorsel, '_gorsel', lambda n: None)
    with TestClient(app) as c:
        c.cookies.clear()
        c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, kid))
        assert c.get('/soru-gorsel/201').status_code == 404
