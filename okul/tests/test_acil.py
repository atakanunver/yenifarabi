"""Acil durum: rol yetkisi, 2 adımlı onay + şifre, kilitleme, jeton, dashboard hatası, konum, push, şerit.

Gerçek siren/SMS ASLA tetiklenmez: kaynaklar.acil (dashboard çağrısı) her testte mock'lanır, conftest anahtarı boşaltır.
"""

import json
import re
from datetime import timedelta

import acil
import auth
import push
import pytest
import zaman
from fastapi.testclient import TestClient
from kaynaklar import acil as dis

SIFRE = "Parola123"


def _istemci():
    from app import app

    return TestClient(app)


def _kisi(conn, yeni_kullanici, rol, kadi):
    k = yeni_kullanici(conn, rol, kadi.title(), kadi, sifre=SIFRE)
    if rol == "ogrenci":
        conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (?, ?, '9-A', ?)", (k + 100, kadi, k))
        conn.commit()
    return k


def _oturum(c, conn, kid):
    c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, kid))


def _csrf(c, yol="/acil"):
    return c.get(yol).text.split('name="csrf" value="')[1].split('"')[0]


@pytest.fixture
def dashboard(monkeypatch):
    """Dashboard çağrılarını kaydeden sahte; gerçek ağ yok."""
    cagri = {"tetikle": [], "yanlis": []}
    mod = {"tatbikat": True}

    def tetikle(tur, kaynak, sms_metni):
        cagri["tetikle"].append((tur, kaynak, sms_metni))
        return {"tatbikat": mod["tatbikat"], "kanallar": [{"kanal": "SMS", "basarili": True}], "tahtalar": []}

    def yanlis(kaynak):
        cagri["yanlis"].append(kaynak)
        return {"tatbikat": mod["tatbikat"], "kanallar": [], "tahtalar": []}

    monkeypatch.setattr(dis, "tetikle", tetikle)
    monkeypatch.setattr(dis, "yanlis_alarm", yanlis)
    monkeypatch.setattr(dis, "durum", lambda: {"aktif": None, "tatbikat": mod["tatbikat"]})
    cagri["mod"] = mod
    return cagri


def _basla(c, tur="kilit", yer="Bahçe / toplanma alanı", sifre=SIFRE, jeton=None):
    csrf = _csrf(c)
    if jeton is None:
        r1 = c.post(f"/acil/onay/{tur}", data={"csrf": csrf, "yer": yer})
        assert r1.status_code == 200, r1.text[:200]
        jeton = re.search(r'name="jeton" value="([^"]+)"', r1.text).group(1)
    return c.post(
        "/acil/baslat", data={"csrf": csrf, "tur": tur, "yer": yer, "jeton": jeton, "sifre": sifre}, follow_redirects=False
    )


def _jeton_al(c, tur="kilit", yer=""):
    r1 = c.post(f"/acil/onay/{tur}", data={"csrf": _csrf(c), "yer": yer})
    return re.search(r'name="jeton" value="([^"]+)"', r1.text).group(1)


def _olay_sayisi(conn):
    return conn.execute("SELECT COUNT(*) FROM acil_olay").fetchone()[0]


# --- yetki ---


@pytest.mark.parametrize("rol", ["ogrenci", "veli"])
def test_ogrenci_ve_veli_goremez(conn, yeni_kullanici, dashboard, rol):
    k = _kisi(conn, yeni_kullanici, rol, "x" + rol)
    with _istemci() as c:
        _oturum(c, conn, k)
        for yol in ("/acil", "/acil/durum", "/acil/onay/kilit"):
            assert c.get(yol).status_code == 404
        assert c.post("/acil/baslat", data={"tur": "kilit"}).status_code in (400, 404)
        assert c.post("/acil/konum", data={"yer": "Müdür odası"}).status_code in (400, 404)
    assert _olay_sayisi(conn) == 0 and not dashboard["tetikle"]


def test_girissiz_yonlendirir(dashboard):
    with _istemci() as c:
        assert c.get("/acil", follow_redirects=False).status_code == 303
        assert c.get("/acil/durum", follow_redirects=False).status_code == 303


# --- 2 adımlı onay ---


