"""
core/transcript.py — Ders konuşma kaydı (günlük düz metin dosyası)

Sınıfta konuşulanlar iki yerde tutulur:
  1. Ekrandaki DERS KAYDI paneli — anlık, geçici
  2. Bu modül — logs/ders/YYYY-AA-GG.txt, kalıcı, tahtanın kendi diskinde

KVKK notu: burada yalnızca METİN tutulur, ham ses ASLA kaydedilmez.
Öğrenci kimliği yazılmaz — sınıfta kimin konuştuğu bilinmediği için sesli
gelen her şey ÖĞRENCİ etiketiyle geçer. ÖĞRETMEN yalnızca YAZILI (panel
düğmesi / giriş kutusu) talimatlar için kullanılır — bu ikisi karıştırılmaz,
çünkü core/prompt.txt'nin ÖĞRETMEN KOMUTLARI kuralı yalnızca yazılı gelen
metne pedagojik varsayılanların üstünde davranır (bkz. main.py
`_on_teacher_command`). Bu satır olmadan bir dersi sonradan incelemek —
Farabi neden öyle davrandı diye — modelin kendi çıktısını görüp
GİRDİYİ (öğretmenin ne yazdığını) hiç görememek demekti.
"""

import os
import threading
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# core/logger.py'deki FARABI_LOG_DIR ile AYNI gerekçe, ayrı bir değişken:
# testler gerçek ders kaydını kirletmesin. tests/conftest.py yalnızca tanı
# logunu (farabi.log) yönlendiriyordu; bu dosya kendi başına savunmasızdı —
# transcript.log_line() çağıran bir test, monkeypatch'lenmezse doğrudan
# logs/ders/<bugün>.txt'ye yazardı.
LOG_DIR    = Path(os.environ.get("FARABI_DERS_LOG_DIR") or (BASE_DIR / "logs" / "ders"))
_lock      = threading.Lock()
_last_date = None


def _today_path() -> Path:
    return LOG_DIR / f"{datetime.now():%Y-%m-%d}.txt"


def _ensure_header(path: Path) -> None:
    """Dosya yeni açıldıysa başlık yaz."""
    if path.exists() and path.stat().st_size > 0:
        return
    path.write_text(
        f"# Farabi ders kaydı — {datetime.now():%d.%m.%Y}\n"
        f"# Yalnızca konuşma metni tutulur; ses kaydı yoktur.\n"
        f"{'-' * 60}\n",
        encoding="utf-8",
    )


def log_line(speaker: str, text: str) -> None:
    """
    Tek bir konuşma satırı ekle.

    speaker: 'ogrenci' | 'farabi' | 'ogretmen' | 'sistem'
    Hata durumunda sessizce vazgeçer — kayıt tutulamıyor diye ders durmamalı.
    """
    text = (text or "").strip()
    if not text:
        return

    etiket = {
        "ogrenci":  "ÖĞRENCİ",
        "farabi":   "FARABİ ",
        "ogretmen": "ÖĞRETMEN",
        "sistem":   "SİSTEM ",
    }.get(speaker, speaker.upper())

    try:
        with _lock:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            path = _today_path()
            _ensure_header(path)
            with path.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%H:%M:%S}  {etiket}  {text}\n")
    except Exception as e:
        print(f"[Transkript] Yazılamadı: {e}")


def log_session_start() -> None:
    log_line("sistem", "— Oturum başladı —")


def log_session_end() -> None:
    log_line("sistem", "— Oturum bitti —")


def today_file() -> Path:
    """O günkü ders kaydı dosyasının yolu."""
    return _today_path()
