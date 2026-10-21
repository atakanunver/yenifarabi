import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import atos_wiki as w
import auth

ANAHTAR = "wiki-test-anahtari"
B = {"X-Farabi-WebUI-Key": ANAHTAR}
SAYFA = {
    "ad": "Liste",
    "baslik": ["SN", "Adı-Soyadı", "T.C Kimlik No", "Branşı"],
    "satirlar": [["1", "Ayşe Çelik", "12345678901", "Matematik"], ["2", "Mehmet Öz", "98765432109", "Fizik"]],
}


@pytest.fixture
def ist(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "webui_anahtari", lambda: ANAHTAR)
    monkeypatch.setattr(w, "DIZIN", tmp_path / "wiki")
    app = FastAPI()
    app.include_router(w.router)
    return TestClient(app), tmp_path / "wiki"


def _kaydet(c, ad="EKD Çizelgesi", sayfa=SAYFA):
    return c.post("/api/webui/wiki/kaydet", headers=B, json={"ad": ad, "kaynak": "ekd.xls", "sayfalar": [sayfa]}).json()


def test_anahtarsiz_reddedilir(ist):
    c, _ = ist
    assert c.post("/api/webui/wiki/liste").status_code == 401


def test_maskele():
    assert w.maskele("TC 12345678901 ve 123456789012") == "TC 123******01 ve 123456789012"  # 12 hane dokunulmaz


def test_kaydet_md_json_indeks_ve_tc_maskesi(ist):
    c, d = ist
    r = _kaydet(c)
    assert r == {"durum": "kaydedildi", "id": "ekd-cizelgesi", "sayfa": 1, "satir": 2}
    md = (d / "ekd-cizelgesi.md").read_text(encoding="utf-8")
    assert "123******01" in md and "12345678901" not in md
    assert "12345678901" in (d / "ekd-cizelgesi.json").read_text(encoding="utf-8")  # gerçek veri json'da
    assert "ekd-cizelgesi.md" in (d / "index.md").read_text(encoding="utf-8")


def test_ayni_icerik_zaten_vardi_degisince_guncellendi(ist):
    c, _ = ist
    _kaydet(c)
    assert _kaydet(c)["durum"] == "zaten_vardi"
    yeni = dict(SAYFA, satirlar=SAYFA["satirlar"] + [["3", "Şule Ğür", "11111111111", "Biyoloji"]])
    assert _kaydet(c, sayfa=yeni)["durum"] == "guncellendi"


def test_satir_siniri(ist, monkeypatch):
    c, _ = ist
    monkeypatch.setattr(w, "AZAMI_SATIR", 1)
    assert _kaydet(c)["durum"] == "hata"


def test_ara_satir_ve_maskeli_cikti(ist):
    c, _ = ist
    _kaydet(c)
    y = c.post("/api/webui/wiki/ara", headers=B, json={"sorgu": "ayse celik"}).json()
    ilk = y["sonuclar"][0]
    assert ilk["id"] == "ekd-cizelgesi"
    satir = ilk["eslesen_satirlar"][0]["satir"]
    assert satir["Adı-Soyadı"] == "Ayşe Çelik" and satir["T.C Kimlik No"] == "123******01"
    assert c.post("/api/webui/wiki/ara", headers=B, json={"sorgu": "zzzz"}).json()["sonuclar"] == []


def test_getir_maskeli_ve_gercek(ist):
    c, _ = ist
    _kaydet(c)
    m = c.post("/api/webui/wiki/getir", headers=B, json={"id": "ekd-cizelgesi"}).json()
    assert m["kayit"]["sayfalar"][0]["satirlar"][0][2] == "123******01" and "hash" not in m["kayit"]
    g = c.post("/api/webui/wiki/getir", headers=B, json={"id": "ekd-cizelgesi", "maskele": False}).json()
    assert g["kayit"]["sayfalar"][0]["satirlar"][0][2] == "12345678901"


