import io
import sqlite3

import belgeler
import db
import dosyalar
import openpyxl
import pytest
import sinavlar
from ayarlar import AYAR

JPG = b"\xff\xd8\xff\xe0" + b"0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
PDF = b"%PDF-1.7\n" + b"0" * 100
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 100


def _xlsx():
    b = io.BytesIO()
    openpyxl.Workbook().save(b)
    return b.getvalue()


def _k(conn, kid):
    return conn.execute("SELECT * FROM kullanici WHERE id = ?", (kid,)).fetchone()


# --- göç ---


def test_v1_veritabani_v2_ye_kayipsiz_gecer(tmp_path, monkeypatch):
    monkeypatch.setattr(AYAR, "db_yolu", tmp_path / "eski.db")
    c = sqlite3.connect(AYAR.db_yolu)
    c.executescript(db.SEMA_V1 + "PRAGMA user_version = 1;")
    c.execute(
        "INSERT INTO kullanici (rol, ad_soyad, kullanici_adi, olusturma) VALUES ('ogrenci', 'Eski', '1', 'x')"
    )
    c.commit()
    c.close()
    db.sema_kur()
    c = db.baglanti()
    assert c.execute("PRAGMA user_version").fetchone()[0] == 2
    assert c.execute("SELECT ad_soyad, foto FROM kullanici").fetchone()[:] == (
        "Eski",
        None,
    )
    assert {r[0] for r in c.execute("SELECT name FROM sqlite_master")} >= {
        "yillik_plan",
        "sinav",
    }


# --- dosya doğrulama ---


