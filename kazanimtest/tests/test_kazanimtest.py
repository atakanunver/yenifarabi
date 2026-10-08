import json
from datetime import date

import pytest

from kazanimtest import (
    agy_secim,
    anlik,
    calistir,
    cikti,
    google_form,
    hedef,
    secici,
    sonuc,
)

PROGRAM = {"siniflar": {"9-A": {"sali": {"1": "tarih", "2": "tarih", "7": "biyoloji"}},
                         "12-A": {"sali": {"1": "hedef fizik", "2": "türk dili ve edebiyatı"}}}}
KZ = {"haftalar": {"4": "2026-10-05"},
      "kazanimlar": {"9": {"biyoloji": {"4": "Hücre\nZar"}, "tarih": {"4": "X"}},
                     "12": {"hedef fizik": {"4": "Dairesel hareket"}, "türk dili ve edebiyatı": {"4": "Şiir"}}}}
SALI = date(2026, 10, 6)


def _aday(i, dogru=1):
    return {"kimlik": f"havuz:{i}", "kaynak": "havuz", "db_id": i, "soru": f"S{i}?",
            "secenekler": ["a", "b", "c", "d"], "dogru_index": dogru, "etiket": "k", "benzerlik": 1 - i / 100}


def test_hedef_beyaz_liste_ve_esleme():
    assert hedef.hedefler(SALI, {"dersler": []}, program=PROGRAM, kz=KZ) == []
    h = hedef.hedefler(SALI, {"dersler": ["fizik", "edebiyat", "biyoloji"]}, program=PROGRAM, kz=KZ)
    assert [(x.sinif, x.ders) for x in h] == [("12-A", "fizik"), ("12-A", "edebiyat"), ("9-A", "biyoloji")]
    assert h[0].kazanimlar == ["Dairesel hareket"] and h[1].hafta == 4
    # tarih: kazanım var ama beyaz listede yok; aynı ders iki saat olsa tek kayıt
    h2 = hedef.hedefler(SALI, {"dersler": ["tarih"]}, program=PROGRAM, kz=KZ)
    assert len(h2) == 1
    assert hedef.hedefler(date(2026, 10, 10), {"dersler": ["tarih"]}, program=PROGRAM, kz=KZ) == []  # hafta sonu


def test_hedef_duzey_suzgeci():
    ayar = {"dersler": ["fizik", "biyoloji"], "duzeyler": [9, 10]}
    assert [(x.sinif, x.ders) for x in hedef.hedefler(SALI, ayar, program=PROGRAM, kz=KZ)] == [("9-A", "biyoloji")]
    ayar["duzeyler"] = []  # boş = tümü
    assert len(hedef.hedefler(SALI, ayar, program=PROGRAM, kz=KZ)) == 2


def test_agy_dusus_ve_secim():
    ad = [_aday(i) for i in range(5)]
    def kotu(*a, **k):
        raise OSError("yok")
    assert [a["db_id"] for a in agy_secim.sec(["k"], ad, 3, cagir=kotu)] == [0, 1, 2]
    cevap = json.dumps({"secilen": [4, 2, 4, 99], "red": []})
    assert [a["db_id"] for a in agy_secim.sec(["k"], ad, 3, cagir=lambda *a, **k: cevap)] == [4, 2, 0]
    assert agy_secim.yaniti_coz("bozuk", 5) == []
    sarili = json.dumps({"response": "```json\n" + cevap + "\n```"})
    assert agy_secim.yaniti_coz(sarili, 5) == [4, 2]


def test_secici_adaylar_meb_once(monkeypatch):
    monkeypatch.setattr(secici, "vektor", lambda m, model=None: [0.0])
    monkeypatch.setattr(secici, "meb_adaylari", lambda *a: [_aday(1)])
    monkeypatch.setattr(secici, "havuz_adaylari", lambda c, d, de, v, lim, model=None: [_aday(i) for i in range(10, 10 + lim)])
    r = secici.adaylar(None, None, 12, "fizik", "k", azami=4)
    assert [a["db_id"] for a in r] == [1, 10, 11, 12]


