import json
from datetime import UTC, date, datetime

import pytest

from kazanimtest import aylik, google_form

E = {"zorlanilan_esik": 0.5, "eksik_esik": 0.5, "guclu_esik": 0.8, "kazanim_min_soru": 2}
SCRIPT_URL = "https://script.google.com/macros/s/" + "A" * 70 + "/exec"
GIZLI = {"script_url": SCRIPT_URL, "anahtar": "K", "sms_arac_anahtar": "S", "test_telefon": "05000000000"}
AYAR = {"rapor_sms_sablon": "{ad} için {ay_adi} kazanım raporu: {link}", "sms_url": "http://sms", "rapor_gecerlilik_gun": 90}


def _analiz():
    """9-A: kimya iki kazanım. no1 K1 2/2 (güçlü), K2 0/2 (eksik); no2 K1 1/2 (orta), K2 2/2 (güçlü)."""
    def k(ders, satir, soru, dogru, sayfa):
        return {"ders": ders, "kazanim_satiri": satir, "soru": soru, "dogru": dogru, "oran": dogru / soru,
                "durum": "guclu" if dogru / soru >= 0.8 else ("eksik" if dogru / soru < 0.5 else "orta"),
                "sayfalar": sayfa}
    return {
        "sinif": "9-A",
        "testler": [{"id": 1}],
        "kazanimlar": [
            {"ders": "kimya", "kazanim_satiri": "K1", "soru_sayisi": 2, "cevap_sayisi": 4, "dogru_orani": 0.75, "zorlanilan": False},
            {"ders": "kimya", "kazanim_satiri": "K2", "soru_sayisi": 2, "cevap_sayisi": 4, "dogru_orani": 0.5, "zorlanilan": False},
        ],
        "ogrenciler": [
            {"okul_no": 1, "test_sayisi": 1, "dogru": 2, "toplam": 4, "oran": 0.5,
             "kazanimlar": [k("kimya", "K1", 2, 2, []), k("kimya", "K2", 2, 0, ["Kimya 9, s. 54-55"])]},
            {"okul_no": 2, "test_sayisi": 1, "dogru": 3, "toplam": 4, "oran": 0.75,
             "kazanimlar": [k("kimya", "K1", 2, 1, ["Kimya 9, s. 10"]), k("kimya", "K2", 2, 2, [])]},
            {"okul_no": 3, "test_sayisi": 0, "dogru": 0, "toplam": 0, "oran": 0.0, "kazanimlar": []},
        ],
    }


def test_ay_araligi():
    assert aylik.ay_araligi("2026-10") == (date(2026, 10, 1), date(2026, 10, 31))
    assert aylik.ay_araligi("2026-12") == (date(2026, 12, 1), date(2026, 12, 31))
    assert aylik.ay_araligi("2028-02")[1] == date(2028, 2, 29)
    assert aylik.ay_araligi(None, date(2026, 1, 15)) == (date(2025, 12, 1), date(2025, 12, 31))
    assert aylik.ay_araligi(None, date(2026, 10, 1)) == (date(2026, 9, 1), date(2026, 9, 30))


def test_rapor_verisi_sinif_orani_ve_katilmayan_yok():
    r = aylik.rapor_verisi(_analiz(), date(2026, 10, 1), lambda d: d.capitalize())
    assert [x["okul_no"] for x in r] == [1, 2]  # no3 katılmamış → rapor yok
    x = r[0]
    assert x["ay"] == "2026-10" and x["ay_adi"] == "Ekim 2026" and x["sinif"] == "9-A"
    assert x["genel"] == {"oran": 0.5, "sinif_orani": 0.625, "test_sayisi": 1}  # 5/8
    d = x["dersler"][0]
    assert d["ders"] == "Kimya" and d["oran"] == 0.5 and d["sinif_orani"] == 0.625
    assert [k["durum"] for k in d["kazanimlar"]] == ["eksik", "guclu"]  # eksik önce
    assert x["eksikler"] == [{"ders": "Kimya", "kazanim_satiri": "K2", "sayfalar": ["Kimya 9, s. 54-55"]}]
    assert x["gucluler"] == [{"ders": "Kimya", "kazanim_satiri": "K1"}]


