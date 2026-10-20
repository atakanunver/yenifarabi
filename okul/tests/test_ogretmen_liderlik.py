"""Öğretmen liderlik ekranları, soru bazlı etkinlik sonucu ve kazanım ısı haritası."""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import auth
import oduller
import odevler
import pytest
from deps import TEMPLATES
from fastapi.testclient import TestClient
from kaynaklar import arena_soru, kazanim
from kaynaklar import soru as havuz

HB = "2026-10-12"  # saat fixture'ı: pazartesi; geçen hafta 2026-10-05


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
    oid = conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (?, ?, ?, ?)", (no, ad, sinif, kid)).lastrowid
    conn.commit()
    return kid, oid


def _gorev(conn, kid, gun, dogru=5):
    b = datetime.strptime(gun + " 15:00:00", "%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO bilgi_tur (kullanici_id, gun, sinif, ders, basla, bitis, durum, dogru) VALUES (?, ?, 'x', 'm', ?, ?, 'tamam', ?)",
                 (kid, gun, b.strftime("%Y-%m-%d %H:%M:%S"), (b + timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S"), dogru))
    conn.commit()


def _xp(conn, kid, miktar, gun, ref):
    conn.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (?, 'arena_bonus', ?, ?, ?, 'z')", (kid, ref, miktar, gun))
    conn.commit()


@pytest.fixture
def sinif9(conn, ornek, yeni_kullanici):
    """9-A: Ali Veli (ornek), Cem, Deniz; 9-B: Ayşe Kaya (ornek). Cem 90 XP, Ali 40 XP, Deniz hiç oynamadı."""
    cem, _ = _ogr(conn, yeni_kullanici, 301, "9-A", "Cem Demir")
    deniz, _ = _ogr(conn, yeni_kullanici, 302, "9-A", "Deniz Acar")
    _gorev(conn, cem, HB, dogru=5)
    _gorev(conn, ornek["ogr1_k"], HB, dogru=3)
    _xp(conn, cem, 90, HB, "1")
    _xp(conn, ornek["ogr1_k"], 40, HB, "2")
    _gorev(conn, ornek["ogr2_k"], HB, dogru=2)
    _xp(conn, ornek["ogr2_k"], 20, HB, "3")
    return {"cem": cem, "deniz": deniz}


def test_sinif_liderlik_tum_ogrenciler_ve_sira(conn, ornek, sinif9, saat):
    t = oduller.sinif_liderlik(conn, "9-A", HB)
    assert [o["ad_soyad"] for o in t["satirlar"]] == ["Cem Demir", "Ali Veli", "Deniz Acar"]
    assert [o["sira"] for o in t["satirlar"]] == [1, 2, 3]
    assert (t["katilan"], t["mevcut"]) == (2, 3)
    deniz = t["satirlar"][2]
    assert (deniz["xp"], deniz["dogru"], deniz["etkinlik"]) == (0, 0, 0)
    # tüm zamanlar: geçen haftanın XP'si de sayılır
    _xp(conn, sinif9["deniz"], 500, "2026-10-01", "9")
    assert oduller.sinif_liderlik(conn, "9-A", None)["satirlar"][0]["ad_soyad"] == "Deniz Acar"
    assert oduller.sinif_liderlik(conn, "9-A", HB)["satirlar"][2]["ad_soyad"] == "Deniz Acar"


def test_yukselenler(conn, ornek, sinif9, saat):
    # geçen hafta Ali önde (100), Cem 10; bu hafta Cem 90, Ali 40 → Cem yükselir
    _xp(conn, ornek["ogr1_k"], 100, "2026-10-06", "a")
    _xp(conn, sinif9["cem"], 10, "2026-10-06", "b")
    y = oduller.yukselenler(conn, "9-A", HB)
    assert [(x["ad_soyad"], x["once"], x["simdi"], x["atlama"]) for x in y] == [("Cem Demir", 2, 1, 1)]
    # geçen hafta hiç oynamayan (Deniz, sonda) Ali'yi geçerse yükselen sayılır; düşen Ali ve XP'si 0 olan sayılmaz
    _xp(conn, sinif9["deniz"], 50, HB, "d")
    adlar = [x["ad_soyad"] for x in oduller.yukselenler(conn, "9-A", HB)]
    assert "Deniz Acar" in adlar and "Ali Veli" not in adlar


def test_sinif_ozetleri_oran_ve_lider_gizliligi(conn, ornek, sinif9, saat):
    o = {s["sinif"]: s for s in oduller.sinif_ozetleri(conn, HB, {"9-A"})}
    assert (o["9-A"]["mevcut"], o["9-A"]["katilan"], o["9-A"]["oran"]) == (3, 2, 67)
    assert o["9-A"]["xp"] == 130 and o["9-A"]["ort_xp"] == 65 and o["9-A"]["lider"] == "Cem D."
    assert o["9-B"]["oran"] == 100 and o["9-B"]["lider"] is None  # başka sınıfın lideri verilmez
    s = oduller.sinif_ozetleri(conn, HB)
    assert [x["sinif"] for x in s] == ["9-B", "9-A"]  # önce katılım oranı


def test_ogretmen_kendi_sinifini_gorur(istemci, conn, ornek, sinif9, saat):
    giris(istemci, "hoca", "hoca-sifre")
    r = istemci.get("/ogretmen/liderlik/9-A")
    assert r.status_code == 200 and "Cem Demir" in r.text and "Deniz Acar" in r.text and "Ali Veli" in r.text
    assert istemci.get("/ogretmen/liderlik/9-B").status_code == 404
    assert istemci.get("/ogretmen/liderlik/9-A?donem=tum").status_code == 200
    assert istemci.get("/ogretmen/liderlik/yok").status_code == 404


def test_genel_ekran_baska_sinif_ogrencisi_gorunmez(istemci, conn, ornek, sinif9, saat):
    giris(istemci, "hoca", "hoca-sifre")
    r = istemci.get("/ogretmen/liderlik")
    assert r.status_code == 200 and "9-B" in r.text and "9-A" in r.text
    assert "Ayşe Kaya" not in r.text  # 9-B öğrencisi (sınıf ödülü satırı hariç, sadece toplamlar)
    ana = istemci.get("/ogretmen")
    assert ana.status_code == 200 and "Yarışmalar bu hafta" in ana.text and "lider <b>Cem D.</b>" in ana.text
    assert "Ayşe" not in ana.text


def test_yonetici_her_sinifi_gorur_ogrenci_ve_veli_gormez(istemci, conn, ornek, sinif9, saat):
    giris(istemci, "mudur", "mudur-sifre")
    assert istemci.get("/ogretmen/liderlik/9-B").status_code == 200
    giris(istemci, "101", "ali-sifre")
    assert istemci.get("/ogretmen/liderlik").status_code == 404
    assert istemci.get("/ogretmen/liderlik/9-A").status_code == 404


def test_erisim_kaydi_yazilir(istemci, conn, ornek, sinif9, saat):
    giris(istemci, "hoca", "hoca-sifre")
    istemci.get("/ogretmen/liderlik/9-A")
    assert conn.execute("SELECT COUNT(*) FROM erisim_log WHERE eylem = 'sinif_liderlik:9-A'").fetchone()[0] == 1


# ---- Hızlı Etkinlik / test ödevi: soru bazlı sonuç ----

def _test_odevi(conn, ornek, cevaplar_listesi, sinif="9-A"):
    od = conn.execute("INSERT INTO odev (ogretmen_id, sinif, ders, tur, baslik, teslim, olusturma) VALUES (?, ?, 'matematik', 'test', 'T', '2026-12-01', 't')",
                      (ornek["ogretmen"], sinif)).lastrowid
    idler = []
    for sira in (1, 2, 3):
        idler.append(conn.execute("INSERT INTO odev_soru (odev_id, sira, metin, siklar, dogru, kazanim) VALUES (?, ?, ?, ?, 0, 'K')",
                                  (od, sira, f"Soru metni {sira}", json.dumps(["a", "b", "c", "d"]))).lastrowid)
    for oid, secim in cevaplar_listesi:
        cev = {str(i): s for i, s in zip(idler, secim) if s is not None}
        conn.execute("INSERT INTO odev_teslim (odev_id, ogrenci_id, durum, puan, cevaplar, zaman) VALUES (?, ?, 'tamam', 0, ?, 'z')", (od, oid, json.dumps(cev)))
    conn.commit()
    return od


def test_soru_istatistik(conn, ornek, yeni_kullanici, sinif9):
    _, o2 = _ogr(conn, yeni_kullanici, 303, "9-A", "Ece Tan")
    od = _test_odevi(conn, ornek, [(ornek["ogr1"], [0, 1, 1]), (o2, [0, 2, None])])
    ist = odevler.soru_istatistik(conn, conn.execute("SELECT * FROM odev WHERE id = ?", (od,)).fetchone())
    assert [(x["sira"], x["dogru"], x["cevaplayan"], x["yuzde"]) for x in ist] == [(1, 2, 2, 100), (2, 0, 2, 0), (3, 0, 2, 0)]
    assert ist[1]["yanlis_dagilim"] == {"1": 1, "2": 1} and ist[2]["yanlis_dagilim"] == {"1": 1, "bos": 1}
    assert [x["tekrar"] for x in ist] == [False, True, True]  # en düşük 3 içinde ve < %70
    assert "ogrenci" not in str(ist) and "Ali" not in str(ist)  # kimlik yok
    klasik = conn.execute("INSERT INTO odev (ogretmen_id, sinif, ders, tur, baslik, teslim, olusturma) VALUES (?, '9-A', 'm', 'klasik', 'K', '2026-12-01', 't')", (ornek["ogretmen"],)).lastrowid
    assert odevler.soru_istatistik(conn, conn.execute("SELECT * FROM odev WHERE id = ?", (klasik,)).fetchone()) == []


def test_odev_sonuc_sayfasi_soru_bolumu(istemci, conn, ornek, saat):
    od = _test_odevi(conn, ornek, [(ornek["ogr1"], [0, 1, 0])])
    giris(istemci, "hoca", "hoca-sifre")
    r = istemci.get(f"/ogretmen/odev/{od}")
    assert r.status_code == 200 and "Soru bazında sınıf" in r.text and "Yarın tekrar edilebilir" in r.text and "Soru 2" in r.text
    bos = _test_odevi(conn, ornek, [])  # kimse çözmedi: bölüm yok
    assert "Soru bazında sınıf" not in istemci.get(f"/ogretmen/odev/{bos}").text


# ---- Gelişim raporu: kazanım ısı haritası ----

def test_isi_haritasi_sablon():
    kaz = [{"kazanim": f"Kazanım {i}", "ogrenci": 6, "basarili": 3, "oran": o, "yuzde": o} for i, o in enumerate((20, 50, 70, 90))]
    r = {"sinif": "9-A", "mevcut": 8, "verili_ogrenci": 6, "esik_n": 5, "min_soru": 5, "odev_orani": None, "calisan": 0,
         "ogrenciler": [], "kaynak_erisildi": True,
         "dersler": [{"ders": "matematik", "ogrenci": 6, "gizli": False, "soru": 40, "yuzde": 60, "trend": None, "kazanimlar": kaz}]}
    s = TEMPLATES.get_template("ogretmen/gelisim_sinif.html").render(
        r=r, ders="", tum_dersler=[], k={"id": 1, "rol": "ogretmen", "ad_soyad": "T", "foto": None, "sifre_degismeli": 0}, csrf="c",
        bugun_gun="Sal", request=SimpleNamespace(url=SimpleNamespace(path="/ogretmen/gelisim/9-A")))
    assert s.count('class="isi isi-') == 4
    for sev, oran, ad in ((1, 20, "Çok zayıf"), (2, 50, "Zayıf"), (3, 70, "Orta"), (4, 90, "İyi")):
        assert f"isi isi-{sev}" in s and f"%{oran}" in s and ad in s  # renk + yüzde + yazı


# --- öğretmene açılan okul geneli yarışma tabloları (öğrencinin gördüğüyle aynı veri) ---

def _maraton(conn, kid, sinif, puan, gun=HB):
    conn.execute(
        "INSERT INTO maraton (kullanici_id, sinif, duzey, ders, basla, bitis, puan, dogru) VALUES (?, ?, 9, 'matematik', ?, ?, ?, 5)",
        (kid, sinif, gun + " 10:00:00", gun + " 10:05:00", puan),
    )
    conn.commit()


def test_ogretmen_maraton_ve_arena_okul_geneli_gorur(istemci, conn, ornek, sinif9, saat):
    _maraton(conn, sinif9["cem"], "9-A", 80)
    _maraton(conn, ornek["ogr2_k"], "9-B", 95)  # başka sınıf: kısa adla okul tablosunda görünür
    giris(istemci, "hoca", "hoca-sifre")
    r = istemci.get("/ogretmen/liderlik")
    assert r.status_code == 200
    assert "Soru Maratonu" in r.text and "Bilgi Arenası" in r.text and "En çok XP" in r.text
    assert "Ayşe K." in r.text and "Cem D." in r.text  # kısa adlar (öğrencinin gördüğü gibi)
    assert "Ayşe Kaya" not in r.text and "Cem Demir" not in r.text  # tam ad yok
    assert "Sınıflarımdaki öğrenciler" in r.text
    assert r.text.index("Ayşe K.") < r.text.index("Cem D.")  # 95 > 80: maraton sırası


def test_maraton_tablosu_ogrenciyle_ayni_veri(istemci, conn, ornek, sinif9, saat):
    import maraton

    _maraton(conn, sinif9["cem"], "9-A", 80)
    _maraton(conn, ornek["ogr2_k"], "9-B", 95)
    giris(istemci, "hoca", "hoca-sifre")
    r = istemci.get("/ogretmen/liderlik")
    for d in maraton.liderlik(conn):
        assert d["ad"] in r.text


def test_arena_donem_tum_zamanlar(istemci, conn, ornek, sinif9, saat):
    _xp(conn, sinif9["deniz"], 500, "2026-10-01", "t1")
    giris(istemci, "hoca", "hoca-sifre")
    assert "Deniz A." not in istemci.get("/ogretmen/liderlik").text  # bu hafta yok
    r = istemci.get("/ogretmen/liderlik?donem=tum")
    assert r.status_code == 200 and "Deniz A." in r.text
    assert istemci.get("/ogretmen/liderlik?donem=zzz").status_code == 200  # geçersiz değer haftaya düşer


def test_yarisma_tablolari_ogrenci_ve_veliye_kapali(istemci, conn, ornek, sinif9, saat):
    giris(istemci, "101", "ali-sifre")
    assert istemci.get("/ogretmen/liderlik").status_code == 404
    giris(istemci, "mudur", "mudur-sifre")
    assert "Soru Maratonu" in istemci.get("/ogretmen/liderlik").text  # yönetici de görür


def test_ana_sayfalarda_yarisma_baglantisi_hep_gorunur(istemci, conn, ornek, saat):
    giris(istemci, "hoca", "hoca-sifre")
    assert 'href="/ogretmen/liderlik"' in istemci.get("/ogretmen").text
    giris(istemci, "mudur", "mudur-sifre")
    assert 'href="/ogretmen/liderlik"' in istemci.get("/yonetici").text


def test_odev_sonuc_havuz_sorusunda_isaretle_dugmesi(istemci, conn, ornek, saat):
    od = _test_odevi(conn, ornek, [(ornek["ogr1"], [0, 1, 0])])
    conn.execute("UPDATE odev_soru SET kaynak = 'havuz:55' WHERE odev_id = ? AND sira = 1", (od,))
    conn.commit()
    giris(istemci, "hoca", "hoca-sifre")
    h = istemci.get(f"/ogretmen/odev/{od}").text
    assert h.count("data-isaretle ") == 5 and 'data-soru-id="55"' in h  # yalnızca havuz kaynaklı soruda, 5 sebep
    assert "/static/soru-isaretle.js" in h