def test_cikti_ve_form_govdesi(tmp_path):
    sorular = [_aday(i) for i in range(3)]
    t = cikti.dosya_tabani(tmp_path, SALI, "9-A", "biyoloji")
    assert cikti.excel_yaz(t, "B", sorular).exists() and cikti.word_yaz(t, "B", sorular).exists()
    g = google_form.govde("AN", "B", "A", sorular)
    assert g["sorular"][0]["dogru_index"] == 1 and len(g["sorular"][0]["secenekler"]) == 4 and g["anahtar"] == "AN"

    class R:
        def __init__(s, v): s.v = v
        def json(s): return s.v
    class K:
        def __init__(s, v): s.v = v
        def post(s, url, **kw):
            assert kw["follow_redirects"] and kw["json"]["anahtar"] == "AN"
            return R(s.v)
    ok = {"ok": True, "form_url": "u", "form_kisa_url": "k", "form_id": "i", "tablo_url": "t"}
    assert google_form.form_olustur({"script_url": "x", "anahtar": "AN"}, "B", "A", sorular, K(ok))["form_id"] == "i"
    with pytest.raises(google_form.FormHatasi):
        google_form.form_olustur({"script_url": "x", "anahtar": "AN"}, "B", "A", sorular, K({"ok": False, "hata": "yetkisiz"}))


def test_sms_parcala_limit():
    tek = calistir.sms_metni_parcala([("Biyoloji", "https://forms.gle/a"), ("Fizik", "https://forms.gle/b")])
    assert len(tek) == 1 and tek[0].startswith("Bugünkü kazanım testleriniz: Biyoloji")
    cok = calistir.sms_metni_parcala([(f"Ders{i}", "https://forms.gle/" + "x" * 40) for i in range(12)])
    assert len(cok) > 1 and all(len(p) <= 300 for p in cok)


def test_sms_test_alani(monkeypatch):
    gonderilen = []
    class R:
        def __init__(s, v): s.v = v; s.text = ""
        def raise_for_status(s): pass
        def json(s): return s.v
    class K:
        def post(s, url, **kw):
            gonderilen.append((url, kw["json"]))
            return R({"taslak_id": 7})
    g = {"sms_arac_anahtar": "k"}
    calistir.sms_gonder(g, {}, "9-A", "m", K(), test_telefon="05000000000")
    assert gonderilen[0][1]["test_telefon"] == "05000000000"
    gonderilen.clear()
    calistir.sms_gonder(g, {}, "9-A", "m", K())
    assert "test_telefon" not in gonderilen[0][1]
    with pytest.raises(RuntimeError):
        calistir.sinif_sms("9-A", [{"id": 1, "ders": "fizik", "form_url": "u"}], {}, g, None, test=True)


def test_uret_unique_ve_hata_devami(monkeypatch, tmp_path):
    ayar = {"dersler": ["fizik", "edebiyat"], "soru_sayisi": 3, "min_soru": 2, "cikti_dizini": str(tmp_path)}
    monkeypatch.setattr(hedef, "yukle", lambda ad, dizin=None: PROGRAM if "program" in ad else KZ)
    class C:
        def rollback(s): pass
        def close(s): pass
    monkeypatch.setattr(secici, "baglan", lambda db: C())
    monkeypatch.setattr(secici, "adaylar", lambda *a, **k: [_aday(i) for i in range(5)])
    monkeypatch.setattr(agy_secim, "agy_cagir", lambda *a, **k: "{}")
    monkeypatch.setattr(google_form, "gizli_oku", lambda: {"script_url": "x", "anahtar": "a"})
    kayitlar = {}
    cagrilar = []
    def form(gizli, baslik, aciklama, sorular, istemci=None):
        cagrilar.append(baslik)
        if "edebiyat" in baslik.lower():
            raise google_form.FormHatasi("x")
        return {"form_url": "u", "form_kisa_url": "k", "form_id": "i", "tablo_url": "t"}
    monkeypatch.setattr(google_form, "form_olustur", form)
    monkeypatch.setattr(calistir.kayit, "var_mi", lambda c, s, d, h: kayitlar.get((s, d, h)))
    def kaydet(c, s, d, h, kz, idler, f, x, sorular=None):
        kayitlar[(s, d, h)] = {"id": 1, "sinif": s, "ders": d, **f}
        return True
    monkeypatch.setattr(calistir.kayit, "kaydet", kaydet)
    monkeypatch.setattr(calistir.kayit, "kullanim_artir", lambda c, i: None)
    hata = calistir.uret(SALI, kuru=False, ayar=ayar)
    assert hata == 1 and ("12-A", "fizik", 4) in kayitlar and len(cagrilar) == 2  # edebiyat hatası fizik'i durdurmadı
    cagrilar.clear()
    calistir.uret(SALI, sinif="12-A", ders="fizik", ayar=ayar)
    assert cagrilar == []  # ikinci kez form açılmadı
    kayitlar.clear()
    calistir.uret(SALI, kuru=True, ayar=ayar)
    assert cagrilar == [] and not kayitlar and list(tmp_path.glob("*.xlsx"))


