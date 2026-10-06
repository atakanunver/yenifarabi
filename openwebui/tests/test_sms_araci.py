import farabi_sms_araci as fs


def test_gun_adi_aractan_gelir():
    assert fs._gunlu("2026-10-14 10:00") == "14.10.2026 Çarşamba 10:00"
    assert fs._gunlu("2026-10-17 08:30") == "17.10.2026 Cumartesi 08:30"
    assert fs._gunlu("bozuk") == "bozuk"
