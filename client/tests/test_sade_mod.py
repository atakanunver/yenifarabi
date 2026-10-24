"""core.tahta.sade_mod: varsayılan AÇIK; yalnızca açık bir 'false' ders modlarını geri açar (2026-10-24)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import tahta


def _yaz(tmp_path, monkeypatch, icerik):
    yol = tmp_path / "api_keys.json"
    yol.write_text(icerik if isinstance(icerik, str) else json.dumps(icerik), encoding="utf-8")
    monkeypatch.setattr(tahta, "CONFIG_PATH", yol)


def test_dosya_yoksa_veya_bozuksa_sade(tmp_path, monkeypatch):
    monkeypatch.setattr(tahta, "CONFIG_PATH", tmp_path / "yok.json")
    assert tahta.sade_mod() is True
    _yaz(tmp_path, monkeypatch, "{bozuk")
    assert tahta.sade_mod() is True


def test_anahtar_yoksa_sade(tmp_path, monkeypatch):
    _yaz(tmp_path, monkeypatch, {"derslik": "9-A"})
    assert tahta.sade_mod() is True


@pytest.mark.parametrize("deger", [True, "true", "evet", 1])
def test_acik_degerler_sade(tmp_path, monkeypatch, deger):
    _yaz(tmp_path, monkeypatch, {"sade_mod": deger})
    assert tahta.sade_mod() is True


@pytest.mark.parametrize("deger", [False, "false", "False", "0", "hayır", "kapalı", 0])
def test_yalniz_acik_kapatma_ders_modlarini_acar(tmp_path, monkeypatch, deger):
    _yaz(tmp_path, monkeypatch, {"sade_mod": deger})
    assert tahta.sade_mod() is False
