"""
actions/yoklama_al.py — Tahtanın harici, dokunmatik yoklama programını
(tahtayoklama/yoklama.py) açar/çalıştırır.

Farabi'den bağımsız, ayrı bir proje (`tahtayoklama/`, kök CLAUDE.md'de
belgeli) — bu araç yalnızca AÇAR, sonucunu okumaya/ayrıştırmaya çalışmaz;
öğretmenin isteği tam olarak buydu (2026-09-01). Daha önce bir deneme
(aynı dosya adıyla) vardı ama hiç `actions/kayit.py`'ye kaydedilmemiş, ölü/
erişilemez kod olarak 2026-08-31'de silinmişti — bu, CLAUDE.md'nin işaret
ettiği "gerçek bir Arac(...) girdisi ve açık bir kapasite-sınırı kararıyla"
şartını karşılayan, yeniden kaydedilmiş hâli.
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def yoklama_al(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    # 9-A tam klon: <repo>/tahtayoklama; diğer tahtalar sparse-checkout: ~/tahtayoklama
    adaylar = [BASE_DIR.parent / "tahtayoklama", Path.home() / "tahtayoklama"]
    klasor = next((k for k in adaylar if (k / "yoklama.py").exists()), None)
    if klasor is None:
        log(f"[Yoklama Al] Yoklama scripti bulunamadı: {[str(k) for k in adaylar]}")
        return "Yoklama programı bulunamadı, efendim."
    yoklama_yolu = klasor / "yoklama.py"
    # Kendi venv'i varsa onu kullan (9-A dışı); yoksa Farabi venv'i (PyQt6 var).
    python = klasor / "venv" / "bin" / "python"
    python = str(python) if python.exists() else sys.executable

    log("[Yoklama Al] Harici yoklama programı başlatılıyor…")
    try:
        # Arka planda, non-blocking — sonucu okumuyoruz, yalnızca açıyoruz.
        subprocess.Popen(
            [python, str(yoklama_yolu)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log("[Yoklama Al] Yoklama programı başarıyla başlatıldı.")
        return "Yoklama programını ekranda açıyorum, efendim."
    except Exception as e:
        log(f"[Yoklama Al] Başlatma hatası: {e}")
        return f"Yoklama programı başlatılırken bir hata oluştu: {e}"