@pytest.mark.parametrize("rol", ["ogretmen", "yonetici"])
def test_tam_akis_alarm_baslatir(conn, yeni_kullanici, dashboard, rol):
    k = _kisi(conn, yeni_kullanici, rol, "a" + rol)
    with _istemci() as c:
        _oturum(c, conn, k)
        r = _basla(c)
        assert r.status_code == 303 and r.headers["location"] == "/acil?tamam=kilit"
        sayfa = c.get("/acil?tamam=kilit").text
    assert len(dashboard["tetikle"]) == 1
    tur, kaynak, sms = dashboard["tetikle"][0]
    assert tur == "kilit" and kaynak.startswith(f"okul:{k}:") and len(sms) <= 160
    assert ("A" + rol).title() in sms and "Bahçe" in sms
    assert "TATBİKAT" in sayfa
    o = conn.execute("SELECT * FROM acil_olay").fetchone()
    assert o["basarili"] == 1 and o["tatbikat"] == 1 and o["kapanis"] is None
    assert conn.execute("SELECT COUNT(*) FROM erisim_log WHERE eylem = 'acil:kilit'").fetchone()[0] == 1


def test_jetonsuz_veya_sahte_jeton_basamaz(conn, yeni_kullanici, dashboard):
    k = _kisi(conn, yeni_kullanici, "ogretmen", "tek")
    with _istemci() as c:
        _oturum(c, conn, k)
        assert _basla(c, jeton="").status_code == 400
        assert _basla(c, jeton="9999999999.deadbeef").status_code == 400
    assert not dashboard["tetikle"] and _olay_sayisi(conn) == 0


def test_jeton_tur_yer_ve_kisiye_baglidir(conn, yeni_kullanici, dashboard):
    a = _kisi(conn, yeni_kullanici, "ogretmen", "bir")
    b = _kisi(conn, yeni_kullanici, "yonetici", "iki")
    with _istemci() as c:
        _oturum(c, conn, a)
        jeton = _jeton_al(c)
        assert _basla(c, tur="yangin", yer="", jeton=jeton).status_code == 400  # başka tür
        assert _basla(c, tur="kilit", yer="Müdür odası", jeton=jeton).status_code == 400  # başka yer
    with _istemci() as c:
        _oturum(c, conn, b)
        assert _basla(c, tur="kilit", yer="", jeton=jeton).status_code == 400  # başkasının jetonu
    assert not dashboard["tetikle"]


def test_jeton_suresi_dolar(conn, yeni_kullanici, dashboard, monkeypatch):
    k = _kisi(conn, yeni_kullanici, "ogretmen", "gec")
    with _istemci() as c:
        _oturum(c, conn, k)
        jeton = _jeton_al(c)
        gercek = zaman.simdi
        monkeypatch.setattr(zaman, "simdi", lambda: gercek() + timedelta(seconds=acil.JETON_SURESI + 5))
        assert _basla(c, yer="", jeton=jeton).status_code == 400
    assert not dashboard["tetikle"]


def test_jeton_tekrar_kullanilamaz(conn, yeni_kullanici, dashboard):
    k = _kisi(conn, yeni_kullanici, "yonetici", "cift")
    with _istemci() as c:
        _oturum(c, conn, k)
        jeton = _jeton_al(c)
        assert _basla(c, yer="", jeton=jeton).status_code == 303
        assert _basla(c, yer="", jeton=jeton).status_code == 400
    assert len(dashboard["tetikle"]) == 1


def test_csrf_zorunlu(conn, yeni_kullanici, dashboard):
    k = _kisi(conn, yeni_kullanici, "ogretmen", "csrfli")
    with _istemci() as c:
        _oturum(c, conn, k)
        assert c.post("/acil/onay/kilit", data={"csrf": "yanlis", "yer": ""}).status_code == 400
        assert c.post("/acil/baslat", data={"csrf": "yanlis", "tur": "kilit"}).status_code == 400
    assert not dashboard["tetikle"]


def test_gecersiz_tur_ve_yer(conn, yeni_kullanici, dashboard):
    k = _kisi(conn, yeni_kullanici, "ogretmen", "gecersiz")
    with _istemci() as c:
        _oturum(c, conn, k)
        assert c.get("/acil/onay/reklam").status_code == 404
        assert c.post("/acil/onay/kilit", data={"csrf": _csrf(c), "yer": "Ay yüzeyi"}).status_code == 400


