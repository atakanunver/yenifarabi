"""Haftalık ödüller: sayım kuralları, A/C/D kazananları, eşikler, beraberlik, değişmezlik, kiosk günleri, rozet görünürlüğü."""

import json
from datetime import datetime, timedelta

import oduller
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rotalar import pano

HB = "2026-10-05"  # geçen hafta (saat fixture'ı 12 Ekim pazartesi)


def _ogr(conn, yeni_kullanici, no, sinif="9-A", ad=None):
    kid = yeni_kullanici(conn, "ogrenci", ad or f"Ogr Soy{no}", str(no), sifre="x")
    oid = conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (?, ?, ?, ?)",
                       (no, ad or f"Ogr Soy{no}", sinif, kid)).lastrowid
    conn.commit()
    return kid, oid


def _gorev(conn, kid, gun, sure=120, dogru=4):
    b = datetime.strptime(gun + " 15:00:00", "%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO bilgi_tur (kullanici_id, gun, sinif, ders, basla, bitis, durum, dogru) VALUES (?, ?, 'x', 'm', ?, ?, 'tamam', ?)",
                 (kid, gun, b.strftime("%Y-%m-%d %H:%M:%S"), (b + timedelta(seconds=sure)).strftime("%Y-%m-%d %H:%M:%S"), dogru))
    conn.commit()


def _maraton(conn, kid, gun, sure=300, dogru=6, saat="16:00:00", terk=False):
    b = datetime.strptime(f"{gun} {saat}", "%Y-%m-%d %H:%M:%S")
    mid = conn.execute("INSERT INTO maraton (kullanici_id, sinif, duzey, ders, basla, bitis, dogru) VALUES (?, 'x', 9, 'm', ?, ?, ?)",
                       (kid, b.strftime("%Y-%m-%d %H:%M:%S"), (b + timedelta(seconds=sure)).strftime("%Y-%m-%d %H:%M:%S"), dogru)).lastrowid
    conn.execute("INSERT INTO maraton_soru (maraton_id, sira, soru_id, soru, secenekler, dogru_index, cevap) VALUES (?, 1, 1, 's', '[]', 0, ?)",
                 (mid, -2 if terk else 0))
    conn.commit()


def _test(conn, ornek, oid, zaman_):
    od = conn.execute("INSERT INTO odev (ogretmen_id, sinif, ders, tur, baslik, teslim, olusturma) VALUES (?, 'x', 'm', 'test', 'T', '2026-12-01 10:00:00', 't')", (ornek["ogretmen"],)).lastrowid
    conn.execute("INSERT INTO odev_teslim (odev_id, ogrenci_id, durum, puan, cevaplar, zaman) VALUES (?, ?, 'tamam', 50, ?, ?)", (od, oid, json.dumps({}), zaman_))
    conn.commit()


def _n(conn, kid, hb=HB):
    return oduller.haftalik(conn, hb).get(kid)


def test_sayim_kurallari(conn, ornek, yeni_kullanici, saat):
    kid, oid = _ogr(conn, yeni_kullanici, 800)
    _gorev(conn, kid, "2026-10-09", sure=29)  # çok kısa: sayılmaz
    assert _n(conn, kid) is None
    _gorev(conn, kid, "2026-10-05", sure=30)
    _maraton(conn, kid, "2026-10-06", sure=59)  # sayılmaz
    _maraton(conn, kid, "2026-10-06", terk=True, saat="10:00:00")  # sayılmaz
    for s in ("11:00:00", "12:00:00", "13:00:00"):  # günde en çok 2
        _maraton(conn, kid, "2026-10-07", saat=s)
    _test(conn, ornek, oid, "2026-10-08 09:00:00")
    _gorev(conn, kid, "2026-10-12")  # sonraki hafta
    x = _n(conn, kid)
    assert (x["etkinlik"], x["gun"]) == (1 + 2 + 1, 3)  # görev + 2 maraton + test; 5., 7., 8. Ekim
    assert x["dogru"] == 4 + 6 + 6


