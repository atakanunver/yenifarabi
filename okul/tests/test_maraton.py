"""Soru Maratonu: puanlama, sunucu süresi, ders saati kilidi, yetki (404), sızıntı, tekrar engeli, liderlik."""

import json
from datetime import datetime, timedelta

import auth
import maraton
import pytest
from ayarlar import AYAR
from fastapi.testclient import TestClient
from kaynaklar import KaynakHatasi, kazanim, soru

JSON = {"Accept": "application/json"}
ZIL = {
    "dersler": [
        {"no": 1, "baslangic": "08:10", "bitis": "08:50"},
        {"no": 3, "baslangic": "09:50", "bitis": "10:30"},
        {"no": 4, "baslangic": "10:40", "bitis": "11:20"},
    ],
    "ogle_arasi": {"baslangic": "12:10", "bitis": "13:30"},
    "ders_gunleri": [1, 2, 3, 4, 5],
}


@pytest.fixture
def havuz(monkeypatch):
    """Postgres yok: kaynaklar.soru taklit edilir; sorular() çağrıları kaydedilir."""
    cagrilar = []

    def sorular(sinif, ders, haric_ids, n=10, gorulme=None):
        cagrilar.append({"sinif": sinif, "ders": ders, "haric": list(haric_ids), "n": n})
        taban = 1000 * sinif
        return [
            {"id": taban + i, "konu": "Konu", "soru": f"Soru {taban + i}?",
             "secenekler": ["a", "b", "c", "d"], "dogru_index": 2, "kaynak": "Kitap s. 1"}
            for i in range(n + len(haric_ids))
            if taban + i not in haric_ids
        ][:n]

    monkeypatch.setattr(soru, "dersler", lambda sinif: [("matematik", 40), ("cografya", 12)])
    monkeypatch.setattr(soru, "sorular", sorular)
    return cagrilar


