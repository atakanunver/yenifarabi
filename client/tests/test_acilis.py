"""
Ders açılışı (`_send_session_opening`) — mikrofonlu akış.

Plandan gelen kazanım (2026-10-06) dersi 'hazır' yapmaz (karar: planı
kullan, konuyu sor): öneri olarak söylenir, öğretmen onaylamadan başlanmaz.
Konu ya da öğretmen kazanımı varsa ders hazırdır ve yoklamaya geçilir.

Ağ yok — session mock'lanır.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("sounddevice", reason="ses bağımlılıkları olmadan atlanır")

import main  # noqa: E402


class _SahteSession:
    def __init__(self):
        self.gonderilen: list[str] = []

    async def send_client_content(self, turns, turn_complete=True):
        self.gonderilen.append(turns["parts"][0]["text"])


def _acilis_farabi(lesson: dict | None):
    f = main.FarabiLive.__new__(main.FarabiLive)
    f.session = _SahteSession()
    f.ui = SimpleNamespace(write_log=lambda *_a: None, ders_dili="tr")
    f._ders_kipi = main.KIP_OGRETMENLI
    f._program_slotu = None
    f._current_lesson = lesson
    return f


def _acilis_metni(f) -> str:
    asyncio.run(f._send_session_opening())
    return f.session.gonderilen[0]


class TestAcilis:
    DERS = {"subject": "Fizik", "topic": "Newton'un yasaları", "kazanim": ""}

    def test_normal_acilis_degismedi(self):
        metin = _acilis_metni(_acilis_farabi(self.DERS))
        assert "Yoklama al" in metin


class TestAcilisPlanKazanimi:
    PLAN = {"subject": "Matematik", "topic": "", "kazanim": "12.1.2.2. Logaritma",
            "kazanim_kaynagi": "plan"}

    def test_plan_kazanimi_konuyu_sorar_yoklamaya_gecmez(self):
        metin = _acilis_metni(_acilis_farabi(dict(self.PLAN)))
        assert "Yoklama al" not in metin
        assert "Yıllık plana göre bu haftanın kazanımı: 12.1.2.2. Logaritma" in metin
        assert "öğretmen onaylamadan bu kazanımla derse BAŞLAMA" in metin
        assert "söylemesini" in metin

    def test_ogretmen_kazanimi_eskisi_gibi_hazir(self):
        ders = {"subject": "Fizik", "topic": "", "kazanim": "Newton",
                "kazanim_kaynagi": "ogretmen"}
        metin = _acilis_metni(_acilis_farabi(ders))
        assert "Dersin kazanımını tek cümleyle, kendi sözlerinle söyle: Newton" in metin
        assert "Yoklama al" in metin