def test_12_sinif_dahil(conn, ornek, yeni_kullanici, saat):
    kid, _ = _ogr(conn, yeni_kullanici, 801, "12-A")
    _maraton(conn, kid, "2026-10-05")
    assert _n(conn, kid)["etkinlik"] == 1


def test_pasif_ogrenci_sayilmaz(conn, ornek, yeni_kullanici, saat):
    kid, _ = _ogr(conn, yeni_kullanici, 802)
    _gorev(conn, kid, "2026-10-05")
    conn.execute("UPDATE kullanici SET aktif = 0 WHERE id = ?", (kid,))
    conn.commit()
    assert _n(conn, kid) is None


def _etkinlik(conn, kid, n, gunler=("2026-10-05", "2026-10-06", "2026-10-07")):
    """n sayılan etkinlik üretir: gün başına ilk etkinlik Günlük Görev (günde bir), sonra Hızlı Mod (en çok 2), sonra test ödevi."""
    oid = conn.execute("SELECT id FROM ogrenci WHERE kullanici_id = ?", (kid,)).fetchone()[0]
    hoca = conn.execute("SELECT id FROM kullanici WHERE rol = 'ogretmen'").fetchone()[0]
    sayac: dict[str, int] = {}
    for i in range(n):
        gun = gunler[i % len(gunler)]
        k = sayac.get(gun, 0)
        sayac[gun] = k + 1
        if k == 0:
            _gorev(conn, kid, gun)
        elif k <= 2:
            _maraton(conn, kid, gun, saat=f"1{k}:00:00")
        else:
            _test(conn, {"ogretmen": hoca}, oid, f"{gun} 1{k % 10}:30:00")


def test_a_ve_c_kazananlari_ve_esik(conn, ornek, yeni_kullanici, saat):
    a, _ = _ogr(conn, yeni_kullanici, 810)
    b, _ = _ogr(conn, yeni_kullanici, 811)
    c, _ = _ogr(conn, yeni_kullanici, 812)
    _etkinlik(conn, a, 6, ("2026-10-05", "2026-10-06"))  # 6 etkinlik, 2 gün
    _etkinlik(conn, b, 4, ("2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"))  # 4 etkinlik, 4 gün
    _etkinlik(conn, c, 2)  # eşik altı (A için 3, C için 3 gün)
    s = oduller.siralama(conn, HB)
    assert [x["kid"] for x in s["etkinlik"]] == [a]
    assert [x["kid"] for x in s["istikrar"]] == [b]


def test_esik_altinda_odul_yok(conn, ornek, yeni_kullanici, saat):
    a, _ = _ogr(conn, yeni_kullanici, 815)
    _etkinlik(conn, a, 2)
    s = oduller.siralama(conn, HB)
    assert s["etkinlik"] == [] and s["istikrar"] == [] and s["sinif"] == []


def test_beraberlik_hepsi_kazanir(conn, ornek, yeni_kullanici, saat):
    a, _ = _ogr(conn, yeni_kullanici, 820)
    b, _ = _ogr(conn, yeni_kullanici, 821)
    for k in (a, b):
        _etkinlik(conn, k, 3)
    assert {x["kid"] for x in oduller.siralama(conn, HB)["etkinlik"]} == {a, b}


def test_sinif_katilimi_d(conn, ornek, yeni_kullanici, saat):
    # 10-A: 6 öğrenci, 5'i çalıştı (%83); 10-B: 10 öğrenci, 5'i çalıştı (%50); 10-C: 4/4 ama eşik (5) altı
    for sinif, mevcut, calisan, no in (("10-A", 6, 5, 830), ("10-B", 10, 5, 850), ("10-C", 4, 4, 870)):
        for i in range(mevcut):
            kid, _ = _ogr(conn, yeni_kullanici, no + i, sinif)
            if i < calisan:
                _gorev(conn, kid, "2026-10-05")
    s = oduller.siralama(conn, HB)["sinif"]
    assert [(x["sinif"], x["oran"], x["katilan"], x["mevcut"]) for x in s] == [("10-A", 83, 5, 6)]


