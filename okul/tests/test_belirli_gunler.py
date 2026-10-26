"""Belirli gün ve haftalar: kural çözümü (hareketli günler), 69 kaydın hatasız çözülmesi, eksik/bozuk dosya."""

import json
from datetime import date, timedelta

import belirli_gunler as bg


def adlar(tarih, yol=None):
    return [g["ad"] for g in bg.bugun(yol, tarih)]


def test_kayit_sayisi_ve_gecerli():
    liste = json.loads(bg.YOL.read_text(encoding="utf-8"))["liste"]
    assert len(liste) == 69
    assert {k["tur"] for k in liste} == {"gun", "hafta"}


def test_her_kural_2026_2030_hatasiz_cozulur():
    liste = json.loads(bg.YOL.read_text(encoding="utf-8"))["liste"]
    for yil in range(2026, 2031):
        for k in liste:
            a = bg._aralik(k["kural"], yil)
            if k["kural"]["tip"] == "yila_ozel":
                assert a is None  # Mevlid-i Nebî: tarih girilene kadar yok
                continue
            assert a is not None and a[0] <= a[1], (yil, k["ad"])


def test_hareketli_gunler():
    assert "Anneler Günü" in adlar(date(2027, 5, 9)) and "Anneler Günü" not in adlar(date(2027, 5, 16))
    assert "Babalar Günü" in adlar(date(2027, 6, 20))
    assert "Dünya İlk Yardım Günü" in adlar(date(2026, 9, 12))
    assert "Dünya Disleksi Günü" in adlar(date(2026, 10, 1)) and "Dünya Disleksi Günü" in adlar(date(2027, 10, 7))
    assert "Kütüphaneler Haftası" in adlar(date(2027, 3, 29)) and "Kütüphaneler Haftası" in adlar(date(2027, 4, 4))  # son Pzt 29 Mart
    assert "Kütüphaneler Haftası" not in adlar(date(2027, 4, 5))
    assert "Vergi Haftası" in adlar(date(2028, 2, 29)) and "Vergi Haftası" not in adlar(date(2028, 2, 22))  # artık yıl


def test_ayin_haftalari_ve_ogrenciler_gunu():
    assert "İlköğretim Haftası" in adlar(date(2026, 9, 15)) and "İlköğretim Haftası" in adlar(date(2026, 9, 21))
    assert "İlköğretim Haftası" not in adlar(date(2026, 9, 22))
    assert "Öğrenciler Günü" in adlar(date(2026, 9, 21)) and "Öğrenciler Günü" not in adlar(date(2026, 9, 20))
    assert "Enerji Tasarrufu Haftası" in adlar(date(2027, 1, 8)) and "Enerji Tasarrufu Haftası" not in adlar(date(2027, 1, 15))


def test_hafta_icerir_ve_ay_gecisi():
    assert "Yeşilay Haftası" in adlar(date(2027, 3, 1))  # Pazartesi
    assert "Yeşilay Haftası" in adlar(date(2026, 3, 1)) and "Yeşilay Haftası" in adlar(date(2026, 2, 23))  # Pazar'a denk gelen 1 Mart
    assert "Kızılay Haftası" in adlar(date(2026, 11, 4)) and "Cumhuriyet Bayramı" in adlar(date(2026, 10, 29))
    assert "Kızılay Haftası" not in adlar(date(2026, 11, 5))


def test_ayni_gun_gunler_once_haftalar_sonra():
    g = bg.bugun(None, date(2026, 11, 10))  # Atatürk Haftası başlangıcı
    assert [x["ad"] for x in g] == ["Atatürk Haftası"] and g[0]["metin"] == "10–16 Kasım"
    g = bg.bugun(None, date(2027, 3, 8))  # Dünya Kadınlar Günü + Bilim ve Teknoloji Haftası
    assert [x["tur"] for x in g] == ["gun", "hafta"] and g[1]["metin"] == "8–14 Mart"


def test_yila_ozel_ve_ay_gecen_metin(tmp_path):
    yol = tmp_path / "b.json"
    yol.write_text(json.dumps({"liste": [{"ad": "Mevlid", "tur": "hafta", "kural": {"tip": "yila_ozel", "deger": {"2027": ["08-12", "08-18"]}}}]}), encoding="utf-8")
    assert adlar(date(2027, 8, 14), yol) == ["Mevlid"] and adlar(date(2026, 8, 14), yol) == []
    yol.write_text(json.dumps({"liste": [{"ad": "Yıl", "tur": "hafta", "kural": {"tip": "aralik", "deger": ["12-28", "01-03"]}}]}), encoding="utf-8")
    assert adlar(date(2027, 1, 2), yol) == ["Yıl"] and adlar(date(2026, 12, 30), yol) == ["Yıl"] and adlar(date(2027, 1, 4), yol) == []
    assert bg.bugun(yol, date(2027, 1, 2))[0]["metin"] == "28 Aralık – 3 Ocak"


def test_eksik_bozuk_dosya_ve_bozuk_kayit(tmp_path):
    assert bg.bugun(tmp_path / "yok.json", date(2026, 10, 29)) == []
    yol = tmp_path / "b.json"
    yol.write_text("{bozuk", encoding="utf-8")
    assert bg.bugun(yol, date(2026, 10, 29)) == []
    yol.write_text(json.dumps({"liste": [{"ad": "Kötü", "tur": "gun", "kural": {"tip": "yok", "deger": 1}},
                                         {"ad": "İyi", "tur": "gun", "kural": {"tip": "sabit", "deger": "10-29"}}]}), encoding="utf-8")
    assert adlar(date(2026, 10, 29), yol) == ["İyi"]  # bozuk kayıt diğerlerini engellemez


def test_varsayilan_tarih_turkiye_saati(saat):
    assert bg.bugun() == bg.bugun(None, saat["an"].date())


def test_yilin_hicbir_gunu_hata_vermez():
    d = date(2027, 1, 1)
    while d.year == 2027:
        bg.bugun(None, d)
        d += timedelta(days=1)


def test_dort_ana_sayfada_kart_gorunur(conn, ornek, saat):
    from datetime import datetime

    import auth
    from app import app
    from fastapi.testclient import TestClient

    saat["an"] = datetime(2026, 10, 29, 9, 0)  # noqa: DTZ001 — Cumhuriyet Bayramı + Kızılay Haftası
    for rol, yol in (("ogr1_k", "/ogrenci"), ("ogretmen", "/ogretmen"), ("veli1", "/veli"), ("yonetici", "/yonetici")):
        with TestClient(app) as c:
            c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, ornek[rol]))
            s = c.get(yol).text
            assert "Belirli gün ve haftalar" in s, rol
            assert "Cumhuriyet Bayramı" in s and "Kızılay Haftası" in s and "29 Ekim – 4 Kasım" in s, rol


def test_kart_gunun_bilgisinden_once_ve_bos_gunde_gizli(conn, ornek, saat):
    from datetime import datetime

    import auth
    from app import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, ornek["ogr1_k"]))
        saat["an"] = datetime(2026, 10, 29, 9, 0)  # noqa: DTZ001
        s = c.get("/ogrenci").text
        assert "gunun-bilgisi-b" in s and s.index("belirli-gunler-b") < s.index("gunun-bilgisi-b")
        saat["an"] = datetime(2026, 10, 20, 9, 0)  # noqa: DTZ001 — listede gün/hafta yok
        assert "Belirli gün ve haftalar" not in c.get("/ogrenci").text
