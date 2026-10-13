"""Bilgi Arenası rotaları: yetki (404), CSRF, cevap sızıntısı, çift/paralel gönderim, kilit, havuz hatası, Maraton XP."""

import threading

import arena
import auth
import maraton
import pytest
from fastapi.testclient import TestClient
from kaynaklar import KaynakHatasi, arena_soru, kazanim
from kaynaklar import soru as havuz

JSON = {"Accept": "application/json"}
ZIL = {
    "dersler": [{"no": 3, "baslangic": "09:50", "bitis": "10:30"}],
    "ogle_arasi": {"baslangic": "12:10", "bitis": "13:30"},
    "ders_gunleri": [1, 2, 3, 4, 5],
}


@pytest.fixture
def istemci(monkeypatch):
    def sorular(sinif, ders, haric, n=5, gorulme=None):
        return [
            {"id": 7000 + i, "konu": "Konu", "soru": f"Arena sorusu {7000 + i}?",
             "secenekler": ["a", "b", "c", "d"], "dogru_index": 2, "kazanim_id": 3,
             "kazanim_kod": "MAT.9.1", "kazanim_metin": "Bir kazanım"}
            for i in range(n)
        ]

    monkeypatch.setattr(arena_soru, "sorular", sorular)
    monkeypatch.setattr(havuz, "dersler", lambda s: [("matematik", 40)])
    monkeypatch.setattr(havuz, "sorular", lambda sinif, ders, haric, n=10, g=None: [
        {"id": 9000 + i, "konu": "K", "soru": f"M{i}?", "secenekler": ["a", "b", "c", "d"],
         "dogru_index": 2, "kaynak": "k"} for i in range(n)])
    monkeypatch.setattr(kazanim, "form_sonuclari", lambda okul_no: [])
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def basla(c, csrf):
    r = c.post("/ogrenci/arena/basla", data={"csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return int(r.headers["location"].rsplit("/", 1)[1])


def cevap(c, csrf, tur, sira, sec, js=True):
    return c.post(f"/ogrenci/arena/{tur}/cevap", data={"csrf": csrf, "sira": sira, "sec": sec},
                  headers=JSON if js else {}, follow_redirects=False)


def test_merkez_ve_gorev_akisi(istemci, ornek, saat):
    csrf = giris(istemci, "101", "ali-sifre")
    r = istemci.get("/ogrenci/arena")
    assert r.status_code == 200 and "Arena'ya Gir" in r.text and "Hızlı Mod" in r.text
    tur = basla(istemci, csrf)
    assert basla(istemci, csrf) == tur  # ikinci başlatma aynı tura gider
    for sira in range(1, 6):
        s = istemci.get(f"/ogrenci/arena/{tur}")
        assert s.status_code == 200 and f"Soru {sira} / 5" in s.text
        c = cevap(istemci, csrf, tur, sira, 2)
        assert c.status_code == 200 and c.json()["dogru"] is True
        g = istemci.get(f"/ogrenci/arena/{tur}/soru/{sira}")
        assert g.status_code == 200 and "Doğru!" in g.text
    assert istemci.get(f"/ogrenci/arena/{tur}", follow_redirects=False).headers["location"].endswith("/sonuc")
    sonuc = istemci.get(f"/ogrenci/arena/{tur}/sonuc")
    assert sonuc.status_code == 200 and "MAT.9.1" in sonuc.text and "5" in sonuc.text
    assert "İlk Arena Turu" in sonuc.text
    ilr = istemci.get("/ogrenci/arena/ilerleme")
    assert ilr.status_code == 200 and "Beş Gün Katılım" in ilr.text
    assert "Sonucu gör" in istemci.get("/ogrenci/arena").text


def test_cevap_cevaptan_once_sizmaz(istemci, ornek, saat):
    csrf = giris(istemci, "101", "ali-sifre")
    tur = basla(istemci, csrf)
    s = istemci.get(f"/ogrenci/arena/{tur}")
    assert "Arena sorusu 7000" in s.text
    assert "(doğru cevap)" not in s.text and "dogru_index" not in s.text and 'class="sik dogru' not in s.text
    # cevaplanmamış sorunun geri bildirimi sızdırmaz: soruya yönlendirir
    g = istemci.get(f"/ogrenci/arena/{tur}/soru/1", follow_redirects=False)
    assert g.status_code == 303 and g.headers["location"] == f"/ogrenci/arena/{tur}"
    istemci.get(f"/ogrenci/arena/{tur}/soru/2", follow_redirects=False)
    cevap(istemci, csrf, tur, 1, 0)
    g = istemci.get(f"/ogrenci/arena/{tur}/soru/1")
    assert "(doğru cevap)" in g.text and "(senin cevabın)" in g.text and "Doğru cevap: <b" in g.text


def test_cift_ve_gecersiz_cevap(istemci, ornek, saat, conn):
    csrf = giris(istemci, "101", "ali-sifre")
    tur = basla(istemci, csrf)
    assert cevap(istemci, csrf, tur, 1, 9).status_code == 400
    assert cevap(istemci, csrf, tur, 1, -1).status_code == 400
    assert cevap(istemci, csrf, tur, 99, 1).status_code == 400
    assert istemci.post(f"/ogrenci/arena/{tur}/cevap", data={"csrf": csrf, "sira": "x", "sec": "1"}).status_code == 400
    assert cevap(istemci, csrf, tur, 1, 2).status_code == 200
    ikinci = cevap(istemci, csrf, tur, 1, 2)
    assert ikinci.status_code == 409
    assert cevap(istemci, csrf, tur, 1, 2, js=False).headers["location"] == f"/ogrenci/arena/{tur}"
    assert arena.toplam_xp(conn, ornek["ogr1_k"]) == 10


def test_paralel_ayni_cevap_tek_xp(istemci, ornek, saat, conn):
    csrf = giris(istemci, "101", "ali-sifre")
    tur = basla(istemci, csrf)
    kodlar = []

    def gonder():
        with TestClient(istemci.app) as c2:
            c2.cookies.update(istemci.cookies)
            kodlar.append(cevap(c2, csrf, tur, 1, 2).status_code)

    ts = [threading.Thread(target=gonder) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(kodlar).count(200) == 1
    assert arena.toplam_xp(conn, ornek["ogr1_k"]) == 10


def test_yetki_404_ve_baskasinin_turu(istemci, ornek, saat):
    csrf = giris(istemci, "101", "ali-sifre")
    tur = basla(istemci, csrf)
    giris(istemci, "201", "ayse-sifre")
    for yol in (f"/ogrenci/arena/{tur}", f"/ogrenci/arena/{tur}/sonuc", f"/ogrenci/arena/{tur}/soru/1"):
        assert istemci.get(yol).status_code == 404
    csrf2 = auth.csrf_token(istemci.cookies.get(auth.COOKIE_ADI))
    assert cevap(istemci, csrf2, tur, 1, 2).status_code == 404
    for kadi, sifre in (("hoca", "hoca-sifre"), ("mudur", "mudur-sifre")):
        giris(istemci, kadi, sifre)
        assert istemci.get("/ogrenci/arena").status_code == 404
        assert istemci.get("/ogrenci/arena/ilerleme").status_code == 404
    istemci.cookies.clear()
    assert istemci.get("/ogrenci/arena", follow_redirects=False).status_code in (303, 404)


def test_12_sinif_arena_yok(istemci, ornek, conn, saat):
    conn.execute("UPDATE ogrenci SET sinif = '12-A' WHERE id = ?", (ornek["ogr1"],))
    conn.commit()
    giris(istemci, "101", "ali-sifre")
    assert istemci.get("/ogrenci/arena").status_code == 404


def test_csrf_zorunlu(istemci, ornek, saat):
    giris(istemci, "101", "ali-sifre")
    assert istemci.post("/ogrenci/arena/basla", data={}, follow_redirects=False).status_code in (400, 403)
    assert istemci.post("/ogrenci/arena/basla", data={"csrf": "yanlis"}, follow_redirects=False).status_code in (400, 403)


def test_ders_saatinde_kilit(istemci, ornek, saat, monkeypatch):
    import json
    from datetime import datetime

    from ayarlar import AYAR

    AYAR.zil_yolu.write_text(json.dumps(ZIL), encoding="utf-8")
    saat["an"] = datetime(2026, 10, 12, 10, 0)  # pazartesi, 3. ders
    csrf = giris(istemci, "101", "ali-sifre")
    assert "Ders sırasında kapalı" in istemci.get("/ogrenci/arena").text
    r = istemci.post("/ogrenci/arena/basla", data={"csrf": csrf}, follow_redirects=False)
    assert r.status_code == 423 and "10:30" in r.text
    saat["an"] = datetime(2026, 10, 12, 10, 45)
    tur = basla(istemci, csrf)
    saat["an"] = datetime(2026, 10, 12, 10, 0)  # görev açıkken ders girerse cevap da kilitli
    assert cevap(istemci, csrf, tur, 1, 2).status_code == 423
    assert istemci.get(f"/ogrenci/arena/{tur}").status_code == 423


def test_havuz_hatasi(istemci, ornek, saat, monkeypatch):
    csrf = giris(istemci, "101", "ali-sifre")

    def patla(s):
        raise KaynakHatasi("pg")

    monkeypatch.setattr(havuz, "dersler", patla)
    assert "ulaşılamıyor" in istemci.get("/ogrenci/arena").text
    r = istemci.post("/ogrenci/arena/basla", data={"csrf": csrf}, follow_redirects=False)
    assert r.status_code == 503


def test_yeni_gun_yeni_gorev(istemci, ornek, saat):
    from datetime import timedelta

    csrf = giris(istemci, "101", "ali-sifre")
    t1 = basla(istemci, csrf)
    saat["an"] += timedelta(days=1)
    assert basla(istemci, csrf) != t1


def test_maraton_xp_rota_uzerinden(istemci, ornek, saat, conn):
    csrf = giris(istemci, "101", "ali-sifre")
    r = istemci.post("/ogrenci/maraton/basla", data={"csrf": csrf, "ders": "matematik"}, follow_redirects=False)
    mid = int(r.headers["location"].rsplit("/", 1)[1])
    for sira in range(1, 11):
        istemci.get(f"/ogrenci/maraton/{mid}")  # gösterim zamanı sunucuda yazılır
        istemci.post(f"/ogrenci/maraton/{mid}/cevap", data={"csrf": csrf, "sira": sira, "sec": 2}, headers=JSON)
    assert arena.toplam_xp(conn, ornek["ogr1_k"]) == 100
    s = istemci.get(f"/ogrenci/maraton/{mid}/sonuc")
    assert s.status_code == 200 and "+100 XP" in s.text
    istemci.get(f"/ogrenci/maraton/{mid}/sonuc")  # yeniden yükleme
    assert arena.toplam_xp(conn, ornek["ogr1_k"]) == 100


def test_eski_maraton_sonuc_gorulunce_xp_yazilmaz(istemci, ornek, saat, conn):
    giris(istemci, "101", "ali-sifre")
    mid = conn.execute(
        "INSERT INTO maraton (kullanici_id, sinif, duzey, ders, basla, bitis, dogru, puan) VALUES (?, '9-A', 9, 'matematik',"
        " '2026-10-01 10:00:00', '2026-10-01 10:05:00', 8, 900)", (ornek["ogr1_k"],)).lastrowid
    conn.commit()
    assert istemci.get(f"/ogrenci/maraton/{mid}/sonuc").status_code == 200
    assert arena.toplam_xp(conn, ornek["ogr1_k"]) == 0  # geriye dönük XP yok


def test_arena_analitik_olaylari(istemci, ornek, saat, conn):
    import analitik

    csrf = giris(istemci, "101", "ali-sifre")
    istemci.get("/ogrenci/arena")
    tur = basla(istemci, csrf)
    basla(istemci, csrf)
    for sira in range(1, 6):
        cevap(istemci, csrf, tur, sira, 1)
    analitik.bosalt()
    n = dict(conn.execute("SELECT tur, count(*) FROM olay WHERE tur LIKE 'arena_%' GROUP BY tur").fetchall())
    assert n == {"arena_goruntule": 1, "arena_basla": 1, "arena_tamamla": 1}


def test_surum_degisimi_yok_regresyon(istemci, ornek):
    assert maraton.SORU_SAYISI == 10  # Hızlı Mod değişmedi