def test_kapat_yalniz_biten_hafta_ve_degismez(conn, ornek, yeni_kullanici, saat):
    a, _ = _ogr(conn, yeni_kullanici, 840)
    _etkinlik(conn, a, 3)
    with pytest.raises(ValueError):
        oduller.kapat(conn, "2026-10-12")  # içinde bulunulan hafta
    n = oduller.kapat(conn, HB)
    assert n >= 2  # etkinlik + istikrar (3 farklı gün)
    assert oduller.kapat(conn, HB) == 0  # tekrar: eklenen yok
    assert conn.execute("SELECT count(*) FROM odul_hafta").fetchone()[0] == 1
    # sonradan gelen veri geçmiş sonucu değiştirmez
    b, _ = _ogr(conn, yeni_kullanici, 841)
    _etkinlik(conn, b, 20)
    oduller.kapat(conn, HB)
    k = oduller.kayitli(conn, HB)
    assert [r["kullanici_id"] for r in k if r["kategori"] == "etkinlik"] == [a]
    assert [r["kahve"] for r in k if r["kategori"] == "etkinlik"] == [1]
    assert all(r["kahve"] == 0 for r in k if r["kategori"] != "etkinlik")


def test_kiosk_gunleri(conn, ornek, yeni_kullanici, saat):
    a, _ = _ogr(conn, yeni_kullanici, 850, "11-B", "Elif Yıldız Kaya")
    _etkinlik(conn, a, 4)
    for gun in (13, 14, 15, 18):  # salı..çarşamba..persembe..pazar: kiosk boş
        saat["an"] = datetime(2026, 10, 12) + timedelta(days=gun - 12, hours=10)
        if saat["an"].weekday() not in (0, 4):
            assert oduller.kiosk_ogeleri(conn) == []
    saat["an"] = datetime(2026, 10, 12, 10)  # pazartesi: geçen hafta kesin
    o = oduller.kiosk_ogeleri(conn)
    assert [x["baslik"] for x in o][0].startswith("GEÇEN HAFTANIN ÇALIŞKANLARI: EN ÇOK ETKİNLİK")
    assert "Elif Yıldız K. (11-B)" in o[0]["metin"] and "Nescafe" in o[0]["metin"] and "Kaya" not in o[0]["metin"]
    assert conn.execute("SELECT count(*) FROM odul").fetchone()[0] >= 1  # pazartesi sonuç yazıldı


def test_kiosk_cuma_gecici_ve_bos_hafta(conn, ornek, yeni_kullanici, saat):
    saat["an"] = datetime(2026, 10, 16, 10)  # cuma
    o = oduller.kiosk_ogeleri(conn)
    assert len(o) == 1 and "henüz ödül şartını" in o[0]["metin"] and "Nescafe" in o[0]["metin"]
    a, _ = _ogr(conn, yeni_kullanici, 860)
    _etkinlik(conn, a, 3, ("2026-10-12", "2026-10-13", "2026-10-14"))
    o = oduller.kiosk_ogeleri(conn)
    assert o[0]["baslik"].startswith("HAFTANIN ÇALIŞKANLARI (GEÇİCİ)") and "pazartesi kesinleşir" in o[0]["metin"]
    assert conn.execute("SELECT count(*) FROM odul").fetchone()[0] == 0  # geçici: kayıt yok
    saat["an"] = datetime(2026, 10, 19, 10)
    assert oduller.kiosk_ogeleri(conn)[0]["baslik"].startswith("GEÇEN HAFTANIN ÇALIŞKANLARI")
    saat["an"] = datetime(2026, 10, 26, 10)  # sonraki pazartesi: geçen hafta kimse yapmadı → ekranda mesaj yok
    assert oduller.kiosk_ogeleri(conn) == []


