"""Kişisel Gelişim: haftalık hedef, gerçek etkinlikten ilerleme, hedef düşürme kuralı, rozet, yetki."""

import json
from datetime import timedelta

import arena
import auth
import kisisel
import pytest
from fastapi.testclient import TestClient


def _ogr(conn, ornek):
    return conn.execute("SELECT * FROM ogrenci WHERE id = ?", (ornek["ogr1"],)).fetchone()


def _arena_tur(conn, kid, gun):
    conn.execute("INSERT INTO bilgi_tur (kullanici_id, gun, sinif, ders, basla, durum) VALUES (?, ?, '9-A', 'matematik', 't', 'tamam')", (kid, gun))
    conn.commit()


def _maraton(conn, kid, bitis, terk=False):
    mid = conn.execute("INSERT INTO maraton (kullanici_id, sinif, duzey, ders, basla, bitis) VALUES (?, '9-A', 9, 'm', 't', ?)", (kid, bitis)).lastrowid
    conn.execute("INSERT INTO maraton_soru (maraton_id, sira, soru_id, soru, secenekler, dogru_index, cevap) VALUES (?, 1, 1, 's', '[]', 0, ?)", (mid, -2 if terk else 0))
    conn.commit()


def _test_teslim(conn, ornek, o, zaman_, durum="tamam", tur="test"):
    oid = conn.execute("INSERT INTO odev (ogretmen_id, sinif, ders, tur, baslik, teslim, olusturma) VALUES (?, '9-A', 'm', ?, 'T', '2026-10-20 10:00:00', 't')", (ornek["ogretmen"], tur)).lastrowid
    conn.execute("INSERT INTO odev_teslim (odev_id, ogrenci_id, durum, puan, cevaplar, zaman) VALUES (?, ?, ?, 50, ?, ?)", (oid, o["id"], durum, json.dumps({}), zaman_))
    conn.commit()


def test_hafta_basi_pazartesi(saat):
    assert kisisel.hafta_basi() == "2026-10-12"  # saat fixture: pazartesi
    saat["an"] += timedelta(days=6, hours=10)  # pazar
    assert kisisel.hafta_basi() == "2026-10-12"
    saat["an"] += timedelta(days=1)
    assert kisisel.hafta_basi() == "2026-10-19"


def test_hedefsiz_ilerleme_yok(conn, ornek, saat):
    h = kisisel.bu_hafta(conn, _ogr(conn, ornek))
    assert h["hedef"] is None and h["yuzde"] is None and h["kalan"] is None and h["tamamlandi"] is False
    assert h["yapilan"]["toplam"] == 0


def test_gercek_etkinlikler_sayilir(conn, ornek, saat):
    o, k = _ogr(conn, ornek), ornek["ogr1_k"]
    _arena_tur(conn, k, "2026-10-12")
    _arena_tur(conn, k, "2026-10-05")  # geçen hafta: sayılmaz
    _maraton(conn, k, "2026-10-12 11:00:00")
    _maraton(conn, k, "2026-10-12 12:00:00", terk=True)  # terk: sayılmaz
    _test_teslim(conn, ornek, o, "2026-10-12 13:00:00")
    _test_teslim(conn, ornek, o, "2026-10-12 13:30:00", durum="yapti", tur="klasik")  # beyan: sayılmaz
    y = kisisel.etkinlik_sayisi(conn, o["id"], k, "2026-10-12")
    assert y == {"arena": 1, "maraton": 1, "test": 1, "toplam": 3}


def test_hedef_koyma_ve_ilerleme(conn, ornek, saat):
    o, k = _ogr(conn, ornek), ornek["ogr1_k"]
    for kotu in (0, 15, -1):
        with pytest.raises(kisisel.HedefHatasi):
            kisisel.hedef_koy(conn, o, kotu)
    kisisel.hedef_koy(conn, o, 4)
    _arena_tur(conn, k, "2026-10-12")
    h = kisisel.bu_hafta(conn, o)
    assert (h["hedef"], h["yuzde"], h["kalan"], h["tamamlandi"]) == (4, 25, 3, False)
    kisisel.hedef_koy(conn, o, 6)  # yükseltmek serbest
    assert kisisel.bu_hafta(conn, o)["hedef"] == 6


