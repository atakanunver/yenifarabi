"""Akademik Gelişim Analizi: yalnızca GERÇEK kayıtlardan hesaplanan göstergeler (veri uydurulmaz).

Akademik gösterge kaynakları: platform içi test ödevleri (okul.db) + Google Form kazanım testleri
(soru_havuzu, salt-okunur). Arena/Maraton çalışma katılımı AYRI bir göstergedir: akademik başarıya
karıştırılmaz (Arena'daki kazanım eşleşmesi çoğunlukla otomatik atanmıştır).

İlkeler:
- Küçük grup: bir grupta (sınıf x ders vb.) verisi olan öğrenci sayısı < ESIK_N ise grup değeri gösterilmez.
- Yetersiz veri: bir ders/dönemde soru sayısı < MIN_SORU ise yüzde ve trend gösterilmez ("veri az").
- Risk puanı/etiketi YOK. "Tekrar edilebilir kazanımlar" kanıtıyla (doğru/toplam) listelenir; hüküm değildir
  ve yalnızca öğretmen/yönetici ile öğrencinin kendisine, destekleyici dille gösterilir.
- Eşleşmeyen/eksik kaynak: kaynak_erisildi=False döner; arayüz bunu açıkça söyler.
"""

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

import odevler
import zaman
from ayarlar import AYAR
from metin import tr_kucuk

ESIK_N = 5
MIN_SORU = 5
PENCERE = 30  # gün; trend: son PENCERE gün ile bir önceki PENCERE gün
TEKRAR_YUZDE = 50  # bu yüzdenin altı ve en az TEKRAR_MIN soru: "tekrar edilebilir"
TEKRAR_MIN = 3


def _gun(s: str | None) -> str:
    return (s or "")[:10]


def ders_anahtari(ders: str) -> str:
    return tr_kucuk((ders or "").strip())


def _yuzde(d: int, n: int) -> int | None:
    return round(100 * d / n) if n else None


def satirlar(conn: sqlite3.Connection, ogrenciler: list[sqlite3.Row], form: dict[int, list]) -> list[dict]:
    """Öğrenci x (ders, kazanım) x test kayıtları: {ogrenci_id, ders, kazanim, dogru, toplam, tarih, kaynak}.
    form: okul_no -> TestSonucu listesi (erişilemezse boş sözlük)."""
    kimlik = {o["id"]: o for o in ogrenciler}
    if not kimlik:
        return []
    cikti: list[dict] = []
    yer = ",".join("?" * len(kimlik))
    soru_onbellek: dict[int, list[dict]] = {}
    for t in conn.execute(
        "SELECT o.id AS odev_id, o.ders, o.baslik, t.ogrenci_id, t.cevaplar, t.zaman FROM odev_teslim t"
        " JOIN odev o ON o.id = t.odev_id WHERE o.tur = 'test' AND t.cevaplar IS NOT NULL"
        f" AND t.ogrenci_id IN ({yer})",
        list(kimlik),
    ):
        if t["odev_id"] not in soru_onbellek:
            soru_onbellek[t["odev_id"]] = odevler.sorular(conn, t["odev_id"])
        cevap = json.loads(t["cevaplar"])
        for s in soru_onbellek[t["odev_id"]]:
            cikti.append({
                "ogrenci_id": t["ogrenci_id"], "ders": ders_anahtari(t["ders"]),
                "kazanim": s["kazanim"] or t["baslik"], "dogru": int(cevap.get(str(s["id"])) == s["dogru"]),
                "toplam": 1, "tarih": _gun(t["zaman"]), "kaynak": "odev",
            })
    for o in ogrenciler:
        for f in form.get(o["okul_no"], []):
            cikti.append({
                "ogrenci_id": o["id"], "ders": ders_anahtari(f.ders), "kazanim": f.kazanim,
                "dogru": f.dogru, "toplam": f.toplam, "tarih": _gun(f.tarih), "kaynak": "form",
            })
    return cikti


