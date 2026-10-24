"""Serbest çalışma + yanlışları tekrar: havuz kuralları, sunucu taraflı cevap, XP/hedefe bağlı olmama, yetki."""

import json

import arena
import auth
import calisma
import kisisel
import maraton
import pytest
import soru_bildirim
from fastapi.testclient import TestClient
from kaynaklar import arena_soru
from kaynaklar import soru as havuz

SECENEK = json.dumps(["a", "b", "c"])


def _tur(conn, kid, gun="2026-10-10"):
    return conn.execute(
        "INSERT INTO bilgi_tur (kullanici_id, gun, sinif, ders, basla, durum) VALUES (?, ?, '9-A', 'matematik', ?, 'tamam')",
        (kid, gun, gun + " 09:00:00"),
    ).lastrowid


def _arena_cevap(conn, tur, sira, soru_id, cevap, zaman_):
    conn.execute(
        "INSERT INTO bilgi_cevap (tur_id, sira, soru_id, kazanim_kod, soru, secenekler, dogru_index, cevap, cevap_zamani)"
        " VALUES (?, ?, ?, 'MAT.1', ?, ?, 1, ?, ?)",
        (tur, sira, soru_id, f"Soru {soru_id}?", SECENEK, cevap, zaman_),
    )
    conn.commit()


def _yanlis(conn, kid, soru_id, gun="2026-10-10"):
    _arena_cevap(conn, _tur(conn, kid, gun), 1, soru_id, 0, gun + " 09:05:00")


@pytest.fixture
def sahte(monkeypatch):
    sorulanlar = []

    def sorular(sinif, ders, haric, n=5, gorulme=None, yasak=None, kazanim_id=None):
        sorulanlar.append({"ders": ders, "kazanim_id": kazanim_id, "haric": list(haric)})
        return [{"id": 900, "konu": "K", "soru": "Serbest?", "secenekler": ["a", "b", "c"], "dogru_index": 2,
                 "kazanim_id": 7, "kazanim_kod": "MAT.9.1", "kazanim_metin": "M"}]

    monkeypatch.setattr(arena_soru, "sorular", sorular)
    monkeypatch.setattr(arena_soru, "kazanimlar", lambda s, d, y=None, en_az=3: [{"id": 7, "kod": "MAT.9.1", "metin": "M", "adet": 5}])
    monkeypatch.setattr(havuz, "dersler", lambda s: [("matematik", 40), ("fizik", 20)])
    monkeypatch.setattr(maraton, "kilit", lambda: None)
    return sorulanlar


def test_tekrar_havuzu_kurallari(conn, ornek, saat):
    k = ornek["ogr1_k"]
    _yanlis(conn, k, 1, gun="2026-10-08")  # tekrar edilecek
    _yanlis(conn, k, 2, gun="2026-10-09")
    _yanlis(conn, k, 3, gun="2026-08-01")  # 30 günden eski
    _arena_cevap(conn, _tur(conn, k, "2026-10-11"), 1, 2, 1, "2026-10-11 09:00:00")  # 2 sonradan doğru yapıldı
    _arena_cevap(conn, _tur(conn, k, "2026-10-07"), 1, 4, -3, "2026-10-07 09:00:00")  # pas: yanlış sayılmaz
    assert {s["sid"] for s in calisma.yanlislar(conn, k)} == {1}
    # öğretmen bildirimi (ağırlık 2 = eşik): soru okulda gizlenir
    conn.execute("INSERT INTO soru_bildirim (soru_id, kullanici_id, tur, zaman, rol, kaynak) VALUES (1, ?, 'cevap', '2026-10-11 10:00:00', 'ogretmen', 'x')", (ornek["ogretmen"],))
    conn.commit()
    assert 1 in soru_bildirim.gizli_idler(conn) and calisma.yanlislar(conn, k) == []
    assert calisma.yanlislar(conn, ornek["ogr2_k"]) == []  # başkasının yanlışı görünmez


def test_tekrar_akisi_xp_ve_hedefe_baglanmaz(conn, ornek, saat):
    k = ornek["ogr1_k"]
    _yanlis(conn, k, 1)
    o = conn.execute("SELECT * FROM ogrenci WHERE id = ?", (ornek["ogr1"],)).fetchone()
    seri_once = kisisel.calisma_serisi(conn, o)
    cid = calisma.tekrar_baslat(conn, k)
    assert calisma.tekrar_baslat(conn, k) == cid  # yenilemek soru değiştirmez
    sonuc = calisma.cevapla(conn, k, cid, 1)
    assert sonuc == {"dogru": True, "dogru_index": 1, "gayret_xp": 0}  # anında cevap: gayret XP yok
    with pytest.raises(calisma.CalismaHatasi):
        calisma.cevapla(conn, k, cid, 0)  # çift gönderim
    assert calisma.yanlislar(conn, k) == []
    assert arena.toplam_xp(conn, k) == 0
    o = conn.execute("SELECT * FROM ogrenci WHERE id = ?", (ornek["ogr1"],)).fetchone()
    assert kisisel.calisma_serisi(conn, o) == seri_once + 1  # çalışma bugünü seriye ekler
    assert kisisel.etkinlik_sayisi(conn, o["id"], k, "2026-10-12")["toplam"] == 0  # haftalık hedefe sayılmaz
    with pytest.raises(calisma.CalismaHatasi):
        calisma.tekrar_baslat(conn, k)


