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
import logging
import threading
import time
from pathlib import Path
from threading import Event
from typing import Callable

import requests
from huawei_lte_api.Client import Client
from huawei_lte_api.Connection import Connection
from huawei_lte_api.enums.sms import BoxTypeEnum, TextModeEnum

from gonderim import is_ascii

log = logging.getLogger("smssistemi.modem")

# Modemde tek oturum olur: toplu_gonder, gelen kutusu okuma ve bildirim
# gönderimi bu kilit altında bağlanır. RLock: bildirim akışı kilidi tutarken
# toplu_gonder'i çağırabilsin diye. Gelen kutusu poller'ı kilidi BEKLEMEZ
# (alınamazsa turu atlar); gönderim ise sırasını bekler.
modem_kilidi = threading.RLock()

# Giden/gelen kutusu sayfalama sınırları (sonsuz döngü koruması).
_SAYFA_BOYUTU = 50
_AZAMI_SAYFA = 20

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


def _yanittan_mesajlar(yanit: dict | None) -> list[dict]:
    """huawei_lte_api yanıtı: {"Messages": {"Message": [..]}} (tek öğe dict olabilir)."""
    ic = (yanit or {}).get("Messages") or {}
    mesajlar = ic.get("Message") if isinstance(ic, dict) else ic
    if not mesajlar:
        return []
    if isinstance(mesajlar, dict):
        return [mesajlar]
    return list(mesajlar)


def _kutu_mesajlari(client: Client, kutu: BoxTypeEnum) -> list[dict]:
    """Bir kutudaki tüm mesajları (sayfalayarak, üst sınırlı) ham dict olarak döner."""
    sonuc: list[dict] = []
    for sayfa in range(1, _AZAMI_SAYFA + 1):
        yanit = client.sms.get_sms_list(page=sayfa, box_type=kutu, read_count=_SAYFA_BOYUTU)
        mesajlar = _yanittan_mesajlar(yanit)
        sonuc.extend(mesajlar)
        if len(mesajlar) < _SAYFA_BOYUTU:
            break
    return sonuc


def giden_kutusunu_temizle(client: Client) -> int:
    """Modemin GİDEN (LOCAL_SENT) kutusunu siler; gelen kutusuna dokunmaz.
    Hata gönderimi bozmaz — loglanır, silinen sayı döner."""
    silinen = 0
    try:
        for _tur in range(_AZAMI_SAYFA):
            mesajlar = _yanittan_mesajlar(
                client.sms.get_sms_list(page=1, box_type=BoxTypeEnum.LOCAL_SENT, read_count=_SAYFA_BOYUTU)
            )
            if not mesajlar:
                break
            for m in mesajlar:
                client.sms.delete_sms(int(m["Index"]))
                silinen += 1
    except Exception as exc:  # noqa: BLE001 - temizlik gönderimi bozmamalı
        log.warning("giden kutusu temizliği başarısız (%s), silinen=%d", type(exc).__name__, silinen)
    return silinen


def gelen_kutusunu_isle(
    ayarlar: dict,
    isleyici: Callable[[list[dict]], list[int]],
) -> int | None:
    """Gelen kutusunu okur, `isleyici(mesajlar)`'a verir; isleyici DB'ye kaydedip
    doğruladığı mesajların modem Index listesini döner, yalnızca onlar modemden
    silinir (hata olursa modemde kalır — kayıp yok). Kilit alınamazsa None
    (tur atlandı); aksi halde silinen sayı."""
    if not modem_kilidi.acquire(blocking=False):
        return None
    try:
        connection = _baglan(ayarlar)
        with connection:
            client = Client(connection)
            mesajlar = _kutu_mesajlari(client, BoxTypeEnum.LOCAL_INBOX)
            if not mesajlar:
                return 0
            silinecek = isleyici(mesajlar)
            silinen = 0
            for index in silinecek:
                try:
                    client.sms.delete_sms(int(index))
                    silinen += 1
                except Exception as exc:  # noqa: BLE001
                    log.warning("gelen mesaj silinemedi (%s)", type(exc).__name__)
            return silinen
    finally:
        modem_kilidi.release()


def toplu_gonder(
    ayarlar: dict,
    kisiler: list[tuple[str, str, str]],
    sonuc_callback: Callable[[str, str, str, str, str | None], None],
    durdur_bayragi: Event,
    bekleme_sn: float,
) -> None:
    with modem_kilidi:
        _toplu_gonder_kilitli(ayarlar, kisiler, sonuc_callback, durdur_bayragi, bekleme_sn)


def _toplu_gonder_kilitli(
    ayarlar: dict,
    kisiler: list[tuple[str, str, str]],
    sonuc_callback: Callable[[str, str, str, str, str | None], None],
    durdur_bayragi: Event,
    bekleme_sn: float,
) -> None:
    try:
        connection = _baglan(ayarlar)
    except Exception as exc:  # noqa: BLE001 - birkaç denemeden sonra hala basarisiz
        # 2026-09-28: tek bir bos satir yerine HER alici kendi isim/telefon/
        # mesajiyla "hata" kaydediliyor — aksi halde telefon="" oldugu icin
        # db.gonderim_basarisizlari() (telefon != '' filtresi) hicbirini
        # /tekrar-gonder ile yeniden deneyemiyordu (DECISIONS.md 2026-09-28).
        hata_metni = f"BAĞLANTI HATASI: {exc}"
        for isim, telefon, mesaj in kisiler:
            sonuc_callback(isim, telefon, mesaj, "hata", hata_metni)
        return

    # `kaydedilen`: sonuc_callback'e fiilen verilmis (basarili ya da
    # kendi try/except'inde yakalanmis hatali) alici sayisi — telefona gore
    # degil INDEKSE gore takip edilir, cunku kardesler ayni telefonu
    # paylasabilir (bkz. CLAUDE.md smssistemi bolumu). durdur_bayragi ile
    # durdurulan aliciler bu sayaca hic girmez, bilerek kayitsiz kalir.
    kaydedilen = 0
    durduruldu = False
    try:
        with connection:
            client = Client(connection)
            for i, (isim, telefon, mesaj) in enumerate(kisiler):
                if durdur_bayragi.is_set():
                    durduruldu = True
                    break
                mode = TextModeEnum.SEVEN_BIT if is_ascii(mesaj) else TextModeEnum.UCS2
                try:
                    client.sms.send_sms([telefon], mesaj, text_mode=mode)
                    sonuc_callback(isim, telefon, mesaj, "gonderildi", None)
                except Exception as exc:  # noqa: BLE001 - modem API'si spesifik olmayan hatalar fırlatabiliyor
                    sonuc_callback(isim, telefon, mesaj, "hata", str(exc))
                kaydedilen = i + 1
                if i < len(kisiler) - 1 and not durdur_bayragi.is_set():
                    time.sleep(bekleme_sn)
            giden_kutusunu_temizle(client)
    except Exception as exc:  # noqa: BLE001 - baglanti kurulduktan sonraki genel hata
        # `with connection:` bloğundan çıkışta (ör. modemden logout isteği)
        # da bu hataya düşülebilir — kullanıcı DURDUR'a bastıysa (durduruldu)
        # kalanları hiç kaydetme, mevcut durdurma davranışı korunur.
        if durduruldu:
            return
        hata_metni = f"BAĞLANTI HATASI (gönderim sırasında): {exc}"
        for isim, telefon, mesaj in kisiler[kaydedilen:]:
            sonuc_callback(isim, telefon, mesaj, "hata", hata_metni)