# --- şifre ve kilitleme ---


def test_yanlis_sifre_basamaz_ve_hatalarda_kilitlenir(conn, yeni_kullanici, dashboard):
    k = _kisi(conn, yeni_kullanici, "ogretmen", "sifreli")
    with _istemci() as c:
        _oturum(c, conn, k)
        jeton = _jeton_al(c)
        for _ in range(auth.DENEME_ESIK):
            assert _basla(c, yer="", sifre="yanlis", jeton=jeton).status_code == 403
        assert _basla(c, yer="", sifre=SIFRE, jeton=jeton).status_code == 429  # doğru şifre de kilitli
    assert not dashboard["tetikle"] and _olay_sayisi(conn) == 0


# --- dashboard hatası / kapanış ---


def test_dashboard_hatasi_alarm_sayilmaz_ve_net_mesaj(conn, yeni_kullanici, dashboard, monkeypatch):
    def patla(*_):
        raise dis.AcilHatasi("Alarm sistemine ulaşılamıyor.")

    monkeypatch.setattr(dis, "tetikle", patla)
    k = _kisi(conn, yeni_kullanici, "yonetici", "hatali")
    with _istemci() as c:
        _oturum(c, conn, k)
        r = _basla(c)
        assert r.status_code == 502 and "112" in r.text
    assert conn.execute("SELECT basarili FROM acil_olay").fetchone()[0] == 0
    assert acil.aktif(conn) is None


@pytest.mark.parametrize("kapatan", ["gecti", "yanlis_alarm"])
def test_gecti_ve_yanlis_alarm_aktifi_kapatir(conn, yeni_kullanici, dashboard, kapatan):
    k = _kisi(conn, yeni_kullanici, "yonetici", "kapat" + kapatan[:3])
    with _istemci() as c:
        _oturum(c, conn, k)
        assert _basla(c, tur="yangin", yer="").status_code == 303
        assert acil.aktif(conn)["tur"] == "yangin"
        assert _basla(c, tur=kapatan, yer="").status_code == 303
    assert acil.aktif(conn) is None
    if kapatan == "yanlis_alarm":
        assert len(dashboard["yanlis"]) == 1


def test_gercek_mod_etiketi(conn, yeni_kullanici, dashboard):
    dashboard["mod"]["tatbikat"] = False
    k = _kisi(conn, yeni_kullanici, "yonetici", "gercek")
    with _istemci() as c:
        _oturum(c, conn, k)
        assert "tüm personele SMS" in c.get("/acil/onay/kilit").text
        assert _basla(c, yer="").status_code == 303
    assert conn.execute("SELECT tatbikat FROM acil_olay").fetchone()[0] == 0


def test_anahtar_yokken_dis_cagri_yapilmaz():
    # conftest acil_anahtar'ı boşaltır → gerçek ağ çağrısı hiç denenmez
    with pytest.raises(dis.AcilHatasi, match="ayarlanmamış"):
        dis.tetikle("kilit", "okul:1:x", "m")


def test_aktif_alarm_12_saat_sonra_dusar(conn, yeni_kullanici, dashboard, monkeypatch):
    k = _kisi(conn, yeni_kullanici, "yonetici", "eski")
    with _istemci() as c:
        _oturum(c, conn, k)
        assert _basla(c, yer="").status_code == 303
    assert acil.aktif(conn) is not None
    gercek = zaman.simdi
    monkeypatch.setattr(zaman, "simdi", lambda: gercek() + timedelta(hours=acil.AKTIF_SAAT + 1))
    assert acil.aktif(conn) is None


# --- 112 arama ---


@pytest.mark.parametrize("rol,yol", [("ogrenci", "/ogrenci"), ("ogretmen", "/ogretmen"), ("ogretmen", "/acil"), ("yonetici", "/acil")])
def test_112_arama_baglantisi(conn, yeni_kullanici, dashboard, rol, yol):
    k = _kisi(conn, yeni_kullanici, rol, "ara" + rol)
    with _istemci() as c:
        _oturum(c, conn, k)
        assert 'href="tel:112"' in c.get(yol).text


