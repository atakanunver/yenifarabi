"""Haftalık ödüller: kiosk duyurusu + rozet + haftanın Nescafe'si (yalnızca öğrenciler, 12. sınıf DAHİL).

Üç kategori (hafta = pazartesi-pazar):
  etkinlik  A: en çok sayılan etkinlik (Günlük Görev + Hızlı Mod turu + test ödevi). Nescafe bu kategoridedir.
  istikrar  C: etkinlik yaptığı farklı gün sayısı.
  sinif     D: sınıfın katılım oranı (en az bir etkinlik yapan öğrenci / sınıf mevcudu).
Hile/yarış önlemi: Hızlı Mod günde en çok 2 tur sayılır; Maraton turu >= 60 sn, Günlük Görev >= 30 sn sürmüşse sayılır
(rastgele tıklayıp bitirilen turlar sayılmaz). Eşik altı katılımda o kategori için ödül verilmez.
Beraberlik: tüm ölçütleri eşit olanların hepsi ödül alır; tek kahve için idare karar verir (yönetici ekranı).
12. sınıf Günlük Görev'e erişemez (dondurma); onlar için Hızlı Mod ve test ödevi sayılır.
Hafta bittikten sonra sonuç `odul` tablosuna BİR KEZ yazılır; geçmiş hafta yeniden hesaplanmaz/değişmez.
"""

import sqlite3
from datetime import datetime, timedelta

import arena
import avatar
import zaman
from metin import kisa_ad

MARATON_GUNLUK_SAYILAN = 2
MARATON_MIN_SN = 60
GOREV_MIN_SN = 30
MIN_ETKINLIK = 3  # A için alt sınır
MIN_GUN = 3  # C için alt sınır
MIN_KATILAN = 5  # D için sınıfta en az bu kadar katılımcı
KATEGORILER = {
    "etkinlik": "En Çok Etkinlik",
    "istikrar": "En İstikrarlı",
    "sinif": "En Katılımcı Sınıf",
}
ROZET_AD = {
    "etkinlik": "Haftanın Çalışkanı",
    "istikrar": "Haftanın İstikrarlısı",
    "sinif": "Haftanın Sınıfı",
}


def _dt(s: str) -> datetime:
    return datetime.strptime(s, zaman.BICIM)


