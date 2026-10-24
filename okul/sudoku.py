"""Sudoku Düellosu: üretici/çözücü (saf Python) + eşzamansız düello yaşam döngüsü + haftalık puan (okul.db).

Bulmaca ve çözüm 81 karakterlik dizgedir ('0' = boş). Çözüm istemciye ASLA gitmez; süre sunucuda ölçülür
(bulmaca ilk açılışta `baslama`, doğru gönderimde `bitis`). Puan SAKLANMAZ: biten düellolardan türetilir.
Bilgi Arenası XP'sine (bilgi_xp) bağlı değildir.
"""

import random
import secrets
import sqlite3
from datetime import datetime, timedelta

import oduller
import zaman
from metin import kisa_ad

ZORLUK = {"basit": 40, "orta": 32, "zor": 26}  # ipucu sayısı
CARPAN = {"basit": 1, "orta": 2, "zor": 3}
ZORLUK_AD = {"basit": "Basit", "orta": "Orta", "zor": "Zor"}
SURE_SAAT = 24
HATA_CEZA = 10  # sn
IPUCU_CEZA = 15  # sn (her ipucu skora eklenir)
IPUCU_EN_COK = 3  # oyun başına
BEKLEYEN_EN_COK = 3
GUNLUK_EN_COK = 5
CIFT_GUNLUK_PUANLI = 2
PUAN = {"galibiyet": 3, "beraberlik": 1, "maglubiyet": 0}
_BUTCE = 20000  # tek çözüm sayımında düğüm bütçesi; aşılırsa "tek çözüm kanıtlanamadı" sayılır (deterministik)


class SudokuHatasi(Exception):
    pass


# --- üretici / çözücü ---

