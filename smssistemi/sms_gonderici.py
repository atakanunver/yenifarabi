"""Huawei HiLink modem köprüsü — Müdür PC'deki WifiHttpProxy (gerçek bir
HTTP forward proxy, Wi-Fi arayüzüne bound) üzerinden (bkz.
docs/superpowers/specs/2026-09-19-smssistemi-design.md "Mimari").
huawei_lte_api'nin gerçek ağ çağrılarını yapan tek yer; app.py bunu
threading.Thread içinde çağırır (senkron/bloklayan kütüphane).

2026-09-20: köprü mekanizması `netsh portproxy` (ham TCP yönlendirme,
HTTP çerçevelemesini bozuyordu — BadStatusLine, DECISIONS.md 2026-09-19)
üzerinden WifiHttpProxy'ye (gerçek HTTP/CONNECT proxy, mesajları
ayrıştırıp doğru şekilde aktarıyor) taşındı. Artık modeme onun GERÇEK
IP'siyle (`modem_ip`) doğrudan konuşuluyor, proxy sadece taşımayı
yapıyor — modemin kendi Host kontrolü de böylece doğal şekilde geçiyor,
eski `_kopru_session` Location-yeniden-yazma hack'ine gerek kalmadı.
"""

import json
import time
from pathlib import Path
from threading import Event
from typing import Callable

import requests
from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from huawei_lte_api.enums.sms import TextModeEnum

from gonderim import is_ascii

MODEM_CONFIG_YOLU = Path(__file__).resolve().parent / "config" / "modem.json"


def modem_ayarlarini_yukle() -> dict:
    veri = json.loads(MODEM_CONFIG_YOLU.read_text(encoding="utf-8"))
    return {
        "user": veri["user"],
        "pass": veri["pass"],
        "modem_ip": veri.get("modem_ip", "192.168.8.1"),
        "proxy_host": veri["proxy_host"],
        "proxy_port": veri["proxy_port"],
        "proxy_user": veri["proxy_user"],
        "proxy_pass": veri["proxy_pass"],
    }


def _baglanti_url(ayarlar: dict) -> str:
    return f"http://{ayarlar['user']}:{ayarlar['pass']}@{ayarlar['modem_ip']}/"


class _TekSeferlikSession(requests.Session):
    """WifiHttpProxy (Müdür PC) her TCP bağlantısında yalnızca TEK istek
    işleyip sonra soketi kapatıyor (kalıcı/keep-alive bağlantı
    desteklemiyor) — `requests`'in varsayılan bağlantı havuzu aynı soketi
    ikinci istek için yeniden kullanmaya çalışınca ConnectionResetError/
    ReadTimeout ile düşüyor (canlı teşhis, 2026-09-20; `Connection: close`
    header'ı da tek başına yetmiyor). Her istekten sonra adapter'ın
    bağlantı havuzunu kapatıp sonraki isteğin taze bir TCP bağlantısı
    açmasını zorluyor."""

    def send(self, *args, **kwargs):
        yanit = super().send(*args, **kwargs)
        for adapter in self.adapters.values():
            adapter.close()
        return yanit


def _proxy_session(ayarlar: dict) -> requests.Session:
    """Müdür PC'deki WifiHttpProxy'yi kullanan session — modem plain HTTP
    olduğu için `requests` CONNECT değil, proxy'ye mutlak-URI GET/POST
    (absolute-form) isteği atar; WifiHttpProxy bunu gerçek bir HTTP
    isteği olarak ayrıştırıp modeme iletir (ham byte kopyalama değil)."""
    proxy_url = (
        f"http://{ayarlar['proxy_user']}:{ayarlar['proxy_pass']}"
        f"@{ayarlar['proxy_host']}:{ayarlar['proxy_port']}"
    )
    session = _TekSeferlikSession()
    session.proxies = {"http": proxy_url}
    return session


def _baglan(ayarlar: dict, deneme: int = 8, bekleme_sn: float = 1.0) -> Connection:
    """2026-09-19: `netsh portproxy` relay'i HTTP framing'i güvenilir
    taşımıyordu (DECISIONS.md — art arda denemelerin çoğu
    ConnectionError/BadStatusLine ile düşüyordu). 2026-09-20'de köprü
    WifiHttpProxy'ye (gerçek HTTP proxy) taşındı ama yine de her deneme
    TAMAMEN taze bir Connection/session ile kurulup gerçek bir API
    çağrısıyla (`device.information`) doğrulanıyor — proxy/modem tarafında
    beklenmeyen bir davranış çıkarsa (ör. modemin tek-oturum kısıtı) taze
    bağlantı bunu tolere eder. Yalnızca bu doğrulama başarılı olursa
    bağlantı 'sağlıklı' kabul edilir. Hiçbir SMS burada gönderilmez,
    tekrar denemek yan etkisiz."""
    son_hata: Exception | None = None
    for i in range(1, deneme + 1):
        connection: Connection | None = None
        try:
            connection = Connection(_baglanti_url(ayarlar), requests_session=_proxy_session(ayarlar))
            Client(connection).device.information()
            return connection
        except Exception as exc:  # noqa: BLE001 - kopru/modem'den gelen cesitli hatalar
            son_hata = exc
            if connection is not None:
                try:
                    connection.close()
                except Exception:  # noqa: BLE001 - zaten bozuk bir baglantiyi kapatmaya calisiyoruz
                    pass
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
