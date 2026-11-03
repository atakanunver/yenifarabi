import duyurular
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rotalar import pano


def _istemci(host):
    app = FastAPI()
    app.include_router(pano.router)
    return TestClient(app, client=(host, 5555))


def test_lan_okul_duyurusu_doner(conn, ornek, saat):
    duyurular.duyuru_ekle(conn, ornek["yonetici"], "Okul", "x", "okul")
    duyurular.duyuru_ekle(conn, ornek["yonetici"], "9A", "x", "sinif", "9-A")
    r = _istemci("192.168.23.254").get("/api/pano")
    assert r.status_code == 200
    assert [d["baslik"] for d in r.json()["duyurular"]] == ["Okul"]


def test_tunel_ve_dis_ip_404(conn, ornek, saat):
    assert _istemci("192.168.23.254").get("/api/pano", headers={"cf-ray": "1"}).status_code == 404
    assert _istemci("8.8.8.8").get("/api/pano").status_code == 404


def test_belirli_gunler_alani(conn, ornek, saat):
    from datetime import datetime

    saat["an"] = datetime(2026, 10, 29, 9, 0)  # noqa: DTZ001 — Cumhuriyet Bayramı + Kızılay Haftası
    j = _istemci("192.168.23.254").get("/api/pano").json()
    assert [g["ad"] for g in j["belirli_gunler"]] == ["Cumhuriyet Bayramı", "Kızılay Haftası"]
    assert j["belirli_gunler"][1] == {"ad": "Kızılay Haftası", "tur": "hafta", "metin": "29 Ekim – 4 Kasım"}
    saat["an"] = datetime(2026, 10, 20, 9, 0)  # noqa: DTZ001
    assert _istemci("192.168.23.254").get("/api/pano").json()["belirli_gunler"] == []


def test_belirli_gunler_hata_panoyu_dusurmez(conn, ornek, saat, monkeypatch):
    def patla():
        raise RuntimeError("x")

    monkeypatch.setattr(pano.belirli_gunler, "bugun", patla)
    r = _istemci("192.168.23.254").get("/api/pano")
    assert r.status_code == 200 and r.json()["belirli_gunler"] == []


def test_yaklasan_deneme_panoda(conn, ornek, saat):
    from datetime import datetime

    import sinavlar

    hoca = conn.execute("SELECT * FROM kullanici WHERE id = ?", (ornek["ogretmen"],)).fetchone()
    sinavlar.deneme_ekle(conn, hoca, "MEBİ 3. YKS Denemesi", "2026-11-09", ["11", "12"],
                         "mebi.eba.gov.tr", bitis="2026-11-15")
    saat["an"] = datetime(2026, 11, 5, 9, 0)  # noqa: DTZ001
    j = _istemci("192.168.23.254").get("/api/pano").json()
    assert j["yaklasan_denemeler"] == [] and j["duyurular"] == []
    saat["an"] = datetime(2026, 11, 8, 9, 0)  # noqa: DTZ001
    j = _istemci("192.168.23.254").get("/api/pano").json()
    assert j["duyurular"][0] == {"baslik": "MEBİ 3. YKS Denemesi",
                                 "metin": "9–15 Kasım · 1 gün kaldı — mebi.eba.gov.tr"}
    assert j["yaklasan_denemeler"][0]["duzeyler"] == "11,12"
