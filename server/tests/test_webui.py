"""/api/webui/ara — Open WebUI arama ucu. main.app KURULMAZ (lifespan
model yükler); yalnızca webui.router bağlı küçük bir app (test_proxy.py deseni)."""

import auth
import db
import pytest
import rag
import webui
from conftest import SahteBaglanti, SahteEmbed
from fastapi import FastAPI
from fastapi.testclient import TestClient

ANAHTAR = "webui-gizli"
KITAPLAR = [  # (id, sinif, ders, dosya_yolu)
    (20, 9, "Kimya", "/k/kimya_9.pdf"),
    (9, 10, "Kimya", "/k/kimya-10.pdf"),
    (27, 11, "Kimya", "/k/kimya-11.pdf"),
]


def _m(id_, sayfa, metin, kaynak_id, mesafe=0.1):
    return (id_, sayfa, metin, mesafe, kaynak_id)


@pytest.fixture
def kur(monkeypatch):
    """(istemci, baglanti) döndüren fabrika."""
    def _kur(conn: SahteBaglanti, motor=True):
        monkeypatch.setattr(auth, "webui_anahtari", lambda: ANAHTAR)
        monkeypatch.setattr(auth, "_board_keys", lambda: {"9-A": "tahta-anahtari"})

        class _Ctx:
            def __enter__(self):
                return conn

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(db, "baglanti", _Ctx)
        monkeypatch.setattr(webui, "MOTOR", rag.RagMotoru(SahteEmbed(), None) if motor else None)
        app = FastAPI()
        app.include_router(webui.router)
        return TestClient(app), conn
    return _kur


def _post(ist, govde, anahtar=ANAHTAR):
    h = {"X-Farabi-WebUI-Key": anahtar} if anahtar else {}
    return ist.post("/api/webui/ara", json=govde, headers=h)


class TestAuth:
    def test_basliksiz_401(self, kur):
        ist, _ = kur(SahteBaglanti(kitap_satirlari=KITAPLAR))
        assert _post(ist, {"kapsam": "kimya", "soru": "mol"}, anahtar=None).status_code == 401

    def test_tahta_anahtari_REDDEDILIR(self, kur):
        ist, _ = kur(SahteBaglanti(kitap_satirlari=KITAPLAR))
        assert _post(ist, {"kapsam": "kimya", "soru": "mol"}, anahtar="tahta-anahtari").status_code == 401

    def test_anahtar_tanimsizsa_herkes_401(self, kur, monkeypatch):
        ist, _ = kur(SahteBaglanti(kitap_satirlari=KITAPLAR))
        monkeypatch.setattr(auth, "webui_anahtari", lambda: None)
        assert _post(ist, {"kapsam": "kimya", "soru": "mol"}).status_code == 401


