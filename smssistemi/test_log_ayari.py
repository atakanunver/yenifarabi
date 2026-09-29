"""app.log_ayarla birim testleri — smssistemi.* INFO logları journal'a düşmeli."""

import logging
import sys

import app


def test_smssistemi_loggeri_info_duzeyinde_ve_stderre_yazar():
    lg = logging.getLogger("smssistemi")
    assert lg.level == logging.INFO
    assert len(lg.handlers) == 1
    assert lg.handlers[0].stream is sys.stderr
    assert logging.getLogger("smssistemi.otomasyon").isEnabledFor(logging.INFO)


def test_iki_kez_cagrilinca_handler_cogalmaz():
    app.log_ayarla()
    app.log_ayarla()
    assert len(logging.getLogger("smssistemi").handlers) == 1


def test_koke_yayilmaz():
    # Kök logger'a yayılsaydı başka biri kökü yapılandırdığında satırlar iki kez basılırdı.
    assert logging.getLogger("smssistemi").propagate is False
