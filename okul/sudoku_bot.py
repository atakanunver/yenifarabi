"""Sudoku: botla tek oyunculu antrenman (2026-10-24).

Öğrenci bir bulmacayı çözer; bot "oynamaz", süresi ve hatası oyun BAŞLARKEN sunucuda belirlenip saklanır
(sayfa yenilense de değişmez, istemciye bitene kadar gitmez). Skor düelloyla aynı: süre + HATA_CEZA × hata,
düşük olan kazanır; sonuç bitirir bitirmez çıkar. Bot süresi öğrencinin son 5 çözümünün medyanına göre ayarlanır
(geçmiş yoksa zorluğa göre sabit). Puan: günde yalnızca İLK bot galibiyeti sınıf puanına sayılır (3 × zorluk çarpanı);
diğer oyunlar antrenmandır. Çözüm istemciye hiçbir yanıtta gitmez.
"""

import random
import secrets
import sqlite3
import statistics
from datetime import timedelta

import sudoku
import zaman
from sudoku import HATA_CEZA, SudokuHatasi

GUNLUK_BASLAT_EN_COK = 5
GUNLUK_PUANLI = 1  # günde en çok bu kadar bot galibiyeti puana sayılır
TERK_SAAT = 3  # bitmemiş oyun bu süreden sonra terk sayılır (yenisi başlatılabilir)
TABAN_SN = {"basit": 300, "orta": 480, "zor": 780}
EN_AZ_SN = {"basit": 120, "orta": 240, "zor": 420}
EN_COK_SN = {"basit": 900, "orta": 1500, "zor": 2400}
HATA_AGIRLIK = {"basit": (0.85, 0.13, 0.02), "orta": (0.70, 0.25, 0.05), "zor": (0.55, 0.35, 0.10)}  # 0/1/2 hata


def _gecmis_sureler(conn: sqlite3.Connection, kid: int, zorluk: str) -> list[int]:
    return [
        r[0] for r in conn.execute(
            "SELECT sure_sn FROM ("
            " SELECT bitis, sure_sn FROM sudoku_bot WHERE kullanici_id = ? AND zorluk = ? AND bitis IS NOT NULL"
            " UNION ALL"
            " SELECT o.bitis, o.sure_sn FROM sudoku_oyun o JOIN sudoku_duello d ON d.id = o.duello_id"
            "  WHERE o.kullanici_id = ? AND d.zorluk = ? AND o.bitis IS NOT NULL"
            ") ORDER BY bitis DESC LIMIT 5",
            (kid, zorluk, kid, zorluk),
        )
    ]


def bot_hedefi(conn: sqlite3.Connection, kid: int, zorluk: str, rnd: random.Random) -> tuple[int, int]:
    """(bot süresi sn, bot hatası): öğrencinin geçmiş medyanı (yoksa taban) ±%15, zorluğa göre sınırlı."""
    gecmis = _gecmis_sureler(conn, kid, zorluk)
    hedef = statistics.median(gecmis) if gecmis else TABAN_SN[zorluk]
    sure = int(hedef * rnd.uniform(0.85, 1.15))
    sure = max(EN_AZ_SN[zorluk], min(EN_COK_SN[zorluk], sure))
    hata = rnd.choices([0, 1, 2], weights=HATA_AGIRLIK[zorluk])[0]
    return sure, hata


def baslat(conn: sqlite3.Connection, kid: int, zorluk: str, rnd: random.Random | None = None) -> int:
    """Yeni bot oyunu açar; açık (terk edilmemiş) oyun varsa ONU döner (bot süresi yeniden çekilemesin)."""
    if zorluk not in sudoku.ZORLUK:
        raise SudokuHatasi("Geçersiz zorluk.")
    simdi = zaman.simdi()
    esik = (simdi - timedelta(hours=TERK_SAAT)).strftime(zaman.BICIM)
    acik = conn.execute(
        "SELECT id FROM sudoku_bot WHERE kullanici_id = ? AND bitis IS NULL AND baslama > ? ORDER BY id DESC LIMIT 1",
        (kid, esik),
    ).fetchone()
    if acik:
        return acik["id"]
    gun = simdi.strftime("%Y-%m-%d")
    if conn.execute(
        "SELECT COUNT(*) FROM sudoku_bot WHERE kullanici_id = ? AND substr(baslama, 1, 10) = ?", (kid, gun)
    ).fetchone()[0] >= GUNLUK_BASLAT_EN_COK:
        raise SudokuHatasi(f"Günde en çok {GUNLUK_BASLAT_EN_COK} bot oyunu başlatabilirsin.")
    bulmaca, cozum = sudoku.uret(secrets.randbits(32), zorluk)
    bot_sure, bot_hata = bot_hedefi(conn, kid, zorluk, rnd or random.Random())
    cur = conn.execute(
        "INSERT INTO sudoku_bot (kullanici_id, zorluk, bulmaca, cozum, baslama, hata, bot_sure_sn, bot_hata)"
        " VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
        (kid, zorluk, bulmaca, cozum, zaman.simdi_str(), bot_sure, bot_hata),
    )
    conn.commit()
    return cur.lastrowid


def getir(conn: sqlite3.Connection, oyun_id: int, kid: int) -> sqlite3.Row | None:
    """Yalnızca oyunun sahibi görür (başkasınınki None -> 404)."""
    return conn.execute("SELECT * FROM sudoku_bot WHERE id = ? AND kullanici_id = ?", (oyun_id, kid)).fetchone()


def skor(o: sqlite3.Row) -> int | None:
    return o["sure_sn"] + HATA_CEZA * o["hata"] if o["bitis"] else None


