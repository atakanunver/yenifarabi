"""Gayret (süreç) XP'si: formül, günlük sınır, sınıf kapsamı, çift gönderim; Maraton/Günlük Görev/Çalışma entegrasyonu; göç."""

import sqlite3
from datetime import datetime, timedelta

import pytest

import arena
import calisma
import db
import gayret
import maraton
from kaynaklar import arena_soru
from kaynaklar import soru as havuz


def gayret_xp(conn, kid):
    return conn.execute("SELECT COALESCE(SUM(miktar), 0) FROM bilgi_xp WHERE kullanici_id = ? AND kaynak = 'gayret'", (kid,)).fetchone()[0]


@pytest.mark.parametrize(
    ("saniye", "beklenen"),
    [(0, 0), (4.9, 0), (5, 0), (9.9, 0), (10, 1), (35, 3), (59, 5), (60, 6), (600, 6)],  # 5 sn altı yok, 60 sn'de kırpılır
)
def test_xp_formulu(saniye, beklenen):
    assert gayret.xp_hesapla(saniye) == beklenen


def test_gecen_saniye():
    assert gayret.gecen("2026-10-12 10:00:00", "2026-10-12 10:00:42") == 42
    assert gayret.gecen(None, "2026-10-12 10:00:42") == 0
    assert gayret.gecen("2026-10-12 10:01:00", "2026-10-12 10:00:00") == 0  # negatif olmaz


def test_gunluk_sinir_cift_gonderim_ve_ertesi_gun(conn, ornek, saat):
    kid = ornek["ogr1_k"]
    for i in range(10):  # 10 soru x 60 sn = 60 XP
        assert gayret.ver(conn, kid, f"t:{i}", 90) == 6
    assert gayret.ver(conn, kid, "t:11", 90) == 0  # günlük 60 doldu
    assert gayret_xp(conn, kid) == 60
    saat["an"] += timedelta(days=1)
    assert gayret.ver(conn, kid, "t:12", 90) == 6  # yeni gün
    assert gayret.ver(conn, kid, "t:12", 90) == 0  # aynı ref ikinci kez yazılmaz
    assert gayret_xp(conn, kid) == 66


def test_son_kalan_miktar_kirpilir(conn, ornek):
    kid = ornek["ogr1_k"]
    for i in range(9):
        gayret.ver(conn, kid, f"t:{i}", 60)  # 54 XP
    assert gayret.ver(conn, kid, "t:9", 60) == 6
    assert gayret.ver(conn, kid, "t:10", 60) == 0
    kid2 = ornek["ogr2_k"]
    for i in range(10):
        gayret.ver(conn, kid2, f"u:{i}", 60)
    assert gayret.ver(conn, kid2, "u:99", 60) == 0 and gayret_xp(conn, kid2) == 60  # kişi başına ayrı sayaç


def test_sinif_kapsami_12_sinif_xp_almaz(conn, ornek):
    kid = ornek["ogr1_k"]
    conn.execute("UPDATE ogrenci SET sinif = '12-A' WHERE kullanici_id = ?", (kid,))
    conn.commit()
    assert gayret.ver(conn, kid, "t:1", 60) == 0
    conn.execute("UPDATE ogrenci SET sinif = '9-A' WHERE kullanici_id = ?", (kid,))
    conn.commit()
    assert gayret.ver(conn, kid, "t:1", 60) == 6


def test_ogrenci_olmayan_kullanici_xp_almaz(conn, ornek):
    assert gayret.ver(conn, ornek["yonetici"], "t:1", 60) == 0


@pytest.fixture
def sahte(monkeypatch):
    def sorular(sinif, ders, haric, n=5, gorulme=None, yasak=None, kazanim_id=None):
        return [{"id": 100 * sinif + i, "konu": "K", "soru": f"S{i}?", "secenekler": ["a", "b", "c"], "dogru_index": 1,
                 "kazanim_id": 7, "kazanim_kod": "MAT.9.1", "kazanim_metin": "Metin"} for i in range(n)]

    monkeypatch.setattr(arena_soru, "sorular", sorular)
    monkeypatch.setattr(arena_soru, "kazanimlar", lambda s, d, y=None, en_az=3: [{"id": 7, "kod": "MAT.9.1", "metin": "M", "adet": 5}])
    monkeypatch.setattr(havuz, "dersler", lambda s: [("matematik", 40), ("fizik", 20)])
    monkeypatch.setattr(maraton, "kilit", lambda: None)


