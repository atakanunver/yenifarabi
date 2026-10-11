"""Soru Maratonu: 10 soru x 30 sn, sunucu tarafında puanlama (saf mantık, okul.db).

Doğru şık istemciye cevaptan önce gitmez; süre sunucuda ölçülür (gösterim zamanı kaydedilir).
cevap: NULL bekliyor, 0.. şık, SURE_DOLDU süre doldu, TERK yarıda bırakıldı (puana/seriye/liderliğe sayılmaz).
"""

import json
import sqlite3
from datetime import datetime, timedelta

import zaman
from kaynaklar import KaynakHatasi, zil
from kaynaklar import soru as havuz
from metin import kisa_ad

SORU_SAYISI = 10
SURE = 30
TOLERANS = 2  # ağ gecikmesi payı: geçen > SURE + TOLERANS ise süre doldu
TEMEL_PUAN = 100
HIZ_CARPANI = 3
SURE_DOLDU = -1
TERK = -2
EN_IYI = 3  # haftalık toplamda sayılan en iyi maraton sayısı

# yalnızca bitirilmiş (yarıda bırakılmamış) maratonlar
_TAMAM = (
    "m.bitis IS NOT NULL AND NOT EXISTS ("
    "SELECT 1 FROM maraton_soru s WHERE s.maraton_id = m.id AND s.cevap = -2)"
)


class MaratonHatasi(Exception):
    pass


def kilit() -> dict | None:
    """Ders saatinde {'bit': '10:30', 'no': 3}, değilse None. Zil okunamazsa (tur=yok) açık."""
    d = zil.durum(zaman.simdi())
    if d["tur"] == "ders":
        return {"bit": d["bit"], "no": d["no"]}
    return None


def puan_hesapla(dogru: bool, gecen_sn: float) -> int:
    if not dogru or gecen_sn > SURE + TOLERANS:
        return 0
    kalan = max(0, min(SURE, SURE - int(gecen_sn)))
    return TEMEL_PUAN + kalan * HIZ_CARPANI


def duzey(sinif: str) -> int:
    return int(sinif.split("-", 1)[0])


def _an() -> datetime:
    return zaman.simdi()


def _dt(s: str) -> datetime:
    return datetime.strptime(s, zaman.BICIM)


def gorulme(conn: sqlite3.Connection, kullanici_id: int) -> dict[int, int]:
    """soru_id -> öğrencinin bu soruyu maratonda görme sayısı."""
    return {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT s.soru_id, count(*) FROM maraton_soru s JOIN maraton m ON m.id = s.maraton_id"
            " WHERE m.kullanici_id = ? AND s.gosterim IS NOT NULL GROUP BY s.soru_id",
            (kullanici_id,),
        )
    }


def getir(conn: sqlite3.Connection, maraton_id: int, kullanici_id: int) -> sqlite3.Row | None:
    """Yalnızca kendi maratonu; başkasınınki None (rota 404 verir)."""
    return conn.execute(
        "SELECT * FROM maraton WHERE id = ? AND kullanici_id = ?", (maraton_id, kullanici_id)
    ).fetchone()


def acik_maraton(conn: sqlite3.Connection, kullanici_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM maraton WHERE kullanici_id = ? AND bitis IS NULL ORDER BY id DESC LIMIT 1",
        (kullanici_id,),
    ).fetchone()


def baslat(conn: sqlite3.Connection, kullanici_id: int, sinif: str, ders: str) -> int:
    """Yeni maraton: eskisi açıksa terk edilir; sorular havuzdan okul.db'ye kopyalanır."""
    seviye = duzey(sinif)
    gorulen = gorulme(conn, kullanici_id)
    sorular = havuz.sorular(seviye, ders, list(gorulen), SORU_SAYISI, gorulen)
    if len(sorular) < SORU_SAYISI:
        raise MaratonHatasi("Bu derste yeterli soru yok.")
    for eski in conn.execute(
        "SELECT id FROM maraton WHERE kullanici_id = ? AND bitis IS NULL", (kullanici_id,)
    ).fetchall():
        bitir(conn, eski["id"], terk=True)
    cur = conn.execute(
        "INSERT INTO maraton (kullanici_id, sinif, duzey, ders, basla) VALUES (?, ?, ?, ?, ?)",
        (kullanici_id, sinif, seviye, ders, zaman.simdi_str()),
    )
    mid = cur.lastrowid
    conn.executemany(
        "INSERT INTO maraton_soru (maraton_id, sira, soru_id, soru, secenekler, dogru_index, konu, kaynak)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (mid, i, s["id"], s["soru"], json.dumps(s["secenekler"], ensure_ascii=False),
             s["dogru_index"], s["konu"], s["kaynak"])
            for i, s in enumerate(sorular, 1)
        ],
    )
    conn.commit()
    return mid


