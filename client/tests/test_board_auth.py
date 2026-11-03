"""
client/tests/test_board_auth.py — FAZ 1 (IMPLEMENT): tahta kimlik anahtarı.

Ağsız: core.tahta.tahta_anahtari()/auth_headers() saf config-okuma
fonksiyonları (test_program.py'nin CONFIG_PATH monkeypatch deseniyle aynı).
Ayrıca sunucudan 401 geldiğinde PDF sayfası aracının hata metniyle
sınırlı şekilde devam ettiğini doğrular.
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
        # X-Farabi-Client-Version KOŞULSUZ gider (server/main.py::/api/version
        # sürüm uyumluluğunu bu header'la kontrol ediyor, board anahtarından
        # bağımsız) — yalnızca X-Farabi-Board-Key board anahtarına bağlı.
        assert tahta.auth_headers() == {"X-Farabi-Client-Version": tahta.VERSION}

    def test_anahtar_varsa_okunur(self, tmp_path, monkeypatch):
        (tmp_path / "api_keys.json").write_text(
            '{"tahta_anahtari": "gizli-9a"}', encoding="utf-8")
        monkeypatch.setattr(tahta, "CONFIG_PATH", tmp_path / "api_keys.json")
        assert tahta.tahta_anahtari() == "gizli-9a"
        assert tahta.auth_headers() == {
            "X-Farabi-Client-Version": tahta.VERSION,
            "X-Farabi-Board-Key": "gizli-9a",
        }

    def test_bos_dize_de_header_uretmez(self, tmp_path, monkeypatch):
        (tmp_path / "api_keys.json").write_text(
            '{"tahta_anahtari": "   "}', encoding="utf-8")
        monkeypatch.setattr(tahta, "CONFIG_PATH", tmp_path / "api_keys.json")
        assert tahta.tahta_anahtari() == ""
        # "header üretmez" başlığı artık yalnızca X-Farabi-Board-Key için
        # geçerli — boş/whitespace tahta_anahtari o header'ı eklemiyor, ama
        # X-Farabi-Client-Version'ı etkilemiyor.
        assert tahta.auth_headers() == {"X-Farabi-Client-Version": tahta.VERSION}


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

    def test_pdf_sayfa_401de_hata_metni_doner_raise_etmez(self, monkeypatch):
        import actions.pdf_sayfa as m
        monkeypatch.setattr(m.requests, "get", lambda *a, **kw: _Sahte401Yaniti())
        sonuc = m.pdf_sayfa(parameters={"sayfa": 5, "ders": "fizik"})
        # pdf_sayfa.py `r.status_code != 200` dalına düşer — exception
        # FIRLATMAZ, "detail" metnini döner (mevcut davranış, DEĞİŞMEDİ).
        assert sonuc == "Geçersiz X-Farabi-Board-Key"
