"""Kelebek yerleşimi (salt-okunur kaynak) ve öğrenci ana ekranındaki sınav yeri/devamsızlık hapları."""

import sqlite3

import pytest
from ayarlar import AYAR
from kaynaklar import KaynakHatasi, kelebek

from tests.test_ana_yeni import giris, istemci  # noqa: F401


def _kelebek_db(yol):
    c = sqlite3.connect(yol)
    c.executescript(
        "CREATE TABLE dagitim_salon (tarih TEXT, ders_no INT, derslik_id INT, ad TEXT, sutun INT, sira INT, sira_basi INT);"
        "CREATE TABLE dagitim (tarih TEXT, ders_no INT, okul_no INT, ad_soyad TEXT, cinsiyet TEXT, sinif TEXT, seviye INT,"
        " ders TEXT, derslik_id INT, koltuk INT);"
        "INSERT INTO dagitim_salon VALUES ('2026-10-14', 3, 7, '10-A Salonu', 3, 5, 2);"
        "INSERT INTO dagitim VALUES ('2026-10-14', 3, 101, 'Ali', 'E', '9-A', 9, 'Matematik', 7, 9);"
        "INSERT INTO dagitim VALUES ('2026-10-14', 3, 102, 'Ayşe', 'K', '9-A', 9, 'Matematik', 7, 10);"
    )
    c.commit()
    c.close()


def test_yerlesim_yalniz_kendi_koltugu_ve_konum(tmp_path):
    _kelebek_db(AYAR.kelebek_db_yolu)
    y = kelebek.yaklasan(101, "2026-10-14", "2026-10-20")
    assert [(x.salon, x.koltuk, x.sutun, x.sira) for x in y] == [("10-A Salonu", 9, 1, 5)]  # koltuk 9 → masa 4 → 1. sütun, 5. sıra
    assert kelebek.yaklasan(999, "2026-10-14", "2026-10-20") == []
    assert kelebek.yaklasan(101, "2026-10-15", "2026-10-20") == []


def test_kaynak_yoksa_hata():
    with pytest.raises(KaynakHatasi):
        kelebek.yaklasan(101, "2026-10-14", "2026-10-20")


def test_ana_ekran_sinav_yeri_ve_serit(istemci, ornek, conn, saat):  # noqa: F811
    _kelebek_db(AYAR.kelebek_db_yolu)
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci").text
    assert "Sınav yerin" in t and "10-A Salonu" in t and "Sütun 1 · Sıra 5" in t
    assert 'class="ogr-serit"' in t and 'class="ogr-pills"' in t and "ogrenci-ana.css" in t
    assert "Ayşe" not in t


def test_ana_ekran_kelebek_yoksa_kart_gizli(istemci, ornek, conn, saat):  # noqa: F811
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci").text
    assert "Sınav yerin" not in t and "Devamsızlığım" in t


@pytest.mark.parametrize("kadi,sifre,yol", [("hoca", "hoca-sifre", "/ogretmen"), ("mudur", "mudur-sifre", "/yonetici")])
def test_rol_ana_sayfalari_ortak_bilesen(istemci, ornek, conn, saat, kadi, sifre, yol):  # noqa: F811
    giris(istemci, kadi, sifre)
    t = istemci.get(yol).text
    assert 'class="rol-ana"' in t and "rol-ana.css" in t
    if yol == "/yonetici":
        assert 'class="rol-pills"' in t and "/yonetici/kullanicilar" in t
