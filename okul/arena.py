"""Bilgi Arenası: Günlük Görev (5 soru, süre sınırı yok, günde bir) + ortak XP / seviye / rozet katmanı.

Hızlı Mod (Soru Maratonu) aynı XP defterini besler (maraton_xp). Toplam XP ve seviye saklanmaz,
`bilgi_xp` defterinden türetilir; defterde (kullanıcı, kaynak, ref) tekildir, böylece tekrar gönderim
ya da yeniden yükleme ikinci kez ödül vermez. Doğru şık istemciye cevaptan önce gitmez.
Kazanım eşleşmesi havuzda çoğunlukla otomatik atanmıştır: ekranda "tahmini" olarak sunulur.
"""

import json
import sqlite3
import zlib
from datetime import timedelta

import maraton
import soru_bildirim
import zaman
from kaynaklar import KaynakHatasi, arena_soru
from kaynaklar import soru as havuz

SORU_SAYISI = 5
DAKIKA = 4  # ekranda gösterilen tahmini süre
MIN_DUZEY, MAX_DUZEY = 9, 11  # 12. sınıf donduruldu
XP_DOGRU = 10
XP_BONUS = 10  # görevi tamamlama
MARATON_XP_DOGRU = 10
MARATON_GUNLUK_TUR = 5
# seviye n (1'den başlar) XP eşiği = ESIKLER[n-1]
ESIKLER = [0, 50, 120, 220, 350, 520, 740, 1000, 1300, 1650]

ROZETLER = [
    ("ilk_tur", "İlk Arena Turu", "İlk Günlük Görevini tamamladın."),
    ("bes_gun", "Beş Gün Katılım", "5 farklı günde Günlük Görev tamamladın."),
    ("elli_dogru", "İlk 50 Doğru", "Arena'da toplam 50 soruyu doğru yanıtladın."),
    (
        "kazanim_ustasi",
        "Kazanım Ustası",
        "Aynı kazanımda en az 3 ayrı günde, en az 6 soruda %80 ve üzeri başarı (tahmini eşleşme).",
    ),
    ("hedef_ilk", "İlk Haftalık Hedef", "Koyduğun haftalık çalışma hedefine ulaştın."),
    ("hedef_uc", "Üç Haftalık Hedef", "3 farklı haftada kendi koyduğun hedefe ulaştın."),
]
_ROZET_AD = {k: a for k, a, _ in ROZETLER}


class ArenaHatasi(Exception):
    pass


# --- XP / seviye ---


def toplam_xp(conn: sqlite3.Connection, kullanici_id: int) -> int:
    return conn.execute(
        "SELECT COALESCE(SUM(miktar), 0) FROM bilgi_xp WHERE kullanici_id = ?", (kullanici_id,)
    ).fetchone()[0]


def seviye_hesapla(xp: int) -> dict:
    """{no, xp, bu_baslangic, sonraki|None}; no ESIKLER'e göre 1'den başlar."""
    no = 1
    for i, esik in enumerate(ESIKLER, 1):
        if xp >= esik:
            no = i
    sonraki = ESIKLER[no] if no < len(ESIKLER) else None
    return {"no": no, "xp": xp, "bu_baslangic": ESIKLER[no - 1], "sonraki": sonraki}


def seviye(conn: sqlite3.Connection, kullanici_id: int) -> dict:
    return seviye_hesapla(toplam_xp(conn, kullanici_id))


def xp_ver(conn: sqlite3.Connection, kullanici_id: int, kaynak: str, ref: str, miktar: int) -> bool:
    """Defter satırı ekler (commit etmez). Aynı (kullanıcı, kaynak, ref) ikinci kez eklenmez → False."""
    if miktar <= 0:
        return False
    simdi = zaman.simdi()
    return (
        conn.execute(
            "INSERT OR IGNORE INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (kullanici_id, kaynak, ref, miktar, simdi.strftime("%Y-%m-%d"), zaman.simdi_str()),
        ).rowcount
        == 1
    )


# --- Günlük görev ---


def bugun() -> str:
    return zaman.simdi().strftime("%Y-%m-%d")


def duzey_uygun(sinif: str) -> bool:
    try:
        return MIN_DUZEY <= maraton.duzey(sinif) <= MAX_DUZEY
    except (ValueError, IndexError):
        return False


