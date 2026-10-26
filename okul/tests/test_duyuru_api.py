from tests.test_web_belge_sinav import istemci, lan_istemci  # noqa: F401
from ayarlar import AYAR

import duyurular

GOVDE = {"hedef": "veli", "baslik": "Toplantı", "metin": "Cuma 14:00", "gecerlilik_gun": 7}


def _k(conn, kid):
    return conn.execute("SELECT * FROM kullanici WHERE id = ?", (kid,)).fetchone()


def test_anahtar_tunel_ve_ekleme(lan_istemci, conn, ornek, yeni_kullanici, monkeypatch):
    yeni_kullanici(conn, "yonetici", "Atakan Ünver", kullanici_adi="atakan")
    monkeypatch.setattr(AYAR, "duyuru_anahtar", "gizli")
    assert lan_istemci.post("/api/duyuru-ekle", json=GOVDE).status_code == 404
    assert lan_istemci.post("/api/duyuru-ekle", json=GOVDE, headers={"X-Duyuru-Anahtar": "yanlis"}).status_code == 404
    h = {"X-Duyuru-Anahtar": "gizli"}
    assert lan_istemci.post("/api/duyuru-ekle", json=GOVDE, headers={**h, "CF-Ray": "x"}).status_code == 404
    assert lan_istemci.post("/api/duyuru-ekle", json={**GOVDE, "hedef": "yonetici"}, headers=h).status_code == 400
    assert lan_istemci.post("/api/duyuru-ekle", json={**GOVDE, "metin": " "}, headers=h).status_code == 400
    r = lan_istemci.post("/api/duyuru-ekle", json=GOVDE, headers=h)
    assert r.status_code == 200 and r.json()["tamam"]
    d = conn.execute("SELECT * FROM duyuru WHERE id = ?", (r.json()["id"],)).fetchone()
    assert (d["hedef_tur"], d["hedef"], d["baslik"]) == ("rol", "veli", "Toplantı") and d["bitis"]
    assert "Toplantı" in {x["baslik"] for x in duyurular.gorunur_duyurular(conn, _k(conn, ornek["veli1"]))}
    assert "Toplantı" not in {x["baslik"] for x in duyurular.gorunur_duyurular(conn, _k(conn, ornek["ogr1_k"]))}
    monkeypatch.setattr(AYAR, "duyuru_anahtar", "")  # anahtar tanımsızsa uç kapalı
    assert lan_istemci.post("/api/duyuru-ekle", json=GOVDE, headers={"X-Duyuru-Anahtar": ""}).status_code == 404
