from datetime import datetime, timedelta

from fastapi.testclient import TestClient

import analitik
import auth
import zaman

SIMDI = datetime(2026, 10, 13, 14, 30, 0)


def _saat(monkeypatch, dt):
    monkeypatch.setattr(zaman, "simdi", lambda: dt)


def _filtre(conn, bas="2026-10-01", bit="2026-10-13", **kw):
    return analitik.filtre_coz(
        conn, bas, bit, kw.get("rol"), kw.get("sinif"), kw.get("duzey"),
        ("ogrenci", "veli", "ogretmen", "yonetici"),
    )


def _satirlar(conn):
    return conn.execute("SELECT * FROM olay ORDER BY id").fetchall()


def test_ayni_olay_tekrar_gonderilince_tek_kayit(conn, yeni_kullanici, monkeypatch):
    _saat(monkeypatch, SIMDI)
    k = yeni_kullanici(conn, "ogrenci", "A")
    for _ in range(5):  # sayfa yenileme / istemci tekrarı
        analitik.kaydet(k, "ogrenci", "ana_sayfa", token="t1")
    analitik.bosalt()
    assert len(_satirlar(conn)) == 1


def test_veritabani_tekilligi_onbellek_olmasa_da_korur(conn, yeni_kullanici, monkeypatch):
    _saat(monkeypatch, SIMDI)
    k = yeni_kullanici(conn, "ogrenci", "A")
    analitik.kaydet(k, "ogrenci", "ana_sayfa", token="t1")
    analitik.bosalt()
    analitik.sifirla()  # süreç yeniden başlamış gibi
    analitik.kaydet(k, "ogrenci", "ana_sayfa", token="t1")
    analitik.bosalt()
    assert len(_satirlar(conn)) == 1


def test_tampon_toplu_yazilir(conn, yeni_kullanici, monkeypatch):
    _saat(monkeypatch, SIMDI)
    k = yeni_kullanici(conn, "ogrenci", "A")
    analitik.kaydet(k, "ogrenci", "ana_sayfa", token="t")
    analitik.kaydet(k, "ogrenci", "duyuru_goruntule", token="t")
    assert _satirlar(conn) == []  # henüz tamponda
    analitik.bosalt()
    assert len(_satirlar(conn)) == 2


def test_cok_cihaz_tek_kullanici(conn, yeni_kullanici, monkeypatch):
    _saat(monkeypatch, SIMDI)
    k = yeni_kullanici(conn, "ogrenci", "A")
    for t in ("telefon", "tahta"):
        auth_token = auth.oturum_ac(conn, k, t)
        conn.execute("UPDATE oturum SET son_nabiz = ? WHERE token_hash = ?", (zaman.simdi_str(), auth._ozet(auth_token)))
        analitik.kaydet(k, "ogrenci", "aktif", "14", token=auth_token)
    conn.commit()
    analitik.bosalt()
    f = _filtre(conn)
    o = analitik.ozet(conn, f)
    assert o["cevrimici"] == 1 and o["bugun"] == 1 and o["hafta"] == 1


def test_cevrimici_90_saniye_siniri(conn, yeni_kullanici, monkeypatch):
    _saat(monkeypatch, SIMDI)
    k = yeni_kullanici(conn, "ogrenci", "A")
    t = auth.oturum_ac(conn, k)
    f = _filtre(conn)
    for sn, beklenen in ((89, 1), (91, 0)):
        conn.execute("UPDATE oturum SET son_nabiz = ?", ((SIMDI - timedelta(seconds=sn)).strftime(zaman.BICIM),))
        conn.commit()
        assert analitik.cevrimici(conn, f) == beklenen
    auth.oturum_kapat(conn, t)
    conn.execute("UPDATE oturum SET son_nabiz = ?", (SIMDI.strftime(zaman.BICIM),))
    assert analitik.cevrimici(conn, f) == 0  # kapatılan oturum sayılmaz


def test_pasif_kullanici_cevrimici_sayilmaz(conn, yeni_kullanici, monkeypatch):
    _saat(monkeypatch, SIMDI)
    k = yeni_kullanici(conn, "ogrenci", "A")
    auth.oturum_ac(conn, k)
    conn.execute("UPDATE oturum SET son_nabiz = ?", (SIMDI.strftime(zaman.BICIM),))
    conn.execute("UPDATE kullanici SET aktif = 0")
    conn.commit()
    assert analitik.cevrimici(conn, _filtre(conn)) == 0


def test_haftalik_aktif_7_takvim_gunu(conn, yeni_kullanici, monkeypatch):
    k = yeni_kullanici(conn, "ogrenci", "A")
    for gun_once in (0, 6, 7):
        _saat(monkeypatch, SIMDI - timedelta(days=gun_once))
        analitik.sifirla()
        analitik.kaydet(k, "ogrenci", "aktif", "14", token="t")
        analitik.bosalt()
    _saat(monkeypatch, SIMDI)
    o = analitik.ozet(conn, _filtre(conn))
    assert o["bugun"] == 1 and o["hafta"] == 1 and o["ay"] == 1
    k2 = yeni_kullanici(conn, "ogrenci", "B")
    _saat(monkeypatch, SIMDI - timedelta(days=7))
    analitik.kaydet(k2, "ogrenci", "aktif", "9", token="x")
    analitik.bosalt()
    _saat(monkeypatch, SIMDI)
    o = analitik.ozet(conn, _filtre(conn))
    assert o["hafta"] == 1 and o["ay"] == 2  # 7 gün önce haftaya girmez


