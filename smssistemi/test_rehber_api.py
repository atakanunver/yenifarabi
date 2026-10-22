"""rehber_api.py testleri (/api/arac/ogrenci-iletisim). Telefonlar SAHTE (0555…)."""

import json

import pytest
from fastapi import HTTPException

import arac_api as aa
import db
import rehber_api as ra

ANAHTAR = "test-anahtari"


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "t.db")
    monkeypatch.setattr(db, "YEDEK_DIZINI", tmp_path / "yedek")
    ayar = tmp_path / "arac.json"
    ayar.write_text(json.dumps({"anahtar": ANAHTAR}))
    monkeypatch.setattr(aa, "AYAR_YOLU", ayar)
    db.semayi_kur()
    conn = db.baglanti()
    def sinif_id(ad):  # semayi_kur varsayılan sınıfları tohumlar
        r = conn.execute("SELECT id FROM siniflar WHERE ad = ?", (ad,)).fetchone()
        return r[0] if r else conn.execute("INSERT INTO siniflar (ad) VALUES (?)", (ad,)).lastrowid

    s9, s12 = sinif_id("9-A"), sinif_id("12-A")

    def kisi(ad, sinif, tur, tel, bagli=None, dogum=None, no=None, rol=None):
        return conn.execute(
            "INSERT INTO kisiler (ad_soyad, telefon, sinif_id, tur, ogrenci_kisi_id, dogum_tarihi, okul_no, veli_rol) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (ad, tel, sinif, tur, bagli, dogum, no, rol),
        ).lastrowid

    cagla = kisi("Çağla Yıldız", s9, "ogrenci", "05550000001", dogum="2011-03-04", no=11)
    kisi("Selma Yıldız", s9, "veli", "05550000002", bagli=cagla, rol="Anne")
    kisi("Hasan Yıldız", s9, "veli", "05550000003", bagli=cagla, rol="Baba")
    kardes = kisi("Emre Yıldız", s12, "ogrenci", "", dogum="2008-01-01", no=31)  # Çağla'nın kardeşi
    kisi("Selma Yıldız", s12, "veli", "05550000002", bagli=kardes, rol="Anne")
    kisi("Ayşe Kaya", s12, "ogrenci", "", dogum="2010-07-01", no=21)
    kisi("Ayşe Demir", s9, "ogrenci", "05550000004", dogum="2010-12-31", no=12)
    conn.commit()
    conn.close()


def test_anahtarsiz_401(ortam):
    with pytest.raises(HTTPException) as e:
        aa.anahtar_dogrula(None)
    assert e.value.status_code == 401


def test_bos_sorgu_400(ortam):
    with pytest.raises(HTTPException) as e:
        ra.ogrenci_iletisim()
    assert e.value.status_code == 400


def test_veliler_baglanir_ve_aksansiz_arama(ortam):
    v = json.loads(ra.ogrenci_iletisim(ad="cagla").body)
    assert v["toplam"] == 1
    o = v["ogrenciler"][0]
    assert o["okul_no"] == 11 and o["ogrenci_telefon"] == "05550000001"
    assert [(x["rol"], x["telefon"]) for x in o["veliler"]] == [("Anne", "05550000002"), ("Baba", "05550000003")]


def test_ayni_adli_iki_ayse_ikisi_de_doner(ortam):
    v = json.loads(ra.ogrenci_iletisim(ad="Ayşe").body)
    assert {o["ad_soyad"] for o in v["ogrenciler"]} == {"Ayşe Kaya", "Ayşe Demir"}


def test_dogum_yili_ve_sinif_filtresi(ortam):
    assert json.loads(ra.ogrenci_iletisim(dogum_yili="2010").body)["toplam"] == 2
    v = json.loads(ra.ogrenci_iletisim(dogum_yili="2010", sinif="12 a").body)
    assert [o["ad_soyad"] for o in v["ogrenciler"]] == ["Ayşe Kaya"]


def test_veli_adindan_ogrenci_bulunur(ortam):
    v = json.loads(ra.ogrenci_iletisim(veli_ad="selma yildiz").body)
    assert {o["ad_soyad"] for o in v["ogrenciler"]} == {"Çağla Yıldız", "Emre Yıldız"}  # iki çocuğu
    cagla = next(o for o in v["ogrenciler"] if o["ad_soyad"] == "Çağla Yıldız")
    assert len(cagla["veliler"]) == 2  # anne+baba görünür, yalnız eşleşen değil
    assert json.loads(ra.ogrenci_iletisim(veli_ad="Hasan").body)["toplam"] == 1  # baba tek çocuğa bağlı
    assert json.loads(ra.ogrenci_iletisim(veli_ad="Yok Boyle").body)["toplam"] == 0


def test_veli_ad_ogrenci_adiyla_karismaz(ortam):
    # "Ayşe" öğrenci adı; veli_ad yalnız veli kayıtlarında aranır
    assert json.loads(ra.ogrenci_iletisim(veli_ad="Ayşe").body)["toplam"] == 0


def test_gecersiz_dogum_yili_400(ortam):
    with pytest.raises(HTTPException) as e:
        ra.ogrenci_iletisim(dogum_yili="20x0")
    assert e.value.status_code == 400


def test_sonuc_yoksa_bos_liste(ortam):
    assert json.loads(ra.ogrenci_iletisim(ad="Yok Boyle").body) == {"toplam": 0, "ogrenciler": []}


def test_ad_ve_telefon_loga_yazilmaz(ortam, caplog):
    with caplog.at_level("INFO", logger="smssistemi.rehber"):
        ra.ogrenci_iletisim(ad="Çağla")
    metin = " ".join(r.getMessage() for r in caplog.records)
    assert "Çağla" not in metin and "0555" not in metin


def test_limit_sonucu_kisar_ama_toplam_gercek(ortam):
    v = json.loads(ra.ogrenci_iletisim(dogum_yili="2010", limit=1).body)
    assert v["toplam"] == 2 and len(v["ogrenciler"]) == 1