def _topla(rows: list[dict]) -> tuple[int, int]:
    return sum(r["dogru"] for r in rows), sum(r["toplam"] for r in rows)


def _trend(rows: list[dict], bugun: str) -> dict:
    """Son PENCERE gün ile önceki PENCERE günü karşılaştırır; ikisinde de MIN_SORU yoksa 'yetersiz'."""
    d = datetime.strptime(bugun, "%Y-%m-%d")  # noqa: DTZ007
    sinir1 = (d - timedelta(days=PENCERE)).strftime("%Y-%m-%d")
    sinir2 = (d - timedelta(days=2 * PENCERE)).strftime("%Y-%m-%d")
    son = [r for r in rows if r["tarih"] > sinir1]
    once = [r for r in rows if sinir2 < r["tarih"] <= sinir1]
    (d1, n1), (d0, n0) = _topla(son), _topla(once)
    if n1 < MIN_SORU or n0 < MIN_SORU:
        return {"durum": "yetersiz", "mesaj": f"Karşılaştırma için her dönemde en az {MIN_SORU} soru gerekir."}
    fark = _yuzde(d1, n1) - _yuzde(d0, n0)
    return {"durum": "artti" if fark > 0 else ("azaldi" if fark < 0 else "sabit"), "fark": fark,
            "son": _yuzde(d1, n1), "once": _yuzde(d0, n0)}


def calisma_katilimi(conn: sqlite3.Connection, kullanici_id: int, bugun: str) -> dict:
    """Son PENCERE günde tamamlanan Arena görevi / Maraton sayısı (akademik gösterge DEĞİL, çalışma sıklığı)."""
    sinir = (datetime.strptime(bugun, "%Y-%m-%d") - timedelta(days=PENCERE)).strftime("%Y-%m-%d")  # noqa: DTZ007
    arena = conn.execute(
        "SELECT count(*) FROM bilgi_tur WHERE kullanici_id = ? AND durum = 'tamam' AND gun > ?", (kullanici_id, sinir)
    ).fetchone()[0]
    mar = conn.execute(
        "SELECT count(*) FROM maraton m WHERE m.kullanici_id = ? AND m.bitis IS NOT NULL AND substr(m.bitis, 1, 10) > ?"
        " AND NOT EXISTS (SELECT 1 FROM maraton_soru s WHERE s.maraton_id = m.id AND s.cevap = -2)",
        (kullanici_id, sinir),
    ).fetchone()[0]
    return {"arena": arena, "maraton": mar, "toplam": arena + mar}


def odev_durumu(conn: sqlite3.Connection, ogrenci: sqlite3.Row, bugun: str) -> dict:
    """Son PENCERE gündeki sınıf ödevlerinden kaçı teslim edilmiş (teslim tarihi geçmiş olanlar payda)."""
    sinir = (datetime.strptime(bugun, "%Y-%m-%d") - timedelta(days=PENCERE)).strftime("%Y-%m-%d")  # noqa: DTZ007
    verilen = conn.execute(
        "SELECT count(*) FROM odev WHERE sinif = ? AND substr(teslim, 1, 10) > ? AND substr(teslim, 1, 10) <= ?",
        (ogrenci["sinif"], sinir, bugun),
    ).fetchone()[0]
    teslim = conn.execute(
        "SELECT count(*) FROM odev_teslim t JOIN odev o ON o.id = t.odev_id WHERE t.ogrenci_id = ? AND o.sinif = ?"
        " AND substr(o.teslim, 1, 10) > ? AND substr(o.teslim, 1, 10) <= ?",
        (ogrenci["id"], ogrenci["sinif"], sinir, bugun),
    ).fetchone()[0]
    return {"verilen": verilen, "teslim": teslim, "oran": _yuzde(teslim, verilen) if verilen else None}


