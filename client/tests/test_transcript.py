"""
core/transcript.py — ders kaydı satırları.

tests/conftest.py, FARABI_DERS_LOG_DIR'ı geçici bir dizine yönlendiriyor;
burada yazılan hiçbir şey gerçek logs/ders/ dizinine gitmez.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import transcript  # noqa: E402


def test_ogretmen_etiketi_ayri_ve_dogru():
    transcript.log_line("ogretmen", "Cevabı göster.")
    metin = transcript.session_file().read_text(encoding="utf-8")
    assert "ÖĞRETMEN  Cevabı göster." in metin


def test_dort_etiket_de_dogru_yazilir():
    transcript.log_line("ogrenci", "test-öğrenci-satırı")
    transcript.log_line("farabi", "test-farabi-satırı")
    transcript.log_line("ogretmen", "test-öğretmen-satırı")
    transcript.log_line("sistem", "test-sistem-satırı")
    metin = transcript.session_file().read_text(encoding="utf-8")
    assert "ÖĞRENCİ  test-öğrenci-satırı" in metin
    assert "FARABİ   test-farabi-satırı" in metin
    assert "ÖĞRETMEN  test-öğretmen-satırı" in metin
    assert "SİSTEM   test-sistem-satırı" in metin


def test_bos_metin_yazilmaz():
    onceki = transcript.session_file().read_text(encoding="utf-8") if transcript.session_file().exists() else ""
    transcript.log_line("ogretmen", "   ")
    sonraki = transcript.session_file().read_text(encoding="utf-8") if transcript.session_file().exists() else ""
    assert onceki == sonraki


def test_yazma_gerceklen_izole_test_dizinine_gidiyor():
    """Gerçek logs/ders/ dizinini KİRLETMEDİĞİMİZİ doğrular."""
    import os
    assert os.environ.get("FARABI_DERS_LOG_DIR"), "conftest.py bu değişkeni ayarlamış olmalı"
    assert str(transcript.LOG_DIR) == os.environ["FARABI_DERS_LOG_DIR"]
    gercek_dizin = Path(__file__).resolve().parent.parent / "logs" / "ders"
    assert transcript.LOG_DIR != gercek_dizin


def test_yeni_oturum_baslat_yeni_dosya_uretir():
    """main.py'nin _DersBitti akışı: ders bitince süreç yaşamaya devam
    ediyor, bir sonraki ders AYNI süreçte başlıyor — yeni_oturum_baslat()
    olmadan ikinci ders birinci dersin dosyasına yazardı."""
    eski_yol = transcript.session_file()
    transcript.yeni_oturum_baslat()
    yeni_yol = transcript.session_file()
    assert eski_yol != yeni_yol
    # Sıfırlama sonrası yazma da doğru (yeni) dosyaya gidiyor mu?
    transcript.log_line("sistem", "test-yeni-oturum-satırı")
    assert "test-yeni-oturum-satırı" in yeni_yol.read_text(encoding="utf-8")


def test_yeni_oturum_baslat_hicbir_yazma_olmadan_da_calisir():
    """Süreç ömrü boyunca hiç log_line() çağrılmamışken (_oturum_yolu hâlâ
    None) yeni_oturum_baslat() çağrılırsa çökmemeli."""
    transcript.yeni_oturum_baslat()
    transcript.yeni_oturum_baslat()  # ard arda iki kez de güvenli olmalı
