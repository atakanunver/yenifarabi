"""
actions/ekran_goruntusu_al.py — Tahtanın ekran görüntüsünü alır ve loglara ekler.
"""

import threading
from core import transcript


def ekran_goruntusu_al(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    if player is None or not hasattr(player, "_win"):
        return "Ekran görüntüsü alma arayüzü şu an hazır değil, efendim."

    log("[Ekran Görüntüsü] Ekran görüntüsü alınıyor…")
    
    # GUI operasyonları için ana thread ile senkronizasyon nesneleri
    ctx = {"event": threading.Event(), "path": ""}
    
    try:
        # Sinyali tetikle
        player._win._screenshot_sig.emit(ctx)
        # GUI thread'inin ekran görüntüsünü alıp kaydetmesini bekle (max 5 saniye)
        if ctx["event"].wait(timeout=5.0) and ctx["path"]:
            yol = ctx["path"]
            log(f"[Ekran Görüntüsü] Başarıyla kaydedildi: {yol}")
            return f"Ekran görüntüsü başarıyla alındı ve ders loglarına eklendi, efendim."
        else:
            log("[Ekran Görüntüsü] Zaman aşımı veya kaydetme hatası.")
            return "Ekran görüntüsü alınamadı, zaman aşımı oluştu."
    except Exception as e:
        log(f"[Ekran Görüntüsü] Hata: {e}")
        return f"Ekran görüntüsü alınırken bir hata oluştu: {e}"
