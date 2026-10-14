"""panel_api.py testleri."""

import importlib.util
import json
import stat
from pathlib import Path

import pytest
from fastapi import HTTPException

import db
import panel_api
import veli_mesaj


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_YOLU", tmp_path / "t.db")
    db.semayi_kur()
    ayar = tmp_path / "panel.json"
    ayar.write_text(json.dumps({"anahtar": "test-anahtar"}))
    monkeypatch.setattr(panel_api, "PANEL_AYAR_YOLU", ayar)
    c = db.baglanti()
    veli_mesaj.mesajlari_kaydet(
        c,
        [
            {"Index": "1", "Phone": "05550001111", "Content": "selam", "Date": "2026-10-14 09:00:00"},
            {"Index": "2", "Phone": "05550002222", "Content": "çıkarın beni", "Date": "2026-10-14 10:00:00"},
        ],
        set(),
    )
    c.close()
    return ayar


def test_anahtar_zorunlu(ortam):
    ayar = ortam
    dogrula = panel_api.anahtar_dogrula
    dogrula("test-anahtar")  # geçer
    for kotu in (None, "", "yanlis"):
        with pytest.raises(HTTPException) as e:
            dogrula(kotu)
        assert e.value.status_code == 401
    ayar.write_text(json.dumps({"anahtar": ""}))
    with pytest.raises(HTTPException) as e:
        dogrula("test-anahtar")
    assert e.value.status_code == 503
    ayar.unlink()
    with pytest.raises(HTTPException) as e:
        dogrula("test-anahtar")
    assert e.value.status_code == 503


def test_uclar_anahtarsiz_korumali():
    # her uç Depends(anahtar_dogrula) taşımalı
    for r in panel_api.router.routes:
        assert any(d.call is panel_api.anahtar_dogrula for d in r.dependant.dependencies), r.path


def test_liste_yeni_eskiye_ve_telefon_maskeli(ortam):
    r = panel_api.liste()["mesajlar"]
    assert [m["metin"] for m in r] == ["çıkarın beni", "selam"]
    assert r[0]["telefon"] == "*******2222" and "05550002222" not in json.dumps(r)
    assert r[0]["cikis_talebi"] == 1


def test_sayac_okundu_sil(ortam):
    assert panel_api.sayac() == {"okunmamis": 2, "cikis_talebi_okunmamis": 1}
    mid = panel_api.liste()["mesajlar"][0]["id"]
    assert panel_api.okundu(mid) == {"ok": True}
    assert panel_api.sayac() == {"okunmamis": 1, "cikis_talebi_okunmamis": 0}
    assert len(panel_api.liste(okunmamis=1)["mesajlar"]) == 1
    assert panel_api.sil(mid) == {"ok": True}
    for fn in (panel_api.sil, panel_api.okundu):
        with pytest.raises(HTTPException) as e:
            fn(mid)
        assert e.value.status_code == 404


def _betik():
    yol = Path(__file__).parent / "scripts" / "panel_anahtari_uret.py"
    spec = importlib.util.spec_from_file_location("panel_anahtari_uret", yol)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_anahtar_uretici(tmp_path, capsys):
    m = _betik()
    panel, dash = tmp_path / "a" / "panel.json", tmp_path / "d" / "sms_panel.json"
    m.calistir(panel, dash, False)
    k = json.loads(panel.read_text())["anahtar"]
    assert len(k) >= 32 and json.loads(dash.read_text())["anahtar"] == k
    assert stat.S_IMODE(panel.stat().st_mode) == 0o600 and stat.S_IMODE(dash.stat().st_mode) == 0o600
    cikti = "\n".join(m.calistir(panel, dash, False))  # ezmez
    assert json.loads(panel.read_text())["anahtar"] == k and k not in cikti
    m.calistir(panel, dash, True)
    yeni = json.loads(panel.read_text())["anahtar"]
    assert yeni != k and json.loads(dash.read_text())["anahtar"] == yeni