def test_112_veli_ana_sayfasinda_yok(conn, yeni_kullanici, dashboard):
    k = _kisi(conn, yeni_kullanici, "veli", "araveli")
    with _istemci() as c:
        _oturum(c, conn, k)
        assert 'href="tel:112"' not in c.get("/veli").text


# --- şerit ---


def test_serit_yalniz_ogretmen_yonetici_ve_aktifken_gorunur(conn, yeni_kullanici, dashboard):
    og = _kisi(conn, yeni_kullanici, "ogretmen", "seritli")
    st = _kisi(conn, yeni_kullanici, "ogrenci", "seritsiz")
    with _istemci() as c:
        _oturum(c, conn, og)
        assert 'role="alert" hidden' in c.get("/ogretmen").text
        assert _basla(c, tur="deprem", yer="").status_code == 303
        html = c.get("/ogretmen").text
        assert 'role="alert">' in html and ": Deprem (TATBİKAT)</span>" in html
        assert c.get("/acil/durum").json()["aktif"]["tur"] == "deprem"
    with _istemci() as c:
        _oturum(c, conn, st)
        assert "acil-serit" not in c.get("/ogrenci").text


# --- konum ---


def _konum(c, yer="Müdür odası", **extra):
    return c.post("/acil/konum", data={"csrf": _csrf(c), "yer": yer, **extra}, follow_redirects=False)


def test_konum_paylasimi_digerine_gorunur_ogrenciye_degil(conn, yeni_kullanici, dashboard):
    a = _kisi(conn, yeni_kullanici, "ogretmen", "gonderen")
    b = _kisi(conn, yeni_kullanici, "yonetici", "gorur")
    st = _kisi(conn, yeni_kullanici, "ogrenci", "gormez")
    with _istemci() as c:
        _oturum(c, conn, a)
        assert _konum(c, enlem="39.92", boylam="32.85", dogruluk="12").status_code == 303
    with _istemci() as c:
        _oturum(c, conn, b)
        html = c.get("/acil").text
        assert "Gonderen" in html and "Müdür odası" in html and "google.com/maps?q=39.92,32.85" in html and "±12 m" in html
    with _istemci() as c:
        _oturum(c, conn, st)
        assert c.get("/acil").status_code == 404


def test_konum_yer_sinif_kati(conn, yeni_kullanici, dashboard, tmp_path, monkeypatch):
    from ayarlar import AYAR

    yol = tmp_path / "program.json"
    yol.write_text(json.dumps({"siniflar": {"9-A": {}, "11-B": {}}}), encoding="utf-8")
    monkeypatch.setattr(AYAR, "program_yolu", yol)
    k = _kisi(conn, yeni_kullanici, "ogretmen", "kat")
    with _istemci() as c:
        _oturum(c, conn, k)
        assert _konum(c, yer="9-A sınıfı").status_code == 303
        assert _konum(c, yer="11-B sınıfı").status_code == 303
    yerler = [r[0] for r in conn.execute("SELECT yer FROM acil_konum ORDER BY id")]
    assert yerler == ["9-A sınıfı (üst kat)", "11-B sınıfı (giriş katı)"]


@pytest.mark.parametrize(
    "veri",
    [
        {"yer": ""},
        {"yer": "Ay yüzeyi"},
        {"yer": "Müdür odası", "enlem": "91", "boylam": "10"},
        {"yer": "Müdür odası", "enlem": "10", "boylam": "181"},
        {"yer": "Müdür odası", "enlem": "10"},
        {"yer": "Müdür odası", "enlem": "abc", "boylam": "10"},
        {"yer": "Müdür odası", "enlem": "10", "boylam": "10", "dogruluk": "99999"},
    ],
)
def test_konum_dogrulama(conn, yeni_kullanici, dashboard, veri):
    k = _kisi(conn, yeni_kullanici, "ogretmen", "dogrulayan")
    with _istemci() as c:
        _oturum(c, conn, k)
        assert _konum(c, **veri).status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM acil_konum").fetchone()[0] == 0


def test_konum_hiz_siniri(conn, yeni_kullanici, dashboard):
    k = _kisi(conn, yeni_kullanici, "ogretmen", "hizli")
    with _istemci() as c:
        _oturum(c, conn, k)
        for _ in range(acil.KONUM_DAKIKA_AZAMI):
            assert _konum(c).status_code == 303
        assert _konum(c).status_code == 429


