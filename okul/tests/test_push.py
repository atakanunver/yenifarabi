"""Web Push: abonelik kuralları, sabit şablon (veri sızmaz), hata yalıtımı, rotalar."""

import json

import auth
import push
import pytest
from ayarlar import AYAR
from fastapi.testclient import TestClient

UC = "https://fcm.googleapis.com/fcm/send/abc123"


@pytest.fixture
def etkin(monkeypatch):
    monkeypatch.setattr(AYAR, "vapid_ozel", "ozel")
    monkeypatch.setattr(AYAR, "vapid_acik", "acik-anahtar")
    monkeypatch.setattr(AYAR, "vapid_konu", "mailto:idare@ornek.k12.tr")


def _kullanici(conn, yeni_kullanici, rol="ogrenci", kadi="ogr1"):
    return yeni_kullanici(conn, rol, kadi.title(), kadi, sifre="Parola123")


def test_kapaliyken_gonderim_yapilmaz(conn, yeni_kullanici):
    k = _kullanici(conn, yeni_kullanici)
    push.abone_ol(conn, k, UC, "p", "a")
    cagrilar = []
    s = push.gonder(conn, [k], "duyuru", gonderici=lambda *a: cagrilar.append(a))
    assert cagrilar == [] and s == {"gonderilen": 0, "silinen": 0, "hata": 0}


def test_sabit_sablon_ve_veri_sizmaz(conn, yeni_kullanici, etkin):
    k = _kullanici(conn, yeni_kullanici)
    push.abone_ol(conn, k, UC, "p", "a")
    alinan = []
    s = push.gonder(conn, [k], "duyuru", gonderici=lambda ab, veri: alinan.append((ab, veri)))
    assert s["gonderilen"] == 1
    ab, veri = alinan[0]
    assert ab["endpoint"] == UC and ab["keys"] == {"p256dh": "p", "auth": "a"}
    assert json.loads(veri) == {"baslik": "Dijital Okul", "govde": "Yeni bir duyuru var.", "url": "/"}
    assert "Ogr1" not in veri  # kullanıcı adı/ad soyad payload'a girmez


def test_bilinmeyen_tur_gonderilmez(conn, yeni_kullanici, etkin):
    k = _kullanici(conn, yeni_kullanici)
    push.abone_ol(conn, k, UC, "p", "a")
    alinan = []
    push.gonder(conn, [k], "serbest-metin", gonderici=lambda *a: alinan.append(a))
    assert alinan == []


def test_kalici_hata_aboneligi_siler(conn, yeni_kullanici, etkin):
    k = _kullanici(conn, yeni_kullanici)
    push.abone_ol(conn, k, UC, "p", "a")

    def gec(ab, veri):
        raise push._KaliciHata

    s = push.gonder(conn, [k], "duyuru", gonderici=gec)
    assert s["silinen"] == 1 and push.abonelik_sayisi(conn, k) == 0


def test_gecici_hata_sayac_artirir_esikte_siler_ve_istisna_firlatmaz(conn, yeni_kullanici, etkin):
    k = _kullanici(conn, yeni_kullanici)
    push.abone_ol(conn, k, UC, "p", "a")

    def bozuk(ab, veri):
        raise RuntimeError("ağ hatası")

    for i in range(push.AZAMI_HATA - 1):
        assert push.gonder(conn, [k], "duyuru", gonderici=bozuk)["hata"] == 1
        assert push.abonelik_sayisi(conn, k) == 1
    push.gonder(conn, [k], "duyuru", gonderici=bozuk)
    assert push.abonelik_sayisi(conn, k) == 0


def test_basari_hata_sayacini_sifirlar(conn, yeni_kullanici, etkin):
    k = _kullanici(conn, yeni_kullanici)
    push.abone_ol(conn, k, UC, "p", "a")
    push.gonder(conn, [k], "duyuru", gonderici=lambda *a: (_ for _ in ()).throw(RuntimeError()))
    assert conn.execute("SELECT hata_sayisi FROM push_abonelik").fetchone()[0] == 1
    push.gonder(conn, [k], "duyuru", gonderici=lambda *a: None)
    r = conn.execute("SELECT hata_sayisi, son_basari FROM push_abonelik").fetchone()
    assert r["hata_sayisi"] == 0 and r["son_basari"]


def test_baska_kullanicinin_aboneligi_gonderimde_olmaz(conn, yeni_kullanici, etkin):
    a = _kullanici(conn, yeni_kullanici, kadi="ogr1")
    b = _kullanici(conn, yeni_kullanici, kadi="ogr2")
    push.abone_ol(conn, a, UC, "p", "a")
    alinan = []
    push.gonder(conn, [b], "duyuru", gonderici=lambda *x: alinan.append(x))
    assert alinan == []


