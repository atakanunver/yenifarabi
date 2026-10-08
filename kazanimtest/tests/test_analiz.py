import json
from datetime import date, datetime, timezone

from kazanimtest import analiz

E = {"zorlanilan_esik": 0.5, "eksik_esik": 0.5, "guclu_esik": 0.8, "kazanim_min_soru": 2}


def _soru(i, kaz="K1", etiket="Kimya 9, s. 54", dogru=0):
    return {"kimlik": f"havuz:{i}", "soru": f"Soru {i} " + "x" * 200, "secenekler": list("abcd"),
            "dogru_index": dogru, "etiket": etiket, "kazanim_satiri": kaz}


def _test(i=1, sorular=None):
    return {"id": i, "ders": "kimya", "hafta": 1, "kazanim": "k", "form_url": "u",
            "olusturma": datetime(2026, 10, 7, 22, 30, tzinfo=timezone.utc), "sorular": sorular}


def _cv(no, doğrular, secilenler=None):
    return [(no, i, (secilenler[i] if secilenler else (0 if d else 1)), d) for i, d in enumerate(doğrular)]


def test_esik_sinirlari_ve_az_veri():
    sorular = [_soru(i) for i in range(2)] + [_soru(2, "K2"), _soru(3, "K3"), _soru(4, "K3")]
    # no1: K1 1/2=0.5 -> orta; K2 1/1 -> az_veri; K3 0/2 -> eksik
    # no2: K1 2/2 -> guclu ; K3 1/2 orta ; K2 0/1 az_veri
    c = _cv(1, [True, False, True, False, False]) + _cv(2, [True, True, False, True, False])
    r = analiz.analiz_hesapla("9-A", [_test(1, sorular)], {1: c}, E)
    d = {o["okul_no"]: {k["kazanim_satiri"]: k["durum"] for k in o["kazanimlar"]} for o in r["ogrenciler"]}
    assert d[1] == {"K1": "orta", "K2": "az_veri", "K3": "eksik"}
    assert d[2] == {"K1": "guclu", "K2": "az_veri", "K3": "orta"}
    o1 = r["ogrenciler"][0]
    assert (o1["eksik_sayisi"], o1["guclu_sayisi"]) == (1, 0)
    assert r["ogrenciler"][1]["guclu_sayisi"] == 1


def test_sinir_degerleri():
    assert analiz._durum(0.499, 2, E) == "eksik"
    assert analiz._durum(0.5, 2, E) == "orta"
    assert analiz._durum(0.8, 2, E) == "guclu"
    assert analiz._durum(0.0, 1, E) == "az_veri"


def test_zorlanilan_siralama_ve_soru_ozeti():
    sorular = [_soru(0, "A"), _soru(1, "B"), _soru(2, "C")]
    c = _cv(1, [True, False, False]) + _cv(2, [True, True, False])
    r = analiz.analiz_hesapla("9-A", [_test(1, sorular)], {1: c}, E)
    assert [(k["kazanim_satiri"], k["zorlanilan"]) for k in r["kazanimlar"]] == [("C", True), ("B", False), ("A", False)]
    assert r["kazanimlar"][0]["dogru_orani"] == 0.0
    assert r["testler"][0]["katilim"] == 2 and r["testler"][0]["ortalama_oran"] == 0.5
    assert len(r["testler"][0]["sorular"][0]["soru"]) == 120


def test_en_cok_secilen_yanlis():
    r = analiz.analiz_hesapla("9-A", [_test(1, [_soru(0)])], {1: [(1, 0, 2, False), (2, 0, 2, False), (3, 0, 1, False), (4, 0, 0, True)]}, E)
    assert r["testler"][0]["sorular"][0]["en_cok_secilen_yanlis"] == {"sik_harfi": "C", "oran": 0.5}
    r = analiz.analiz_hesapla("9-A", [_test(1, [_soru(0)])], {1: [(1, 0, 0, True)]}, E)
    assert r["testler"][0]["sorular"][0]["en_cok_secilen_yanlis"] is None


def test_sayfa_listesi_ve_birlestirme():
    assert analiz.sayfalari_birlestir(["Kimya 9, s. 55", "Kimya 9, s. 54", "Kimya 9, s. 54", "Kimya 9, s. 60", "Biyoloji 9, s. 3", "x"]) == [
        "Biyoloji 9, s. 3", "Kimya 9, s. 54-55", "Kimya 9, s. 60", "x"]
    sorular = [_soru(0, etiket="Kimya 9, s. 54"), _soru(1, etiket="Kimya 9, s. 55"), _soru(2, etiket="Kimya 9, s. 9")]
    r = analiz.analiz_hesapla("9-A", [_test(1, sorular)], {1: [(1, 0, 1, False), (1, 1, None, False), (1, 2, 0, True)]}, E)
    assert r["ogrenciler"][0]["kazanimlar"][0]["sayfalar"] == ["Kimya 9, s. 54-55"]


def test_sorular_null_atlanir():
    r = analiz.analiz_hesapla("9-A", [_test(1, None), _test(2, [_soru(0)])], {2: [(1, 0, 0, True)]}, E)
    assert [t["id"] for t in r["testler"]] == [2]
    assert r["testler"][0]["tarih"] == "2026-10-08"  # 22:30 UTC = 01:30 TR ertesi gün


def test_atomik_yazim(tmp_path, monkeypatch):
    yol = tmp_path / "rapor" / "9-A.json"
    analiz.atomik_yaz(yol, {"a": "çğ"})
    assert json.loads(yol.read_text(encoding="utf-8")) == {"a": "çğ"} and "çğ" in yol.read_text(encoding="utf-8")
    analiz.atomik_yaz(yol, {"a": 2})
    assert list(yol.parent.iterdir()) == [yol]
    # yazım bozulursa eski dosya korunur, tmp kalmaz
    def boz(a, b):
        raise OSError("x")
    monkeypatch.setattr(analiz.os, "replace", boz)
    try:
        analiz.atomik_yaz(yol, {"a": 3})
    except OSError:
        pass
    assert json.loads(yol.read_text()) == {"a": 2} and list(yol.parent.iterdir()) == [yol]


def test_aralik_ve_esikler_oku():
    assert analiz.esikler_oku({"guclu_esik": 0.9})["guclu_esik"] == 0.9
    assert analiz.esikler_oku(None)["kazanim_min_soru"] == 2
    assert analiz._tr_gun(datetime(2026, 10, 7, 22, 30, tzinfo=timezone.utc)) == date(2026, 10, 8)
