"""Öğretmenin günlük 5 soru incelemesi: ders eşlemesi, sabit set, tekrarsızlık, hatalı → bildirim, yetki."""

import inceleme
import pytest
import soru_bildirim
from kaynaklar import soru as havuz

from tests.test_web_belge_sinav import giris, istemci  # noqa: F401


def _sahte_havuz(monkeypatch, adet=30):
    cagrilar = []

    def adaylar(sinif, ders, haric, yasak, n=40):
        cagrilar.append((sinif, ders))
        return [
            {"id": 1000 * sinif + i, "konu": "K", "soru": f"Soru {i}?", "secenekler": ["a", "b", "c", "d"],
             "dogru_index": 1, "kaynak": "Kitap s. 1"}
            for i in range(adet)
            if 1000 * sinif + i not in haric and 1000 * sinif + i not in yasak
        ]

    monkeypatch.setattr(havuz, "inceleme_adaylari", adaylar)
    monkeypatch.setattr(havuz, "getir_tam", lambda idler: {i: {"id": i, "konu": "K", "soru": f"S{i}", "secenekler": ["a", "b", "c", "d"], "dogru_index": 1, "kaynak": "Kitap"} for i in idler})
    monkeypatch.setattr(havuz, "getir", lambda idler: {i: {"soru": "s", "ders": "matematik", "sinif": 9, "durum": "onayli"} for i in idler})
    return cagrilar


def test_ders_esleme():
    assert inceleme.havuz_kodu("türk dili ve edebiyatı") == "edebiyat"
    assert inceleme.havuz_kodu("inkılap tarihi ve atatürkçülük") == "tarih"
    assert inceleme.havuz_kodu("din kültürü ve ahlak bilgisi") == "din"
    assert inceleme.havuz_kodu("coğrafya") == "cografya" and inceleme.havuz_kodu("rehberlik") is None


def test_ciftler_12_sinif_ve_eslesmeyen_elenir(conn, ornek):
    o = ornek["ogretmen"]
    conn.executemany("INSERT INTO ogretmen_gorev (ogretmen_id, sinif, ders) VALUES (?, ?, ?)",
                     [(o, "12-A", "fizik"), (o, "10-B", "fizik"), (o, "9-B", "rehberlik")])
    conn.commit()
    assert inceleme.ciftler(conn, o) == [(9, "matematik"), (10, "fizik")]  # 9-A matematik ornek'ten gelir


def test_set_5_soru_sabit_ve_tekrarsiz(conn, ornek, monkeypatch):
    _sahte_havuz(monkeypatch)
    k = conn.execute("SELECT * FROM kullanici WHERE id = ?", (ornek["ogretmen"],)).fetchone()
    s1 = inceleme.gunun_seti(conn, k)
    assert len(s1) == 5 and len({s["soru_id"] for s in s1}) == 5
    assert [s["soru_id"] for s in inceleme.gunun_seti(conn, k)] == [s["soru_id"] for s in s1]  # yenileme aynı set
    assert inceleme.kart(conn, k) == {"yapilan": 0, "toplam": 5}


def test_hatali_bildirim_yazar_ve_gizler(conn, ornek, monkeypatch):
    _sahte_havuz(monkeypatch)
    k = conn.execute("SELECT * FROM kullanici WHERE id = ?", (ornek["ogretmen"],)).fetchone()
    s = inceleme.gunun_seti(conn, k)
    inceleme.isle(conn, k, 1, "dogru")
    inceleme.isle(conn, k, 2, "hatali", "sekil")
    inceleme.isle(conn, k, 3, "pas")
    with pytest.raises(inceleme.IncelemeHatasi):
        inceleme.isle(conn, k, 1, "pas")  # tek işaret
    with pytest.raises(inceleme.IncelemeHatasi):
        inceleme.isle(conn, k, 4, "hatali", "")  # sebep zorunlu
    assert soru_bildirim.gizli_idler(conn) == [s[1]["soru_id"]]
    b = conn.execute("SELECT rol, kaynak, tur FROM soru_bildirim").fetchone()
    assert (b["rol"], b["kaynak"], b["tur"]) == ("ogretmen", "inceleme", "sekil")
    assert inceleme.kart(conn, k) == {"yapilan": 3, "toplam": 5}
    assert inceleme.bugun_ozeti(conn) == {"ogretmen": 1, "soru": 3, "hatali": 1}


def test_ders_yoksa_kart_yok(conn, ornek):
    conn.execute("DELETE FROM ogretmen_gorev"); conn.commit()
    k = conn.execute("SELECT * FROM kullanici WHERE id = ?", (ornek["ogretmen"],)).fetchone()
    assert inceleme.kart(conn, k) is None
    y = conn.execute("SELECT * FROM kullanici WHERE id = ?", (ornek["yonetici"],)).fetchone()
    assert inceleme.kart(conn, y) is None


def test_web_akis_ve_yetki(istemci, conn, ornek, monkeypatch):
    _sahte_havuz(monkeypatch)
    csrf = giris(istemci, "101", "ali-sifre")  # öğrenci
    assert istemci.get("/ogretmen/inceleme").status_code == 404
    csrf = giris(istemci, "mudur", "mudur-sifre")  # yönetici: kendi dersi yok
    assert istemci.get("/ogretmen/inceleme").status_code == 404
    csrf = giris(istemci, "hoca", "hoca-sifre")
    ana = istemci.get("/ogretmen").text
    assert "Bugünün 5 sorusu" in ana and "İncele (0/5)" in ana
    r = istemci.get("/ogretmen/inceleme")
    assert r.status_code == 200 and "işaretli doğru cevap" in r.text and r.text.count('name="sonuc" value="dogru"') == 5
    assert istemci.post("/ogretmen/inceleme/1", data={"csrf": csrf, "sonuc": "dogru"}, follow_redirects=False).status_code == 303
    assert istemci.post("/ogretmen/inceleme/2", data={"csrf": csrf, "tur": "sacma"}, follow_redirects=False).status_code == 303
    assert "İncele (2/5)" in istemci.get("/ogretmen").text
    r = istemci.post("/ogretmen/inceleme/1", data={"csrf": csrf, "sonuc": "pas"}, follow_redirects=True)
    assert "zaten işaretledin" in r.text
    assert istemci.post("/ogretmen/inceleme/3", data={"csrf": "yanlis", "sonuc": "dogru"}).status_code == 400
    giris(istemci, "mudur", "mudur-sifre")
    assert "1</b> öğretmen" in istemci.get("/yonetici/soru-bildirimleri").text