def test_getir_yol_gecisi_ve_olmayan(ist):
    c, _ = ist
    for kid in ("../x", "yok", "A B"):
        assert c.post("/api/webui/wiki/getir", headers=B, json={"id": kid}).json()["durum"] == "yok"


def test_pdf_tablo(ist):
    pymupdf = pytest.importorskip("pymupdf")
    c, _ = ist
    doc = pymupdf.open()
    sayfa = doc.new_page()
    x0, y0, h, g = 50, 60, 24, 100
    for i in range(3):
        for j in range(3):
            sayfa.draw_rect(pymupdf.Rect(x0 + j * g, y0 + i * h, x0 + (j + 1) * g, y0 + (i + 1) * h))
            sayfa.insert_text((x0 + j * g + 5, y0 + i * h + 16), ["Ad", "Sınıf", "No"][j] if i == 0 else f"{i}{j}")
    b64 = base64.b64encode(doc.tobytes()).decode()
    y = c.post("/api/webui/wiki/pdf-tablo", headers=B, json={"ad": "a.pdf", "icerik_b64": b64}).json()
    assert y["durum"] == "ok" and y["tablolar"][0]["satirlar"][0][0] == "Ad"
    bos = pymupdf.open()
    bos.new_page()
    y = c.post("/api/webui/wiki/pdf-tablo", headers=B, json={"ad": "b.pdf", "icerik_b64": base64.b64encode(bos.tobytes()).decode()}).json()
    assert y["durum"] == "yok"


def test_metin_sayfasi_kaydet_ara_getir_ve_bos_sayfa_reddi(ist):
    c, d = ist
    govde = {"ad": "Yazı", "kaynak": "y.pdf", "sayfalar": [{"ad": "Metin", "metin": "Birinci satır.\nAyşe Çelik TC 12345678901 görevlendirildi."}]}
    assert c.post("/api/webui/wiki/kaydet", headers=B, json=govde).json()["durum"] == "kaydedildi"
    assert "123******01" in (d / "yazi.md").read_text(encoding="utf-8")
    y = c.post("/api/webui/wiki/ara", headers=B, json={"sorgu": "ayse"}).json()["sonuclar"][0]
    assert "123******01" in y["eslesen_satirlar"][0]["satir"]["metin"]
    g = c.post("/api/webui/wiki/getir", headers=B, json={"id": "yazi", "maskele": False}).json()
    assert "12345678901" in g["kayit"]["sayfalar"][0]["metin"]
    bos = {"ad": "B", "kaynak": "", "sayfalar": [{"ad": "S", "baslik": ["A"], "satirlar": []}]}
    assert c.post("/api/webui/wiki/kaydet", headers=B, json=bos).status_code == 422


def test_metin_ucu_belge_oku_sonucunu_aktarir(ist, monkeypatch):
    c, _ = ist
    import belge_arsiv

    monkeypatch.setattr(belge_arsiv, "belge_oku", lambda i: {"durum": "ok", "metin": "m", "sayfa": 1, "ad": i.ad})
    y = c.post("/api/webui/wiki/metin", headers=B, json={"ad": "a.pdf", "icerik_b64": "AA=="}).json()
    assert y == {"durum": "ok", "metin": "m"}


def _yaz(c, ad, icerik, sabit=False):
    return c.post("/api/webui/wiki/yaz", headers=B, json={"ad": ad, "icerik": icerik, "sabit": sabit}).json()


def test_yaz_not_sayfasi_md_indeks_log(ist):
    c, d = ist
    r = _yaz(c, "Nöbet Düzeni", "Nöbet pazartesi günleri güncellenir. Bkz. [[Okul Kuralları]]")
    assert r == {"durum": "yazildi", "id": "nobet-duzeni", "eksik_baglantilar": ["okul-kurallari"]}
    assert "[[Okul Kuralları]]" in (d / "nobet-duzeni.md").read_text(encoding="utf-8")
    assert "not" in (d / "index.md").read_text(encoding="utf-8")
    assert "yazıldı | [[Nöbet Düzeni]]" in (d / "log.md").read_text(encoding="utf-8")


