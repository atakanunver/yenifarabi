"""
actions/file_processor.py — Farabi Evrensel Dosya İşleyici.

Server-taşıma (2026-08-14): PDF/docx/xlsx/pptx ayrıştırma ve AI özet/analiz
çağrıları artık BURADA değil, `server/dosya.py`de (multipart upload) —
"client ince kalmalı" (CLAUDE.md Kural 1). Bu dosya yalnızca dosyayı
sunucuya yükler, sonucu döndürür.

Desteklenen türler değişmedi (bkz. server/dosya.py docstring'i).
"""

from pathlib import Path

import requests

from core.tahta import sunucu_url as _sunucu_url

ZAMAN_ASIMI = 60.0  # eski client zaman_asimi=45sn + ağ/upload payı


def file_processor(parameters: dict, player=None, speak=None) -> str:
    log = getattr(player, "write_log", None) or (lambda *_a: None)

    file_path_str = parameters.get("file_path", "").strip()
    if not file_path_str:
        return "Dosya yolu belirtilmedi."

    path = Path(file_path_str)
    if not path.exists():
        return f"Dosya bulunamadı: {file_path_str}"
    if not path.is_file():
        return f"Yol bir dosya değil: {file_path_str}"

    action = (parameters.get("action") or "").lower().strip()
    instruction = parameters.get("instruction", "")

    log_msg = f"[FileProcessor] {path.name} | action={action or 'auto'} | sunucuya gönderiliyor"
    log(log_msg)

    try:
        with open(path, "rb") as f:
            r = requests.post(
                f"{_sunucu_url()}/api/egitim/dosya_isle",
                data={"action": action, "instruction": instruction},
                files={"dosya": (path.name, f)},
                timeout=ZAMAN_ASIMI,
            )
        r.raise_for_status()
        veri = r.json()
    except Exception as e:
        log(f"[FileProcessor] sunucu hatası: {type(e).__name__}: {e}")
        return "Dosya işleme sunucusuna şu an ulaşılamıyor. Dosyayı daha sonra tekrar deneyin."

    durum = veri.get("status")
    if durum == "cok_buyuk":
        return veri.get("sonuc") or "Dosya çok büyük, sunucu işleyemedi."
    if durum == "desteklenmiyor":
        return veri.get("sonuc") or "Desteklenmeyen dosya türü."
    if durum == "hata":
        log(f"[FileProcessor] sunucu 'hata' bildirdi: {veri.get('sonuc')}")
        return veri.get("sonuc") or "Dosya işlenemedi."

    sonuc = veri.get("sonuc") or "Done."
    if veri.get("dosya_url"):
        sonuc += f"\n\nÜretilen dosya sunucuda hazır: {_sunucu_url()}{veri['dosya_url']}"
    return sonuc