def siradaki(conn: sqlite3.Connection, maraton_id: int) -> sqlite3.Row | None:
    """İlk cevapsız soru; gösterim zamanı ilk gösterimde bir kez yazılır (yenileme sayacı sıfırlamaz)."""
    s = conn.execute(
        "SELECT * FROM maraton_soru WHERE maraton_id = ? AND cevap IS NULL ORDER BY sira LIMIT 1",
        (maraton_id,),
    ).fetchone()
    if s is None:
        return None
    if s["gosterim"] is None:
        conn.execute(
            "UPDATE maraton_soru SET gosterim = ? WHERE maraton_id = ? AND sira = ?",
            (zaman.simdi_str(), maraton_id, s["sira"]),
        )
        conn.commit()
        s = conn.execute(
            "SELECT * FROM maraton_soru WHERE maraton_id = ? AND sira = ?", (maraton_id, s["sira"])
        ).fetchone()
    return s


def gecen_sn(s: sqlite3.Row) -> float:
    return (_an() - _dt(s["gosterim"])).total_seconds() if s["gosterim"] else 0.0


def kalan_sn(s: sqlite3.Row) -> int:
    return max(0, SURE - int(gecen_sn(s)))


def sure_asildi(s: sqlite3.Row) -> bool:
    return gecen_sn(s) > SURE + TOLERANS


def cevapla(conn: sqlite3.Connection, maraton_id: int, sira: int, secim: int | None) -> dict:
    """Şu anki soruyu puanlar. secim None = süre doldu. Dönen sözlük doğru şıkkı içerir (cevap sonrası)."""
    s = conn.execute(
        "SELECT * FROM maraton_soru WHERE maraton_id = ? AND cevap IS NULL ORDER BY sira LIMIT 1",
        (maraton_id,),
    ).fetchone()
    if s is None or s["sira"] != sira:
        raise MaratonHatasi("Bu soru zaten cevaplanmış.")
    n = len(json.loads(s["secenekler"]))
    if secim is not None and not 0 <= secim < n:
        raise MaratonHatasi("Geçersiz şık.")
    sure_doldu = secim is None or s["gosterim"] is None or sure_asildi(s)
    dogru = (not sure_doldu) and secim == s["dogru_index"]
    puan = puan_hesapla(dogru, gecen_sn(s)) if dogru else 0
    cevap = SURE_DOLDU if sure_doldu else secim
    # cevap IS NULL koşulu: çift dokunma / iki sekmede aynı soru iki kez puanlanmasın
    if conn.execute(
        "UPDATE maraton_soru SET cevap = ?, cevap_zamani = ?, puan = ?"
        " WHERE maraton_id = ? AND sira = ? AND cevap IS NULL",
        (cevap, zaman.simdi_str(), puan, maraton_id, sira),
    ).rowcount != 1:
        conn.rollback()
        raise MaratonHatasi("Bu soru zaten cevaplanmış.")
    conn.execute(
        "UPDATE maraton SET puan = puan + ?, dogru = dogru + ? WHERE id = ?",
        (puan, int(dogru), maraton_id),
    )
    kalan = conn.execute(
        "SELECT count(*) FROM maraton_soru WHERE maraton_id = ? AND cevap IS NULL", (maraton_id,)
    ).fetchone()[0]
    if kalan == 0:
        conn.execute("UPDATE maraton SET bitis = ? WHERE id = ?", (zaman.simdi_str(), maraton_id))
    conn.commit()
    toplam = conn.execute("SELECT puan FROM maraton WHERE id = ?", (maraton_id,)).fetchone()[0]
    return {
        "dogru": dogru,
        "dogru_index": s["dogru_index"],
        "puan": puan,
        "toplam": toplam,
        "sure_doldu": sure_doldu,
        "bitti": kalan == 0,
    }