class TestArama:
    def test_ok_etiketli_parca(self, kur):
        ist, _ = kur(SahteBaglanti([_m(1, 84, "Mol ...", 9)], kitap_satirlari=KITAPLAR))
        y = _post(ist, {"kapsam": "kimya", "soru": "mol nedir"}).json()
        assert y["durum"] == "ok"
        assert y["parcalar"][0]["kaynak"] == "Kimya 10, s. 84"
        assert y["parcalar"][0]["metin"] == "Mol ..."

    def test_bilinmeyen_kapsam_400(self, kur):
        ist, _ = kur(SahteBaglanti(kitap_satirlari=KITAPLAR))
        assert _post(ist, {"kapsam": "astroloji", "soru": "x"}).status_code == 400

    def test_sinif_ifadesi_kitabi_daraltir(self, kur):
        ist, conn = kur(SahteBaglanti([_m(1, 3, "x", 9)], kitap_satirlari=KITAPLAR))
        _post(ist, {"kapsam": "kimya", "soru": "10. sınıf mol konusu için etkinlik"})
        _, params = next(q for q in conn.sorgular if "FROM chunk_egitim" in q[0])
        assert [9] in params

    def test_kitabi_olmayan_sinif_daraltmaz(self, kur):
        ist, conn = kur(SahteBaglanti([_m(1, 3, "x", 9)], kitap_satirlari=KITAPLAR))
        _post(ist, {"kapsam": "kimya", "soru": "12. sınıf mol"})
        _, params = next(q for q in conn.sorgular if "FROM chunk_egitim" in q[0])
        assert sorted(params[1]) == [9, 20, 27]

    def test_zayif_bos_parca(self, kur):
        ist, _ = kur(SahteBaglanti([_m(1, 3, "x", 9, mesafe=0.7)], kitap_satirlari=KITAPLAR))
        y = _post(ist, {"kapsam": "kimya", "soru": "x"}).json()
        assert y["durum"] == "zayif" and y["parcalar"] == []

    def test_kapsamda_kitap_yoksa_zayif(self, kur):
        ist, conn = kur(SahteBaglanti([_m(1, 3, "x", 9)], kitap_satirlari=[]))
        y = _post(ist, {"kapsam": "kimya", "soru": "x"}).json()
        assert y["durum"] == "zayif"
        assert not any("FROM chunk_egitim" in q[0] for q in conn.sorgular)

    def test_rag_kapaliysa_hata(self, kur):
        ist, _ = kur(SahteBaglanti(kitap_satirlari=KITAPLAR), motor=False)
        assert _post(ist, {"kapsam": "kimya", "soru": "x"}).json()["durum"] == "hata"

    def test_db_hatasinda_hata_ve_rollback(self, kur):
        conn = SahteBaglanti(kitap_satirlari=KITAPLAR, patlat_sql="FROM kitap",
                             patlat=RuntimeError("db"))
        ist, _ = kur(conn)
        r = _post(ist, {"kapsam": "kimya", "soru": "x"})
        assert r.status_code == 200 and r.json()["durum"] == "hata"
        assert conn.rollback_sayisi >= 1

    def test_uzun_soru_2000_e_kirpilir(self, kur):
        ist, _ = kur(SahteBaglanti([_m(1, 3, "x", 9)], kitap_satirlari=KITAPLAR))
        _post(ist, {"kapsam": "kimya", "soru": "a" * 9000})
        assert len(webui.MOTOR.embed_model.son_soru) == 2000

    def test_cilt_etiketi(self, kur):
        kit = [(11, 9, "Matematik", "/k/matematik_9.pdf"), (12, 9, "Matematik", "/k/matematik_9_2.pdf")]
        ist, _ = kur(SahteBaglanti([_m(1, 5, "x", 12)], kitap_satirlari=kit))
        y = _post(ist, {"kapsam": "matematik", "soru": "x"}).json()
        assert y["parcalar"][0]["kaynak"] == "Matematik 9 (2. cilt), s. 5"

    def test_idari_belge_etiketi(self, kur):
        conn = SahteBaglanti(idari_satirlari=[_m(1, 12, "Madde", 2)],
                             idari_belge_satirlari=[(2, "Ortaöğretim Kurumları Yönetmeliği")])
        ist, _ = kur(conn)
        y = _post(ist, {"kapsam": "idari", "soru": "devamsızlık"}).json()
        assert y["parcalar"][0]["kaynak"] == "Ortaöğretim Kurumları Yönetmeliği, s. 12"


class TestLoglama:
    def test_metrik_webui_ok_yazilir_soru_log_yazilmaz(self, kur):
        ist, conn = kur(SahteBaglanti([_m(1, 84, "x", 9)], kitap_satirlari=KITAPLAR))
        _post(ist, {"kapsam": "kimya", "soru": "mol"})
        (_sql, params), = conn.metrik_kayitlari()
        assert "webui_ok" in params and params[0] is None
        assert conn.soru_log_kayitlari() == []

    def test_ara_ic_hata_rollback_ve_webui_hata_metrigi(self, kur):
        conn = SahteBaglanti(kitap_satirlari=KITAPLAR, patlat_sql="FROM chunk_egitim",
                             patlat=RuntimeError("db"))
        ist, _ = kur(conn)
        y = _post(ist, {"kapsam": "kimya", "soru": "mol"}).json()
        assert y["durum"] == "hata"
        assert conn.rollback_sayisi >= 1
        (_sql, params), = conn.metrik_kayitlari()
        assert "webui_hata" in params


