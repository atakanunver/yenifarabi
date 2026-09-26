"""tests/test_network.py — ses düğümü websocket'inin LAN-dışı reddi.
`_adres_izinli_mi` doğrudan test edilir (Starlette TestClient websocket'i
"testclient" gibi sahte bir host stringi rapor eder, IP tabanlı bir
kontrolü tetiklemez — bkz. plan/advisor notu; bu yüzden fonksiyon
IZOLE test edilir, ASGI TestClient üzerinden DEĞİL)."""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _yukle(izinli_aglar: str):
    import os

    os.environ["IZINLI_AGLAR"] = izinli_aglar
    if "app" in sys.modules:
        importlib.reload(sys.modules["app"])
        return sys.modules["app"]
    import app

    return app


def test_lan_adresi_izinli():
    app = _yukle("192.168.23.0/24,127.0.0.1/32,::1/128")
    assert app._adres_izinli_mi("192.168.23.245") is True
    assert app._adres_izinli_mi("127.0.0.1") is True
    assert app._adres_izinli_mi("::1") is True


def test_lan_disi_adres_reddedilir():
    app = _yukle("192.168.23.0/24,127.0.0.1/32,::1/128")
    assert app._adres_izinli_mi("10.0.0.5") is False
    assert app._adres_izinli_mi("8.8.8.8") is False
    assert app._adres_izinli_mi(None) is False


def test_gecersiz_adres_reddedilir():
    app = _yukle("192.168.23.0/24")
    assert app._adres_izinli_mi("testclient") is False
    assert app._adres_izinli_mi("") is False
