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
