"""Günün Teşekkürü (2026-10-25): öğretmen, gayret gösteren / derse katılan / yardımsever öğrencilere hazır şablonlu
Teşekkür Kartı gönderir; kartı öğrenci ve velisi görür.

Yalnızca SABİT şablonlar (serbest metin yok). Öğretmen yalnızca ders verdiği sınıfların öğrencilerine gönderir
(`yetki.ogrenci_gorebilir`; başkası → 404). Aynı öğretmen aynı öğrenciye günde en çok 1 kart (UNIQUE); öğretmen başına
günde en çok GUNLUK_OGRETMEN kart. Kart öğrenciye XP (avatar puanı) kazandırır: kart başına KART_XP, öğrenci başına günde
en çok GUNLUK_XP (yalnız 9-11, Arena ile aynı; 12. sınıf kartı görür ama XP yazılmaz). Teşekkür XP'si avatar seviyesine
sayılır ama haftalık XP yarışına/ödüle SAYILMAZ (`oduller._xp_toplamlari`): öğretmen tercihi yarışı etkilemesin.
"""

import sqlite3
from datetime import timedelta

import arena
import yetki
import zaman

# anahtar -> (simge, metin). Yeni şablon = buraya ekle; anahtar değişirse eski kartlar görünmez.
SABLONLAR = {
    "gayret": ("💪", "Bugün çok gayretliydin!"),
    "katilim": ("🙋", "Derse katılımın harikaydı!"),
    "yardim": ("🤝", "Yardımseverliğin için teşekkürler!"),
    "ozen": ("✨", "Çalışmana gösterdiğin özen için teşekkürler!"),
    "nezaket": ("🌱", "Nezaketin ve saygın için teşekkürler!"),
    "gelisim": ("📈", "Kendini geliştirdiğini görüyorum, bravo!"),
}
KART_XP = 5
GUNLUK_XP = 15  # öğrenci başına günde en çok teşekkür XP'si (3 kart)
GUNLUK_OGRETMEN = 60  # öğretmen başına günde en çok kart
GORUNUM_GUN = 60  # öğrenci/veli listesinde son kaç günün kartları


class TesekkurHatasi(Exception):
    def __init__(self, mesaj: str, kod: int = 400):
        super().__init__(mesaj)
        self.mesaj = mesaj
        self.kod = kod


def _xp_yaz(conn: sqlite3.Connection, ogrenci: sqlite3.Row, tid: int, gun: str) -> int:
    kid = ogrenci["kullanici_id"]
    if not kid or not arena.duzey_uygun(ogrenci["sinif"]):
        return 0
    bugunku = conn.execute(
        "SELECT COALESCE(SUM(miktar), 0) FROM bilgi_xp WHERE kullanici_id = ? AND kaynak = 'tesekkur' AND gun = ?", (kid, gun)
    ).fetchone()[0]
    miktar = min(KART_XP, GUNLUK_XP - bugunku)
    return miktar if miktar > 0 and arena.xp_ver(conn, kid, "tesekkur", str(tid), miktar) else 0