def test_foto_turu_icerikten():
    assert dosyalar.foto_turu(JPG) == "jpg" and dosyalar.foto_turu(PNG) == "png"
    assert dosyalar.foto_turu(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"
    assert dosyalar.foto_turu(PDF) is None
    with pytest.raises(dosyalar.DosyaHatasi):
        dosyalar.foto_kaydet(PDF)
    with pytest.raises(dosyalar.DosyaHatasi):
        dosyalar.foto_kaydet(JPG + b"0" * dosyalar.FOTO_AZAMI)


def test_plan_turu_ve_sahte_uzanti():
    assert dosyalar.plan_kaydet(PDF, "plan.PDF").tur == "pdf"
    assert dosyalar.plan_kaydet(_xlsx(), "plan.xlsx").tur == "xlsx"
    assert dosyalar.plan_kaydet(OLE, "eski.doc").tur == "doc"
    for veri, ad in [
        (PDF, "plan.docx"),
        (_xlsx(), "plan.docx"),
        (JPG, "plan.pdf"),
        (b"MZ\x90\x00", "virus.pdf"),
        (OLE, "x.exe"),
        (b"PK\x03\x04bozuk", "a.xlsx"),
    ]:
        with pytest.raises(dosyalar.DosyaHatasi):
            dosyalar.plan_kaydet(veri, ad)


def test_kayit_static_disinda_ve_yol_kacisi_yok():
    d = dosyalar.foto_kaydet(JPG)
    assert dosyalar.yol("foto", d.depo_adi).read_bytes() == JPG
    assert AYAR.dosya_dizini in dosyalar.yol("foto", d.depo_adi).parents
    for kotu in ("../okul.db", "a/b", ".gizli", ""):
        with pytest.raises(dosyalar.DosyaHatasi):
            dosyalar.yol("foto", kotu)


# --- fotoğraf görünürlüğü ---


def test_foto_gorunurluk_matrisi(conn, ornek):
    ogr1, ogr2, hoca, veli, yon = (
        ornek["ogr1_k"],
        ornek["ogr2_k"],
        ornek["ogretmen"],
        ornek["veli1"],
        ornek["yonetici"],
    )
    g = lambda kim, hedef: belgeler.foto_gorebilir(conn, _k(conn, kim), hedef)
    assert g(ogr1, ogr1) and g(veli, ogr1) and g(hoca, ogr1) and g(yon, ogr1)
    assert not g(ogr2, ogr1)  # öğrenciler birbirini göremez
    assert not g(veli, ogr2)  # başka çocuğun velisi değil
    assert not g(hoca, ogr2)  # 9-B'ye girmiyor
    assert g(hoca, hoca) and g(yon, hoca)
    assert not g(ogr1, hoca) and not g(
        veli, hoca
    )  # öğretmen fotoğrafı yalnızca kendisi + yönetici


def test_foto_degistir_eskisini_siler(conn, ornek):
    k = _k(conn, ornek["ogr1_k"])
    belgeler.foto_degistir(conn, k, JPG)
    ilk = _k(conn, k["id"])["foto"]
    belgeler.foto_degistir(conn, k, PNG)
    ikinci = _k(conn, k["id"])["foto"]
    assert (
        ikinci != ilk
        and not dosyalar.yol("foto", ilk).exists()
        and dosyalar.yol("foto", ikinci).exists()
    )
    belgeler.foto_sil(conn, k)
    assert (
        _k(conn, k["id"])["foto"] is None and not dosyalar.yol("foto", ikinci).exists()
    )
    with pytest.raises(dosyalar.DosyaHatasi):
        belgeler.foto_degistir(conn, _k(conn, ornek["veli1"]), JPG)


# --- yıllık plan ---


def test_plan_yukle_degistir_ve_erisim(conn, ornek, yeni_kullanici):
    hoca = _k(conn, ornek["ogretmen"])
    pid = belgeler.plan_yukle(conn, hoca, "9-A", "matematik", "mat.pdf", PDF)
    eski = belgeler.plan_getir(conn, hoca, pid)["depo_adi"]
    assert (
        belgeler.plan_yukle(conn, hoca, "9-A", "matematik", "mat.xlsx", _xlsx()) == pid
    )  # yerine geçer
    assert not dosyalar.yol("plan", eski).exists()
    assert (
        belgeler.plan_getir(conn, _k(conn, ornek["yonetici"]), pid)["dosya_adi"]
        == "mat.xlsx"
    )
    diger = _k(conn, yeni_kullanici(conn, "ogretmen", "Diğer", "diger", sifre="x"))
    for kim in (diger, _k(conn, ornek["ogr1_k"]), _k(conn, ornek["veli1"])):
        assert belgeler.plan_getir(conn, kim, pid) is None
        assert not belgeler.plan_sil(conn, kim, pid)
    with pytest.raises(PermissionError):
        belgeler.plan_yukle(conn, hoca, "9-B", "matematik", "x.pdf", PDF)
    eksik = [r for r in belgeler.tum_planlar(conn) if r["plan_id"] is None]
    assert eksik == []
    assert belgeler.plan_sil(conn, hoca, pid)
    assert [
        r["ad_soyad"] for r in belgeler.tum_planlar(conn) if r["plan_id"] is None
    ] == ["Hoca Hanım"]


# --- sınavlar ---


def test_yazili_yalnizca_gorevli_sinif_ders(conn, ornek, saat):
    hoca = _k(conn, ornek["ogretmen"])
    sid = sinavlar.yazili_ekle(
        conn, hoca, "9-A", "Matematik", "2026-10-20", "3", "Kesirler"
    )
    s = sinavlar.getir(conn, sid)
    assert (s["baslik"], s["ders"], s["ders_no"]) == (
        "Matematik yazılısı",
        "matematik",
        3,
    )
    for sinif, ders in (("9-B", "matematik"), ("9-A", "fizik")):
        with pytest.raises(sinavlar.YetkiYok):
            sinavlar.yazili_ekle(conn, hoca, sinif, ders, "2026-10-20")
    with pytest.raises(sinavlar.YetkiYok):
        sinavlar.yazili_ekle(
            conn, _k(conn, ornek["ogr1_k"]), "9-A", "matematik", "2026-10-20"
        )
    with pytest.raises(sinavlar.SinavHatasi):
        sinavlar.yazili_ekle(conn, hoca, "9-A", "matematik", "yarın")


def test_deneme_duzeylere_gore_gorunur(conn, ornek, saat):
    hoca = _k(conn, ornek["ogretmen"])
    sinavlar.deneme_ekle(conn, hoca, "1. TYT Denemesi", "2026-10-25", ["12"])
    sinavlar.deneme_ekle(conn, hoca, "Okul geneli deneme", "2026-10-26", [])
    sinavlar.deneme_ekle(conn, hoca, "9-10 deneme", "2026-10-27", ["9", "10"])
    sinavlar.yazili_ekle(conn, hoca, "9-A", "matematik", "2026-10-20")
    assert [s["baslik"] for s in sinavlar.sinif_sinavlari(conn, "9-A")] == [
        "Matematik yazılısı",
        "Okul geneli deneme",
        "9-10 deneme",
    ]
    assert [s["baslik"] for s in sinavlar.sinif_sinavlari(conn, "9-B")] == [
        "Okul geneli deneme",
        "9-10 deneme",
    ]
    assert [s["baslik"] for s in sinavlar.sinif_sinavlari(conn, "12-A")] == [
        "1. TYT Denemesi",
        "Okul geneli deneme",
    ]
    assert (
        sinavlar.sinif_sinavlari(conn, "9-A", "2026-10-26")[0]["baslik"]
        == "Okul geneli deneme"
    )
    with pytest.raises(sinavlar.SinavHatasi):
        sinavlar.deneme_ekle(conn, hoca, "x", "2026-10-25", ["13"])
    with pytest.raises(sinavlar.YetkiYok):
        sinavlar.deneme_ekle(conn, _k(conn, ornek["veli1"]), "x", "2026-10-25", [])


def test_duzenleme_ve_silme_yetkisi(conn, ornek, yeni_kullanici, saat):
    hoca = _k(conn, ornek["ogretmen"])
    diger = _k(conn, yeni_kullanici(conn, "ogretmen", "Diğer", "diger", sifre="x"))
    sid = sinavlar.deneme_ekle(conn, hoca, "Deneme", "2026-10-25", [])
    with pytest.raises(sinavlar.YetkiYok):
        sinavlar.guncelle(conn, diger, sid, "2026-10-26", baslik="X")
    assert not sinavlar.sil(conn, diger, sid)
    sinavlar.guncelle(
        conn, hoca, sid, "2026-10-28", baslik="Deneme 2", duzeyler=["11", "12"]
    )
    s = sinavlar.getir(conn, sid)
    assert (s["baslik"], s["tarih"], s["duzeyler"]) == (
        "Deneme 2",
        "2026-10-28",
        "11,12",
    )
    assert sinavlar.sil(conn, _k(conn, ornek["yonetici"]), sid)


def test_ogretmen_listesi(conn, ornek, yeni_kullanici, saat):
    hoca = _k(conn, ornek["ogretmen"])
    diger_id = yeni_kullanici(conn, "ogretmen", "Diğer", "diger", sifre="x")
    conn.execute("INSERT INTO ogretmen_gorev VALUES (?, '9-B', 'fizik')", (diger_id,))
    conn.commit()
    diger = _k(conn, diger_id)
    sinavlar.yazili_ekle(conn, diger, "9-B", "fizik", "2026-10-20")
    sinavlar.deneme_ekle(conn, diger, "Genel", "2026-10-21", [])
    sinavlar.yazili_ekle(conn, hoca, "9-A", "matematik", "2026-10-22")
    assert [
        s["baslik"] for s in sinavlar.ogretmen_sinavlari(conn, hoca, "2026-10-01")
    ] == ["Genel", "Matematik yazılısı"]
    assert (
        len(
            sinavlar.ogretmen_sinavlari(conn, _k(conn, ornek["yonetici"]), "2026-10-01")
        )
        == 3
    )
    assert sinavlar.kalan_gun("2026-10-14") == 2
