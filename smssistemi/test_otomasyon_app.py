"""Otomasyon web route birim testleri."""

import json
import sqlite3

import pytest
from fastapi import Request

import app
import auth
import db
import otomasyon
import yoklama_kaynak

TARIH = "2026-09-25"

_PANO_SEMA = """
CREATE TABLE yoklama_onbellek (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarih TEXT NOT NULL,
    sinif TEXT NOT NULL,
    ders_no INTEGER NOT NULL,
    durum TEXT NOT NULL,
    yok_isimleri TEXT,
    izinli_isimleri TEXT,
    kaynak_tahta TEXT,
    kaydedilme_saati TEXT,
    UNIQUE(tarih, sinif, ders_no)
);
"""


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "test_otomasyon_app.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    db.semayi_kur()
    conn = db.baglanti()
    yield conn
    conn.close()


@pytest.fixture
def pano(tmp_path, monkeypatch):
    yol = tmp_path / "yoklama_pano.db"
    conn = sqlite3.connect(yol)
    conn.executescript(_PANO_SEMA)
    conn.commit()
    monkeypatch.setattr(yoklama_kaynak, "YOKLAMA_DB_YOLU", yol)

    def ekle(sinif, ders_no, durum="alindi", yok=(), izinli=(), tarih=TARIH):
        conn.execute(
            "INSERT INTO yoklama_onbellek (tarih, sinif, ders_no, durum, "
            "yok_isimleri, izinli_isimleri) VALUES (?, ?, ?, ?, ?, ?)",
            (tarih, sinif, ders_no, durum, json.dumps(list(yok)), json.dumps(list(izinli))),
        )
        conn.commit()

    yield ekle
    conn.close()


def _sahte_oturum_request(conn, token=None, path="/otomasyon"):
    if token is None:
        token = auth.oturum_olustur(conn)
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [(b"cookie", f"{auth.COOKIE_ADI}={token}".encode())],
    }
    return Request(scope)


def _oturumsuz_request(path="/otomasyon"):
    return Request({"type": "http", "method": "GET", "path": path, "headers": []})


@pytest.mark.anyio
async def test_oturumsuz_otomasyon_girise_yonlendirir(test_db):
    yanit = await app.otomasyon_sayfa(_oturumsuz_request())
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/giris"


@pytest.mark.anyio
async def test_otomasyon_sayfa_acilir(test_db, pano):
    req = _sahte_oturum_request(test_db)
    resp = await app.otomasyon_sayfa(req)
    assert resp.status_code == 200
    assert "SMS Otomasyonu" in resp.body.decode("utf-8")


@pytest.mark.anyio
async def test_otomasyon_durum_degistir(test_db):
    req = _sahte_oturum_request(test_db)
    resp = await app.otomasyon_durum_degistir(req, aktif="1")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/otomasyon?mesaj=durum_degisti"
    assert db.ayar_oku(test_db, otomasyon.AYAR_AKTIF) == "1"

    resp2 = await app.otomasyon_durum_degistir(req, aktif="0")
    assert resp2.status_code == 303
    assert db.ayar_oku(test_db, otomasyon.AYAR_AKTIF) == "0"


@pytest.mark.anyio
async def test_otomasyon_ayarlar_kaydet(test_db):
    req = _sahte_oturum_request(test_db)
    yeni_sablon = "Özel şablon: {isim}, {ogrenci_adi} derse gelmedi."
    resp = await app.otomasyon_ayarlar_kaydet(req, sablon=yeni_sablon)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/otomasyon?mesaj=ayarlar_kaydedildi"
    assert db.ayar_oku(test_db, otomasyon.AYAR_SABLON) == yeni_sablon


@pytest.mark.anyio
async def test_otomasyon_manuel_calistir(test_db, pano, monkeypatch):
    pano("9-A", 1, "alindi", yok=["Murat Polat"])
    sinif_9a = [s["id"] for s in db.siniflar_listele(test_db) if s["ad"] == "9-A"][0]
    ogr_id = db.kisi_ekle(test_db, "Murat Polat", None, sinif_9a, "ogrenci")
    db.kisi_ekle(test_db, "Zeynep Polat", "05321110099", sinif_9a, "veli", ogrenci_kisi_id=ogr_id)

    gonderilenler = []

    def mock_toplu_gonder(ayarlar, kisiler, callback, durdur_bayragi, bekleme_sn):
        for isim, tel, msg in kisiler:
            gonderilenler.append((isim, tel, msg))
            callback(isim, tel, msg, "gonderildi", None)

    monkeypatch.setattr(otomasyon.sms_gonderici, "toplu_gonder", mock_toplu_gonder)

    req = _sahte_oturum_request(test_db)
    resp = await app.otomasyon_manuel_calistir(req)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/otomasyon?mesaj=gonderildi"


