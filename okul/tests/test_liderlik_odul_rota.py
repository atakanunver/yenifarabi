"""Arena liderliği ve haftalık ödül ekranları: sıralama, hile önlemi, gizlilik, yetki, kahve takibi."""

from datetime import datetime, timedelta

import auth
import oduller
import pytest
from fastapi.testclient import TestClient
from kaynaklar import arena_soru, kazanim
from kaynaklar import soru as havuz


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setattr(havuz, "dersler", lambda s: [("matematik", 40)])
    monkeypatch.setattr(arena_soru, "sorular", lambda *a, **k: [])
    monkeypatch.setattr(kazanim, "form_sonuclari", lambda okul_no: [])
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def _ogr(conn, yeni_kullanici, no, sinif, ad):
    kid = yeni_kullanici(conn, "ogrenci", ad, str(no), sifre="x")
    conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (?, ?, ?, ?)", (no, ad, sinif, kid))
    conn.commit()
    return kid


def _gorev(conn, kid, gun, dogru=5, sure=120):
    b = datetime.strptime(gun + " 15:00:00", "%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO bilgi_tur (kullanici_id, gun, sinif, ders, basla, bitis, durum, dogru) VALUES (?, ?, 'x', 'm', ?, ?, 'tamam', ?)",
                 (kid, gun, b.strftime("%Y-%m-%d %H:%M:%S"), (b + timedelta(seconds=sure)).strftime("%Y-%m-%d %H:%M:%S"), dogru))
    conn.commit()


def _xp(conn, kid, miktar, gun, ref):
    conn.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (?, 'arena_bonus', ?, ?, ?, 'z')", (kid, ref, miktar, gun))
    conn.commit()


def test_liderlik_modulu(conn, ornek, yeni_kullanici, saat):
    a = _ogr(conn, yeni_kullanici, 900, "9-A", "Ayşe Yılmaz Kaya")
    b = _ogr(conn, yeni_kullanici, 901, "10-A", "Burak Aydın")
    c = _ogr(conn, yeni_kullanici, 902, "11-A", "Cem Demir")
    _gorev(conn, a, "2026-10-12", dogru=5)
    _gorev(conn, b, "2026-10-12", dogru=3)
    _gorev(conn, b, "2026-10-13", dogru=3)
    _gorev(conn, c, "2026-10-12", dogru=3, sure=10)  # çok kısa: sayılmaz
    _xp(conn, a, 60, "2026-10-12", "1")
    _xp(conn, b, 40, "2026-10-13", "2")
    _xp(conn, c, 900, "2026-10-05", "3")  # geçen hafta
    t = oduller.liderlik(conn, "2026-10-12", a)
    assert [(x["ad"], x["deger"]) for x in t["xp"]["ilk"]] == [("Ayşe Yılmaz K.", 60), ("Burak A.", 40)]
    assert [(x["ad"], x["deger"]) for x in t["dogru"]["ilk"]] == [("Burak A.", 6), ("Ayşe Yılmaz K.", 5)]
    assert [(x["ad"], x["deger"]) for x in t["cozulen"]["ilk"]] == [("Burak A.", 10), ("Ayşe Yılmaz K.", 5)]
    assert t["xp"]["ilk"][0]["ben"] is True and t["xp"]["benim"] is None
    tum = oduller.liderlik(conn, None)
    assert tum["xp"]["ilk"][0]["ad"] == "Cem D." and tum["xp"]["ilk"][0]["deger"] == 900  # tüm zamanlar xp


def test_esit_deger_ayni_sira_ve_ilk_on(conn, ornek, yeni_kullanici, saat):
    for i in range(12):
        k = _ogr(conn, yeni_kullanici, 910 + i, "9-A", f"Ogr{i:02d} Soy")
        _xp(conn, k, 100 if i < 2 else 10 + i, "2026-10-12", str(i))
    me = conn.execute("SELECT kullanici_id FROM ogrenci WHERE okul_no = 911").fetchone()[0]
    sirali = oduller.liderlik(conn, "2026-10-12", me)["xp"]
    assert len(sirali["ilk"]) == 10 and [x["sira"] for x in sirali["ilk"]][:3] == [1, 1, 3]
    t = oduller.liderlik(conn, "2026-10-12", conn.execute("SELECT kullanici_id FROM ogrenci WHERE okul_no = 910").fetchone()[0])
    assert t["xp"]["benim"] is None  # ilk 10'daysa ayrıca gösterilmez
    son = conn.execute("SELECT kullanici_id FROM ogrenci WHERE okul_no = 912").fetchone()[0]
    assert oduller.liderlik(conn, "2026-10-12", son)["xp"]["benim"]["sira"] >= 11


def test_liderlik_sayfasi_ve_yetki(istemci, ornek, yeni_kullanici, conn, saat):
    a = _ogr(conn, yeni_kullanici, 930, "9-A", "Deniz Çelik Tan")
    _xp(conn, a, 70, "2026-10-12", "1")
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci/arena/liderlik").text
    assert "Liderlik" in t and "Deniz Çelik T." in t and "70 XP" in t and "Tan" not in t.replace("Tan.", "")
    assert "Tüm zamanlar" in istemci.get("/ogrenci/arena/liderlik?donem=tum").text
    assert "Deniz Çelik T." in istemci.get("/ogrenci/arena/liderlik?donem=gecersiz").text  # geçersiz dönem → hafta
    hub = istemci.get("/ogrenci/arena").text
    assert "XP liderleri" in hub and "Deniz Çelik T." in hub
    for kadi, sifre in (("hoca", "hoca-sifre"), ("mudur", "mudur-sifre")):
        giris(istemci, kadi, sifre)
        assert istemci.get("/ogrenci/arena/liderlik").status_code == 404