def test_paylasilan_cihaz_uc_nokta_devredilir_ve_sinir(conn, yeni_kullanici):
    a = _kullanici(conn, yeni_kullanici, kadi="ogr1")
    b = _kullanici(conn, yeni_kullanici, kadi="ogr2")
    assert push.abone_ol(conn, a, UC, "p", "a")
    assert push.abone_ol(conn, b, UC, "p2", "a2")
    assert push.abonelik_sayisi(conn, a) == 0 and push.abonelik_sayisi(conn, b) == 1
    for i in range(push.AZAMI_ABONELIK - 1):
        assert push.abone_ol(conn, b, f"https://x.example/{i}", "p", "a")
    assert not push.abone_ol(conn, b, "https://x.example/fazla", "p", "a")


def test_abonelik_sil_yalniz_kendininkini(conn, yeni_kullanici):
    a = _kullanici(conn, yeni_kullanici, kadi="ogr1")
    b = _kullanici(conn, yeni_kullanici, kadi="ogr2")
    push.abone_ol(conn, a, UC, "p", "a")
    push.abonelik_sil(conn, b, UC)
    assert push.abonelik_sayisi(conn, a) == 1
    push.abonelik_sil(conn, a, UC)
    assert push.abonelik_sayisi(conn, a) == 0


@pytest.mark.parametrize("uc", ["", "http://x.example/a", "javascript:alert(1)", "https://", "https://x/" + "a" * 700])
def test_gecersiz_uc_nokta(uc):
    assert not push.uc_nokta_gecerli(uc)


def test_gecerli_uc_nokta():
    assert push.uc_nokta_gecerli(UC)


# --- rotalar ---

def _istemci():
    from app import app

    return TestClient(app)


def _giris(c, conn, yeni_kullanici, rol="ogrenci", kadi="ogr1"):
    k = yeni_kullanici(conn, rol, kadi.title(), kadi, sifre="Parola123")
    c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, k))  # veli SMS koduyla girer: oturumu doğrudan aç
    return k


def test_rotalar_kapaliyken_404(conn, yeni_kullanici):
    with _istemci() as c:
        _giris(c, conn, yeni_kullanici)
        assert c.get("/push/anahtar").status_code == 404
        assert c.get("/bildirimler").status_code == 404
        assert "/bildirimler" not in c.get("/duyurular").text


def test_rotalar_girissiz_yonlendirir(etkin):
    with _istemci() as c:
        assert c.get("/push/anahtar", follow_redirects=False).status_code == 303
        assert c.post("/push/abone", data={}, follow_redirects=False).status_code == 303


@pytest.mark.parametrize("rol", ["ogrenci", "veli", "ogretmen", "yonetici"])
def test_her_rol_abone_olabilir(conn, yeni_kullanici, etkin, rol):
    with _istemci() as c:
        k = _giris(c, conn, yeni_kullanici, rol, "k" + rol)
        assert c.get("/push/anahtar").json() == {"acik": "acik-anahtar"}
        sayfa = c.get("/bildirimler")
        assert sayfa.status_code == 200 and "push-kutu" in sayfa.text
        csrf = sayfa.text.split('data-csrf="')[1].split('"')[0]
        r = c.post("/push/abone", data={"csrf": csrf, "uc_nokta": UC, "p256dh": "p", "auth": "a"})
        assert r.status_code == 204
        assert push.abonelik_sayisi(conn, k) == 1
        assert c.post("/push/iptal", data={"csrf": csrf, "uc_nokta": UC}).status_code == 204
        assert push.abonelik_sayisi(conn, k) == 0


def test_abone_csrf_ve_dogrulama(conn, yeni_kullanici, etkin):
    with _istemci() as c:
        k = _giris(c, conn, yeni_kullanici)
        csrf = c.get("/bildirimler").text.split('data-csrf="')[1].split('"')[0]
        veri = {"uc_nokta": UC, "p256dh": "p", "auth": "a"}
        assert c.post("/push/abone", data=veri).status_code == 400  # csrf yok
        assert c.post("/push/abone", data={**veri, "csrf": csrf, "uc_nokta": "http://x.example/a"}).status_code == 400
        assert c.post("/push/abone", data={**veri, "csrf": csrf, "p256dh": ""}).status_code == 400
        assert c.post("/push/abone", data={**veri, "csrf": csrf, "auth": "a" * 500}).status_code == 400
        assert push.abonelik_sayisi(conn, k) == 0


def test_deneme_rotasi_sabit_metin_yollar(conn, yeni_kullanici, etkin, monkeypatch):
    alinan = []
    monkeypatch.setattr(push, "_webpush_gonder", lambda ab, veri: alinan.append(veri))
    with _istemci() as c:
        k = _giris(c, conn, yeni_kullanici)
        csrf = c.get("/bildirimler").text.split('data-csrf="')[1].split('"')[0]
        push.abone_ol(conn, k, UC, "p", "a")
        assert c.post("/push/deneme", data={"csrf": csrf}).status_code == 204
    assert len(alinan) == 1 and "Test bildirimi" in alinan[0]


def test_sema_v11_ve_geri_alma_betigi():
    import db
    from scripts import geri_al

    assert len(db.GOCLER) >= 11 and "push_abonelik" in db.GOCLER[10]
    assert "push_abonelik" in geri_al.GERI[11]
