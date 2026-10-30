#!/usr/bin/env python3
"""announcement_agent.py — tahtada sağ altta açılan MSN tarzı duyuru penceresi (2026-10-30).

Sunucu tarafı: dashboard/duyuru.py. Duyuruyu `tahta_istemci.py` sunucudan çeker ve bu
betiği her duyuru için ayrı süreç olarak başlatır:

    python announcement_agent.py --goster '{"id":7,"mesaj":"...","tip":"idare",...}'
    python announcement_agent.py --test      # sunucusuz deneme penceresi

Neden ayrı süreç: yoklama.py ve tahta_istemci.py duyuru penceresi çökse bile etkilenmez
(Farabi dersi bozmaz). Socket.IO kullanılmaz; iletim istemcinin HTTP sorgusudur.

Pencere dersi bölmez: odak ÇALMAZ (WindowDoesNotAcceptFocus + ShowWithoutActivating,
X11'de pencere yöneticisini atlar = tkinter `overrideredirect`), her zaman üstte, 350x150.
Tipler:
  bilgi = mavi, sessiz, 10 sn
  idare = sarı, ding + 1 kez sesli okuma, 15 sn
  acil  = kırmızı yanıp sönen, ding + 3 kez sesli okuma, elle kapatılana kadar durur
Ses: wav dosyası (sunucudaki TTS üretir) `paplay`/`aplay` ile çalınır; çalınamazsa pencere
yine görünür. Gereken: PyQt6 (yoklama venv'inde zaten var), ek paket yok.
"""

import argparse
import atexit
import json
import logging
import logging.handlers
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DUYURU_DIR = BASE_DIR / "data" / ".duyuru"
DING = BASE_DIR / "assets" / "ding.wav"

GENISLIK, YUKSEKLIK, KENAR_BOSLUK = 350, 150, 16
# tip -> (başlık, zemin, yazı, sure_sn (0 = elle kapanır), okuma sayısı)
TIPLER = {
    "bilgi": ("Duyuru", "#1e66d0", "#ffffff", 10, 0),
    "idare": ("İdare duyurusu", "#f5c518", "#2b2200", 15, 1),
    "acil": ("ACİL DUYURU", "#d00000", "#ffffff", 0, 3),
}
ACIL_SONUK_ZEMIN = "#6e0000"