def test_konum_24_saat_sonra_gorunmez_ve_silinir(conn, yeni_kullanici, dashboard):
    k = _kisi(conn, yeni_kullanici, "ogretmen", "eskikonum")
    eski = (zaman.simdi() - timedelta(hours=acil.KONUM_SAKLAMA_SAAT + 1)).strftime(zaman.BICIM)
    conn.execute("INSERT INTO acil_konum (kullanici_id, yer, olusturma) VALUES (?, 'Müdür odası', ?)", (k, eski))
    conn.commit()
    assert acil.konumlar(conn) == []  # fiziksel silme gecikse bile görünmez
    assert acil.temizle(conn) == 1
    assert conn.execute("SELECT COUNT(*) FROM acil_konum").fetchone()[0] == 0


def test_konumlarda_kisi_basina_en_yenisi(conn, yeni_kullanici, dashboard):
    k = _kisi(conn, yeni_kullanici, "ogretmen", "tekrar")
    with _istemci() as c:
        _oturum(c, conn, k)
        _konum(c, yer="Müdür odası")
        _konum(c, yer="Bahçe / toplanma alanı")
    liste = acil.konumlar(conn)
    assert len(liste) == 1 and liste[0]["yer"] == "Bahçe / toplanma alanı"


# --- push ---


def test_push_sabit_sablon_ve_alicilar(conn, yeni_kullanici, dashboard, monkeypatch):
    assert push.SABLONLAR["acil"][1] == "Acil durum bildirimi var!"
    a = _kisi(conn, yeni_kullanici, "ogretmen", "basan")
    b = _kisi(conn, yeni_kullanici, "yonetici", "alan")
    v = _kisi(conn, yeni_kullanici, "veli", "veli")
    for kid in (a, b, v):
        conn.execute(
            "INSERT INTO push_abonelik (kullanici_id, uc_nokta, p256dh, auth, olusturma) VALUES (?, ?, 'p', 'a', ?)",
            (kid, f"https://fcm.googleapis.com/{kid}", zaman.simdi_str()),
        )
    conn.commit()
    assert acil.bildirim_alicilari(conn, a) == [b]  # basan hariç, veli yok
    gonderilen = []
    monkeypatch.setattr(push, "etkin_mi", lambda: True)
    monkeypatch.setattr(push, "gonder", lambda c, idler, tur, **kw: gonderilen.append((list(idler), tur)))
    with _istemci() as c:
        _oturum(c, conn, a)
        assert _basla(c, yer="").status_code == 303
    assert gonderilen == [([b], "acil")]


def test_geri_al_v15():
    from scripts import geri_al

    assert 15 in geri_al.GERI and "acil_konum" in geri_al.GERI[15] and "acil_olay" in geri_al.GERI[15]


# --- öğrenci acil bildirimi (yalnızca yöneticiler görür) ---


def _ogr_gonder(c, **veri):
    return c.post("/acil/ogrenci", data={"csrf": _csrf(c, "/acil/ogrenci"), **veri})


@pytest.mark.parametrize("rol", ["ogretmen", "yonetici", "veli"])
def test_ogrenci_bildirimi_yalniz_ogrenci_gonderir(conn, yeni_kullanici, dashboard, rol):
    k = _kisi(conn, yeni_kullanici, rol, "no" + rol)
    with _istemci() as c:
        _oturum(c, conn, k)
        assert c.get("/acil/ogrenci").status_code == 404
        assert c.post("/acil/ogrenci", data={}).status_code in (400, 404)
    assert conn.execute("SELECT COUNT(*) FROM acil_ogrenci").fetchone()[0] == 0


def test_ogrenci_ana_sayfada_dugme_var_ogretmende_yok(conn, yeni_kullanici, dashboard):
    st = _kisi(conn, yeni_kullanici, "ogrenci", "dugmeli")
    og = _kisi(conn, yeni_kullanici, "ogretmen", "dugmesiz")
    with _istemci() as c:
        _oturum(c, conn, st)
        assert 'href="/acil/ogrenci"' in c.get("/ogrenci").text
    with _istemci() as c:
        _oturum(c, conn, og)
        assert 'href="/acil/ogrenci"' not in c.get("/ogretmen").text


