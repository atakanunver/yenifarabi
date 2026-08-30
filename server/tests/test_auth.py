"""
server/tests/test_auth.py — FAZ 1 (IMPLEMENT): board kimlik doğrulama.

Ağsız/modelsiz/DB'siz: `TestClient(app)` **`with` bloğu OLMADAN** kullanılır
(doğrulandı: bu, FastAPI/Starlette'in `lifespan` başlatmasını TETİKLEMEZ —
`server/main.py`'nin lifespan'ı gerçek SentenceTransformer/CrossEncoder
modellerini GPU'ya yükleyip PostgreSQL'e bağlanıyor, testte bu ASLA
çalıştırılmamalı). Router'ların ("icerik", "yks", "proxy", "dosya",
"ders_hafizasi", "client_durum") kendisi lifespan taşımıyor — onlar
doğrudan `TestClient` ile, `main.app` da `with` OLMADAN test edilir.

"Valid key" senaryolarında endpoint'in TAM İŞ MANTIĞI çalıştırılmaz (DB/NAS
yolu gerçek ortamda var/yok olabilir, teste bağımlılık istemiyoruz) —
yalnızca auth katmanını GEÇTİĞİ (`status_code != 401`) doğrulanır; ne
döndüğü (503/404/200/500...) her endpoint'in kendi iş mantığına bağlıdır ve
bu dosyanın kapsamı DIŞINDADIR.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import auth  # noqa: E402

HEADER = auth.HEADER_ADI


# ── auth.dogrula_tahta — birim testleri (ağsız, FastAPI'siz) ───────────────
#
# ÖNEMLİ: `dogrula_tahta`'yı DOĞRUDAN çağırırken `x_farabi_board_key`'i HER
# ZAMAN açıkça geçin (ör. `x_farabi_board_key=None`) — FastAPI dışında
# çağrıldığında parametrenin varsayılanı `Header(...)` NESNESİDİR, `None`
# DEĞİL; boş bırakmak "eksik anahtar" yerine yanlışlıkla "Header nesnesi
# geldi" durumunu test eder.

class TestDogrulaTahtaBirim:
    def test_eksik_anahtar_401(self, monkeypatch):
        monkeypatch.setenv("FARABI_AUTH_REQUIRED", "1")
        monkeypatch.setattr(auth, "_board_keys", lambda: {"9-A": "gizli-anahtar"})
        with pytest.raises(Exception) as exc_info:
            auth.dogrula_tahta(x_farabi_board_key=None)
        assert getattr(exc_info.value, "status_code", None) == 401

    def test_bos_anahtar_401(self, monkeypatch):
        monkeypatch.setenv("FARABI_AUTH_REQUIRED", "1")
        monkeypatch.setattr(auth, "_board_keys", lambda: {"9-A": "gizli-anahtar"})
        with pytest.raises(Exception) as exc_info:
            auth.dogrula_tahta(x_farabi_board_key="")
        assert getattr(exc_info.value, "status_code", None) == 401

    def test_yanlis_anahtar_401(self, monkeypatch):
        monkeypatch.setenv("FARABI_AUTH_REQUIRED", "1")
        monkeypatch.setattr(auth, "_board_keys", lambda: {"9-A": "gizli-anahtar"})
        with pytest.raises(Exception) as exc_info:
            auth.dogrula_tahta(x_farabi_board_key="tamamen-yanlis")
        assert getattr(exc_info.value, "status_code", None) == 401

    def test_dogru_anahtar_kabul_edilir(self, monkeypatch):
        monkeypatch.setenv("FARABI_AUTH_REQUIRED", "1")
        monkeypatch.setattr(auth, "_board_keys", lambda: {"9-A": "gizli-anahtar"})
        kimlik = auth.dogrula_tahta(x_farabi_board_key="gizli-anahtar")
        assert kimlik is not None
        assert kimlik.derslik == "9-A"
        assert kimlik.board_id is None   # bkz. auth.py docstring madde 3

    def test_coklu_tahta_dogru_kimlik(self, monkeypatch):
        """Birden fazla tahta anahtarı tanımlıyken, sunulan anahtar HANGİ
        derslikle eşleşiyorsa o kimlik dönmeli — başka bir tahtanınki değil."""
        monkeypatch.setenv("FARABI_AUTH_REQUIRED", "1")
        monkeypatch.setattr(auth, "_board_keys", lambda: {
            "9-A": "anahtar-a", "9-B": "anahtar-b", "10-A": "anahtar-c",
        })
        assert auth.dogrula_tahta(x_farabi_board_key="anahtar-b").derslik == "9-B"
        assert auth.dogrula_tahta(x_farabi_board_key="anahtar-c").derslik == "10-A"
        assert auth.dogrula_tahta(x_farabi_board_key="anahtar-a").derslik == "9-A"

    def test_rollback_modu_auth_kapali(self, monkeypatch):
        """FARABI_AUTH_REQUIRED=0 — acil rollback, doğrulama hiç yapılmadan
        None döner (istek geçer)."""
        monkeypatch.setenv("FARABI_AUTH_REQUIRED", "0")
        monkeypatch.setattr(auth, "_board_keys", lambda: {"9-A": "gizli-anahtar"})
        assert auth.dogrula_tahta(x_farabi_board_key=None) is None
        assert auth.dogrula_tahta(x_farabi_board_key="yanlis-bile-olsa") is None

    def test_varsayilan_auth_zorunlu(self, monkeypatch):
        """Env değişkeni HİÇ verilmezse varsayılan AÇIKTIR — kalıcı güvensiz
        varsayılan olmadığının doğrulaması (FAZ 1 raporu, kritik başarı
        kriteri)."""
        monkeypatch.delenv("FARABI_AUTH_REQUIRED", raising=False)
        assert auth._auth_zorunlu() is True

    def test_bos_board_keys_hicbir_anahtar_gecmez(self, monkeypatch):
        """server/config/api_keys.json'da board_keys hiç yoksa/boşsa —
        fail-closed: hiçbir anahtar geçerli olmaz."""
        monkeypatch.setenv("FARABI_AUTH_REQUIRED", "1")
        monkeypatch.setattr(auth, "_board_keys", lambda: {})
        with pytest.raises(Exception) as exc_info:
            auth.dogrula_tahta(x_farabi_board_key="herhangi-bir-sey")
        assert getattr(exc_info.value, "status_code", None) == 401

    def test_config_dosyasi_okunamazsa_bos_doner(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auth, "CONFIG_PATH", tmp_path / "yok.json")
        assert auth._board_keys() == {}

    def test_board_keys_gecersiz_deger_atlanir(self, tmp_path, monkeypatch):
        (tmp_path / "api_keys.json").write_text(
            '{"board_keys": {"9-A": "gercek", "9-B": ""}}', encoding="utf-8")
        monkeypatch.setattr(auth, "CONFIG_PATH", tmp_path / "api_keys.json")
        anahtarlar = auth._board_keys()
        assert anahtarlar == {"9-A": "gercek"}   # boş değerli 9-B ATLANDI


# ── Gerçek router'lara takılı mı? — TestClient, lifespan TETİKLENMEDEN ─────

@pytest.fixture(autouse=True)
def _her_testte_auth_acik(monkeypatch, tmp_path):
    """TÜM testler için: auth zorunlu + geçerli bir `board_keys` config
    dosyası. `CONFIG_PATH`'i (fonksiyonu DEĞİL) patchliyoruz — böylece
    `_board_keys()`'in GERÇEK dosya-okuma davranışı çalışmaya devam eder;
    yalnızca `_board_keys()`'in kendisini test eden birim testler (yukarıda)
    `CONFIG_PATH`'i KENDİ İÇİNDE tekrar patchleyip bunu geçersiz kılar."""
    monkeypatch.setenv("FARABI_AUTH_REQUIRED", "1")
    gecici = tmp_path / "api_keys.json"
    gecici.write_text('{"board_keys": {"9-A": "test-anahtari"}}', encoding="utf-8")
    monkeypatch.setattr(auth, "CONFIG_PATH", gecici)


