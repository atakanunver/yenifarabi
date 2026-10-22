"""Yeni öğrenci ana ekranı: görev listesi, hedef, hızlı çalışma, korunan okul bilgisi, 12. sınıf, boş durum."""

import auth
import kisisel
import maraton
import pytest
from fastapi.testclient import TestClient
from kaynaklar import arena_soru, kazanim
from kaynaklar import soru as havuz


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setattr(maraton, "kilit", lambda: None)
    monkeypatch.setattr(havuz, "dersler", lambda s: [("matematik", 40)])
    monkeypatch.setattr(arena_soru, "sorular", lambda *a, **k: [])
    monkeypatch.setattr(kazanim, "form_sonuclari", lambda okul_no: [])
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303


def test_ana_ekran_bolumleri(istemci, ornek, conn, saat):
    conn.execute("INSERT INTO odev (ogretmen_id, sinif, ders, tur, baslik, teslim, olusturma) VALUES (?, '9-A', 'matematik', 'klasik', 'Limit çalışması', '2026-10-13 09:00:00', 't')", (ornek["ogretmen"],))
    conn.commit()
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci").text
    assert "Merhaba" in t and "Ali" in t
    assert "Bugün ne yapacağım?" in t and "Limit çalışması" in t and 'href="/ogrenci/odev/1"' in t
    assert "Haftalık hedefim" in t and "Hedef koy" in t and "/ogrenci/hedefim" in t
    assert 'href="/ogrenci/maraton"' in t and "Hızlı Mod" in t and 'href="/ogrenci/arena/liderlik"' in t
    assert "Gelişimim" in t and "/ogrenci/gelisim" in t
    # okul bilgisi korunur
    for korunan in ("Bugünkü dersler", "Yaklaşan sınavlar", "Duyurular"):
        assert korunan in t


def test_seviye_ve_hedef_ilerlemesi(istemci, ornek, conn, saat):
    o = conn.execute("SELECT * FROM ogrenci WHERE id = ?", (ornek["ogr1"],)).fetchone()
    kisisel.hedef_koy(conn, o, 4)
    conn.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (?, 'arena_bonus', '1', 60, '2026-10-12', 'z')", (ornek["ogr1_k"],))
    conn.commit()
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci").text
    assert "Seviye 2</b> · 60 XP" in t and "<b>0 / 4</b>" in t and 'aria-valuenow="0"' in t
    assert "Bu hafta için hedef koy" not in t  # hedef konduğu için görev yok


def test_12_sinif_arena_yok_ama_ekran_calisir(istemci, ornek, conn, saat):
    conn.execute("UPDATE ogrenci SET sinif = '12-A' WHERE id = ?", (ornek["ogr1"],))
    conn.commit()
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci").text
    assert "Günlük Görev" not in t and "Seviye" not in t and "Hızlı Mod" in t


def test_bos_durum_uydurma_gorev_yok(istemci, ornek, conn, saat):
    conn.execute("UPDATE ogrenci SET sinif = '12-A' WHERE id = ?", (ornek["ogr1"],))
    o = conn.execute("SELECT * FROM ogrenci WHERE id = ?", (ornek["ogr1"],)).fetchone()
    conn.commit()
    kisisel.hedef_koy(conn, o, 3)
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci").text
    assert "Bugün için bekleyen bir şeyin yok." in t


def test_diger_roller_ana_ekrani_goremez(istemci, ornek, conn):
    giris(istemci, "hoca", "hoca-sifre")
    assert istemci.get("/ogrenci").status_code == 404
    istemci.cookies.clear()
    istemci.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, ornek["veli1"]))
    assert istemci.get("/ogrenci").status_code == 404