def bitir(conn: sqlite3.Connection, maraton_id: int, terk: bool = False) -> None:
    """Kalan sorular 0 puanla kapatılır; terk=True ise liderlik/seriye sayılmaz."""
    conn.execute(
        "UPDATE maraton_soru SET cevap = ?, cevap_zamani = ?, puan = 0"
        " WHERE maraton_id = ? AND cevap IS NULL",
        (TERK if terk else SURE_DOLDU, zaman.simdi_str(), maraton_id),
    )
    conn.execute(
        "UPDATE maraton SET bitis = ? WHERE id = ? AND bitis IS NULL", (zaman.simdi_str(), maraton_id)
    )
    conn.commit()


def sorular(conn: sqlite3.Connection, maraton_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM maraton_soru WHERE maraton_id = ? ORDER BY sira", (maraton_id,)
    ).fetchall()


def ilerleme(conn: sqlite3.Connection, maraton_id: int) -> list[str]:
    """Kare durumları: 'dogru' | 'yanlis' | 'bos'."""
    out = []
    for r in sorular(conn, maraton_id):
        if r["cevap"] is None:
            out.append("bos")
        else:
            out.append("dogru" if r["cevap"] == r["dogru_index"] else "yanlis")
    return out


def son_maratonlar(conn: sqlite3.Connection, kullanici_id: int, n: int = 5) -> list[sqlite3.Row]:
    return conn.execute(
        f"SELECT m.* FROM maraton m WHERE m.kullanici_id = ? AND {_TAMAM} ORDER BY m.id DESC LIMIT ?",
        (kullanici_id, n),
    ).fetchall()


def seri(conn: sqlite3.Connection, kullanici_id: int) -> int:
    """Maraton bitirilen art arda gün sayısı (bugün ya da dün bitenle başlar)."""
    gunler = {
        r[0]
        for r in conn.execute(
            f"SELECT DISTINCT substr(m.bitis, 1, 10) FROM maraton m WHERE m.kullanici_id = ? AND {_TAMAM}",
            (kullanici_id,),
        )
    }
    gun = _an().date()
    if gun.isoformat() not in gunler:
        gun -= timedelta(days=1)
    n = 0
    while gun.isoformat() in gunler:
        n += 1
        gun -= timedelta(days=1)
    return n


def hafta_basi() -> str:
    d = _an().date()
    return (d - timedelta(days=d.weekday())).isoformat() + " 00:00:00"


def liderlik(conn: sqlite3.Connection, sinif: str | None = None) -> list[dict]:
    """Bu hafta (pazartesiden beri) her öğrencinin EN İYİ 3 maratonunun toplamı. sinif verilirse yalnız o şube."""
    sorgu = (
        "SELECT m.kullanici_id, m.puan, o.ad_soyad, o.sinif FROM maraton m"
        " JOIN ogrenci o ON o.kullanici_id = m.kullanici_id"
        f" WHERE m.bitis >= ? AND {_TAMAM}"
    )
    arg: list = [hafta_basi()]
    if sinif:
        sorgu += " AND o.sinif = ?"
        arg.append(sinif)
    ogr: dict[int, dict] = {}
    for r in conn.execute(sorgu + " ORDER BY m.puan DESC", arg):
        d = ogr.setdefault(
            r["kullanici_id"],
            {"kullanici_id": r["kullanici_id"], "ad": kisa_ad(r["ad_soyad"]), "sinif": r["sinif"], "puanlar": []},
        )
        d["puanlar"].append(r["puan"])
    liste = []
    for d in ogr.values():
        en_iyi = sorted(d.pop("puanlar"), reverse=True)[:EN_IYI]
        liste.append({**d, "toplam": sum(en_iyi), "adet": len(en_iyi)})
    liste.sort(key=lambda d: (-d["toplam"], d["ad"]))
    for i, d in enumerate(liste, 1):
        d["sira"] = i
    return liste


def ana_ozet(conn: sqlite3.Connection, kullanici_id: int) -> dict:
    """Ana sayfa kartı: seri + bu haftaki okul sırası (oynamadıysa None)."""
    sira = next(
        (d["sira"] for d in liderlik(conn) if d["kullanici_id"] == kullanici_id), None
    )
    return {"seri": seri(conn, kullanici_id), "sira": sira, "kilit": kilit()}


def dersler(sinif: str) -> list[tuple[str, str, int]] | None:
    """[(kod, görünen ad, soru sayısı)]; havuza ulaşılamazsa None."""
    try:
        return [(k, havuz.ders_adi(k), n) for k, n in havuz.dersler(duzey(sinif))]
    except KaynakHatasi:
        return None
