"""Ana ekran 'Bugün ne yapacağım?': gerçek kayıtlardan görev, öncelik, boş durum, kilit."""

import json

import arena
import bugun
import kisisel
import maraton
import pytest
from kaynaklar import arena_soru
from kaynaklar import soru as havuz


@pytest.fixture(autouse=True)
def havuz_var(monkeypatch):
    monkeypatch.setattr(maraton, "kilit", lambda: None)
    monkeypatch.setattr(havuz, "dersler", lambda s: [("matematik", 40)])
    monkeypatch.setattr(arena_soru, "sorular", lambda sinif, ders, haric, n=5, g=None: [
        {"id": 100 + len(haric) + i, "konu": "K", "soru": "S?", "secenekler": ["a", "b"], "dogru_index": 1,
         "kazanim_id": 1, "kazanim_kod": "K.1", "kazanim_metin": "M"} for i in range(n)])


def _ogr(conn, ornek):
    return conn.execute("SELECT * FROM ogrenci WHERE id = ?", (ornek["ogr1"],)).fetchone()


def _odev(conn, ornek, baslik, teslim, sinif="9-A"):
    return conn.execute(
        "INSERT INTO odev (ogretmen_id, sinif, ders, tur, baslik, teslim, olusturma) VALUES (?, ?, 'matematik', 'klasik', ?, ?, 't')",
        (ornek["ogretmen"], sinif, baslik, teslim)).lastrowid


def test_hicbir_sey_yoksa_yalnizca_yapilabilir_gorevler(conn, ornek, saat, monkeypatch):
    monkeypatch.setattr(havuz, "dersler", lambda s: [])  # havuzda yeterli soru yok: Arena görevi yok
    r = bugun.gorevler(conn, _ogr(conn, ornek))
    assert [g["tur"] for g in r["gorevler"]] == ["hedef"]  # yalnızca "hedef koy"
    assert r["tamamlanan"] == [] and r["fazla_odev"] == 0


def test_oncelik_acil_odev_once(conn, ornek, saat):
    _odev(conn, ornek, "Yarınki", "2026-10-13 09:00:00")  # 24 saat içinde: acil
    _odev(conn, ornek, "Uzak", "2026-10-30 09:00:00")
    r = bugun.gorevler(conn, _ogr(conn, ornek))
    tur = [(g["tur"], g["baslik"]) for g in r["gorevler"]]
    assert tur[0] == ("odev", "Yarınki")
    assert ("odev", "Uzak") in tur
    assert r["gorevler"][0]["acil"] is True and r["gorevler"][0]["href"].startswith("/ogrenci/odev/")


def test_gecmis_odev_en_basta_ve_fazla_sayisi(conn, ornek, saat):
    for i in range(4):
        _odev(conn, ornek, f"O{i}", f"2026-10-{10 + i} 09:00:00")  # ilk ikisi vadesi geçmiş
    r = bugun.gorevler(conn, _ogr(conn, ornek))
    odevler_ = [g for g in r["gorevler"] if g["tur"] == "odev"]
    assert [g["baslik"] for g in odevler_] == ["O0", "O1"] and all(g["acil"] for g in odevler_)
    assert r["fazla_odev"] == 2


def test_teslim_edilen_odev_gorev_degil(conn, ornek, saat):
    oid = _odev(conn, ornek, "Yapıldı", "2026-10-13 09:00:00")
    conn.execute("INSERT INTO odev_teslim (odev_id, ogrenci_id, durum, zaman) VALUES (?, ?, 'yapti', '2026-10-12 08:00:00')", (oid, ornek["ogr1"]))
    conn.commit()
    r = bugun.gorevler(conn, _ogr(conn, ornek))
    assert not [g for g in r["gorevler"] if g["tur"] == "odev"]
    assert "Bugün 1 ödev teslim ettin" in r["tamamlanan"]


