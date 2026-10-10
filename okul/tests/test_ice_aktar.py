import io
from datetime import timedelta

import auth
import ice_aktar
import openpyxl
import pytest


def _xlsx(baslik, satirlar):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(baslik)
    for s in satirlar:
        ws.append(s)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


OGR = ice_aktar.OGRENCI_BASLIK


def test_sablon_basliklari():
    wb = openpyxl.load_workbook(io.BytesIO(ice_aktar.sablon(OGR)))
    assert [c.value for c in wb.active[1]] == OGR


def test_ogrenci_onizleme_hatalari():
    veri = _xlsx(
        OGR,
        [
            [101, "Ali Veli", "9-a", "Veli Bey", "0532 111 22 33", None, None],
            ["abc", "X", "9-A", None, None, None, None],
            [102, "", "9-A", None, None, None, None],
            [103, "Can", "13-Z", None, None, None, None],
            [104, "Ece", "9-A", "Anne", "123", None, None],
            [101, "Tekrar", "9-A", None, None, None, None],
            [None, None, None, None, None, None, None],
        ],
    )
    o = ice_aktar.ogrenci_onizle(veri)
    assert o.satirlar[0] == {
        "okul_no": 101,
        "ad_soyad": "Ali Veli",
        "sinif": "9-A",
        "veliler": [["Veli Bey", "05321112233"]],
    }
    assert len(o.satirlar) == 1
    assert len(o.hatalar) == 5
    assert any("Satır 3" in h for h in o.hatalar)


def test_eksik_baslik_hatasi():
    with pytest.raises(ice_aktar.AktarimHatasi):
        ice_aktar.ogrenci_onizle(_xlsx(["okul_no", "ad"], [[1, "x"]]))


def test_ogrenci_uygula_ekler_gunceller_ve_veli_baglar(conn, saat):
    o = ice_aktar.ogrenci_onizle(
        _xlsx(
            OGR,
            [
                [
                    101,
                    "Ayşe Nur Yılmaz",
                    "9-A",
                    "Anne Yılmaz",
                    "05321112233",
                    "Baba Yılmaz",
                    "05324445566",
                ],
                [102, "Can Demir", "9-A", "Anne Yılmaz", "05321112233", None, None],
            ],
        )
    )
    s = ice_aktar.ogrenci_uygula(conn, o.satirlar)
    assert (s.eklenen, s.guncellenen) == (2, 0)
    assert ("Ayşe Nur Yılmaz", "101", "ayse123") in s.yeni_hesaplar
    k = conn.execute("SELECT * FROM kullanici WHERE kullanici_adi = '101'").fetchone()
    assert k["rol"] == "ogrenci" and k["sifre_degismeli"] == 1
    assert auth.sifre_dogrula("ayse123", k["sifre_hash"])
    anne = conn.execute(
        "SELECT * FROM kullanici WHERE telefon = '05321112233' AND rol = 'veli'"
    ).fetchone()
    assert (
        conn.execute(
            "SELECT count(*) FROM veli_ogrenci WHERE veli_id = ?", (anne["id"],)
        ).fetchone()[0]
        == 2
    )
    assert len(s.yeni_veliler) == 2

    o2 = ice_aktar.ogrenci_onizle(
        _xlsx(OGR, [[101, "Ayşe Nur Yılmaz", "10-A", None, None, None, None]])
    )
    s2 = ice_aktar.ogrenci_uygula(conn, o2.satirlar)
    assert (s2.eklenen, s2.guncellenen, s2.yeni_hesaplar) == (0, 1, [])
    assert (
        conn.execute("SELECT sinif FROM ogrenci WHERE okul_no = 101").fetchone()[0]
        == "10-A"
    )
    assert s2.excelde_olmayan == ["102 Can Demir (9-A)"]
    assert conn.execute("SELECT count(*) FROM ogrenci").fetchone()[0] == 2  # silmez


def test_ogretmen_aktarimi(conn, saat):
    o = ice_aktar.ogretmen_onizle(
        _xlsx(
            ice_aktar.OGRETMEN_BASLIK,
            [
                ["Hatice Öz", "hoz", "0532 000 00 01", "9-A", "Matematik"],
                ["Hatice Öz", "hoz", "0532 000 00 01", "9-B", "matematik"],
                ["Eksik", "", None, "9-A", "fizik"],
            ],
        )
    )
    assert len(o.hatalar) == 1
    s = ice_aktar.ogretmen_uygula(conn, o.satirlar)
    assert s.yeni_hesaplar == [("Hatice Öz", "hoz", "hatice123")]
    gorev = conn.execute(
        "SELECT sinif, ders FROM ogretmen_gorev ORDER BY sinif"
    ).fetchall()
    assert [tuple(g) for g in gorev] == [("9-A", "matematik"), ("9-B", "matematik")]


def test_taslak_kaydet_al_ve_sure(conn, saat):
    tid = ice_aktar.taslak_kaydet(conn, "ogrenci", [{"okul_no": 1}])
    assert ice_aktar.taslak_al(conn, tid, "ogrenci") == [{"okul_no": 1}]
    assert ice_aktar.taslak_al(conn, tid, "ogretmen") is None
    saat["an"] += timedelta(hours=2)
    assert ice_aktar.taslak_al(conn, tid, "ogrenci") is None
