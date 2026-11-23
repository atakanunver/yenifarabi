"""Telegram bildirimi (Bot API sendMessage). Yalnız SABİT metin gönderilir: Telegram bulut, öğrenci/veli verisi gitmez.

Kablolu hattan doğrudan çıkar (trust_env=False: Wi-Fi proxy kullanılmaz). Hata asıl işlemi bozmaz.
"""

import logging

import httpx
from ayarlar import AYAR

log = logging.getLogger("okul.telegram")


def gonder(metin: str) -> int:
    """AYAR.telegram_sohbet'teki (virgüllü) her sohbete gönderir; başarılı gönderim sayısını döner. Ayar boşsa 0."""
    if not AYAR.telegram_token or not AYAR.telegram_sohbet:
        return 0
    url = f"https://api.telegram.org/bot{AYAR.telegram_token}/sendMessage"
    basarili = 0
    for sohbet in (s.strip() for s in AYAR.telegram_sohbet.split(",")):
        if not sohbet:
            continue
        try:
            r = httpx.post(url, json={"chat_id": sohbet, "text": metin}, timeout=5, trust_env=False)
            if r.status_code == 200:
                basarili += 1
            else:
                log.warning("telegram gönderilemedi: HTTP %s", r.status_code)
        except httpx.HTTPError as e:
            log.warning("telegram gönderilemedi: %s", type(e).__name__)  # jeton URL'de: ham hata loglanmaz
    return basarili
