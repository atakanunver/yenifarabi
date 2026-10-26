from tests.test_web_belge_sinav import lan_istemci  # noqa: F401
from ayarlar import AYAR

GOVDE = {"okul_no_listesi": [101]}


def test_anahtar_tunel_ve_bildirim(lan_istemci, conn, ornek, monkeypatch):
    monkeypatch.setattr(AYAR, "devamsizlik_anahtar", "gizli")
    assert lan_istemci.post("/api/devamsizlik-bildir", json=GOVDE).status_code == 404
    assert lan_istemci.post("/api/devamsizlik-bildir", json=GOVDE, headers={"X-Devamsizlik-Anahtar": "yanlis"}).status_code == 404
    h = {"X-Devamsizlik-Anahtar": "gizli"}
    assert lan_istemci.post("/api/devamsizlik-bildir", json=GOVDE, headers={**h, "CF-Ray": "x"}).status_code == 404
    assert lan_istemci.post("/api/devamsizlik-bildir", json={"okul_no_listesi": ["yok"]}, headers=h).status_code == 400
    r = lan_istemci.post("/api/devamsizlik-bildir", json=GOVDE, headers=h)
    assert r.status_code == 200 and r.json()["tamam"]
    monkeypatch.setattr(AYAR, "devamsizlik_anahtar", "")  # anahtar tanımsızsa uç kapalı
    assert lan_istemci.post("/api/devamsizlik-bildir", json=GOVDE, headers={"X-Devamsizlik-Anahtar": ""}).status_code == 404


def test_alicilar_veliyi_bulur(conn, ornek):
    import push

    push.abone_ol(conn, ornek["veli1"], "https://fcm.googleapis.com/fcm/send/abc123", "p", "a")
    alicilar = push.devamsizlik_alicilari(conn, [101])
    assert alicilar == [ornek["veli1"]]
    assert push.devamsizlik_alicilari(conn, []) == []
