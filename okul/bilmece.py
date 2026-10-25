"""Günün Bilmecesi (2026-10-25): her gün 08:00'de açılan, müfredat dışı tek soru (genel kültür / mantık).

Kurallar: öğrenci günde TEK cevap verir; o gün doğru/yanlış GÖSTERİLMEZ ("cevabın kaydedildi"), doğru şık istemciye
ertesi gün açıklanana kadar gitmez (cevap sınıfta yayılmasın). İlk çözen değil, gün içinde doğru çözen herkes aynı
ödülü alır: XP açıklamadan sonra, öğrencinin bir sonraki ana sayfa/bilmece ziyaretinde `odulleri_ver` ile yazılır
(defter (kullanıcı, 'bilmece', gün) tekil → tekrar yazılmaz). XP yalnızca 9-11 (Arena ile aynı); 12. sınıf da çözer.
Günün sorusu ilk istekte havuzdan seçilip `bilmece_gun`'e sabitlenir (gün boyu aynı kalır); havuz bitince en uzun
süredir sorulmamış olan yeniden gelir. Havuz boşsa kart görünmez.
"""

import json
import sqlite3
from datetime import timedelta

import arena
import zaman

ACILIS_SAATI = 8
XP = 10
SECENEK_EN_AZ, SECENEK_EN_COK = 2, 4
SORU_AZAMI, SECENEK_AZAMI, ACIKLAMA_AZAMI = 400, 120, 400


class BilmeceHatasi(Exception):
    def __init__(self, mesaj: str, kod: int = 400):
        super().__init__(mesaj)
        self.mesaj = mesaj
        self.kod = kod


def _bugun() -> str:
    return zaman.simdi().strftime("%Y-%m-%d")


def acik_mi() -> bool:
    return zaman.simdi().hour >= ACILIS_SAATI


def _kayit(r: sqlite3.Row, dogru_dahil: bool) -> dict:
    d = {"id": r["id"], "soru": r["soru"], "secenekler": json.loads(r["secenekler"])}
    if dogru_dahil:
        d["dogru"] = r["dogru"]
        d["aciklama"] = r["aciklama"]
    return d


def _gunun_idsi(conn: sqlite3.Connection, gun: str) -> int | None:
    r = conn.execute("SELECT bilmece_id FROM bilmece_gun WHERE gun = ?", (gun,)).fetchone()
    if r:
        return r[0]
    sec = conn.execute(
        "SELECT b.id FROM bilmece b LEFT JOIN (SELECT bilmece_id, MAX(gun) AS son FROM bilmece_gun GROUP BY bilmece_id) g"
        " ON g.bilmece_id = b.id WHERE b.aktif = 1 ORDER BY g.son IS NOT NULL, g.son, b.id LIMIT 1"
    ).fetchone()
    if sec is None:
        return None
    conn.execute("INSERT OR IGNORE INTO bilmece_gun (gun, bilmece_id) VALUES (?, ?)", (gun, sec[0]))
    conn.commit()
    return conn.execute("SELECT bilmece_id FROM bilmece_gun WHERE gun = ?", (gun,)).fetchone()[0]


def bugunku(conn: sqlite3.Connection, kid: int | None = None) -> dict | None:
    """Bugünün bilmecesi (doğru şık YOK) + 'secim' (öğrencinin cevabı|None); 08:00 öncesi ya da havuz boşsa None."""
    if not acik_mi():
        return None
    gun = _bugun()
    bid = _gunun_idsi(conn, gun)
    if bid is None:
        return None
    d = _kayit(conn.execute("SELECT * FROM bilmece WHERE id = ?", (bid,)).fetchone(), dogru_dahil=False)
    d["gun"] = gun
    d["secim"] = None
    if kid:
        r = conn.execute("SELECT secim FROM bilmece_cevap WHERE kullanici_id = ? AND gun = ?", (kid, gun)).fetchone()
        d["secim"] = r[0] if r else None
    return d


