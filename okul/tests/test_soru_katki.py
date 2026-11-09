"""Öğretmen soru katkısı (V41): cevap anahtarı, yetki, kuyruk API'si, LLM şıklı soruların onayı."""

import pytest
import soru_katki
from ayarlar import AYAR
from kaynaklar import soru as havuz
from test_web_belge_sinav import giris, istemci, lan_istemci  # noqa: F401

PDF = b"%PDF-1.4\n" + b"x" * 200


def _k(conn, kid):
    return conn.execute("SELECT * FROM kullanici WHERE id = ?", (kid,)).fetchone()


@pytest.mark.parametrize(
    "metin, beklenen",
    [("1-A 2-c 3-B", "ACB"), ("1.A\n2.D\n3)E", "ADE"), ("2-B 1-A", "AB"), ("ac bd", "ACBD"), ("", "")],
)
def test_cevap_coz(metin, beklenen):
    assert soru_katki.cevap_coz(metin) == beklenen


@pytest.mark.parametrize("metin", ["1-A 3-B", "1-F", "ABX", "1-A iki-B"])
def test_cevap_coz_gecersiz(metin):
    with pytest.raises(soru_katki.KatkiHatasi):
        soru_katki.cevap_coz(metin)


def test_gonder_yetki_ve_kuyruk(conn, ornek):
    k = _k(conn, ornek["ogretmen"])  # 9-A matematik
    with pytest.raises(PermissionError):
        soru_katki.gonder(conn, k, 9, "fizik", "", "a.pdf", PDF, "ABCD")
    with pytest.raises(PermissionError):
        soru_katki.gonder(conn, _k(conn, ornek["ogr1_k"]), 9, "matematik", "", "a.pdf", PDF, "AB")
    kid = soru_katki.gonder(conn, k, 9, "matematik", "", "tarama.pdf", PDF, "1-A 2-B")
    assert soru_katki.bekleyenler(conn) == [
        {"id": kid, "sinif": 9, "ders": "matematik", "baslik": "tarama", "cevap": "AB"}
    ]
    soru_katki.sonuc(conn, kid, "isleniyor")
    assert soru_katki.bekleyenler(conn) == []
    conn.execute("UPDATE soru_katki SET islem_zaman = '2000-01-01 00:00:00' WHERE id = ?", (kid,))
    conn.commit()
    assert [r["id"] for r in soru_katki.bekleyenler(conn)] == [kid]  # takılı kalan yeniden sıraya girer
    # yönetici her düzey ve dersi seçebilir
    assert soru_katki.gonder(conn, _k(conn, ornek["yonetici"]), 12, "fizik", "", "b.pdf", PDF, "")


def _askida(monkeypatch):
    sorular = [{"id": 501, "konu": "k", "soru": "s?", "secenekler": ["a", "b", "c", "d"], "dogru_index": 0,
                "kaynak": "x", "sinif": 9, "ders": "matematik", "kaynak_metin": "özgün"}]
    alinan = []
    monkeypatch.setattr(havuz, "onay_bekleyenler", lambda ciftler: (alinan.append(ciftler), sorular)[1])
    return alinan


def test_karar_akisi(conn, ornek, monkeypatch):
    alinan = _askida(monkeypatch)
    k = _k(conn, ornek["ogretmen"])
    assert [s["id"] for s in soru_katki.onay_bekleyenler(conn, k)] == [501]
    assert alinan[0] == [(9, "matematik")]
    with pytest.raises(PermissionError):
        soru_katki.karar_ver(conn, k, 999, "onay")  # öğretmenin dersinde bekleyen soru değil
    with pytest.raises(soru_katki.KatkiHatasi):
        soru_katki.karar_ver(conn, k, 501, "belki")
    soru_katki.karar_ver(conn, k, 501, "onay")
    assert soru_katki.onay_bekleyenler(conn, k) == []  # karar verilen listeden düşer
    assert soru_katki.uygulanacak_kararlar(conn) == [{"soru_id": 501, "karar": "onay"}]
    assert soru_katki.kararlar_uygulandi(conn, [501]) == 1
    assert soru_katki.uygulanacak_kararlar(conn) == []