@pytest.fixture
def istemci(monkeypatch, havuz):
    monkeypatch.setattr(kazanim, "form_sonuclari", lambda okul_no: [])
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def baslat(c, csrf, ders="matematik"):
    r = c.post("/ogrenci/maraton/basla", data={"csrf": csrf, "ders": ders}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return int(r.headers["location"].rsplit("/", 1)[1])


def cevapla(c, csrf, mid, sira, sec=None, js=True):
    veri = {"csrf": csrf, "sira": sira}
    if sec is not None:
        veri["sec"] = sec
    return c.post(f"/ogrenci/maraton/{mid}/cevap", data=veri, headers=JSON if js else {}, follow_redirects=False)


def ogrenci_ekle(conn, yeni_kullanici, ad, no, sinif):
    kid = yeni_kullanici(conn, "ogrenci", ad, str(no), sifre="x-sifre")
    conn.execute(
        "INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (?, ?, ?, ?)", (no, ad, sinif, kid)
    )
    conn.commit()
    return kid


def maraton_ekle(conn, kid, sinif, bitis, puan, terk=False):
    mid = conn.execute(
        "INSERT INTO maraton (kullanici_id, sinif, duzey, ders, basla, bitis, puan) VALUES (?, ?, ?, 'matematik', ?, ?, ?)",
        (kid, sinif, int(sinif.split("-")[0]), bitis, bitis, puan),
    ).lastrowid
    conn.execute(
        "INSERT INTO maraton_soru (maraton_id, sira, soru_id, soru, secenekler, dogru_index, cevap) VALUES (?, 1, 1, 's', '[]', 0, ?)",
        (mid, -2 if terk else 0),
    )
    conn.commit()
    return mid


def test_puan_formulu():
    assert maraton.puan_hesapla(True, 0) == 190
    assert maraton.puan_hesapla(True, 5) == 175
    assert maraton.puan_hesapla(True, 30) == 100
    assert maraton.puan_hesapla(True, 31.5) == 100
    assert maraton.puan_hesapla(True, 33) == 0
    assert maraton.puan_hesapla(False, 1) == 0


def test_soru_sayfasi_dogru_cevabi_sizdirmaz(istemci, ornek, saat):
    csrf = giris(istemci, "101", "ali-sifre")
    mid = baslat(istemci, csrf)
    sayfa = istemci.get(f"/ogrenci/maraton/{mid}")
    assert sayfa.status_code == 200 and "Soru 1 / 10" in sayfa.text and "Soru 9000" in sayfa.text
    assert "dogru" not in sayfa.text.lower() and "dogru_index" not in sayfa.text
    # JSON olmayan başka bir GET yanıtı da sızdırmaz
    assert "dogru_index" not in istemci.get("/ogrenci/maraton").text


def test_dogru_cevap_hizli_puan_ve_akis(istemci, ornek, saat):
    csrf = giris(istemci, "101", "ali-sifre")
    mid = baslat(istemci, csrf)
    istemci.get(f"/ogrenci/maraton/{mid}")
    saat["an"] += timedelta(seconds=5)
    j = cevapla(istemci, csrf, mid, 1, 2).json()
    assert j["dogru"] and j["puan"] == 175 and j["toplam"] == 175 and j["dogru_index"] == 2 and not j["bitti"]
    # ikinci soru: yanlış şık
    istemci.get(f"/ogrenci/maraton/{mid}")
    j = cevapla(istemci, csrf, mid, 2, 0).json()
    assert not j["dogru"] and j["puan"] == 0 and j["dogru_index"] == 2 and j["toplam"] == 175
    # aynı soruyu tekrar cevaplamak ya da atlamak olmaz
    assert cevapla(istemci, csrf, mid, 1, 2).status_code == 409
    assert cevapla(istemci, csrf, mid, 5, 2).status_code == 409


def test_sure_asimi_sunucuda(istemci, ornek, saat, conn):
    csrf = giris(istemci, "101", "ali-sifre")
    mid = baslat(istemci, csrf)
    istemci.get(f"/ogrenci/maraton/{mid}")
    saat["an"] += timedelta(seconds=33)  # 30 + 2 tolerans aşıldı
    j = cevapla(istemci, csrf, mid, 1, 2).json()  # doğru şık bile 0 puan
    assert j["sure_doldu"] and not j["dogru"] and j["puan"] == 0
    # sayfa terk edilip geç dönülürse sıradaki soru otomatik süre doldu sayılır
    istemci.get(f"/ogrenci/maraton/{mid}")
    saat["an"] += timedelta(seconds=40)
    r = istemci.get(f"/ogrenci/maraton/{mid}", follow_redirects=False)
    assert r.status_code == 303
    assert conn.execute("SELECT cevap FROM maraton_soru WHERE maraton_id=? AND sira=2", (mid,)).fetchone()[0] == -1
    # tolerans içinde (31 sn) doğru cevap 100 puan
    istemci.get(f"/ogrenci/maraton/{mid}")
    saat["an"] += timedelta(seconds=31)
    assert cevapla(istemci, csrf, mid, 3, 2).json()["puan"] == 100


def test_formla_tum_maraton_ve_sonuc(istemci, ornek, saat):
    csrf = giris(istemci, "101", "ali-sifre")
    mid = baslat(istemci, csrf)
    for sira in range(1, 11):  # JS'siz: form POST + redirect
        istemci.get(f"/ogrenci/maraton/{mid}")
        r = cevapla(istemci, csrf, mid, sira, 2, js=False)
        assert r.status_code == 303
    assert r.headers["location"].endswith("/sonuc")
    s = istemci.get(f"/ogrenci/maraton/{mid}/sonuc")
    assert s.status_code == 200 and "1900" in s.text and "10</b> / 10" in s.text
    assert istemci.get(f"/ogrenci/maraton/{mid}", follow_redirects=False).status_code == 303


def test_ders_saatinde_kilit(istemci, ornek, saat):
    csrf = giris(istemci, "101", "ali-sifre")
    mid = baslat(istemci, csrf)  # 10:00, zil.json yok -> açık
    istemci.get(f"/ogrenci/maraton/{mid}")
    AYAR.zil_yolu.write_text(json.dumps(ZIL), encoding="utf-8")  # 10:00 = 3. ders (09:50-10:30)
    r = istemci.post("/ogrenci/maraton/basla", data={"csrf": csrf, "ders": "matematik"})
    assert r.status_code == 423 and "Ders sırasında kapalı" in r.text and "10:30" in r.text
    r = cevapla(istemci, csrf, mid, 1, 2)
    assert r.status_code == 423 and r.json()["kilit"] and "10:30" in r.json()["mesaj"]
    assert cevapla(istemci, csrf, mid, 1, 2, js=False).status_code == 423
    assert "Ders sırasında kapalı · 10:30&#39;de açılır" in istemci.get("/ogrenci/maraton").text
    sayfa = istemci.get(f"/ogrenci/maraton/{mid}")
    assert sayfa.status_code == 423 and "Soru 9000" not in sayfa.text
    # teneffüs açık
    saat["an"] = datetime(2026, 10, 12, 10, 30)
    assert cevapla(istemci, csrf, mid, 1, 2).status_code == 200


def test_baskasinin_maratonu_404(istemci, ornek):
    csrf1 = giris(istemci, "101", "ali-sifre")
    mid = baslat(istemci, csrf1)
    csrf2 = giris(istemci, "201", "ayse-sifre")
    assert istemci.get(f"/ogrenci/maraton/{mid}").status_code == 404
    assert istemci.get(f"/ogrenci/maraton/{mid}/sonuc").status_code == 404
    assert cevapla(istemci, csrf2, mid, 1, 2).status_code == 404
    assert istemci.get("/ogrenci/maraton/99999").status_code == 404


def test_diger_roller_404(istemci, ornek, conn):
    for kadi, sifre in (("hoca", "hoca-sifre"), ("mudur", "mudur-sifre")):
        giris(istemci, kadi, sifre)
        for yol in ("/ogrenci/maraton", "/ogrenci/liderlik"):
            assert istemci.get(yol).status_code == 404
    istemci.cookies.clear()
    istemci.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, ornek["veli1"]))
    for yol in ("/ogrenci/maraton", "/ogrenci/liderlik", "/ogrenci/maraton/1"):
        assert istemci.get(yol).status_code == 404


