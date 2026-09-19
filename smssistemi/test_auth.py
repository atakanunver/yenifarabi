import hashlib
import hmac
import json
import time

import auth


def _sso_gizli_yaz(tmp_path, monkeypatch, secret_hex: str = "aa" * 32):
    yol = tmp_path / "sso.json"
    yol.write_text(json.dumps({"secret": secret_hex}), encoding="utf-8")
    monkeypatch.setattr(auth, "SSO_GIZLI_YOLU", yol)
    return bytes.fromhex(secret_hex)


def test_sso_dogrula_gecerli_imzayi_kabul_eder(tmp_path, monkeypatch):
    anahtar = _sso_gizli_yaz(tmp_path, monkeypatch)
    zaman_str = str(int(time.time()))
    imza = hmac.new(anahtar, zaman_str.encode("utf-8"), hashlib.sha256).hexdigest()
    assert auth.sso_dogrula(zaman_str, imza) is True


def test_sso_dogrula_yanlis_imzayi_reddeder(tmp_path, monkeypatch):
    _sso_gizli_yaz(tmp_path, monkeypatch)
    zaman_str = str(int(time.time()))
    assert auth.sso_dogrula(zaman_str, "yanlis-imza") is False


def test_sso_dogrula_suresi_gecmis_tokeni_reddeder(tmp_path, monkeypatch):
    anahtar = _sso_gizli_yaz(tmp_path, monkeypatch)
    eski_zaman_str = str(int(time.time()) - 3600)
    imza = hmac.new(anahtar, eski_zaman_str.encode("utf-8"), hashlib.sha256).hexdigest()
    assert auth.sso_dogrula(eski_zaman_str, imza) is False


def test_sifre_hashle_dogru_sifreyle_dogrulanir():
    hash_str = auth.sifre_hashle("gizliSifre123")
    assert auth.sifre_dogrula("gizliSifre123", hash_str) is True


def test_sifre_dogrula_yanlis_sifreyi_reddeder():
    hash_str = auth.sifre_hashle("gizliSifre123")
    assert auth.sifre_dogrula("baskaSifre", hash_str) is False


def test_sifre_dogrula_bozuk_hash_formatinda_false_doner():
    assert auth.sifre_dogrula("herhangi", "gecersiz-format") is False
