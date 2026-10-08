import json
from datetime import date

import pytest

from kazanimtest import agy_secim, calistir, cikti, google_form, hedef, secici

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
    def kaydet(c, s, d, h, kz, idler, f, x):
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
