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


def _ogrenci_ve_veli(conn, sinif="9-A"):
    sinif_id = next(s["id"] for s in db.siniflar_listele(conn) if s["ad"] == sinif)
    ogr_id = db.kisi_ekle(conn, "Murat Polat", None, sinif_id, "ogrenci")
    db.kisi_ekle(conn, "Zeynep Polat", "05321110099", sinif_id, "veli", ogrenci_kisi_id=ogr_id, veli_rol="Anne")


@pytest.mark.anyio
async def test_otomasyon_sayfa_kurallari_ve_rol_rozetini_gosterir(test_db, pano, monkeypatch):
    from datetime import date

    monkeypatch.setattr(otomasyon, "bugun_istanbul", lambda: date.fromisoformat(TARIH))
    pano("9-A", 1, "alindi", yok=["Murat Polat"])
    _ogrenci_ve_veli(test_db)
    govde = (await app.otomasyon_sayfa(_sahte_oturum_request(test_db), kural=1)).body.decode("utf-8")
    assert "Sabah 1. ders" in govde and "Öğleden sonra 6. ders" in govde
    assert "/otomasyon/kural/1/sil" in govde and "/otomasyon/kural/ekle" in govde
    # rehberde 'Anne' büyük harfle; eskiden her zaman "Veli" rozeti çıkıyordu
    assert '<span class="rozet rozet-yesil">Anne</span>' in govde
    # kullanıcı metni JS'e gömülmez (onay metni data-onay'da)
    assert "onsubmit" not in govde


@pytest.mark.anyio
async def test_kural_ekle_guncelle_durum_sil(test_db):
    req = _sahte_oturum_request(test_db)
    resp = await app.otomasyon_kural_ekle(req, ad="", saat="10:30", ders_no="3", sablon="Sayın {isim}")
    assert resp.status_code == 303
    kid = next(k["id"] for k in otomasyon.kurallar(test_db) if k["ders_no"] == 3)
    assert resp.headers["location"] == f"/otomasyon?kural={kid}&mesaj=eklendi"
    assert otomasyon.kural_getir(test_db, kid)["aktif"] is False

    resp = await app.otomasyon_kural_guncelle(req, kid, ad="Üçüncü", saat="10:45", ders_no="3", sablon="Yeni {isim}")
    assert resp.headers["location"] == f"/otomasyon?kural={kid}&mesaj=guncellendi"
    k = otomasyon.kural_getir(test_db, kid)
    assert (k["ad"], k["saat"], k["sablon"]) == ("Üçüncü", "10:45", "Yeni {isim}")

    await app.otomasyon_kural_durum(req, kid, aktif="1")
    assert otomasyon.kural_getir(test_db, kid)["aktif"] is True

    resp = await app.otomasyon_kural_sil(req, kid)
    assert resp.headers["location"] == "/otomasyon?mesaj=silindi"
    assert otomasyon.kural_getir(test_db, kid) is None


@pytest.mark.anyio
async def test_kural_ekle_hatali_girdi_400_ve_formu_korur(test_db, pano):
    req = _sahte_oturum_request(test_db)
    resp = await app.otomasyon_kural_ekle(req, ad="Deneme", saat="10:30", ders_no="1", sablon="x")
    assert resp.status_code == 400
    govde = resp.body.decode("utf-8")
    assert "1. ders için zaten bir otomasyon var" in govde
    assert 'value="Deneme"' in govde
    assert len(otomasyon.kurallar(test_db)) == 2


@pytest.mark.anyio
async def test_kural_uclari_oturumsuz_401_ve_olmayan_kural_404(test_db):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        await app.otomasyon_kural_sil(_oturumsuz_request(), 1)
    assert e.value.status_code == 401
    assert otomasyon.kural_getir(test_db, 1) is not None
    req = _sahte_oturum_request(test_db)
    for cagri in (
        app.otomasyon_kural_sil(req, 999),
        app.otomasyon_kural_durum(req, 999, aktif="1"),
        app.otomasyon_manuel_calistir(req, 999),
    ):
        with pytest.raises(HTTPException) as e:
            await cagri
        assert e.value.status_code == 404


@pytest.mark.anyio
async def test_otomasyon_manuel_calistir(test_db, pano, monkeypatch):
    pano("9-A", 1, "alindi", yok=["Murat Polat"])
    _ogrenci_ve_veli(test_db)

    def mock_toplu_gonder(ayarlar, kisiler, callback, durdur_bayragi, bekleme_sn):
        for isim, tel, msg in kisiler:
            callback(isim, tel, msg, "gonderildi", None)

    monkeypatch.setattr(otomasyon.sms_gonderici, "toplu_gonder", mock_toplu_gonder)
    resp = await app.otomasyon_manuel_calistir(_sahte_oturum_request(test_db), 1)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/otomasyon?kural=1&mesaj=gonderildi"


