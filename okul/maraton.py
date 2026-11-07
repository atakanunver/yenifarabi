"""Soru Maratonu: 10 soru x 80 sn, sunucu tarafında puanlama (saf mantık, okul.db).

Doğru şık istemciye cevaptan önce gitmez; süre sunucuda ölçülür (gösterim zamanı kaydedilir).
cevap: NULL bekliyor, 0.. şık, SURE_DOLDU süre doldu, TERK yarıda bırakıldı (puana/seriye/liderliğe sayılmaz).
"""

import json
import random
import sqlite3
from datetime import datetime, timedelta

import gayret
import soru_bildirim
import zaman
from kaynaklar import KaynakHatasi, zil
from kaynaklar import soru as havuz
from metin import kisa_ad

SORU_SAYISI = 10
SURE = 80
TOLERANS = 2  # ağ gecikmesi payı: geçen > SURE + TOLERANS ise süre doldu
TEMEL_PUAN = 100
HIZ_CARPANI = 3
SURE_DOLDU = -1
TERK = -2
PAS = -3  # öğrenci pas geçti (0 puan)
HATALI = -4  # soru hatalı bildirildi: puansız geçilir, istatistiğe katılmaz
PAS_HAKKI = 2  # maraton başına
# Sallama freni (2026-11-07): soruyu okumaya yetmeyecek kadar hızlı cevap hız puanı almaz;
# üst üste SERI_ESIK hızlı cevaptan sonra turun kalanında da hız puanı kapanır. Temel puan korunur, ceza yok.
OKUMA_TABANI = 3  # sn
OKUMA_KELIME_SN = 15  # her 15 kelime +1 sn
GORSEL_OKUMA_EK = 4  # sn (metni yalnız "görselden incele" olan sorular)
YER_TUTUCU = "Soruyu görselden inceleyiniz."
SERI_ESIK = 3
# Yanlış çözülen soru tekrar gelir (yeni turda en çok TEKRAR_KOTA tane); aynı soruyu TEKRAR_ESIK. kez yanlış
# yapmak anlayarak çözülmediğini gösterir: uyarı + TEKRAR_CEZA puan düşer (tur puanı 0'ın altına inmez).
TEKRAR_KOTA = 3
TEKRAR_ESIK = 3
TEKRAR_CEZA = 50
EN_IYI = 3  # haftalık toplamda sayılan en iyi maraton sayısı

# yalnızca bitirilmiş (yarıda bırakılmamış) maratonlar
_TAMAM = (
    "m.bitis IS NOT NULL AND NOT EXISTS ("
    "SELECT 1 FROM maraton_soru s WHERE s.maraton_id = m.id AND s.cevap = -2)"
)


class MaratonHatasi(Exception):
    pass


# Ders saati kilidi 2026-10-14'te kaldırıldı (öğrenciler Maraton/Günlük Görev'i her zaman oynar).
# Geri açmak için True yap: ders saatinde kilit() {'bit', 'no'} döner, rotalar 423 verir.
DERS_KILIDI = False


def kilit() -> dict | None:
    """DERS_KILIDI açıksa ders saatinde {'bit': '10:30', 'no': 3}, değilse None. Zil okunamazsa (tur=yok) açık."""
    if not DERS_KILIDI:
        return None
    d = zil.durum(zaman.simdi())
    if d["tur"] == "ders":
        return {"bit": d["bit"], "no": d["no"]}
    return None


def puan_hesapla(dogru: bool, gecen_sn: float, bonus: bool = True) -> int:
    if not dogru or gecen_sn > SURE + TOLERANS:
        return 0
    if not bonus:
        return TEMEL_PUAN
    kalan = max(0, min(SURE, SURE - int(gecen_sn)))
    return TEMEL_PUAN + kalan * HIZ_CARPANI


def okuma_tabani(metin: str) -> float:
    """Sorunun okunabileceği en kısa makul süre (sn)."""
    ek = GORSEL_OKUMA_EK if metin.strip() == YER_TUTUCU else len(metin.split()) / OKUMA_KELIME_SN
    return OKUMA_TABANI + ek


