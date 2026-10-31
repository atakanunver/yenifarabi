"""logger.py - Sınıf Arenası Kalıcı Loglama ve Hata Takip Motoru.

Loglar /home/ata/arenasinif/logs/ altında toplanır:
- arena.log: Tüm erişimler, IP'ler, sınıf/ders eşleşmeleri, AI soru üretim süreleri.
- arena_hata.log: Yalnızca sunucu ve akıllı tahta tarayıcısından gelen hatalar.
RotatingFileHandler ile 10MB x 5 dosya sınırıyla disk şişmesini engeller.
"""

import logging
import os
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
# Testler/geliştirme için: ARENA_LOG_DIZINI ortam değişkeni log klasörünü değiştirir.
LOG_DIR = Path(os.environ.get("ARENA_LOG_DIZINI") or (BASE_DIR / "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

ARENA_LOG_PATH = LOG_DIR / "arena.log"
HATA_LOG_PATH = LOG_DIR / "arena_hata.log"

# Ana logger yapılandırması
logger = logging.getLogger("arena")
logger.setLevel(logging.INFO)
logger.propagate = False

# Konsol formatlayıcı
c_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Dosya formatlayıcı (daha ayrıntılı)
f_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Konsol handler
if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(c_formatter)
    logger.addHandler(ch)

# 1. Genel Log Dosyası (arena.log - 10MB x 5)
if not any(getattr(h, "baseFilename", "") == str(ARENA_LOG_PATH) for h in logger.handlers):
    fh_all = RotatingFileHandler(
        ARENA_LOG_PATH,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh_all.setLevel(logging.INFO)
    fh_all.setFormatter(f_formatter)
    logger.addHandler(fh_all)

# 2. Yalnızca Hatalar Dosyası (arena_hata.log - 10MB x 5)
if not any(getattr(h, "baseFilename", "") == str(HATA_LOG_PATH) for h in logger.handlers):
    fh_err = RotatingFileHandler(
        HATA_LOG_PATH,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh_err.setLevel(logging.WARNING)
    fh_err.setFormatter(f_formatter)
    logger.addHandler(fh_err)


def log_oturum(ip: str, sinif: str, ders_no: int, ders_adi: str, mevcut: int, devamsiz: int) -> None:
    logger.info(
        f"[OTURUM] IP: {ip} | Sınıf: {sinif} | {ders_no}. Ders: {ders_adi} | "
        f"Mevcut: {mevcut} | Devamsız: {devamsiz}"
    )


def log_olay(olay: str, detay: str) -> None:
    """Genel olay log kaydı (Fetih hamleleri, oturumlar vb.)."""
    logger.info(f"[{olay}] {detay}")


def log_takim_yenile(ip: str, sinif: str, ders: str, takim_sayisi: int, takimlar: list[dict[str, Any]]) -> None:
    isimler = ", ".join(t.get("name", "") for t in takimlar)
    logger.info(
        f"[TAKIM_YENILE] IP: {ip} | Sınıf: {sinif} | Ders: {ders} | "
        f"{takim_sayisi} Takım ({isimler})"
    )


def log_soru_uret(
    ip: str,
    sinif: str,
    ders: str,
    konu: str,
    kaynak: str,
    sure_sn: float,
    durum: str,
    hata: str = "",
) -> None:
    msg = (
        f"[SORU_URET] IP: {ip} | Sınıf: {sinif} | Ders: {ders} | "
        f"Konu: '{konu}' | Kaynak: {kaynak} | Süre: {sure_sn:.1f}sn | Durum: {durum}"
    )
    if hata:
        msg += f" | Hata: {hata}"
        logger.warning(msg)
    else:
        logger.info(msg)


def log_istemci_hata(
    ip: str,
    mesaj: str,
    kaynak_url: str = "",
    satir: int = 0,
    sutun: int = 0,
    stack: str = "",
    user_agent: str = "",
) -> None:
    logger.error(
        f"[ISTEMCI_HATA] IP: {ip} | Mesaj: {mesaj} | Konum: {kaynak_url}:{satir}:{sutun} | "
        f"UA: {user_agent} | Stack: {stack}"
    )


def log_hata(nerede: str, mesaj: str, exc: Exception | None = None) -> None:
    if exc:
        tb = traceback.format_exc()
        logger.error(f"[SUNUCU_HATA] {nerede}: {mesaj} | İstisna: {exc}\n{tb}")
    else:
        logger.error(f"[SUNUCU_HATA] {nerede}: {mesaj}")


def son_loglari_getir(limit: int = 50, sadece_hata: bool = False) -> list[str]:
    """Son n satır log kaydını okur."""
    hedef_dosya = HATA_LOG_PATH if sadece_hata else ARENA_LOG_PATH
    if not hedef_dosya.exists():
        return []
    try:
        satirlar = hedef_dosya.read_text(encoding="utf-8").splitlines()
        return satirlar[-limit:]
    except Exception as e:
        logger.warning(f"Log okunamadı: {e}")
        return []