def tur_getir(conn: sqlite3.Connection, tur_id: int, kullanici_id: int) -> sqlite3.Row | None:
    """Yalnızca kendi turu; başkasınınki None (rota 404 verir)."""
    return conn.execute(
        "SELECT * FROM bilgi_tur WHERE id = ? AND kullanici_id = ?", (tur_id, kullanici_id)
    ).fetchone()


def bugunku_tur(conn: sqlite3.Connection, kullanici_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM bilgi_tur WHERE kullanici_id = ? AND gun = ?", (kullanici_id, bugun())
    ).fetchone()


def cevaplanan(conn: sqlite3.Connection, tur_id: int) -> int:
    return conn.execute(
        "SELECT count(*) FROM bilgi_cevap WHERE tur_id = ? AND cevap IS NOT NULL", (tur_id,)
    ).fetchone()[0]


def _gorulen(conn: sqlite3.Connection, kullanici_id: int) -> dict[int, int]:
    """Arena + Maraton'da görülen soru_id -> sayı (aynı soruyu art arda sunmamak için)."""
    g = dict(maraton.gorulme(conn, kullanici_id))
    for soru_id, n in conn.execute(
        "SELECT c.soru_id, count(*) FROM bilgi_cevap c JOIN bilgi_tur t ON t.id = c.tur_id"
        " WHERE t.kullanici_id = ? GROUP BY c.soru_id",
        (kullanici_id,),
    ):
        g[soru_id] = g.get(soru_id, 0) + n
    return g


def gunun_dersi(kullanici_id: int, gun: str, dersler: list[str]) -> str:
    """Gün + kullanıcıya göre kararlı seçim (aynı gün sayfa yenilense de değişmez)."""
    return sorted(dersler)[zlib.crc32(f"{kullanici_id}:{gun}".encode()) % len(dersler)]


def gorev_durumu(conn: sqlite3.Connection, kullanici_id: int, sinif: str) -> dict:
    """Merkez ekran kartı için durum. Havuz erişilemezse 'kaynak_yok' (diğer kartlar çalışır)."""
    temel = {"soru_sayisi": SORU_SAYISI, "dk": DAKIKA}
    tur = bugunku_tur(conn, kullanici_id)
    if tur is not None:
        if tur["durum"] == "tamam":
            return {**temel, "durum": "tamam", "tur_id": tur["id"], "dogru": tur["dogru"], "xp": tur["xp"]}
        return {
            **temel, "durum": "devam", "tur_id": tur["id"], "cevaplanan": cevaplanan(conn, tur["id"]),
        }
    kilit = maraton.kilit()
    if kilit:
        return {**temel, "durum": "kilit", "kilit_bit": kilit["bit"]}
    try:
        if not dersler_uygun(sinif):
            return {**temel, "durum": "yetersiz"}
    except KaynakHatasi:
        return {**temel, "durum": "kaynak_yok"}
    return {**temel, "durum": "hazir"}


def dersler_uygun(sinif: str) -> list[str]:
    """Bu düzeyde en az MIN_SORU onaylı sorusu olan ders kodları."""
    if not duzey_uygun(sinif):
        return []
    return [kod for kod, _ in havuz.dersler(maraton.duzey(sinif))]


