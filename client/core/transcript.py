"""
core/transcript.py — Ders konuşma kaydı (ders-başına düz metin dosyası)

Sınıfta konuşulanlar iki yerde tutulur:
  1. Ekrandaki DERS KAYDI paneli — anlık, geçici
  2. Bu modül — logs/ders/<derslik>_<oturum-zamanı>.txt, kalıcı, tahtanın
     kendi diskinde

2026-08-12'ye kadar tek dosya GÜNLÜKTÜ (YYYY-AA-GG.txt) — aynı gün birden
fazla ders aynı dosyaya karışıyordu. Artık DERS-BAŞINA ayrı dosya: tahta
açılışında (uygulama süreci başlarken) bir dosya adı BİR KEZ hesaplanıp
süreç ömrü boyunca önbelleğe alınıyor (`_OTURUM_YOLU`) — Gemini Live
bağlantısı ara sıra kopup yeniden kurulsa bile (log_session_start/end bunun
için çağrılır) AYNI dosyaya yazılmaya devam edilir, ders parçalanmaz. Yeni
`actions/ders_hafizasi.py` aracı bu dosyaları geçmiş ders özetini hatırlamak
için okur — TEK kaynak, iki farklı kullanım (ders kaydı + hafıza aracı).

Ders/konu çerçevesi dosya AÇILIRKEN çoğu zaman henüz bilinmez (öğretmen
henüz söylemedi) — bu yüzden dosya ADINDA değil, `log_frame()` ile dosyanın
İÇİNE "ÇERÇEVE: ders=… konu=…" satırı olarak yazılır; `ders_hafizasi.py` bu
satırı arayarak hangi dosyanın hangi konuyla ilgili olduğunu çözer.

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
import re
import threading
from datetime import datetime
from pathlib import Path

from core import tahta

BASE_DIR = Path(__file__).resolve().parent.parent
# core/logger.py'deki FARABI_LOG_DIR ile AYNI gerekçe, ayrı bir değişken:
# testler gerçek ders kaydını kirletmesin. tests/conftest.py yalnızca tanı
# logunu (farabi.log) yönlendiriyordu; bu dosya kendi başına savunmasızdı —
# transcript.log_line() çağıran bir test, monkeypatch'lenmezse doğrudan
# logs/ders/<bugün>.txt'ye yazardı.
LOG_DIR = Path(os.environ.get("FARABI_DERS_LOG_DIR") or (BASE_DIR / "logs" / "ders"))
_lock = threading.Lock()
_oturum_yolu: Path | None = None

_GUVENSIZ_KARAKTER = re.compile(r"[^A-Za-z0-9ÇĞİÖŞÜçğıöşü_-]+")


def _oturum_dosya_adi() -> str:
    derslik = _GUVENSIZ_KARAKTER.sub("-", tahta.derslik().strip()) or "bilinmeyen-derslik"
    return f"{datetime.now():%Y-%m-%d_%H-%M-%S}_{derslik}.txt"


def _oturum_yolunu_al() -> Path:
    """Süreç ömrü boyunca AYNI dosya yolunu döner — ilk çağrıda hesaplanır."""
    global _oturum_yolu
    if _oturum_yolu is None:
        _oturum_yolu = LOG_DIR / _oturum_dosya_adi()
    return _oturum_yolu


def _ensure_header(path: Path) -> None:
    """Dosya yeni açıldıysa başlık yaz."""
    if path.exists() and path.stat().st_size > 0:
        return
    path.write_text(
        f"# Farabi ders kaydı — {datetime.now():%d.%m.%Y %H:%M}\n"
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
            path = _oturum_yolunu_al()
            _ensure_header(path)
            with path.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%H:%M:%S}  {etiket}  {text}\n")
    except Exception as e:
        print(f"[Transkript] Yazılamadı: {e}")


def log_session_start() -> None:
    log_line("sistem", "— Oturum başladı —")


def log_session_end() -> None:
    log_line("sistem", "— Oturum bitti —")


def log_frame(ders: str, konu: str) -> None:
    """Ders/konu çerçevesi öğretmenden gelince çağrılır — `ders_hafizasi.py`
    bu satırı arayarak dosyanın hangi konuyla ilgili olduğunu çözer."""
    log_line("sistem", f"ÇERÇEVE: ders={ders or '?'} konu={konu or '?'}")


def session_file() -> Path:
    """Bu oturumun ders kaydı dosyasının yolu."""
    return _oturum_yolunu_al()
