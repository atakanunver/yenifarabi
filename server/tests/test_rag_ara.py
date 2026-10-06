"""RagMotoru.ara() — Open WebUI arama yolu: yalnızca vektör araması, LLM ve
reranker YOK (2026-10-03 kararı C). Tahta yolu (`sorgula`) test_rag.py'de."""

import pytest
import rag
from conftest import SahteBaglanti, SahteEmbed, SahteReranker


def _m(id_, sayfa, metin, kaynak_id, mesafe=0.1):
    return (id_, sayfa, metin, mesafe, kaynak_id)


def _t(id_, sayfa, baslik, ozet, kitap_id, mesafe=0.1):
    return (id_, sayfa, baslik, ozet, mesafe, kitap_id)


@pytest.fixture
def motor():
    return rag.RagMotoru(SahteEmbed(), None)


@pytest.fixture(autouse=True)
def _llm_yasak(monkeypatch):
    def _patla(*a, **k):
        raise AssertionError("ara() LLM'e GİTMEMELİ")
    monkeypatch.setattr(rag.RagMotoru, "_llm_cevap", _patla)


def test_ok_parcalar_kaynak_id_sayfa_ve_benzerlik_skoru(motor):
    conn = SahteBaglanti([_m(1, 84, "Mol, madde miktarı birimidir.", 9, mesafe=0.2)])
    s = motor.ara(conn, "egitim", [9, 20], "mol nedir")
    assert s["durum"] == "ok" and s["rerank_ms"] is None
    assert s["parcalar"][0] == {"kaynak_id": 9, "sayfa": 84, "metin": "Mol, madde miktarı birimidir.",
                                "skor": 0.8, "tur": "metin"}
    assert s["en_iyi_skor"] == 0.8


def test_reranker_HIC_kullanilmaz():
    m = rag.RagMotoru(SahteEmbed(), SahteReranker(patlat=AssertionError("rerank çağrıldı")))
    assert m.ara(SahteBaglanti([_m(1, 1, "x", 9)]), "egitim", [9], "s")["durum"] == "ok"


def test_kaynak_idler_ANY_ve_LIMIT_TOP_N(motor):
    conn = SahteBaglanti([_m(1, 84, "x", 9)])
    motor.ara(conn, "egitim", [9, 20], "soru")
    sql, params = next(q for q in conn.sorgular if "FROM chunk_egitim" in q[0])
    assert "ANY(%s)" in sql and params[1] == [9, 20] and params[2] == rag.TOP_N


def test_en_fazla_TOP_N_parca_mesafe_sirasinda(motor):
    satirlar = [_m(i, i, f"m{i}", 9, mesafe=0.1 + i / 100) for i in range(10)]
    s = motor.ara(SahteBaglanti(list(reversed(satirlar))), "egitim", [9], "s")
    assert [p["sayfa"] for p in s["parcalar"]] == [0, 1, 2, 3]


def test_tablo_daha_yakinsa_once_gelir(motor):
    conn = SahteBaglanti([_m(1, 5, "metin", 9, mesafe=0.3)], [_t(7, 6, "Tablo A", "a — 1", 9, mesafe=0.1)])
    s = motor.ara(conn, "egitim", [9], "s")
    assert s["parcalar"][0]["tur"] == "tablo" and s["parcalar"][0]["metin"].startswith("Tablo: Tablo A.")
    assert s["parcalar"][1]["tur"] == "metin"


def test_tablo_sorgusu_patlarsa_metin_yolu_etkilenmez(motor):
    conn = SahteBaglanti([_m(1, 5, "metin", 9)], tablo_patlat=RuntimeError("tablo yok"))
    s = motor.ara(conn, "egitim", [9], "s")
    assert s["durum"] == "ok" and conn.rollback_sayisi == 1


def test_esik_altinda_zayif_ve_bos(motor):
    s = motor.ara(SahteBaglanti([_m(1, 1, "x", 9, mesafe=0.5)]), "egitim", [9], "s")
    assert s["durum"] == "zayif" and s["parcalar"] == [] and s["en_iyi_skor"] == 0.5


def test_esigin_tam_ustunde_ok(motor):
    s = motor.ara(SahteBaglanti([_m(1, 1, "x", 9, mesafe=1 - rag.ESIK_BENZERLIK)]), "egitim", [9], "s")
    assert s["durum"] == "ok"


def test_aday_yoksa_zayif(motor):
    assert motor.ara(SahteBaglanti([]), "egitim", [9], "s")["durum"] == "zayif"


def test_bos_kaynak_listesinde_DB_ye_gidilmez(motor):
    conn = SahteBaglanti([_m(1, 1, "x", 9)])
    s = motor.ara(conn, "egitim", [], "s")
    assert s["durum"] == "zayif" and conn.sorgular == []


def test_idari_kaynakta_chunk_idari_sorulur_tabloya_sorulmaz(motor):
    conn = SahteBaglanti(idari_satirlari=[_m(3, 12, "Madde 5 ...", 2)])
    s = motor.ara(conn, "idari", [2], "devamsızlık")
    assert s["durum"] == "ok" and s["parcalar"][0]["kaynak_id"] == 2
    assert not any("chunk_tablo" in q[0] or "chunk_egitim" in q[0] for q in conn.sorgular)


def test_embedding_patlarsa_hata():
    m = rag.RagMotoru(SahteEmbed(patlat=RuntimeError("x")), None)
    s = m.ara(SahteBaglanti([_m(1, 1, "x", 9)]), "egitim", [9], "s")
    assert s["durum"] == "hata" and s["parcalar"] == [] and "RuntimeError" in s["hata"]


def test_ana_sorgu_patlarsa_hata():
    conn = SahteBaglanti(patlat_sql="FROM chunk_egitim", patlat=RuntimeError("db"))
    assert rag.RagMotoru(SahteEmbed(), None).ara(conn, "egitim", [9], "s")["durum"] == "hata"


def test_ara_HICBIR_sey_yazmaz(motor):
    conn = SahteBaglanti([_m(1, 1, "x", 9)])
    motor.ara(conn, "egitim", [9], "s")
    assert conn.metrik_kayitlari() == [] and conn.soru_log_kayitlari() == []


def test_bilinmeyen_kaynak_ValueError(motor):
    with pytest.raises(ValueError):
        motor.ara(SahteBaglanti(), "kitapsiz", [1], "s")


def test_hibrit_arama_anahtar_kelime_onceliklendirir(motor):
    conn = SahteBaglanti([_m(1, 1, "örnek metin", 9)])
    # k=15 vererek hibrit arama dalını tetikle
    soru = "657 sayılı kanun madde 104 babalık izni"
    motor.ara(conn, "egitim", [9], soru, k=15)
    ilike_sorgulari = [q for q in conn.sorgular if "ILIKE" in q[0]]
    assert len(ilike_sorgulari) > 0
    aranan_terimler = [q[1][2] for q in ilike_sorgulari]
    # Rakamlar ('657', '104') ve özgül kelimeler ('babalık') ILIKE sorgularına girmeli
    assert "%657%" in aranan_terimler or "%104%" in aranan_terimler
    assert "%babalık%" in aranan_terimler
    # Durak kelimeler ('sayılı', 'kanun', 'madde') tek başına aranmamalı
    assert "%sayılı%" not in aranan_terimler
    assert "%kanun%" not in aranan_terimler

