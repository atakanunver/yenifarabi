import json
from datetime import date

import pytest
from ayarlar import AYAR
from kaynaklar import KaynakHatasi, program

PROGRAM = {
    "siniflar": {
        "9-A": {
            "pazartesi": {"2": "fizik", "1": "matematik"},
            "sali": {"1": "türk dili ve edebiyatı"},
        },
        "9-B": {"pazartesi": {"1": "matematik"}},
    }
}


@pytest.fixture
def prog():
    AYAR.program_yolu.write_text(
        json.dumps(PROGRAM, ensure_ascii=False), encoding="utf-8"
    )


def test_gun_dersleri_sirali(prog):
    assert program.gun_dersleri("9-A", "pazartesi") == [(1, "matematik"), (2, "fizik")]
    assert program.gun_dersleri("9-A", "cuma") == []
    assert program.gun_dersleri("12-Z", "pazartesi") == []


def test_bugun(prog):
    assert program.bugun("9-A", date(2026, 10, 12)) == [(1, "matematik"), (2, "fizik")]
    assert program.bugun("9-A", date(2026, 10, 11)) == []  # pazar


def test_haftalik_bes_gun(prog):
    h = program.haftalik("9-A")
    assert [g for g, _ in h] == ["pazartesi", "sali", "carsamba", "persembe", "cuma"]
    assert h[1][1] == [(1, "türk dili ve edebiyatı")]


def test_ogretmen_haftalik(prog):
    h = dict(program.ogretmen_haftalik([("9-A", "Matematik"), ("9-B", "matematik")]))
    assert h["pazartesi"] == [(1, "9-A", "matematik"), (1, "9-B", "matematik")]
    assert h["sali"] == []


def test_dosya_yoksa_kaynak_hatasi():
    with pytest.raises(KaynakHatasi):
        program.gun_dersleri("9-A", "pazartesi")