def test_havuz_kapaliysa_onay_listesi_bos(conn, ornek, monkeypatch):
    def hata(_):
        raise havuz.KaynakHatasi("yok")

    monkeypatch.setattr(havuz, "onay_bekleyenler", hata)
    assert soru_katki.onay_bekleyenler(conn, _k(conn, ornek["ogretmen"])) == []


def test_web_yukleme_ve_karar(istemci, conn, ornek, monkeypatch):  # noqa: F811
    _askida(monkeypatch)
    csrf = giris(istemci, "hoca", "hoca-sifre")
    r = istemci.get("/ogretmen/soru-katki")
    assert r.status_code == 200 and "Onayınızı bekleyen sorular (1)" in r.text
    dosya = {"dosya": ("t.pdf", PDF, "application/pdf")}
    r = istemci.post("/ogretmen/soru-katki", data={"csrf": csrf, "secim": "9|matematik", "cevap": "AB"}, files=dosya)
    assert r.status_code == 422 and "onayını" in r.text  # onay kutusu şart
    r = istemci.post("/ogretmen/soru-katki", data={"csrf": csrf, "secim": "9|matematik", "cevap": "1-A 3-B", "onay": "1"}, files=dosya)
    assert r.status_code == 422 and "eksiksiz" in r.text
    r = istemci.post("/ogretmen/soru-katki", data={"csrf": csrf, "secim": "10|fizik", "cevap": "AB", "onay": "1"}, files=dosya)
    assert r.status_code == 404
    r = istemci.post("/ogretmen/soru-katki", data={"csrf": csrf, "secim": "9|matematik", "cevap": "AB", "onay": "1"},
                     files=dosya, follow_redirects=False)
    assert r.status_code == 303
    assert "Sırada" in istemci.get("/ogretmen/soru-katki").text
    r = istemci.post("/ogretmen/soru-katki/karar", data={"csrf": csrf, "soru_id": "501", "karar": "red"}, follow_redirects=False)
    assert r.status_code == 303
    assert soru_katki.uygulanacak_kararlar(conn) == [{"soru_id": 501, "karar": "red"}]


def test_servis_api(lan_istemci, conn, ornek, monkeypatch):  # noqa: F811
    monkeypatch.setattr(AYAR, "soru_anahtar", "anahtar-x")
    h = {"X-Soru-Anahtar": "anahtar-x"}
    kid = soru_katki.gonder(conn, _k(conn, ornek["ogretmen"]), 9, "matematik", "Föy", "f.pdf", PDF, "AB")
    assert lan_istemci.get("/api/soru-katki").status_code == 404  # anahtarsız
    v = lan_istemci.get("/api/soru-katki", headers=h).json()
    assert [x["id"] for x in v["katkilar"]] == [kid] and v["kararlar"] == []
    r = lan_istemci.get(f"/api/soru-katki/{kid}/pdf", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"%PDF-")
    assert lan_istemci.post(f"/api/soru-katki/{kid}/sonuc", json={"durum": "bitti", "eklenen": 2}, headers=h).status_code == 200
    assert soru_katki.getir(conn, kid)["eklenen"] == 2
    assert lan_istemci.post(f"/api/soru-katki/{kid}/sonuc", json={"durum": "x"}, headers=h).status_code == 400
    assert lan_istemci.post("/api/soru-katki/999/sonuc", json={"durum": "bitti"}, headers=h).status_code == 404
    assert lan_istemci.post("/api/soru-katki/kararlar", json={"uygulandi": [1]}, headers=h).json()["guncellenen"] == 0


def test_arena_filtresi_takma_adla_gecerli():
    """`s` takma adlı sorguda çıplak `soru.id` Postgres'te hata verir (2026-11-07 Bilgi Arenası/etkinlik kırılması)."""
    from kaynaklar import arena_soru

    assert "soru.id" not in arena_soru._F.replace("s.id", "")
    assert "g.soru_id = s.id" in arena_soru._F
