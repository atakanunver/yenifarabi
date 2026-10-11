"""Saat widget'ı / zil tablosu: okul günü, tatil, yarım gün, ders-teneffüs-öğle hesabı."""

import json
import shutil
from datetime import datetime

import pytest
from ayarlar import AYAR, KOK
from fastapi.testclient import TestClient
from kaynaklar import zil

ZIL = {
    "dersler": [
        {"no": 1, "baslangic": "08:10", "bitis": "08:50"},
        {"no": 2, "baslangic": "09:00", "bitis": "09:40"},
        {"no": 5, "baslangic": "11:30", "bitis": "12:10"},
        {"no": 6, "baslangic": "13:30", "bitis": "14:10"},
    ],
    "ogle_arasi": {"baslangic": "12:10", "bitis": "13:30"},
    "ders_gunleri": [1, 2, 3, 4, 5],
}


@pytest.fixture
def cizelge():
    AYAR.zil_yolu.write_text(json.dumps(ZIL), encoding="utf-8")
    shutil.copy(KOK / "config" / "takvim.json", AYAR.takvim_yolu)  # gerçek takvim de doğrulanmış olur


@pytest.mark.parametrize(
    "an, tur, metin",
    [
        (datetime(2026, 10, 12, 7, 30), "once", "1. ders 08:10'de başlıyor"),
        (datetime(2026, 10, 12, 8, 10), "ders", "1. ders"),
        (datetime(2026, 10, 12, 8, 50), "teneffus", "Teneffüs · 2. ders 09:00"),
        (datetime(2026, 10, 12, 12, 30), "ogle", "Öğle arası · 6. ders 13:30"),
        (datetime(2026, 10, 12, 14, 10), "bitti", "Dersler bitti"),
        (datetime(2026, 10, 17, 10, 0), "tatil", "Hafta sonu"),
        (datetime(2026, 10, 29, 10, 0), "tatil", "Cumhuriyet Bayramı"),
        (datetime(2026, 11, 18, 10, 0), "tatil", "1. dönem ara tatili"),
        (datetime(2027, 7, 5, 10, 0), "tatil", "Yaz tatili"),
        (datetime(2026, 10, 28, 13, 0), "bitti", "Dersler bitti"),  # yarım gün: öğleden sonra ders yok
    ],
)
def test_durum(cizelge, an, tur, metin):
    d = zil.durum(an)
    assert (d["tur"], d["metin"]) == (tur, metin)


def test_zil_yoksa_saat_yine_calisir():
    assert zil.durum(datetime(2026, 10, 12, 10, 0))["tur"] == "yok"
    assert zil.widget_verisi(datetime(2026, 10, 12, 10, 0))["dersler"] == []


def test_widget_ve_zil_tablosu_sayfalarda(cizelge, ornek, saat, monkeypatch):
    from app import app
    from kaynaklar import kazanim
    from test_web_belge_sinav import giris

    monkeypatch.setattr(kazanim, "form_sonuclari", lambda okul_no: [])
    saat["an"] = datetime(2026, 10, 12, 9, 10)
    with TestClient(app) as c:
        for kadi, sifre, yol in [("101", "ali-sifre", "/ogrenci"), ("hoca", "hoca-sifre", "/ogretmen"),
                                 ("mudur", "mudur-sifre", "/yonetici")]:
            giris(c, kadi, sifre)
            t = c.get(yol).text
            assert 'id="saat-kart"' in t and "2. ders" in t and "saat.js" in t
        for kadi, sifre, yol in [("101", "ali-sifre", "/ogrenci/program"), ("hoca", "hoca-sifre", "/ogretmen/program")]:
            giris(c, kadi, sifre)
            t = c.get(yol).text
            assert 'id="zil-tablo"' in t and "13:30" in t and "Öğle arası" in t