def sallama_mi(conn: sqlite3.Connection, maraton_id: int) -> bool:
    """Tur sallama gibi mi: en az yarısı okumadan hızlı cevap ve 10 soruda en çok 1 doğru."""
    satirlar = conn.execute(
        "SELECT soru, gosterim, cevap_zamani, cevap, dogru_index FROM maraton_soru"
        " WHERE maraton_id = ? AND cevap >= 0 AND gosterim IS NOT NULL AND cevap_zamani IS NOT NULL",
        (maraton_id,),
    ).fetchall()
    if len(satirlar) < SORU_SAYISI // 2:
        return False
    dogru = sum(r["cevap"] == r["dogru_index"] for r in satirlar)
    hizli = sum(
        (_dt(r["cevap_zamani"]) - _dt(r["gosterim"])).total_seconds() < okuma_tabani(r["soru"]) for r in satirlar
    )
    return dogru <= 1 and hizli * 2 >= len(satirlar)


def _hizli_seri(conn: sqlite3.Connection, maraton_id: int) -> int:
    """Bu turda en son verilen cevaplardan geriye doğru ardışık 'okumadan hızlı' cevap sayısı."""
    seri = 0
    for r in conn.execute(
        "SELECT soru, gosterim, cevap_zamani FROM maraton_soru WHERE maraton_id = ? AND cevap >= 0"
        " AND gosterim IS NOT NULL AND cevap_zamani IS NOT NULL ORDER BY sira DESC",
        (maraton_id,),
    ):
        if (_dt(r["cevap_zamani"]) - _dt(r["gosterim"])).total_seconds() >= okuma_tabani(r["soru"]):
            break
        seri += 1
    return seri


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


def yanlis_havuzu(conn: sqlite3.Connection, kullanici_id: int, ders: str, yasak: list[int]) -> list[int]:
    """Bu derste yanlış yapılmış ve sonradan doğru yapılmamış soru id'leri; en çok yanlışlı, sonra en eski önce."""
    satirlar = conn.execute(
        "SELECT s.soru_id,"
        " sum(s.cevap >= 0 AND s.cevap <> s.dogru_index) AS yanlis,"
        " max(CASE WHEN s.cevap >= 0 AND s.cevap <> s.dogru_index THEN m.id END) AS son_yanlis,"
        " max(CASE WHEN s.cevap = s.dogru_index THEN m.id END) AS son_dogru"
        " FROM maraton_soru s JOIN maraton m ON m.id = s.maraton_id"
        " WHERE m.kullanici_id = ? AND m.ders = ? GROUP BY s.soru_id"
        " HAVING yanlis > 0 AND (son_dogru IS NULL OR son_dogru < son_yanlis)"
        " ORDER BY yanlis DESC, son_yanlis",
        (kullanici_id, ders),
    ).fetchall()
    yasakli = set(yasak)
    return [r["soru_id"] for r in satirlar if r["soru_id"] not in yasakli]


def yanlis_sayisi(conn: sqlite3.Connection, kullanici_id: int, soru_id: int) -> int:
    """Öğrencinin bu soruyu daha önce (cevaplanmış turlarda) kaç kez yanlış yaptığı."""
    return conn.execute(
        "SELECT count(*) FROM maraton_soru s JOIN maraton m ON m.id = s.maraton_id"
        " WHERE m.kullanici_id = ? AND s.soru_id = ? AND s.cevap >= 0 AND s.cevap <> s.dogru_index",
        (kullanici_id, soru_id),
    ).fetchone()[0]


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
    yasak = soru_bildirim.gizli_idler(conn)
    tekrar_idler = yanlis_havuzu(conn, kullanici_id, ders, yasak)[:TEKRAR_KOTA]
    tekrar = havuz.secili(tekrar_idler, seviye, ders) if tekrar_idler else []
    sorular = tekrar + havuz.sorular(seviye, ders, list(gorulen), SORU_SAYISI - len(tekrar), gorulen, yasak)
    if tekrar:
        random.shuffle(sorular)
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
    hizli = not sure_doldu and gecen_sn(s) < okuma_tabani(s["soru"])
    bonus_kapali = not sure_doldu and (hizli or _hizli_seri(conn, maraton_id) >= SERI_ESIK)
    puan = puan_hesapla(dogru, gecen_sn(s), not bonus_kapali) if dogru else 0
    kid = conn.execute("SELECT kullanici_id FROM maraton WHERE id = ?", (maraton_id,)).fetchone()[0]
    yanlis_n = 0
    ceza = 0
    if secim is not None and not sure_doldu and not dogru:
        yanlis_n = yanlis_sayisi(conn, kid, s["soru_id"]) + 1
        if yanlis_n >= TEKRAR_ESIK:
            mevcut = conn.execute("SELECT puan FROM maraton WHERE id = ?", (maraton_id,)).fetchone()[0]
            ceza = min(TEKRAR_CEZA, mevcut)
            puan = -ceza
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
    gayret_xp = 0
    if not sure_doldu:  # gerçekten cevap verildi: soruya ayrılan süre kadar gayret XP'si (doğru/yanlış fark etmez)
        gayret_xp = gayret.ver(conn, kid, f"m{maraton_id}:{sira}", gayret.gecen(s["gosterim"], zaman.simdi_str()))
    conn.commit()
    toplam = conn.execute("SELECT puan FROM maraton WHERE id = ?", (maraton_id,)).fetchone()[0]
    return {
        "gayret_xp": gayret_xp,
        "dogru": dogru,
        "dogru_index": s["dogru_index"],
        "puan": puan,
        "toplam": toplam,
        "sure_doldu": sure_doldu,
        "bonus_kapali": bonus_kapali,
        "tekrar_uyari": yanlis_n >= TEKRAR_ESIK,
        "yanlis_sayisi": yanlis_n,
        "ceza": ceza,
        "bitti": kalan == 0,
    }