def baslat(conn: sqlite3.Connection, kullanici_id: int, sinif: str) -> int:
    """Bugünün görevini başlatır; zaten varsa mevcut turun id'sini döner (ikinci tur/ödül yok)."""
    mevcut = bugunku_tur(conn, kullanici_id)
    if mevcut is not None:
        return mevcut["id"]
    if not duzey_uygun(sinif):
        raise ArenaHatasi("Günlük Görev bu sınıf düzeyi için açık değil.")
    if maraton.kilit():
        raise ArenaHatasi("Ders sırasında kapalı.")
    dersler = dersler_uygun(sinif)  # KaynakHatasi yukarı geçer
    if not dersler:
        raise ArenaHatasi("Bu düzey için yeterli soru yok.")
    gun = bugun()
    ders = gunun_dersi(kullanici_id, gun, dersler)
    g = _gorulen(conn, kullanici_id)
    sorular = arena_soru.sorular(maraton.duzey(sinif), ders, list(g), SORU_SAYISI, g, soru_bildirim.gizli_idler(conn))
    if len(sorular) < SORU_SAYISI:
        raise ArenaHatasi("Bu derste yeterli soru yok.")
    # dünden kalan yarım tur: kapatılır (ödül gün içinde cevaplananlar için zaten verildi)
    conn.execute(
        "UPDATE bilgi_tur SET durum = 'terk', bitis = ? WHERE kullanici_id = ? AND durum = 'acik'",
        (zaman.simdi_str(), kullanici_id),
    )
    try:
        cur = conn.execute(
            "INSERT INTO bilgi_tur (kullanici_id, gun, sinif, ders, basla) VALUES (?, ?, ?, ?, ?)",
            (kullanici_id, gun, sinif, ders, zaman.simdi_str()),
        )
    except sqlite3.IntegrityError:  # paralel istek aynı anda başlattı
        conn.rollback()
        return bugunku_tur(conn, kullanici_id)["id"]
    tid = cur.lastrowid
    conn.executemany(
        "INSERT INTO bilgi_cevap (tur_id, sira, soru_id, kazanim_id, kazanim_kod, kazanim_metin,"
        " soru, secenekler, dogru_index, konu) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (tid, i, s["id"], s["kazanim_id"], s["kazanim_kod"], s["kazanim_metin"], s["soru"],
             json.dumps(s["secenekler"], ensure_ascii=False), s["dogru_index"], s["konu"])
            for i, s in enumerate(sorular, 1)
        ],
    )
    conn.commit()
    return tid


def siradaki(conn: sqlite3.Connection, tur_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM bilgi_cevap WHERE tur_id = ? AND cevap IS NULL ORDER BY sira LIMIT 1",
        (tur_id,),
    ).fetchone()


def soru_getir(conn: sqlite3.Connection, tur_id: int, sira: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM bilgi_cevap WHERE tur_id = ? AND sira = ?", (tur_id, sira)
    ).fetchone()


def sorular(conn: sqlite3.Connection, tur_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM bilgi_cevap WHERE tur_id = ? ORDER BY sira", (tur_id,)
    ).fetchall()


def kareler(conn: sqlite3.Connection, tur_id: int) -> list[str]:
    return [
        "bos" if r["cevap"] is None or r["cevap"] in (maraton.PAS, maraton.HATALI)
        else ("dogru" if r["cevap"] == r["dogru_index"] else "yanlis")
        for r in sorular(conn, tur_id)
    ]


def cevapla(conn: sqlite3.Connection, tur_id: int, sira: int, secim: int) -> dict:
    """Sıradaki soruyu puanlar. `cevap IS NULL` koşulu çift gönderimi/paralel isteği engeller
    (ikinci istek ArenaHatasi, XP yok). Son soruda tur tek işlemde kapanır, bonus ve rozetler işlenir."""
    tur = conn.execute("SELECT * FROM bilgi_tur WHERE id = ?", (tur_id,)).fetchone()
    if tur is None or tur["durum"] != "acik":
        raise ArenaHatasi("Bu görev kapalı.")
    s = siradaki(conn, tur_id)
    if s is None or s["sira"] != sira:
        raise ArenaHatasi("Bu soru zaten cevaplanmış.")
    if not 0 <= secim < len(json.loads(s["secenekler"])):
        raise ArenaHatasi("Geçersiz şık.")
    if conn.execute(
        "UPDATE bilgi_cevap SET cevap = ?, cevap_zamani = ? WHERE tur_id = ? AND sira = ? AND cevap IS NULL",
        (secim, zaman.simdi_str(), tur_id, sira),
    ).rowcount != 1:
        conn.rollback()
        raise ArenaHatasi("Bu soru zaten cevaplanmış.")
    dogru = secim == s["dogru_index"]
    eski_seviye = seviye(conn, tur["kullanici_id"])["no"]
    kazanilan = 0
    if dogru:
        conn.execute("UPDATE bilgi_tur SET dogru = dogru + 1 WHERE id = ?", (tur_id,))
        if xp_ver(conn, tur["kullanici_id"], "arena_dogru", f"{tur_id}:{sira}", XP_DOGRU):
            kazanilan += XP_DOGRU
    bitti = siradaki(conn, tur_id) is None
    yeni_rozet: list[str] = []
    if bitti:
        if xp_ver(conn, tur["kullanici_id"], "arena_bonus", str(tur_id), XP_BONUS):
            kazanilan += XP_BONUS
        conn.execute(
            "UPDATE bilgi_tur SET durum = 'tamam', bitis = ? WHERE id = ? AND durum = 'acik'",
            (zaman.simdi_str(), tur_id),
        )
    if kazanilan:
        conn.execute("UPDATE bilgi_tur SET xp = xp + ? WHERE id = ?", (kazanilan, tur_id))
    if bitti:
        yeni_rozet = rozet_kontrol(conn, tur["kullanici_id"])
    conn.commit()
    yeni = seviye(conn, tur["kullanici_id"])
    return {
        "dogru": dogru,
        "dogru_index": s["dogru_index"],
        "bitti": bitti,
        "xp": kazanilan,
        "yeni_rozetler": [{"ad": _ROZET_AD[k]} for k in yeni_rozet],
        "seviye_atladi": yeni["no"] if yeni["no"] > eski_seviye else None,
    }


