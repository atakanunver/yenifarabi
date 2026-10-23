import json
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent


def _modlar():
    return json.loads((KOK / "modlar.json").read_text(encoding="utf-8"))


def test_tek_mod_atos():
    # 2026-10-23 (kullanıcı kararı): tek model; branş/derin/müdür yrd./yönetim modları kaldırıldı.
    assert [x["id"] for x in _modlar()] == ["farabi"]


def test_atos_alanlari():
    (x,) = _modlar()
    assert set(x) == {"id", "ad", "aciklama", "kapsam", "think", "gruplar", "ek", "hafiza"}
    assert x["ad"] == "Atos" and x["kapsam"] == "hepsi" and x["gruplar"] == ["İdare"]
    assert x["hafiza"] is True and x["think"] is False
    assert (KOK / "promptlar" / x["ek"]).is_file()


def test_prompt_boyutu_sinirli():
    cekirdek = (KOK / "promptlar" / "cekirdek.md").read_text(encoding="utf-8")
    assert len(cekirdek) < 5000          # ~1.300 token
    for x in _modlar():
        ek = (KOK / "promptlar" / x["ek"]).read_text(encoding="utf-8")
        assert len(ek) < 1500 and "wiki_kaydet" in ek
