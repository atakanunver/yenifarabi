"""
client/tests/test_board_auth.py — FAZ 1 (IMPLEMENT): tahta kimlik anahtarı.

Ağsız: core.tahta.tahta_anahtari()/auth_headers() saf config-okuma
fonksiyonları (test_program.py'nin CONFIG_PATH monkeypatch deseniyle aynı).
Ayrıca: server 401 döndürdüğünde MEVCUT "sınırlı devam" davranışının
bozulmadığını (regresyon) iki farklı hata-işleme deseniyle doğrular —
`kitap_sorusu.py` (raise_for_status → except) ve `pdf_sayfa.py` (açık
status_code kontrolü) — actions/*.py'deki iki farklı üsluptan biri.
"""

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import requests  # noqa: E402

import core.tahta as tahta  # noqa: E402


class TestTahtaAnahtari:
    def test_anahtar_yoksa_bos(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tahta, "CONFIG_PATH", tmp_path / "yok.json")
        assert tahta.tahta_anahtari() == ""
        assert tahta.auth_headers() == {}

    def test_anahtar_varsa_okunur(self, tmp_path, monkeypatch):
        (tmp_path / "api_keys.json").write_text(
            '{"tahta_anahtari": "gizli-9a"}', encoding="utf-8")
        monkeypatch.setattr(tahta, "CONFIG_PATH", tmp_path / "api_keys.json")
        assert tahta.tahta_anahtari() == "gizli-9a"
        assert tahta.auth_headers() == {"X-Farabi-Board-Key": "gizli-9a"}

    def test_bos_dize_de_header_uretmez(self, tmp_path, monkeypatch):
        (tmp_path / "api_keys.json").write_text(
            '{"tahta_anahtari": "   "}', encoding="utf-8")
        monkeypatch.setattr(tahta, "CONFIG_PATH", tmp_path / "api_keys.json")
        assert tahta.tahta_anahtari() == ""
        assert tahta.auth_headers() == {}


class _Sahte401Yaniti:
    status_code = 401

    def raise_for_status(self):
        raise requests.exceptions.HTTPError("401 Client Error: Unauthorized")

    def json(self):
        return {"detail": "Geçersiz X-Farabi-Board-Key"}


class TestSunucu401SessizceKarsilanir:
    """Kritik davranış (FAZ 1 raporu §11/§25): auth hatası dersi asla
    kesmemeli — mevcut try/except → sınırlı-devam deseni 401'i de KAPSAMALI,
    özel bir dal AÇILMAMALI."""

    def test_kitap_sorusu_401de_sinirli_devam_doner(self, monkeypatch):
        import actions.kitap_sorusu as m
        monkeypatch.setattr(m, "_KITAP_ONBELLEK",
                             [{"id": 1, "dosya_adi": "biyoloji-9.pdf", "sinif": 9, "ders": "Biyoloji"}])
        monkeypatch.setattr(m.requests, "post", lambda *a, **kw: _Sahte401Yaniti())
        sonuc = m.kitap_sorusu(parameters={"soru": "test?", "ders": "biyoloji", "sinif": "9"})
        assert sonuc == m._SINIRLI_DEVAM

    def test_pdf_sayfa_401de_hata_metni_doner_raise_etmez(self, monkeypatch):
        import actions.pdf_sayfa as m
        monkeypatch.setattr(m.requests, "get", lambda *a, **kw: _Sahte401Yaniti())
        sonuc = m.pdf_sayfa(parameters={"sayfa": 5, "ders": "fizik"})
        # pdf_sayfa.py `r.status_code != 200` dalına düşer — exception
        # FIRLATMAZ, "detail" metnini döner (mevcut davranış, DEĞİŞMEDİ).
        assert sonuc == "Geçersiz X-Farabi-Board-Key"