def test_csrf_zorunlu(istemci, ornek):
    csrf = giris(istemci, "101", "ali-sifre")
    mid = baslat(istemci, csrf)
    assert istemci.post(f"/ogrenci/maraton/{mid}/cevap", data={"sira": 1, "sec": 2}).status_code == 400
    assert istemci.post("/ogrenci/maraton/basla", data={"ders": "matematik"}).status_code == 400


def test_gorulen_sorular_haric_tutulur(istemci, ornek, havuz, saat):
    csrf = giris(istemci, "101", "ali-sifre")
    mid = baslat(istemci, csrf)
    assert havuz[-1]["haric"] == [] and havuz[-1]["sinif"] == 9 and havuz[-1]["n"] == 10
    for sira in (1, 2, 3):
        istemci.get(f"/ogrenci/maraton/{mid}")
        cevapla(istemci, csrf, mid, sira, 2)
    istemci.get(f"/ogrenci/maraton/{mid}")  # 4. soru gösterildi ama cevaplanmadı
    baslat(istemci, csrf)
    assert sorted(havuz[-1]["haric"]) == [9000, 9001, 9002, 9003]


def test_on_sorudan_az_kalirsa_hata(istemci, ornek, monkeypatch):
    csrf = giris(istemci, "101", "ali-sifre")
    monkeypatch.setattr(soru, "sorular", lambda *a, **k: [])
    r = istemci.post("/ogrenci/maraton/basla", data={"csrf": csrf, "ders": "matematik"})
    assert r.status_code == 400
    r = istemci.post("/ogrenci/maraton/basla", data={"csrf": csrf, "ders": "yok_ders"})
    assert r.status_code == 400


def test_havuz_kapaliysa_acik_hata(istemci, ornek, monkeypatch):
    csrf = giris(istemci, "101", "ali-sifre")

    def patla(sinif):
        raise KaynakHatasi("x")

    monkeypatch.setattr(soru, "dersler", patla)
    assert "şu an alınamıyor" in istemci.get("/ogrenci/maraton").text
    assert istemci.post("/ogrenci/maraton/basla", data={"csrf": csrf, "ders": "matematik"}).status_code == 503


def test_12_sinif_duzey_12(istemci, ornek, conn, yeni_kullanici, havuz):
    ogrenci_ekle(conn, yeni_kullanici, "On İki", 301, "12-A")
    csrf = giris(istemci, "301", "x-sifre")
    mid = baslat(istemci, csrf)
    assert havuz[-1]["sinif"] == 12
    assert conn.execute("SELECT duzey, sinif FROM maraton WHERE id=?", (mid,)).fetchone()[:] == (12, "12-A")


def test_yarim_kalan_maraton(istemci, ornek, conn, saat):
    csrf = giris(istemci, "101", "ali-sifre")
    ilk = baslat(istemci, csrf)
    istemci.get(f"/ogrenci/maraton/{ilk}")
    cevapla(istemci, csrf, ilk, 1, 2)
    sayfa = istemci.get("/ogrenci/maraton").text
    assert "Yarım kalan maraton" in sayfa and f"/ogrenci/maraton/{ilk}" in sayfa
    yeni = baslat(istemci, csrf, "cografya")
    assert yeni != ilk
    eski = conn.execute("SELECT bitis FROM maraton WHERE id=?", (ilk,)).fetchone()[0]
    assert eski is not None
    assert conn.execute("SELECT count(*) FROM maraton_soru WHERE maraton_id=? AND cevap=-2 AND puan=0", (ilk,)).fetchone()[0] == 9
    # terk edilen maraton liderliğe ve seriye sayılmaz
    assert maraton.liderlik(conn) == [] and maraton.seri(conn, ornek["ogr1_k"]) == 0
    assert maraton.acik_maraton(conn, ornek["ogr1_k"])["id"] == yeni