def test_etkinlikten_sonra_hedef_dusurulemez(conn, ornek, saat):
    o = _ogr(conn, ornek)
    kisisel.hedef_koy(conn, o, 5)
    kisisel.hedef_koy(conn, o, 2)  # etkinlik yok: düşürmek serbest
    _arena_tur(conn, ornek["ogr1_k"], "2026-10-12")
    kisisel.hedef_koy(conn, o, 3)
    with pytest.raises(kisisel.HedefHatasi):
        kisisel.hedef_koy(conn, o, 1)
    assert kisisel.bu_hafta(conn, o)["hedef"] == 3


def test_hedef_ulasilinca_tamam_ve_yuzde_tavani(conn, ornek, saat):
    o, k = _ogr(conn, ornek), ornek["ogr1_k"]
    kisisel.hedef_koy(conn, o, 1)
    _arena_tur(conn, k, "2026-10-12")
    _maraton(conn, k, "2026-10-13 10:00:00")
    h = kisisel.bu_hafta(conn, o)
    assert h["tamamlandi"] is True and h["yuzde"] == 100 and h["kalan"] == 0 and h["yapilan"]["toplam"] == 2


def test_gecmis_haftalar(conn, ornek, saat):
    o, k = _ogr(conn, ornek), ornek["ogr1_k"]
    conn.execute("INSERT INTO hedef (kullanici_id, hafta_basi, hedef_sayi, olusturma) VALUES (?, '2026-10-05', 1, 't')", (k,))
    _arena_tur(conn, k, "2026-10-06")
    g = kisisel.gecmis(conn, o)
    assert len(g) == 6 and g[-1]["su_an"] is True and g[-1]["hedef"] is None
    gecen = next(x for x in g if x["hafta_basi"] == "2026-10-05")
    assert gecen["tamam"] is True and gecen["yapilan"] == 1
    assert all(x["hedef"] is None and x["tamam"] is False for x in g if x["hafta_basi"] != "2026-10-05")


def test_hedef_rozetleri(conn, ornek, saat):
    o, k = _ogr(conn, ornek), ornek["ogr1_k"]
    assert kisisel.rozet_kontrol(conn, o) == []
    for i, hb in enumerate(("2026-09-21", "2026-09-28", "2026-10-05")):
        conn.execute("INSERT INTO hedef (kullanici_id, hafta_basi, hedef_sayi, olusturma) VALUES (?, ?, 1, 't')", (k, hb))
        _arena_tur(conn, k, hb)
        assert kisisel.rozet_kontrol(conn, o) == (["hedef_ilk"] if i == 0 else (["hedef_uc"] if i == 2 else []))
    assert kisisel.rozet_kontrol(conn, o) == []  # tekrar verilmez
    kodlar = {r["kod"] for r in arena.rozetler(conn, k) if r["kazanildi"]}
    assert {"hedef_ilk", "hedef_uc"} <= kodlar


def test_ulasilmayan_hedef_rozet_vermez(conn, ornek, saat):
    o, k = _ogr(conn, ornek), ornek["ogr1_k"]
    conn.execute("INSERT INTO hedef (kullanici_id, hafta_basi, hedef_sayi, olusturma) VALUES (?, '2026-10-12', 5, 't')", (k,))
    _arena_tur(conn, k, "2026-10-12")
    assert kisisel.rozet_kontrol(conn, o) == []


# --- rotalar ---