def test_arena_gorevi_durumlari(conn, ornek, saat):
    o = _ogr(conn, ornek)
    r = bugun.gorevler(conn, o)
    g = next(g for g in r["gorevler"] if g["tur"] == "arena")
    assert g["baslik"] == "Günlük Görev" and g["href"] == "/ogrenci/arena"
    tur = arena.baslat(conn, ornek["ogr1_k"], "9-A")
    arena.cevapla(conn, tur, 1, 1)
    g = next(g for g in bugun.gorevler(conn, o)["gorevler"] if g["tur"] == "arena")
    assert "devam et" in g["baslik"] and g["href"] == f"/ogrenci/arena/{tur}"
    for sira in range(2, 6):
        arena.cevapla(conn, tur, sira, 1)
    r = bugun.gorevler(conn, o)
    assert not [g for g in r["gorevler"] if g["tur"] == "arena"]
    assert any("Günlük Görev tamamlandı (5/5 doğru)" in t for t in r["tamamlanan"])


def test_ders_saatinde_arena_kilitli_gorunur(conn, ornek, saat, monkeypatch):
    monkeypatch.setattr(maraton, "kilit", lambda: {"bit": "10:30", "no": 3})
    g = next(g for g in bugun.gorevler(conn, _ogr(conn, ornek))["gorevler"] if g["tur"] == "arena")
    assert g.get("kilitli") is True and "10:30" in g["alt"] and g["href"] == ""


def test_12_sinif_arena_gorevi_yok(conn, ornek, saat):
    conn.execute("UPDATE ogrenci SET sinif = '12-A' WHERE id = ?", (ornek["ogr1"],))
    conn.commit()
    assert not [g for g in bugun.gorevler(conn, _ogr(conn, ornek))["gorevler"] if g["tur"] == "arena"]


def test_hedef_gorevi_yalniz_hedefsizken(conn, ornek, saat):
    o = _ogr(conn, ornek)
    assert "hedef" in [g["tur"] for g in bugun.gorevler(conn, o)["gorevler"]]
    kisisel.hedef_koy(conn, o, 3)
    assert "hedef" not in [g["tur"] for g in bugun.gorevler(conn, o)["gorevler"]]


def test_yaklasan_sinav_hatirlatmasi(conn, ornek, saat):
    conn.execute("INSERT INTO sinav (tur, baslik, tarih, sinif, ders, yazar_id, olusturma) VALUES ('yazili', 'Mat yazılı', '2026-10-14', '9-A', 'matematik', ?, 't')", (ornek["ogretmen"],))
    conn.commit()
    g = next(g for g in bugun.gorevler(conn, _ogr(conn, ornek))["gorevler"] if g["tur"] == "sinav")
    assert g["baslik"] == "Mat yazılı yaklaşıyor" and "2 gün sonra · kısa" in g["alt"] and g["acil"] is False
    conn.execute("UPDATE sinav SET tarih = '2026-10-12'")
    conn.commit()
    g = next(g for g in bugun.gorevler(conn, _ogr(conn, ornek))["gorevler"] if g["tur"] == "sinav")
    assert g["alt"].startswith("Bugün · kısa") and g["acil"] is True


def test_tekrar_onerisi_ve_azami_gorev(conn, ornek, saat):
    o = _ogr(conn, ornek)
    tur = arena.baslat(conn, ornek["ogr1_k"], "9-A")
    for sira in range(1, 6):
        arena.cevapla(conn, tur, sira, 0)  # hepsi yanlış → tekrar önerisi
    for i in range(5):
        _odev(conn, ornek, f"O{i}", f"2026-10-2{i} 09:00:00")
    r = bugun.gorevler(conn, o)
    assert len(r["gorevler"]) <= bugun.MAX_GOREV
    r2 = bugun.gorevler(conn, o)
    assert json.dumps([g["baslik"] for g in r["gorevler"]]) == json.dumps([g["baslik"] for g in r2["gorevler"]])  # kararlı
