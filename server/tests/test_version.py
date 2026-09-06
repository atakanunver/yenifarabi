import auth
import main
from fastapi.testclient import TestClient
from version import VERSION


def _client(config_path, monkeypatch):
    monkeypatch.setenv("FARABI_AUTH_REQUIRED", "1")
    config_path.write_text(
        '{"board_keys": {"9-A": "test-anahtari"}}', encoding="utf-8"
    )
    monkeypatch.setattr(auth, "CONFIG_PATH", config_path)
    return TestClient(main.app)


def test_version_ayni_major_uyumlu(tmp_path, monkeypatch):
    client = _client(tmp_path / "api_keys.json", monkeypatch)

    response = client.get(
        "/api/version",
        headers={
            "X-Farabi-Board-Key": "test-anahtari",
            "X-Farabi-Client-Version": "0.1.9",
        },
    )

    assert response.status_code == 200
    assert response.json()["server_version"] == VERSION
    assert response.json()["uyari"]


def test_version_farkli_major_reddedilir(tmp_path, monkeypatch):
    client = _client(tmp_path / "api_keys.json", monkeypatch)

    response = client.get(
        "/api/version",
        headers={
            "X-Farabi-Board-Key": "test-anahtari",
            "X-Farabi-Client-Version": "1.0.0",
        },
    )

    assert response.status_code == 426
    assert response.json()["detail"]["server_version"] == VERSION
