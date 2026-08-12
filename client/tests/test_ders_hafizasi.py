"""
actions/ders_hafizasi — geçmiş ders kaydını hatırlama, ağsız/dosya-tabanlı
test. Her test kendi İZOLE `transcript.LOG_DIR`'ını kullanır (`_izole_dizin`
fixture'ı) — testler arasında sentetik dosya sızıntısı olmasın diye; aksi
halde "en son ders" gibi sıralamaya dayalı testler, aynı süreçte çalışan
başka testlerin bıraktığı dosyalardan yanlış sonuç alabilir.
"""

import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from core import transcript                      # noqa: E402
from actions.ders_hafizasi import ders_hafizasi   # noqa: E402


@pytest.fixture
def izole_dizin(monkeypatch, tmp_path):
    """Her test kendi boş logs/ders/ dizinini görür; oturum önbelleği de
    sıfırlanır ki `session_file()` bu yeni dizinde yeniden hesaplansın."""
    monkeypatch.setattr(transcript, "LOG_DIR", tmp_path)
    monkeypatch.setattr(transcript, "_oturum_yolu", None)
    return tmp_path


def _gecmis_dosya_yaz(dizin: Path, ad: str, icerik: str) -> Path:
    dizin.mkdir(parents=True, exist_ok=True)
    yol = dizin / ad
    yol.write_text(icerik, encoding="utf-8")
    return yol


def test_konu_verilince_dogru_gecmis_ders_eslesir(izole_dizin):
    _gecmis_dosya_yaz(
        izole_dizin, "2019-01-01_09-00-00_10-A.txt",
        "# Farabi ders kaydı — 01.01.2019 09:00\n"
        "------------------------------------------------------------\n"
        "09:00:05  SİSTEM   ÇERÇEVE: ders=Biyoloji konu=Hücre zarı\n"
        "09:00:10  FARABİ   Hücre zarı fosfolipit çift tabakasından oluşur.\n",
    )
    _gecmis_dosya_yaz(
        izole_dizin, "2019-01-02_10-00-00_10-A.txt",
        "# Farabi ders kaydı — 02.01.2019 10:00\n"
        "------------------------------------------------------------\n"
        "10:00:05  SİSTEM   ÇERÇEVE: ders=Matematik konu=Türev\n"
        "10:00:10  FARABİ   Türev anlık değişim hızıdır.\n",
    )
    sonuc = ders_hafizasi({"konu": "hücre zarı"})
    assert "Biyoloji" in sonuc
    assert "fosfolipit" in sonuc
    assert "Türev" not in sonuc


def test_konu_verilmezse_en_son_gecmis_ders_doner(izole_dizin):
    _gecmis_dosya_yaz(
        izole_dizin, "2018-01-01_09-00-00_10-A.txt",
        "# Farabi ders kaydı — 01.01.2018 09:00\n"
        "------------------------------------------------------------\n"
        "09:00:05  SİSTEM   ÇERÇEVE: ders=Kimya konu=Asitler\n"
        "09:00:10  FARABİ   Asitler suda H+ iyonu verir.\n",
    )
    _gecmis_dosya_yaz(
        izole_dizin, "2018-06-01_09-00-00_10-A.txt",
        "# Farabi ders kaydı — 01.06.2018 09:00\n"
        "------------------------------------------------------------\n"
        "09:00:05  SİSTEM   ÇERÇEVE: ders=Fizik konu=Newton yasaları\n"
        "09:00:10  FARABİ   Cisimler net kuvvet olmadıkça hareketini korur.\n",
    )
    sonuc = ders_hafizasi({})
    assert "Fizik" in sonuc
    assert "Newton" in sonuc
    assert "Asitler" not in sonuc


def test_suren_oturum_kendi_kendini_hatirlamaz(izole_dizin):
    transcript.log_line("sistem", "gizli-suren-oturum-imi-x7q9")
    _gecmis_dosya_yaz(
        izole_dizin, "2017-01-01_09-00-00_10-A.txt",
        "# Farabi ders kaydı — 01.01.2017 09:00\n"
        "------------------------------------------------------------\n"
        "09:00:05  SİSTEM   ÇERÇEVE: ders=Tarih konu=Kurtuluş Savaşı\n"
        "09:00:10  FARABİ   Kurtuluş Savaşı 1919'da başladı.\n",
    )
    guncel = transcript.session_file()
    sonuc = ders_hafizasi({})
    assert guncel.name not in sonuc
    assert "gizli-suren-oturum-imi-x7q9" not in sonuc


def test_gecmis_kayit_yokken_uydurmadan_mesaj_doner(izole_dizin):
    sonuc = ders_hafizasi({"konu": "herhangi bir şey"})
    assert "bulamadım" in sonuc or "yok" in sonuc


def test_eslesmeyen_konu_uydurmadan_mesaj_doner(izole_dizin):
    _gecmis_dosya_yaz(
        izole_dizin, "2016-01-01_09-00-00_10-A.txt",
        "# Farabi ders kaydı — 01.01.2016 09:00\n"
        "------------------------------------------------------------\n"
        "09:00:05  SİSTEM   ÇERÇEVE: ders=Biyoloji konu=Hücre zarı\n"
        "09:00:10  FARABİ   Hücre zarı fosfolipit çift tabakasından oluşur.\n",
    )
    sonuc = ders_hafizasi({"konu": "kuantum tünelleme çok garip bir sorgu"})
    assert "bulamadım" in sonuc
