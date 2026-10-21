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
    assert json.loads(veri) == {"baslik": "Dijital Okul", "govde": "Yeni bir duyuru var.", "url": "/duyurular"}
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


# --- Faz 2: alıcılar ve tetikleyiciler ---

def _kur(conn, yeni_kullanici):
    """9-A: öğrenci+veli+öğretmen; 10-A: öğrenci; hepsi bildirime abone."""
    k = {}
    k["yonetici"] = yeni_kullanici(conn, "yonetici", "Yon", "yon", sifre="Parola123")
    k["ogretmen"] = yeni_kullanici(conn, "ogretmen", "Ogt", "ogt", sifre="Parola123")
    k["ogr9"] = yeni_kullanici(conn, "ogrenci", "Ogr9", "ogr9", sifre="Parola123")
    k["ogr10"] = yeni_kullanici(conn, "ogrenci", "Ogr10", "ogr10", sifre="Parola123")
    k["veli9"] = yeni_kullanici(conn, "veli", "Veli9", "veli9", telefon="05550000001")
    k["veli10"] = yeni_kullanici(conn, "veli", "Veli10", "veli10", telefon="05550000002")
    conn.execute("INSERT INTO ogrenci (id, okul_no, ad_soyad, sinif, kullanici_id) VALUES (1, 1, 'A', '9-A', ?)", (k["ogr9"],))
    conn.execute("INSERT INTO ogrenci (id, okul_no, ad_soyad, sinif, kullanici_id) VALUES (2, 2, 'B', '10-A', ?)", (k["ogr10"],))
    conn.execute("INSERT INTO veli_ogrenci (veli_id, ogrenci_id) VALUES (?, 1)", (k["veli9"],))
    conn.execute("INSERT INTO veli_ogrenci (veli_id, ogrenci_id) VALUES (?, 2)", (k["veli10"],))
    conn.execute("INSERT INTO ogretmen_gorev (ogretmen_id, sinif, ders) VALUES (?, '9-A', 'matematik')", (k["ogretmen"],))
    conn.commit()
    for i, (ad, uid) in enumerate(k.items()):
        push.abone_ol(conn, uid, f"https://x.example/{i}", "p", "a")
    return k


def test_duyuru_alicilari_gorunurluk_kuraliyla_ayni(conn, yeni_kullanici):
    k = _kur(conn, yeni_kullanici)
    sinif = set(push.duyuru_alicilari(conn, "sinif", "9-A", k["ogretmen"]))
    assert sinif == {k["yonetici"], k["ogr9"], k["veli9"]}  # yazar (öğretmen) hariç; 10-A'dakiler yok
    okul = set(push.duyuru_alicilari(conn, "okul", None, k["yonetici"]))
    assert okul == set(k.values()) - {k["yonetici"]}
    rol = set(push.duyuru_alicilari(conn, "rol", "veli", k["yonetici"]))
    assert rol == {k["veli9"], k["veli10"]}
    assert push.duyuru_alicilari(conn, "sinif", "", 0) == [] and push.duyuru_alicilari(conn, "x", "y", 0) == []


def test_pasif_ve_abonesiz_kullanici_alici_olmaz(conn, yeni_kullanici):
    k = _kur(conn, yeni_kullanici)
    conn.execute("UPDATE kullanici SET aktif = 0 WHERE id = ?", (k["ogr9"],))
    conn.execute("DELETE FROM push_abonelik WHERE kullanici_id = ?", (k["veli9"],))
    conn.commit()
    assert set(push.duyuru_alicilari(conn, "sinif", "9-A", k["ogretmen"])) == {k["yonetici"]}


def test_odev_alicilari_yalniz_sinif_ogrencileri(conn, yeni_kullanici):
    k = _kur(conn, yeni_kullanici)
    assert push.odev_alicilari(conn, "9-A", k["ogretmen"]) == [k["ogr9"]]
    assert push.odev_alicilari(conn, "11-A", k["ogretmen"]) == []