def cevapla(conn: sqlite3.Connection, kid: int, secim: int) -> None:
    """Günün tek cevabı. Doğru/yanlış bilgisi DÖNMEZ (ertesi gün açıklanır)."""
    b = bugunku(conn)
    if b is None:
        raise BilmeceHatasi("Bugünün bilmecesi henüz açılmadı.", 404)
    if not 0 <= secim < len(b["secenekler"]):
        raise BilmeceHatasi("Bir seçenek işaretle.")
    yazildi = conn.execute(
        "INSERT OR IGNORE INTO bilmece_cevap (kullanici_id, gun, secim, zaman) VALUES (?, ?, ?, ?)",
        (kid, b["gun"], secim, zaman.simdi_str()),
    ).rowcount
    conn.commit()
    if yazildi != 1:
        raise BilmeceHatasi("Bugünün bilmecesini zaten cevapladın. Sonuç yarın açıklanacak.", 409)


def onceki(conn: sqlite3.Connection, kid: int | None = None) -> dict | None:
    """Bugünden önceki son bilmece: doğru cevap + açıklama + katılım özeti (kimliksiz sayı) + öğrencinin kendi cevabı."""
    r = conn.execute(
        "SELECT g.gun, b.* FROM bilmece_gun g JOIN bilmece b ON b.id = g.bilmece_id WHERE g.gun < ? ORDER BY g.gun DESC LIMIT 1",
        (_bugun(),),
    ).fetchone()
    if r is None:
        return None
    d = _kayit(r, dogru_dahil=True)
    d["gun"] = r["gun"]
    d["cevaplayan"], d["dogru_sayisi"] = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(secim = ?), 0) FROM bilmece_cevap WHERE gun = ?", (r["dogru"], r["gun"])
    ).fetchone()
    d["secim"] = None
    if kid:
        c = conn.execute("SELECT secim FROM bilmece_cevap WHERE kullanici_id = ? AND gun = ?", (kid, r["gun"])).fetchone()
        d["secim"] = c[0] if c else None
    return d


def odulleri_ver(conn: sqlite3.Connection, kid: int, sinif: str) -> int:
    """Açıklanmış (bugünden önceki) günlerdeki doğru cevaplar için XP yazar; yazılan toplam. Tekrar çağrılabilir."""
    if not arena.duzey_uygun(sinif):
        return 0
    satirlar = conn.execute(
        "SELECT c.gun FROM bilmece_cevap c JOIN bilmece_gun g ON g.gun = c.gun JOIN bilmece b ON b.id = g.bilmece_id"
        " WHERE c.kullanici_id = ? AND c.gun < ? AND c.secim = b.dogru"
        " AND NOT EXISTS (SELECT 1 FROM bilgi_xp x WHERE x.kullanici_id = c.kullanici_id AND x.kaynak = 'bilmece' AND x.ref = c.gun)",
        (kid, _bugun()),
    ).fetchall()
    toplam = sum(XP for (gun,) in satirlar if arena.xp_ver(conn, kid, "bilmece", gun, XP))
    if toplam:
        conn.commit()
    return toplam


def kart(conn: sqlite3.Connection, ogrenci: sqlite3.Row) -> dict:
    """Öğrenci ana sayfası / bilmece sayfası: önce birikmiş ödülleri yazar, sonra bugünkü + önceki bilmece."""
    kid = ogrenci["kullanici_id"]
    yeni = odulleri_ver(conn, kid, ogrenci["sinif"]) if kid else 0
    return {
        "bugun": bugunku(conn, kid), "onceki": onceki(conn, kid), "yeni_xp": yeni,
        "xp": XP if arena.duzey_uygun(ogrenci["sinif"]) else 0, "acilis": f"{ACILIS_SAATI:02d}:00", "acik": acik_mi(),
    }


# --- yönetici: havuz ---