def test_baglanti_alinamazsa_200_hata_metriksiz(kur, monkeypatch):
    conn = SahteBaglanti(kitap_satirlari=KITAPLAR)
    ist, _ = kur(conn)

    def _patla():
        raise RuntimeError("havuz tükendi")
    monkeypatch.setattr(db, "baglanti", _patla)
    r = _post(ist, {"kapsam": "kimya", "soru": "mol"})
    assert r.status_code == 200
    y = r.json()
    assert y["durum"] == "hata" and y["parcalar"] == []
    assert conn.metrik_kayitlari() == []


@pytest.mark.parametrize("soru,beklenen", [
    ("10. sınıf mol", 10), ("10.sınıf", 10), ("9 sınıf", 9), ("11-A için plan", 11),
    ("12. SINIF", 12), ("mol nedir", None), ("2010 yılında", None), ("110. sayfa", None),
])
def test_sinif_cikar(soru, beklenen):
    assert webui.sinif_cikar(soru) == beklenen


class TestGenelKitapMevzuat:
    """2026-10-05: "hepsi" kapsamı (yalnızca İdare modu) hem kitaplarda hem mevzuatta arar."""

    def _conn(self, metin=(), idari=()):
        return SahteBaglanti(list(metin), kitap_satirlari=KITAPLAR, idari_satirlari=list(idari),
                             idari_belge_satirlari=[(2, "Ortaöğretim Kurumları Yönetmeliği")])

    def test_iki_kaynak_birlikte_skora_gore(self, kur):
        ist, conn = kur(self._conn([_m(1, 84, "Mol", 9, mesafe=0.30)],
                                   [_m(5, 12, "Geç gelen öğretmen", 2, mesafe=0.10)]))
        y = _post(ist, {"kapsam": "hepsi", "soru": "öğretmen geç gelirse"}).json()
        assert y["durum"] == "ok"
        assert [p["kaynak"] for p in y["parcalar"]] == [
            "Ortaöğretim Kurumları Yönetmeliği, s. 12", "Kimya 10, s. 84"]
        assert any("FROM chunk_egitim" in q[0] for q in conn.sorgular)
        assert any("FROM chunk_idari" in q[0] for q in conn.sorgular)

    def test_genel_kapsam_idari_aramaz(self, kur):
        # öğretmen/tahta modları: mevzuat eşleşse bile yalnızca kitap
        ist, conn = kur(self._conn([_m(1, 84, "Mol", 9, mesafe=0.30)],
                                   [_m(5, 12, "Geç gelen öğretmen", 2, mesafe=0.10)]))
        y = _post(ist, {"kapsam": "genel", "soru": "öğretmen geç gelirse"}).json()
        assert [p["kaynak"] for p in y["parcalar"]] == ["Kimya 10, s. 84"]
        assert not any("chunk_idari" in q[0] or "idari_belge" in q[0] for q in conn.sorgular)

    def test_yalniz_mevzuat_eslesirse_ok(self, kur):
        ist, _ = kur(self._conn([_m(1, 84, "x", 9, mesafe=0.9)],
                                [_m(5, 12, "Madde", 2, mesafe=0.1)]))
        y = _post(ist, {"kapsam": "hepsi", "soru": "devamsızlık"}).json()
        assert y["durum"] == "ok" and y["parcalar"][0]["kaynak"].startswith("Ortaöğretim")

    def test_ikisi_de_zayifsa_zayif(self, kur):
        ist, _ = kur(self._conn([_m(1, 84, "x", 9, mesafe=0.9)], [_m(5, 12, "y", 2, mesafe=0.9)]))
        assert _post(ist, {"kapsam": "hepsi", "soru": "x"}).json()["durum"] == "zayif"

    def test_en_fazla_top_n_parca(self, kur):
        metin = [_m(i, i, f"m{i}", 9, mesafe=0.1 + i / 100) for i in range(1, 5)]
        idari = [_m(10 + i, i, f"i{i}", 2, mesafe=0.1 + i / 100) for i in range(1, 5)]
        ist, _ = kur(self._conn(metin, idari))
        assert len(_post(ist, {"kapsam": "hepsi", "soru": "x"}).json()["parcalar"]) == rag.TOP_N

    def test_metrik_tek_satir(self, kur):
        ist, conn = kur(self._conn([_m(1, 84, "Mol", 9)], [_m(5, 12, "Madde", 2)]))
        _post(ist, {"kapsam": "hepsi", "soru": "x"})
        assert len(conn.metrik_kayitlari()) == 1

    def test_kimya_kapsami_mevzuata_bakmaz(self, kur):
        ist, conn = kur(self._conn([_m(1, 84, "Mol", 9)], [_m(5, 12, "Madde", 2)]))
        _post(ist, {"kapsam": "kimya", "soru": "mol"})
        assert not any("FROM chunk_idari" in q[0] for q in conn.sorgular)