def test_ogrenci_gonderir_yalniz_yonetici_gorur_alarm_tetiklenmez(conn, yeni_kullanici, dashboard, monkeypatch):
    st = _kisi(conn, yeni_kullanici, "ogrenci", "cocuk")
    yon = _kisi(conn, yeni_kullanici, "yonetici", "mudur")
    og = _kisi(conn, yeni_kullanici, "ogretmen", "hoca")
    for kid in (yon, og, st):
        conn.execute(
            "INSERT INTO push_abonelik (kullanici_id, uc_nokta, p256dh, auth, olusturma) VALUES (?, ?, 'p', 'a', ?)",
            (kid, f"https://fcm.googleapis.com/{kid}", zaman.simdi_str()),
        )
    conn.commit()
    gonderilen = []
    monkeypatch.setattr(push, "etkin_mi", lambda: True)
    monkeypatch.setattr(push, "gonder", lambda c, idler, tur, **kw: gonderilen.append((list(idler), tur)))
    with _istemci() as c:
        _oturum(c, conn, st)
        r = _ogr_gonder(c, enlem="39.9", boylam="32.8", dogruluk="15")
        assert r.status_code == 200 and "idareye iletildi" in r.text and 'href="tel:112"' in r.text
    assert gonderilen == [([yon], "acil")]  # yalnızca yönetici; öğretmen/öğrenci yok
    assert not dashboard["tetikle"] and _olay_sayisi(conn) == 0 and acil.aktif(conn) is None  # alarm/SMS yok
    with _istemci() as c:
        _oturum(c, conn, yon)
        html = c.get("/acil").text
        assert "Öğrenciden acil bildirim" in html and "Cocuk" in html and "9-A" in html and "google.com/maps?q=39.9,32.8" in html
    with _istemci() as c:
        _oturum(c, conn, og)
        html = c.get("/acil").text
        assert "Öğrenciden acil bildirim" not in html and "Cocuk" not in html  # öğretmen görmez


def test_ogrenci_konumsuz_gonderebilir(conn, yeni_kullanici, dashboard):
    st = _kisi(conn, yeni_kullanici, "ogrenci", "izinsiz")
    yon = _kisi(conn, yeni_kullanici, "yonetici", "mudur2")
    with _istemci() as c:
        _oturum(c, conn, st)
        assert "idareye iletildi" in _ogr_gonder(c).text
    with _istemci() as c:
        _oturum(c, conn, yon)
        assert "yalnızca ad ve sınıf" in c.get("/acil").text


@pytest.mark.parametrize("veri", [{"enlem": "91", "boylam": "10"}, {"enlem": "10"}, {"enlem": "x", "boylam": "10"}])
def test_ogrenci_gecersiz_konum(conn, yeni_kullanici, dashboard, veri):
    st = _kisi(conn, yeni_kullanici, "ogrenci", "gecersizk")
    with _istemci() as c:
        _oturum(c, conn, st)
        assert _ogr_gonder(c, **veri).status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM acil_ogrenci").fetchone()[0] == 0


def test_ogrenci_hiz_siniri_ve_csrf(conn, yeni_kullanici, dashboard):
    st = _kisi(conn, yeni_kullanici, "ogrenci", "cok")
    with _istemci() as c:
        _oturum(c, conn, st)
        assert c.post("/acil/ogrenci", data={"csrf": "yanlis"}).status_code == 400
        for _ in range(acil.OGRENCI_DAKIKA_AZAMI):
            assert _ogr_gonder(c).status_code == 200
        assert _ogr_gonder(c).status_code == 429


def test_ogrenci_bildirimi_24_saat_sonra_silinir(conn, yeni_kullanici, dashboard):
    st = _kisi(conn, yeni_kullanici, "ogrenci", "eskiogr")
    eski = (zaman.simdi() - timedelta(hours=acil.KONUM_SAKLAMA_SAAT + 1)).strftime(zaman.BICIM)
    conn.execute("INSERT INTO acil_ogrenci (kullanici_id, olusturma) VALUES (?, ?)", (st, eski))
    conn.commit()
    assert acil.ogrenci_bildirimleri(conn) == []
    assert acil.temizle(conn) == 1


