import json
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
KAPSAMLAR = {"genel", "kimya", "fizik", "biyoloji", "matematik", "edebiyat", "ingilizce",
             "felsefe", "din", "tarih", "cografya", "idari", None}


def _modlar():
    return json.loads((KOK / "modlar.json").read_text(encoding="utf-8"))


def test_14_mod_benzersiz_id():
    m = _modlar()
    assert len(m) == 14 and len({x["id"] for x in m}) == 14


def test_alanlar_ve_ek_dosyalari_var():
    for x in _modlar():
        assert set(x) == {"id", "ad", "aciklama", "kapsam", "think", "gruplar", "ek"}
        assert x["kapsam"] in KAPSAMLAR
        assert (KOK / "promptlar" / x["ek"]).is_file()


def test_mudur_yrd_yalnizca_idare():
    m = {x["id"]: x for x in _modlar()}
    assert m["farabi-mudur-yrd"]["gruplar"] == ["İdare"]
    assert all(x["gruplar"] == ["Öğretmenler", "İdare"] for i, x in m.items() if i != "farabi-mudur-yrd")


def test_yalnizca_derin_dusunur():
    assert [x["id"] for x in _modlar() if x["think"]] == ["farabi-derin"]


def test_prompt_boyutu_sinirli():
    cekirdek = (KOK / "promptlar" / "cekirdek.md").read_text(encoding="utf-8")
    assert len(cekirdek) < 5000          # ~1.300 token
    for x in _modlar():
        assert len((KOK / "promptlar" / x["ek"]).read_text(encoding="utf-8")) < 1500