def test_bugun_yanlis_yapilan_ayni_gun_tekrar_gelmez(conn, ornek, saat):
    k = ornek["ogr1_k"]
    _yanlis(conn, k, 1)
    cid = calisma.tekrar_baslat(conn, k)
    calisma.cevapla(conn, k, cid, 0)  # tekrarda da yanlış
    assert calisma.yanlislar(conn, k) == []  # aynı soru bugün döngüye girmez
    saat["an"] = saat["an"].replace(day=13)
    assert {s["sid"] for s in calisma.yanlislar(conn, k)} == {1}  # ertesi gün yine tekrar edilir


def test_serbest_baslat(conn, ornek, sahte, saat):
    k = ornek["ogr1_k"]
    with pytest.raises(calisma.CalismaHatasi):
        calisma.serbest_baslat(conn, k, "9-A", "kimya", None)  # havuz dersi değil
    with pytest.raises(calisma.CalismaHatasi):
        calisma.serbest_baslat(conn, k, "9-A", "matematik", 99)  # listede olmayan kazanım
    cid = calisma.serbest_baslat(conn, k, "9-A", "matematik", 7)
    assert sahte[-1]["kazanim_id"] == 7
    c = calisma.getir(conn, cid, k)
    assert (c["kaynak"], c["ders"], c["soru_id"], c["dogru_index"]) == ("serbest", "matematik", 900, 2)
    assert calisma.serbest_baslat(conn, k, "9-A", "fizik", None) == cid  # açık soru varken yenisi verilmez


def _istemci(conn, kadi, sifre):
    from app import app

    c = TestClient(app)
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303
    return c, auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def test_web_dogru_sik_cevaptan_once_yok_ve_yetki(conn, ornek, sahte, saat):
    c, csrf = _istemci(conn, "101", "ali-sifre")
    assert "Konu seçerek çalış" in c.get("/ogrenci/calisma").text
    r = c.post("/ogrenci/calisma/serbest/basla", data={"csrf": csrf, "ders": "matematik", "kazanim": "7"}, follow_redirects=False)
    assert r.status_code == 303
    yol = r.headers["location"]
    sayfa = c.get(yol).text
    assert "Serbest?" in sayfa and "doğru cevap" not in sayfa and "Doğru!" not in sayfa
    cid = int(yol.rsplit("/", 1)[1])
    assert c.post(f"/ogrenci/calisma/{cid}/cevap", data={"csrf": csrf, "sec": "2"}, follow_redirects=False).status_code == 303
    assert "Doğru!" in c.get(yol).text
    assert "Sorun mu var" in c.get(yol).text or "sorun mu var" in c.get(yol).text.lower()
    # çalışma sorusu da bildirilebilir (gördü_mu)
    assert c.post("/ogrenci/soru-bildir", data={"csrf": csrf, "soru_id": "900", "tur": "cevap", "geri": yol}, follow_redirects=False).status_code == 303
    # başka öğrenci 404; öğretmen 404
    c2, _ = _istemci(conn, "201", "ayse-sifre")
    assert c2.get(yol).status_code == 404
    c3, _ = _istemci(conn, "hoca", "hoca-sifre")
    assert c3.get("/ogrenci/calisma").status_code == 404
    # XP yazılmadı
    assert conn.execute("SELECT count(*) FROM bilgi_xp").fetchone()[0] == 0


def test_web_gec_ve_csrf(conn, ornek, sahte, saat):
    k = ornek["ogr1_k"]
    c, csrf = _istemci(conn, "101", "ali-sifre")
    cid = calisma.serbest_baslat(conn, k, "9-A", "matematik", None)
    assert c.post(f"/ogrenci/calisma/{cid}/gec", data={}, follow_redirects=False).status_code in (403, 400, 404)  # csrf yok
    assert c.post(f"/ogrenci/calisma/{cid}/gec", data={"csrf": csrf}, follow_redirects=False).status_code == 303
    assert calisma.getir(conn, cid, k)["cevap"] == calisma.PAS
    assert calisma.acik(conn, k) is None


def test_on_ikinci_sinif_kapali(conn, ornek, sahte, saat):
    conn.execute("UPDATE ogrenci SET sinif = '12-A' WHERE id = ?", (ornek["ogr1"],))
    conn.commit()
    c, _ = _istemci(conn, "101", "ali-sifre")
    assert c.get("/ogrenci/calisma").status_code == 404
