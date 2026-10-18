"""ogrenci_durum.py — geçici docx (SAHTE öğrenciler) ile; gerçek mudur/ klasörüne dokunmaz."""

import docx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
import idari_yukle
import ogrenci_durum as od

ANAHTAR = "webui-test-anahtari"
B = {"X-Farabi-WebUI-Key": ANAHTAR}
SATIRLAR = [
    ("9/A", "11", "Ayşe Örnek", "-", "-", "AYRI"),
    ("9/A", "12", "Ali Deneme", "VAR", "-", "-"),
    ("10-A", "21", "Veli Sahte", "-", "ASTIM", "ÖLÜ"),
    ("12/B", "31", "Zeynep Test", "-", "-", "TEYZESİ VE EŞİ İLE KALIYOR"),
    ("12/B", "32", "Can Örnek", "--", "--", "--"),
]


def _belge(klasor, ad="bilgi fomu detay20262027.docx", satirlar=SATIRLAR):
    d = docx.Document()
    t = d.add_table(rows=1, cols=6)
    for c, b in zip(t.rows[0].cells, ["SINIF", "OKUL NO", "AD SOYAD", "MADDİ YETERSİZLİK", "HASTALIK", "ANA BABA AYRI / ÖLÜ"]):
        c.text = b
    for s in satirlar:
        for c, v in zip(t.add_row().cells, s):
            c.text = v
    d.save(klasor / ad)


@pytest.fixture
def ist(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "webui_anahtari", lambda: ANAHTAR)
    monkeypatch.setattr(idari_yukle, "KLASOR", tmp_path)
    od._ONBELLEK.clear()
    _belge(tmp_path)
    app = FastAPI()
    app.include_router(od.router)
    return TestClient(app), tmp_path


def _getir(c, **g):
    return c.post("/api/webui/ogrenci-durum/getir", headers=B, json=g).json()


def test_anahtarsiz_401(ist):
    assert ist[0].post("/api/webui/ogrenci-durum/getir", json={}).status_code == 401


def test_ana_baba_ayri_olu_ve_diger_metin_gelir_tire_gelmez(ist):
    y = _getir(ist[0], tur="ana_baba")
    assert y["durum"] == "ok" and y["toplam_kayit"] == 5
    assert [o["ad_soyad"] for o in y["ogrenciler"]] == ["Ayşe Örnek", "Veli Sahte", "Zeynep Test"]
    assert y["ogrenciler"][0]["sinif"] == "9-A" and y["ogrenciler"][2]["sinif"] == "12-B"


def test_sinif_filtresi_bicimden_bagimsiz(ist):
    for yazim in ("9-A", "9/a", "9 A", "9A"):
        assert [o["okul_no"] for o in _getir(ist[0], tur="hepsi", sinif=yazim)["ogrenciler"]] == ["11", "12"]


def test_maddi_hastalik_hepsi(ist):
    assert [o["ad_soyad"] for o in _getir(ist[0], tur="maddi")["ogrenciler"]] == ["Ali Deneme"]
    assert [o["ad_soyad"] for o in _getir(ist[0], tur="hastalik")["ogrenciler"]] == ["Veli Sahte"]
    assert len(_getir(ist[0], tur="hepsi")["ogrenciler"]) == 4  # Can Örnek (hepsi '--') hariç


def test_en_yeni_dosya_secilir_ve_degisince_yeniden_okunur(ist):
    c, klasor = ist
    import os
    import time

    _getir(c, tur="ana_baba")
    _belge(klasor, "bilgi fomu detay20272028.docx", [("9/A", "1", "Yeni Yıl", "-", "-", "AYRI")])
    os.utime(klasor / "bilgi fomu detay20272028.docx", (time.time() + 5, time.time() + 5))
    y = _getir(c, tur="ana_baba")
    assert y["kaynak"] == "bilgi fomu detay20272028.docx" and [o["ad_soyad"] for o in y["ogrenciler"]] == ["Yeni Yıl"]


def test_belge_yoksa_yok_der(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "webui_anahtari", lambda: ANAHTAR)
    monkeypatch.setattr(idari_yukle, "KLASOR", tmp_path)
    app = FastAPI()
    app.include_router(od.router)
    assert _getir(TestClient(app), tur="ana_baba")["durum"] == "yok"


def test_ad_loga_yazilmaz(ist, caplog):
    with caplog.at_level("INFO", logger="farabi.ogrenci_durum"):
        _getir(ist[0], tur="ana_baba")
    assert "Ayşe" not in " ".join(r.getMessage() for r in caplog.records)
