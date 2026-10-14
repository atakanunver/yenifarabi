"""Hızlı Etkinlik Atama: ödev oluşturma, yetki (404), çift tıklama, soru sayısı, tekrarsız soru, havuz hatası."""

import auth
import pytest
from fastapi.testclient import TestClient
from kaynaklar import KaynakHatasi, arena_soru, kazanim


@pytest.fixture
def istemci(monkeypatch):
    cagrilar = []

    def sorular(sinif, ders, haric, n=5, gorulme=None):
        cagrilar.append({"sinif": sinif, "ders": ders, "haric": list(haric), "n": n})
        taban = 100 * sinif + len(haric)
        return [{"id": taban + i, "konu": f"Konu{i}", "soru": f"S{taban + i}?", "secenekler": ["a", "b", "c", "d"],
                 "dogru_index": 2, "kazanim_id": None, "kazanim_kod": None, "kazanim_metin": None} for i in range(n)]

    monkeypatch.setattr(arena_soru, "sorular", sorular)
    monkeypatch.setattr(kazanim, "havuz_dersleri", lambda s: ["matematik", "fizik"])
    from app import app

    with TestClient(app) as c:
        c.cagrilar = cagrilar
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def ata(c, csrf, **kw):
    veri = {"csrf": csrf, "sinif": "9-A", "ders": "matematik", "havuz_ders": "matematik", "adet": "5", "sure": "yarin", **kw}
    return c.post("/ogretmen/hizli", data=veri, follow_redirects=False)


def test_form_ve_atama(istemci, ornek, conn, saat):
    csrf = giris(istemci, "hoca", "hoca-sifre")
    f = istemci.get("/ogretmen/hizli")
    assert f.status_code == 200 and "Etkinliği ata" in f.text and 'value="matematik" selected' in f.text
    r = ata(istemci, csrf)
    assert r.status_code == 303
    oid = int(r.headers["location"].rsplit("/", 1)[1])
    o = conn.execute("SELECT * FROM odev WHERE id = ?", (oid,)).fetchone()
    assert (o["sinif"], o["ders"], o["tur"], o["ogretmen_id"]) == ("9-A", "matematik", "test", ornek["ogretmen"])
    assert o["teslim"] == "2026-10-13 23:59:00"
    assert conn.execute("SELECT count(*) FROM odev_soru WHERE odev_id = ?", (oid,)).fetchone()[0] == 5
    # öğrenci ödev listesinde görür
    giris(istemci, "101", "ali-sifre")
    assert "Hızlı etkinlik" in istemci.get("/ogrenci/odevler").text
    giris(istemci, "hoca", "hoca-sifre")
    assert istemci.get(f"/ogretmen/odev/{oid}").status_code == 200  # sonuç sayfası mevcut akıştan


@pytest.mark.parametrize("adet,kod", [("3", 303), ("10", 303), ("7", 400), ("x", 400)])
def test_soru_sayisi(istemci, ornek, adet, kod):
    csrf = giris(istemci, "hoca", "hoca-sifre")
    assert ata(istemci, csrf, adet=adet).status_code == kod


def test_cift_tiklama_tek_etkinlik(istemci, ornek, conn):
    csrf = giris(istemci, "hoca", "hoca-sifre")
    a = ata(istemci, csrf).headers["location"]
    b = ata(istemci, csrf).headers["location"]
    assert a == b and conn.execute("SELECT count(*) FROM odev").fetchone()[0] == 1


def test_yetkisiz_404(istemci, ornek, conn):
    csrf = giris(istemci, "hoca", "hoca-sifre")  # yalnızca 9-A matematik
    assert ata(istemci, csrf, sinif="9-B").status_code == 404
    assert ata(istemci, csrf, ders="fizik").status_code == 404
    assert istemci.get("/ogretmen/hizli?sinif=9-B&ders=matematik").status_code == 404
    c2 = giris(istemci, "101", "ali-sifre")
    assert istemci.get("/ogretmen/hizli").status_code == 404 and ata(istemci, c2).status_code == 404
    assert istemci.post("/ogretmen/hizli", data={"sinif": "9-A"}).status_code in (400, 404)
    assert conn.execute("SELECT count(*) FROM odev").fetchone()[0] == 0


def test_csrf_zorunlu(istemci, ornek):
    giris(istemci, "hoca", "hoca-sifre")
    assert istemci.post("/ogretmen/hizli", data={"sinif": "9-A", "ders": "matematik"}).status_code == 400


def test_yeterli_soru_yoksa_hata(istemci, ornek, conn, monkeypatch):
    monkeypatch.setattr(arena_soru, "sorular", lambda *a, **k: [])
    csrf = giris(istemci, "hoca", "hoca-sifre")
    r = ata(istemci, csrf)
    assert r.status_code == 400 and conn.execute("SELECT count(*) FROM odev").fetchone()[0] == 0


def test_havuz_erisilemez(istemci, ornek, conn, monkeypatch):
    def patla(*a, **k):
        raise KaynakHatasi("pg")

    monkeypatch.setattr(arena_soru, "sorular", patla)
    monkeypatch.setattr(kazanim, "havuz_dersleri", patla)
    csrf = giris(istemci, "hoca", "hoca-sifre")
    assert "ulaşılamıyor" in istemci.get("/ogretmen/hizli").text
    assert ata(istemci, csrf).status_code == 400


def test_onceki_sorular_haric_tutulur(istemci, ornek, conn, saat):
    from datetime import timedelta

    csrf = giris(istemci, "hoca", "hoca-sifre")
    ata(istemci, csrf)
    saat["an"] += timedelta(minutes=5)  # çift tıklama penceresi geçti
    ata(istemci, csrf, adet="3")
    assert len(istemci.cagrilar[1]["haric"]) == 5  # ilk atamanın 5 sorusu hariç tutuldu


def test_yonetici_havuz_dersiyle_atar(istemci, ornek, conn):
    csrf = giris(istemci, "mudur", "mudur-sifre")
    r = ata(istemci, csrf, ders="", havuz_ders="fizik")
    assert r.status_code == 303
    assert conn.execute("SELECT ders FROM odev").fetchone()[0] == "fizik"
    assert ata(istemci, csrf, sinif="99-Z").status_code == 404


def test_analitik_olayi(istemci, ornek, conn):
    import analitik

    csrf = giris(istemci, "hoca", "hoca-sifre")
    ata(istemci, csrf)
    analitik.bosalt()
    assert conn.execute("SELECT count(*) FROM olay WHERE tur = 'ogretmen_hizli_etkinlik'").fetchone()[0] == 1