def _dogru_basliklar():
    return {HEADER: "test-anahtari"}


class TestMainPyUclari:
    """server/main.py'nin KENDİ 3 endpoint'i — question/kitaplar/
    ders_kaydi_yedek. `main.app` `with` OLMADAN kullanılır (lifespan
    tetiklenmez, bkz. dosya docstring'i); `durum['hazir']` bu yüzden hep
    False kalır — auth'tan SONRA 503 almak "auth'ı geçti" demektir."""

    def test_question_anahtarsiz_401(self):
        import main
        c = TestClient(main.app)
        r = c.post("/api/egitim/question", json={"kitap_id": 1, "soru": "x"})
        assert r.status_code == 401

    def test_question_yanlis_anahtar_401(self):
        import main
        c = TestClient(main.app)
        r = c.post("/api/egitim/question", json={"kitap_id": 1, "soru": "x"},
                    headers={HEADER: "yanlis"})
        assert r.status_code == 401

    def test_question_dogru_anahtar_authtan_geciyor(self):
        import main
        c = TestClient(main.app)
        r = c.post("/api/egitim/question", json={"kitap_id": 1, "soru": "x"},
                    headers=_dogru_basliklar())
        assert r.status_code != 401

    def test_kitaplar_anahtarsiz_401(self):
        import main
        c = TestClient(main.app)
        assert c.get("/api/egitim/kitaplar").status_code == 401

    def test_kitaplar_dogru_anahtar_authtan_geciyor(self):
        import main
        c = TestClient(main.app)
        r = c.get("/api/egitim/kitaplar", headers=_dogru_basliklar())
        assert r.status_code != 401

    def test_ders_kaydi_yedek_anahtarsiz_401(self):
        import main
        c = TestClient(main.app)
        r = c.post("/api/egitim/ders_kaydi_yedek",
                    json={"derslik": "9-A", "dosya_adi": "x.txt", "icerik": "test"})
        assert r.status_code == 401

    def test_ders_kaydi_yedek_dogru_anahtar_yazar(self, tmp_path):
        """Auth'ı geçince MEVCUT davranış (path-traversal savunması dahil)
        AYNEN çalışmalı — bu fazda o koda dokunulmadı, yalnızca üstüne auth
        eklendi."""
        import main
        main.YEDEK_DIR.__class__  # sadece erişilebilir olduğunu doğrula
        orig = main.YEDEK_DIR
        try:
            main.YEDEK_DIR = tmp_path  # gerçek yedekler/ dizinine YAZMA
            c = TestClient(main.app)
            r = c.post("/api/egitim/ders_kaydi_yedek",
                       json={"derslik": "9-A", "dosya_adi": "x.txt", "icerik": "test"},
                       headers=_dogru_basliklar())
            assert r.status_code == 200
            assert (tmp_path / "9-A" / "x.txt").read_text(encoding="utf-8") == "test"
        finally:
            main.YEDEK_DIR = orig

    def test_health_ready_auth_gerektirmez(self):
        """Kasıtlı: /health ve /ready operasyonel uçlar, sır döndürmez —
        bkz. main.py'deki yorum ve FAZ 1 raporu 'AUTH KAPSAMI'."""
        import main
        c = TestClient(main.app)
        assert c.get("/health").status_code == 200
        # /ready: durum['hazir'] False olduğu için 503 döner ama bu AUTH
        # kaynaklı DEĞİL — asıl kontrol: 401 OLMADIĞI.
        assert c.get("/ready").status_code != 401

    def test_traversal_savunmasi_authtan_sonra_hala_calisiyor(self, tmp_path):
        """server/main.py'nin ".." traversal savunması — bu fazda
        DEĞİŞTİRİLMEDİ, yalnızca doğrulanıyor."""
        import main
        orig = main.YEDEK_DIR
        try:
            main.YEDEK_DIR = tmp_path
            c = TestClient(main.app)
            r = c.post("/api/egitim/ders_kaydi_yedek",
                       json={"derslik": "..", "dosya_adi": "x.txt", "icerik": "z"},
                       headers=_dogru_basliklar())
            # Regex allowlist ".."ı GEÇİRİR (bkz. main.py yorumu) ama
            # resolve+containment kontrolü 400 döndürmeli.
            assert r.status_code == 400
        finally:
            main.YEDEK_DIR = orig