def _yakala(monkeypatch):
    cagrilar = []
    monkeypatch.setattr(push, "_webpush_gonder", lambda ab, veri: cagrilar.append((ab["endpoint"], json.loads(veri))))
    return cagrilar


def _csrf(c):
    return c.get("/ogretmen/duyuru").text.split('name="csrf" value="')[1].split('"')[0]


def test_duyuru_rotasi_sinif_alicilarina_bildirir(conn, yeni_kullanici, etkin, monkeypatch):
    k = _kur(conn, yeni_kullanici)
    cagrilar = _yakala(monkeypatch)
    with _istemci() as c:
        c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, k["ogretmen"]))
        r = c.post("/ogretmen/duyuru", data={"csrf": _csrf(c), "baslik": "Gizli Baslik", "metin": "Gizli Metin", "hedef_tur": "sinif", "hedef": "9-A"}, follow_redirects=False)
        assert r.status_code == 303
    assert len(cagrilar) == 3  # öğrenci, veli, yönetici
    for _, veri in cagrilar:
        assert veri["govde"] == "Yeni bir duyuru var."
        assert "Gizli" not in json.dumps(veri)  # başlık/metin payload'a girmez


def test_odev_rotasi_ogrencilere_bildirir(conn, yeni_kullanici, etkin, monkeypatch):
    k = _kur(conn, yeni_kullanici)
    cagrilar = _yakala(monkeypatch)
    with _istemci() as c:
        c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, k["ogretmen"]))
        csrf = _csrf(c)
        r = c.post("/ogretmen/odev/yeni", data={"csrf": csrf, "sinif": "9-A", "ders": "matematik", "tur": "klasik", "baslik": "Gizli Ödev", "aciklama": "", "teslim": "2030-01-01"}, follow_redirects=False)
        assert r.status_code == 303
    assert [v["govde"] for _, v in cagrilar] == ["Yeni bir ödevin var."]
    assert "Gizli" not in json.dumps(cagrilar)


def test_bildirim_hatasi_duyuruyu_bozmaz(conn, yeni_kullanici, etkin, monkeypatch):
    k = _kur(conn, yeni_kullanici)

    def patla(ab, veri):
        raise RuntimeError("push servisi çöktü")

    monkeypatch.setattr(push, "_webpush_gonder", patla)
    with _istemci() as c:
        c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, k["ogretmen"]))
        r = c.post("/ogretmen/duyuru", data={"csrf": _csrf(c), "baslik": "B", "metin": "M", "hedef_tur": "sinif", "hedef": "9-A"}, follow_redirects=False)
        assert r.status_code == 303
    assert conn.execute("SELECT COUNT(*) FROM duyuru").fetchone()[0] == 1


def test_kapaliyken_rota_bildirim_denemez(conn, yeni_kullanici, monkeypatch):
    k = _kur(conn, yeni_kullanici)
    cagrilar = _yakala(monkeypatch)
    with _istemci() as c:
        c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, k["ogretmen"]))
        c.post("/ogretmen/duyuru", data={"csrf": _csrf(c), "baslik": "B", "metin": "M", "hedef_tur": "sinif", "hedef": "9-A"})
    assert cagrilar == []


# --- çıkışta abonelik silme ---

