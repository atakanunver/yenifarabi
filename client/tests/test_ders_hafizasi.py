"""
actions/ders_hafizasi.py'nin server-proxy davranışı. Ağ yok — `requests`
mock'lanır.

Eşleştirme mantığının kendisi artık burada değil, `server/ders_hafizasi.py`'de
(bkz. server/tests/test_ders_hafizasi.py) — bu dosya taşındı, ORADA test
ediliyor. Burada yalnızca HTTP proxy davranışı (başarı → sunucunun 'metin'
alanı döner, sunucu hatası/bağlantı hatası → sessizce nazik bir mesaj, asla
raise) test edilir.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from actions.ders_hafizasi import ders_hafizasi  # noqa: E402
from core import transcript                      # noqa: E402


@pytest.fixture
def izole_oturum(monkeypatch, tmp_path):
    """session_file()'ın gerçek diskte bir şey yazmasını engelle."""
    monkeypatch.setattr(transcript, "LOG_DIR", tmp_path)
    monkeypatch.setattr(transcript, "_oturum_yolu", None)


def _sahte_yanit(json_veri: dict, status_ok: bool = True):
    r = SimpleNamespace()
    r.json = lambda: json_veri
    r.raise_for_status = (lambda: None) if status_ok else _patlat
    return r


def _patlat():
    raise RuntimeError("http hata")


def test_basarili_yanit_metni_doner(monkeypatch, izole_oturum):
    monkeypatch.setattr(
        "requests.post",
        lambda url, **kw: _sahte_yanit({"metin": "geçmiş ders özeti"}),
    )
    assert ders_hafizasi({"konu": "hücre zarı"}) == "geçmiş ders özeti"


def test_istek_govdesi_derslik_ve_guncel_dosya_icerir(monkeypatch, izole_oturum):
    yakalanan = {}

    def _sahte_post(url, json=None, **kw):
        yakalanan.update(json or {})
        return _sahte_yanit({"metin": "ok"})

    monkeypatch.setattr("requests.post", _sahte_post)
    ders_hafizasi({"ders": "Matematik", "konu": "Türev"})
    assert yakalanan["ders"] == "Matematik"
    assert yakalanan["konu"] == "Türev"
    assert yakalanan["guncel_dosya"]  # session_file().name boş olmamalı


def test_baglanti_hatasi_sessizce_nazik_mesaj_doner(monkeypatch, izole_oturum):
    def _patlayan_post(url, **kw):
        raise ConnectionError("bağlantı reddedildi")
    monkeypatch.setattr("requests.post", _patlayan_post)
    sonuc = ders_hafizasi({})
    assert "ulaşamıyorum" in sonuc


def test_sunucu_metin_alani_bossa_nazik_mesaj_doner(monkeypatch, izole_oturum):
    monkeypatch.setattr("requests.post", lambda url, **kw: _sahte_yanit({}))
    sonuc = ders_hafizasi({})
    assert "okunamadı" in sonuc
