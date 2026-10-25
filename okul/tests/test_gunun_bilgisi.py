"""Günün bilgisi kartı: tarih anahtarı, sıralama, eksik/bozuk dosya, üç ana sayfada en altta görünme."""

import json
from datetime import datetime
from pathlib import Path

import auth
import gunun_bilgisi
from fastapi.testclient import TestClient


def test_bugun_ve_eksik_kayit(tmp_path, saat):
    yol = tmp_path / "g.json"
    yol.write_text(json.dumps({"gunler": {"10-12": ["Deneme Günü"]}, "tarihte": {"10-12": [{"yil": 1950, "olay": "B"}, {"yil": 1900, "olay": "A"}]}}), encoding="utf-8")
    g = gunun_bilgisi.bugun(yol)
    assert g["gunler"] == ["Deneme Günü"] and [t["yil"] for t in g["tarihte"]] == [1900, 1950]
    saat["an"] = datetime(2026, 10, 13, 9, 0)  # noqa: DTZ001
    assert gunun_bilgisi.bugun(yol) is None
    yol.write_text("{bozuk", encoding="utf-8")
    assert gunun_bilgisi.bugun(yol) is None
    assert gunun_bilgisi.bugun(tmp_path / "yok.json") is None


def test_gercek_dosya_gecerli():
    veri = json.loads((Path(__file__).resolve().parent.parent / "config" / "gunun_bilgisi.json").read_text(encoding="utf-8"))
    for anahtar in list(veri["gunler"]) + list(veri["tarihte"]):
        datetime.strptime(f"2024-{anahtar}", "%Y-%m-%d")
    assert all(isinstance(t["yil"], int) and t["olay"] for l in veri["tarihte"].values() for t in l)


def test_uc_ana_sayfada_en_altta(conn, ornek, saat, monkeypatch, tmp_path):
    yol = tmp_path / "g.json"
    yol.write_text(json.dumps({"gunler": {"10-12": ["Deneme Dünya Günü"]}, "tarihte": {}}), encoding="utf-8")
    monkeypatch.setattr(gunun_bilgisi, "YOL", yol)
    from app import app

    for rol, yol_ in (("ogr1_k", "/ogrenci"), ("ogretmen", "/ogretmen"), ("veli1", "/veli")):
        with TestClient(app) as c:
            c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, ornek[rol]))
            s = c.get(yol_).text
            assert "Deneme Dünya Günü" in s
            assert s.index("Deneme Dünya Günü") > s.rindex('class="kart', 0, s.index("gunun-bilgisi")) - 1
            assert s.rfind("<section", s.index("gunun-bilgisi")) == -1  # kendisinden sonra başka kart yok
