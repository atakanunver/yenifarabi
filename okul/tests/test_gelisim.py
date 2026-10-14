"""Akademik gelişim analizi: gerçek veriden hesap, yetersiz veri, küçük grup gizleme, trend, ödev/çalışma göstergeleri."""

import json
from datetime import timedelta

import gelisim
import pytest
from kaynaklar.kazanim import TestSonucu


def _ogr(conn, yeni_kullanici, no, sinif="9-A"):
    kid = yeni_kullanici(conn, "ogrenci", f"Ogr {no}", str(no), sifre="x")
    oid = conn.execute(
        "INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (?, ?, ?, ?)", (no, f"Ogr {no}", sinif, kid)
    ).lastrowid
    conn.commit()
    return conn.execute("SELECT * FROM ogrenci WHERE id = ?", (oid,)).fetchone()


def _test_odevi(conn, ogretmen, sinif="9-A", ders="Matematik", kazanim="MAT.1", soru=6, teslim="2026-10-05 18:00:00"):
    oid = conn.execute(
        "INSERT INTO odev (ogretmen_id, sinif, ders, tur, baslik, teslim, olusturma) VALUES (?, ?, ?, 'test', 'T', ?, ?)",
        (ogretmen, sinif, ders, teslim, "2026-09-01 10:00:00"),
    ).lastrowid
    sids = []
    for i in range(1, soru + 1):
        sids.append(conn.execute(
            "INSERT INTO odev_soru (odev_id, sira, metin, siklar, dogru, kazanim) VALUES (?, ?, 's', '[\"a\",\"b\"]', 1, ?)",
            (oid, i, kazanim),
        ).lastrowid)
    conn.commit()
    return oid, sids


def _teslim(conn, oid, sids, ogr, dogru_say, zaman_="2026-10-05 12:00:00"):
    cevap = {str(s): (1 if i < dogru_say else 0) for i, s in enumerate(sids)}
    conn.execute(
        "INSERT INTO odev_teslim (odev_id, ogrenci_id, durum, puan, cevaplar, zaman) VALUES (?, ?, 'tamam', 0, ?, ?)",
        (oid, ogr["id"], json.dumps(cevap), zaman_),
    )
    conn.commit()


def test_veri_yoksa_uydurma_yok(conn, ornek, yeni_kullanici):
    o = _ogr(conn, yeni_kullanici, 500)
    r = gelisim.ogrenci_raporu(conn, o, {})
    assert r["dersler"] == [] and r["tekrar"] == [] and r["veri_var"] is False
    assert r["odev"] == {"verilen": 0, "teslim": 0, "oran": None}
    assert r["calisma"] == {"arena": 0, "maraton": 0, "toplam": 0}


def test_ogrenci_ders_yuzdesi_ve_yetersiz_veri(conn, ornek, yeni_kullanici, saat):
    o = _ogr(conn, yeni_kullanici, 501)
    oid, sids = _test_odevi(conn, ornek["ogretmen"], soru=6)
    _teslim(conn, oid, sids, o, 4)
    r = gelisim.ogrenci_raporu(conn, o, {})
    d = r["dersler"][0]
    assert (d["ders"], d["dogru"], d["toplam"], d["yuzde"], d["yeterli"]) == ("matematik", 4, 6, 67, True)
    assert d["kazanimlar"][0]["kazanim"] == "MAT.1" and d["basarili_kazanim"] == 0  # %67 < eşik %70
    # 3 soruluk ders: yüzde gösterilmez
    oid2, s2 = _test_odevi(conn, ornek["ogretmen"], ders="Fizik", soru=3)
    _teslim(conn, oid2, s2, o, 3)
    f = next(x for x in gelisim.ogrenci_raporu(conn, o, {})["dersler"] if x["ders"] == "fizik")
    assert f["toplam"] == 3 and f["yuzde"] is None and f["yeterli"] is False