def test_gunluk_gorev_soru_basina_sure_xp_yazar_yanlis_da_sayilir(conn, ornek, sahte, saat):
    k = ornek["ogr1_k"]
    tur = arena.baslat(conn, k, "9-A")
    saat["an"] += timedelta(seconds=30)
    r1 = arena.cevapla(conn, tur, 1, 1)  # doğru, 30 sn -> 3 gayret + 10 doğru
    assert r1["gayret_xp"] == 3 and r1["xp"] == 13
    saat["an"] += timedelta(seconds=45)
    r2 = arena.cevapla(conn, tur, 2, 0)  # YANLIŞ, 45 sn -> 4 gayret, doğru XP yok
    assert r2["gayret_xp"] == 4 and r2["xp"] == 4
    saat["an"] += timedelta(seconds=2)
    r3 = arena.cevapla(conn, tur, 3, 1)  # 2 sn: anında cevap, gayret yok
    assert r3["gayret_xp"] == 0
    assert gayret_xp(conn, k) == 7
    assert conn.execute("SELECT xp FROM bilgi_tur WHERE id = ?", (tur,)).fetchone()[0] == 13 + 4 + 10  # tur XP'sine dahil


def test_calisma_gayret_xp(conn, ornek, sahte, saat):
    k = ornek["ogr1_k"]
    cid = calisma.serbest_baslat(conn, k, "9-A", "matematik", None)
    saat["an"] += timedelta(seconds=80)  # 60'a kırpılır -> 6 XP
    r = calisma.cevapla(conn, k, cid, 0)  # yanlış da olsa
    assert r["gayret_xp"] == 6 and arena.toplam_xp(conn, k) == 6
    with pytest.raises(calisma.CalismaHatasi):
        calisma.cevapla(conn, k, cid, 0)  # çift gönderim: ikinci XP yok
    assert arena.toplam_xp(conn, k) == 6


def test_maraton_gayret_xp_sure_dolumu_ve_aninda_cevap_sayilmaz(conn, ornek, monkeypatch, saat):
    saat["an"] = datetime(2026, 10, 17, 10, 0)  # noqa: DTZ001 - cumartesi
    monkeypatch.setattr(havuz, "sorular", lambda *a, **kw: [
        {"id": i, "soru": f"S{i}", "secenekler": ["a", "b", "c", "d"], "dogru_index": 0, "konu": "k", "kaynak": "x"}
        for i in range(1, 11)])
    k = ornek["ogr1_k"]
    mid = maraton.baslat(conn, k, "9-A", "tarih")
    maraton.siradaki(conn, mid)
    saat["an"] += timedelta(seconds=25)
    r1 = maraton.cevapla(conn, mid, 1, 1)  # yanlış, 25 sn -> 2 XP
    assert r1["gayret_xp"] == 2
    maraton.siradaki(conn, mid)
    saat["an"] += timedelta(seconds=1)
    assert maraton.cevapla(conn, mid, 2, 0)["gayret_xp"] == 0  # anında cevap
    maraton.siradaki(conn, mid)
    saat["an"] += timedelta(seconds=40)
    r3 = maraton.cevapla(conn, mid, 3, None)  # süre doldu / cevap yok
    assert r3["gayret_xp"] == 0
    assert gayret_xp(conn, k) == 2


def test_gocu_kaynak_kisitina_gayret_eklenir_eski_veri_korunur(tmp_path):
    from scripts import geri_al

    c = sqlite3.connect(tmp_path / "t.db")
    c.executescript("\n".join(db.GOCLER[:32]))  # V32'de: bilgi_xp 'gayret' kabul etmez
    c.execute("PRAGMA foreign_keys = OFF")
    c.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (1, 'arena_dogru', 'r', 10, '2026-10-12', 'z')")
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (1, 'gayret', 'g', 3, '2026-10-12', 'z')")
    c.commit()
    c.executescript(db.GOCLER[32])  # V33
    assert c.execute("SELECT COUNT(*) FROM bilgi_xp WHERE kaynak = 'arena_dogru'").fetchone()[0] == 1  # eski veri kaldı
    c.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (1, 'gayret', 'g', 3, '2026-10-12', 'z')")
    c.commit()
    assert 33 in geri_al.GERI
    c.executescript(geri_al.GERI[33])
    assert c.execute("SELECT kaynak FROM bilgi_xp").fetchall() == [("arena_dogru",)]  # gayret satırları silinir, diğerleri kalır
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (1, 'gayret', 'g2', 3, '2026-10-12', 'z')")


def test_gayret_yazilan_ve_calisma_ekraninda_gosterilir(conn, ornek, sahte, saat, monkeypatch):
    from fastapi.testclient import TestClient

    import auth
    from app import app

    k = ornek["ogr1_k"]
    cid = calisma.serbest_baslat(conn, k, "9-A", "matematik", None)
    saat["an"] += timedelta(seconds=50)
    calisma.cevapla(conn, k, cid, 0)
    assert gayret.yazilan(conn, k, f"c{cid}") == 5 and gayret.yazilan(conn, k, "yok") == 0
    with TestClient(app) as c:
        c.post("/giris", data={"kullanici_adi": "101", "sifre": "ali-sifre"}, follow_redirects=False)
        assert auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))
        sayfa = c.get(f"/ogrenci/calisma/{cid}")
    assert sayfa.status_code == 200 and "+5 gayret XP" in sayfa.text
