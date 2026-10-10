from kaynaklar import kazanim
from kaynaklar.kazanim import TestSonucu


def test_ozet_form_ve_odev_birlesir():
    form = [
        TestSonucu("matematik", 3, "Kesirler", 8, 10, "2026-10-01"),
        TestSonucu("matematik", 4, "Oran", 3, 10, "2026-10-08"),
        TestSonucu("fizik", 2, "Hız", 7, 10, "2026-10-02"),
    ]
    odev = [
        ("matematik", "Kesirler", False),
        ("matematik", "Kesirler", True),
        ("fizik", "Kuvvet", True),
    ]
    o = kazanim.ozet(form, odev)
    mat = {d.kazanim: (d.dogru, d.toplam) for d in o["matematik"]}
    assert mat == {"Kesirler": (9, 12), "Oran": (3, 10)}
    assert {d.kazanim for d in o["fizik"]} == {"Hız", "Kuvvet"}


def test_basari_esigi():
    d = kazanim.KazanimDurum("matematik", "K", 7, 10)
    assert d.basarili(0.7)
    assert not kazanim.KazanimDurum("matematik", "K", 6, 10).basarili(0.7)
    assert d.yuzde == 70


def test_ders_ozeti():
    o = kazanim.ozet(
        [
            TestSonucu("matematik", 1, "A", 9, 10, "x"),
            TestSonucu("matematik", 2, "B", 1, 10, "x"),
        ],
        [],
    )
    assert kazanim.ders_ozeti(o, 0.7) == [("matematik", 1, 2)]