def test_bekleyen_anket_bildirimi_ve_gorevi(istemci, ornek, conn, saat):
    import anket

    aid = anket.olustur(conn, ornek["yonetici"], "Okul memnuniyeti")
    anket.soru_ekle(conn, aid, "olcek", "Memnun musun?", [], True, ["ogrenci", "veli", "ogretmen"])
    anket.dagit(conn, aid, "ogrenci")
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci").text
    assert "Yanıtlamanı bekleyen 1 anket var" in t and "Anket: Okul memnuniyeti" in t and f'href="/anket/{aid}"' in t
    assert "Yanıtlamanı bekleyen" not in istemci.get("/anket").text  # anket sayfasında tekrar yok
    giris(istemci, "201", "ayse-sifre")  # 9-B: süzgeç yok, onun da görmesi beklenir
    assert "Yanıtlamanı bekleyen 1 anket var" in istemci.get("/ogrenci").text
    giris(istemci, "mudur", "mudur-sifre")
    assert "Yanıtlamanı bekleyen" not in istemci.get("/yonetici").text  # yönetici katılımcı değil


def test_modul_baglantilari(istemci, ornek):
    giris(istemci, "mudur", "mudur-sifre")
    y = istemci.get("/yonetici").text
    assert 'href="/yonetici/gelisim"' in y and 'href="/yonetici/anketler"' in y and 'href="/yonetici/oduller"' in y
    giris(istemci, "hoca", "hoca-sifre")
    assert 'href="/ogretmen/hizli"' in istemci.get("/ogretmen/odev/yeni").text
    assert 'href="/ogretmen/gelisim/9-A"' in istemci.get("/ogretmen/sinif/9-A").text


def test_bildirim_hatasi_sayfayi_bozmaz(istemci, ornek, monkeypatch):
    import anket

    def patla(c, k):
        raise RuntimeError("x")

    monkeypatch.setattr(anket, "bekleyen_sayisi", patla)
    giris(istemci, "101", "ali-sifre")
    r = istemci.get("/ogrenci")
    assert r.status_code == 200 and "Yanıtlamanı bekleyen" not in r.text


def test_oyun_alani_ve_yaris_seridi(istemci, ornek, conn, yeni_kullanici, saat):
    for no, ad, xp in ((950, "Zeynep Kaya", 90), (951, "Mert Demir", 40)):
        kid = yeni_kullanici(conn, "ogrenci", ad, str(no), sifre="x")
        conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (?, ?, '10-A', ?)", (no, ad, kid))
        conn.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (?, 'arena_bonus', 'x', ?, '2026-10-12', 'z')", (kid, xp))
    conn.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (?, 'arena_bonus', 'y', 60, '2026-10-12', 'z')", (ornek["ogr1_k"],))
    conn.commit()
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci").text
    assert "oyun-alani" in t and "Günlük Görev" in t and "Hızlı Mod" in t and "Bu haftanın XP yarışı" in t
    assert "Zeynep K." in t and 'href="/ogrenci/arena/liderlik"' in t and 'class="avatar"' in t
    assert "Sıran <b>2.</b>" in t and "1. sıradaki Zeynep K.'ı geçmek için <b>31 XP</b> daha" in t


def test_yaris_bos_ve_birinci_mesaji(istemci, ornek, conn, saat):
    giris(istemci, "101", "ali-sifre")
    assert "İlk sen ol!" in istemci.get("/ogrenci").text
    conn.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (?, 'arena_bonus', 'y', 60, '2026-10-12', 'z')", (ornek["ogr1_k"],))
    conn.commit()
    assert "Birincisin!" in istemci.get("/ogrenci").text


def test_alt_menu_oyun_odakli_ve_tek_aktif(istemci, ornek):
    import re

    giris(istemci, "101", "ali-sifre")
    for yol, aktif in (("/ogrenci/arena/liderlik", "Liderlik"), ("/ogrenci/arena", "Oyun"), ("/ogrenci", "Ana sayfa"), ("/duyurular", "Duyurular")):
        t = istemci.get(yol).text
        nav = t[t.index('<nav class="sekmeler"'):]
        nav = nav[:nav.index("</nav>")]
        assert [m for m in re.findall(r'<a href="[^"]+" class="aktif"[^>]*>.*?</svg>([^<]+)</a>', nav, re.S)] == [aktif], yol
        for ad in ("Oyun", "Liderlik", "Ödevler", "Duyurular"):
            assert ad in nav