def ogrenci_raporu(
    conn: sqlite3.Connection, ogrenci: sqlite3.Row, form: dict[int, list], kaynak_erisildi: bool = True
) -> dict:
    """Bir öğrencinin raporu. Veri yoksa dersler boş döner; hiçbir değer varsayılmaz."""
    bugun = zaman.simdi().strftime("%Y-%m-%d")
    rows = satirlar(conn, [ogrenci], form)
    ders_satir: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        ders_satir[r["ders"]].append(r)
    dersler, tekrar = [], []
    for ders, liste in sorted(ders_satir.items()):
        d, n = _topla(liste)
        kaz: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in liste:
            kaz[r["kazanim"]][0] += r["dogru"]
            kaz[r["kazanim"]][1] += r["toplam"]
        kazanimlar = [
            {"kazanim": k, "dogru": a, "toplam": b, "yuzde": _yuzde(a, b), "basarili": b > 0 and a / b >= AYAR.kazanim_esik}
            for k, (a, b) in sorted(kaz.items())
        ]
        for k in kazanimlar:
            if k["toplam"] >= TEKRAR_MIN and k["yuzde"] < TEKRAR_YUZDE:
                tekrar.append({"ders": ders, **k})
        dersler.append({
            "ders": ders, "dogru": d, "toplam": n, "yeterli": n >= MIN_SORU,
            "yuzde": _yuzde(d, n) if n >= MIN_SORU else None,
            "kazanimlar": kazanimlar, "basarili_kazanim": sum(k["basarili"] for k in kazanimlar),
            "trend": _trend(liste, bugun),
        })
    return {
        "ogrenci": ogrenci, "dersler": dersler, "tekrar": tekrar, "odev": odev_durumu(conn, ogrenci, bugun),
        "calisma": calisma_katilimi(conn, ogrenci["kullanici_id"], bugun) if ogrenci["kullanici_id"] else None,
        "kaynak_erisildi": kaynak_erisildi, "veri_var": bool(rows), "esik": AYAR.kazanim_esik,
    }


def sinif_raporu(
    conn: sqlite3.Connection, sinif: str, form: dict[int, list], kaynak_erisildi: bool = True, ders: str | None = None
) -> dict:
    """Sınıf (ve isteğe bağlı ders) raporu. Verisi olan öğrenci sayısı < ESIK_N ise grup değerleri gizlenir."""
    bugun = zaman.simdi().strftime("%Y-%m-%d")
    ogrenciler = conn.execute("SELECT * FROM ogrenci WHERE sinif = ? ORDER BY okul_no", (sinif,)).fetchall()
    rows = satirlar(conn, ogrenciler, form)
    ders_k = ders_anahtari(ders) if ders else None
    if ders_k:
        rows = [r for r in rows if r["ders"] == ders_k]
    ogr_satir: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        ogr_satir[r["ogrenci_id"]].append(r)
    ders_satir: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        ders_satir[r["ders"]].append(r)
    dersler = []
    for dk, liste in sorted(ders_satir.items()):
        verili = {r["ogrenci_id"] for r in liste}
        d = {"ders": dk, "ogrenci": len(verili), "gizli": len(verili) < ESIK_N}
        if not d["gizli"]:
            dd, nn = _topla(liste)
            d.update(soru=nn, yuzde=_yuzde(dd, nn), trend=_trend(liste, bugun), kazanimlar=_sinif_kazanimlari(liste))
        dersler.append(d)
    ogr_ozet = []
    for o in ogrenciler:
        liste = ogr_satir.get(o["id"], [])
        d, n = _topla(liste)
        od = odev_durumu(conn, o, bugun)
        ogr_ozet.append({
            "id": o["id"], "okul_no": o["okul_no"], "ad_soyad": o["ad_soyad"], "toplam": n,
            "yuzde": _yuzde(d, n) if n >= MIN_SORU else None, "odev": od,
            "calisma": calisma_katilimi(conn, o["kullanici_id"], bugun)["toplam"] if o["kullanici_id"] else 0,
        })
    teslim_verilen = sum(x["odev"]["verilen"] for x in ogr_ozet)
    teslim = sum(x["odev"]["teslim"] for x in ogr_ozet)
    return {
        "sinif": sinif, "mevcut": len(ogrenciler), "verili_ogrenci": len(ogr_satir), "dersler": dersler,
        "ogrenciler": ogr_ozet, "kaynak_erisildi": kaynak_erisildi, "esik_n": ESIK_N, "min_soru": MIN_SORU,
        "odev_orani": _yuzde(teslim, teslim_verilen) if teslim_verilen else None,
        "calisan": sum(1 for x in ogr_ozet if x["calisma"] > 0),
    }