# Ses çalar adayları (Pardus/Cinnamon'da paplay genelde vardır).
CALARLAR = (["paplay"], ["aplay", "-q"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"])

log = logging.getLogger("duyuru")


def log_kur() -> None:
    log.setLevel(logging.INFO)
    bicim = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    akim = logging.StreamHandler(sys.stderr)
    akim.setFormatter(bicim)
    log.addHandler(akim)
    try:
        DUYURU_DIR.mkdir(parents=True, exist_ok=True)
        dosya = logging.handlers.RotatingFileHandler(
            DUYURU_DIR / "agent.log", maxBytes=100_000, backupCount=1, encoding="utf-8")
        dosya.setFormatter(bicim)
        log.addHandler(dosya)
    except OSError:
        pass  # günlük dosyası yazılamıyorsa yalnız stderr


def cal(yol: Path) -> bool:
    """Wav dosyasını bloklayarak çalar; çalar yoksa/hata olursa False (çökmez)."""
    if not yol.is_file():
        log.warning("ses dosyasi yok: %s", yol.name)
        return False
    for komut in CALARLAR:
        if shutil.which(komut[0]):
            try:
                subprocess.run(komut + [str(yol)], timeout=120, check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except (subprocess.SubprocessError, OSError) as e:
                log.warning("ses calinamadi (%s): %r", komut[0], e)
                return False
    log.warning("ses calar bulunamadi (paplay/aplay/ffplay)")
    return False


def sesli_okuma(veri: dict, okuma: int) -> None:
    """Önce ding, sonra TTS wav'ı `okuma` kez. Ayrı iş parçacığında (arayüzü bloklamaz)."""
    try:
        cal(DING)
        ses = veri.get("ses_dosya")
        if not ses:
            log.info("sesli okuma icin ses dosyasi yok; yalniz ding")
            return
        for _ in range(okuma):
            if not cal(Path(ses)):
                break
    except Exception as e:  # noqa: BLE001 — ses hatası pencereyi etkilememeli
        log.warning("sesli okuma hatasi: %r", e)


def _canli_pid(pid_dosyasi: Path) -> bool:
    try:
        pid = int(pid_dosyasi.read_text().strip())
        return "announcement_agent" in Path(f"/proc/{pid}/cmdline").read_text()
    except (OSError, ValueError):
        return False


def pid_kaydet(duyuru_id) -> int:
    """Aynı id ikinci kez açılmasın; kaç pencere açık olduğunu döndürür (üst üste binmesin)."""
    DUYURU_DIR.mkdir(parents=True, exist_ok=True)
    acik = [p for p in DUYURU_DIR.glob("*.pid") if _canli_pid(p)]
    if duyuru_id is not None:
        benim = DUYURU_DIR / f"{duyuru_id}.pid"
        if benim in acik:
            log.info("duyuru %s zaten acik", duyuru_id)
            sys.exit(0)
        benim.write_text(str(os.getpid()))
        atexit.register(lambda: benim.unlink(missing_ok=True))
    return len(acik)


def pencere_goster(veri: dict, sira: int) -> int:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

    tip = veri.get("tip") if veri.get("tip") in TIPLER else "bilgi"
    baslik, zemin, yazi, varsayilan_sure, varsayilan_okuma = TIPLER[tip]
    sure = int(veri.get("sure_sn", varsayilan_sure))
    okuma = int(veri.get("okuma_sayisi", varsayilan_okuma))

    uygulama = QApplication(sys.argv[:1])
    pencere = QWidget()
    # X11BypassWindowManagerHint = tkinter overrideredirect karşılığı: pencere yöneticisi
    # devreye girmez, odak ve etkin pencere değişmez.
    pencere.setWindowFlags(
        Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus
        | Qt.WindowType.X11BypassWindowManagerHint)
    pencere.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    pencere.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    pencere.resize(GENISLIK, YUKSEKLIK)

    def stil(arka: str) -> None:
        pencere.setStyleSheet(
            f"QWidget {{ background: {arka}; color: {yazi}; }}"
            f"QPushButton {{ background: rgba(0,0,0,60); color: {yazi}; border: 0; padding: 4px 12px; }}")

    stil(zemin)
    ust = QLabel(baslik)
    ust.setStyleSheet("font-weight: bold; font-size: 11pt;")
    mesaj = QLabel(str(veri.get("mesaj", "")))
    mesaj.setWordWrap(True)
    mesaj.setStyleSheet("font-size: 13pt;")
    mesaj.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    kapat = QPushButton("Kapat")
    kapat.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    kapat.clicked.connect(uygulama.quit)
    alt = QHBoxLayout()
    alt.addStretch(1)
    alt.addWidget(kapat)
    yerlesim = QVBoxLayout(pencere)
    yerlesim.addWidget(ust)
    yerlesim.addWidget(mesaj, 1)
    yerlesim.addLayout(alt)

    ekran = QGuiApplication.primaryScreen().availableGeometry()
    pencere.move(ekran.right() - GENISLIK - KENAR_BOSLUK,
                 ekran.bottom() - YUKSEKLIK - KENAR_BOSLUK - sira * (YUKSEKLIK + 10))
    pencere.show()

    # Başka pencere önüne geçerse yeniden üste al (override-redirect penceresi için yeterli).
    ust_zamanlayici = QTimer()
    ust_zamanlayici.timeout.connect(pencere.raise_)
    ust_zamanlayici.start(2000)

    if tip == "acil":
        sonuk = [False]

        def yanip_son() -> None:
            sonuk[0] = not sonuk[0]
            stil(ACIL_SONUK_ZEMIN if sonuk[0] else zemin)

        yanip = QTimer()
        yanip.timeout.connect(yanip_son)
        yanip.start(500)
    if sure > 0:
        QTimer.singleShot(sure * 1000, uygulama.quit)

    if tip != "bilgi" and veri.get("sesli_oku"):
        threading.Thread(target=sesli_okuma, args=(veri, okuma), daemon=True).start()
    return uygulama.exec()


def main() -> int:
    ap = argparse.ArgumentParser(description="Tahta duyuru penceresi")
    ap.add_argument("--goster", help="duyuru JSON'u (tahta_istemci verir)")
    ap.add_argument("--test", action="store_true", help="sunucusuz deneme duyurusu")
    args = ap.parse_args()
    log_kur()
    try:
        if args.test:
            veri = {"hedef": "9-A", "mesaj": "9-A Ali Yılmaz idareye", "tip": "idare",
                    "sesli_oku": True}
        elif args.goster:
            veri = json.loads(args.goster)
            if not isinstance(veri, dict):
                raise ValueError("JSON nesnesi bekleniyor")
        else:
            ap.error("--goster ya da --test gerekli")
        sira = pid_kaydet(veri.get("id"))
        log.info("duyuru aciliyor: id=%s tip=%s", veri.get("id"), veri.get("tip"))
        return pencere_goster(veri, sira)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — ajan hiçbir durumda yoklama/istemciyi düşürmemeli
        log.error("duyuru penceresi acilamadi: %r", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
