"""Veli giriş kodu — smssistemi /api/arac/kod-sms üzerinden (aynı makine, :8020)."""

import httpx
from ayarlar import AYAR

from kaynaklar import KaynakHatasi


class SmsHatasi(KaynakHatasi):
    pass


def kod_gonder(telefon: str, metin: str) -> None:
    if not AYAR.sms_anahtar:
        raise SmsHatasi(
            "SMS gönderimi henüz ayarlanmamış. Lütfen okulla iletişime geçin."
        )
    try:
        r = httpx.post(
            AYAR.sms_url,
            json={"telefon": telefon, "metin": metin},
            headers={"X-Sms-Arac-Key": AYAR.sms_anahtar},
            timeout=10,
            trust_env=False,
        )
    except httpx.HTTPError as e:
        raise SmsHatasi(
            "SMS servisine şu an ulaşılamıyor. Biraz sonra tekrar deneyin."
        ) from e
    if r.status_code == 429:
        raise SmsHatasi(
            "Bu numaraya az önce kod gönderildi. 1 dakika sonra tekrar deneyin."
        )
    if r.status_code != 200:
        raise SmsHatasi(
            f"SMS gönderilemedi (hata {r.status_code}). Lütfen okulla iletişime geçin."
        )