ARENA_PAS_HAKKI = 1  # Günlük Görev başına


def pas_kalan(conn: sqlite3.Connection, tur_id: int) -> int:
    return max(0, ARENA_PAS_HAKKI - conn.execute(
        "SELECT count(*) FROM bilgi_cevap WHERE tur_id = ? AND cevap = ?", (tur_id, maraton.PAS)
    ).fetchone()[0])


def gec(conn: sqlite3.Connection, tur_id: int, sira: int, hatali: bool = False) -> dict:
    """Sıradaki soruyu puansız geçer (pas: hak sınırlı; hatalı: bildirimi çağıran yazar). XP yok; son soruda tur kapanır
    ve bitiş bonusu yalnızca en az bir soru gerçekten cevaplandıysa verilir."""
    tur = conn.execute("SELECT * FROM bilgi_tur WHERE id = ?", (tur_id,)).fetchone()
    if tur is None or tur["durum"] != "acik":
        raise ArenaHatasi("Bu görev kapalı.")
    s = siradaki(conn, tur_id)
    if s is None or s["sira"] != sira:
        raise ArenaHatasi("Bu soru zaten cevaplanmış.")
    if not hatali and pas_kalan(conn, tur_id) <= 0:
        raise ArenaHatasi("Pas hakkın bitti.")
    if conn.execute(
        "UPDATE bilgi_cevap SET cevap = ?, cevap_zamani = ? WHERE tur_id = ? AND sira = ? AND cevap IS NULL",
        (maraton.HATALI if hatali else maraton.PAS, zaman.simdi_str(), tur_id, sira),
    ).rowcount != 1:
        conn.rollback()
        raise ArenaHatasi("Bu soru zaten cevaplanmış.")
    bitti = siradaki(conn, tur_id) is None
    if bitti:
        kazanilan = 0
        if conn.execute(
            "SELECT 1 FROM bilgi_cevap WHERE tur_id = ? AND cevap >= 0 LIMIT 1", (tur_id,)
        ).fetchone() and xp_ver(conn, tur["kullanici_id"], "arena_bonus", str(tur_id), XP_BONUS):
            kazanilan = XP_BONUS
        conn.execute(
            "UPDATE bilgi_tur SET durum = 'tamam', bitis = ?, xp = xp + ? WHERE id = ? AND durum = 'acik'",
            (zaman.simdi_str(), kazanilan, tur_id),
        )
        rozet_kontrol(conn, tur["kullanici_id"])
    conn.commit()
    return {"bitti": bitti}


def seviye_atladi(conn: sqlite3.Connection, kid: int, tur: sqlite3.Row) -> int | None:
    """Bu turda seviye atlandıysa yeni seviye no (tur başındaki XP = toplam - tur XP'si)."""
    toplam = toplam_xp(conn, kid)
    once = seviye_hesapla(toplam - tur["xp"])["no"]
    simdi = seviye_hesapla(toplam)["no"]
    return simdi if simdi > once else None


# --- Rozetler ---


