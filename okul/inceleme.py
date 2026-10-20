"""Öğretmenin günlük 5 soru incelemesi: kendi dersinden (9-11) havuz sorularını doğru/hatalı/pas diye işaretler.

Gün başına sabit set `soru_inceleme`ye yazılır (yenilemede değişmez). 'hatali' sonucu `soru_bildirim`e öğretmen
bildirimi olarak da yazılır (ağırlık 2: soru hemen gizlenir). 'dogru' yalnızca dahili iyi-soru sinyalidir;
soruhavuzu köprüsüne ve Postgres'e kişi bilgisi gitmez."""

import random
import sqlite3

import soru_bildirim
import yetki
import zaman
from kaynaklar import soru as havuz
from metin import sinif_seviyesi

GUNLUK = 5
SEVIYELER = (9, 10, 11)  # 12. sınıf donduruldu (kitaplar değişecek)
SONUCLAR = ("dogru", "hatali", "pas")

# ogretmen_gorev.ders (küçük harf, serbest metin) -> havuz ders kodu; ilk eşleşen anahtar kazanır.
_ESLEME = (
    ("edebiyat", "edebiyat"),
    ("din kültürü", "din"),
    ("peygamber", "din"),
    ("matematik", "matematik"),
    ("ingilizce", "ingilizce"),
    ("almanca", "almanca"),
    ("felsefe", "felsefe"),
    ("fizik", "fizik"),
    ("kimya", "kimya"),
    ("biyoloji", "biyoloji"),
    ("coğrafya", "cografya"),
    ("tarih", "tarih"),
    ("görsel", "gorsel_sanatlar"),
    ("bilişim", "bilisim"),
)


def havuz_kodu(ders: str) -> str | None:
    d = (ders or "").lower()
    for anahtar, kod in _ESLEME:
        if anahtar in d:
            return kod
    return None


def ciftler(conn: sqlite3.Connection, ogretmen_id: int) -> list[tuple[int, str]]:
    """Öğretmenin (sınıf seviyesi, havuz dersi) çiftleri; havuzda karşılığı olmayan ders/12. sınıf elenir."""
    sonuc = set()
    for sinif, ders in yetki.ogretmen_gorevleri(conn, ogretmen_id):
        kod = havuz_kodu(ders)
        try:
            sev = sinif_seviyesi(sinif)
        except ValueError:
            continue
        if kod and sev in SEVIYELER:
            sonuc.add((sev, kod))
    return sorted(sonuc)


def _gun() -> str:
    return zaman.simdi_str()[:10]


def kart(conn: sqlite3.Connection, k: sqlite3.Row) -> dict | None:
    """Ana sayfa kartı için özet; incelenecek dersi olmayan öğretmende None (Postgres'e dokunmaz)."""
    if k["rol"] != "ogretmen" or not ciftler(conn, k["id"]):
        return None
    yapilan, toplam = conn.execute(
        "SELECT count(sonuc), count(*) FROM soru_inceleme WHERE ogretmen_id = ? AND gun = ?", (k["id"], _gun())
    ).fetchone()
    return {"yapilan": yapilan, "toplam": toplam or GUNLUK}


def _goruldu_sayisi(conn: sqlite3.Connection, idler: list[int]) -> dict[int, int]:
    if not idler:
        return {}
    yer = ",".join("?" * len(idler))
    return dict(conn.execute(
        f"SELECT soru_id, count(*) FROM soru_inceleme WHERE sonuc IN ('dogru','hatali') AND soru_id IN ({yer})"
        " GROUP BY soru_id", idler,
    ).fetchall())


