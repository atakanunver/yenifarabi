"""
main.py::FarabiLive._oturum_devam_notu() — yeniden bağlanma sonrası devam notu.

Regresyon: konu/kazanım henüz bilinmiyorken "dersin ortasındasın, sürdür"
denince model var olmayan bir konu icat ediyordu (ölçüldü: 02.08.2026,
logs/ders/2026-08-02.txt, 09:52:13 — "türev" konusu icat edilip "kaldığımız
yerden devam edelim" dendi, oysa hiçbir konu konuşulmamıştı). Ağ yok —
session.send_client_content mock'lanır.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("sounddevice", reason="ses bağımlılıkları olmadan atlanır")

import main                              # noqa: E402
from core.ders_motoru import DersDurumu  # noqa: E402


class _SahteSession:
    def __init__(self):
        self.gonderilen: list[dict] = []

    async def send_client_content(self, turns, turn_complete=True):
        self.gonderilen.append(turns)


def _f(durum: DersDurumu) -> main.FarabiLive:
    f = main.FarabiLive.__new__(main.FarabiLive)
    f.session = _SahteSession()
    f.motor = SimpleNamespace(durum=durum)
    f.ui = SimpleNamespace(write_log=lambda *_a: None)
    return f


def _metin(f: main.FarabiLive) -> str:
    turns = f.session.gonderilen[0]
    return turns["parts"][0]["text"]


class TestOturumDevamNotu:
    def test_konu_bilinmiyorsa_devam_iddiasinda_bulunmaz(self):
        f = _f(DersDurumu())   # ders_adi="", konu="" — hiçbir şey bilinmiyor
        asyncio.run(f._oturum_devam_notu())
        metin = _metin(f)

        assert "UYDURMA" in metin
        assert "kaldığımız yerden devam edelim" not in metin.lower() or \
               "DEME" in metin
        assert "dersin ortasındasın" not in metin.lower()
        assert "- Ders:" not in metin   # bilinmeyen konu satırı eklenmemeli

    def test_konu_biliniyorsa_normal_devam_notu_gider(self):
        d = DersDurumu(ders_adi="Matematik", konu="Permütasyon", kalan_dk=25)
        f = _f(d)
        asyncio.run(f._oturum_devam_notu())
        metin = _metin(f)

        assert "dersin ortasındasın" in metin.lower()
        assert "Matematik" in metin and "Permütasyon" in metin
        assert "UYDURMA bir konu İCAT ETME" not in metin

    def test_ikisinde_de_selamlama_yasagi_var(self):
        for d in (DersDurumu(), DersDurumu(ders_adi="Fizik", konu="Kuvvet")):
            f = _f(d)
            asyncio.run(f._oturum_devam_notu())
            assert "SELAMLAMA YAPMA" in _metin(f)