def pas_kalan(conn: sqlite3.Connection, maraton_id: int) -> int:
    return max(0, PAS_HAKKI - conn.execute(
        "SELECT count(*) FROM maraton_soru WHERE maraton_id = ? AND cevap = ?", (maraton_id, PAS)
    ).fetchone()[0])


def gec(conn: sqlite3.Connection, maraton_id: int, sira: int, hatali: bool = False) -> dict:
    """Şu anki soruyu puansız geçer: pas (hak sınırlı) ya da hatalı soru (sınırsız; bildirimi çağıran yazar)."""
    s = conn.execute(
        "SELECT * FROM maraton_soru WHERE maraton_id = ? AND cevap IS NULL ORDER BY sira LIMIT 1",
        (maraton_id,),
    ).fetchone()
    if s is None or s["sira"] != sira:
        raise MaratonHatasi("Bu soru zaten cevaplanmış.")
    if not hatali and pas_kalan(conn, maraton_id) <= 0:
        raise MaratonHatasi("Pas hakkın bitti.")
    if conn.execute(
        "UPDATE maraton_soru SET cevap = ?, cevap_zamani = ?, puan = 0"
        " WHERE maraton_id = ? AND sira = ? AND cevap IS NULL",
        (HATALI if hatali else PAS, zaman.simdi_str(), maraton_id, sira),
    ).rowcount != 1:
        conn.rollback()
        raise MaratonHatasi("Bu soru zaten cevaplanmış.")
    kalan = conn.execute(
        "SELECT count(*) FROM maraton_soru WHERE maraton_id = ? AND cevap IS NULL", (maraton_id,)
    ).fetchone()[0]
    if kalan == 0:
        conn.execute("UPDATE maraton SET bitis = ? WHERE id = ?", (zaman.simdi_str(), maraton_id))
    conn.commit()
    return {"bitti": kalan == 0}


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
        if r["cevap"] is None or r["cevap"] == HATALI:
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


def liderlik(conn: sqlite3.Connection, sinif: str | None = None, hafta: str | None = None) -> list[dict]:
    """Bu hafta (pazartesiden beri) her öğrencinin EN İYİ 3 maratonunun toplamı. sinif verilirse yalnız o şube.
    hafta ('YYYY-MM-DD' pazartesi) verilirse o haftanın (pazartesi-pazar) sonucu."""
    sorgu = (
        "SELECT m.kullanici_id, m.puan, o.ad_soyad, o.sinif FROM maraton m"
        " JOIN ogrenci o ON o.kullanici_id = m.kullanici_id"
        f" WHERE m.bitis >= ? AND {_TAMAM}"
    )
    if hafta:
        bas = f"{hafta} 00:00:00"
        sorgu += " AND m.bitis < ?"
        arg: list = [bas, (datetime.strptime(hafta, "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")]  # noqa: DTZ007
    else:
        arg = [hafta_basi()]
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