@pytest.mark.anyio
async def test_otomasyon_manuel_calistir_baglanti_hatasinda_basarisiz_mesaji_doner(test_db, pano, monkeypatch):
    """2026-09-28 regresyonu: otomasyon_calistir 'basarisiz' dönerse
    route bunu ayrı bir mesajla yönlendirmeli (aksi halde manuel sayfa
    hiçbir SMS gitmemişken bile 'başarıyla gönderildi' gösteriyordu)."""
    from datetime import date

    monkeypatch.setattr(otomasyon, "bugun_istanbul", lambda: date.fromisoformat(TARIH))
    pano("9-A", 1, "alindi", yok=["Murat Polat"])
    _ogrenci_ve_veli(test_db)

    def mock_toplu_gonder(ayarlar, kisiler, callback, durdur_bayragi, bekleme_sn):
        for isim, tel, msg in kisiler:
            callback(isim, tel, msg, "hata", "BAĞLANTI HATASI: proxy erişilemedi")

    monkeypatch.setattr(otomasyon.sms_gonderici, "toplu_gonder", mock_toplu_gonder)
    resp = await app.otomasyon_manuel_calistir(_sahte_oturum_request(test_db), 1)
    assert resp.headers["location"] == "/otomasyon?kural=1&mesaj=basarisiz"
    assert otomasyon.ders_son_tarih(test_db, 1) == ""


@pytest.mark.anyio
async def test_otomasyon_manuel_calistir_ogle(test_db, pano, monkeypatch):
    from datetime import date

    monkeypatch.setattr(otomasyon, "bugun_istanbul", lambda: date.fromisoformat(TARIH))
    pano("9-A", 6, "alindi", yok=["Murat Polat"])
    _ogrenci_ve_veli(test_db)
    gonderilenler = []

    def mock_toplu_gonder(ayarlar, kisiler, callback, durdur_bayragi, bekleme_sn):
        for isim, tel, msg in kisiler:
            gonderilenler.append(msg)
            callback(isim, tel, msg, "gonderildi", None)

    monkeypatch.setattr(otomasyon.sms_gonderici, "toplu_gonder", mock_toplu_gonder)
    resp = await app.otomasyon_manuel_calistir(_sahte_oturum_request(test_db), 2)
    assert resp.headers["location"] == "/otomasyon?kural=2&mesaj=gonderildi"
    assert len(gonderilenler) == 1 and "öğleden sonra" in gonderilenler[0]
    assert otomasyon.ders_son_tarih(test_db, 6) == TARIH


@pytest.mark.anyio
async def test_api_otomasyon_durum(test_db):
    otomasyon.kural_aktif_yaz(test_db, 1, True)
    resp = await app.api_otomasyon_durum(_sahte_oturum_request(test_db))
    assert resp.status_code == 200
    kurallar = {k["id"]: k for k in json.loads(resp.body)["kurallar"]}
    assert kurallar[1]["aktif"] is True and kurallar[1]["ders_no"] == 1
    assert kurallar[2]["aktif"] is False and kurallar[2]["saat"] == "14:00"
    assert "Sayın {isim}" in kurallar[1]["sablon"]


@pytest.mark.anyio
async def test_manuel_calistir_event_loopu_bloklamaz(test_db, pano, monkeypatch):
    """Gönderim sürerken event loop başka işleri yürütebilmeli (2026-09-25
    düzeltmesi: toplu_gonder artık asyncio.to_thread içinde)."""
    import asyncio
    import time
    from datetime import date

    monkeypatch.setattr(otomasyon, "bugun_istanbul", lambda: date.fromisoformat(TARIH))
    pano("9-A", 1, "alindi", yok=["Murat Polat"])
    _ogrenci_ve_veli(test_db)

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
    resp = await app.otomasyon_manuel_calistir(_sahte_oturum_request(test_db), 1)
    gorev.cancel()
    assert resp.headers["location"] == "/otomasyon?kural=1&mesaj=gonderildi"
    assert tikler >= 5  # bloklansaydı gönderim boyunca 0 kalırdı


@pytest.mark.anyio
async def test_manuel_calistir_zaten_calisiyorsa_gondermez(test_db, monkeypatch):
    gonderildi = []
    monkeypatch.setattr(
        otomasyon.sms_gonderici, "toplu_gonder", lambda *a, **k: gonderildi.append(1)
    )
    assert otomasyon._CALISMA_KILIDI.acquire(blocking=False)
    try:
        resp = await app.otomasyon_manuel_calistir(_sahte_oturum_request(test_db), 1)
    finally:
        otomasyon._CALISMA_KILIDI.release()
    assert resp.headers["location"] == "/otomasyon?kural=1&mesaj=calisiyor"
    assert gonderildi == []
