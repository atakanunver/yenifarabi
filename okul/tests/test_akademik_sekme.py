"""Sınavlar akademik bölümü: Denemeler / Takvim / Kazanımlar alt sekme şeridi ve alt menüde etkin 'Sınavlar'."""

import json
import re

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


@pytest.fixture
def deneme_id(conn, ornek):
    did = conn.execute("INSERT INTO deneme (ad, yayinda, olusturma) VALUES ('Aktif', 1, 'x')").lastrowid
    conn.execute(
        "INSERT INTO deneme_ogrenci (deneme_id, okul_no, veri, analiz) VALUES (?, 101, ?, 'a')",
        (did, json.dumps({"toplam_net": 40.0, "dersler": {"Türkçe": 20.0}, "kazanimlar": []})),
    )
    conn.commit()
    return did


def _giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303


def _blok(t, etiket):
    b = t[t.index(f'<nav class="{etiket}"'):]
    return b[: b.index("</nav>")]


def _aktifler(blok):
    return re.findall(r'<a href="[^"]+" class="aktif"[^>]*>(?:.*?</svg>)?([^<]+)</a>', blok, re.DOTALL)


def _kontrol(t, yol, etkin_sekme, ek):
    sekme = _blok(t, "akademik-sekme")
    for ad in ("Denemeler", "Takvim", "Kazanımlar"):
        assert ad in sekme, yol
    assert _aktifler(sekme) == [etkin_sekme], yol
    for h in ("/deneme", "/sinavlar"):
        assert f'href="{ek[0]}{h}{ek[1]}"' in sekme, yol
    assert f'href="{ek[0]}{ek[2]}{ek[1]}"' in sekme, yol
    assert _aktifler(_blok(t, "sekmeler")) == ["Sınavlar"], yol


def test_ogrenci_uc_sayfada_serit_ve_sinavlar_etkin(istemci, ornek, deneme_id):
    _giris(istemci, "101", "ali-sifre")
    for yol, etkin in (
        ("/ogrenci/deneme", "Denemeler"),
        (f"/ogrenci/deneme/{deneme_id}", "Denemeler"),
        ("/ogrenci/sinavlar", "Takvim"),
        ("/ogrenci/kazanimlar", "Kazanımlar"),
    ):
        r = istemci.get(yol)
        assert r.status_code == 200, yol
        _kontrol(r.text, yol, etkin, ("/ogrenci", "", "/kazanimlar"))


def test_diger_ogrenci_sayfasinda_serit_yok_sinavlar_etkin_degil(istemci, ornek):
    _giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci/odevler").text
    assert 'class="akademik-sekme"' not in t
    assert "Sınavlar" not in _aktifler(_blok(t, "sekmeler"))


def test_veli_serit_ogr_parametresini_korur(istemci, ornek, deneme_id, monkeypatch):
    from test_web import _veli_girisi

    _veli_girisi(istemci, monkeypatch)
    ogr = ornek["ogr1"]
    for yol, etkin in (
        (f"/veli/deneme?ogr={ogr}", "Denemeler"),
        (f"/veli/deneme/{deneme_id}?ogr={ogr}", "Denemeler"),
        (f"/veli/sinavlar?ogr={ogr}", "Takvim"),
        (f"/veli/kazanim?ogr={ogr}", "Kazanımlar"),
        ("/veli/sinavlar", "Takvim"),
    ):
        r = istemci.get(yol)
        assert r.status_code == 200, yol
        _kontrol(r.text, yol, etkin, ("/veli", f"?ogr={ogr}", "/kazanim"))


def test_veli_baska_cocuk_404_degismedi(istemci, ornek, monkeypatch):
    from test_web import _veli_girisi

    _veli_girisi(istemci, monkeypatch)
    for yol in ("/veli/deneme", "/veli/sinavlar", "/veli/kazanim"):
        assert istemci.get(f"{yol}?ogr={ornek['ogr2']}").status_code == 404, yol