def test_cikista_yalniz_bu_cihazin_aboneligi_silinir(conn, yeni_kullanici, etkin):
    a = _kullanici(conn, yeni_kullanici, kadi="ogr1")
    b = _kullanici(conn, yeni_kullanici, kadi="ogr2")
    push.abone_ol(conn, a, UC, "p", "a")
    push.abone_ol(conn, a, "https://x.example/diger-cihaz", "p", "a")
    push.abone_ol(conn, b, "https://x.example/baskasi", "p", "a")
    with _istemci() as c:
        c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, a))
        csrf = c.get("/bildirimler").text.split('data-csrf="')[1].split('"')[0]
        # başkasının uç noktasını göndermek onu silemez
        c.post("/cikis", data={"csrf": csrf, "push_uc": "https://x.example/baskasi"}, follow_redirects=False)
    assert push.abonelik_sayisi(conn, b) == 1
    assert push.abonelik_sayisi(conn, a) == 2  # kendi diğer cihazları da duruyor
    with _istemci() as c:
        c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, a))
        csrf = c.get("/bildirimler").text.split('data-csrf="')[1].split('"')[0]
        r = c.post("/cikis", data={"csrf": csrf, "push_uc": UC}, follow_redirects=False)
        assert r.status_code == 303
    left = [r[0] for r in conn.execute("SELECT uc_nokta FROM push_abonelik WHERE kullanici_id = ?", (a,))]
    assert left == ["https://x.example/diger-cihaz"]


def test_cikis_push_alanisiz_calisir(conn, yeni_kullanici, etkin):
    a = _kullanici(conn, yeni_kullanici)
    push.abone_ol(conn, a, UC, "p", "a")
    with _istemci() as c:
        c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, a))
        csrf = c.get("/bildirimler").text.split('data-csrf="')[1].split('"')[0]
        assert c.post("/cikis", data={"csrf": csrf}, follow_redirects=False).status_code == 303
    assert push.abonelik_sayisi(conn, a) == 1


def test_cikis_betigi_yalniz_bildirim_acikken_yuklenir(conn, yeni_kullanici, etkin, monkeypatch):
    a = _kullanici(conn, yeni_kullanici)
    with _istemci() as c:
        c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, a))
        assert "/static/push-cikis.js" in c.get("/duyurular").text
        monkeypatch.setattr(AYAR, "vapid_ozel", "")
        assert "/static/push-cikis.js" not in c.get("/duyurular").text


# --- "Bildirimleri aç" kartı ---

@pytest.mark.parametrize("rol,yol", [
    ("ogrenci", "/ogrenci"), ("veli", "/veli"), ("ogretmen", "/ogretmen"), ("yonetici", "/yonetici"),
    ("ogrenci", "/duyurular"),
])
def test_acma_karti_ana_sayfalarda_herkese_gorunur(conn, yeni_kullanici, etkin, rol, yol):
    with _istemci() as c:
        k = _giris(c, conn, yeni_kullanici, rol, "k" + rol)
        if rol == "ogrenci":  # ana sayfa öğrenci kaydı ister
            conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (77, 'T', '9-A', ?)", (k,))
            conn.commit()
        r = c.get(yol)
        assert r.status_code == 200
        assert 'id="push-kart"' in r.text and "/static/push-kart.js" in r.text and "/static/push-ortak.js" in r.text
        assert 'data-csrf="' in r.text


def test_acma_karti_diger_sayfalarda_ve_kapaliyken_yok(conn, yeni_kullanici, etkin, monkeypatch):
    with _istemci() as c:
        _giris(c, conn, yeni_kullanici, "ogrenci", "ogr1")
        assert 'id="push-kart"' not in c.get("/ogrenci/odevler").text
        monkeypatch.setattr(AYAR, "vapid_ozel", "")
        assert 'id="push-kart"' not in c.get("/ogrenci").text


def test_odev_hatirlat_alicilari_yalniz_teslim_etmeyenler(conn, yeni_kullanici):
    import odevler

    k = _kur(conn, yeni_kullanici)
    oid = odevler.odev_olustur(conn, k["ogretmen"], "9-A", "matematik", "klasik", "A", "", "2026-10-20", [])
    assert push.odev_hatirlat_alicilari(conn, oid, k["ogretmen"]) == [k["ogr9"]]
    conn.execute(
        "INSERT INTO odev_teslim (odev_id, ogrenci_id, durum, zaman) VALUES (?, 1, 'yapti', '2026-10-12 10:00:00')", (oid,)
    )
    conn.commit()
    assert push.odev_hatirlat_alicilari(conn, oid, k["ogretmen"]) == []
