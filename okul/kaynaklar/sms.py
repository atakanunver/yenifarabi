"""Veli giriş kodu — smssistemi /api/arac/kod-sms üzerinden (aynı makine, :8020)."""

import re

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
# --- Yönetici SMS paneli: smssistemi /api/arac uçlarının istemcisi ---------

_PANEL_MESAJLARI = {
    400: "Tüm okul gönderimi için alıcı sayısını aynen yazarak onaylamalısınız.",
    404: "Kayıt ya da alıcı bulunamadı.",
    410: "Taslağın süresi doldu; yeni taslak oluşturun.",
    422: "Mesaj geçersiz (boş ya da çok uzun) veya telefon numarası hatalı.",
    429: "Günlük toplu SMS sınırına ulaşıldı.",
}


def _taban() -> str:
    return AYAR.sms_url.rsplit("/", 1)[0]


def _panel(yontem: str, yol: str, json: dict | None = None):
    if not AYAR.sms_anahtar:
        raise SmsHatasi(
            "SMS servisi ayarlanmamış (config/gizli.json: sms_arac_anahtar)."
        )
    try:
        r = httpx.request(
            yontem,
            _taban() + yol,
            json=json,
            headers={"X-Sms-Arac-Key": AYAR.sms_anahtar},
            timeout=15,
            trust_env=False,
        )
    except httpx.HTTPError as e:
        raise SmsHatasi("SMS servisine şu an ulaşılamıyor.") from e
    if r.status_code != 200:
        try:
            veri = r.json()
            ayrinti = veri.get("detail") if isinstance(veri, dict) else None
        except ValueError:
            ayrinti = None
        raise SmsHatasi(
            ayrinti
            if isinstance(ayrinti, str)
            else _PANEL_MESAJLARI.get(
                r.status_code, f"SMS servisi hata verdi ({r.status_code})."
            )
        )
    try:
        veri = r.json()
    except ValueError as e:
        raise SmsHatasi("SMS servisinden geçersiz yanıt alındı.") from e
    if not isinstance(veri, dict):
        raise SmsHatasi("SMS servisinden geçersiz yanıt alındı.")
    return veri


_TURLER = ("veli", "ogrenci", "personel")


def _tur_dogrula(tur: str) -> str:
    if tur not in _TURLER:
        raise SmsHatasi("Geçersiz alıcı grubu.")
    return tur


def taslak(tur: str, sinif: str, metin: str, test_telefon: str = "") -> dict:
    """tur: veli|ogrenci|personel. Gönderilmez; alıcı sayısı + önizleme döner."""
    _tur_dogrula(tur)
    if tur == "personel":
        return _panel("POST", "/personel-taslak", {"metin": metin})
    govde = {"sinif": sinif, "metin": metin}
    if tur == "ogrenci" and test_telefon:
        govde["test_telefon"] = test_telefon
    return _panel("POST", f"/{tur}-taslak", govde)


def taslak_gonder(tur: str, taslak_id: str, alici_sayisi: int | None) -> dict:
    _tur_dogrula(tur)
    return _panel(
        "POST", f"/{tur}-gonder", {"taslak_id": taslak_id, "alici_sayisi": alici_sayisi}
    )


def gonderimler() -> list[dict]:
    sonuc = _panel("GET", "/gonderimler?limit=100").get("gonderimler")
    return sonuc if isinstance(sonuc, list) else []


def _gid(gonderim_id: str) -> str:
    if not re.fullmatch(r"[\w-]{1,40}", gonderim_id):
        raise SmsHatasi("Geçersiz gönderim numarası.")
    return gonderim_id


def gonderim(gonderim_id: str) -> dict:
    return _panel("GET", f"/gonderim/{_gid(gonderim_id)}")


def tekrar(gonderim_id: str) -> dict:
    return _panel("POST", f"/gonderim/{_gid(gonderim_id)}/tekrar")
