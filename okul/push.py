"""Web Push bildirimleri (VAPID). Yalnızca SABİT, veri içermeyen metin gider.

Push mesajı tarayıcı üreticisinin (Google/Apple/Mozilla) sunucularından geçer; bu yüzden ad, ders, not,
devamsızlık gibi hiçbir öğrenci/veli verisi payload'a konmaz — şablon dışı metin kabul edilmez.
Bildirim asıl işlemi (duyuru, ödev) ASLA bozmaz: gönderim hataları yutulur ve loglanır.
"""

import json
import logging
import sqlite3
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import db
import zaman
from ayarlar import AYAR

log = logging.getLogger("okul.push")

# tür -> (başlık, gövde, açılacak sayfa). Yeni tür = buraya sabit metin ve sabit yol ekle; serbest metin geçirilemez.
# Yol veri taşımaz (kimlik/ad yok): bildirime tıklayınca ilgili liste sayfası açılır.
SABLONLAR = {
    "duyuru": ("Dijital Okul", "Yeni bir duyuru var.", "/duyurular"),
    "odev": ("Dijital Okul", "Yeni bir ödevin var.", "/ogrenci/odevler"),
    "odev_hatirlat": ("Dijital Okul", "Teslim edilmemiş bir ödevin var.", "/ogrenci/odevler"),
    "odev_yaklasan": ("Dijital Okul", "Teslim tarihi yaklaşan bir ödevin var.", "/ogrenci/odevler"),
    "pdf": ("Dijital Okul", "Yeni bir dosya paylaşıldı.", "/ogrenci/dosyalar"),
    "sohbet": ("Dijital Okul", "Yeni bir sohbet mesajı var.", "/sohbet"),
    "acil": ("Dijital Okul", "Acil durum bildirimi var!", "/acil"),
    "acil_bitti": ("Dijital Okul", "Acil durum sona erdi.", "/acil"),
    "deneme": ("Dijital Okul", "Test bildirimi: bildirimler açık.", "/bildirimler"),
    "devamsizlik": ("Dijital Okul", "Öğrenciniz bugün bir derse girmedi.", "/veli/devamsizlik"),
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
        baslik, govde, yol = SABLONLAR[tur]
        veri = json.dumps({"baslik": baslik, "govde": govde, "url": yol}, ensure_ascii=False)
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


# --- Alıcı çözümleme + arka plan tetikleyicileri (Faz 2) ---
# Alıcılar duyurular.gorunur_duyurular ile AYNI görünürlük kuralını izler; yalnızca bildirime abone, aktif ve
# yazar dışındaki kullanıcılar döner.

_ABONELI = (
    "SELECT DISTINCT u.id FROM kullanici u JOIN push_abonelik p ON p.kullanici_id = u.id"
    " WHERE u.aktif = 1 AND u.id != ?"
)


def duyuru_alicilari(conn: sqlite3.Connection, hedef_tur: str, hedef: str | None, yazar_id: int) -> list[int]:
    if hedef_tur == "okul":
        sql, par = _ABONELI, [yazar_id]
    elif hedef_tur == "rol":
        sql, par = _ABONELI + " AND u.rol = ?", [yazar_id, hedef]
    elif hedef_tur == "sinif" and hedef:
        sql = _ABONELI + (
            " AND (u.rol = 'yonetici'"
            " OR u.id IN (SELECT kullanici_id FROM ogrenci WHERE sinif = ? AND kullanici_id IS NOT NULL)"
            " OR u.id IN (SELECT vo.veli_id FROM veli_ogrenci vo JOIN ogrenci o ON o.id = vo.ogrenci_id"
            " WHERE o.sinif = ?)"
            " OR u.id IN (SELECT ogretmen_id FROM ogretmen_gorev WHERE sinif = ?))"
        )
        par = [yazar_id, hedef, hedef, hedef]
    else:
        return []
    return [r[0] for r in conn.execute(sql, par)]


def odev_alicilari(conn: sqlite3.Connection, sinif: str, yazar_id: int) -> list[int]:
    """Ödevin sınıfındaki öğrenciler (veliye gitmez: bildirim metni öğrenciye hitap eder)."""
    return [
        r[0]
        for r in conn.execute(
            _ABONELI + " AND u.id IN (SELECT kullanici_id FROM ogrenci WHERE sinif = ? AND kullanici_id IS NOT NULL)",
            (yazar_id, sinif),
        )
    ]


def _arkaplan(tur: str, alici_bul: Callable[[sqlite3.Connection], list[int]]) -> None:
    """İstek bittikten sonra çalışır; kendi bağlantısını açar (istek bağlantısı kapanmış olabilir). Asla istisna fırlatmaz."""
    if not etkin_mi():
        return
    try:
        conn = db.baglanti()
        try:
            gonder(conn, alici_bul(conn), tur)
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        log.warning("push arka plan hatası (%s): %s", tur, type(e).__name__)


def duyuru_bildir(hedef_tur: str, hedef: str | None, yazar_id: int) -> None:
    _arkaplan("duyuru", lambda c: duyuru_alicilari(c, hedef_tur, hedef, yazar_id))


def odev_bildir(sinif: str, yazar_id: int) -> None:
    _arkaplan("odev", lambda c: odev_alicilari(c, sinif, yazar_id))


def odev_hatirlat_alicilari(conn: sqlite3.Connection, odev_id: int, yazar_id: int) -> list[int]:
    """Ödevin sınıfında henüz teslim etmemiş öğrenciler."""
    return [
        r[0]
        for r in conn.execute(
            _ABONELI + " AND u.id IN (SELECT g.kullanici_id FROM ogrenci g JOIN odev o ON o.sinif = g.sinif"
            " WHERE o.id = ? AND g.kullanici_id IS NOT NULL"
            " AND NOT EXISTS (SELECT 1 FROM odev_teslim t WHERE t.odev_id = o.id AND t.ogrenci_id = g.id))",
            (yazar_id, odev_id),
        )
    ]


UYARI_ONCE = timedelta(hours=24)  # teslime bu kadar kala uyar
UYARI_MIN_YAS = timedelta(hours=12)  # yeni verilen ödev için "yeni ödev" bildirimiyle üst üste uyarı gitmesin
UYARI_SAATLERI = range(8, 20)  # gece uyarı yok


def yaklasan_odev_uyar(conn: sqlite3.Connection, simdi: datetime) -> int:
    """Teslimine 24 saatten az kalmış, teslim etmemiş öğrencilere ödev başına bir kez uyarı. Gönderilen ödev sayısı döner.
    Push kapalıysa ya da saat dışındaysa hiçbir şey işaretlenmez."""
    if not etkin_mi() or simdi.hour not in UYARI_SAATLERI:
        return 0
    simdi_s = simdi.strftime(zaman.BICIM)
    odevler = conn.execute(
        "SELECT id FROM odev WHERE teslim > ? AND teslim <= ? AND olusturma <= ?"
        " AND id NOT IN (SELECT odev_id FROM odev_uyari)",
        (simdi_s, (simdi + UYARI_ONCE).strftime(zaman.BICIM), (simdi - UYARI_MIN_YAS).strftime(zaman.BICIM)),
    ).fetchall()
    for o in odevler:
        conn.execute("INSERT OR IGNORE INTO odev_uyari (odev_id, zaman) VALUES (?, ?)", (o["id"], simdi_s))
        conn.commit()
        gonder(conn, odev_hatirlat_alicilari(conn, o["id"], 0), "odev_yaklasan")
    return len(odevler)


def odev_hatirlat_bildir(odev_id: int, yazar_id: int) -> None:
    _arkaplan("odev_hatirlat", lambda c: odev_hatirlat_alicilari(c, odev_id, yazar_id))


def pdf_bildir(sinif: str, yazar_id: int) -> None:
    _arkaplan("pdf", lambda c: odev_alicilari(c, sinif, yazar_id))


def devamsizlik_alicilari(conn: sqlite3.Connection, okul_no_listesi: list[int]) -> list[int]:
    """Verilen okul numaralarının velileri (öğrenciye gitmez — anlık bildirim veliye hitap eder)."""
    if not okul_no_listesi:
        return []
    yer = ",".join("?" * len(okul_no_listesi))
    return [
        r[0]
        for r in conn.execute(
            _ABONELI + f" AND u.id IN (SELECT vo.veli_id FROM veli_ogrenci vo"
            f" JOIN ogrenci o ON o.id = vo.ogrenci_id WHERE o.okul_no IN ({yer}))",
            [0, *okul_no_listesi],
        )
    ]


def devamsizlik_bildir(okul_no_listesi: list[int]) -> None:
    _arkaplan("devamsizlik", lambda c: devamsizlik_alicilari(c, okul_no_listesi))
