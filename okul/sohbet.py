"""Öğretmen+yönetici ortak sohbet odası: yalnızca metin, 30 gün saklama, dosya/foto yok.

Yönetici tüm mesajları görür ve silebilir; yazar kendi mesajını silebilir. Okuma sorguları süresi dolan mesajı hiç
döndürmez (fiziksel silme geç kalsa bile görünmez). Elle alınan veri/yedek/ dosyaları eski mesajları içerebilir
(kullanıcı kararı: yedekler temizlenmez). Bildirim (push) içeriksiz sabit metindir ve alıcı başına 10 dk'da bir gider.
"""

import logging
import re
import sqlite3
from datetime import datetime, timedelta

import db
import push
import zaman

log = logging.getLogger("okul.sohbet")

ROLLER = ("ogretmen", "yonetici")
AZAMI_METIN = 1000
SAKLAMA_GUN = 30
DAKIKA_AZAMI = 20  # kullanıcı başına dakikada en çok mesaj
PUSH_ARALIK_DK = 10  # aynı alıcıya iki sohbet bildirimi arası
SAYFA_AZAMI = 100
TEMIZLIK_ARALIK = timedelta(hours=1)

_son_temizlik: datetime | None = None
_KONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class SohbetHatasi(Exception):
    def __init__(self, mesaj: str, kod: int = 400):
        super().__init__(mesaj)
        self.mesaj = mesaj
        self.kod = kod


def _esik() -> str:
    return (zaman.simdi() - timedelta(days=SAKLAMA_GUN)).strftime(zaman.BICIM)


def temizle(conn: sqlite3.Connection) -> int:
    """Süresi dolan mesajları fiziksel olarak siler; silinen sayısı döner."""
    n = conn.execute("DELETE FROM sohbet_mesaj WHERE olusturma < ?", (_esik(),)).rowcount
    conn.commit()
    return n


def _temizle_gerekirse(conn: sqlite3.Connection) -> None:
    global _son_temizlik
    simdi = zaman.simdi()
    if _son_temizlik is None or simdi - _son_temizlik >= TEMIZLIK_ARALIK:
        _son_temizlik = simdi
        temizle(conn)


def baslangic_temizligi() -> None:
    """Servis açılışında bir kez; hata servisi düşürmez."""
    try:
        conn = db.baglanti()
        try:
            temizle(conn)
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        log.warning("sohbet temizliği yapılamadı: %s", type(e).__name__)


def metin_duzenle(metin: str) -> str:
    m = _KONTROL.sub("", (metin or "").replace("\r\n", "\n").replace("\r", "\n")).strip()
    return re.sub(r"\n{3,}", "\n\n", m)


def mesaj_ekle(conn: sqlite3.Connection, yazar_id: int, metin: str) -> int:
    m = metin_duzenle(metin)
    if not m:
        raise SohbetHatasi("Mesaj boş olamaz.")
    if len(m) > AZAMI_METIN:
        raise SohbetHatasi(f"Mesaj en çok {AZAMI_METIN} karakter olabilir.")
    dakika_once = (zaman.simdi() - timedelta(seconds=60)).strftime(zaman.BICIM)
    son = conn.execute(
        "SELECT COUNT(*) FROM sohbet_mesaj WHERE yazar_id = ? AND olusturma >= ?", (yazar_id, dakika_once)
    ).fetchone()[0]
    if son >= DAKIKA_AZAMI:
        raise SohbetHatasi("Çok hızlı mesaj gönderiyorsun; biraz bekle.", 429)
    cur = conn.execute(
        "INSERT INTO sohbet_mesaj (yazar_id, metin, olusturma) VALUES (?, ?, ?)",
        (yazar_id, m, zaman.simdi_str()),
    )
    conn.commit()
    _temizle_gerekirse(conn)
    return cur.lastrowid


def gorunum_zamani(olusturma: str) -> str:
    """Bugünse 'SS:DD', değilse 'GG.AA SS:DD'."""
    try:
        dt = datetime.strptime(olusturma, zaman.BICIM)
    except ValueError:
        return olusturma
    if dt.date() == zaman.simdi().date():
        return dt.strftime("%H:%M")
    return dt.strftime("%d.%m %H:%M")