def test_ogrenci_kendi_odulleri_ve_sinif_odulu(conn, ornek, yeni_kullanici, saat):
    kids = []
    for i in range(6):
        kid, oid = _ogr(conn, yeni_kullanici, 870 + i, "10-A")
        kids.append((kid, oid))
        if i < 5:
            _etkinlik(conn, kid, 3 if i else 5)
    oduller.kapat(conn, HB)
    ogr = lambda kid: conn.execute("SELECT * FROM ogrenci WHERE kullanici_id = ?", (kid,)).fetchone()  # noqa: E731
    kazanan = oduller.ogrenci_oduller(conn, ogr(kids[0][0]))
    assert {x["kategori"] for x in kazanan} >= {"etkinlik", "sinif"} and any(x["kahve"] for x in kazanan)
    katilan = oduller.ogrenci_oduller(conn, ogr(kids[2][0]))  # kazanmadı ama sınıfı kazandı ve katıldı
    assert [x["kategori"] for x in katilan if x["kategori"] != "istikrar"] == ["sinif"]
    assert oduller.ogrenci_oduller(conn, ogr(kids[5][0])) == []  # sınıf üyesi ama katılmadı
    assert oduller.ogrenci_oduller(conn, conn.execute("SELECT * FROM ogrenci WHERE id = ?", (ornek["ogr1"],)).fetchone()) == []


def test_kahve_teslim_isareti(conn, ornek, yeni_kullanici, saat):
    a, _ = _ogr(conn, yeni_kullanici, 880)
    _etkinlik(conn, a, 3)
    oduller.kapat(conn, HB)
    oid = conn.execute("SELECT id FROM odul WHERE kahve = 1").fetchone()[0]
    oduller.kahve_teslim(conn, oid, True)
    assert conn.execute("SELECT kahve_teslim FROM odul WHERE id = ?", (oid,)).fetchone()[0]
    oduller.kahve_teslim(conn, oid, False)
    assert conn.execute("SELECT kahve_teslim FROM odul WHERE id = ?", (oid,)).fetchone()[0] is None
    istikrar = conn.execute("SELECT id FROM odul WHERE kategori = 'istikrar'").fetchone()[0]
    with pytest.raises(ValueError):
        oduller.kahve_teslim(conn, istikrar, True)  # yalnızca kahveli ödül


def test_pano_ucu_cuma_ve_pazartesi(conn, ornek, yeni_kullanici, saat):
    a, _ = _ogr(conn, yeni_kullanici, 890, "9-B", "Can Aksu")
    _etkinlik(conn, a, 3, ("2026-10-12", "2026-10-13", "2026-10-14"))
    app = FastAPI()
    app.include_router(pano.router)
    c = TestClient(app, client=("192.168.23.254", 5555))
    saat["an"] = datetime(2026, 10, 14, 10)  # çarşamba
    assert not [d for d in c.get("/api/pano").json()["duyurular"] if "HAFTA" in d["baslik"]]
    saat["an"] = datetime(2026, 10, 16, 10)  # cuma
    d = c.get("/api/pano").json()["duyurular"]
    assert d[0]["baslik"].startswith("HAFTANIN ÇALIŞKANLARI (GEÇİCİ)") and "Can A. (9-B)" in d[0]["metin"]


def test_kazanansiz_hafta_da_kapanir(conn, ornek, yeni_kullanici, saat):
    assert oduller.kapat(conn, HB) == 0
    a, _ = _ogr(conn, yeni_kullanici, 895)
    _etkinlik(conn, a, 5)  # hafta kapandıktan sonra gelen veri
    assert oduller.kapat(conn, HB) == 0 and oduller.kayitli(conn, HB) == []
