"""kazanimtest/analiz.py — form_cevap'tan sınıf/kazanım/öğrenci analizi → rapor/<sinif>.json.

Çıktıda öğrenci ismi YOKTUR (yalnızca okul_no). Analiz mantığı saf fonksiyonlarda (`analiz_hesapla`),
DB okuması ayrı (`_testleri_oku`); DB'ye yazılmaz. Pano bu JSON'u okur (tahtayoklama/CLAUDE.md değil,
kazanimtest/CLAUDE.md "Analiz raporu" bölümü).
"""

import json
import logging
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg2.extras

log = logging.getLogger("kazanimtest")
TR = ZoneInfo("Europe/Istanbul")
VARSAYILAN_ESIKLER = {"zorlanilan_esik": 0.5, "eksik_esik": 0.5, "guclu_esik": 0.8, "kazanim_min_soru": 2}
YOK = "(kazanım satırı yok)"
_ETIKET = re.compile(r"^(.*?),\s*s\.\s*(\d+)(?:\s*-\s*(\d+))?\s*$")


def esikler_oku(ayar: dict | None) -> dict:
    e = dict(VARSAYILAN_ESIKLER)
    for k, v in VARSAYILAN_ESIKLER.items():
        if ayar and ayar.get(k) is not None:
            e[k] = type(v)(ayar[k])
    return e


def _oran(d: int, n: int) -> float:
    return round(d / n, 3) if n else 0.0


def sayfalari_birlestir(etiketler) -> list[str]:
    """["Kimya 9, s. 55", "Kimya 9, s. 54"] → ["Kimya 9, s. 54-55"]; ayrıştırılamayan etiket olduğu gibi kalır."""
    sayfalar: dict[str, set[int]] = defaultdict(set)
    ham: set[str] = set()
    for e in etiketler:
        if not e:
            continue
        m = _ETIKET.match(str(e))
        if not m:
            ham.add(str(e))
            continue
        a, b = int(m.group(2)), int(m.group(3) or m.group(2))
        sayfalar[m.group(1)].update(range(a, max(a, b) + 1))
    sonuc = []
    for kitap in sorted(sayfalar):
        sirali = sorted(sayfalar[kitap])
        bas = onceki = sirali[0]
        for s in sirali[1:] + [None]:
            if s is not None and s == onceki + 1:
                onceki = s
                continue
            sonuc.append(f"{kitap}, s. {bas}" if bas == onceki else f"{kitap}, s. {bas}-{onceki}")
            if s is not None:
                bas = onceki = s
    return sonuc + sorted(ham)


def _durum(oran: float, soru: int, e: dict) -> str:
    if soru < e["kazanim_min_soru"]:
        return "az_veri"
    if oran < e["eksik_esik"]:
        return "eksik"
    if oran >= e["guclu_esik"]:
        return "guclu"
    return "orta"