def mesajlar(conn: sqlite3.Connection, k: sqlite3.Row, sonra_id: int = 0, limit: int = SAYFA_AZAMI) -> list[dict]:
    """sonra_id > 0: bundan yeni mesajlar (eskiden yeniye). 0: son `limit` mesaj (eskiden yeniye)."""
    taban = (
        "SELECT m.id, m.metin, m.olusturma, m.yazar_id, u.ad_soyad, u.rol FROM sohbet_mesaj m"
        " JOIN kullanici u ON u.id = m.yazar_id WHERE m.olusturma >= ?"
    )
    if sonra_id > 0:
        satirlar = conn.execute(taban + " AND m.id > ? ORDER BY m.id ASC LIMIT ?", (_esik(), sonra_id, limit)).fetchall()
    else:
        satirlar = conn.execute(taban + " ORDER BY m.id DESC LIMIT ?", (_esik(), limit)).fetchall()[::-1]
    return [
        {
            "id": r["id"], "metin": r["metin"], "zaman": gorunum_zamani(r["olusturma"]), "yazar": r["ad_soyad"],
            "rol": r["rol"], "benim": r["yazar_id"] == k["id"],
            "silinebilir": r["yazar_id"] == k["id"] or k["rol"] == "yonetici",
        }
        for r in satirlar
    ]


def sil(conn: sqlite3.Connection, k: sqlite3.Row, mesaj_id: int) -> bool:
    """Yönetici herhangi bir mesajı, yazar kendi mesajını siler. Yetkisiz/yok = False (sızıntı yok)."""
    r = conn.execute("SELECT yazar_id FROM sohbet_mesaj WHERE id = ?", (mesaj_id,)).fetchone()
    if r is None or not (k["rol"] == "yonetici" or r["yazar_id"] == k["id"]):
        return False
    conn.execute("DELETE FROM sohbet_mesaj WHERE id = ?", (mesaj_id,))
    conn.commit()
    return True


def okundu(conn: sqlite3.Connection, kullanici_id: int, son_id: int) -> None:
    conn.execute(
        "INSERT INTO sohbet_okuma (kullanici_id, son_id) VALUES (?, ?)"
        " ON CONFLICT(kullanici_id) DO UPDATE SET son_id = MAX(son_id, excluded.son_id)",
        (kullanici_id, son_id),
    )
    conn.commit()


def en_son_id(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COALESCE(MAX(id), 0) FROM sohbet_mesaj WHERE olusturma >= ?", (_esik(),)).fetchone()[0]


def okunmamis_sayisi(conn: sqlite3.Connection, kullanici_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM sohbet_mesaj WHERE olusturma >= ? AND yazar_id != ? AND id >"
        " COALESCE((SELECT son_id FROM sohbet_okuma WHERE kullanici_id = ?), 0)",
        (_esik(), kullanici_id, kullanici_id),
    ).fetchone()[0]


def bildirim_alicilari(conn: sqlite3.Connection, yazar_id: int) -> list[int]:
    """Bildirime abone, aktif öğretmen/yönetici; yazar hariç; son bildirimi PUSH_ARALIK_DK'dan eski olanlar.
    Seçilenlerin son_push'u hemen işaretlenir (aralıktaki sonraki mesajlar yeni bildirim üretmez)."""
    sinir = (zaman.simdi() - timedelta(minutes=PUSH_ARALIK_DK)).strftime(zaman.BICIM)
    ids = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT u.id FROM kullanici u JOIN push_abonelik p ON p.kullanici_id = u.id"
            " LEFT JOIN sohbet_okuma o ON o.kullanici_id = u.id"
            " WHERE u.aktif = 1 AND u.rol IN ('ogretmen', 'yonetici') AND u.id != ?"
            " AND (o.son_push IS NULL OR o.son_push < ?)",
            (yazar_id, sinir),
        )
    ]
    simdi = zaman.simdi_str()
    for i in ids:
        conn.execute(
            "INSERT INTO sohbet_okuma (kullanici_id, son_id, son_push) VALUES (?, 0, ?)"
            " ON CONFLICT(kullanici_id) DO UPDATE SET son_push = excluded.son_push",
            (i, simdi),
        )
    conn.commit()
    return ids


def bildir(yazar_id: int) -> None:
    """Arka plan görevi: kendi bağlantısını açar, asla istisna fırlatmaz."""
    if not push.etkin_mi():
        return
    try:
        conn = db.baglanti()
        try:
            push.gonder(conn, bildirim_alicilari(conn, yazar_id), "sohbet")
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        log.warning("sohbet bildirimi hatası: %s", type(e).__name__)