# --- spam engeli ---

def _idare(monkeypatch, numaralar=("05550009999",)):
    import arac_api

    monkeypatch.setattr(arac_api, "yonetim_alicilari", lambda: [("Idare", n) for n in numaralar])


def _ekle(*mesajlar, idare=()):
    c = db.baglanti()
    veli_mesaj.mesajlari_kaydet(
        c,
        [{"Index": str(i), "Phone": t, "Content": m, "Date": f"2026-10-14 11:0{i}:00"} for i, (t, m) in enumerate(mesajlar, 3)],
        set(idare),
    )
    c.close()


def test_sistem_numarasi_listede_ve_sayacta_yok_spam_ucunda(ortam):
    _ekle(("REKLAMX", "indirim"), ("2020", "kampanya"))
    assert {m["metin"] for m in panel_api.liste()["mesajlar"]} == {"selam", "çıkarın beni"}
    assert panel_api.sayac() == {"okunmamis": 2, "cikis_talebi_okunmamis": 1}
    sp = panel_api.liste(spam=1)["mesajlar"]
    assert {m["metin"] for m in sp} == {"indirim", "kampanya"}
    assert all(m["spam_neden"] == "sistem numarası" for m in sp)
    assert panel_api.liste()["mesajlar"][0]["spam_neden"] is None


def test_engelle_ve_engeli_kaldir(ortam, monkeypatch):
    _idare(monkeypatch)
    _ekle(("05550003333", "birinci"), ("05550003333", "ikinci"))
    mid = next(m["id"] for m in panel_api.liste()["mesajlar"] if m["metin"] == "birinci")
    assert panel_api.engelle(mid, panel_api.EngelGovde(neden="x" * 200)) == {"ok": True, "etkilenen": 2}
    c = db.baglanti()
    assert len(c.execute("SELECT * FROM engelli_gonderenler").fetchall()) == 1
    assert len(c.execute("SELECT neden FROM engelli_gonderenler").fetchone()["neden"]) == 80
    c.close()
    assert panel_api.sayac()["okunmamis"] == 2
    sp = panel_api.liste(spam=1)["mesajlar"]
    assert {m["spam_neden"] for m in sp} == {"engelli"} and len(sp) == 2
    assert "05550003333" not in json.dumps(sp)
    # engel sonrası yeni mesaj da spam
    _ekle(("05550003333", "ucuncu"))
    assert len(panel_api.liste(spam=1)["mesajlar"]) == 3
    # kaldır: numaranın tüm engelli satırları geri, okunmamış
    assert panel_api.engeli_kaldir(mid) == {"ok": True, "etkilenen": 3}
    assert panel_api.liste(spam=1)["mesajlar"] == [] and panel_api.sayac()["okunmamis"] == 5
    with pytest.raises(HTTPException) as e:
        panel_api.engeli_kaldir(mid)
    assert e.value.status_code == 404


def test_engelle_idare_409_ve_404(ortam, monkeypatch):
    _idare(monkeypatch)
    _ekle(("05550009999", "idare mesajı"))
    mid = next(m["id"] for m in panel_api.liste()["mesajlar"] if m["metin"] == "idare mesajı")
    with pytest.raises(HTTPException) as e:
        panel_api.engelle(mid)
    assert e.value.status_code == 409
    with pytest.raises(HTTPException) as e:
        panel_api.engelle(99999)
    assert e.value.status_code == 404


def test_sistem_numarasi_engeli_kaldir_yalniz_o_mesaj(ortam, monkeypatch):
    _ekle(("REKLAMX", "a"), ("REKLAMX", "b"))
    sp = panel_api.liste(spam=1)["mesajlar"]
    assert panel_api.engeli_kaldir(sp[0]["id"]) == {"ok": True, "etkilenen": 1}
    assert len(panel_api.liste(spam=1)["mesajlar"]) == 1
    assert panel_api.liste(okunmamis=1)["mesajlar"][0]["id"] == sp[0]["id"]