def _rozet_kosullari(conn: sqlite3.Connection, kid: int) -> set[str]:
    k: set[str] = set()
    tamam, dogru = conn.execute(
        "SELECT count(*), COALESCE(SUM(dogru), 0) FROM bilgi_tur WHERE kullanici_id = ? AND durum = 'tamam'",
        (kid,),
    ).fetchone()
    if tamam >= 1:
        k.add("ilk_tur")
    if tamam >= 5:  # UNIQUE(kullanici_id, gun): her tamam tur ayrı bir gündür
        k.add("bes_gun")
    if dogru >= 50:
        k.add("elli_dogru")
    # Kazanım Ustası: kazanım eşleşmesi tahminidir; tek doğru cevap kalıcı edinim sayılmaz
    if conn.execute(
        "SELECT 1 FROM bilgi_cevap c JOIN bilgi_tur t ON t.id = c.tur_id"
        " WHERE t.kullanici_id = ? AND c.kazanim_id IS NOT NULL AND c.cevap >= 0"
        " GROUP BY c.kazanim_id HAVING count(DISTINCT t.gun) >= 3 AND count(*) >= 6"
        " AND 1.0 * SUM(c.cevap = c.dogru_index) / count(*) >= 0.8 LIMIT 1",
        (kid,),
    ).fetchone():
        k.add("kazanim_ustasi")
    return k


def rozet_kontrol(conn: sqlite3.Connection, kid: int) -> list[str]:
    """Yeni kazanılan rozet kodları (commit etmez). INSERT OR IGNORE: aynı rozet iki kez verilmez."""
    yeni = []
    for kod in sorted(_rozet_kosullari(conn, kid)):
        if conn.execute(
            "INSERT OR IGNORE INTO bilgi_rozet (kullanici_id, rozet_kodu, zaman) VALUES (?, ?, ?)",
            (kid, kod, zaman.simdi_str()),
        ).rowcount == 1:
            yeni.append(kod)
    return yeni


def rozetler(conn: sqlite3.Connection, kid: int) -> list[dict]:
    kazanilan = {
        r["rozet_kodu"]: r["zaman"]
        for r in conn.execute("SELECT rozet_kodu, zaman FROM bilgi_rozet WHERE kullanici_id = ?", (kid,))
    }
    return [
        {"kod": k, "ad": a, "aciklama": ac, "kazanildi": k in kazanilan, "tarih": kazanilan.get(k)}
        for k, a, ac in ROZETLER
    ]


# --- Hızlı Mod (Maraton) XP kancası ---


def maraton_xp(conn: sqlite3.Connection, kid: int, maraton_id: int) -> int:
    """Tamamlanmış (terk edilmemiş) Maraton turu için XP: doğru x 10, günde en çok 5 tur.
    Idempotenttir: aynı tur için ikinci çağrı 0 döner. Geçmiş turlar geriye dönük işlenmez
    (yalnızca çağrıldığında). Düzey dışı (12. sınıf) XP almaz. Commit eder."""
    m = conn.execute(
        "SELECT * FROM maraton WHERE id = ? AND kullanici_id = ?", (maraton_id, kid)
    ).fetchone()
    if m is None or not m["bitis"] or not MIN_DUZEY <= m["duzey"] <= MAX_DUZEY:
        return 0
    if conn.execute(
        "SELECT 1 FROM maraton_soru WHERE maraton_id = ? AND cevap = ?", (maraton_id, maraton.TERK)
    ).fetchone():
        return 0
    gun = m["bitis"][:10]
    if conn.execute(
        "SELECT 1 FROM bilgi_xp WHERE kullanici_id = ? AND kaynak = 'maraton_tur' AND ref = ?",
        (kid, str(maraton_id)),
    ).fetchone():
        return 0
    sayi = conn.execute(
        "SELECT count(*) FROM bilgi_xp WHERE kullanici_id = ? AND kaynak = 'maraton_tur' AND gun = ?",
        (kid, gun),
    ).fetchone()[0]
    if sayi >= MARATON_GUNLUK_TUR:
        return 0
    miktar = m["dogru"] * MARATON_XP_DOGRU
    if miktar <= 0:
        return 0
    conn.execute(
        "INSERT OR IGNORE INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman)"
        " VALUES (?, 'maraton_tur', ?, ?, ?, ?)",
        (kid, str(maraton_id), miktar, gun, zaman.simdi_str()),
    )
    conn.commit()
    return miktar


def maraton_xp_miktar(conn: sqlite3.Connection, kid: int, maraton_id: int) -> int:
    """Bu Maraton turundan daha önce yazılmış XP (yoksa 0): sonuç ekranında gösterim için."""
    r = conn.execute(
        "SELECT miktar FROM bilgi_xp WHERE kullanici_id = ? AND kaynak = 'maraton_tur' AND ref = ?",
        (kid, str(maraton_id)),
    ).fetchone()
    return r[0] if r else 0


# --- Ekran verileri ---


