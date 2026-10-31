"""conftest.py - Testler üretim verisine/loglarına/DB'sine dokunmaz.

logger modülü import anında log dosyalarını açtığından ortam değişkenleri BURADA, test
modülleri import edilmeden önce ayarlanır.
"""

import json
import os
import sqlite3
import tempfile
from pathlib import Path

_GECICI = Path(tempfile.mkdtemp(prefix="arena_test_"))
os.environ["ARENA_LOG_DIZINI"] = str(_GECICI / "logs")
os.environ["ARENA_VERI_DIZINI"] = str(_GECICI / "veri")

import pytest  # noqa: E402

import havuz  # noqa: E402
import server  # noqa: E402

SINIFLAR = ["9-A", "9-B", "10-A", "11-A", "11-B", "12-A", "12-B", "fenlab"]


def _ogrenciler(n=17):
    return [
        {"no": 100 + i, "ad_soyad": f"Öğrenci {i:02d}", "cinsiyet": "Kız" if i % 2 else "Erkek"}
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def sahte_dunya(tmp_path, monkeypatch):
    """Tahta/zil/program/roster/yoklama/kazanım dosyalarını ve havuz DB'sini sahtesiyle değiştirir."""
    veri = tmp_path / "farabi"
    veri.mkdir()
    roster = veri / "roster"
    roster.mkdir()
    for s in SINIFLAR:
        (roster / f"{s}.json").write_text(
            json.dumps({"sinif": s, "ogrenciler": _ogrenciler()}, ensure_ascii=False), encoding="utf-8")

    (veri / "tahtalar.json").write_text(json.dumps({
        "_aciklama": ["test"],
        "9-A": {"ip": "192.168.23.245"},
        "12-B": {"ip": "192.168.23.240"},
    }), encoding="utf-8")
    (veri / "zil.json").write_text(json.dumps({"dersler": [
        {"no": i, "baslangic": f"{7 + i:02d}:10", "bitis": f"{7 + i:02d}:50"} for i in range(1, 9)
    ]}), encoding="utf-8")
    gunler = {g: {str(i): "biyoloji" for i in range(1, 9)} for g in
              ("pazartesi", "sali", "carsamba", "persembe", "cuma")}
    for g in gunler:
        gunler[g]["5"] = "hedef fizik"
        gunler[g]["6"] = "ingilizce"
        gunler[g]["7"] = "türk dili ve edebiyatı"
    (veri / "ders_programi.json").write_text(json.dumps(
        {"siniflar": {s: gunler for s in SINIFLAR}}, ensure_ascii=False), encoding="utf-8")
    (veri / "kazanimlar.json").write_text(json.dumps({
        "haftalar": {"1": "2026-09-14", "2": "2026-09-21"},
        "kazanimlar": {"12": {"hedef fizik": {"2": "Kuvvet ve hareket ilişkisini yorumlar.\nİş ve enerji hesaplar."}}},
    }, ensure_ascii=False), encoding="utf-8")

    yoklama = veri / "yoklama.db"
    c = sqlite3.connect(yoklama)
    c.execute("""CREATE TABLE yoklama_onbellek (id INTEGER PRIMARY KEY AUTOINCREMENT, tarih TEXT NOT NULL,
        sinif TEXT NOT NULL, ders_no INTEGER NOT NULL, durum TEXT NOT NULL, yok_isimleri TEXT, izinli_isimleri TEXT,
        kaynak_tahta TEXT, kaydedilme_saati TEXT, guncelleme_zamani TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(tarih, sinif, ders_no))""")
    c.execute("INSERT INTO yoklama_onbellek (tarih, sinif, ders_no, durum, yok_isimleri, izinli_isimleri) VALUES (?,?,?,?,?,?)",
              ("2020-01-01", "12-B", 8, "ok",
               json.dumps(["Öğrenci 01", "Öğrenci 02", "Öğrenci 03"]), json.dumps(["Öğrenci 04"])))
    c.commit()
    c.close()

    monkeypatch.setattr(server, "TAHTALAR_JSON", veri / "tahtalar.json")
    monkeypatch.setattr(server, "ZIL_JSON", veri / "zil.json")
    monkeypatch.setattr(server, "DERS_PROGRAMI_JSON", veri / "ders_programi.json")
    monkeypatch.setattr(server, "KAZANIMLAR_JSON", veri / "kazanimlar.json")
    monkeypatch.setattr(server, "ROSTER_DIR", roster)
    monkeypatch.setattr(server, "YOKLAMA_DB", yoklama)
    monkeypatch.setenv("ARENA_VERI_DIZINI", str(tmp_path / "veri"))
    server._HATA_SON.clear()

    def _db_yok(sql, parametreler):
        raise RuntimeError("testte canlı soru havuzu DB'sine bağlanılmaz")

    monkeypatch.setattr(havuz, "_db_sorgu", _db_yok)
    yield veri
