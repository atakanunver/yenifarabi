"""hafiza.py — saf mantık + GERÇEK Postgres/pgvector (geçici tabloda; üretim atos_hafiza'ya dokunmaz).
Postgres'e bağlanılamazsa entegrasyon testleri atlanır."""

import hashlib
import re
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
import db
import hafiza as h
import webui

ANAHTAR = "webui-test-anahtari"
B = {"X-Farabi-WebUI-Key": ANAHTAR}


class KelimeEmbed:
    """Deterministik: kelime torbası → 1024-d normalize vektör (ortak kelime = benzerlik)."""

    def __init__(self, patlat=False):
        self.patlat = patlat

    def encode(self, metin, normalize_embeddings=True):
        if self.patlat:
            raise RuntimeError("gömme kapalı")
        v = np.zeros(1024, dtype=np.float32)
        for k in re.findall(r"\w+", metin.lower()):
            v[int(hashlib.md5(k.encode()).hexdigest(), 16) % 1024] += 1
        return v / (np.linalg.norm(v) or 1)


def test_kirp_butce():
    k = [{"baslik": "a" * 10, "icerik": "b" * 100} for _ in range(5)]
    assert len(h._kirp(k, 300)) == 2  # 140 + 140 = 280 ≤ 300, üçüncü sığmaz
    assert h._kirp([], 300) == []


def _pg():
    try:
        db.baslat("127.0.0.1", "farabi", "farabi", 1, 1)
        with db.baglanti() as c, c.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001
        db.kapat()
        return False


@pytest.fixture
def ist(monkeypatch):
    if not _pg():
        pytest.skip("Postgres/pgvector yok")
    monkeypatch.setattr(auth, "webui_anahtari", lambda: ANAHTAR)
    monkeypatch.setattr(h, "TABLO", "atos_hafiza_test")
    ddl = Path(h.__file__).with_name("schema_hafiza.sql").read_text(encoding="utf-8")
    govde = re.search(r"CREATE TABLE IF NOT EXISTS atos_hafiza \((.*?)\n\);", ddl, re.DOTALL).group(1)
    govde = govde.replace("REFERENCES atos_hafiza(id)", "")
    with db.baglanti() as c, c.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE atos_hafiza_test ({govde})")
        c.commit()
    monkeypatch.setattr(webui, "MOTOR", type("M", (), {"embed_model": KelimeEmbed()})())
    app = FastAPI()
    app.include_router(h.router)
    yield TestClient(app)
    db.kapat()


def _k(c, baslik, icerik, **ek):
    return c.post("/api/webui/hafiza/kaydet", headers=B, json={"baslik": baslik, "icerik": icerik, **ek}).json()


def test_anahtarsiz_401(ist):
    assert ist.post("/api/webui/hafiza/ara", json={"sorgu": "x"}).status_code == 401


def test_once_taslak_sonra_yazar(ist):
    t = _k(ist, "Veli toplantısı", "Veli toplantısı 22 Ekim saat 14:00")
    assert t["durum"] == "taslak" and t["onizleme"]["baslik"] == "Veli toplantısı"
    assert ist.post("/api/webui/hafiza/ara", headers=B, json={}).json()["kayitlar"] == []  # taslak yazmadı
    y = _k(ist, "Veli toplantısı", "Veli toplantısı 22 Ekim saat 14:00", onaylandi=True)
    assert y["durum"] == "kaydedildi" and y["embedding"] is True


def test_kisisel_veri_reddedilmez(ist):
    r = _k(ist, "Veli iletişim", "Örnek veli telefonu 0555 000 00 00, TC 10000000146", onaylandi=True)
    assert r["durum"] == "kaydedildi"


def test_ayni_bilgi_guncellenir_yeni_acilmaz(ist):
    _k(ist, "Nöbet düzeni", "Nöbet çizelgesi her pazartesi güncellenir", onaylandi=True)
    r = _k(ist, "Nöbet düzeni", "Nöbet çizelgesi her pazartesi güncellenir", onaylandi=True, kaynak="Yazı 12")
    assert r["durum"] == "guncellendi"
    assert len(ist.post("/api/webui/hafiza/ara", headers=B, json={}).json()["kayitlar"]) == 1


def test_ara_ilgiliyi_bulur_ilgisizi_getirmez(ist):
    _k(ist, "Nöbet düzeni", "Nöbet çizelgesi her pazartesi güncellenir", onaylandi=True)
    _k(ist, "Kermes", "Kermes cumartesi okul bahçesinde", onaylandi=True)
    r = ist.post("/api/webui/hafiza/ara", headers=B, json={"sorgu": "nöbet çizelgesi ne zaman güncellenir"}).json()
    assert [k["baslik"] for k in r["kayitlar"]] == ["Nöbet düzeni"]


def test_suresi_dolan_gelmez(ist):
    dun = (h.bugun() - timedelta(days=2)).isoformat()
    _k(ist, "Eski duyuru", "Eski duyuru metni kermes", onaylandi=True, son_gecerlilik=dun)
    assert ist.post("/api/webui/hafiza/ara", headers=B, json={"sorgu": "eski duyuru kermes"}).json()["kayitlar"] == []
    assert ist.post("/api/webui/hafiza/ara", headers=B, json={}).json()["kayitlar"] == []


def test_unut_arsivler(ist):
    i = _k(ist, "Geçici", "Geçici not", onaylandi=True)["id"]
    assert ist.post("/api/webui/hafiza/unut", headers=B, json={"id": i}).json()["durum"] == "unutuldu"
    assert ist.post("/api/webui/hafiza/unut", headers=B, json={"id": i}).json()["durum"] == "bulunamadi"
    assert ist.post("/api/webui/hafiza/ara", headers=B, json={}).json()["kayitlar"] == []


def test_getir_sabit_ve_ilgili(ist):
    _k(ist, "Eğitim yılı", "Eğitim öğretim yılı 1 Eylül'de başlar 30 Haziran'da biter", onaylandi=True, sabit=True)
    _k(ist, "Nöbet düzeni", "Nöbet çizelgesi her pazartesi güncellenir", onaylandi=True)
    g = ist.post("/api/webui/hafiza/getir", headers=B, json={"soru": "nöbet çizelgesi ne zaman güncellenir"}).json()
    assert g["durum"] == "ok" and [k["baslik"] for k in g["sabit"]] == ["Eğitim yılı"]
    assert [k["baslik"] for k in g["kayitlar"]] == ["Nöbet düzeni"]


def test_gomme_kapaliyken_tam_metin(ist, monkeypatch):
    _k(ist, "Nöbet düzeni", "Nöbet çizelgesi her pazartesi güncellenir", onaylandi=True)
    monkeypatch.setattr(webui, "MOTOR", type("M", (), {"embed_model": KelimeEmbed(patlat=True)})())
    r = ist.post("/api/webui/hafiza/ara", headers=B, json={"sorgu": "çizelgesi"}).json()
    assert [k["baslik"] for k in r["kayitlar"]] == ["Nöbet düzeni"]
    y = _k(ist, "Embeddingsiz", "gömme olmadan yazıldı", onaylandi=True)
    assert y["durum"] == "kaydedildi" and y["embedding"] is False


def test_dolu_siniri(ist, monkeypatch):
    monkeypatch.setattr(h, "AZAMI_KAYIT", 1)
    _k(ist, "Bir", "Birinci kayıt alfa", onaylandi=True)
    assert _k(ist, "İki", "tamamen farklı konu beta gama", onaylandi=True)["durum"] == "dolu"