def test_geri_al_v16():
    from scripts import geri_al

    assert 16 in geri_al.GERI and "acil_ogrenci" in geri_al.GERI[16]


# --- panel/Telegram/tahta kaynaklı olay (dashboard → okul) ---


@pytest.fixture
def dis_anahtar(monkeypatch):
    import rotalar.acil as rota_acil
    from ayarlar import AYAR

    monkeypatch.setattr(AYAR, "acil_anahtar", "gizli-k")
    monkeypatch.setattr(rota_acil, "_lan_mi", lambda request: True)  # TestClient LAN sayılsın
    return {"X-Acil-Anahtar": "gizli-k"}


def _dis(c, headers, **govde):
    return c.post("/acil/dis-olay", json={"tur": "kilit", "tatbikat": True, "kaynak": "Telegram: Ali", **govde}, headers=headers)


def test_dis_olay_anahtarsiz_ve_yanlis_anahtar_404(conn, monkeypatch):
    import rotalar.acil as rota_acil
    from ayarlar import AYAR

    monkeypatch.setattr(rota_acil, "_lan_mi", lambda request: True)
    with _istemci() as c:
        assert _dis(c, {"X-Acil-Anahtar": "x"}).status_code == 404  # sunucuda anahtar yok
        monkeypatch.setattr(AYAR, "acil_anahtar", "dogru")
        assert _dis(c, {}).status_code == 404
        assert _dis(c, {"X-Acil-Anahtar": "yanlis"}).status_code == 404
    assert conn.execute("SELECT COUNT(*) FROM acil_dis_olay").fetchone()[0] == 0


def test_dis_olay_tunel_basligi_ve_ag_siniri():
    from types import SimpleNamespace

    from rotalar import pano

    lan = SimpleNamespace(headers={}, client=SimpleNamespace(host="192.168.23.252"))
    assert pano._lan_mi(lan) is True
    tunel = SimpleNamespace(headers={"cf-connecting-ip": "1.2.3.4"}, client=SimpleNamespace(host="127.0.0.1"))
    assert pano._lan_mi(tunel) is False
    dis_ip = SimpleNamespace(headers={}, client=SimpleNamespace(host="8.8.8.8"))
    assert pano._lan_mi(dis_ip) is False


def test_dis_olay_tunelden_gelirse_404(conn, monkeypatch):
    from ayarlar import AYAR

    monkeypatch.setattr(AYAR, "acil_anahtar", "k")  # _lan_mi gerçek: TestClient 'testclient' host → LAN dışı
    with _istemci() as c:
        assert _dis(c, {"X-Acil-Anahtar": "k", "cf-connecting-ip": "1.2.3.4"}).status_code == 404


def test_dis_olay_serit_ve_push_tum_personele(conn, yeni_kullanici, dashboard, dis_anahtar, monkeypatch):
    og = _kisi(conn, yeni_kullanici, "ogretmen", "hoca")
    yon = _kisi(conn, yeni_kullanici, "yonetici", "mudur")
    for kid in (og, yon):
        conn.execute(
            "INSERT INTO push_abonelik (kullanici_id, uc_nokta, p256dh, auth, olusturma) VALUES (?, ?, 'p', 'a', ?)",
            (kid, f"https://fcm.googleapis.com/{kid}", zaman.simdi_str()),
        )
    conn.commit()
    gonderilen = []
    monkeypatch.setattr(push, "etkin_mi", lambda: True)
    monkeypatch.setattr(push, "gonder", lambda c, idler, tur, **kw: gonderilen.append((sorted(idler), tur)))
    with _istemci() as c:
        assert _dis(c, dis_anahtar).status_code == 200
        _oturum(c, conn, og)
        assert "Telegram: Ali" in c.get("/ogretmen").text and ": Kilit-kapı (TATBİKAT)</span>" in c.get("/ogretmen").text
        assert c.get("/acil/durum").json()["aktif"]["ad"] == "Telegram: Ali"
        assert "Telegram: Ali" in c.get("/acil").text  # son olaylar
    assert gonderilen == [(sorted([og, yon]), "acil")]
    assert not dashboard["tetikle"]  # okul alarm TETİKLEMEZ, yalnızca bildirir


