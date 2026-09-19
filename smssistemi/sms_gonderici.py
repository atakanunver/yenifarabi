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


def _baglan(ayarlar: dict, deneme: int = 5, bekleme_sn: float = 1.5) -> Connection:
    """Müdür PC'deki `netsh portproxy` relay'i HTTP framing'i güvenilir
    taşımıyor (bkz. DECISIONS.md 2026-09-19 — art arda denemelerin çoğu
    ConnectionError/BadStatusLine ile düşüyor). Bağlantı kurulumu (login/
    CSRF init, Connection.__init__ içinde olur) bu yüzden birkaç kez
    denenir; hiçbir SMS burada gönderilmez, tekrar denemek yan etkisiz."""
    son_hata: Exception | None = None
    for i in range(1, deneme + 1):
        try:
            return Connection(_baglanti_url(ayarlar), requests_session=_kopru_session(ayarlar))
        except Exception as exc:  # noqa: BLE001 - kopru/modem'den gelen cesitli hatalar
            son_hata = exc
            if i < deneme:
                time.sleep(bekleme_sn)
    assert son_hata is not None
    raise son_hata


def baglantiyi_test_et(ayarlar: dict) -> dict:
    with _baglan(ayarlar) as connection:
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
        connection = _baglan(ayarlar)
    except Exception as exc:  # noqa: BLE001 - birkaç denemeden sonra hala basarisiz
        sonuc_callback("", "", "", "hata", f"BAĞLANTI HATASI: {exc}")
        return
    try:
        with connection:
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
    except Exception as exc:  # noqa: BLE001 - baglanti kurulduktan sonraki genel hata
        sonuc_callback("", "", "", "hata", f"BAĞLANTI HATASI (gönderim sırasında): {exc}")
