"""Öğretmen bir dersi 'yok' olarak kaydettiğinde okul'a (smual.app, port 9090) anlık bildirim.

Dashboard okul.db'yi PAYLAŞMAZ: okul/rotalar/devamsizlik_api.py'yi HTTP ile çağırır
(başlık X-Devamsizlik-Anahtar, anahtar config/devamsizlik_bildirim.json {"anahtar": ...},
gitignore'lu — aynı değer okul/config/gizli.json "devamsizlik_anahtar" alanında durmalı).
Anahtar yok / servis kapalı / zaman aşımı → sessizce hiçbir şey olmaz (Farabi dersi bozmaz,
yoklama kaydı bu çağrıdan BAĞIMSIZ zaten yazılmıştır).
"""

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

AYAR_YOLU = Path(__file__).resolve().parent / "config" / "devamsizlik_bildirim.json"
URL = "http://127.0.0.1:9090/api/devamsizlik-bildir"
ZAMAN_ASIMI_SN = 3

log = logging.getLogger("dashboard.devamsizlik_bildirim")


def _anahtar() -> str:
    try:
        return str(json.loads(AYAR_YOLU.read_text(encoding="utf-8")).get("anahtar") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def bildir(okul_no_listesi: list[int]) -> None:
    """Fire-and-forget: hata asla fırlatılmaz, yoklama kaydını etkilemez."""
    if not okul_no_listesi:
        return
    anahtar = _anahtar()
    if not anahtar:
        return
    govde = json.dumps({"okul_no_listesi": okul_no_listesi}).encode("utf-8")
    istek = urllib.request.Request(
        URL, method="POST", data=govde,
        headers={"X-Devamsizlik-Anahtar": anahtar, "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI_SN)
    except (urllib.error.URLError, OSError, ValueError):  # HTTPError URLError alt sınıfı
        log.warning("devamsızlık bildirimi gönderilemedi (okul'a ulaşılamadı)")