_KUTU = [(r // 3) * 3 + c // 3 for r in range(9) for c in range(9)]


def _say(tahta: list[int], limit: int = 2) -> int:
    """Çözüm sayısı (en çok `limit`). Bütçe aşılırsa `limit` döner (güvenli taraf: tek çözüm sayılmaz)."""
    satir, sutun, kutu = [0] * 9, [0] * 9, [0] * 9
    bos = []
    for i, v in enumerate(tahta):
        if v:
            b = 1 << v
            satir[i // 9] |= b
            sutun[i % 9] |= b
            kutu[_KUTU[i]] |= b
        else:
            bos.append(i)
    sayac = [0, 0]  # çözüm, düğüm

    def ara(kalan: list[int]) -> None:
        if sayac[0] >= limit or sayac[1] > _BUTCE:
            return
        if not kalan:
            sayac[0] += 1
            return
        en_i, en_m, en_n = -1, 0, 10
        for j, i in enumerate(kalan):
            m = ~(satir[i // 9] | sutun[i % 9] | kutu[_KUTU[i]]) & 0x3FE
            n = m.bit_count()
            if n < en_n:
                en_i, en_m, en_n = j, m, n
                if n <= 1:
                    break
        if en_n == 0:
            return
        i = kalan[en_i]
        sonraki = kalan[:en_i] + kalan[en_i + 1:]
        r, c, k = i // 9, i % 9, _KUTU[i]
        for v in range(1, 10):
            b = 1 << v
            if en_m & b:
                sayac[1] += 1
                satir[r] |= b
                sutun[c] |= b
                kutu[k] |= b
                ara(sonraki)
                satir[r] &= ~b
                sutun[c] &= ~b
                kutu[k] &= ~b
                if sayac[0] >= limit or sayac[1] > _BUTCE:
                    return

    ara(bos)
    return limit if sayac[1] > _BUTCE else sayac[0]


def _dolu_tahta(rnd: random.Random) -> list[int]:
    rakamlar = list(range(1, 10))
    rnd.shuffle(rakamlar)

    def karis() -> list[int]:
        bantlar = list(range(3))
        rnd.shuffle(bantlar)
        sirali = []
        for b in bantlar:
            ic = list(range(3))
            rnd.shuffle(ic)
            sirali += [b * 3 + x for x in ic]
        return sirali

    sat, sut = karis(), karis()
    return [rakamlar[(3 * (r % 3) + r // 3 + c) % 9] for r in sat for c in sut]


def uret(tohum: int, zorluk: str) -> tuple[str, str]:
    """(bulmaca, çözüm) — aynı tohum/zorluk her zaman aynı sonucu verir; bulmaca tek çözümlüdür.
    Hedef ipucu sayısına ulaşılamazsa (nadir) ulaşılabilen en az ipuçlu tek çözümlü bulmaca döner."""
    if zorluk not in ZORLUK:
        raise SudokuHatasi("Geçersiz zorluk.")
    rnd = random.Random(tohum)
    cozum = _dolu_tahta(rnd)
    tahta = cozum[:]
    ipucu = 81
    sira = list(range(81))
    rnd.shuffle(sira)
    for i in sira:
        if ipucu <= ZORLUK[zorluk]:
            break
        eski, tahta[i] = tahta[i], 0
        if _say(tahta) == 1:
            ipucu -= 1
        else:
            tahta[i] = eski
    return "".join(map(str, tahta)), "".join(map(str, cozum))


# --- düello yaşam döngüsü ---

def _simdi() -> datetime:
    return zaman.simdi()


def _dt(s: str) -> datetime:
    return datetime.strptime(s, zaman.BICIM)  # noqa: DTZ007


def sinif_arkadaslari(conn: sqlite3.Connection, sinif: str, kid: int) -> list[dict]:
    """Aynı sınıftaki aktif diğer öğrenciler: [{kid, ad}]."""
    return [
        {"kid": o["kid"], "ad": kisa_ad(o["ad_soyad"])}
        for o in oduller._sinif_ogrencileri(conn, sinif) if o["kid"] != kid
    ]


def getir(conn: sqlite3.Connection, duello_id: int, kid: int) -> sqlite3.Row | None:
    """Yalnızca katılımcıya döner (diğerleri None → rota 404). Önce süreleri kapatır."""
    kapat_sureleri(conn)
    return conn.execute(
        "SELECT * FROM sudoku_duello WHERE id = ? AND (kuran_kid = ? OR rakip_kid = ?)", (duello_id, kid, kid)
    ).fetchone()


def meydan_oku(conn: sqlite3.Connection, kuran_kid: int, sinif: str, rakip_kid: int, zorluk: str) -> int:
    if zorluk not in ZORLUK:
        raise SudokuHatasi("Geçersiz zorluk.")
    if rakip_kid == kuran_kid or rakip_kid not in {o["kid"] for o in oduller._sinif_ogrencileri(conn, sinif)}:
        raise SudokuHatasi("Yalnızca kendi sınıfındaki bir arkadaşına meydan okuyabilirsin.")
    kapat_sureleri(conn)
    simdi = _simdi()
    bekleyen = conn.execute(
        "SELECT COUNT(*) FROM sudoku_duello WHERE kuran_kid = ? AND durum = 'bekliyor'", (kuran_kid,)
    ).fetchone()[0]
    if bekleyen >= BEKLEYEN_EN_COK:
        raise SudokuHatasi(f"En çok {BEKLEYEN_EN_COK} bekleyen meydan okuman olabilir.")
    gun = simdi.strftime("%Y-%m-%d")
    if conn.execute(
        "SELECT COUNT(*) FROM sudoku_duello WHERE kuran_kid = ? AND substr(olusturma, 1, 10) = ?", (kuran_kid, gun)
    ).fetchone()[0] >= GUNLUK_EN_COK:
        raise SudokuHatasi(f"Günde en çok {GUNLUK_EN_COK} meydan okuma yapabilirsin.")
    bulmaca, cozum = uret(secrets.randbits(32), zorluk)
    cur = conn.execute(
        "INSERT INTO sudoku_duello (sinif, zorluk, bulmaca, cozum, kuran_kid, rakip_kid, durum, olusturma, son_tarih)"
        " VALUES (?, ?, ?, ?, ?, ?, 'bekliyor', ?, NULL)",
        (sinif, zorluk, bulmaca, cozum, kuran_kid, rakip_kid, zaman.simdi_str()),
    )
    conn.commit()
    return cur.lastrowid


def _karar(conn: sqlite3.Connection, duello_id: int, kid: int, yeni: str) -> None:
    kapat_sureleri(conn)
    d = conn.execute(
        "SELECT * FROM sudoku_duello WHERE id = ? AND rakip_kid = ? AND durum = 'bekliyor'", (duello_id, kid)
    ).fetchone()
    if d is None:
        raise SudokuHatasi("Bu meydan okuma artık beklemiyor.")
    son = (_simdi() + timedelta(hours=SURE_SAAT)).strftime(zaman.BICIM) if yeni == "surer" else None
    conn.execute("UPDATE sudoku_duello SET durum = ?, son_tarih = ? WHERE id = ?", (yeni, son, duello_id))
    conn.commit()


def kabul(conn: sqlite3.Connection, duello_id: int, kid: int) -> None:
    _karar(conn, duello_id, kid, "surer")


def red(conn: sqlite3.Connection, duello_id: int, kid: int) -> None:
    _karar(conn, duello_id, kid, "red")


def oyun(conn: sqlite3.Connection, duello_id: int, kid: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM sudoku_oyun WHERE duello_id = ? AND kullanici_id = ?", (duello_id, kid)
    ).fetchone()


def baslat(conn: sqlite3.Connection, duello_id: int, kid: int) -> sqlite3.Row:
    """Bulmacayı ilk açışta `baslama` yazılır; tekrar açışta aynı kayıt döner (saat sıfırlanmaz)."""
    d = getir(conn, duello_id, kid)
    if d is None or d["durum"] != "surer":
        raise SudokuHatasi("Düello oynanamaz durumda.")
    conn.execute(
        "INSERT OR IGNORE INTO sudoku_oyun (duello_id, kullanici_id, baslama, hata) VALUES (?, ?, ?, 0)",
        (duello_id, kid, zaman.simdi_str()),
    )
    conn.commit()
    return oyun(conn, duello_id, kid)


def kaydet(conn: sqlite3.Connection, duello_id: int, kid: int, tahta: str) -> None:
    """Doldurulan rakamları saklar (süren düelloda, bitirmemiş oyuncu için; sabit ipuçları kaydedilmez)."""
    d = getir(conn, duello_id, kid)
    if d is None or d["durum"] != "surer":
        raise SudokuHatasi("Düello oynanamaz durumda.")
    o = oyun(conn, duello_id, kid)
    if o is None:
        raise SudokuHatasi("Önce bulmacayı aç.")
    if o["bitis"]:
        raise SudokuHatasi("Bu düelloyu zaten bitirdin.")
    tahta = (tahta or "").strip()
    if len(tahta) != 81 or not tahta.isascii() or not tahta.isdigit():
        raise SudokuHatasi("Geçersiz tahta.")
    temiz = "".join("0" if b != "0" else t for b, t in zip(d["bulmaca"], tahta, strict=True))
    conn.execute(
        "UPDATE sudoku_oyun SET tahta = ? WHERE duello_id = ? AND kullanici_id = ? AND bitis IS NULL", (temiz, duello_id, kid)
    )
    conn.commit()


def temiz_tahta(bulmaca: str, tahta: str) -> str:
    """Yalnız oyuncunun boş hücrelere yazdıkları kalır; sabit ipuçları bulmacadan gelir."""
    return "".join("0" if b != "0" else t for b, t in zip(bulmaca, tahta, strict=True))


def ipucu_sec(bulmaca: str, cozum: str, tahta: str, rnd: random.Random | None = None) -> int | None:
    """Açılacak hücre: oyuncunun YANLIŞ doldurduğu (öncelikli: takıldığı yer), yoksa boş bıraktığı hücrelerden biri.
    Sabit ipuçları seçilmez; açılacak hücre yoksa None."""
    yanlis = [i for i in range(81) if bulmaca[i] == "0" and tahta[i] not in ("0", cozum[i])]
    bos = [i for i in range(81) if bulmaca[i] == "0" and tahta[i] == "0"]
    havuz = yanlis or bos
    return (rnd or random).choice(havuz) if havuz else None


def _tahta_dogrula(tahta: str) -> str:
    tahta = (tahta or "").strip()
    if len(tahta) != 81 or not tahta.isascii() or not tahta.isdigit():
        raise SudokuHatasi("Geçersiz tahta.")
    return tahta


def ipucu_al(conn: sqlite3.Connection, duello_id: int, kid: int, tahta: str, rnd: random.Random | None = None) -> dict:
    """Bir hücrenin doğru rakamını açar ve kaydeder; skora IPUCU_CEZA sn eklenir. {'index', 'rakam', 'ipucu', 'kalan'}."""
    d = getir(conn, duello_id, kid)
    if d is None or d["durum"] != "surer":
        raise SudokuHatasi("Düello oynanamaz durumda.")
    o = oyun(conn, duello_id, kid)
    if o is None:
        raise SudokuHatasi("Önce bulmacayı aç.")
    if o["bitis"]:
        raise SudokuHatasi("Bu düelloyu zaten bitirdin.")
    if o["ipucu"] >= IPUCU_EN_COK:
        raise SudokuHatasi(f"Bir oyunda en çok {IPUCU_EN_COK} ipucu alabilirsin.")
    tahta = _tahta_dogrula(tahta)
    i = ipucu_sec(d["bulmaca"], d["cozum"], tahta, rnd)
    if i is None:
        raise SudokuHatasi("Tahtadaki tüm rakamlar doğru görünüyor; ipucuna gerek yok.")
    rakam = d["cozum"][i]
    yeni = temiz_tahta(d["bulmaca"], tahta)
    yeni = yeni[:i] + rakam + yeni[i + 1:]
    if conn.execute(
        "UPDATE sudoku_oyun SET tahta = ?, ipucu = ipucu + 1 WHERE duello_id = ? AND kullanici_id = ? AND bitis IS NULL AND ipucu < ?",
        (yeni, duello_id, kid, IPUCU_EN_COK),
    ).rowcount != 1:
        conn.rollback()
        raise SudokuHatasi("İpucu hakkın bitti.")
    conn.commit()
    return {"index": i, "rakam": rakam, "ipucu": o["ipucu"] + 1, "kalan": IPUCU_EN_COK - o["ipucu"] - 1}


def gecen_sn(o: sqlite3.Row) -> int:
    """Oyuncunun bulmacayı açtığından bu yana (bitmişse bitişe kadar) geçen süre — sunucu saati."""
    son = _dt(o["bitis"]) if o["bitis"] else _simdi()
    return max(0, int((son - _dt(o["baslama"])).total_seconds()))


def gonder(conn: sqlite3.Connection, duello_id: int, kid: int, tahta: str) -> dict:
    """Dolu tahtayı doğrular. {'dogru': bool, 'hata': n} ; doğruysa ayrıca 'sure_sn', 'skor'.
    Eksik/biçimsiz tahta hata sayılmaz (SudokuHatasi)."""
    d = getir(conn, duello_id, kid)
    if d is None or d["durum"] != "surer":
        raise SudokuHatasi("Düello oynanamaz durumda.")
    o = oyun(conn, duello_id, kid)
    if o is None:
        raise SudokuHatasi("Önce bulmacayı aç.")
    if o["bitis"]:
        raise SudokuHatasi("Bu düelloyu zaten bitirdin.")
    tahta = (tahta or "").strip()
    if len(tahta) != 81 or not tahta.isascii() or not tahta.isdigit() or "0" in tahta:
        raise SudokuHatasi("Tahtayı tamamen doldur.")
    if tahta != d["cozum"]:
        conn.execute(
            "UPDATE sudoku_oyun SET hata = hata + 1 WHERE duello_id = ? AND kullanici_id = ? AND bitis IS NULL",
            (duello_id, kid),
        )
        conn.commit()
        return {"dogru": False, "hata": oyun(conn, duello_id, kid)["hata"]}
    simdi = zaman.simdi_str()
    sure = max(0, int((_dt(simdi) - _dt(o["baslama"])).total_seconds()))
    conn.execute(
        "UPDATE sudoku_oyun SET bitis = ?, sure_sn = ? WHERE duello_id = ? AND kullanici_id = ? AND bitis IS NULL",
        (simdi, sure, duello_id, kid),
    )
    bitenler = conn.execute(
        "SELECT COUNT(*) FROM sudoku_oyun WHERE duello_id = ? AND bitis IS NOT NULL", (duello_id,)
    ).fetchone()[0]
    if bitenler >= 2:
        conn.execute("UPDATE sudoku_duello SET durum = 'bitti' WHERE id = ?", (duello_id,))
    conn.commit()
    son = oyun(conn, duello_id, kid)
    return {"dogru": True, "hata": son["hata"], "ipucu": son["ipucu"], "sure_sn": sure,
            "skor": sure + HATA_CEZA * son["hata"] + IPUCU_CEZA * son["ipucu"]}


def skor(o: sqlite3.Row | None) -> int | None:
    """Süre + 10×hata + 15×ipucu; bitirmeyen için None."""
    if o is None or not o["bitis"]:
        return None
    return o["sure_sn"] + HATA_CEZA * o["hata"] + IPUCU_CEZA * o["ipucu"]


def kapat_sureleri(conn: sqlite3.Connection) -> None:
    """Süresi dolan düelloları kapatır. Bekleyen (kabul edilmemiş) meydan okuma 24 saatte 'doldu' olur.
    Süren düello: tam biri bitirdiyse ve diğeri BAŞLAMIŞSA bitirene galibiyet ('bitti');
    rakip hiç başlamadıysa ya da kimse bitirmediyse 'doldu' (puan yok)."""
    simdi = zaman.simdi_str()
    bek = (_simdi() - timedelta(hours=SURE_SAAT)).strftime(zaman.BICIM)
    degisti = conn.execute(
        "UPDATE sudoku_duello SET durum = 'doldu' WHERE durum = 'bekliyor' AND olusturma < ?", (bek,)
    ).rowcount
    for d in conn.execute(
        "SELECT id FROM sudoku_duello WHERE durum = 'surer' AND son_tarih < ?", (simdi,)
    ).fetchall():
        oy = conn.execute("SELECT * FROM sudoku_oyun WHERE duello_id = ?", (d["id"],)).fetchall()
        biten = [x for x in oy if x["bitis"]]
        yeni = "bitti" if len(biten) == 1 and len(oy) == 2 else "doldu"
        conn.execute("UPDATE sudoku_duello SET durum = ? WHERE id = ?", (yeni, d["id"]))
        degisti += 1
    if degisti:
        conn.commit()


# --- sonuç / puan ---

def sonuc(conn: sqlite3.Connection, d: sqlite3.Row) -> dict | None:
    """Biten düello için {'kuran': 'galibiyet'|'beraberlik'|'maglubiyet', 'rakip': ..., 'skorlar': {kid: skor|None},
    'tarih': 'YYYY-MM-DD'}; bitmemişse None. Bitirmeyen (başlamış) oyuncu kaybeder."""
    if d["durum"] != "bitti":
        return None
    oy = {x["kullanici_id"]: x for x in conn.execute("SELECT * FROM sudoku_oyun WHERE duello_id = ?", (d["id"],))}
    sk = {k: skor(oy.get(k)) for k in (d["kuran_kid"], d["rakip_kid"])}
    a, b = sk[d["kuran_kid"]], sk[d["rakip_kid"]]
    if a is None and b is None:
        return None
    if a is not None and (b is None or a < b):
        kur, rak = "galibiyet", "maglubiyet"
    elif b is not None and (a is None or b < a):
        kur, rak = "maglubiyet", "galibiyet"
    else:
        kur = rak = "beraberlik"
    bitisler = [x["bitis"] for x in oy.values() if x["bitis"]]
    tarih = (max(bitisler) if len(bitisler) == 2 else d["son_tarih"])[:10]
    return {"kuran": kur, "rakip": rak, "skorlar": sk, "tarih": tarih}


def _puanlar(conn: sqlite3.Connection, hb: str | None) -> dict[int, dict]:
    """Biten düellolardan {kid: {puan, galibiyet, oynanan}}. hb = haftanın pazartesisi (None = tüm zamanlar).
    Aynı çift günde en çok CIFT_GUNLUK_PUANLI düello puana sayar (id sırasıyla)."""
    kapat_sureleri(conn)
    son = None
    if hb is not None:
        son = (datetime.strptime(hb, "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d")  # noqa: DTZ007
    cikti: dict[int, dict] = {}
    cift: dict[tuple, int] = {}
    for d in conn.execute("SELECT * FROM sudoku_duello WHERE durum = 'bitti' ORDER BY id").fetchall():
        s = sonuc(conn, d)
        if s is None:
            continue
        if hb is not None and not (hb <= s["tarih"] < son):
            continue
        anahtar = (tuple(sorted((d["kuran_kid"], d["rakip_kid"]))), s["tarih"])
        cift[anahtar] = cift.get(anahtar, 0) + 1
        if cift[anahtar] > CIFT_GUNLUK_PUANLI:
            continue
        for kid, sonuc_ in ((d["kuran_kid"], s["kuran"]), (d["rakip_kid"], s["rakip"])):
            v = cikti.setdefault(kid, {"puan": 0, "galibiyet": 0, "oynanan": 0})
            v["puan"] += PUAN[sonuc_] * CARPAN[d["zorluk"]]
            v["galibiyet"] += int(sonuc_ == "galibiyet")
            v["oynanan"] += 1
    import sudoku_bot  # döngüsel içe aktarmayı önler (sudoku_bot sudoku'yu içe aktarır)

    sudoku_bot.puanlar_ekle(conn, cikti, hb, son)
    return cikti


def liderlik(conn: sqlite3.Connection, sinif: str, hb: str | None) -> list[dict]:
    """Sınıfın tablosu (0 puanlılar dahil): [{kid, ad, puan, galibiyet, oynanan, sira}] — puan, galibiyet azalan."""
    veri = _puanlar(conn, hb)
    satirlar = []
    for o in oduller._sinif_ogrencileri(conn, sinif):
        v = veri.get(o["kid"], {})
        satirlar.append({
            "kid": o["kid"], "ad": kisa_ad(o["ad_soyad"]), "puan": v.get("puan", 0),
            "galibiyet": v.get("galibiyet", 0), "oynanan": v.get("oynanan", 0),
        })
    satirlar.sort(key=lambda x: (-x["puan"], -x["galibiyet"], x["ad"]))
    for x in satirlar:
        x["_a"] = (x["puan"], x["galibiyet"])
    oduller._sira_ver(satirlar, "_a")
    for x in satirlar:
        x.pop("_a")
    return satirlar


def sinif_ozetleri(conn: sqlite3.Connection, hb: str | None) -> list[dict]:
    """Sınıflar arası kıyas: {sinif, mevcut, katilan, oran, puan, ort_puan}. Katılan başına ortalama puan
    (toplam değil: kalabalık sınıf haksız avantaj kazanmasın)."""
    veri = _puanlar(conn, hb)
    siniflar: dict[str, dict] = {}
    for r in conn.execute(
        "SELECT o.sinif, o.kullanici_id AS kid FROM ogrenci o JOIN kullanici k ON k.id = o.kullanici_id WHERE k.aktif = 1"
    ):
        s = siniflar.setdefault(r["sinif"], {"sinif": r["sinif"], "mevcut": 0, "katilan": 0, "puan": 0})
        s["mevcut"] += 1
        v = veri.get(r["kid"])
        if v:
            s["katilan"] += 1
            s["puan"] += v["puan"]
    for s in siniflar.values():
        s["oran"] = round(100 * s["katilan"] / s["mevcut"]) if s["mevcut"] else 0
        s["ort_puan"] = round(s["puan"] / s["katilan"], 1) if s["katilan"] else 0
    return sorted(siniflar.values(), key=lambda x: (-x["oran"], -x["ort_puan"], x["sinif"]))


def duellolarim(conn: sqlite3.Connection, kid: int) -> dict:
    """Liste sayfası için: gelen (bana gelen bekleyen), giden (benim bekleyenlerim), suren, biten (son 10).
    Her öğe: düello satırı + 'rakip' kısa adı + 'oyun' (benim kaydım) + 'sonuc'."""
    kapat_sureleri(conn)
    adlar = {r["kullanici_id"]: kisa_ad(r["ad_soyad"]) for r in conn.execute("SELECT kullanici_id, ad_soyad FROM ogrenci")}
    cikti = {"gelen": [], "giden": [], "suren": [], "biten": []}
    for d in conn.execute(
        "SELECT * FROM sudoku_duello WHERE kuran_kid = ? OR rakip_kid = ? ORDER BY id DESC LIMIT 60", (kid, kid)
    ).fetchall():
        ben_kuran = d["kuran_kid"] == kid
        e = {
            **dict(d), "rakip": adlar.get(d["rakip_kid"] if ben_kuran else d["kuran_kid"], "?"),
            "oyun": oyun(conn, d["id"], kid), "zorluk_ad": ZORLUK_AD[d["zorluk"]],
        }
        e.pop("cozum"), e.pop("bulmaca")
        if d["durum"] == "bekliyor":
            cikti["giden" if ben_kuran else "gelen"].append(e)
        elif d["durum"] == "surer":
            cikti["suren"].append(e)
        elif len(cikti["biten"]) < 10:
            s = sonuc(conn, d)
            e["benim"] = (s["kuran"] if ben_kuran else s["rakip"]) if s else None
            cikti["biten"].append(e)
    return cikti