def bot_skoru(o: sqlite3.Row) -> int:
    return o["bot_sure_sn"] + HATA_CEZA * o["bot_hata"]


def gonder(conn: sqlite3.Connection, oyun_id: int, kid: int, tahta: str) -> dict:
    """Dolu tahtayı doğrular. Yanlışsa {'dogru': False, 'hata': n}; doğruysa sonucu da yazar ve döner."""
    o = getir(conn, oyun_id, kid)
    if o is None:
        raise SudokuHatasi("Oyun bulunamadı.")
    if o["bitis"]:
        raise SudokuHatasi("Bu oyunu zaten bitirdin.")
    tahta = (tahta or "").strip()
    if len(tahta) != 81 or not tahta.isascii() or not tahta.isdigit() or "0" in tahta:
        raise SudokuHatasi("Tahtayı tamamen doldur.")
    if tahta != o["cozum"]:
        conn.execute("UPDATE sudoku_bot SET hata = hata + 1 WHERE id = ? AND bitis IS NULL", (oyun_id,))
        conn.commit()
        return {"dogru": False, "hata": getir(conn, oyun_id, kid)["hata"]}
    simdi = zaman.simdi_str()
    sure = max(0, int((sudoku._dt(simdi) - sudoku._dt(o["baslama"])).total_seconds()))
    benim = sure + HATA_CEZA * o["hata"]
    bot = bot_skoru(o)
    sonuc = "galibiyet" if benim < bot else "maglubiyet" if benim > bot else "beraberlik"
    conn.execute(
        "UPDATE sudoku_bot SET bitis = ?, sure_sn = ?, sonuc = ? WHERE id = ? AND bitis IS NULL", (simdi, sure, sonuc, oyun_id)
    )
    conn.commit()
    return {"dogru": True, "hata": o["hata"], "sure_sn": sure, "skor": benim, "bot_skor": bot, "sonuc": sonuc}


def _puanli_idler(conn: sqlite3.Connection) -> dict[int, tuple[int, str, str, str]]:
    """{oyun_id: (kid, gun, zorluk, bitis)} — kullanıcı başına günün ilk GUNLUK_PUANLI galibiyeti (id sırasıyla)."""
    sayac: dict[tuple[int, str], int] = {}
    cikti = {}
    for r in conn.execute(
        "SELECT id, kullanici_id AS kid, zorluk, bitis FROM sudoku_bot WHERE sonuc = 'galibiyet' ORDER BY id"
    ):
        anahtar = (r["kid"], r["bitis"][:10])
        sayac[anahtar] = sayac.get(anahtar, 0) + 1
        if sayac[anahtar] <= GUNLUK_PUANLI:
            cikti[r["id"]] = (r["kid"], r["bitis"][:10], r["zorluk"], r["bitis"])
    return cikti


def kazanc(conn: sqlite3.Connection, o: sqlite3.Row) -> int:
    """Bu oyunun sınıf puanına yazdığı puan (günün ilk galibiyeti değilse ya da kazanılmadıysa 0)."""
    if o["sonuc"] != "galibiyet" or o["id"] not in _puanli_idler(conn):
        return 0
    return sudoku.PUAN["galibiyet"] * sudoku.CARPAN[o["zorluk"]]


def puanlar_ekle(conn: sqlite3.Connection, cikti: dict[int, dict], hb: str | None, son: str | None) -> None:
    """`sudoku._puanlar` çıktısına bot galibiyetlerini ekler (hb..son haftası; None = tüm zamanlar)."""
    for kid, gun, zorluk, _bitis in _puanli_idler(conn).values():
        if hb is not None and not (hb <= gun < son):
            continue
        v = cikti.setdefault(kid, {"puan": 0, "galibiyet": 0, "oynanan": 0})
        v["puan"] += sudoku.PUAN["galibiyet"] * sudoku.CARPAN[zorluk]
        v["galibiyet"] += 1
        v["oynanan"] += 1


def ozet(conn: sqlite3.Connection, kid: int) -> dict:
    """Ana sayfa kartı: açık oyun, son 5 bitmiş oyun, bugün kalan başlatma hakkı, bugün puan yazıldı mı."""
    simdi = zaman.simdi()
    esik = (simdi - timedelta(hours=TERK_SAAT)).strftime(zaman.BICIM)
    gun = simdi.strftime("%Y-%m-%d")
    acik = conn.execute(
        "SELECT id, zorluk FROM sudoku_bot WHERE kullanici_id = ? AND bitis IS NULL AND baslama > ? ORDER BY id DESC LIMIT 1",
        (kid, esik),
    ).fetchone()
    biten = [
        {**dict(r), "zorluk_ad": sudoku.ZORLUK_AD[r["zorluk"]], "benim_skor": skor(r), "bot_skor": bot_skoru(r)}
        for r in conn.execute(
            "SELECT id, zorluk, sure_sn, hata, bot_sure_sn, bot_hata, sonuc, bitis, bulmaca FROM sudoku_bot"
            " WHERE kullanici_id = ? AND bitis IS NOT NULL ORDER BY id DESC LIMIT 5",
            (kid,),
        )
    ]
    for b in biten:
        b.pop("bulmaca")
    bugun_baslayan = conn.execute(
        "SELECT COUNT(*) FROM sudoku_bot WHERE kullanici_id = ? AND substr(baslama, 1, 10) = ?", (kid, gun)
    ).fetchone()[0]
    puanli_bugun = any(v[0] == kid and v[1] == gun for v in _puanli_idler(conn).values())
    return {
        "acik": dict(acik) if acik else None, "biten": biten, "puanli_bugun": puanli_bugun,
        "kalan": max(0, GUNLUK_BASLAT_EN_COK - bugun_baslayan),
    }
