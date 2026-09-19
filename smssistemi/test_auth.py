import auth


def test_sifre_hashle_dogru_sifreyle_dogrulanir():
    hash_str = auth.sifre_hashle("gizliSifre123")
    assert auth.sifre_dogrula("gizliSifre123", hash_str) is True


def test_sifre_dogrula_yanlis_sifreyi_reddeder():
    hash_str = auth.sifre_hashle("gizliSifre123")
    assert auth.sifre_dogrula("baskaSifre", hash_str) is False


def test_sifre_dogrula_bozuk_hash_formatinda_false_doner():
    assert auth.sifre_dogrula("herhangi", "gecersiz-format") is False
