"""Öğretmen ve yönetici ana ekranlarından Farabi kılavuzuna erişim."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    ("kullanici", "sifre", "sayfa"),
    [("hoca", "hoca-sifre", "/ogretmen"), ("mudur", "mudur-sifre", "/yonetici")],
)
def test_farabi_kilavuzu_ana_ekrandan_acilir(ornek, kullanici, sifre, sayfa):
    from app import app

    with TestClient(app) as istemci:
        giris = istemci.post(
            "/giris", data={"kullanici_adi": kullanici, "sifre": sifre},
            follow_redirects=False,
        )
        assert giris.status_code == 303
        ana = istemci.get(sayfa)
        assert ana.status_code == 200
        assert 'href="/static/farabi-kilavuz.html"' in ana.text
        kilavuz = istemci.get("/static/farabi-kilavuz.html")
        assert kilavuz.status_code == 200
        assert "Farabi öğretmen kullanım kılavuzu" in kilavuz.text
        assert "SORUYU ÇÖZ" in kilavuz.text