def analiz_hesapla(sinif: str, testler: list[dict], cevaplar: dict, esikler: dict, aralik: dict | None = None,
                   simdi: datetime | None = None) -> dict:
    """testler: [{id, ders, hafta, olusturma(datetime), kazanim, form_url, sorular(list)}]
    cevaplar: {test_id: [(okul_no, soru_sira, secilen|None, dogru)]}"""
    test_cikti = []
    kaz_ist: dict[tuple, dict] = {}
    ogr: dict[int, dict] = {}
    for t in testler:
        sorular = t.get("sorular")
        if not sorular:
            log.warning("form_testi %s (%s): sorular NULL — analize alınmadı", t.get("id"), sinif)
            continue
        soru_cvp: dict[int, list] = defaultdict(list)
        katilanlar: set[int] = set()
        for no, sira, secilen, dogru in cevaplar.get(t["id"], []):
            if not 0 <= sira < len(sorular):
                continue
            soru_cvp[sira].append((no, secilen, bool(dogru)))
            katilanlar.add(no)
        t_dogru = t_toplam = 0
        soru_cikti = []
        for sira, s in enumerate(sorular):
            cv = soru_cvp.get(sira, [])
            dogru = sum(1 for _, _, d in cv if d)
            satir = s.get("kazanim_satiri") or YOK
            yanlis = Counter(sec for _, sec, d in cv if not d and sec is not None)
            en_cok = None
            if yanlis:
                sec, say = min(yanlis.items(), key=lambda x: (-x[1], x[0]))
                en_cok = {"sik_harfi": chr(65 + int(sec)), "oran": _oran(say, len(cv))}
            soru_cikti.append({"sira": sira + 1, "soru": str(s.get("soru", ""))[:120], "kazanim_satiri": satir,
                               "dogru_orani": _oran(dogru, len(cv)), "cevap_sayisi": len(cv),
                               "en_cok_secilen_yanlis": en_cok})
            t_dogru += dogru
            t_toplam += len(cv)
            k = kaz_ist.setdefault((t["ders"], satir), {"sorular": set(), "cevap": 0, "dogru": 0})
            k["sorular"].add((t["id"], sira))
            k["cevap"] += len(cv)
            k["dogru"] += dogru
            for no, _, d in cv:
                o = ogr.setdefault(no, {"testler": set(), "dogru": 0, "toplam": 0, "kaz": {}})
                o["testler"].add(t["id"])
                o["dogru"] += d
                o["toplam"] += 1
                kk = o["kaz"].setdefault((t["ders"], satir), {"soru": 0, "dogru": 0, "etiket": []})
                kk["soru"] += 1
                kk["dogru"] += d
                if not d:
                    kk["etiket"].append(s.get("etiket"))
        olus = t["olusturma"]
        olus = olus.astimezone(TR) if olus.tzinfo else olus
        test_cikti.append({"id": t["id"], "ders": t["ders"], "hafta": t["hafta"], "tarih": olus.date().isoformat(),
                           "kazanim": t.get("kazanim"), "form_url": t.get("form_url"), "katilim": len(katilanlar),
                           "sms_gonderildi": bool(t.get("sms_gonderim_id")),
                           "ortalama_oran": _oran(t_dogru, t_toplam), "sorular": soru_cikti})
    kazanimlar = [{"ders": d, "kazanim_satiri": s, "soru_sayisi": len(v["sorular"]), "cevap_sayisi": v["cevap"],
                   "dogru_orani": _oran(v["dogru"], v["cevap"]),
                   "zorlanilan": bool(v["cevap"]) and _oran(v["dogru"], v["cevap"]) < esikler["zorlanilan_esik"]}
                  for (d, s), v in kaz_ist.items()]
    kazanimlar.sort(key=lambda x: (not x["zorlanilan"], x["dogru_orani"], x["ders"], x["kazanim_satiri"]))
    ogrenciler = []
    for no in sorted(ogr):
        o = ogr[no]
        kl = []
        for (d, s), v in sorted(o["kaz"].items()):
            oran = _oran(v["dogru"], v["soru"])
            kl.append({"ders": d, "kazanim_satiri": s, "soru": v["soru"], "dogru": v["dogru"], "oran": oran,
                       "durum": _durum(oran, v["soru"], esikler), "sayfalar": sayfalari_birlestir(v["etiket"])})
        ogrenciler.append({"okul_no": no, "test_sayisi": len(o["testler"]), "dogru": o["dogru"],
                           "toplam": o["toplam"], "oran": _oran(o["dogru"], o["toplam"]), "kazanimlar": kl,
                           "eksik_sayisi": sum(1 for x in kl if x["durum"] == "eksik"),
                           "guclu_sayisi": sum(1 for x in kl if x["durum"] == "guclu")})
    return {"sinif": sinif, "uretim": (simdi or datetime.now(TR)).isoformat(timespec="seconds"),
            "aralik": aralik or {"baslangic": None, "bitis": None}, "esikler": esikler,
            "testler": test_cikti, "kazanimlar": kazanimlar, "ogrenciler": ogrenciler}


def _tr_gun(dt: datetime) -> date:
    return (dt.astimezone(TR) if dt.tzinfo else dt).date()


def _testleri_oku(conn, sinif: str, baslangic, bitis) -> tuple[list[dict], dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT id, ders, hafta, olusturma, kazanim, sorular, "
                    "COALESCE(form_kisa_url, form_url) AS form_url, sms_gonderim_id FROM form_testi WHERE sinif=%s "
                    "ORDER BY olusturma, id", (sinif,))
        testler = [t for t in cur.fetchall()
                   if (baslangic is None or _tr_gun(t["olusturma"]) >= baslangic)
                   and (bitis is None or _tr_gun(t["olusturma"]) <= bitis)]
        cevaplar: dict = defaultdict(list)
        if testler:
            cur.execute("SELECT form_testi_id, okul_no, soru_sira, secilen, dogru FROM form_cevap "
                        "WHERE form_testi_id = ANY(%s)", ([t["id"] for t in testler],))
            for r in cur.fetchall():
                cevaplar[r["form_testi_id"]].append((r["okul_no"], r["soru_sira"], r["secilen"], r["dogru"]))
    return testler, cevaplar


def sinif_analizi(conn, sinif: str, baslangic: date | None = None, bitis: date | None = None,
                  esikler: dict | None = None) -> dict:
    testler, cevaplar = _testleri_oku(conn, sinif, baslangic, bitis)
    aralik = {"baslangic": baslangic.isoformat() if baslangic else None, "bitis": bitis.isoformat() if bitis else None}
    return analiz_hesapla(sinif, testler, cevaplar, esikler or dict(VARSAYILAN_ESIKLER), aralik)


def atomik_yaz(yol: Path, veri: dict) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(f".{yol.name}.tmp")
    try:
        gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(gecici, yol)
    finally:
        gecici.unlink(missing_ok=True)


def rapor_yaz(conn, ayar: dict) -> int:
    """Her sınıf için tüm zamanlar raporu; hata sayısını döner."""
    esikler = esikler_oku(ayar)
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT sinif FROM form_testi ORDER BY sinif")
        siniflar = [r[0] for r in cur.fetchall()]
    hata = 0
    for sinif in siniflar:
        try:
            veri = sinif_analizi(conn, sinif, esikler=esikler)
            ad = re.sub(r"[^\w\-]", "_", sinif)
            atomik_yaz(Path(ayar["cikti_dizini"]) / "rapor" / f"{ad}.json", veri)
            log.info("rapor %s: %d test, %d öğrenci", sinif, len(veri["testler"]), len(veri["ogrenciler"]))
        except Exception:
            hata += 1
            log.exception("%s analizi başarısız — sonrakine geçiliyor", sinif)
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                log.debug("rollback başarısız")
    return hata