def son_tur(conn: sqlite3.Connection, kid: int) -> dict | None:
    r = conn.execute(
        "SELECT gun, dogru, xp FROM bilgi_tur WHERE kullanici_id = ? AND durum = 'tamam'"
        " ORDER BY gun DESC LIMIT 1",
        (kid,),
    ).fetchone()
    return {"gun": r["gun"], "dogru": r["dogru"], "soru_sayisi": SORU_SAYISI, "xp": r["xp"]} if r else None


def hafta_ozeti(conn: sqlite3.Connection, kid: int) -> dict | None:
    simdi = zaman.simdi()
    pazartesi = (simdi - timedelta(days=simdi.weekday())).strftime("%Y-%m-%d")
    r = conn.execute(
        "SELECT count(*), COALESCE(SUM(dogru), 0), COALESCE(SUM(xp), 0) FROM bilgi_tur"
        " WHERE kullanici_id = ? AND durum = 'tamam' AND gun >= ?",
        (kid, pazartesi),
    ).fetchone()
    return {"tur": r[0], "dogru": r[1], "xp": r[2]} if r[0] else None


_GUN = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]


def gunler(conn: sqlite3.Connection, kid: int) -> list[dict]:
    """Son 7 gün (bugün dahil, eskiden yeniye): görev tamamlandı mı."""
    simdi = zaman.simdi()
    liste = [simdi - timedelta(days=i) for i in range(6, -1, -1)]
    tamam = {
        r[0]
        for r in conn.execute(
            "SELECT gun FROM bilgi_tur WHERE kullanici_id = ? AND durum = 'tamam' AND gun >= ?",
            (kid, liste[0].strftime("%Y-%m-%d")),
        )
    }
    return [
        {"ad": _GUN[d.weekday()], "tamam": d.strftime("%Y-%m-%d") in tamam, "bugun": i == 6}
        for i, d in enumerate(liste)
    ]


def kazanim_ozeti(conn: sqlite3.Connection, tur_id: int) -> list[dict]:
    """Tur içindeki kazanım başına doğru/toplam (tahmini eşleşme)."""
    return [
        dict(r)
        for r in conn.execute(
            "SELECT kazanim_kod AS kod, kazanim_metin AS metin, SUM(cevap = dogru_index) AS dogru,"
            " count(*) AS toplam FROM bilgi_cevap WHERE tur_id = ? AND kazanim_id IS NOT NULL AND cevap >= 0"
            " GROUP BY kazanim_id ORDER BY kazanim_kod",
            (tur_id,),
        )
    ]


def kazanim_calismalari(conn: sqlite3.Connection, kid: int, n: int = 8) -> list[dict]:
    """Arena'da çalışılan kazanımlar (en çok soru çözülenden), tahmini eşleşme."""
    return [
        dict(r)
        for r in conn.execute(
            "SELECT c.kazanim_kod AS kod, c.kazanim_metin AS metin, SUM(c.cevap = c.dogru_index) AS dogru,"
            " count(*) AS toplam FROM bilgi_cevap c JOIN bilgi_tur t ON t.id = c.tur_id"
            " WHERE t.kullanici_id = ? AND c.kazanim_id IS NOT NULL AND c.cevap >= 0"
            " GROUP BY c.kazanim_id ORDER BY toplam DESC, kod LIMIT ?",
            (kid, n),
        )
    ]


def tekrar_onerileri(conn: sqlite3.Connection, kid: int, n: int = 3) -> list[dict]:
    """En az bir yanlış yapılan ve doğru oranı %80'in altında kalan kazanımlar. Yargı değil, öneri."""
    return [
        {"kod": r["kod"], "metin": r["metin"]}
        for r in conn.execute(
            "SELECT c.kazanim_kod AS kod, c.kazanim_metin AS metin FROM bilgi_cevap c"
            " JOIN bilgi_tur t ON t.id = c.tur_id WHERE t.kullanici_id = ? AND c.kazanim_id IS NOT NULL"
            " AND c.cevap >= 0 GROUP BY c.kazanim_id"
            " HAVING SUM(c.cevap <> c.dogru_index) >= 1 AND 1.0 * SUM(c.cevap = c.dogru_index) / count(*) < 0.8"
            " ORDER BY 1.0 * SUM(c.cevap = c.dogru_index) / count(*), kod LIMIT ?",
            (kid, n),
        )
    ]