@pytest.fixture
def istemci():
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def test_hedefim_sayfasi_ve_koyma(istemci, ornek, conn, saat):
    csrf = giris(istemci, "101", "ali-sifre")
    g = istemci.get("/ogrenci/hedefim")
    assert g.status_code == 200 and "henüz hedef koymadın" in g.text and "Hedef koy" in g.text
    r = istemci.post("/ogrenci/hedefim", data={"csrf": csrf, "hedef": "4"}, follow_redirects=False)
    assert r.status_code == 303
    t = istemci.get("/ogrenci/hedefim").text
    assert "0</b> / 4 etkinlik" in t and 'aria-valuenow="0"' in t and "İlk Haftalık Hedef" in t
    assert istemci.post("/ogrenci/hedefim", data={"csrf": csrf, "hedef": "99"}).status_code == 400
    assert istemci.post("/ogrenci/hedefim", data={"csrf": csrf, "hedef": "x"}).status_code == 400
    assert conn.execute("SELECT hedef_sayi FROM hedef").fetchone()[0] == 4


def test_yetki_ve_csrf(istemci, ornek, conn):
    giris(istemci, "101", "ali-sifre")
    assert istemci.post("/ogrenci/hedefim", data={"hedef": "3"}).status_code == 400  # csrf yok
    for kadi, sifre in (("hoca", "hoca-sifre"), ("mudur", "mudur-sifre")):
        c2 = giris(istemci, kadi, sifre)
        assert istemci.get("/ogrenci/hedefim").status_code == 404
        assert istemci.post("/ogrenci/hedefim", data={"csrf": c2, "hedef": "3"}).status_code == 404
    istemci.cookies.clear()
    istemci.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, ornek["veli1"]))
    assert istemci.get("/ogrenci/hedefim").status_code == 404
    assert conn.execute("SELECT count(*) FROM hedef").fetchone()[0] == 0


def test_baskasinin_hedefi_gorunmez(istemci, ornek, conn, saat):
    csrf = giris(istemci, "101", "ali-sifre")
    istemci.post("/ogrenci/hedefim", data={"csrf": csrf, "hedef": "9"})
    giris(istemci, "201", "ayse-sifre")
    t = istemci.get("/ogrenci/hedefim").text
    assert "henüz hedef koymadın" in t and "/ 9 etkinlik" not in t


def _etkinlik_gunleri(conn, ornek, gunler):
    for g in gunler:
        conn.execute(
            "INSERT INTO bilgi_tur (kullanici_id, gun, sinif, ders, basla, durum) VALUES (?, ?, '9-A', 'matematik', ?, 'tamam')",
            (ornek["ogr1_k"], g, g + " 10:00:00"),
        )
    conn.commit()


def test_calisma_serisi_hafta_sonu_bozmaz(conn, ornek, saat):
    o = conn.execute("SELECT * FROM ogrenci WHERE id = ?", (ornek["ogr1"],)).fetchone()
    assert kisisel.calisma_serisi(conn, o) == 0
    # saat: 12 Ekim 2026 Pazartesi. Cuma 9, Perşembe 8 ve Pazartesi 12 çalışıldı; hafta sonu arada
    _etkinlik_gunleri(conn, ornek, ["2026-10-08", "2026-10-09", "2026-10-12"])
    assert kisisel.calisma_serisi(conn, o) == 3


def test_calisma_serisi_bugun_bos_dunle_surer_bos_okul_gunu_keser(conn, ornek, saat):
    o = conn.execute("SELECT * FROM ogrenci WHERE id = ?", (ornek["ogr1"],)).fetchone()
    _etkinlik_gunleri(conn, ornek, ["2026-10-08", "2026-10-09"])  # bugün (Pzt 12) boş: Cuma ile süren seri
    assert kisisel.calisma_serisi(conn, o) == 2
    saat["an"] = saat["an"].replace(day=14)  # Çarşamba: Salı 13 boş okul günü → seri kesilir
    assert kisisel.calisma_serisi(conn, o) == 0


def test_ana_ekranda_calisma_serisi(conn, ornek, saat):
    from app import app

    _etkinlik_gunleri(conn, ornek, ["2026-10-08", "2026-10-09", "2026-10-12"])
    c = TestClient(app)
    assert c.post("/giris", data={"kullanici_adi": "101", "sifre": "ali-sifre"}, follow_redirects=False).status_code == 303
    assert "3</b> gündür üst üste" in c.get("/ogrenci").text
