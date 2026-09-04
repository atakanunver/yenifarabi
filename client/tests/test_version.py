from core import tahta
from core.version import VERSION, major_version


def test_major_version_strict_semantic_version():
    assert major_version("12.34.56") == 12


def test_auth_headers_include_client_version(monkeypatch):
    monkeypatch.setattr(tahta, "tahta_anahtari", lambda: "test-anahtari")

    assert tahta.auth_headers() == {
        "X-Farabi-Board-Key": "test-anahtari",
        "X-Farabi-Client-Version": VERSION,
    }