def _sinif_kazanimlari(liste: list[dict]) -> list[dict]:
    """Sınıfın kazanım bazında durumu: başarılı (eşik üstü) öğrenci oranı. Kazanımda < ESIK_N öğrenci varsa atlanır."""
    ogr: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in liste:
        ogr[r["kazanim"]][r["ogrenci_id"]][0] += r["dogru"]
        ogr[r["kazanim"]][r["ogrenci_id"]][1] += r["toplam"]
    cikti = []
    for kaz, per in ogr.items():
        if len(per) < ESIK_N:
            continue
        basarili = sum(1 for d, n in per.values() if n and d / n >= AYAR.kazanim_esik)
        d, n = sum(v[0] for v in per.values()), sum(v[1] for v in per.values())
        cikti.append({"kazanim": kaz, "ogrenci": len(per), "basarili": basarili,
                      "oran": _yuzde(basarili, len(per)), "yuzde": _yuzde(d, n)})
    return sorted(cikti, key=lambda x: (x["oran"], x["kazanim"]))


def okul_raporu(conn: sqlite3.Connection, form: dict[int, list], kaynak_erisildi: bool = True) -> dict:
    """Yönetici genel görünümü: sınıf x ders; küçük gruplar gizli. Bireysel veri yok."""
    bugun = zaman.simdi().strftime("%Y-%m-%d")
    ogrenciler = conn.execute("SELECT * FROM ogrenci ORDER BY sinif, okul_no").fetchall()
    rows = satirlar(conn, ogrenciler, form)
    sinif_of = {o["id"]: o["sinif"] for o in ogrenciler}
    mevcut: dict[str, int] = defaultdict(int)
    for o in ogrenciler:
        mevcut[o["sinif"]] += 1
    grup: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        grup[(sinif_of[r["ogrenci_id"]], r["ders"])].append(r)
    siniflar = []
    for sinif in sorted(mevcut):
        dersler = []
        for (s, dk), liste in sorted(grup.items()):
            if s != sinif:
                continue
            verili = {r["ogrenci_id"] for r in liste}
            satir = {"ders": dk, "ogrenci": len(verili), "gizli": len(verili) < ESIK_N}
            if not satir["gizli"]:
                d, n = _topla(liste)
                satir.update(soru=n, yuzde=_yuzde(d, n), trend=_trend(liste, bugun))
            dersler.append(satir)
        od_ver = od_tes = calisan = 0
        for o in (x for x in ogrenciler if x["sinif"] == sinif):
            od = odev_durumu(conn, o, bugun)
            od_ver += od["verilen"]
            od_tes += od["teslim"]
            if o["kullanici_id"] and calisma_katilimi(conn, o["kullanici_id"], bugun)["toplam"] > 0:
                calisan += 1
        siniflar.append({
            "sinif": sinif, "mevcut": mevcut[sinif], "dersler": dersler,
            "verili": len({r["ogrenci_id"] for r in rows if sinif_of[r["ogrenci_id"]] == sinif}),
            "odev_orani": _yuzde(od_tes, od_ver) if od_ver else None, "calisan": calisan,
            "calisan_gizli": mevcut[sinif] < ESIK_N,
        })
    return {
        "siniflar": siniflar, "ogrenci": len(ogrenciler), "verili": len({r["ogrenci_id"] for r in rows}),
        "kaynak_erisildi": kaynak_erisildi, "esik_n": ESIK_N, "min_soru": MIN_SORU, "pencere": PENCERE,
    }
