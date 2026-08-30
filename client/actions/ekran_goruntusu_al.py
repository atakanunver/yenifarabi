"""
actions/ekran_goruntusu_al.py — Tahtanın KENDİ ekranının görüntüsünü alır ve
ders loglarına ekler. Kamera/webcam DEĞİL — bu tahtada kamera donanımı yok
(2026-08-30 doğrulandı), yalnızca o an ekranda gösterilen şey yakalanır.

2026-08-30: `ui.py::_ekran_goruntusu_yakala` (GUI-thread slot, `_screenshot_sig`
ile tetiklenir) eksikti — bu dosya var ama hiçbir şey yakalamıyordu, kayıt da
BURADAN değil o slot'tan yapılıyor (`transcript.log_line`, GUI thread'inde).
Ayrıca bu tool `actions/kayit.py::ARACLAR`'a hiç kayıtlı değildi, modele hiç
sunulmuyordu.
"""

import threading


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
