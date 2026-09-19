"""Huawei HiLink modem köprüsü — Müdür PC'deki netsh portproxy üzerinden
(bkz. docs/superpowers/specs/2026-09-19-smssistemi-design.md "Mimari").
huawei_lte_api'nin gerçek ağ çağrılarını yapan tek yer; app.py bunu
threading.Thread içinde çağırır (senkron/bloklayan kütüphane).
"""

import json
import time
from pathlib import Path
from threading import Event
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

import requests
from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from huawei_lte_api.enums.sms import TextModeEnum

from gonderim import is_ascii

MODEM_CONFIG_YOLU = Path(__file__).resolve().parent / "config" / "modem.json"


def modem_ayarlarini_yukle() -> dict:
    veri = json.loads(MODEM_CONFIG_YOLU.read_text(encoding="utf-8"))
    return {"host": veri["host"], "port": veri["port"], "user": veri["user"], "pass": veri["pass"]}


def _baglanti_url(ayarlar: dict) -> str:
    return f"http://{ayarlar['user']}:{ayarlar['pass']}@{ayarlar['host']}:{ayarlar['port']}/"


def _kopru_session(ayarlar: dict) -> requests.Session:
    """Müdür PC'deki netsh portproxy salt TCP yönlendirmesi — modem kendi
    HTML'inde/Location header'ında hep kendi LAN IP'sine (örn. 192.168.8.1)
    mutlak URL üretiyor, Farabi o ağa doğrudan ulaşamadığı için `requests`
    bu redirect'i takip ederken bağlantı timeout'a düşüyor (bkz.
    docs/superpowers/specs/2026-09-19-smssistemi-design.md "Mimari" — köprü
    yalnızca TCP seviyesinde, HTTP içeriğini yeniden yazmıyor). Bu hook her
    redirect'in Location'ındaki host:port'u köprünün kendisiyle değiştirip
    modemin kendi ağına kaçmasını engelliyor."""
    kopru_netloc = f"{ayarlar['host']}:{ayarlar['port']}"

    def _location_duzelt(response: requests.Response, *args, **kwargs) -> requests.Response:
        konum = response.headers.get("Location")
        if not konum:
            return response
        parcalar = urlsplit(konum)
        if parcalar.netloc and parcalar.netloc != kopru_netloc:
            response.headers["Location"] = urlunsplit(
                (parcalar.scheme or "http", kopru_netloc, parcalar.path, parcalar.query, parcalar.fragment)
            )
        return response

    session = requests.Session()
    session.hooks["response"].append(_location_duzelt)
    return session


def baglantiyi_test_et(ayarlar: dict) -> dict:
    with Connection(_baglanti_url(ayarlar), requests_session=_kopru_session(ayarlar)) as connection:
        client = Client(connection)
        info = client.device.information()
        signal = client.device.signal()
    return {"cihaz": info.get("DeviceName", "?"), "sinyal": signal.get("rssi", "?")}


def toplu_gonder(
    ayarlar: dict,
    kisiler: list[tuple[str, str, str]],
    sonuc_callback: Callable[[str, str, str, str, str | None], None],
    durdur_bayragi: Event,
    bekleme_sn: float,
) -> None:
    try:
        with Connection(_baglanti_url(ayarlar), requests_session=_kopru_session(ayarlar)) as connection:
            client = Client(connection)
            for i, (isim, telefon, mesaj) in enumerate(kisiler):
                if durdur_bayragi.is_set():
                    break
                mode = TextModeEnum.SEVEN_BIT if is_ascii(mesaj) else TextModeEnum.UCS2
                try:
                    client.sms.send_sms([telefon], mesaj, text_mode=mode)
                    sonuc_callback(isim, telefon, mesaj, "gonderildi", None)
                except Exception as exc:  # noqa: BLE001 - modem API'si spesifik olmayan hatalar fırlatabiliyor
                    sonuc_callback(isim, telefon, mesaj, "hata", str(exc))
                if i < len(kisiler) - 1 and not durdur_bayragi.is_set():
                    time.sleep(bekleme_sn)
    except Exception as exc:  # noqa: BLE001 - bağlantı hatası, tüm batch için
        sonuc_callback("", "", "", "hata", f"BAĞLANTI HATASI: {exc}")
