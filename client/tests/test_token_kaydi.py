"""
main.py — Gemini token kaydı entegrasyonu (`_receive_audio`,
`_kullanim_kaydet`, `_dersi_bitir`). Ağ yok; session.receive() sahte, sonlu.
Kayıt hatası dersi/alım döngüsünü ASLA bozmamalı.
"""

import asyncio
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("sounddevice", reason="ses bağımlılıkları olmadan atlanır")

import main


class _TestBitti(Exception):
    """Sahte alım döngüsünü sonlandırmak için — gerçek bir hata değil."""


class _SahteSession:
    def __init__(self, olaylar):
        self._olaylar = olaylar
        self._cagri_sayisi = 0

    def receive(self):
        self._cagri_sayisi += 1
        if self._cagri_sayisi > 1:
            raise _TestBitti("döngü bir daha denedi — test bitti")
        return self._uretec()

    async def _uretec(self):
        for olay in self._olaylar:
            yield olay


def _yanit(usage=None):
    return SimpleNamespace(data=None, server_content=None, tool_call=None,
                           usage_metadata=usage)


def _usage(girdi, yanit=0, toplam=0):
    return SimpleNamespace(prompt_token_count=girdi, response_token_count=yanit,
                           total_token_count=toplam)


def _farabi_live(olaylar=()) -> main.FarabiLive:
    f = main.FarabiLive.__new__(main.FarabiLive)
    f.session = _SahteSession(list(olaylar))
    f.audio_in_queue = asyncio.Queue()
    f._turn_done_event = None
    f._speaking_lock = threading.Lock()
    f._is_speaking = False
    f._son_etkinlik = time.monotonic()
    f.ui = SimpleNamespace(
        write_log=lambda *_a: None,
        set_state=lambda *_a: None,
        canli_satir_baslat=lambda *_a: None,
        canli_satir_guncelle=lambda *_a: None,
        canli_satir_bitir=lambda *_a: None,
        muted=False,
    )
    return f


def test_usage_metadata_iki_sayaca_birikir():
    f = _farabi_live([_yanit(_usage(100, 10, 110)), _yanit(None),
                      _yanit(_usage(300, 20, 320))])
    with pytest.raises(_TestBitti):
        asyncio.run(f._receive_audio())
    for sayac in (f._kullanim_baglanti, f._kullanim_ders):
        assert sayac.mesaj == 2
        assert sayac.toplam["girdi"] == 400
        assert sayac.toplam["toplam"] == 430
        assert sayac.en_buyuk_girdi == 300


def test_kullanim_kaydet_patlayan_usage_istisna_firlatmaz():
    class _Patlak:
        @property
        def prompt_token_count(self):
            raise RuntimeError("bozuk usage")

    f = _farabi_live()
    f._kullanim_kaydet(_Patlak())  # fırlatmamalı
    f._kullanim_kaydet(None)       # None da güvenli (0 sayılır)


def _dersi_bitir_hazirla(monkeypatch):
    kayitlar: list[tuple[str, str]] = []
    monkeypatch.setattr(main.transcript, "log_line",
                        lambda s, t: kayitlar.append((s, t)))
    monkeypatch.setattr(main.transcript, "log_session_end", lambda: None)
    monkeypatch.setattr(main.FarabiLive, "_ders_kaydini_yedekle",
                        staticmethod(lambda: None))
    f = _farabi_live()
    f._ders_bitti_event = None
    return f, kayitlar


def test_dersi_bitir_token_satiri_yazar_ve_sayaci_sifirlar(monkeypatch):
    f, kayitlar = _dersi_bitir_hazirla(monkeypatch)
    f._kullanim_kaydet(_usage(100, 10, 110))
    asyncio.run(f._dersi_bitir("test"))
    token = [t for s, t in kayitlar if s == "sistem" and "Gemini token kullanımı" in t]
    assert len(token) == 1 and "mesaj=1" in token[0]
    # Satır, "Oturum kapandı" satırından ÖNCE yazılmış olmalı
    assert kayitlar.index(("sistem", token[0])) < len(kayitlar) - 1
    assert f._kullanim_ders.bos
    assert not f._kullanim_baglanti.bos  # bağlantı sayacı run()'a ait


def test_dersi_bitir_bos_sayacta_token_satiri_yazmaz(monkeypatch):
    f, kayitlar = _dersi_bitir_hazirla(monkeypatch)
    asyncio.run(f._dersi_bitir("test"))
    assert not any("Gemini token kullanımı" in t for _s, t in kayitlar)