def gunun_seti(conn: sqlite3.Connection, k: sqlite3.Row) -> list[dict]:
    """Bugünün 5 sorusu. İlk çağrıda seçilip yazılır; ders eşleşmesi yoksa boş. KaynakHatasi yukarı gider."""
    gun = _gun()
    if conn.execute("SELECT 1 FROM soru_inceleme WHERE ogretmen_id = ? AND gun = ? LIMIT 1", (k["id"], gun)).fetchone() is None:
        _sec_ve_yaz(conn, k["id"], gun)
    satirlar = conn.execute(
        "SELECT sira, soru_id, sonuc FROM soru_inceleme WHERE ogretmen_id = ? AND gun = ? ORDER BY sira", (k["id"], gun)
    ).fetchall()
    sorular = havuz.getir_tam([s["soru_id"] for s in satirlar]) if satirlar else {}
    return [
        {**sorular[s["soru_id"]], "sira": s["sira"], "soru_id": s["soru_id"], "sonuc": s["sonuc"]}
        for s in satirlar
        if s["soru_id"] in sorular
    ]


def _sec_ve_yaz(conn: sqlite3.Connection, ogretmen_id: int, gun: str) -> None:
    cift = ciftler(conn, ogretmen_id)
    if not cift:
        return
    rng = random.Random(f"{ogretmen_id}:{gun}")
    gorulen = [r[0] for r in conn.execute("SELECT soru_id FROM soru_inceleme WHERE ogretmen_id = ?", (ogretmen_id,))]
    yasak = soru_bildirim.gizli_idler(conn)
    havuzlar = []
    for sev, kod in cift:
        adaylar = havuz.inceleme_adaylari(sev, kod, gorulen, yasak)
        sayi = _goruldu_sayisi(conn, [a["id"] for a in adaylar])
        rng.shuffle(adaylar)
        adaylar.sort(key=lambda a: sayi.get(a["id"], 0))  # kararlı: en az incelenen önce
        havuzlar.append(adaylar)
    secilen: list[int] = []
    i = rng.randrange(len(havuzlar))
    bos = 0
    while len(secilen) < GUNLUK and bos < len(havuzlar):
        h = havuzlar[i % len(havuzlar)]
        if h:
            secilen.append(h.pop(0)["id"])
            bos = 0
        else:
            bos += 1
        i += 1
    for sira, soru_id in enumerate(secilen, start=1):
        conn.execute(
            "INSERT OR IGNORE INTO soru_inceleme (ogretmen_id, gun, sira, soru_id) VALUES (?, ?, ?, ?)",
            (ogretmen_id, gun, sira, soru_id),
        )
    conn.commit()


class IncelemeHatasi(ValueError):
    pass


def isle(conn: sqlite3.Connection, k: sqlite3.Row, sira: int, sonuc: str, tur: str = "") -> None:
    """Bugünün `sira`. sorusunu işaretler (yalnız bir kez). sonuc='hatali' ise `tur` (sebep) zorunlu."""
    if sonuc not in SONUCLAR:
        raise IncelemeHatasi("Geçersiz seçim.")
    r = conn.execute(
        "SELECT soru_id, sonuc FROM soru_inceleme WHERE ogretmen_id = ? AND gun = ? AND sira = ?",
        (k["id"], _gun(), sira),
    ).fetchone()
    if r is None:
        raise IncelemeHatasi("Soru bulunamadı.")
    if r["sonuc"] is not None:
        raise IncelemeHatasi("Bu soruyu zaten işaretledin.")
    if sonuc == "hatali":
        try:
            soru_bildirim.bildir(conn, k["id"], r["soru_id"], tur, rol="ogretmen", kaynak="inceleme")
        except soru_bildirim.BildirimHatasi as e:
            raise IncelemeHatasi(str(e)) from e
    conn.execute(
        "UPDATE soru_inceleme SET sonuc = ?, zaman = ? WHERE ogretmen_id = ? AND gun = ? AND sira = ? AND sonuc IS NULL",
        (sonuc, zaman.simdi_str(), k["id"], _gun(), sira),
    )
    conn.commit()


def bugun_ozeti(conn: sqlite3.Connection) -> dict:
    """Yönetici: bugün kaç öğretmen kaç soru inceledi (kişi adı yok)."""
    ogretmen, soru, hatali = conn.execute(
        "SELECT count(DISTINCT ogretmen_id), count(sonuc), coalesce(sum(sonuc = 'hatali'), 0)"
        " FROM soru_inceleme WHERE gun = ?", (_gun(),)
    ).fetchone()
    return {"ogretmen": ogretmen, "soru": soru, "hatali": hatali}
