"""Uçtan uca: vesikalık, yıllık plan, sınav takvimi — yetki matrisi (404), doğrulama, görünürlük."""

import auth
import pytest
from fastapi.testclient import TestClient
from kaynaklar import kazanim

JPG = b"\xff\xd8\xff\xe0" + b"0" * 200
PDF = b"%PDF-1.7\n" + b"0" * 200


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setattr(kazanim, "form_sonuclari", lambda okul_no: [])
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert (
        c.post(
            "/giris",
            data={"kullanici_adi": kadi, "sifre": sifre},
            follow_redirects=False,
        ).status_code
        == 303
    )
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def veli_giris(c, conn, veli_id):
    c.cookies.clear()
    token = auth.oturum_ac(conn, veli_id)
    c.cookies.set(auth.COOKIE_ADI, token)
    return auth.csrf_token(token)


# --- vesikalık ---


def test_foto_yukleme_ve_gorunurluk(istemci, ornek, conn, yeni_kullanici):
    csrf = giris(istemci, "101", "ali-sifre")
    assert istemci.get("/profil").status_code == 200
    assert (
        istemci.post(
            "/profil/foto", files={"foto": ("a.jpg", JPG, "image/jpeg")}
        ).status_code
        == 400
    )  # csrf yok
    r = istemci.post(
        "/profil/foto",
        data={"csrf": csrf},
        files={"foto": ("a.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 422 and "JPG, PNG ya da WEBP" in r.text
    assert (
        istemci.post(
            "/profil/foto",
            data={"csrf": csrf},
            files={"foto": ("a.jpg", JPG, "image/jpeg")},
            follow_redirects=False,
        ).status_code
        == 303
    )
    kid = ornek["ogr1_k"]
    r = istemci.get(f"/foto/{kid}")
    assert (
        r.status_code == 200
        and r.content == JPG
        and r.headers["content-type"] == "image/jpeg"
    )
    assert "private" in r.headers["cache-control"]

    giris(istemci, "201", "ayse-sifre")  # başka sınıftan öğrenci
    assert istemci.get(f"/foto/{kid}").status_code == 404
    giris(istemci, "hoca", "hoca-sifre")  # 9-A'ya giriyor
    assert istemci.get(f"/foto/{kid}").status_code == 200
    assert "/foto/" in istemci.get("/ogretmen/sinif/9-A").text
    diger = yeni_kullanici(conn, "ogretmen", "Diğer", "diger", sifre="diger-sifre")
    giris(istemci, "diger", "diger-sifre")  # 9-A'ya girmiyor
    assert istemci.get(f"/foto/{kid}").status_code == 404
    veli_giris(istemci, conn, ornek["veli1"])
    assert istemci.get(f"/foto/{kid}").status_code == 200
    assert f"/foto/{kid}" in istemci.get("/veli").text
    assert istemci.get("/profil").status_code == 404  # velide profil/fotoğraf yok
    giris(istemci, "mudur", "mudur-sifre")
    assert istemci.get(f"/foto/{kid}").status_code == 200
    assert istemci.get(f"/foto/{diger}").status_code == 404  # fotoğrafı yok


def test_ogretmen_fotosunu_ogrenci_goremez(istemci, ornek):
    csrf = giris(istemci, "hoca", "hoca-sifre")
    istemci.post(
        "/profil/foto",
        data={"csrf": csrf},
        files={"foto": ("a.jpg", JPG, "image/jpeg")},
    )
    giris(istemci, "101", "ali-sifre")
    assert istemci.get(f"/foto/{ornek['ogretmen']}").status_code == 404


def test_foto_kaldirma(istemci, ornek):
    csrf = giris(istemci, "101", "ali-sifre")
    istemci.post(
        "/profil/foto",
        data={"csrf": csrf},
        files={"foto": ("a.jpg", JPG, "image/jpeg")},
    )
    assert (
        istemci.post(
            "/profil/foto/sil", data={"csrf": csrf}, follow_redirects=False
        ).status_code
        == 303
    )
    assert istemci.get(f"/foto/{ornek['ogr1_k']}").status_code == 404


# --- yıllık plan ---


def test_yillik_plan_akisi_ve_yetki(istemci, ornek, conn, yeni_kullanici):
    csrf = giris(istemci, "hoca", "hoca-sifre")
    assert "Plan yok" in istemci.get("/ogretmen/planlar").text
    r = istemci.post(
        "/ogretmen/plan",
        data={"csrf": csrf, "sinif": "9-A", "ders": "matematik"},
        files={"dosya": ("Matematik Planı.pdf", PDF, "application/pdf")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    pid = conn.execute("SELECT id FROM yillik_plan").fetchone()[0]
    r = istemci.get(f"/plan/{pid}")
    assert (
        r.status_code == 200
        and r.content == PDF
        and "attachment" in r.headers["content-disposition"]
    )
    # sahte uzantı ve görevsiz sınıf
    r = istemci.post(
        "/ogretmen/plan",
        data={"csrf": csrf, "sinif": "9-A", "ders": "matematik"},
        files={"dosya": ("plan.pdf", JPG, "application/pdf")},
    )
    assert r.status_code == 422 and "Excel" in r.text
    assert (
        istemci.post(
            "/ogretmen/plan",
            data={"csrf": csrf, "sinif": "9-B", "ders": "matematik"},
            files={"dosya": ("p.pdf", PDF, "application/pdf")},
        ).status_code
        == 404
    )

    yeni_kullanici(conn, "ogretmen", "Diğer", "diger", sifre="diger-sifre")
    giris(istemci, "diger", "diger-sifre")
    assert istemci.get(f"/plan/{pid}").status_code == 404
    giris(istemci, "101", "ali-sifre")
    assert istemci.get(f"/plan/{pid}").status_code == 404
    veli_giris(istemci, conn, ornek["veli1"])
    assert istemci.get(f"/plan/{pid}").status_code == 404
    giris(istemci, "mudur", "mudur-sifre")
    assert istemci.get(f"/plan/{pid}").status_code == 200
    assert "Matematik Planı.pdf" in istemci.get("/yonetici/planlar").text
    assert (
        conn.execute(
            "SELECT count(*) FROM erisim_log WHERE eylem = ?", (f"yillik_plan:{pid}",)
        ).fetchone()[0]
        == 1
    )


# --- sınav takvimi ---


def test_sinav_girisi_ve_gorunurluk(istemci, ornek, conn):
    csrf = giris(istemci, "hoca", "hoca-sifre")
    assert istemci.get("/ogretmen/sinavlar").status_code == 200
    r = istemci.post(
        "/ogretmen/sinav/yazili",
        data={
            "csrf": csrf,
            "gorev": "9-A|matematik",
            "tarih": "2099-05-10",
            "ders_no": "3",
            "aciklama": "Kesirler",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert (
        istemci.post(
            "/ogretmen/sinav/yazili",
            data={"csrf": csrf, "gorev": "9-B|matematik", "tarih": "2099-05-10"},
        ).status_code
        == 404
    )
    assert (
        istemci.post(
            "/ogretmen/sinav/yazili",
            data={"csrf": csrf, "gorev": "9-A|matematik", "tarih": ""},
        ).status_code
        == 422
    )
    istemci.post(
        "/ogretmen/sinav/deneme",
        data={
            "csrf": csrf,
            "baslik": "9. sınıf denemesi",
            "tarih": "2099-05-11",
            "duzey": "9",
        },
    )
    istemci.post(
        "/ogretmen/sinav/deneme",
        data={
            "csrf": csrf,
            "baslik": "TYT denemesi",
            "tarih": "2099-05-12",
            "duzey": "12",
        },
    )

    giris(istemci, "101", "ali-sifre")  # 9-A
    t = istemci.get("/ogrenci/sinavlar").text
    assert (
        "Matematik yazılısı" in t
        and "9. sınıf denemesi" in t
        and "TYT denemesi" not in t
    )
    giris(istemci, "201", "ayse-sifre")  # 9-B
    t = istemci.get("/ogrenci/sinavlar").text
    assert "Matematik yazılısı" not in t and "9. sınıf denemesi" in t
    assert (
        istemci.post(
            "/ogretmen/sinav/deneme",
            data={"csrf": "x", "baslik": "x", "tarih": "2099-01-01"},
        ).status_code
        == 404
    )
    veli_giris(istemci, conn, ornek["veli1"])
    t = istemci.get("/veli/sinavlar").text
    assert "Matematik yazılısı" in t and "9. sınıf denemesi" in t
    assert istemci.get(f"/veli/sinavlar?ogr={ornek['ogr2']}").status_code == 404


def test_yaklasan_sinav_ana_sayfada(istemci, ornek, conn, saat):
    import sinavlar

    hoca = conn.execute(
        "SELECT * FROM kullanici WHERE id = ?", (ornek["ogretmen"],)
    ).fetchone()
    sinavlar.yazili_ekle(
        conn, hoca, "9-A", "matematik", "2026-10-14"
    )  # saat: 2026-10-12
    sinavlar.yazili_ekle(
        conn, hoca, "9-A", "matematik", "2026-12-01", baslik="Uzak yazılı"
    )
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci").text
    assert "Matematik yazılısı" in t and "2 gün" in t and "Uzak yazılı" not in t


def test_sinav_duzenleme_yetkisi(istemci, ornek, conn, yeni_kullanici):
    csrf = giris(istemci, "hoca", "hoca-sifre")
    istemci.post(
        "/ogretmen/sinav/deneme",
        data={"csrf": csrf, "baslik": "Deneme", "tarih": "2099-05-11"},
    )
    sid = conn.execute("SELECT id FROM sinav").fetchone()[0]
    assert istemci.get(f"/ogretmen/sinav/{sid}").status_code == 200
    r = istemci.post(
        f"/ogretmen/sinav/{sid}",
        data={"csrf": csrf, "baslik": "Deneme 2", "tarih": "2099-05-12", "duzey": "11"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert conn.execute("SELECT baslik, duzeyler FROM sinav").fetchone()[:] == (
        "Deneme 2",
        "11",
    )
    yeni_kullanici(conn, "ogretmen", "Diğer", "diger", sifre="diger-sifre")
    csrf2 = giris(istemci, "diger", "diger-sifre")
    assert istemci.get(f"/ogretmen/sinav/{sid}").status_code == 404
    assert (
        istemci.post(f"/ogretmen/sinav/{sid}/sil", data={"csrf": csrf2}).status_code
        == 404
    )
    csrf3 = giris(istemci, "mudur", "mudur-sifre")
    assert (
        istemci.post(
            f"/ogretmen/sinav/{sid}/sil", data={"csrf": csrf3}, follow_redirects=False
        ).status_code
        == 303
    )


def test_kisayollar_ve_sekme(istemci, ornek):
    giris(istemci, "hoca", "hoca-sifre")
    t = istemci.get("/ogretmen").text
    assert (
        'href="/ogretmen/planlar"' in t
        and 'href="/ogretmen/sinavlar"' in t
        and 'href="/profil"' in t
    )
    giris(istemci, "mudur", "mudur-sifre")
    t = istemci.get("/yonetici").text
    assert 'href="/yonetici/planlar"' in t and 'href="/ogretmen/sinavlar"' in t
