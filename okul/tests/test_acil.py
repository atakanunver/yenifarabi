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
