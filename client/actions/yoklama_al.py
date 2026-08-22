"""
actions/yoklama_al.py — Tahtanın harici yoklama programını (tahtayoklama/yoklama.py) başlatır.
"""

import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def yoklama_al(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    yoklama_yolu = Path(BASE_DIR).parent / "tahtayoklama" / "yoklama.py"
    if not yoklama_yolu.exists():
        log(f"[Yoklama Al] Yoklama scripti bulunamadı: {yoklama_yolu}")
        return "Yoklama programı bulunamadı, efendim."

    log("[Yoklama Al] Harici yoklama programı başlatılıyor…")
    try:
        # Harici süreci arka planda (non-blocking) başlat
        # sys.executable Farabi'nin kendi venv python'ını gösterir (PyQt6 yüklüdür)
        subprocess.Popen([sys.executable, str(yoklama_yolu)], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL)
        
        log("[Yoklama Al] Yoklama programı başarıyla başlatıldı.")
        return "Yoklama programını ekranda açıyorum, efendim."
    except Exception as e:
        log(f"[Yoklama Al] Başlatma hatası: {e}")
        return f"Yoklama programı başlatılırken bir hata oluştu: {e}"
