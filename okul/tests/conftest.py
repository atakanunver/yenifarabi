import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth
import db
import zaman
from ayarlar import AYAR


@pytest.fixture(autouse=True)
def gecici_ortam(tmp_path, monkeypatch):
    monkeypatch.setattr(AYAR, "db_yolu", tmp_path / "okul.db")
    monkeypatch.setattr(AYAR, "dosya_dizini", tmp_path / "dosyalar")
    monkeypatch.setattr(AYAR, "pano_db_yolu", tmp_path / "pano.db")
    monkeypatch.setattr(AYAR, "program_yolu", tmp_path / "program.json")
    monkeypatch.setattr(AYAR, "zil_yolu", tmp_path / "zil.json")
    monkeypatch.setattr(AYAR, "takvim_yolu", tmp_path / "takvim.json")
    monkeypatch.setattr(AYAR, "sms_anahtar", "test-anahtar")
    db.sema_kur()


@pytest.fixture
def conn():
    c = db.baglanti()
    yield c
    c.close()


@pytest.fixture
def yeni_kullanici():
    def yap(c, rol, ad, kullanici_adi=None, telefon=None, sifre=None):
        cur = c.execute(
            "INSERT INTO kullanici (rol, ad_soyad, kullanici_adi, telefon, sifre_hash,"
            " sifre_degismeli, olusturma) VALUES (?, ?, ?, ?, ?, 0, ?)",
            (
                rol,
                ad,
                kullanici_adi,
                telefon,
                auth.sifre_hashle(sifre) if sifre else None,
                zaman.simdi_str(),
            ),
        )
        c.commit()
        return cur.lastrowid

    return yap


@pytest.fixture
def ornek(conn, yeni_kullanici):
    k = {}
    k["yonetici"] = yeni_kullanici(
        conn, "yonetici", "Müdür Bey", "mudur", sifre="mudur-sifre"
    )
    k["ogretmen"] = yeni_kullanici(
        conn, "ogretmen", "Hoca Hanım", "hoca", sifre="hoca-sifre"
    )
    k["ogr1_k"] = yeni_kullanici(conn, "ogrenci", "Ali Veli", "101", sifre="ali-sifre")
    k["ogr2_k"] = yeni_kullanici(
        conn, "ogrenci", "Ayşe Kaya", "201", sifre="ayse-sifre"
    )
    k["veli1"] = yeni_kullanici(conn, "veli", "Veli Bey", telefon="05321112233")
    k["ogr1"] = conn.execute(
        "INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id)"
        " VALUES (101, 'Ali Veli', '9-A', ?)",
        (k["ogr1_k"],),
    ).lastrowid
    k["ogr2"] = conn.execute(
        "INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id)"
        " VALUES (201, 'Ayşe Kaya', '9-B', ?)",
        (k["ogr2_k"],),
    ).lastrowid
    conn.execute(
        "INSERT INTO veli_ogrenci (veli_id, ogrenci_id) VALUES (?, ?)",
        (k["veli1"], k["ogr1"]),
    )
    conn.execute(
        "INSERT INTO ogretmen_gorev (ogretmen_id, sinif, ders) VALUES (?, '9-A', 'matematik')",
        (k["ogretmen"],),
    )
    conn.commit()
    return k


@pytest.fixture
def saat(monkeypatch):
    """Elle ilerletilebilir saat: saat['an'] = datetime(...)."""
    from datetime import datetime

    durum = {"an": datetime(2026, 10, 12, 10, 0, 0)}
    monkeypatch.setattr(zaman, "simdi", lambda: durum["an"])
    return durum
