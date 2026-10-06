import json

from soruhavuzu import denetci, vt
from soruhavuzu.tests.conftest import ORNEK_SORU


def _agy_cikti(kararlar):
    return json.dumps(
        {"status": "SUCCESS", "response": json.dumps({"kararlar": kararlar})}
    )


def test_yanit_cozulur_bilinmeyen_id_yok_sayilir():
    c = _agy_cikti(
        [
            {"id": 1, "gecerli": True, "neden": "ok"},
            {"id": 99, "gecerli": False, "neden": "x"},
        ]
    )
    assert denetci.yaniti_coz(c, {1, 2}) == {1: (True, "ok")}


def test_markdown_icinde_json_cozulur():
    ic = (
        "```json\n"
        + json.dumps({"kararlar": [{"id": 1, "gecerli": False, "neden": "y"}]})
        + "\n```"
    )
    assert denetci.yaniti_coz(json.dumps({"response": ic}), {1}) == {1: (False, "y")}


def test_bozuk_cikti_bos_doner():
    assert denetci.yaniti_coz("agy hata verdi", {1}) == {}


def test_paket_denetle_kararlari_yazar_eksik_olan_bekler(conn):
    bid = vt.birim_ekle(conn, "kitap", "k:1", "matematik", 12, "E", "metin")
    a = vt.soru_ekle(conn, bid, ORNEK_SORU)
    b = vt.soru_ekle(conn, bid, {**ORNEK_SORU, "soru": "log3(9) kaçtır?"})
    istemler = []

    def sahte(istem, zaman_asimi_sn=900):
        istemler.append(istem)
        return _agy_cikti([{"id": a, "gecerli": False, "neden": "cevap yanlış"}])

    assert denetci.paket_denetle(conn, 100, cagir=sahte) == 1
    assert "log3(9)" in istemler[0] and "metin" in istemler[0]
    assert [s["id"] for s in vt.denetlenecekler(conn, 100)] == [b]


def test_structured_output_oncelikli():
    c = json.dumps(
        {
            "response": "```json\n{bozuk",
            "structured_output": {"kararlar": [{"id": 3, "gecerli": False, "neden": "z"}]},
        }
    )
    assert denetci.yaniti_coz(c, {3}) == {3: (False, "z")}


def test_cift_yazilmis_response_ilk_nesne_alinir():
    k = json.dumps({"kararlar": [{"id": 1, "gecerli": True, "neden": "ok"}]})
    c = json.dumps({"response": "```json\n" + k + "\n```" + k})
    assert denetci.yaniti_coz(c, {1}) == {1: (True, "ok")}


def test_istem_ders_disi_kurali_icerir():
    assert "ders dışı" in denetci.istem([])
