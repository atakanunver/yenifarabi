"""
actions/ekrandaki_soruyu_oku.py — Tahtanın KENDİ ekranındaki sorunun
görüntüsünü yakalar (kamera DEĞİL — bkz. ekran_goruntusu_al.py) ve
`file_processor`'ın "ocr" görevi üzerinden (server/dosya.py::_ai_gorsel,
bulut vision) okur/çözer/açıklar.

2026-08-30: `ui.py::_ekran_goruntusu_yakala` eksikti, bu dosya hiçbir şey
yakalayamıyordu (bkz. ekran_goruntusu_al.py'nin aynı notu). `file_processor`
tarafında "ocr" action'ı zaten destekleniyordu (server/dosya.py:104) — bu
dosyanın kendisi eksik değildi, yalnızca çağırdığı ekran-yakalama sinyali
yoktu.
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