def _yalitilmis_app(router) -> TestClient:
    """Tek bir router'ı, main.app'in lifespan'ı OLMADAN, izole bir FastAPI
    örneğine bağlar — gerçek `router` nesnesini (auth dependency'siyle
    birlikte) kullanır, yeniden tanımlamaz."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestIcerikRouter:
    def test_ders_icerigi_anahtarsiz_401(self):
        import icerik
        c = _yalitilmis_app(icerik.router)
        assert c.post("/api/egitim/ders_icerigi", json={}).status_code == 401

    def test_ders_icerigi_dogru_anahtar_authtan_geciyor(self):
        import icerik
        c = _yalitilmis_app(icerik.router)
        r = c.post("/api/egitim/ders_icerigi", json={}, headers=_dogru_basliklar())
        assert r.status_code != 401

    def test_pdf_sayfa_anahtarsiz_401(self):
        import icerik
        c = _yalitilmis_app(icerik.router)
        r = c.get("/api/egitim/pdf_sayfa", params={"ders": "fizik", "sayfa": 1})
        assert r.status_code == 401


class TestYksRouter:
    def test_yks_sorusu_anahtarsiz_401(self):
        import yks
        c = _yalitilmis_app(yks.router)
        r = c.post("/api/egitim/yks_sorusu", json={"derslik": "9-A"})
        assert r.status_code == 401

    def test_yks_sorusu_dogru_anahtar_authtan_geciyor(self):
        import yks
        c = _yalitilmis_app(yks.router)
        r = c.post("/api/egitim/yks_sorusu", json={"derslik": "9-A"},
                    headers=_dogru_basliklar())
        assert r.status_code != 401   # (konu_yok -> 200, iş mantığı bu dosyanın kapsamı dışı)

    def test_yks_sayfa_anahtarsiz_401(self):
        import yks
        c = _yalitilmis_app(yks.router)
        r = c.get("/api/egitim/yks_sayfa", params={"dosya": "x", "sayfa": 1})
        assert r.status_code == 401


class TestProxyRouter:
    def test_metin_uret_anahtarsiz_401(self):
        import proxy
        c = _yalitilmis_app(proxy.router)
        r = c.post("/api/egitim/metin_uret", json={"gorev": "tanimsiz_gorev_testi", "istem": "x"})
        assert r.status_code == 401

    def test_metin_uret_dogru_anahtar_authtan_geciyor(self):
        """`gorev` bilerek tanımsız — saglayicilar._zinciri_dene() hiçbir
        ağ çağrısı yapmadan hemen RuntimeError fırlatır, proxy.py bunu
        yakalayıp status:'hata' döner (200) — auth katmanının davranışını
        test ediyoruz, provider zincirini DEĞİL."""
        import proxy
        c = _yalitilmis_app(proxy.router)
        r = c.post("/api/egitim/metin_uret", json={"gorev": "tanimsiz_gorev_testi", "istem": "x"},
                    headers=_dogru_basliklar())
        assert r.status_code != 401


class TestDosyaRouter:
    def test_dosya_isle_anahtarsiz_401(self):
        import dosya
        c = _yalitilmis_app(dosya.router)
        r = c.post("/api/egitim/dosya_isle",
                    files={"dosya": ("test.txt", b"merhaba", "text/plain")})
        assert r.status_code == 401

    def test_dosya_indir_anahtarsiz_401(self):
        import dosya
        c = _yalitilmis_app(dosya.router)
        r = c.get("/api/egitim/dosya_indir/abc/def.txt")
        assert r.status_code == 401


class TestDersHafizasiRouter:
    def test_ders_hafizasi_anahtarsiz_401(self):
        import ders_hafizasi
        c = _yalitilmis_app(ders_hafizasi.router)
        r = c.post("/api/egitim/ders_hafizasi", json={"derslik": "9-A"})
        assert r.status_code == 401

    def test_ders_hafizasi_dogru_anahtar_authtan_geciyor(self, tmp_path, monkeypatch):
        import ders_hafizasi
        monkeypatch.setattr(ders_hafizasi, "YEDEK_DIR", tmp_path)
        c = _yalitilmis_app(ders_hafizasi.router)
        r = c.post("/api/egitim/ders_hafizasi", json={"derslik": "9-A"},
                    headers=_dogru_basliklar())
        assert r.status_code == 200   # boş dizin -> "kayıtlı geçmiş ders yok" metni


class TestClientDurumRouter:
    def test_heartbeat_anahtarsiz_401(self):
        import client_durum
        c = _yalitilmis_app(client_durum.router)
        r = c.post("/api/client/heartbeat", json={"derslik": "9-A"})
        assert r.status_code == 401

    def test_heartbeat_dogru_anahtar_authtan_geciyor(self):
        import client_durum
        c = _yalitilmis_app(client_durum.router)
        r = c.post("/api/client/heartbeat", json={"derslik": "9-A"},
                    headers=_dogru_basliklar())
        # db.baslat() hiç çağrılmadı -> heartbeat() kendi try/except'inde
        # yakalar, 200 + status:'hata' döner (main.py'nin dışında test
        # ediyoruz, DB'ye bağlanmıyoruz) — asıl kontrol: 401 DEĞİL.
        assert r.status_code != 401

    def test_durum_anahtarsiz_401(self):
        import client_durum
        c = _yalitilmis_app(client_durum.router)
        assert c.get("/api/client/durum").status_code == 401
