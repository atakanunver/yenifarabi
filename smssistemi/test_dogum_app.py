"""Doğum günleri web route ve SSO entegrasyonu birim testleri."""

import pytest
from unittest.mock import MagicMock
from fastapi import Request
from fastapi.responses import RedirectResponse

import app
import auth
import db
import dogum_mantik


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_yolu = tmp_path / "test_smssistemi.db"
    yedek_dizini = tmp_path / "yedek"
    monkeypatch.setattr(db, "DB_YOLU", db_yolu)
    monkeypatch.setattr(db, "YEDEK_DIZINI", yedek_dizini)
    db.semayi_kur()
    conn = db.baglanti()
    yield conn
    conn.close()


def _sahte_oturum_request(conn, token=None):
    if token is None:
        token = auth.oturum_olustur(conn)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"cookie", f"{auth.COOKIE_ADI}={token}".encode())],
    }
    return Request(scope)


@pytest.mark.anyio
async def test_sso_giris_hedef_yonlendirme(test_db, monkeypatch):
    monkeypatch.setattr(auth, "sso_dogrula", lambda t, s: True)
    req = Request({"type": "http", "method": "GET", "path": "/sso"})

    resp = await app.sso_giris(req, t="123", s="abc", hedef="/dogum-gunleri")
    assert isinstance(resp, RedirectResponse)
    assert resp.headers["location"] == "/dogum-gunleri"
    assert auth.COOKIE_ADI in resp.headers.get("set-cookie", "")


@pytest.mark.anyio
async def test_sso_giris_guvensiz_hedef_guvenlige_alinir(test_db, monkeypatch):
    monkeypatch.setattr(auth, "sso_dogrula", lambda t, s: True)
    req = Request({"type": "http", "method": "GET", "path": "/sso"})

    # Açık yönlendirme saldırısı engellenmeli (//evil.com veya http://...)
    resp = await app.sso_giris(req, t="123", s="abc", hedef="//evil.com")
    assert resp.headers["location"] == "/"


@pytest.mark.anyio
async def test_dogum_ayarlar_kaydet(test_db):
    req = _sahte_oturum_request(test_db)
    resp = await app.dogum_ayarlar_kaydet(
        req,
        sms_otomatik="1",
        dogum_sms_sablonu="Yeni şablon {isim}",
    )
    assert resp.headers["location"] == "/dogum-gunleri?mesaj=ayarlar_kaydedildi"
    assert db.ayar_oku(test_db, "sms_otomatik") == "1"
    assert db.ayar_oku(test_db, "dogum_sms_sablonu") == "Yeni şablon {isim}"


@pytest.mark.anyio
async def test_dogum_kisi_tarih_kaydet(test_db):
    s9a = db.sinif_ekle(test_db, "9-A")
    k_id = db.kisi_ekle(test_db, "Ali Yılmaz", None, s9a, "ogrenci")

    req = _sahte_oturum_request(test_db)
    resp = await app.dogum_kisi_tarih_kaydet(req, kisi_id=k_id, dogum_tarihi="2009-03-15")
    assert resp.headers["location"] == "/dogum-gunleri?mesaj=tarih_kaydedildi"

    k = test_db.execute("SELECT dogum_tarihi FROM kisiler WHERE id = ?", (k_id,)).fetchone()
    assert k["dogum_tarihi"] == "2009-03-15"


@pytest.mark.anyio
async def test_dogum_gunleri_sayfa_durum_filtresi(test_db):
    s9a = db.sinif_ekle(test_db, "9-A")
    k1 = db.kisi_ekle(test_db, "Öğrenci 1", None, s9a, "ogrenci")
    k2 = db.kisi_ekle(test_db, "Öğrenci 2", None, s9a, "ogrenci")
    db.kisi_dogum_tarihi_guncelle(test_db, k1, "2009-01-01")

    req = _sahte_oturum_request(test_db)

    # Durum: eksik
    resp_eksik = await app.dogum_gunleri(req, durum="eksik")
    assert len(resp_eksik.context["kisiler"]) == 1
    assert resp_eksik.context["kisiler"][0]["id"] == k2

    # Durum: tanimli
    resp_tanimli = await app.dogum_gunleri(req, durum="tanimli")
    assert len(resp_tanimli.context["kisiler"]) == 1
    assert resp_tanimli.context["kisiler"][0]["id"] == k1
