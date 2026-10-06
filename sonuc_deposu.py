"""sonuc_deposu.py - Biten oyunların sonuçlarını yerel SQLite'a (veri/sonuclar.db) yazar/özetler.

Öğrenci verisi bu makineden dışarı çıkmaz; dosya .gitignore'dadır. Zaman damgası sunucudan
(Europe/Istanbul) alınır, istemciye güvenilmez. Aynı oyun (kimlik) tekrar gönderilirse güncellenir
(podyum/zafer penceresi birden çok açılabilir).
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
OYUN_TURLERI = {"sinif_arena", "hexafetih", "duello"}
MAX_KATILIMCI = 40
MAX_UYE = 60


def db_yolu() -> Path:
    return Path(os.environ.get("ARENA_VERI_DIZINI") or (BASE_DIR / "veri")) / "sonuclar.db"


def _baglan() -> sqlite3.Connection:
    yol = db_yolu()
    yol.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(yol, timeout=5)
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS oyun (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kimlik TEXT UNIQUE,
            oyun TEXT NOT NULL,
            tarih TEXT NOT NULL,
            sinif TEXT NOT NULL DEFAULT '',
            ders TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS katilimci (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            oyun_id INTEGER NOT NULL REFERENCES oyun(id) ON DELETE CASCADE,
            tur TEXT NOT NULL,            -- 'takim' | 'ogrenci'
            ad TEXT NOT NULL,
            puan INTEGER NOT NULL DEFAULT 0,
            kazanan INTEGER NOT NULL DEFAULT 0,
            uyeler TEXT NOT NULL DEFAULT '[]'
        );
        CREATE INDEX IF NOT EXISTS ix_oyun_tarih ON oyun(tarih);
        CREATE INDEX IF NOT EXISTS ix_katilimci_oyun ON katilimci(oyun_id);
        """
    )
    c.execute("PRAGMA foreign_keys = ON")
    return c


def _kisalt(s, n=80) -> str:
    return str(s or "").strip()[:n]


def kaydet(oyun: str, sinif: str, ders: str, katilimcilar: list[dict], kimlik: str = "", simdi: datetime | None = None) -> int:
    """Sonucu yazar; oyun satırının id'sini döner. Geçersiz oyun türü ValueError."""
    if oyun not in OYUN_TURLERI:
        raise ValueError("geçersiz oyun türü")
    simdi = simdi or datetime.now(ISTANBUL_TZ)
    kimlik = _kisalt(kimlik, 64) or None
    satirlar = []
    for k in (katilimcilar or [])[:MAX_KATILIMCI]:
        ad = _kisalt(k.get("ad"))
        if not ad:
            continue
        tur = "ogrenci" if k.get("tur") == "ogrenci" else "takim"
        try:
            puan = max(-100000, min(100000, int(k.get("puan", 0))))
        except (TypeError, ValueError):
            puan = 0
        uyeler = [_kisalt(u) for u in (k.get("uyeler") or [])[:MAX_UYE] if _kisalt(u)]
        satirlar.append((tur, ad, puan, 1 if k.get("kazanan") else 0, json.dumps(uyeler, ensure_ascii=False)))
    c = _baglan()
    try:
        with c:
            oyun_id = None
            if kimlik:
                eski = c.execute("SELECT id FROM oyun WHERE kimlik = ?", (kimlik,)).fetchone()
                if eski:
                    oyun_id = eski["id"]
                    c.execute("DELETE FROM katilimci WHERE oyun_id = ?", (oyun_id,))
                    c.execute("UPDATE oyun SET oyun=?, sinif=?, ders=?, tarih=? WHERE id=?",
                              (oyun, _kisalt(sinif, 20), _kisalt(ders, 80), simdi.isoformat(timespec="seconds"), oyun_id))
            if oyun_id is None:
                cur = c.execute("INSERT INTO oyun (kimlik, oyun, tarih, sinif, ders) VALUES (?,?,?,?,?)",
                                (kimlik, oyun, simdi.isoformat(timespec="seconds"), _kisalt(sinif, 20), _kisalt(ders, 80)))
                oyun_id = cur.lastrowid
            c.executemany(
                "INSERT INTO katilimci (oyun_id, tur, ad, puan, kazanan, uyeler) VALUES (?,?,?,?,?,?)",
                [(oyun_id, *s) for s in satirlar],
            )
        return oyun_id
    finally:
        c.close()


def ozet(sinif: str | None = None, gun: int = 7, simdi: datetime | None = None) -> dict:
    """Son `gun` günün sınıf bazlı özeti."""
    simdi = simdi or datetime.now(ISTANBUL_TZ)
    gun = max(1, min(int(gun), 365))
    esik = (simdi - timedelta(days=gun)).isoformat(timespec="seconds")
    pazartesi = (simdi - timedelta(days=simdi.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    c = _baglan()
    try:
        sorgu = "SELECT * FROM oyun WHERE tarih >= ?"
        p: list = [esik]
        if sinif:
            sorgu += " AND sinif = ?"
            p.append(sinif)
        oyunlar = c.execute(sorgu + " ORDER BY tarih DESC", p).fetchall()
        siniflar: dict[str, dict] = {}
        for o in oyunlar:
            s = siniflar.setdefault(o["sinif"] or "-", {
                "sinif": o["sinif"] or "-", "oyun_sayisi": 0, "bu_hafta": 0,
                "oyun_turleri": {}, "_takim": {}, "_ogr": {}, "_katilan": set(), "son_oyunlar": [],
            })
            s["oyun_sayisi"] += 1
            if o["tarih"] >= pazartesi.isoformat(timespec="seconds"):
                s["bu_hafta"] += 1
            s["oyun_turleri"][o["oyun"]] = s["oyun_turleri"].get(o["oyun"], 0) + 1
            kat = c.execute("SELECT * FROM katilimci WHERE oyun_id = ? ORDER BY puan DESC", (o["id"],)).fetchall()
            for k in kat:
                hedef = s["_ogr"] if k["tur"] == "ogrenci" else s["_takim"]
                a = hedef.setdefault(k["ad"], {"ad": k["ad"], "puan": 0, "oyun": 0, "galibiyet": 0})
                a["puan"] += k["puan"]
                a["oyun"] += 1
                a["galibiyet"] += k["kazanan"]
                if k["tur"] == "ogrenci":
                    s["_katilan"].add(k["ad"])
                for u in json.loads(k["uyeler"] or "[]"):
                    s["_katilan"].add(u)
            if len(s["son_oyunlar"]) < 8:
                s["son_oyunlar"].append({
                    "tarih": o["tarih"], "oyun": o["oyun"], "ders": o["ders"],
                    "katilimcilar": [{"ad": k["ad"], "puan": k["puan"], "kazanan": bool(k["kazanan"])} for k in kat],
                })
        cikti = []
        for s in siniflar.values():
            s["en_iyi_takimlar"] = sorted(s.pop("_takim").values(), key=lambda a: (-a["puan"], a["ad"]))[:5]
            s["en_iyi_ogrenciler"] = sorted(s.pop("_ogr").values(), key=lambda a: (-a["puan"], a["ad"]))[:5]
            s["katilan_ogrenci_sayisi"] = len(s.pop("_katilan"))
            cikti.append(s)
        cikti.sort(key=lambda s: s["sinif"])
        return {"gun": gun, "olusturma": simdi.isoformat(timespec="seconds"), "siniflar": cikti}
    finally:
        c.close()
