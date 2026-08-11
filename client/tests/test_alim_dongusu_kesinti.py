"""
main.py::FarabiLive._receive_audio() — kesinti (interrupted) anında
arabelleklerin akışı.

Regresyon: `sc.interrupted` geldiğinde out_buf/in_buf SIFIRLANMIYORDU, bu
yüzden kesilen turun yarım metni bir SONRAKİ turun metniyle aynı satırda
birleşiyordu (ölçüldü: 02.08.2026, logs/ders/2026-08-02.txt, 11:30:22 —
öğretmenin "Matematik, permütasyon" dediği an Farabi'nin önceki, kesilmiş
cümlesiyle tek bir dev FARABİ satırında karışmıştı). Ağ yok — session.receive()
sahte, sonlu bir olay dizisi üretir.
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

import main  # noqa: E402


class _TestBitti(Exception):
    """Sahte alım döngüsünü sonlandırmak için — gerçek bir hata değil."""


def _sc(interrupted=False, out_text=None, in_text=None, turn_complete=False):
    return SimpleNamespace(
        interrupted=interrupted,
        output_transcription=SimpleNamespace(text=out_text) if out_text else None,
        input_transcription=SimpleNamespace(text=in_text) if in_text else None,
        turn_complete=turn_complete,
    )


def _yanit(server_content=None):
    return SimpleNamespace(data=None, server_content=server_content, tool_call=None)


class _SahteSession:
    """İlk .receive() çağrısı sabit bir olay dizisi üretir; ikinci çağrı
    (dış while True döngüsü tekrar denediğinde) testi sonlandırır."""

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


def _farabi_live(olaylar) -> main.FarabiLive:
    f = main.FarabiLive.__new__(main.FarabiLive)
    f.session = _SahteSession(olaylar)
    f.audio_in_queue = asyncio.Queue()
    f._turn_done_event = None
    f._speaking_lock = threading.Lock()
    f._is_speaking = False
    f._son_etkinlik = time.monotonic()
    f.ui = SimpleNamespace(
        write_log=lambda *_a: None,
        set_state=lambda *_a: None,
        muted=False,
    )
    return f


def test_kesinti_arabellekleri_sifirlar_sonraki_turla_birlesmez(monkeypatch):
    kayitlar: list[tuple[str, str]] = []
    monkeypatch.setattr(main.transcript, "log_line",
                        lambda speaker, text: kayitlar.append((speaker, text)))

    olaylar = [
        # 1) Kesilen turun yarım kalan çıktısı
        _yanit(_sc(out_text="İlk cümle parçası")),
        # 2) Kesinti sinyali — burada flush+reset olmalı
        _yanit(_sc(interrupted=True)),
        # 3) Yeni turun girdisi (öğretmen/öğrenci konuştu)
        _yanit(_sc(in_text="Matematik, permütasyon")),
        # 4) Yeni turun çıktısı + turn_complete
        _yanit(_sc(out_text="Anladım kıymetli öğretmenim.", turn_complete=True)),
    ]
    f = _farabi_live(olaylar)

    with pytest.raises(_TestBitti):
        asyncio.run(f._receive_audio())

    assert kayitlar == [
        ("farabi", "İlk cümle parçası (kesildi)"),
        ("ogrenci", "Matematik, permütasyon"),
        ("farabi", "Anladım kıymetli öğretmenim."),
    ], f"Beklenmeyen kayıt sırası/içeriği: {kayitlar}"

    # Asıl regresyon: iki FARABİ metni TEK bir satırda birleşmemiş olmalı.
    farabi_kayitlari = [t for s, t in kayitlar if s == "farabi"]
    assert not any("Matematik" in t for t in farabi_kayitlari), \
        "öğretmenin sözü FARABİ satırına karışmış olmamalı"
    assert len(farabi_kayitlari) == 2, "kesilen ve yeni tur ayrı satırlar olmalı"


def test_kesintide_bos_arabellek_hicbir_sey_kaydetmez(monkeypatch):
    kayitlar: list[tuple[str, str]] = []
    monkeypatch.setattr(main.transcript, "log_line",
                        lambda speaker, text: kayitlar.append((speaker, text)))

    olaylar = [
        _yanit(_sc(interrupted=True)),   # hiç birikmiş metin yokken kesinti
        _yanit(_sc(out_text="Temiz başlangıç.", turn_complete=True)),
    ]
    f = _farabi_live(olaylar)

    with pytest.raises(_TestBitti):
        asyncio.run(f._receive_audio())

    assert kayitlar == [("farabi", "Temiz başlangıç.")]