def test_liderlik_12_sinif_dahil_ama_arena_xp_yok(conn, ornek, yeni_kullanici, saat):
    k = _ogr(conn, yeni_kullanici, 940, "12-A", "On İki")
    b = datetime(2026, 10, 12, 16)
    mid = conn.execute("INSERT INTO maraton (kullanici_id, sinif, duzey, ders, basla, bitis, dogru) VALUES (?, '12-A', 12, 'm', ?, ?, 7)",
                       (k, b.strftime("%Y-%m-%d %H:%M:%S"), (b + timedelta(seconds=300)).strftime("%Y-%m-%d %H:%M:%S"))).lastrowid
    conn.execute("INSERT INTO maraton_soru (maraton_id, sira, soru_id, soru, secenekler, dogru_index, cevap) VALUES (?, 1, 1, 's', '[]', 0, 0)", (mid,))
    conn.commit()
    t = oduller.liderlik(conn, "2026-10-12")
    assert [x["deger"] for x in t["dogru"]["ilk"]] == [7] and t["xp"]["ilk"] == []


def _hafta_odulu(conn, yeni_kullanici):
    a = _ogr(conn, yeni_kullanici, 950, "11-B", "Kahve Kazanan")
    for g in ("2026-10-05", "2026-10-06", "2026-10-07"):
        _gorev(conn, a, g)
    return a


def test_yonetici_odul_ekrani_ve_kahve(istemci, ornek, yeni_kullanici, conn, saat):
    _hafta_odulu(conn, yeni_kullanici)
    csrf = giris(istemci, "mudur", "mudur-sifre")
    t = istemci.get("/yonetici/oduller").text
    assert "Haftalık ödüller" in t and "Kahve Kazanan (11-B)" in t and "Kahve bekliyor" in t
    oid = conn.execute("SELECT id FROM odul WHERE kahve = 1").fetchone()[0]
    assert istemci.post(f"/yonetici/oduller/{oid}/kahve", data={"csrf": csrf, "teslim": "1"}, follow_redirects=False).status_code == 303
    assert "Kahve verildi" in istemci.get("/yonetici/oduller").text
    assert istemci.post(f"/yonetici/oduller/{oid}/kahve", data={"teslim": "0"}).status_code == 400  # csrf yok
    assert istemci.post("/yonetici/oduller/9999/kahve", data={"csrf": csrf, "teslim": "1"}).status_code == 404
    for kadi, sifre in (("hoca", "hoca-sifre"), ("101", "ali-sifre")):
        c2 = giris(istemci, kadi, sifre)
        assert istemci.get("/yonetici/oduller").status_code == 404
        assert istemci.post(f"/yonetici/oduller/{oid}/kahve", data={"csrf": c2, "teslim": "0"}).status_code == 404
    assert conn.execute("SELECT kahve_teslim FROM odul WHERE id = ?", (oid,)).fetchone()[0]  # yetkisizler değiştiremedi


def test_ogrenci_kendi_odulunu_ve_kurallari_gorur(istemci, ornek, yeni_kullanici, conn, saat):
    a = _hafta_odulu(conn, yeni_kullanici)
    oduller.kapat(conn, "2026-10-05")
    giris(istemci, "950", "x")
    t = istemci.get("/ogrenci/hedefim").text
    assert "Haftalık ödüllerim" in t and "Haftanın Çalışkanı" in t and "Nescafe kahve ödülünü kazandın" in t
    assert "en az 3" in t
    giris(istemci, "101", "ali-sifre")  # başkası: kendi ödülü yok, başkasınınkini görmez
    t2 = istemci.get("/ogrenci/hedefim").text
    assert "Henüz haftalık ödülün yok" in t2 and "Kahve Kazanan" not in t2 and a


def test_ust_siradakine_fark(conn, ornek, yeni_kullanici, saat):
    a = _ogr(conn, yeni_kullanici, 960, "9-A", "Ayşe Bir")
    b = _ogr(conn, yeni_kullanici, 961, "9-A", "Burak İki")
    c = _ogr(conn, yeni_kullanici, 962, "9-A", "Cem Üç")
    for kid, xp in ((a, 100), (b, 70), (c, 70)):
        _xp(conn, kid, xp, "2026-10-12", str(kid))
    t = oduller.liderlik(conn, "2026-10-12", b)["xp"]
    assert t["ben"]["sira"] == 2 and t["ust"] == {"ad": "Ayşe B.", "sira": 1, "fark": 30}
    assert oduller.liderlik(conn, "2026-10-12", a)["xp"]["ust"] is None  # birinci: üstü yok
    kimse = oduller.liderlik(conn, "2026-10-12", ornek["ogr1_k"])["xp"]
    assert kimse["ben"] is None and kimse["ust"] is None  # listede olmayana mesaj yok