def test_dis_olay_gecti_kapatir_ve_bitti_push(conn, yeni_kullanici, dashboard, dis_anahtar, monkeypatch):
    og = _kisi(conn, yeni_kullanici, "ogretmen", "hoca2")
    conn.execute(
        "INSERT INTO push_abonelik (kullanici_id, uc_nokta, p256dh, auth, olusturma) VALUES (?, 'https://fcm.googleapis.com/z', 'p', 'a', ?)",
        (og, zaman.simdi_str()),
    )
    conn.commit()
    gonderilen = []
    monkeypatch.setattr(push, "etkin_mi", lambda: True)
    monkeypatch.setattr(push, "gonder", lambda c, idler, tur, **kw: gonderilen.append(tur))
    with _istemci() as c:
        assert _dis(c, dis_anahtar, tur="yangin", kaynak="Panel").status_code == 200
        assert acil.aktif(conn)["tur"] == "yangin"
        assert _dis(c, dis_anahtar, tur="gecti", kaynak="Panel").status_code == 200
    assert acil.aktif(conn) is None
    assert gonderilen == ["acil", "acil_bitti"]


@pytest.mark.parametrize(
    "govde",
    [{"tur": "reklam"}, {"tur": 5}, {"tatbikat": "evet"}, {"kaynak": 7}],
)
def test_dis_olay_gecersiz_govde(conn, dis_anahtar, govde):
    with _istemci() as c:
        assert _dis(c, dis_anahtar, **govde).status_code in (400,)
        assert c.post("/acil/dis-olay", content=b"bozuk", headers=dis_anahtar).status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM acil_dis_olay").fetchone()[0] == 0


def test_okul_ve_dis_olaylar_birbirini_kapatir(conn, yeni_kullanici, dashboard, dis_anahtar, monkeypatch):
    yon = _kisi(conn, yeni_kullanici, "yonetici", "karma")
    with _istemci() as c:
        _oturum(c, conn, yon)
        assert _basla(c, tur="yangin", yer="").status_code == 303  # okul kaynaklı
        gercek = zaman.simdi
        monkeypatch.setattr(zaman, "simdi", lambda: gercek() + timedelta(seconds=5))  # dış olay daha yeni (aynı saniye eşitliği olmasın)
        assert _dis(c, dis_anahtar, tur="deprem", kaynak="Tahta 9-A").status_code == 200  # daha yeni, dış kaynaklı
        assert acil.aktif(conn)["tur"] == "deprem"  # en yeni kazanır
        assert _basla(c, tur="gecti", yer="").status_code == 303  # okuldan kapat → ikisi de kapanır
    assert acil.aktif(conn) is None


def test_okul_gecti_bitti_push_sablonu(conn, yeni_kullanici, dashboard, monkeypatch):
    a = _kisi(conn, yeni_kullanici, "ogretmen", "kapatan")
    b = _kisi(conn, yeni_kullanici, "yonetici", "duyan")
    for kid in (a, b):
        conn.execute(
            "INSERT INTO push_abonelik (kullanici_id, uc_nokta, p256dh, auth, olusturma) VALUES (?, ?, 'p', 'a', ?)",
            (kid, f"https://fcm.googleapis.com/{kid}", zaman.simdi_str()),
        )
    conn.commit()
    gonderilen = []
    monkeypatch.setattr(push, "etkin_mi", lambda: True)
    monkeypatch.setattr(push, "gonder", lambda c, idler, tur, **kw: gonderilen.append((list(idler), tur)))
    with _istemci() as c:
        _oturum(c, conn, a)
        assert _basla(c, tur="kilit", yer="").status_code == 303
        assert _basla(c, tur="gecti", yer="").status_code == 303
    assert gonderilen == [([b], "acil"), ([b], "acil_bitti")]


def test_son_olaylar_siralama_ve_sinir(conn):
    for i in range(7):
        acil.dis_olay_ekle(conn, "kilit", True, f"Kaynak {i}")
    liste = acil.son_olaylar(conn, 5)
    assert len(liste) == 5 and liste[0]["kim"] == "Kaynak 6"


def test_geri_al_v17():
    from scripts import geri_al

    assert 17 in geri_al.GERI and "acil_dis_olay" in geri_al.GERI[17]
