"""Okul kanalları şeridi: yapılandırma yoksa gizli, yalnızca güvenli https adresleri."""

import json

import pytest
from ayarlar import AYAR
from fastapi.testclient import TestClient


def _istemci():
    from app import app

    return TestClient(app)


def test_dosya_yoksa_serit_yok():
    with _istemci() as c:
        assert 'class="kanallar"' not in c.get("/giris").text


def test_adresler_giris_sayfasinda_gorunur(tmp_path, monkeypatch):
    (tmp_path / "kanallar.json").write_text(json.dumps({
        "web": "https://okul.example.k12.tr", "instagram": "https://www.instagram.com/okul",
        "youtube": "https://www.youtube.com/@okul"}), encoding="utf-8")
    with _istemci() as c:
        h = c.get("/giris").text
    assert 'class="kanallar"' in h
    for u in ("https://okul.example.k12.tr", "https://www.instagram.com/okul", "https://www.youtube.com/@okul"):
        assert f'href="{u}"' in h
    assert h.count('rel="noopener noreferrer"') >= 3 and 'target="_blank"' in h


@pytest.mark.parametrize("kotu", [
    {"web": "javascript:alert(1)"}, {"web": "http://acik.example"}, {"web": "https://a b.example"},
    {"web": 5}, {"bilinmeyen": "https://x.example"}, {"web": "https://x.example/" + "a" * 400}, [], "metin",
])
def test_guvensiz_ya_da_gecersiz_adres_gosterilmez(kotu):
    AYAR.kanallar_yolu.write_text(json.dumps(kotu), encoding="utf-8")
    with _istemci() as c:
        assert 'class="kanallar"' not in c.get("/giris").text


def test_bozuk_json_sayfayi_bozmaz():
    AYAR.kanallar_yolu.write_text("{bozuk", encoding="utf-8")
    with _istemci() as c:
        r = c.get("/giris")
    assert r.status_code == 200 and 'class="kanallar"' not in r.text


# --- WhatsApp grupları: yalnızca kendi rolüne görünür, giriş sayfasında asla ---

VELI_WA = "https://chat.whatsapp.com/VELIGRUBUTEST"
OGR_WA = "https://chat.whatsapp.com/OGRGRUBUTEST"


def _wa(monkeypatch):
    monkeypatch.setattr(AYAR, "whatsapp_veli", VELI_WA)
    monkeypatch.setattr(AYAR, "whatsapp_ogrenci", OGR_WA)


def _giris_yap(c, conn, yeni_kullanici, rol):
    import auth

    k = yeni_kullanici(conn, rol, rol.title(), rol + "x", sifre="Parola123")
    if rol == "ogrenci":
        conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (88, 'T', '9-A', ?)", (k,))
        conn.commit()
    c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, k))


@pytest.mark.parametrize("rol,yol,gorur,gormez", [
    ("veli", "/veli", VELI_WA, OGR_WA),
    ("ogrenci", "/ogrenci", OGR_WA, VELI_WA),
    ("ogretmen", "/ogretmen", None, None),
])
def test_whatsapp_gruplari_rolune_gore(conn, yeni_kullanici, monkeypatch, rol, yol, gorur, gormez):
    _wa(monkeypatch)
    with _istemci() as c:
        _giris_yap(c, conn, yeni_kullanici, rol)
        h = c.get(yol).text
    if gorur:
        assert f'href="{gorur}"' in h and gormez not in h
    else:
        assert VELI_WA not in h and OGR_WA not in h


def test_yonetici_ikisini_gorur(conn, yeni_kullanici, monkeypatch):
    _wa(monkeypatch)
    with _istemci() as c:
        _giris_yap(c, conn, yeni_kullanici, "yonetici")
        h = c.get("/yonetici").text
    assert VELI_WA in h and OGR_WA in h


def test_giris_sayfasinda_whatsapp_baglantisi_yok(monkeypatch):
    _wa(monkeypatch)
    with _istemci() as c:
        h = c.get("/giris").text
    assert "chat.whatsapp.com" not in h


def test_whatsapp_yalniz_whatsapp_adresi_kabul(conn, yeni_kullanici, monkeypatch):
    monkeypatch.setattr(AYAR, "whatsapp_veli", "https://kotu.example/chat.whatsapp.com/x")
    with _istemci() as c:
        _giris_yap(c, conn, yeni_kullanici, "veli")
        assert "kotu.example" not in c.get("/veli").text