class TestWebuiRerank:
    """2026-10-04: reranker (bilgehan) varsa birleşik sonuç onunla sıralanır,
    ESIK_RERANK uygulanır; hata verirse kosinüs yoluna düşülür."""

    def _kur(self, kur, skorlar=None, patlat=None):
        from conftest import SahteReranker
        conn = SahteBaglanti([_m(1, 84, "Mol", 9, mesafe=0.10)], kitap_satirlari=KITAPLAR,
                             idari_satirlari=[_m(5, 12, "Geç gelen öğretmen", 2, mesafe=0.30)],
                             idari_belge_satirlari=[(2, "Ortaöğretim Kurumları Yönetmeliği")])
        ist, conn = kur(conn)
        webui.MOTOR.reranker = SahteReranker(skorlar if skorlar is not None else 0.9, patlat=patlat)
        return ist, conn

    def test_rerank_sirasi_kosinusu_ezer(self, kur):
        ist, _ = self._kur(kur, skorlar=[0.05, 0.95])  # sıra: kosinüs birleşimi (Mol, Geç gelen)
        y = _post(ist, {"kapsam": "hepsi", "soru": "öğretmen geç gelirse"}).json()
        assert y["durum"] == "ok"
        assert [p["kaynak"] for p in y["parcalar"]] == ["Ortaöğretim Kurumları Yönetmeliği, s. 12"]
        assert y["parcalar"][0]["skor"] == 0.95

    def test_rerank_esik_alti_zayif(self, kur):
        ist, _ = self._kur(kur, skorlar=0.05)
        assert _post(ist, {"kapsam": "hepsi", "soru": "x"}).json()["durum"] == "zayif"

    def test_rerank_esigi_kitapta_dusuk_mevzuatta_yuksek(self, kur):
        # 0.2: kitap eşiğini (0.10) geçer, mevzuat eşiğini (0.25) geçemez
        ist, _ = self._kur(kur, skorlar=0.2)
        y = _post(ist, {"kapsam": "hepsi", "soru": "x"}).json()
        assert y["durum"] == "ok"
        assert [p["kaynak"] for p in y["parcalar"]] == ["Kimya 10, s. 84"]

    def test_rerank_hatasinda_kosinus_yolu(self, kur):
        ist, _ = self._kur(kur, patlat=ConnectionError("bilgehan kapalı"))
        y = _post(ist, {"kapsam": "hepsi", "soru": "x"}).json()
        assert y["durum"] == "ok"
        assert [p["kaynak"] for p in y["parcalar"]] == [
            "Kimya 10, s. 84", "Ortaöğretim Kurumları Yönetmeliği, s. 12"]

    def test_rerank_tek_kaynakta_da_uygulanir_ve_metrige_yazilir(self, kur):
        ist, conn = self._kur(kur, skorlar=[0.8])
        y = _post(ist, {"kapsam": "kimya", "soru": "mol"}).json()
        assert y["parcalar"][0]["skor"] == 0.8
        (_sql, params), = conn.metrik_kayitlari()
        assert params[2] is not None  # rerank_ms
