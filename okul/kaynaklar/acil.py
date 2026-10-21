"""Acil durum — tahtayoklama dashboard makine API'si (:80, X-Acil-Anahtar). Alarm mantığı orada; burası yalnızca çağırır."""

import httpx
from ayarlar import AYAR

from kaynaklar import KaynakHatasi


class AcilHatasi(KaynakHatasi):
    pass


def _istek(yontem: str, yol: str, govde: dict | None = None, zaman_asimi: float = 45) -> dict:
    # tetikle: zil sireni (siren_sn≈8) + SMS + tahta ekranları sırayla beklenir → uzun zaman aşımı.
    if not AYAR.acil_anahtar:
        raise AcilHatasi("Alarm sistemi bu portalda ayarlanmamış.")
    try:
        r = httpx.request(
            yontem,
            AYAR.acil_url + yol,
            json=govde,
            headers={"X-Acil-Anahtar": AYAR.acil_anahtar},
            timeout=zaman_asimi,
            trust_env=False,
        )
    except httpx.HTTPError as e:
        raise AcilHatasi("Alarm sistemine ulaşılamıyor.") from e
    if r.status_code != 200:
        raise AcilHatasi(f"Alarm sistemi hata verdi ({r.status_code}).")
    try:
        return r.json()
    except ValueError as e:
        raise AcilHatasi("Alarm sistemi anlaşılmaz yanıt verdi.") from e


def tetikle(tur: str, kaynak: str, sms_metni: str) -> dict:
    """tatbikat gönderilmez: dashboard'daki tahta alarm modu (tahta_alarm_tatbikat) belirler."""
    return _istek("POST", "/api/acil/makine/tetikle", {"tur": tur, "kaynak": kaynak, "sms_metni": sms_metni})


def yanlis_alarm(kaynak: str) -> dict:
    return _istek("POST", "/api/acil/makine/yanlis-alarm", {"kaynak": kaynak})


def durum() -> dict:
    """{"aktif": {...}|None, "tatbikat": bool}; ulaşılamazsa AcilHatasi."""
    return _istek("GET", "/api/acil/makine/durum", zaman_asimi=5)