def test_form_verisi_birlesir_ve_ders_adi_normalize(conn, ornek, yeni_kullanici):
    o = _ogr(conn, yeni_kullanici, 502)
    oid, sids = _test_odevi(conn, ornek["ogretmen"], ders="MATEMATİK", soru=5)
    _teslim(conn, oid, sids, o, 5)
    form = {502: [TestSonucu("matematik", 3, "MAT.2", 2, 5, "2026-10-01")]}
    r = gelisim.ogrenci_raporu(conn, o, form)
    assert len(r["dersler"]) == 1  # "MATEMATİK" ile "matematik" tek ders
    d = r["dersler"][0]
    assert d["toplam"] == 10 and d["dogru"] == 7 and {k["kazanim"] for k in d["kazanimlar"]} == {"MAT.1", "MAT.2"}


def test_tekrar_onerisi_kanitli_ve_esikli(conn, ornek, yeni_kullanici):
    o = _ogr(conn, yeni_kullanici, 503)
    form = {503: [TestSonucu("matematik", 1, "AZ", 0, 2, "2026-10-01"),  # 2 soru: öneri yok
                  TestSonucu("matematik", 2, "ZAYIF", 1, 4, "2026-10-02"),  # %25, 4 soru: öneri
                  TestSonucu("matematik", 3, "IYI", 4, 4, "2026-10-03")]}
    t = gelisim.ogrenci_raporu(conn, o, form)["tekrar"]
    assert [(x["kazanim"], x["dogru"], x["toplam"]) for x in t] == [("ZAYIF", 1, 4)]


def test_trend_donemler(conn, ornek, yeni_kullanici, saat):
    o = _ogr(conn, yeni_kullanici, 504)
    bugun = saat["an"]  # 2026-10-12
    eski = (bugun - timedelta(days=45)).strftime("%Y-%m-%d")
    yeni = (bugun - timedelta(days=5)).strftime("%Y-%m-%d")
    form = {504: [TestSonucu("matematik", 1, "A", 2, 10, eski), TestSonucu("matematik", 2, "B", 7, 10, yeni)]}
    tr = gelisim.ogrenci_raporu(conn, o, form)["dersler"][0]["trend"]
    assert tr == {"durum": "artti", "fark": 50, "son": 70, "once": 20}
    # önceki dönemde yeterli veri yoksa trend yok
    tr2 = gelisim.ogrenci_raporu(conn, o, {504: [TestSonucu("matematik", 2, "B", 7, 10, yeni)]})["dersler"][0]["trend"]
    assert tr2["durum"] == "yetersiz"


def test_odev_durumu(conn, ornek, yeni_kullanici, saat):
    o = _ogr(conn, yeni_kullanici, 505)
    oid, sids = _test_odevi(conn, ornek["ogretmen"], teslim="2026-10-05 18:00:00")
    _test_odevi(conn, ornek["ogretmen"], teslim="2026-10-06 18:00:00")
    _test_odevi(conn, ornek["ogretmen"], teslim="2026-10-20 18:00:00")  # henüz vadesi gelmedi: paydada değil
    _teslim(conn, oid, sids, o, 3)
    assert gelisim.ogrenci_raporu(conn, o, {})["odev"] == {"verilen": 2, "teslim": 1, "oran": 50}


def test_calisma_katilimi_ayri_ve_terk_sayilmaz(conn, ornek, yeni_kullanici, saat):
    o = _ogr(conn, yeni_kullanici, 506)
    k = o["kullanici_id"]
    conn.execute("INSERT INTO bilgi_tur (kullanici_id, gun, sinif, ders, basla, durum) VALUES (?, '2026-10-10', '9-A', 'matematik', 't', 'tamam')", (k,))
    m1 = conn.execute("INSERT INTO maraton (kullanici_id, sinif, duzey, ders, basla, bitis) VALUES (?, '9-A', 9, 'm', 't', '2026-10-09 10:00:00')", (k,)).lastrowid
    m2 = conn.execute("INSERT INTO maraton (kullanici_id, sinif, duzey, ders, basla, bitis) VALUES (?, '9-A', 9, 'm', 't', '2026-10-09 11:00:00')", (k,)).lastrowid
    conn.execute("INSERT INTO maraton_soru (maraton_id, sira, soru_id, soru, secenekler, dogru_index, cevap) VALUES (?, 1, 1, 's', '[]', 0, -2)", (m2,))
    conn.execute("INSERT INTO maraton_soru (maraton_id, sira, soru_id, soru, secenekler, dogru_index, cevap) VALUES (?, 1, 1, 's', '[]', 0, 0)", (m1,))
    conn.commit()
    r = gelisim.ogrenci_raporu(conn, o, {})
    assert r["calisma"] == {"arena": 1, "maraton": 1, "toplam": 2}
    assert r["dersler"] == []  # çalışma katılımı akademik göstergeye karışmaz


