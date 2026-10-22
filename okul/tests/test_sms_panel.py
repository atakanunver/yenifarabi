"""Yönetici SMS paneli: rol yetkisi, CSRF, taslak→onay akışı, tüm okul sayı onayı, denetim kaydı."""

import auth
import pytest
from fastapi.testclient import TestClient
from kaynaklar import sms


def _istemci():
    from app import app

    return TestClient(app)


def _giris(c, conn, yeni_kullanici, rol, kadi):
    k = yeni_kullanici(conn, rol, kadi.title(), kadi, sifre="Parola123")
    c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, k))
    return k


def _csrf(c, yol="/yonetici/sms"):
    return c.get(yol).text.split('name="csrf" value="')[1].split('"')[0]


@pytest.fixture
def sahte(monkeypatch):
    cagrilar = []

    def panel(yontem, yol, json=None):
        cagrilar.append((yontem, yol, json))
        if yol == "/gonderimler?limit=100":
            return {
                "gonderimler": [
                    {
                        "gonderim_id": "g1",
                        "ilk_zaman": "2026-10-21 10:00:00",
                        "toplam": 2,
                        "basarili": 1,
                        "hatali": 1,
                        "mesaj": "Merhaba veli",
                    }
                ]
            }
        if yol.endswith("-taslak"):
            return {
                "taslak_id": "t1",
                "sinif": (json or {}).get("sinif", "Personel"),
                "alici_sayisi": 7,
                "metin": json["metin"],
                "gecerlilik_dk": 30,
                "test": False,
            }
        if yol.endswith("-gonder"):
            return {"gonderim_id": "g2", "sinif": "9-A", "alici_sayisi": 7}
        if yol == "/gonderim/g1":
            return {
                "gonderim_id": "g1",
                "mesaj": "Merhaba veli",
                "satirlar": [
                    {
                        "isim": "Ali",
                        "telefon": "5551112233",
                        "durum": "gonderildi",
                        "hata_metni": None,
                        "zaman": "x",
                    },
                    {
                        "isim": "Veli",
                        "telefon": "5554445566",
                        "durum": "hata",
                        "hata_metni": "modem",
                        "zaman": "x",
                    },
                ],
            }
        if yol.endswith("/tekrar"):
            return {"gonderim_id": "g3", "alici_sayisi": 1}
        raise AssertionError(yol)

    monkeypatch.setattr(sms, "_panel", panel)
    return cagrilar


@pytest.mark.parametrize("rol", ["ogrenci", "ogretmen", "veli"])
def test_diger_roller_goremez(conn, yeni_kullanici, sahte, rol):
    with _istemci() as c:
        _giris(c, conn, yeni_kullanici, rol, "x" + rol)
        assert c.get("/yonetici/sms").status_code == 404
        assert c.get("/yonetici/sms/g1").status_code == 404
        assert c.post(
            "/yonetici/sms/taslak", data={"tur": "veli", "metin": "x"}
        ).status_code in (400, 404)
    assert sahte == []


def test_liste_taslak_gonder_ve_denetim(conn, yeni_kullanici, sahte):
    with _istemci() as c:
        k = _giris(c, conn, yeni_kullanici, "yonetici", "yon")
        assert "Merhaba veli" in c.get("/yonetici/sms").text
        r = c.post(
            "/yonetici/sms/taslak",
            data={
                "csrf": _csrf(c),
                "tur": "veli",
                "sinif": "9-A",
                "metin": "Kermes var",
            },
        )
        assert (
            r.status_code == 200 and "7</b> alıcı" in r.text and "Kermes var" in r.text
        )
        assert not [x for x in sahte if x[1].endswith("-gonder")]  # önizleme göndermez
        r = c.post(
            "/yonetici/sms/gonder",
            data={"csrf": _csrf(c), "tur": "veli", "taslak_id": "t1"},
            follow_redirects=False,
        )
        assert r.status_code == 303 and r.headers["location"] == "/yonetici/sms/g2"
    assert ("POST", "/veli-gonder", {"taslak_id": "t1", "alici_sayisi": None}) in sahte
    assert (
        conn.execute(
            "SELECT eylem FROM erisim_log WHERE kullanici_id = ?", (k,)
        ).fetchone()[0]
        == "sms_gonder:g2:veli:9-A:7"
    )


def test_tum_okul_sayi_istenir_ve_iletilir(conn, yeni_kullanici, sahte):
    with _istemci() as c:
        _giris(c, conn, yeni_kullanici, "yonetici", "yon")
        r = c.post(
            "/yonetici/sms/taslak",
            data={
                "csrf": _csrf(c),
                "tur": "veli",
                "sinif": "TÜM OKUL",
                "metin": "Duyuru",
            },
        )
        assert 'name="alici_sayisi"' in r.text
        c.post(
            "/yonetici/sms/gonder",
            data={
                "csrf": _csrf(c),
                "tur": "veli",
                "taslak_id": "t1",
                "alici_sayisi": "7",
            },
            follow_redirects=False,
        )
    assert ("POST", "/veli-gonder", {"taslak_id": "t1", "alici_sayisi": 7}) in sahte


def test_csrf_zorunlu_ve_gecersiz_tur(conn, yeni_kullanici, sahte):
    with _istemci() as c:
        _giris(c, conn, yeni_kullanici, "yonetici", "yon")
        assert (
            c.post(
                "/yonetici/sms/taslak", data={"tur": "veli", "metin": "x"}
            ).status_code
            == 400
        )
        assert (
            c.post(
                "/yonetici/sms/taslak",
                data={"csrf": _csrf(c), "tur": "bilinmeyen", "metin": "x"},
            ).status_code
            == 404
        )
    assert not [x for x in sahte if x[0] == "POST"]


def test_detay_ve_tekrar(conn, yeni_kullanici, sahte):
    with _istemci() as c:
        _giris(c, conn, yeni_kullanici, "yonetici", "yon")
        t = c.get("/yonetici/sms/g1").text
        assert "Ali" in t and "modem" in t and "Hatalıları yeniden dene (1)" in t
        r = c.post(
            "/yonetici/sms/g1/tekrar",
            data={"csrf": _csrf(c, "/yonetici/sms/g1")},
            follow_redirects=False,
        )
        assert r.status_code == 303 and r.headers["location"] == "/yonetici/sms/g3"


def test_servis_hatasi_sayfayi_bozmaz(conn, yeni_kullanici, monkeypatch):
    def patla(*a, **k):
        raise sms.SmsHatasi("SMS servisine şu an ulaşılamıyor.")

    monkeypatch.setattr(sms, "_panel", patla)
    with _istemci() as c:
        _giris(c, conn, yeni_kullanici, "yonetici", "yon")
        r = c.get("/yonetici/sms")
        assert r.status_code == 200 and "ulaşılamıyor" in r.text
        assert c.get("/yonetici/sms/g1").status_code == 404
