"""Web Push bildirimleri (VAPID). Yalnızca SABİT, veri içermeyen metin gider.

Push mesajı tarayıcı üreticisinin (Google/Apple/Mozilla) sunucularından geçer; bu yüzden ad, ders, not,
devamsızlık gibi hiçbir öğrenci/veli verisi payload'a konmaz — şablon dışı metin kabul edilmez.
Bildirim asıl işlemi (duyuru, ödev) ASLA bozmaz: gönderim hataları yutulur ve loglanır.
"""

import json
import logging
import sqlite3
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

import zaman
from ayarlar import AYAR

log = logging.getLogger("okul.push")

# tür -> (başlık, gövde). Yeni tür = buraya sabit metin ekle; serbest metin geçirilemez.
SABLONLAR = {
    "duyuru": ("Dijital Okul", "Yeni bir duyuru var."),
    "odev": ("Dijital Okul", "Yeni bir ödevin var."),
    "deneme": ("Dijital Okul", "Test bildirimi: bildirimler açık."),
}
AZAMI_ABONELIK = 10  # kullanıcı başına cihaz
AZAMI_HATA = 5  # ardışık geçici hatadan sonra abonelik silinir
TTL_SN = 3600  # cihaz kapalıysa 1 saat sonra düşer (eski duyuru sürpriz olmasın)
UC_NOKTA_AZAMI = 600


def etkin_mi() -> bool:
    return bool(AYAR.vapid_ozel and AYAR.vapid_acik and AYAR.vapid_konu)


def uc_nokta_gecerli(uc: str) -> bool:
    if not uc or len(uc) > UC_NOKTA_AZAMI:
        return False
    p = urlsplit(uc)
    return p.scheme == "https" and bool(p.hostname)


def abone_ol(conn: sqlite3.Connection, kullanici_id: int, uc: str, p256dh: str, auth: str) -> bool:
    """Aboneliği kaydeder/günceller. Aynı uç nokta başka kullanıcıdaysa (paylaşılan cihaz) ona devredilir.
    Kullanıcı başına cihaz sınırı aşılırsa False döner."""
    mevcut = conn.execute("SELECT kullanici_id FROM push_abonelik WHERE uc_nokta = ?", (uc,)).fetchone()
    if mevcut is None:
        sayi = conn.execute(
            "SELECT COUNT(*) FROM push_abonelik WHERE kullanici_id = ?", (kullanici_id,)
        ).fetchone()[0]
        if sayi >= AZAMI_ABONELIK:
            return False
        conn.execute(
            "INSERT INTO push_abonelik (kullanici_id, uc_nokta, p256dh, auth, olusturma)"
            " VALUES (?, ?, ?, ?, ?)",
            (kullanici_id, uc, p256dh, auth, zaman.simdi_str()),
        )
    else:
        conn.execute(
            "UPDATE push_abonelik SET kullanici_id = ?, p256dh = ?, auth = ?, hata_sayisi = 0"
            " WHERE uc_nokta = ?",
            (kullanici_id, p256dh, auth, uc),
        )
    conn.commit()
    return True


def abonelik_sil(conn: sqlite3.Connection, kullanici_id: int, uc: str) -> None:
    """Yalnızca kendi aboneliğini siler."""
    conn.execute(
        "DELETE FROM push_abonelik WHERE uc_nokta = ? AND kullanici_id = ?", (uc, kullanici_id)
    )
    conn.commit()


def abonelik_sayisi(conn: sqlite3.Connection, kullanici_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM push_abonelik WHERE kullanici_id = ?", (kullanici_id,)
    ).fetchone()[0]


class _KaliciHata(Exception):
    """Uç nokta artık yok (404/410): abonelik silinmeli."""


def _webpush_gonder(abone: dict, veri: str) -> None:
    from pywebpush import (  # geç içe aktarım: kütüphane yoksa modül yine yüklenir
        WebPushException,
        webpush,
    )

    try:
        webpush(
            subscription_info=abone,
            data=veri,
            vapid_private_key=AYAR.vapid_ozel,
            vapid_claims={"sub": AYAR.vapid_konu},
            ttl=TTL_SN,
            timeout=10,
        )
    except WebPushException as e:
        r = getattr(e, "response", None)
        if r is not None and r.status_code in (404, 410):
            raise _KaliciHata from e
        raise


def gonder(
    conn: sqlite3.Connection,
    kullanici_idleri: Iterable[int],
    tur: str,
    gonderici: Callable[[dict, str], None] | None = None,
) -> dict:
    """Kullanıcıların tüm cihazlarına sabit şablonlu bildirim yollar. Asla istisna fırlatmaz.
    Dönüş: {"gonderilen", "silinen", "hata"} sayaçları. `gonderici` yalnızca testler içindir."""
    sonuc = {"gonderilen": 0, "silinen": 0, "hata": 0}
    try:
        if tur not in SABLONLAR or not etkin_mi():
            return sonuc
        idler = sorted({int(i) for i in kullanici_idleri})
        if not idler:
            return sonuc
        baslik, govde = SABLONLAR[tur]
        veri = json.dumps({"baslik": baslik, "govde": govde, "url": "/"}, ensure_ascii=False)
        gonder_fn = gonderici or _webpush_gonder
        yer = ",".join("?" * len(idler))
        satirlar = conn.execute(
            f"SELECT id, uc_nokta, p256dh, auth, hata_sayisi FROM push_abonelik"
            f" WHERE kullanici_id IN ({yer})",
            idler,
        ).fetchall()
        for s in satirlar:
            abone = {"endpoint": s["uc_nokta"], "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}}
            try:
                gonder_fn(abone, veri)
            except _KaliciHata:
                conn.execute("DELETE FROM push_abonelik WHERE id = ?", (s["id"],))
                sonuc["silinen"] += 1
            except Exception as e:  # noqa: BLE001 — bildirim isteğe bağlıdır; ham hata metni loglanmaz
                sonuc["hata"] += 1
                log.warning("push gönderilemedi (abonelik %s): %s", s["id"], type(e).__name__)
                if s["hata_sayisi"] + 1 >= AZAMI_HATA:
                    conn.execute("DELETE FROM push_abonelik WHERE id = ?", (s["id"],))
                    sonuc["silinen"] += 1
                else:
                    conn.execute(
                        "UPDATE push_abonelik SET hata_sayisi = hata_sayisi + 1 WHERE id = ?",
                        (s["id"],),
                    )
            else:
                sonuc["gonderilen"] += 1
                conn.execute(
                    "UPDATE push_abonelik SET son_basari = ?, hata_sayisi = 0 WHERE id = ?",
                    (zaman.simdi_str(), s["id"]),
                )
        conn.commit()
    except Exception as e:  # noqa: BLE001
        log.warning("push toplu gönderim hatası: %s", type(e).__name__)
    return sonuc
