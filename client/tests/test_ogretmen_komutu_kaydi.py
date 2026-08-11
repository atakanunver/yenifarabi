"""
main.py::FarabiLive._on_teacher_command() — yazılı öğretmen talimatı artık
kalıcı ders kaydına da düşüyor.

Regresyon: talimat yalnızca ekrandaki (geçici) DERS KAYDI paneline
yazılıyordu, logs/ders/*.txt'de hiç yoktu — sonradan bir dersi incelerken
Farabi'nin NEDEN öyle davrandığını gösteren en önemli parça (öğretmenin ne
yazdığı) görünmüyordu. tests/conftest.py FARABI_DERS_LOG_DIR'ı geçici bir
dizine yönlendiriyor; burada gerçek ders kaydına yazılmaz.
"""

import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("sounddevice", reason="ses bağımlılıkları olmadan atlanır")

import main  # noqa: E402
from core import transcript  # noqa: E402


def _farabi_live() -> main.FarabiLive:
    f = main.FarabiLive.__new__(main.FarabiLive)
    f._loop = None
    f._son_etkinlik = 0.0
    f._video_yuzunden_susturuldu = False
    f.motor = SimpleNamespace(
        duraklat=lambda *_a: None,
        mudahale=lambda *_a: None,
    )
    f.ui = SimpleNamespace(
        write_log=lambda *_a: None,
        set_state=lambda *_a: None,
        muted=False,
    )
    return f


def test_yazili_talimat_kalici_kayda_duser():
    f = _farabi_live()
    f._on_teacher_command("yazili", "[ÖĞRETMEN KOMUTU] konu: Türev · kazanım: Anlık değişim hızı")

    metin = transcript.today_file().read_text(encoding="utf-8")
    assert "ÖĞRETMEN  konu: Türev · kazanım: Anlık değişim hızı" in metin
    # Etiket öğretmen zaten belirttiği için önek satırda TEKRAR etmemeli.
    assert "[ÖĞRETMEN KOMUTU]" not in metin.splitlines()[-1]


def test_durdur_devam_da_kayda_duser():
    f = _farabi_live()
    f._on_teacher_command("durdur", "[ÖĞRETMEN KOMUTU] Dersi burada duraklat.")
    f._on_teacher_command("devam", "[ÖĞRETMEN KOMUTU] Derse devam et.")

    metin = transcript.today_file().read_text(encoding="utf-8")
    assert "ÖĞRETMEN  Dersi burada duraklat." in metin
    assert "ÖĞRETMEN  Derse devam et." in metin