def test_seri(conn, ornek, saat):
    kid = ornek["ogr1_k"]
    assert maraton.seri(conn, kid) == 0
    for gun in (12, 11, 10, 8):  # bugün = 12 Ekim; 9'u boş
        maraton_ekle(conn, kid, "9-A", f"2026-10-{gun:02d} 16:00:00", 100)
    assert maraton.seri(conn, kid) == 3
    saat["an"] = datetime(2026, 10, 13, 9, 0)  # bugün oynamadı ama dün oynadı: seri sürer
    assert maraton.seri(conn, kid) == 3
    saat["an"] = datetime(2026, 10, 14, 9, 0)  # iki gün boş: seri koptu
    assert maraton.seri(conn, kid) == 0


def test_liderlik_en_iyi_uc_sinif_ve_okul(istemci, ornek, conn, yeni_kullanici, saat):
    saat["an"] = datetime(2026, 10, 14, 12, 0)  # çarşamba; hafta 12 Ekim pazartesi başlar
    ali, ayse = ornek["ogr1_k"], ornek["ogr2_k"]  # 9-A, 9-B
    can = ogrenci_ekle(conn, yeni_kullanici, "Can Ömer Işık", 302, "9-A")
    for p in (500, 400, 300, 200):  # en iyi 3 = 1200 (200 sayılmaz)
        maraton_ekle(conn, ali, "9-A", "2026-10-13 15:00:00", p)
    maraton_ekle(conn, ali, "9-A", "2026-10-11 15:00:00", 9999)  # geçen hafta (pazar)
    maraton_ekle(conn, ali, "9-A", "2026-10-13 15:00:00", 8888, terk=True)  # yarıda bırakılmış
    maraton_ekle(conn, can, "9-A", "2026-10-13 15:00:00", 1500)
    maraton_ekle(conn, ayse, "9-B", "2026-10-13 15:00:00", 1800)
    liste = maraton.liderlik(conn)
    assert [(d["ad"], d["toplam"], d["sira"]) for d in liste] == [
        ("Ayşe K.", 1800, 1), ("Can Ömer I.", 1500, 2), ("Ali V.", 1200, 3)
    ]
    assert [d["ad"] for d in maraton.liderlik(conn, "9-A")] == ["Can Ömer I.", "Ali V."]
    giris(istemci, "101", "ali-sifre")
    sinif = istemci.get("/ogrenci/liderlik").text
    assert "Ali V." in sinif and "Can Ömer I." in sinif and "Ayşe K." not in sinif
    assert '<li class="ben">' in sinif and "1200" in sinif
    okul = istemci.get("/ogrenci/liderlik?kapsam=okul").text
    assert "Ayşe K." in okul and "9-B" in okul
    assert "Bu hafta okulda <b>3.</b>" in istemci.get("/ogrenci").text


def test_ana_sayfa_karti(istemci, ornek):
    giris(istemci, "101", "ali-sifre")
    h = istemci.get("/ogrenci").text
    assert "Soru Maratonu" in h and 'href="/ogrenci/maraton"' in h and "henüz oynamadın" in h


def test_sw_ve_css_surumu(istemci):
    sw = istemci.get("/sw.js").text
    assert "okul-v8" in sw and "/static/maraton.js?v=1" in sw and "okul.css?v=8" in sw
    assert "okul.css?v=8" in istemci.get("/giris").text


def test_ayni_soru_iki_kez_puanlanmaz(conn, ornek, monkeypatch, saat):
    """Çift dokunma: ikinci cevap reddedilir, puan bir kez yazılır."""
    import maraton as mr
    from kaynaklar import soru as havuz

    saat["an"] = datetime(2026, 10, 17, 10, 0)  # cumartesi: kilit yok
    monkeypatch.setattr(havuz, "sorular", lambda *a, **kw: [
        {"id": i, "soru": f"S{i}", "secenekler": ["a", "b", "c", "d"], "dogru_index": 0,
         "konu": "k", "kaynak": "x"} for i in range(1, 11)])
    mid = mr.baslat(conn, ornek["ogr1_k"], "9-A", "tarih")
    mr.siradaki(conn, mid)
    assert mr.cevapla(conn, mid, 1, 0)["dogru"]
    with pytest.raises(mr.MaratonHatasi):
        mr.cevapla(conn, mid, 1, 0)
    assert conn.execute("SELECT dogru FROM maraton WHERE id = ?", (mid,)).fetchone()[0] == 1