def dogrula(soru: str, secenekler: list[str], dogru: int, aciklama: str) -> tuple[str, list[str], str]:
    soru, aciklama = soru.strip(), aciklama.strip()
    secenekler = [s.strip() for s in secenekler if s and s.strip()]
    if not soru or len(soru) > SORU_AZAMI:
        raise BilmeceHatasi(f"Soru boş olamaz, en çok {SORU_AZAMI} karakter olabilir.")
    if not SECENEK_EN_AZ <= len(secenekler) <= SECENEK_EN_COK:
        raise BilmeceHatasi(f"{SECENEK_EN_AZ}-{SECENEK_EN_COK} seçenek yazın.")
    if any(len(s) > SECENEK_AZAMI for s in secenekler) or len(set(secenekler)) != len(secenekler):
        raise BilmeceHatasi(f"Seçenekler birbirinden farklı ve en çok {SECENEK_AZAMI} karakter olmalı.")
    if not 0 <= dogru < len(secenekler):
        raise BilmeceHatasi("Doğru seçeneği işaretleyin.")
    if len(aciklama) > ACIKLAMA_AZAMI:
        raise BilmeceHatasi(f"Açıklama en çok {ACIKLAMA_AZAMI} karakter olabilir.")
    return soru, secenekler, aciklama


def ekle(conn: sqlite3.Connection, soru: str, secenekler: list[str], dogru: int, aciklama: str = "", ekleyen_id: int | None = None) -> int:
    soru, secenekler, aciklama = dogrula(soru, secenekler, dogru, aciklama)
    if conn.execute("SELECT 1 FROM bilmece WHERE soru = ?", (soru,)).fetchone():
        raise BilmeceHatasi("Bu soru havuzda zaten var.", 409)
    cur = conn.execute(
        "INSERT INTO bilmece (soru, secenekler, dogru, aciklama, ekleyen_id, olusturma) VALUES (?, ?, ?, ?, ?, ?)",
        (soru, json.dumps(secenekler, ensure_ascii=False), dogru, aciklama, ekleyen_id, zaman.simdi_str()),
    )
    conn.commit()
    return cur.lastrowid


def aktif_ayarla(conn: sqlite3.Connection, bid: int, aktif: bool) -> bool:
    n = conn.execute("UPDATE bilmece SET aktif = ? WHERE id = ?", (1 if aktif else 0, bid)).rowcount
    conn.commit()
    return n > 0


def havuz(conn: sqlite3.Connection) -> list[dict]:
    """Yönetici listesi (en yeni önce), son sorulduğu günle."""
    sonuc = []
    for r in conn.execute(
        "SELECT b.*, (SELECT MAX(gun) FROM bilmece_gun g WHERE g.bilmece_id = b.id) AS son_gun FROM bilmece b ORDER BY b.id DESC"
    ):
        d = _kayit(r, dogru_dahil=True)
        d["aktif"], d["son_gun"] = bool(r["aktif"]), r["son_gun"]
        sonuc.append(d)
    return sonuc


def sorulmamis_sayisi(conn: sqlite3.Connection) -> int:
    """Hiç sorulmamış aktif bilmece sayısı (havuz azalınca yöneticiye uyarı)."""
    return conn.execute(
        "SELECT COUNT(*) FROM bilmece b WHERE b.aktif = 1 AND NOT EXISTS (SELECT 1 FROM bilmece_gun g WHERE g.bilmece_id = b.id)"
    ).fetchone()[0]


def gecmis(conn: sqlite3.Connection, gun_sayisi: int = 14) -> list[dict]:
    """Son günlerin bilmeceleri ve katılım (kimliksiz sayı)."""
    bas = (zaman.simdi() - timedelta(days=gun_sayisi)).strftime("%Y-%m-%d")
    return [
        dict(r)
        for r in conn.execute(
            "SELECT g.gun, b.soru, (SELECT COUNT(*) FROM bilmece_cevap c WHERE c.gun = g.gun) AS cevaplayan,"
            " (SELECT COUNT(*) FROM bilmece_cevap c WHERE c.gun = g.gun AND c.secim = b.dogru) AS dogru_sayisi"
            " FROM bilmece_gun g JOIN bilmece b ON b.id = g.bilmece_id WHERE g.gun >= ? ORDER BY g.gun DESC",
            (bas,),
        )
    ]