def test_gecmis_gunler_veri_yok_sifir_degil(conn, yeni_kullanici, monkeypatch):
    _saat(monkeypatch, SIMDI)
    k = yeni_kullanici(conn, "ogrenci", "A")
    analitik.kaydet(k, "ogrenci", "aktif", "14", token="t")
    analitik.bosalt()
    g = analitik.gunluk(conn, _filtre(conn, bas="2026-10-10"))
    assert [d["n"] for d in g] == [None, None, None, 1]
    assert analitik.veri_baslangici(conn) == "2026-10-13"


def test_veri_yokken_bos_ve_cokmez(conn):
    f = _filtre(conn)
    assert analitik.veri_baslangici(conn) is None
    assert all(d["n"] is None for d in analitik.gunluk(conn, f))
    assert analitik.oneriler(analitik.ozet(conn, f), analitik.ozellikler(conn, f), analitik.oturum_terk(conn, f)) == []


def test_filtre_gecersiz_girdiyi_yok_sayar(conn):
    f = analitik.filtre_coz(conn, "x'; DROP TABLE olay;--", "2099-01-01", "admin", "9-Z", "99", ("ogrenci",))
    assert f.rol is None and f.sinif is None and f.duzey is None
    assert f.bit <= zaman.simdi().date().isoformat() and f.bas <= f.bit
    g = analitik.filtre_coz(conn, "2000-01-01", "2026-10-13", None, None, None, ())
    assert (datetime.fromisoformat(g.bit) - datetime.fromisoformat(g.bas)).days < analitik.EN_FAZLA_ARALIK


def test_sinif_ve_rol_filtresi(conn, yeni_kullanici, monkeypatch):
    _saat(monkeypatch, SIMDI)
    ka = yeni_kullanici(conn, "ogrenci", "A")
    kb = yeni_kullanici(conn, "ogrenci", "B")
    conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (1, 'A', '9-A', ?)", (ka,))
    conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (2, 'B', '10-A', ?)", (kb,))
    conn.commit()
    for k in (ka, kb):
        analitik.kaydet(k, "ogrenci", "aktif", "14", token=f"t{k}")
    analitik.bosalt()
    assert analitik.ozet(conn, _filtre(conn))["bugun"] == 2
    assert analitik.ozet(conn, _filtre(conn, sinif="9-A"))["bugun"] == 1
    assert analitik.ozet(conn, _filtre(conn, duzey="10"))["bugun"] == 1
    assert analitik.ozet(conn, _filtre(conn, rol="veli"))["bugun"] == 0


def test_ozellik_orani_ve_ilk_kullanim(conn, yeni_kullanici, monkeypatch):
    _saat(monkeypatch, SIMDI)
    ks = [yeni_kullanici(conn, "ogrenci", f"O{i}") for i in range(4)]
    for k in ks:
        analitik.kaydet(k, "ogrenci", "aktif", "14", token=f"t{k}")
    analitik.kaydet(ks[0], "ogrenci", "test_basla", "1", token=f"t{ks[0]}")
    analitik.bosalt()
    o = {x["tur"]: x for x in analitik.ozellikler(conn, _filtre(conn))}
    assert o["test_basla"]["kullanan"] == 1 and o["test_basla"]["oran"] == 25
    assert o["test_basla"]["ilk_tarih"] == "2026-10-13" and o["test_basla"]["yeni_kullanici"] == 1
    assert o["kazanim_raporu"]["kullanan"] == 0 and o["kazanim_raporu"]["ilk_tarih"] is None
    assert o["test_basla"]["egilim"]["durum"] == "yetersiz"  # 28 günlük veri yok → eğilim uydurulmaz


def test_oturum_terk_orani(conn, yeni_kullanici, monkeypatch):
    _saat(monkeypatch, SIMDI)
    for i in range(12):
        k = yeni_kullanici(conn, "ogrenci", f"O{i}")
        analitik.kaydet(k, "ogrenci", "giris", token=f"t{i}")
        analitik.kaydet(k, "ogrenci", "ana_sayfa", token=f"t{i}")
        if i < 3:  # yalnızca 3'ü temel işlem yaptı
            analitik.kaydet(k, "ogrenci", "odev_goruntule", "5", token=f"t{i}")
    analitik.bosalt()
    t = analitik.oturum_terk(conn, _filtre(conn))
    assert (t["giris"], t["giris_bos"], t["giris_oran"]) == (12, 9, 75)
    assert t["gun_oran"] == 75
    conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (1, 'A', '9-A', ?)", (k,))
    conn.commit()
    az = analitik.oturum_terk(conn, _filtre(conn, sinif="9-A"))
    assert az["giris"] == 1 and az["giris_oran"] is None  # 10'dan az oturum → oran verilmez