def test_yaz_guncelleme_eski_surumu_arsivler_ve_ayni_icerik_atlanir(ist):
    c, d = ist
    _yaz(c, "Not", "birinci")
    assert _yaz(c, "Not", "birinci")["durum"] == "zaten_vardi"
    assert _yaz(c, "Not", "ikinci")["durum"] == "guncellendi"
    gecmis = list((d / ".gecmis" / "not").glob("*.json"))
    assert len(gecmis) == 1 and "birinci" in gecmis[0].read_text(encoding="utf-8")
    assert "ikinci" in (d / "not.md").read_text(encoding="utf-8") and "birinci" not in (d / "not.md").read_text(encoding="utf-8")
    log = (d / "log.md").read_text(encoding="utf-8")
    assert log.count("yazıldı") == 1 and log.count("güncellendi") == 1


def test_yaz_dosya_sayfasinin_ustune_yazmaz_ve_ayrik_adlar(ist):
    c, _ = ist
    _kaydet(c)
    assert _yaz(c, "EKD Çizelgesi", "x")["durum"] == "hata"
    assert _yaz(c, "Index", "x")["durum"] == "hata" and _yaz(c, "Log", "x")["durum"] == "hata"
    r = c.post("/api/webui/wiki/kaydet", headers=B, json={"ad": "Log", "kaynak": "x", "sayfalar": [SAYFA]}).json()
    assert r["durum"] == "hata"
    _yaz(c, "Bir Not", "x")
    r = c.post("/api/webui/wiki/kaydet", headers=B, json={"ad": "Bir Not", "kaynak": "x", "sayfalar": [SAYFA]}).json()
    assert r["durum"] == "hata"  # not sayfasını dosya kaydı ezmez


def test_getir_baglantilar_ve_gelenler(ist):
    c, _ = ist
    _yaz(c, "Okul Kuralları", "Genel kurallar.")
    _yaz(c, "Nöbet", "Bkz. [[Okul Kuralları]] ve [[Olmayan Sayfa]]")
    n = c.post("/api/webui/wiki/getir", headers=B, json={"id": "nobet"}).json()["kayit"]
    assert {"id": "okul-kurallari", "var": True} in n["baglantilar"] and {"id": "olmayan-sayfa", "var": False} in n["baglantilar"]
    k = c.post("/api/webui/wiki/getir", headers=B, json={"id": "okul-kurallari"}).json()["kayit"]
    assert k["gelen"] == ["nobet"]


def test_sabit_sayfalar_ve_sinirlar(ist):
    c, _ = ist
    assert _yaz(c, "Uzun", "x" * 501, sabit=True)["durum"] == "hata"
    _yaz(c, "Kural 1", "Telefonlar kilitli kutuda tutulur.", sabit=True)
    _yaz(c, "Normal", "sabit değil")
    y = c.post("/api/webui/wiki/sabit", headers=B).json()
    assert [p["ad"] for p in y["sayfalar"]] == ["Kural 1"]
    for i in range(5):
        _yaz(c, f"Kural {i + 2}", "k" * 400, sabit=True)
    assert sum(len(p["metin"]) for p in c.post("/api/webui/wiki/sabit", headers=B).json()["sayfalar"]) <= w.SABIT_TOPLAM


def test_ara_not_sayfasini_bulur(ist):
    c, _ = ist
    _yaz(c, "Gezi", "Mayıs ayında Çanakkale gezisi yapılacak.")
    y = c.post("/api/webui/wiki/ara", headers=B, json={"sorgu": "canakkale"}).json()["sonuclar"][0]
    assert y["id"] == "gezi" and y["tur"] == "not"