def test_agy_structured_output_ve_hata_durumu():
    from kazanimtest import agy_secim

    yapisal = json.dumps({"status": "OK", "response": "", "structured_output": {"secilen": [2, 0], "red": []}})
    assert agy_secim.yaniti_coz(yapisal, 5) == [2, 0]
    hata = json.dumps({"status": "ERROR", "error": "Individual quota reached", "response": ""})
    assert agy_secim.yaniti_coz(hata, 5) == []


# ---- Faz 2: sonuç çekme ----
SORULAR = [
    {"kimlik": "havuz:1", "soru": "S1", "secenekler": ["a", "b", "c", "d"], "dogru_index": 1},
    {"kimlik": "havuz:2", "soru": "S2", "secenekler": ["w", "x", "y", "z"], "dogru_index": 3},
]


def _g(zaman, no, secimler):
    return {"zaman": zaman, "okul_no": no, "secimler": secimler}


def test_cevap_esleme_dogru_yanlis_bos_bilinmeyen():
    satirlar, ist = sonuc.cevaplari_coz(SORULAR, [_g("2026-10-08T10:00:00.000Z", "12", [" b ", None]),
                                                  _g("2026-10-08T10:01:00.000Z", "13.0", ["a", "????"])])
    s = {(r[0], r[1]): r[2:4] for r in satirlar}
    assert s[(12, 0)] == (1, True) and s[(12, 1)] == (None, False)  # doğru; boş
    assert s[(13, 0)] == (0, False) and s[(13, 1)] == (None, False)  # yanlış; bilinmeyen şık
    assert ist["eslesmeyen_sik"] == 1 and ist["gecersiz_no"] == 0
    assert satirlar[0][4].tzinfo is not None


def test_gecersiz_okul_no_atlanir():
    satirlar, ist = sonuc.cevaplari_coz(SORULAR, [_g("2026-10-08T10:00:00Z", "abc", ["a", "w"]),
                                                  _g("2026-10-08T10:00:00Z", "", ["a", "w"]),
                                                  _g("2026-10-08T10:00:00Z", "12.5", ["a", "w"])])
    assert satirlar == [] and ist["gecersiz_no"] == 3


def test_ilk_gonderim_sayilir():
    # geç gelen listede önde olsa da en erken zamanlı olan sayılır
    satirlar, ist = sonuc.cevaplari_coz(SORULAR, [_g("2026-10-08T10:05:00Z", "7", ["a", "w"]),
                                                  _g("2026-10-08T10:01:00Z", "7", ["b", "z"])])
    assert ist["tekrar"] == 1 and len(satirlar) == 2
    assert [r[3] for r in satirlar] == [True, True]


def test_cevap_yaz_on_conflict_ve_sayim():
    from kazanimtest import kayit

    sql = []
    class Cur:
        rowcount = 1
        def __enter__(s): return s
        def __exit__(s, *a): pass
        def execute(s, q, p): sql.append(q)
    class C:
        def cursor(s, **k): return Cur()
        def commit(s): pass
    import datetime
    assert kayit.cevap_yaz(C(), 5, [(1, 0, 1, True, datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC))] * 2) == 2
    assert all("ON CONFLICT (form_testi_id, okul_no, soru_sira) DO NOTHING" in q for q in sql)


