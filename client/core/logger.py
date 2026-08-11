"""
core/logger.py — FARABİ ortak günlük (log) sistemi
==================================================

Tüm modüllerin kullanabileceği, dosyaya yazan basit bir logger sağlar.
Log dosyası:  <proje kökü>/logs/farabi.log   (otomatik döner: 5 x 1 MB)

Kullanım:
    from core.logger import get_logger
    log = get_logger("web_search")
    log.info("bir şey oldu")
    log.exception("hata yakalandı")   # otomatik traceback yazar
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # core/ klasörünün bir üstü = proje kökü
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()

# Testler ve betikler tanı logunu KİRLETMEMELİ. `logs/farabi.log` sınıfta ne
# olduğunu anlamak için okunuyor; içine pytest çalıştırmalarının ürettiği
# "Ders adımı: BEKLIYOR → YOKLAMA" satırları karışınca gerçek oturumun izi
# kayboluyor. FARABI_LOG_DIR verilirse log oraya yazılır.
LOG_DIR  = Path(os.environ.get("FARABI_LOG_DIR") or (BASE_DIR / "logs"))
LOG_FILE = LOG_DIR / "farabi.log"

_CONFIGURED = False


def _configure_root() -> None:
    """Kök logger'a dosya + konsol handler'larını bir kez ekler."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)-14s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger("farabi")
    root.setLevel(logging.DEBUG)
    root.propagate = False

    # Dosyaya yaz (5 dosya x 1 MB dönerli)
    fh = RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Konsola da yaz (INFO ve üstü)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    root.info("=" * 60)
    root.info("FARABİ log sistemi başlatıldı → %s", LOG_FILE)
    _CONFIGURED = True


def get_logger(name: str = "app") -> logging.Logger:
    """İsimlendirilmiş bir alt-logger döndürür (farabi.<name>)."""
    _configure_root()
    return logging.getLogger(f"farabi.{name}")


def log_path() -> str:
    """Log dosyasının tam yolunu döndürür (kullanıcıya göstermek için)."""
    return str(LOG_FILE)