def _sinif_doldur(conn, yeni_kullanici, ogretmen, n, baslangic=600, sinif="9-A", dogru=4):
    ogrler = [_ogr(conn, yeni_kullanici, baslangic + i, sinif) for i in range(n)]
    oid, sids = _test_odevi(conn, ogretmen, sinif=sinif, soru=6, kazanim="MAT.7")
    for o in ogrler:
        _teslim(conn, oid, sids, o, dogru)
    return ogrler


def test_kucuk_sinif_grubu_gizli(conn, ornek, yeni_kullanici):
    _sinif_doldur(conn, yeni_kullanici, ornek["ogretmen"], 4, sinif="10-A")
    r = gelisim.sinif_raporu(conn, "10-A", {})
    d = r["dersler"][0]
    assert d["ogrenci"] == 4 and d["gizli"] is True and "yuzde" not in d and "kazanimlar" not in d
    ok = gelisim.okul_raporu(conn, {})
    satir = next(s for s in ok["siniflar"] if s["sinif"] == "10-A")
    assert satir["dersler"][0]["gizli"] is True and "yuzde" not in satir["dersler"][0]


def test_sinif_raporu_esik_ustu(conn, ornek, yeni_kullanici):
    _sinif_doldur(conn, yeni_kullanici, ornek["ogretmen"], 5, dogru=3)
    r = gelisim.sinif_raporu(conn, "9-A", {})
    d = r["dersler"][0]
    assert d["gizli"] is False and d["ogrenci"] == 5 and d["soru"] == 30 and d["yuzde"] == 50
    assert d["kazanimlar"] == [{"kazanim": "MAT.7", "ogrenci": 5, "basarili": 0, "oran": 0, "yuzde": 50}]
    assert r["verili_ogrenci"] == 5 and r["mevcut"] == 6  # örnek 9-A öğrencisi + 5
    assert len(r["ogrenciler"]) == 6
    veri_yok = [x for x in r["ogrenciler"] if x["toplam"] == 0]
    assert len(veri_yok) == 1 and all(x["yuzde"] is None for x in veri_yok)  # veri yoksa değer yok


def test_ders_filtresi(conn, ornek, yeni_kullanici):
    ogrler = _sinif_doldur(conn, yeni_kullanici, ornek["ogretmen"], 5)
    oid, sids = _test_odevi(conn, ornek["ogretmen"], ders="Fizik", soru=6)
    for o in ogrler:
        _teslim(conn, oid, sids, o, 6)
    assert [d["ders"] for d in gelisim.sinif_raporu(conn, "9-A", {})["dersler"]] == ["fizik", "matematik"]
    assert [d["ders"] for d in gelisim.sinif_raporu(conn, "9-A", {}, ders="Fizik")["dersler"]] == ["fizik"]


def test_kaynak_erisilemedi_isareti(conn, ornek):
    assert gelisim.sinif_raporu(conn, "9-A", {}, kaynak_erisildi=False)["kaynak_erisildi"] is False
    assert gelisim.okul_raporu(conn, {}, kaynak_erisildi=False)["kaynak_erisildi"] is False


@pytest.mark.parametrize("n,gizli", [(4, True), (5, False)])
def test_esik_siniri(conn, ornek, yeni_kullanici, n, gizli):
    _sinif_doldur(conn, yeni_kullanici, ornek["ogretmen"], n, baslangic=700 + n, sinif="11-A")
    assert gelisim.sinif_raporu(conn, "11-A", {})["dersler"][0]["gizli"] is gizli