def test_hassas_icerik_kaydedilmez(conn):
    sutunlar = {r[1] for r in conn.execute("PRAGMA table_info(olay)")}
    assert sutunlar == {"id", "kullanici_id", "rol", "tur", "nesne", "gun", "saat", "oturum_k"}
    assert analitik.oturum_kodu("gizli-token") not in ("gizli-token",) and len(analitik.oturum_kodu("x")) == 12


def test_sayfa_olayi_esleme():
    assert analitik.sayfa_olayi("/ogrenci") == "ana_sayfa"
    assert analitik.sayfa_olayi("/ogrenci/odev/12") == "odev_goruntule"
    assert analitik.sayfa_olayi("/ogrenci/odev/12/test") is None
    assert analitik.sayfa_olayi("/veli/kazanim") == "veli_gelisim_raporu"
    assert analitik.sayfa_olayi("/ogrenci/kazanimlar") == "kazanim_raporu"
    assert analitik.sayfa_olayi("/veli/deneme") == "deneme_goruntule"
    assert analitik.sayfa_olayi("/ogrenci/deneme/3") == "deneme_goruntule"
    assert analitik.sayfa_olayi("/ogretmen/deneme/3/9-A") == "deneme_goruntule"
    assert analitik.sayfa_olayi("/yonetici/deneme/3") == "deneme_goruntule"
    assert analitik.sayfa_olayi("/veli/deneme/3/pdf") == "deneme_pdf"
    assert analitik.sayfa_olayi("/ogretmen/deneme/3/9-A/12/pdf") == "deneme_pdf"
    assert analitik.sayfa_olayi("/giris") is None


# --- web: yetki, nabız, olay kancaları ---


def _istemci(monkeypatch):
    from app import app
    return TestClient(app)


def _giris(c, conn, yeni_kullanici, rol, kadi):
    k = yeni_kullanici(conn, rol, kadi.title(), kadi, sifre="Parola123")
    r = c.post("/giris", data={"kullanici_adi": kadi, "sifre": "Parola123"}, follow_redirects=False)
    assert r.status_code == 303
    return k


def test_analitik_sayfasi_yalniz_yonetici(conn, yeni_kullanici, monkeypatch):
    with _istemci(monkeypatch) as c:
        assert c.get("/yonetici/analitik", follow_redirects=False).status_code == 303  # girişsiz
    for rol in ("ogrenci", "ogretmen"):
        with _istemci(monkeypatch) as c:
            _giris(c, conn, yeni_kullanici, rol, f"{rol}x")
            assert c.get("/yonetici/analitik").status_code == 404
    with _istemci(monkeypatch) as c:
        _giris(c, conn, yeni_kullanici, "yonetici", "yon")
        r = c.get("/yonetici/analitik?rol=hacker&sinif=%27;--&bas=zzz&bit=2999-01-01")
        assert r.status_code == 200 and "Kullanım analitiği" in r.text
        assert "geriye dönük üretilmez" in r.text or "Veri toplama başlangıcı" in r.text


def test_nabiz_csrfsiz_reddedilir_ve_cevrimici_yapar(conn, yeni_kullanici, monkeypatch):
    with _istemci(monkeypatch) as c:
        _giris(c, conn, yeni_kullanici, "ogrenci", "ogr1")
        assert c.post("/nabiz", data={}).status_code == 400
        sayfa = c.get("/duyurular").text
        csrf = sayfa.split('name="csrf" value="')[1].split('"')[0]
        assert "/static/nabiz.js" in sayfa
        assert c.post("/nabiz", data={"csrf": csrf}).status_code == 204
        assert analitik.cevrimici(conn, _filtre(conn)) == 1


def test_giris_cikis_ve_ana_sayfa_olaylari(conn, yeni_kullanici, monkeypatch):
    with _istemci(monkeypatch) as c:
        k = _giris(c, conn, yeni_kullanici, "ogrenci", "ogr2")
        conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (7, 'O', '9-A', ?)", (k,))
        conn.commit()
        for _ in range(3):
            c.get("/ogrenci")  # yenileme tek sayılır
        csrf = c.get("/ogrenci").text.split('name="csrf" value="')[1].split('"')[0]
        c.post("/cikis", data={"csrf": csrf})
    analitik.bosalt()
    turler = [r["tur"] for r in _satirlar(conn)]
    assert turler.count("giris") == 1 and turler.count("cikis") == 1
    assert turler.count("ana_sayfa") == 1 and turler.count("aktif") == 1
    assert all(len(r["oturum_k"]) == 12 for r in _satirlar(conn))


def test_basarisiz_giris_ve_404_olay_uretmez(conn, yeni_kullanici, monkeypatch):
    with _istemci(monkeypatch) as c:
        yeni_kullanici(conn, "ogrenci", "Ogr", "ogr3", sifre="Parola123")
        c.post("/giris", data={"kullanici_adi": "ogr3", "sifre": "yanlis"})
        _giris(c, conn, yeni_kullanici, "ogretmen", "ogrt3")
        assert c.get("/ogrenci").status_code == 404
    analitik.bosalt()
    assert [r["tur"] for r in _satirlar(conn)] == ["giris"]