def _anahtarlar(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _anahtarlar(v)
    elif isinstance(o, list):
        for v in o:
            yield from _anahtarlar(v)


def test_rapor_verisinde_isim_telefon_yok():
    for r in aylik.rapor_verisi(_analiz(), date(2026, 10, 1)):
        yasak = {"ad", "isim", "ad_soyad", "adi", "soyad", "telefon", "tel", "veli", "veli_telefon", "eposta"}
        assert not yasak & {str(k).lower() for k in _anahtarlar(r)}
        assert set(r) == {"sinif", "okul_no", "ay", "ay_adi", "genel", "dersler", "eksikler", "gucluler"}


class _Cur:
    def __init__(s, c): s.c = c
    def __enter__(s): return s
    def __exit__(s, *a): pass
    def execute(s, q, p):
        s.c.sql.append(q)
        ay, _sinif, no, tok, _sg = p
        s.c.tablo.setdefault((ay, no), [tok, None])  # ON CONFLICT: mevcut token korunur
    def fetchone(s):
        ay, no = s.c.sql_p
        return tuple(s.c.tablo[(ay, no)])


class _Conn:
    def __init__(s): s.tablo, s.sql, s.sql_p = {}, [], None
    def cursor(s, **k): return _Cur(s)
    def commit(s): pass


def test_token_yeniden_kullanilir():
    c = _Conn()
    orijinal = _Cur.execute
    def ex(s, q, p):
        orijinal(s, q, p)
        s.c.sql_p = (p[0], p[2])
    _Cur.execute = ex
    try:
        t1, _ = aylik.token_al(c, "2026-10", "9-A", 7, date(2027, 1, 1), uretici=lambda: "ilk")
        t2, _ = aylik.token_al(c, "2026-10", "9-A", 7, date(2027, 1, 1), uretici=lambda: "ikinci")
    finally:
        _Cur.execute = orijinal
    assert t1 == t2 == "ilk"
    assert "ON CONFLICT (ay, okul_no) DO UPDATE" in c.sql[0] and "token=EXCLUDED" not in c.sql[0].replace(" ", "")


def test_sablon_ad_korunur():
    m = aylik.sablon_doldur(AYAR["rapor_sms_sablon"], "Ekim 2026", "http://x/exec?r=abc")
    assert m == "{ad} için Ekim 2026 kazanım raporu: http://x/exec?r=abc"
    assert "{ad}" in m and "{ay_adi}" not in m and "{link}" not in m


def test_300_karaktere_sigar():
    link = f"{SCRIPT_URL}?r=" + "T" * 22
    m = aylik.sablon_doldur(AYAR["rapor_sms_sablon"], "Ağustos 2026", link)
    assert aylik.sablon_sigiyor_mu(m, 300)
    assert len(m.replace("{ad}", "X" * 45)) < 300
    assert not aylik.sablon_sigiyor_mu(m + "x" * 200, 300)


class _Yanit:
    def __init__(s, v): s.v, s.text = v, json.dumps(v)
    def raise_for_status(s): pass
    def json(s): return s.v


class _Http:
    def __init__(s, taslak=None):
        s.cagrilar = []
        s.taslak = taslak
    def post(s, url, json=None, **kw):
        s.cagrilar.append((url, json))
        if url.endswith("rapor_yaz") or json.get("islem") == "rapor_yaz":
            return _Yanit({"ok": True, "yazilan": len(json["raporlar"])})
        if url.endswith("/kisisel-taslak"):
            return _Yanit(s.taslak or {"taslak_id": "T1", "oge_sayisi": len(json["ogeler"]), "alici_sayisi": 2,
                                       "bulunamayan": [], "alicisiz": []})
        if url.endswith("/kisisel-gonder"):
            return _Yanit({"gonderim_id": "G1"})
        raise AssertionError(url)


def test_raporlari_yaz_50lik_partiler():
    h = _Http()
    rap = [{"token": str(i), "ay": "2026-10", "sinif": "9-A", "okul_no": i, "son_gecerlilik": "2027-01-01", "veri": {}} for i in range(120)]
    assert google_form.raporlari_yaz(GIZLI, rap, h) == 120
    assert [len(c[1]["raporlar"]) for c in h.cagrilar] == [50, 50, 20]
    assert all(c[1]["islem"] == "rapor_yaz" and c[1]["anahtar"] == "K" for c in h.cagrilar)


def test_raporlari_yaz_eksik_yazilan_hata():
    class H(_Http):
        def post(s, url, json=None, **kw):
            return _Yanit({"ok": True, "yazilan": 0})
    with pytest.raises(google_form.FormHatasi):
        google_form.raporlari_yaz(GIZLI, [{"token": "a"}], H())


@pytest.fixture
def duzen(monkeypatch):
    kayit = {"isaret": [], "tablo": {}}
    monkeypatch.setattr(aylik, "siniflar", lambda conn, b, s: ["9-A"])
    monkeypatch.setattr(aylik.analiz, "sinif_analizi", lambda conn, sn, b, s, e: _analiz())
    def token_al(conn, ay, sinif, no, sg, uretici=None):
        return kayit["tablo"].setdefault(no, [f"tok{no}", None])[0], kayit["tablo"][no][1]
    monkeypatch.setattr(aylik, "token_al", token_al)
    monkeypatch.setattr(aylik, "sms_isaretle", lambda conn, ay, nolar, t, g: kayit["isaret"].append((ay, nolar, t, g)))
    class Conn:
        def rollback(s): pass
        def close(s): pass
    return kayit, Conn()


def _calis(duzen, **kw):
    _, conn = duzen
    h = kw.pop("http", _Http())
    hata = aylik.aylik("2026-10", ayar=AYAR, havuz_conn=conn, gizli=GIZLI, istemci=h, bugun=date(2026, 11, 1),
                       ders_gosterim=str.capitalize, **kw)
    return hata, h


def test_kuru_hicbir_sey_yazmaz(duzen):
    hata, h = _calis(duzen, kuru=True, sms=True)
    assert hata == 0 and h.cagrilar == [] and duzen[0]["isaret"] == [] and duzen[0]["tablo"] == {}


def test_sms_yok_ise_yalniz_google(duzen):
    hata, h = _calis(duzen)
    assert hata == 0 and len(h.cagrilar) == 1 and h.cagrilar[0][1]["islem"] == "rapor_yaz"
    yazilan = h.cagrilar[0][1]["raporlar"][0]
    assert yazilan["son_gecerlilik"] == "2027-01-30" and yazilan["token"] == "tok1" and yazilan["okul_no"] == 1
    assert not {"ad", "telefon", "isim"} & set(_anahtarlar(yazilan))


def test_sms_test_akisi_isaretlemez(duzen):
    hata, h = _calis(duzen, sms_test=True)
    assert hata == 0 and duzen[0]["isaret"] == []
    taslak = next(c for c in h.cagrilar if c[0].endswith("/kisisel-taslak"))[1]
    assert taslak["test_telefon"] == "05000000000"
    assert [o["okul_no"] for o in taslak["ogeler"]] == [1, 2]
    assert taslak["ogeler"][0]["metin_sablon"] == f"{{ad}} için Ekim 2026 kazanım raporu: {SCRIPT_URL}?r=tok1"
    assert any(c[0].endswith("/kisisel-gonder") for c in h.cagrilar)


def test_gercek_gonderim_isaretler_ve_tekrar_gondermez(duzen):
    kayit, _ = duzen
    h = _Http(taslak={"taslak_id": "T1", "oge_sayisi": 1, "alici_sayisi": 2, "bulunamayan": [2], "alicisiz": []})
    _calis(duzen, sms=True, http=h)
    assert "test_telefon" not in next(c for c in h.cagrilar if c[0].endswith("/kisisel-taslak"))[1]
    assert kayit["isaret"] == [("2026-10", [1], "T1", "G1")]  # bulunamayan (2) işaretlenmez
    # ikinci çalıştırma: no1 gönderilmiş sayılır, yalnız no2 yeniden denenir
    kayit["tablo"][1][1] = "G1"
    h2 = _Http()
    _calis(duzen, sms=True, http=h2)
    taslak = next(c for c in h2.cagrilar if c[0].endswith("/kisisel-taslak"))[1]
    assert [o["okul_no"] for o in taslak["ogeler"]] == [2]
    kayit["tablo"][2][1] = "G2"
    h3 = _Http()
    _calis(duzen, sms=True, http=h3)
    assert not any("kisisel" in c[0] for c in h3.cagrilar)


def test_sigmayan_sablon_sms_atmaz(duzen):
    ayar = dict(AYAR, rapor_sms_sablon="{ad} " + "x" * 280 + " {link}")
    _, conn = duzen
    h = _Http()
    with pytest.raises(RuntimeError):
        aylik.aylik("2026-10", ayar=ayar, havuz_conn=conn, gizli=GIZLI, istemci=h, bugun=date(2026, 11, 1),
                    ders_gosterim=str.capitalize, sms=True)
    assert not any("kisisel" in c[0] for c in h.cagrilar)


def test_sms_test_telefonsuz_hata(duzen):
    g = {k: v for k, v in GIZLI.items() if k != "test_telefon"}
    _, conn = duzen
    with pytest.raises(RuntimeError):
        aylik.aylik("2026-10", ayar=AYAR, havuz_conn=conn, gizli=g, istemci=_Http(), bugun=date(2026, 11, 1),
                    ders_gosterim=str.capitalize, sms_test=True)


def test_siniflar_ay_filtresi():
    class Cur:
        def __enter__(s): return s
        def __exit__(s, *a): pass
        def execute(s, q): pass
        def fetchall(s):
            return [("9-A", datetime(2026, 10, 7, 22, 30, tzinfo=UTC)),   # TR: 8 Ekim
                    ("9-B", datetime(2026, 9, 30, 22, 0, tzinfo=UTC)),    # TR: 1 Ekim
                    ("10-A", datetime(2026, 10, 31, 22, 0, tzinfo=UTC)),  # TR: 1 Kasım → dışarıda
                    ("11-A", datetime(2026, 9, 30, 20, 0, tzinfo=UTC))]   # TR: 30 Eylül → dışarıda
    class C:
        def cursor(s): return Cur()
    assert aylik.siniflar(C(), date(2026, 10, 1), date(2026, 10, 31)) == ["9-A", "9-B"]
