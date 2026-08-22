"""
actions/ekrandaki_soruyu_oku.py — Tahtadaki sorunun görüntüsünü yakalar ve OCR/AI ile çözer/açıklar.
"""

import threading
from actions.file_processor import file_processor


def ekrandaki_soruyu_oku(parameters: dict | None = None, player=None, speak=None, **_) -> str:
    log = getattr(player, "write_log", None) or (lambda *_a: None)
    p = parameters or {}
    talimat = p.get("talimat") or "Ekrandaki soruyu oku, çözümünü yap ve açıkla."

    if player is None or not hasattr(player, "_win"):
        return "Ekran görüntüsü okuma arayüzü şu an hazır değil, efendim."

    log("[Ekran Soru Oku] Ekran yakalanıyor…")
    
    # GUI operasyonları için ana thread ile senkronizasyon nesneleri
    ctx = {"event": threading.Event(), "path": ""}
    
    try:
        # Sinyali tetikle
        player._win._screenshot_sig.emit(ctx)
        # GUI thread'inin ekran görüntüsünü alıp kaydetmesini bekle (max 5 saniye)
        if not (ctx["event"].wait(timeout=5.0) and ctx["path"]):
            log("[Ekran Soru Oku] Ekran yakalanamadı.")
            return "Ekran görüntüsü alınamadığı için soruyu okuyamadım, efendim."
            
        yol = ctx["path"]
        log(f"[Ekran Soru Oku] Ekran yakalandı: {yol}. Soruyu okumak için sunucuya gönderiliyor…")
        
        # Dosya işleyiciyi çağır
        fp_params = {
            "file_path": yol,
            "action": "ocr",
            "instruction": talimat
        }
        
        return file_processor(fp_params, player=player, speak=speak)
        
    except Exception as e:
        log(f"[Ekran Soru Oku] Hata: {e}")
        return f"Ekrandaki soru okunurken bir hata oluştu: {e}"
