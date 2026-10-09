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


def test_istem_tek_arguman_sinirini_asmaz_kalan_sonraki_pakete(conn):
    # 2026-10-07 23:01: 100 soruluk paketin istemi (her biri ayrı ~2500 kr kaynak)
    # Linux'un tek argüman sınırını (131072 bayt) aştı → OSError E2BIG, servis failed.
    idler = []
    for i in range(80):
        bid = vt.birim_ekle(conn, "kitap", f"k:{i}", "matematik", 12, "E", "çğüşöı" * 420)
        idler.append(vt.soru_ekle(conn, bid, {**ORNEK_SORU, "soru": f"soru {i}?"}))
    istemler = []

    def sahte(istem, zaman_asimi_sn=900):
        istemler.append(istem)
        return _agy_cikti([])

    denetci.paket_denetle(conn, 100, cagir=sahte)
    assert len(istemler) == 1
    assert len(istemler[0].encode()) <= denetci.ISTEM_AZAMI_BAYT
    assert "soru 0?" in istemler[0] and "soru 79?" not in istemler[0]


def test_istem_kazanim_satiri_ve_kurali(conn):
    k = vt.kazanim_upsert(conn, {"sinif": 12, "ders": "matematik", "hafta": 1, "kod": "12.1", "metin": "12.1. Logaritma"})
    bid = vt.birim_ekle(conn, "kitap", "k:1", "matematik", 12, "E", "metin")
    vt.soru_ekle(conn, bid, ORNEK_SORU, kazanim_id=k, kazanim_kaynak="uretim")
    vt.soru_ekle(conn, bid, {**ORNEK_SORU, "soru": "eski?"})
    paket = vt.denetlenecekler(conn, 10)
    metin = denetci.istem(paket)
    assert "Kazanım: 12.1. Logaritma" in metin and "kazanım dışı" in metin
    assert metin.count("Kazanım:") == 1