def hafta_basi(d: datetime | None = None) -> str:
    d = d or zaman.simdi()
    return (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")


def hafta_sonu(hb: str) -> str:
    return (datetime.strptime(hb, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")  # noqa: DTZ007


def onceki_hafta(hb: str) -> str:
    return (datetime.strptime(hb, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")  # noqa: DTZ007


def hafta_bitti_mi(hb: str) -> bool:
    return zaman.simdi().strftime("%Y-%m-%d") > hafta_sonu(hb)


def _ogrenciler(conn: sqlite3.Connection) -> dict[int, dict]:
    return {
        r["kullanici_id"]: {"kid": r["kullanici_id"], "oid": r["id"], "ad": kisa_ad(r["ad_soyad"]), "sinif": r["sinif"],
                            "olaylar": []}
        for r in conn.execute(
            "SELECT o.id, o.kullanici_id, o.ad_soyad, o.sinif FROM ogrenci o JOIN kullanici k ON k.id = o.kullanici_id"
            " WHERE k.aktif = 1 AND o.kullanici_id IS NOT NULL"
        )
    }


def haftalik(conn: sqlite3.Connection, hb: str | None, son: str | None = None, testler: bool = True) -> dict[int, dict]:
    """Öğrenci başına {kid, ad, sinif, etkinlik, gun, dogru, cozulen} (yalnızca >= 1 sayılan etkinliği olanlar).
    hb None = tüm zamanlar. cozulen = sayılan Günlük Görev + Hızlı Mod turlarındaki soru sayısı (test ödevi soru sayısı katılmaz).
    testler=False: test ödevi etkinlik sayılmaz (Arena liderliği)."""
    ogr = _ogrenciler(conn)
    bas = hb or "0000-01-01"
    son = son or (hafta_sonu(hb) if hb else "9999-12-31")
    for r in conn.execute(
        "SELECT kullanici_id, gun, basla, bitis, dogru FROM bilgi_tur WHERE durum = 'tamam' AND gun BETWEEN ? AND ?",
        (bas, son),
    ):
        if r["kullanici_id"] in ogr and r["bitis"] and (_dt(r["bitis"]) - _dt(r["basla"])).total_seconds() >= GOREV_MIN_SN:
            ogr[r["kullanici_id"]]["olaylar"].append((r["gun"], r["dogru"], "gorev", r["bitis"], 5))
    gunluk: dict[tuple[int, str], int] = {}
    for r in conn.execute(
        "SELECT m.kullanici_id, m.basla, m.bitis, m.dogru FROM maraton m WHERE m.bitis IS NOT NULL"
        " AND substr(m.bitis, 1, 10) BETWEEN ? AND ?"
        " AND NOT EXISTS (SELECT 1 FROM maraton_soru s WHERE s.maraton_id = m.id AND s.cevap = -2) ORDER BY m.bitis",
        (bas, son),
    ):
        if r["kullanici_id"] not in ogr or (_dt(r["bitis"]) - _dt(r["basla"])).total_seconds() < MARATON_MIN_SN:
            continue
        gun = r["bitis"][:10]
        anahtar = (r["kullanici_id"], gun)
        if gunluk.get(anahtar, 0) >= MARATON_GUNLUK_SAYILAN:
            continue
        gunluk[anahtar] = gunluk.get(anahtar, 0) + 1
        ogr[r["kullanici_id"]]["olaylar"].append((gun, r["dogru"], "maraton", r["bitis"], 10))
    for r in conn.execute(
        "SELECT o.kullanici_id, t.zaman FROM odev_teslim t JOIN odev d ON d.id = t.odev_id JOIN ogrenci o ON o.id = t.ogrenci_id"
        " WHERE t.durum = 'tamam' AND d.tur = 'test' AND substr(t.zaman, 1, 10) BETWEEN ? AND ?",
        (bas, son),
    ) if testler else ():
        if r["kullanici_id"] in ogr:
            ogr[r["kullanici_id"]]["olaylar"].append((r["zaman"][:10], 0, "test", r["zaman"], 0))
    cikti = {}
    for kid, d in ogr.items():
        o = d.pop("olaylar")
        if o:
            cikti[kid] = {**d, "etkinlik": len(o), "gun": len({x[0] for x in o}), "dogru": sum(x[1] for x in o),
                          "cozulen": sum(x[4] for x in o)}
    return cikti


def _en_iyiler(adaylar: list[dict], anahtar) -> list[dict]:
    if not adaylar:
        return []
    ust = max(anahtar(a) for a in adaylar)
    return [a for a in adaylar if anahtar(a) == ust]


def siralama(conn: sqlite3.Connection, hb: str) -> dict:
    """Haftanın kazananları (kaydetmeden): {'etkinlik': [...], 'istikrar': [...], 'sinif': [...], 'katilim': {...}}."""
    veri = haftalik(conn, hb)
    ogr = _ogrenciler(conn)
    adaylar = list(veri.values())
    a = _en_iyiler([x for x in adaylar if x["etkinlik"] >= MIN_ETKINLIK], lambda x: (x["etkinlik"], x["gun"], x["dogru"]))
    c = _en_iyiler([x for x in adaylar if x["gun"] >= MIN_GUN], lambda x: (x["gun"], x["etkinlik"], x["dogru"]))
    mevcut: dict[str, int] = {}
    for d in ogr.values():
        mevcut[d["sinif"]] = mevcut.get(d["sinif"], 0) + 1
    katilan: dict[str, int] = {}
    for x in adaylar:
        katilan[x["sinif"]] = katilan.get(x["sinif"], 0) + 1
    siniflar = [
        {"sinif": s, "katilan": n, "mevcut": mevcut[s], "oran": round(100 * n / mevcut[s])}
        for s, n in katilan.items() if n >= MIN_KATILAN
    ]
    d_ = _en_iyiler(siniflar, lambda x: (x["oran"], x["katilan"]))
    return {"etkinlik": a, "istikrar": c, "sinif": d_, "katilan_ogrenci": len(adaylar), "toplam_ogrenci": len(ogr)}


def kapat(conn: sqlite3.Connection, hb: str) -> int:
    """Biten haftanın ödüllerini yazar (idempotent, değişmez). Eklenen satır sayısı döner; hafta bitmediyse hata."""
    if not hafta_bitti_mi(hb):
        raise ValueError("Hafta henüz bitmedi.")
    simdi = zaman.simdi_str()
    if conn.execute("INSERT OR IGNORE INTO odul_hafta (hafta_basi, kapanis) VALUES (?, ?)", (hb, simdi)).rowcount != 1:
        conn.rollback()
        return 0  # bu hafta zaten kapatılmış: sonuç değişmez
    s = siralama(conn, hb)
    eklenen = 0
    for x in s["etkinlik"]:
        eklenen += _yaz(conn, hb, "etkinlik", x["kid"], x["sinif"], x["etkinlik"],
                        f"{x['etkinlik']} etkinlik, {x['gun']} gün", 1, simdi)
    for x in s["istikrar"]:
        eklenen += _yaz(conn, hb, "istikrar", x["kid"], x["sinif"], x["gun"],
                        f"{x['gun']} farklı gün, {x['etkinlik']} etkinlik", 0, simdi)
    for x in s["sinif"]:
        eklenen += _yaz(conn, hb, "sinif", None, x["sinif"], x["oran"],
                        f"%{x['oran']} katılım ({x['katilan']}/{x['mevcut']})", 0, simdi)
    conn.commit()
    return eklenen


def _yaz(conn, hb, kategori, kid, sinif, deger, ayrinti, kahve, simdi) -> int:
    return conn.execute(
        "INSERT OR IGNORE INTO odul (hafta_basi, kategori, anahtar, kullanici_id, sinif, deger, ayrinti, kahve, zaman)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (hb, kategori, f"{kid or ''}|{sinif or ''}", kid, sinif, deger, ayrinti, kahve, simdi),
    ).rowcount


def kayitli(conn: sqlite3.Connection, hb: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT od.*, o.ad_soyad FROM odul od LEFT JOIN ogrenci o ON o.kullanici_id = od.kullanici_id"
        " WHERE od.hafta_basi = ? ORDER BY od.kategori, od.id",
        (hb,),
    ).fetchall()


def _kim(x: dict) -> str:
    return f"{x['ad']} ({x['sinif']})"


def _liste(xs: list[dict], ayrinti) -> str:
    return " ve ".join(f"{_kim(x)} — {ayrinti(x)}" for x in xs)


def kiosk_ogeleri(conn: sqlite3.Connection) -> list[dict]:
    """Kiosk duyuruları: CUMA geçici durum (içinde bulunulan hafta), PAZARTESİ kesin sonuç (geçen hafta). Diğer günler boş.
    Kişisel veri yalnızca kısa ad + sınıf. Pazartesi geçen haftayı (henüz yazılmadıysa) kaydeder."""
    simdi = zaman.simdi()
    gun = simdi.weekday()
    if gun == 4:
        s = siralama(conn, hafta_basi(simdi))
        baslik = "HAFTANIN ÇALIŞKANLARI (GEÇİCİ)"
        ek = " Sonuçlar pazartesi kesinleşir."
        if not (s["etkinlik"] or s["istikrar"] or s["sinif"]):
            return [{"baslik": "HAFTALIK ÇALIŞMA ÖDÜLÜ", "metin": (
                f"Bu hafta henüz ödül şartını (en az {MIN_ETKINLIK} etkinlik) sağlayan yok. Bugün Günlük Görev, Hızlı Mod "
                "ya da test ödeviyle yarışa katıl! Haftanın en çok etkinlik yapanına 1 Nescafe kahve.")}]
    elif gun == 0:
        hb = onceki_hafta(hafta_basi(simdi))
        kapat(conn, hb)
        k = kayitli(conn, hb)
        s = {
            "etkinlik": [{"ad": kisa_ad(r["ad_soyad"] or ""), "sinif": r["sinif"], "etkinlik": r["deger"], "gun": 0, "dogru": 0, "r": r}
                         for r in k if r["kategori"] == "etkinlik"],
            "istikrar": [{"ad": kisa_ad(r["ad_soyad"] or ""), "sinif": r["sinif"], "gun": r["deger"], "etkinlik": 0, "dogru": 0, "r": r}
                         for r in k if r["kategori"] == "istikrar"],
            "sinif": [{"sinif": r["sinif"], "oran": r["deger"], "r": r} for r in k if r["kategori"] == "sinif"],
        }
        baslik = "GEÇEN HAFTANIN ÇALIŞKANLARI"
        ek = " Tebrikler!"
        if not any(s.values()):
            return []  # pazartesi kazananı yoksa ekranda olumsuz mesaj yok
    else:
        return []
    ogeler = []
    if s["etkinlik"]:
        ogeler.append({"baslik": f"{baslik}: EN ÇOK ETKİNLİK", "metin":
                       _liste(s["etkinlik"], lambda x: f"{x['etkinlik']} etkinlik") + ". Nescafe kahve ödülü!" + ek})
    if s["istikrar"]:
        ogeler.append({"baslik": f"{baslik}: EN İSTİKRARLI", "metin":
                       _liste(s["istikrar"], lambda x: f"{x['gun']} farklı gün") + "." + ek})
    if s["sinif"]:
        ogeler.append({"baslik": f"{baslik}: EN KATILIMCI SINIF", "metin":
                       " ve ".join(f"{x['sinif']} — %{x['oran']} katılım" for x in s["sinif"]) + "." + ek})
    return ogeler


def ogrenci_oduller(conn: sqlite3.Connection, ogrenci: sqlite3.Row) -> list[dict]:
    """Öğrencinin kendi (yalnızca kendi) ödülleri: bireysel kazandıkları + katıldığı haftada kazanan sınıfı. En yeniden eskiye."""
    liste = []
    for r in conn.execute(
        "SELECT * FROM odul WHERE kullanici_id = ? OR (kullanici_id IS NULL AND sinif = ?) ORDER BY hafta_basi DESC, id",
        (ogrenci["kullanici_id"], ogrenci["sinif"]),
    ):
        if r["kullanici_id"] is None:  # sınıf ödülü: yalnızca o hafta etkinlik yapan sınıf üyesine
            if ogrenci["kullanici_id"] not in haftalik(conn, r["hafta_basi"]):
                continue
        liste.append({"hafta_basi": r["hafta_basi"], "kategori": r["kategori"], "ad": ROZET_AD[r["kategori"]],
                      "ayrinti": r["ayrinti"], "kahve": bool(r["kahve"]), "kahve_teslim": r["kahve_teslim"]})
    return liste


def kahve_teslim(conn: sqlite3.Connection, odul_id: int, teslim: bool) -> None:
    if conn.execute(
        "UPDATE odul SET kahve_teslim = ? WHERE id = ? AND kahve = 1", (zaman.simdi_str() if teslim else None, odul_id)
    ).rowcount != 1:
        conn.rollback()
        raise ValueError("Kahve ödülü bulunamadı.")
    conn.commit()


LIDER_ILK = 10


def _xp_toplamlari(conn: sqlite3.Connection, hb: str | None) -> dict[int, int]:
    if hb:
        satirlar = conn.execute(
            "SELECT kullanici_id, SUM(miktar) FROM bilgi_xp WHERE gun BETWEEN ? AND ? GROUP BY kullanici_id", (hb, hafta_sonu(hb))
        )
    else:
        satirlar = conn.execute("SELECT kullanici_id, SUM(miktar) FROM bilgi_xp GROUP BY kullanici_id")
    return {r[0]: r[1] for r in satirlar}


def _sirala(satirlar: list[dict], ben: int | None) -> dict:
    """Aynı değer aynı sırayı alır (1,1,3). İlk LIDER_ILK + (varsa) kendi sırası; başkalarının verisi yalnızca ilk listede."""
    satirlar = sorted(satirlar, key=lambda x: (-x["deger"], x["ad"]))
    onceki, sira = None, 0
    for i, x in enumerate(satirlar, 1):
        if x["deger"] != onceki:
            sira, onceki = i, x["deger"]
        x["sira"] = sira
        x["ben"] = x["kid"] == ben
    ben_satir = next((x for x in satirlar if x["ben"]), None)
    ust = None
    if ben_satir:  # rekabet: bir üst sıradakini geçmek için gereken fark (eşitlerde aynı sıradakiler "üst" sayılmaz)
        yukari = [x for x in satirlar if x["deger"] > ben_satir["deger"]]
        if yukari:
            y = yukari[-1]
            ust = {"ad": y["ad"], "sira": y["sira"], "fark": y["deger"] - ben_satir["deger"]}
    return {"ilk": satirlar[:LIDER_ILK], "benim": next((x for x in satirlar if x["ben"] and x not in satirlar[:LIDER_ILK]), None),
            "katilan": len(satirlar), "ben": ben_satir, "ust": ust}


def liderlik(conn: sqlite3.Connection, hb: str | None, ben: int | None = None) -> dict:
    """Bilgi Arenası liderliği (Günlük Görev + Hızlı Mod; test ödevi sayılmaz). hb None = tüm zamanlar.
    Üç tablo: xp (kazanılan XP), dogru (doğru cevap), cozulen (çözülen soru). Değeri 0 olan listede yer almaz."""
    veri = haftalik(conn, hb, testler=False)
    xp = _xp_toplamlari(conn, hb)
    ogr = _ogrenciler(conn)
    xp_satir = [{"kid": k, "ad": ogr[k]["ad"], "sinif": ogr[k]["sinif"], "deger": v} for k, v in xp.items() if k in ogr and v > 0]
    sat = lambda anahtar: [  # noqa: E731
        {"kid": k, "ad": x["ad"], "sinif": x["sinif"], "deger": x[anahtar]} for k, x in veri.items() if x[anahtar] > 0
    ]
    tablolar = {"xp": _sirala(xp_satir, ben), "dogru": _sirala(sat("dogru"), ben), "cozulen": _sirala(sat("cozulen"), ben)}
    _avatar_ekle(conn, tablolar)
    return tablolar


def _avatar_ekle(conn: sqlite3.Connection, tablolar: dict) -> None:
    """Listedeki öğrencilere küçük avatar simgesi için {'cfg', 'sev'} ekler (yalnızca ilk liste + kendi satırı)."""
    satirlar = [x for t in tablolar.values() for x in t["ilk"] + ([t["benim"]] if t["benim"] else [])]
    kidler = {x["kid"] for x in satirlar}
    if not kidler:
        return
    yer = ",".join("?" * len(kidler))
    cfg = {r["kullanici_id"]: dict(r) for r in conn.execute(f"SELECT * FROM avatar WHERE kullanici_id IN ({yer})", list(kidler))}
    xp = {r[0]: r[1] for r in conn.execute(f"SELECT kullanici_id, SUM(miktar) FROM bilgi_xp WHERE kullanici_id IN ({yer}) GROUP BY 1", list(kidler))}
    for x in satirlar:
        x["av"] = {"cfg": avatar.cfg_temiz(cfg.get(x["kid"])), "sev": arena.seviye_hesapla(xp.get(x["kid"], 0))["no"]}