def gonder(conn: sqlite3.Connection, ogretmen: sqlite3.Row, ogrenci_idleri: list[int], sablon: str) -> list[int]:
    """Kartları yazar; yeni kart alan öğrenci id'lerini döner (bugün zaten aldıysa atlanır).
    Yetkisiz öğrenci → 404 (hiçbiri yazılmaz)."""
    if sablon not in SABLONLAR:
        raise TesekkurHatasi("Bir kart seçin.")
    idler = sorted(set(ogrenci_idleri))
    if not idler:
        raise TesekkurHatasi("En az bir öğrenci seçin.")
    if not all(yetki.ogrenci_gorebilir(conn, ogretmen, i) for i in idler):
        raise TesekkurHatasi("Öğrenci bulunamadı.", 404)
    simdi = zaman.simdi()
    gun = simdi.strftime("%Y-%m-%d")
    gonderilen = conn.execute("SELECT COUNT(*) FROM tesekkur WHERE ogretmen_id = ? AND gun = ?", (ogretmen["id"], gun)).fetchone()[0]
    if gonderilen + len(idler) > GUNLUK_OGRETMEN:
        raise TesekkurHatasi(f"Günde en çok {GUNLUK_OGRETMEN} kart gönderebilirsiniz (bugün {gonderilen}).", 429)
    yeni = []
    for oid in idler:
        cur = conn.execute(
            "INSERT OR IGNORE INTO tesekkur (ogretmen_id, ogrenci_id, sablon, gun, zaman) VALUES (?, ?, ?, ?, ?)",
            (ogretmen["id"], oid, sablon, gun, simdi.strftime(zaman.BICIM)),
        )
        if cur.rowcount == 1:
            _xp_yaz(conn, conn.execute("SELECT * FROM ogrenci WHERE id = ?", (oid,)).fetchone(), cur.lastrowid, gun)
            yeni.append(oid)
    conn.commit()
    return yeni


def _kart(r: sqlite3.Row) -> dict:
    simge, metin = SABLONLAR.get(r["sablon"], ("💌", "Teşekkürler!"))
    return {"id": r["id"], "simge": simge, "metin": metin, "sablon": r["sablon"], "gun": r["gun"], "zaman": r["zaman"],
            "ogretmen": r["ogretmen"], "xp": r["xp"] or 0}


def ogrenci_kartlari(conn: sqlite3.Connection, ogrenci: sqlite3.Row, gun_sayisi: int = GORUNUM_GUN, limit: int = 100) -> list[dict]:
    """Öğrencinin aldığı kartlar (en yeni önce): öğretmen adı + kazandırdığı XP."""
    bas = (zaman.simdi() - timedelta(days=gun_sayisi)).strftime("%Y-%m-%d")
    return [
        _kart(r)
        for r in conn.execute(
            "SELECT t.*, u.ad_soyad AS ogretmen, x.miktar AS xp FROM tesekkur t JOIN kullanici u ON u.id = t.ogretmen_id"
            " LEFT JOIN bilgi_xp x ON x.kaynak = 'tesekkur' AND x.ref = CAST(t.id AS TEXT) AND x.kullanici_id = ?"
            " WHERE t.ogrenci_id = ? AND t.gun >= ? ORDER BY t.id DESC LIMIT ?",
            (ogrenci["kullanici_id"] or 0, ogrenci["id"], bas, limit),
        )
    ]


def ozet(conn: sqlite3.Connection, ogrenci: sqlite3.Row, gun_sayisi: int = 7) -> dict:
    """Ana sayfa kartı: son günlerin kartları (en çok 3) + toplam sayı."""
    kartlar = ogrenci_kartlari(conn, ogrenci, gun_sayisi)
    return {"son": kartlar[:3], "sayi": len(kartlar)}


def bugun_gonderilen(conn: sqlite3.Connection, ogretmen_id: int) -> list[dict]:
    """Öğretmenin bugün gönderdiği kartlar (öğrenci adı/sınıfıyla)."""
    gun = zaman.simdi().strftime("%Y-%m-%d")
    return [
        {"ad": r["ad_soyad"], "sinif": r["sinif"], "simge": SABLONLAR.get(r["sablon"], ("💌", ""))[0],
         "metin": SABLONLAR.get(r["sablon"], ("", "Teşekkürler!"))[1], "ogrenci_id": r["ogrenci_id"]}
        for r in conn.execute(
            "SELECT t.*, o.ad_soyad, o.sinif FROM tesekkur t JOIN ogrenci o ON o.id = t.ogrenci_id"
            " WHERE t.ogretmen_id = ? AND t.gun = ? ORDER BY t.id DESC",
            (ogretmen_id, gun),
        )
    ]
