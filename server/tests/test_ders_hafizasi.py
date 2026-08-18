"""
server/ders_hafizasi.py — geçmiş ders kaydını hatırlama, ağsız/dosya-tabanlı
test.

client/tests/test_ders_hafizasi.py'den taşındı (2026-08-18, server-taşıma) —
eşleştirme mantığı artık burada yaşıyor, client yalnızca ince bir HTTP
istemcisi (bkz. actions/ders_hafizasi.py'nin modül dokümanı). Davranış
BİREBİR korunur, yalnızca kaynak `transcript.LOG_DIR` yerine
`ders_hafizasi.YEDEK_DIR/<derslik>/` oldu ve "süren oturum" artık client'ın
bildirdiği `guncel_dosya` adıyla hariç tutuluyor (eskiden
`transcript.session_file()` doğrudan karşılaştırılıyordu).

Her test kendi İZOLE dizinini kullanır (`izole_dizin` fixture'ı) — testler
arasında sentetik dosya sızıntısı olmasın diye.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ders_hafizasi as dh  # noqa: E402


@pytest.fixture
def izole_dizin(monkeypatch, tmp_path):
    monkeypatch.setattr(dh, "YEDEK_DIR", tmp_path)
    return tmp_path


def _gecmis_dosya_yaz(derslik_dizin: Path, ad: str, icerik: str) -> Path:
    derslik_dizin.mkdir(parents=True, exist_ok=True)
    yol = derslik_dizin / ad
    yol.write_text(icerik, encoding="utf-8")
    return yol


def test_konu_verilince_dogru_gecmis_ders_eslesir(izole_dizin):
    d = izole_dizin / "10-A"
    _gecmis_dosya_yaz(
        d, "2019-01-01_09-00-00_10-A.txt",
        "# Farabi ders kaydı — 01.01.2019 09:00\n"
        "------------------------------------------------------------\n"
        "09:00:05  SİSTEM   ÇERÇEVE: ders=Biyoloji konu=Hücre zarı\n"
        "09:00:10  FARABİ   Hücre zarı fosfolipit çift tabakasından oluşur.\n",
    )
    _gecmis_dosya_yaz(
        d, "2019-01-02_10-00-00_10-A.txt",
        "# Farabi ders kaydı — 02.01.2019 10:00\n"
        "------------------------------------------------------------\n"
        "10:00:05  SİSTEM   ÇERÇEVE: ders=Matematik konu=Türev\n"
        "10:00:10  FARABİ   Türev anlık değişim hızıdır.\n",
    )
    sonuc = dh.ders_hafizasi(dh.HafizaIstek(derslik="10-A", konu="hücre zarı"))["metin"]
    assert "Biyoloji" in sonuc
    assert "fosfolipit" in sonuc
    assert "Türev" not in sonuc


def test_konu_verilmezse_en_son_gecmis_ders_doner(izole_dizin):
    d = izole_dizin / "10-A"
    _gecmis_dosya_yaz(
        d, "2018-01-01_09-00-00_10-A.txt",
        "# Farabi ders kaydı — 01.01.2018 09:00\n"
        "------------------------------------------------------------\n"
        "09:00:05  SİSTEM   ÇERÇEVE: ders=Kimya konu=Asitler\n"
        "09:00:10  FARABİ   Asitler suda H+ iyonu verir.\n",
    )
    _gecmis_dosya_yaz(
        d, "2018-06-01_09-00-00_10-A.txt",
        "# Farabi ders kaydı — 01.06.2018 09:00\n"
        "------------------------------------------------------------\n"
        "09:00:05  SİSTEM   ÇERÇEVE: ders=Fizik konu=Newton yasaları\n"
        "09:00:10  FARABİ   Cisimler net kuvvet olmadıkça hareketini korur.\n",
    )
    sonuc = dh.ders_hafizasi(dh.HafizaIstek(derslik="10-A"))["metin"]
    assert "Fizik" in sonuc
    assert "Newton" in sonuc
    assert "Asitler" not in sonuc


def test_suren_oturum_kendi_kendini_hatirlamaz(izole_dizin):
    d = izole_dizin / "10-A"
    _gecmis_dosya_yaz(
        d, "2017-01-01_09-00-00_10-A.txt",
        "# Farabi ders kaydı — 01.01.2017 09:00\n"
        "------------------------------------------------------------\n"
        "09:00:05  SİSTEM   ÇERÇEVE: ders=Tarih konu=Kurtuluş Savaşı\n"
        "09:00:10  FARABİ   Kurtuluş Savaşı 1919'da başladı.\n",
    )
    guncel_ad = "2017-06-01_09-00-00_10-A.txt"
    _gecmis_dosya_yaz(d, guncel_ad, "gizli-suren-oturum-imi-x7q9")
    sonuc = dh.ders_hafizasi(dh.HafizaIstek(derslik="10-A", guncel_dosya=guncel_ad))["metin"]
    assert guncel_ad not in sonuc
    assert "gizli-suren-oturum-imi-x7q9" not in sonuc


def test_gecmis_kayit_yokken_uydurmadan_mesaj_doner(izole_dizin):
    sonuc = dh.ders_hafizasi(dh.HafizaIstek(derslik="10-A", konu="herhangi bir şey"))["metin"]
    assert "bulamadım" in sonuc or "yok" in sonuc


def test_eslesmeyen_konu_uydurmadan_mesaj_doner(izole_dizin):
    d = izole_dizin / "10-A"
    _gecmis_dosya_yaz(
        d, "2016-01-01_09-00-00_10-A.txt",
        "# Farabi ders kaydı — 01.01.2016 09:00\n"
        "------------------------------------------------------------\n"
        "09:00:05  SİSTEM   ÇERÇEVE: ders=Biyoloji konu=Hücre zarı\n"
        "09:00:10  FARABİ   Hücre zarı fosfolipit çift tabakasından oluşur.\n",
    )
    sonuc = dh.ders_hafizasi(
        dh.HafizaIstek(derslik="10-A", konu="kuantum tünelleme çok garip bir sorgu")
    )["metin"]
    assert "bulamadım" in sonuc


def test_gecersiz_derslik_path_traversal_reddedilir(izole_dizin):
    with pytest.raises(Exception):
        dh.ders_hafizasi(dh.HafizaIstek(derslik=".."))
