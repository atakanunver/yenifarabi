"""
core/saglayicilar.py'nin server-proxy davranışı. Ağ yok — `requests` mock'lanır.

Sağlayıcı-zinciri/soğuma mantığının kendisi artık burada değil,
server/saglayicilar.py'de (bkz. server/tests/test_saglayicilar.py) — bu
dosya taşındı, ORADA test ediliyor. Burada yalnızca HTTP proxy davranışı
(başarı → metin döner, sunucu 'hata' → RuntimeError, bağlantı hatası →
RuntimeError) test edilir.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import saglayicilar as sg  # noqa: E402


def _sahte_yanit(json_veri: dict, status_ok: bool = True):
    r = SimpleNamespace()
    r.json = lambda: json_veri
    r.raise_for_status = (lambda: None) if status_ok else _patlat
    return r


def _patlat():
    raise RuntimeError("http hata")


class TestMetinUret:
    def test_basarili_yanit_metni_doner(self, monkeypatch):
        monkeypatch.setattr(
            "requests.post",
            lambda url, **kw: _sahte_yanit({"status": "ok", "metin": "sonuç metni"}),
        )
        assert sg.metin_uret("belge_ozet", "istem") == "sonuç metni"

    def test_sunucu_hata_donerse_runtimeerror(self, monkeypatch):
        monkeypatch.setattr(
            "requests.post",
            lambda url, **kw: _sahte_yanit({"status": "hata", "hata": "hiçbir sağlayıcı yanıt vermedi"}),
        )
        with pytest.raises(RuntimeError, match="hiçbir sağlayıcı"):
            sg.metin_uret("belge_ozet", "istem")

    def test_baglanti_hatasi_runtimeerror_yukseltir(self, monkeypatch):
        def _patlayan_post(url, **kw):
            raise ConnectionError("bağlantı reddedildi")
        monkeypatch.setattr("requests.post", _patlayan_post)
        with pytest.raises(RuntimeError, match="ulaşılamadı"):
            sg.metin_uret("belge_ozet", "istem")

    def test_sistem_mesaji_govdede_gonderilir(self, monkeypatch):
        yakalanan = {}

        def _sahte_post(url, json=None, **kw):
            yakalanan.update(json or {})
            return _sahte_yanit({"status": "ok", "metin": "ok"})

        monkeypatch.setattr("requests.post", _sahte_post)
        sg.metin_uret("belge_ozet", "kullanıcı istemi", sistem="sistem talimatı")
        assert yakalanan["gorev"] == "belge_ozet"
        assert yakalanan["istem"] == "kullanıcı istemi"
        assert yakalanan["sistem"] == "sistem talimatı"


class TestGorselUret:
    def test_basarili_yanit_metni_doner(self, monkeypatch):
        monkeypatch.setattr(
            "requests.post",
            lambda url, **kw: _sahte_yanit({"status": "ok", "metin": "görsel açıklaması"}),
        )
        assert sg.gorsel_uret("gorsel", "bu görseli anlat", b"\x00\x01", "image/jpeg") == "görsel açıklaması"

    def test_dosya_multipart_olarak_gonderilir(self, monkeypatch):
        yakalanan = {}

        def _sahte_post(url, data=None, files=None, **kw):
            yakalanan["data"] = data
            yakalanan["files"] = files
            return _sahte_yanit({"status": "ok", "metin": "ok"})

        monkeypatch.setattr("requests.post", _sahte_post)
        sg.gorsel_uret("gorsel", "istem", b"\x00\x01", "image/jpeg")
        assert yakalanan["data"]["gorev"] == "gorsel"
        assert yakalanan["files"]["dosya"][2] == "image/jpeg"