@pytest.mark.anyio
async def test_otomasyon_manuel_calistir_baglanti_hatasinda_basarisiz_mesaji_doner(test_db, pano, monkeypatch):
    """2026-09-28 regresyonu: otomasyon_calistir 'basarisiz' dönerse
    route bunu ayrı bir mesajla yönlendirmeli (aksi halde manuel sayfa
    hiçbir SMS gitmemişken bile 'başarıyla gönderildi' gösteriyordu)."""
    from datetime import date

    # otomasyon_calistir tarihi bugun_istanbul()'dan alır; pano satırı TARIH'e
    # yazıldığı için "bugün" sabitlenmezse test yalnızca TARIH günü geçer.
    monkeypatch.setattr(otomasyon, "bugun_istanbul", lambda: date.fromisoformat(TARIH))
    pano("9-A", 1, "alindi", yok=["Murat Polat"])
    sinif_9a = [s["id"] for s in db.siniflar_listele(test_db) if s["ad"] == "9-A"][0]
    ogr_id = db.kisi_ekle(test_db, "Murat Polat", None, sinif_9a, "ogrenci")
    db.kisi_ekle(test_db, "Zeynep Polat", "05321110099", sinif_9a, "veli", ogrenci_kisi_id=ogr_id)

    def mock_toplu_gonder(ayarlar, kisiler, callback, durdur_bayragi, bekleme_sn):
        for isim, tel, msg in kisiler:
            callback(isim, tel, msg, "hata", "BAĞLANTI HATASI: proxy erişilemedi")

    monkeypatch.setattr(otomasyon.sms_gonderici, "toplu_gonder", mock_toplu_gonder)

    req = _sahte_oturum_request(test_db)
    resp = await app.otomasyon_manuel_calistir(req)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/otomasyon?mesaj=basarisiz"
    assert db.ayar_oku(test_db, otomasyon.AYAR_SON_TARIH) == ""


@pytest.mark.anyio
async def test_api_otomasyon_durum(test_db):
    req = _sahte_oturum_request(test_db)
    db.ayar_yaz(test_db, otomasyon.AYAR_AKTIF, "1")
    resp = await app.api_otomasyon_durum(req)
    assert resp.status_code == 200
    veri = json.loads(resp.body)
    assert veri["aktif"] == "1"
    assert "Sayın {isim}" in veri["sablon"]


@pytest.mark.anyio
async def test_manuel_calistir_event_loopu_bloklamaz(test_db, pano, monkeypatch):
    """Gönderim sürerken event loop başka işleri yürütebilmeli (2026-09-25
    düzeltmesi: toplu_gonder artık asyncio.to_thread içinde)."""
    import asyncio
    import time
    from datetime import date

    # otomasyon_calistir tarihi bugun_istanbul()'dan alır; pano satırı TARIH'e
    # yazıldığı için "bugün" sabitlenmezse test yalnızca TARIH günü geçer.
    monkeypatch.setattr(otomasyon, "bugun_istanbul", lambda: date.fromisoformat(TARIH))
    pano("9-A", 1, "alindi", yok=["Murat Polat"])
    sinif_9a = [s["id"] for s in db.siniflar_listele(test_db) if s["ad"] == "9-A"][0]
    ogr_id = db.kisi_ekle(test_db, "Murat Polat", None, sinif_9a, "ogrenci")
    db.kisi_ekle(test_db, "Zeynep Polat", "05321110099", sinif_9a, "veli", ogrenci_kisi_id=ogr_id)

    def yavas_toplu_gonder(ayarlar, kisiler, callback, durdur_bayragi, bekleme_sn):
        time.sleep(0.5)  # gerçek gönderimdeki time.sleep'in yerine
        for isim, tel, msg in kisiler:
            callback(isim, tel, msg, "gonderildi", None)

    monkeypatch.setattr(otomasyon.sms_gonderici, "toplu_gonder", yavas_toplu_gonder)

    tikler = 0

    async def sayac():
        nonlocal tikler
        while True:
            await asyncio.sleep(0.05)
            tikler += 1

    gorev = asyncio.create_task(sayac())
    resp = await app.otomasyon_manuel_calistir(_sahte_oturum_request(test_db))
    gorev.cancel()
    assert resp.headers["location"] == "/otomasyon?mesaj=gonderildi"
    assert tikler >= 5  # bloklansaydı gönderim boyunca 0 kalırdı


@pytest.mark.anyio
async def test_manuel_calistir_zaten_calisiyorsa_gondermez(test_db, monkeypatch):
    gonderildi = []
    monkeypatch.setattr(
        otomasyon.sms_gonderici, "toplu_gonder", lambda *a, **k: gonderildi.append(1)
    )
    assert otomasyon._CALISMA_KILIDI.acquire(blocking=False)
    try:
        resp = await app.otomasyon_manuel_calistir(_sahte_oturum_request(test_db))
    finally:
        otomasyon._CALISMA_KILIDI.release()
    assert resp.headers["location"] == "/otomasyon?mesaj=calisiyor"
    assert gonderildi == []
