"""PWA: manifest, iOS meta etiketleri, ikonlar, 'Ana Ekrana Ekle' butonunun yerleşimi."""

import pytest
from ayarlar import KOK
from fastapi.testclient import TestClient
from kaynaklar import kazanim

BUTON = 'id="ana-ekran"'


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setattr(kazanim, "form_sonuclari", lambda okul_no: [])
    from app import app

    with TestClient(app) as c:
        yield c


def _giris(c, kadi, sifre):
    assert (
        c.post(
            "/giris",
            data={"kullanici_adi": kadi, "sifre": sifre},
            follow_redirects=False,
        ).status_code
        == 303
    )


def test_manifest_alanlari(istemci):
    m = istemci.get("/manifest.webmanifest").json()
    assert m["name"] == "Şehit Murat Ustaoğlu Anadolu Lisesi - DijitalOkul"
    assert m["short_name"] == "DijitalOkul"
    assert m["lang"] == "tr-TR"
    assert m["display"] == "standalone"
    assert m["start_url"] == "/" and m["scope"] == "/" and m["id"] == "/"
    assert m["theme_color"] == "#4b1f6f"
    boyutlar = {(i["sizes"], i.get("purpose", "any")) for i in m["icons"]}
    assert {
        ("192x192", "any"),
        ("512x512", "any"),
        ("192x192", "maskable"),
        ("512x512", "maskable"),
    } <= boyutlar
    for i in m["icons"]:
        assert (KOK / i["src"].lstrip("/")).exists(), i["src"]
        assert istemci.get(i["src"]).status_code == 200


def test_ios_ve_tema_etiketleri(istemci):
    h = istemci.get("/giris").text
    assert '<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">' in h
    assert '<meta name="apple-mobile-web-app-capable" content="yes">' in h
    assert '<meta name="mobile-web-app-capable" content="yes">' in h
    assert '<meta name="apple-mobile-web-app-title" content="DijitalOkul">' in h
    assert '<meta name="theme-color" content="#4b1f6f">' in h
    assert istemci.get("/static/apple-touch-icon.png").status_code == 200


def test_buton_giris_sayfalarinda(istemci):
    for yol in ("/giris", "/veli-giris"):
        h = istemci.get(yol).text
        assert BUTON in h and "📲 Ana Ekrana Ekle" in h and "/static/kurulum.js" in h, (
            yol
        )


@pytest.mark.parametrize(
    "kadi,sifre,ana",
    [
        ("101", "ali-sifre", "/ogrenci"),
        ("hoca", "hoca-sifre", "/ogretmen"),
        ("mudur", "mudur-sifre", "/yonetici"),
    ],
)
def test_buton_rol_ana_sayfalarinda_var_alt_sayfalarda_yok(
    istemci, ornek, kadi, sifre, ana
):
    _giris(istemci, kadi, sifre)
    assert BUTON in istemci.get(ana).text
    assert BUTON not in istemci.get("/duyurular").text


def test_buton_veli_ana_sayfasinda(istemci, ornek, conn):
    import auth

    istemci.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, ornek["veli1"]))
    assert BUTON in istemci.get("/veli").text
    assert BUTON not in istemci.get("/veli/devamsizlik").text


def test_buton_varsayilan_gizli_ve_erisilebilir(istemci):
    h = istemci.get("/giris").text
    parca = h[h.index(BUTON) - 200 : h.index(BUTON) + 400]
    assert "hidden" in parca  # JS yüklenmeden / kurulu uygulamada görünmez
    assert 'type="button"' in parca


def test_html_sayfalari_saklanmaz(istemci, ornek):
    assert istemci.get("/giris").headers["cache-control"] == "no-store"
    _giris(istemci, "101", "ali-sifre")
    assert istemci.get("/ogrenci").headers["cache-control"] == "no-store"


def test_service_worker_tek_ve_guncel(istemci):
    sw = istemci.get("/sw.js")
    assert sw.status_code == 200 and sw.headers["cache-control"] == "no-cache"
    assert "/static/kurulum.js" in sw.text and "/static/apple-touch-icon.png" in sw.text
    assert len(list((KOK / "static").glob("*sw*.js"))) == 1
