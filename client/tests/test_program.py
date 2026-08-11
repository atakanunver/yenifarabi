"""
Ders programı — "bugün hangi ders?" sorusunun kodla cevaplanması.

Program dosyası testte geçici bir dosyaya yönlendirilir; okulun gerçek
programına bağımlı test yazılmaz.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import program                        # noqa: E402

ORNEK = {
    "siniflar": {
        "9-A": {
            "pazartesi": {"1": "matematik", "3": "fizik"},
            "salı":      {"2": {"ders": "matematik", "kip": "ogretmensiz"}},
        }
    }
}

# 2025-11-03 pazartesi, 2025-11-04 salı
PAZARTESI = datetime(2025, 11, 3, 8, 30)     # 1. ders
SALI      = datetime(2025, 11, 4, 9, 20)     # 2. ders


@pytest.fixture
def program_dosyasi(tmp_path, monkeypatch):
    yol = tmp_path / "ders_programi.json"
    yol.write_text(json.dumps(ORNEK, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(program, "PROGRAM_PATH", yol)
    monkeypatch.setattr(program.tahta, "derslik", lambda: "9-A")
    return yol


def _zil(monkeypatch, tur="ders", ders_no=1, kalan=30):
    monkeypatch.setattr(program.zil, "ders_durumu",
                        lambda simdi=None: {"tur": tur, "ders_no": ders_no,
                                            "kalan_dk": kalan})


def test_ders_saatinden_ders_bulunur(program_dosyasi, monkeypatch):
    _zil(monkeypatch, ders_no=1)
    slot = program.simdiki_ders(PAZARTESI)
    assert slot["ders"] == "matematik"
    assert slot["ders_no"] == 1
    assert slot["sinif"] == "9-A"


def test_bos_saat_none_doner(program_dosyasi, monkeypatch):
    # Pazartesi 2. ders programda yok: Farabi çerçeveyi plandan çözmeye düşer.
    _zil(monkeypatch, ders_no=2)
    assert program.simdiki_ders(PAZARTESI) is None


def test_teneffuste_ders_yok(program_dosyasi, monkeypatch):
    _zil(monkeypatch, tur="teneffus", ders_no=3)
    assert program.simdiki_ders(PAZARTESI) is None


def test_turkce_harfli_gun_adi_da_kabul_edilir(program_dosyasi, monkeypatch):
    # Dosyada "salı" yazıyor, kod "sali" arıyor.
    _zil(monkeypatch, ders_no=2)
    slot = program.simdiki_ders(SALI)
    assert slot and slot["ders"] == "matematik"


def test_slot_kipi_okunur(program_dosyasi, monkeypatch):
    """Etüt/telafi saatleri programda işaretlidir."""
    _zil(monkeypatch, ders_no=2)
    assert program.kip(SALI) == "ogretmensiz"


def test_program_yoksa_sessizce_none(monkeypatch, tmp_path):
    monkeypatch.setattr(program, "PROGRAM_PATH", tmp_path / "yok.json")
    # Program dosyası olmayan bir tahta ders yapamaz hâle GELMEMELİ.
    assert program.cizelge() is None
    assert program.simdiki_ders(PAZARTESI) is None
    assert program.etiket(PAZARTESI) == ""


def test_gunun_programi_sirali(program_dosyasi, monkeypatch):
    _zil(monkeypatch, ders_no=1)
    gun = program.gunun_programi(PAZARTESI)
    assert [s["ders_no"] for s in gun] == [1, 3]


def test_etiket_arayuz_icin_tek_satir(program_dosyasi, monkeypatch):
    _zil(monkeypatch, ders_no=1)
    assert program.etiket(PAZARTESI) == "1. ders · Matematik"


def test_ornek_veri_kullanilmaz(tmp_path, monkeypatch):
    """
    Uydurma programla çalışmak, programsız çalışmaktan tehlikelidir: Farabi
    sınıfa "şu an 3. ders, matematik" diye KENDİNDEN EMİN yanlış söyler.
    '_ornek': true taşıyan dosya bu yüzden hiç kullanılmaz.
    """
    yol = tmp_path / "ders_programi.json"
    yol.write_text(json.dumps({"_ornek": True, **ORNEK}, ensure_ascii=False),
                   encoding="utf-8")
    monkeypatch.setattr(program, "PROGRAM_PATH", yol)
    monkeypatch.setattr(program.tahta, "derslik", lambda: "9-A")
    _zil(monkeypatch, ders_no=1)
    assert program.cizelge() is None
    assert program.simdiki_ders(PAZARTESI) is None


def test_ornek_isareti_kalkinca_kullanilir(tmp_path, monkeypatch):
    yol = tmp_path / "ders_programi.json"
    yol.write_text(json.dumps(ORNEK, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(program, "PROGRAM_PATH", yol)
    monkeypatch.setattr(program.tahta, "derslik", lambda: "9-A")
    _zil(monkeypatch, ders_no=1)
    assert program.simdiki_ders(PAZARTESI)["ders"] == "matematik"