def test_anlik_kazanim_satiri_secimi():
    class M:  # satırlar: 0 → [1,0], 1 → [0,1]; soru "S1" → [1,0], "S2" → [0,1]
        def encode(s, x, normalize_embeddings=True):
            tablo = {"S1": [1.0, 0.0], "S2": [0.0, 1.0], "kz-a": [1.0, 0.0], "kz-b": [0.0, 1.0]}
            return [tablo[i] for i in x] if isinstance(x, list) else tablo[x]
    g = anlik.olustur(SORULAR, "kz-a\n\nkz-b", M())
    assert [x["kazanim_satiri"] for x in g] == ["kz-a", "kz-b"]
    assert g[0]["dogru_index"] == 1 and g[0]["kimlik"] == "havuz:1"
    # tek satır: model hiç yüklenmez
    assert [x["kazanim_satiri"] for x in anlik.olustur(SORULAR, ["tek"], model=None)] == ["tek", "tek"]


def test_anlik_doldur_eski_kayit(monkeypatch):
    yazilan = {}
    class K:
        @staticmethod
        def anliksiz_kayitlar(c): return [{"id": 3, "soru_idler": ["havuz:1", "meb:2"], "kazanim": "tek"},
                                         {"id": 4, "soru_idler": ["havuz:9"], "kazanim": "tek"}]
        @staticmethod
        def anlik_yaz(c, i, s): yazilan[i] = s
    monkeypatch.setattr(anlik, "soru_oku", lambda kim, f, h: None if kim == "havuz:9" else {**SORULAR[0], "kimlik": kim})
    assert anlik.doldur(None, None, K) == (1, 1)
    assert yazilan[3][1]["kimlik"] == "meb:2" and yazilan[3][0]["kazanim_satiri"] == "tek" and 4 not in yazilan


def test_form_hatasi_digerlerini_durdurmaz(monkeypatch):
    formlar = [{"id": 1, "form_id": "f1", "sinif": "9-A", "ders": "x", "hafta": 1, "sorular": SORULAR},
               {"id": 2, "form_id": "f2", "sinif": "9-A", "ders": "y", "hafta": 1, "sorular": SORULAR}]
    monkeypatch.setattr(sonuc.kayit, "son_gun_formlari", lambda c, g: formlar)
    yazilan = []
    monkeypatch.setattr(sonuc.kayit, "cevap_yaz", lambda c, i, s: yazilan.append(i) or len(s))
    def al(gizli, fid, istemci=None):
        if fid == "f1":
            raise google_form.FormHatasi("ağ")
        return [_g("2026-10-08T10:00:00Z", "5", ["b", "z"])]
    monkeypatch.setattr(google_form, "sonuclari_al", al)
    class C:
        def rollback(s): pass
    assert sonuc.calis(C(), {}) == 1 and yazilan == [2]


def test_sonuclari_al_istegi_ve_form_olustur_govdesi_degismedi():
    gonderilen = {}
    class R:
        def json(s): return {"ok": True, "cevaplar": [{"zaman": "z"}]}
    class K:
        def post(s, url, **kw):
            gonderilen.update(kw)
            return R()
    assert google_form.sonuclari_al({"script_url": "x", "anahtar": "AN", "proxy": "p"}, "F", K()) == [{"zaman": "z"}]
    assert gonderilen["json"] == {"anahtar": "AN", "islem": "sonuclar", "form_id": "F"} and gonderilen["proxy"] == "p"
    assert set(google_form.govde("AN", "B", "A", [_aday(1)])) == {"anahtar", "baslik", "aciklama", "sorular"}  # 'islem' yok
    assert "islem" not in google_form.govde("AN", "B", "A", [_aday(1)])


def test_tekrarli_post_html_donerse_tekrar_dener(monkeypatch):
    monkeypatch.setattr(google_form.time, "sleep", lambda s: None)

    class Yanit:
        def __init__(self, govde):
            self.govde = govde

        def json(self):
            return json.loads(self.govde)

    class Istemci:
        def __init__(self, yanitlar):
            self.yanitlar, self.cagri = list(yanitlar), 0

        def post(self, url, **kw):
            self.cagri += 1
            return Yanit(self.yanitlar.pop(0))

    k = Istemci(["<html>Kazanım raporu</html>", '{"ok": true, "yazilan": 1}'])
    assert google_form._tekrarli_post(k, "u") == {"ok": True, "yazilan": 1} and k.cagri == 2
    k = Istemci(["<html>", "<html>", "<html>"])
    with pytest.raises(ValueError):
        google_form._tekrarli_post(k, "u")
    assert k.cagri == 3
