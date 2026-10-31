"""sonuc_deposu.py - Biten oyunların sonuçlarını yerel SQLite'a (veri/sonuclar.db) yazar/özetler.

Öğrenci verisi bu makineden dışarı çıkmaz; dosya .gitignore'dadır. Zaman damgası sunucudan
(Europe/Istanbul) alınır, istemciye güvenilmez. Aynı oyun (kimlik) tekrar gönderilirse güncellenir
(podyum/zafer penceresi birden çok açılabilir).
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
OYUN_TURLERI = {"sinif_arena", "hexafetih", "duello"}
MAX_KATILIMCI = 40
MAX_UYE = 60
_JSON_LOCK = threading.Lock()


def db_yolu() -> Path:
    return Path(os.environ.get("ARENA_VERI_DIZINI") or (BASE_DIR / "veri")) / "sonuclar.db"


def json_skor_dosyasi() -> Path:
    return db_yolu().parent / "oyun_skorlari.json"


def json_sinif_skor_dosyasi(sinif: str) -> Path:
    temiz = "".join(c for c in (sinif or "genel") if c.isalnum() or c in "-_")
    return db_yolu().parent / f"skorlar_{temiz}.json"


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

        # JSON Skor Dosyalarına Yaz (Takımlar ve Oyuncular)
        try:
            _json_skor_guncelle(oyun, sinif, ders, katilimcilar, simdi)
        except Exception as e:
            # Hata SQLite kaydını bozmamalı
            pass

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
        siniflar_arasi_veri = siniflar_arasi_skorlar(gun=gun, simdi=simdi)
        return {
            "gun": gun,
            "olusturma": simdi.isoformat(timespec="seconds"),
            "siniflar": cikti,
            "siniflar_arasi": siniflar_arasi_veri,
        }
    finally:
        c.close()


def siniflar_arasi_skorlar(gun: int = 30, simdi: datetime | None = None) -> dict:
    """Sınıflar arası liderlik tablosu: en çok soru cevaplayan sınıf, en başarılı öğrenciler ve oyun kırılımları."""
    simdi = simdi or datetime.now(ISTANBUL_TZ)
    gun = max(1, min(int(gun), 365))
    esik = (simdi - timedelta(days=gun)).isoformat(timespec="seconds")
    c = _baglan()
    try:
        oyunlar = c.execute("SELECT * FROM oyun WHERE tarih >= ? ORDER BY tarih DESC", (esik,)).fetchall()
        sinif_stats: dict[str, dict] = {}
        ogrenci_stats: dict[str, dict] = {}
        takim_stats: dict[str, dict] = {}
        toplam_oyun_sayisi = len(oyunlar)
        toplam_soru_sayisi = 0

        # Düello skor dosyasından güncel serileri çek (eğer varsa)
        duello_seriler: dict[str, int] = {}
        try:
            d_yol = BASE_DIR / "veri" / "duello_skorlar.json"
            if d_yol.exists():
                with open(d_yol, encoding="utf-8") as df:
                    d_veri = json.load(df)
                    for _, s_d in d_veri.get("siniflar", {}).items():
                        for o_ad, o_d in s_d.get("ogrenciler", {}).items():
                            duello_seriler[o_ad] = o_d.get("en_iyi_seri", 0)
        except Exception:
            pass

        for o in oyunlar:
            s_ad = o["sinif"] or "Genel"
            st = sinif_stats.setdefault(s_ad, {
                "sinif": s_ad,
                "toplam_oyun": 0,
                "duello_oyun": 0,
                "arena_oyun": 0,
                "fetih_oyun": 0,
                "toplam_puan": 0,
                "dogru_soru": 0,
                "galibiyet": 0,
                "_ogrenciler": set(),
            })
            st["toplam_oyun"] += 1
            oyun_turu = o["oyun"]
            if oyun_turu == "duello":
                st["duello_oyun"] += 1
            elif oyun_turu == "sinif_arena":
                st["arena_oyun"] += 1
            elif oyun_turu == "hexafetih":
                st["fetih_oyun"] += 1

            kat = c.execute("SELECT * FROM katilimci WHERE oyun_id = ? ORDER BY puan DESC", (o["id"],)).fetchall()
            for k in kat:
                puan = max(0, k["puan"])
                kazanan = 1 if k["kazanan"] else 0
                tur = k["tur"]
                ad = k["ad"]
                st["toplam_puan"] += puan
                st["galibiyet"] += kazanan

                if tur == "ogrenci":
                    q_cnt = max(0, puan // 10)
                    st["dogru_soru"] += q_cnt
                    st["_ogrenciler"].add(ad)
                    toplam_soru_sayisi += q_cnt

                    ogr = ogrenci_stats.setdefault(ad, {
                        "ad": ad,
                        "sinif": s_ad,
                        "toplam_puan": 0,
                        "dogru_soru": 0,
                        "duello_dogru": 0,
                        "takim_dogru": 0,
                        "oyun_sayisi": 0,
                        "duello_oyun": 0,
                        "takim_oyun": 0,
                        "galibiyet": 0,
                        "en_iyi_seri": duello_seriler.get(ad, 0),
                    })
                    ogr["toplam_puan"] += puan
                    ogr["dogru_soru"] += q_cnt
                    ogr["duello_dogru"] += q_cnt
                    ogr["oyun_sayisi"] += 1
                    ogr["duello_oyun"] += 1
                    ogr["galibiyet"] += kazanan
                else:
                    # Takım
                    q_cnt = max(0, puan // 100)
                    st["dogru_soru"] += q_cnt
                    toplam_soru_sayisi += q_cnt

                    t_key = f"{s_ad} · {ad}"
                    t_stat = takim_stats.setdefault(t_key, {
                        "takim": ad,
                        "sinif": s_ad,
                        "toplam_puan": 0,
                        "dogru_soru": 0,
                        "oyun_sayisi": 0,
                        "galibiyet": 0,
                    })
                    t_stat["toplam_puan"] += puan
                    t_stat["dogru_soru"] += q_cnt
                    t_stat["oyun_sayisi"] += 1
                    t_stat["galibiyet"] += kazanan

                    uyeler = json.loads(k["uyeler"] or "[]")
                    for u in uyeler:
                        if not u:
                            continue
                        st["_ogrenciler"].add(u)
                        ogr = ogrenci_stats.setdefault(u, {
                            "ad": u,
                            "sinif": s_ad,
                            "toplam_puan": 0,
                            "dogru_soru": 0,
                            "duello_dogru": 0,
                            "takim_dogru": 0,
                            "oyun_sayisi": 0,
                            "duello_oyun": 0,
                            "takim_oyun": 0,
                            "galibiyet": 0,
                            "en_iyi_seri": duello_seriler.get(u, 0),
                        })
                        ogr["toplam_puan"] += puan
                        ogr["dogru_soru"] += q_cnt
                        ogr["takim_dogru"] += q_cnt
                        ogr["oyun_sayisi"] += 1
                        ogr["takim_oyun"] += 1
                        ogr["galibiyet"] += kazanan

        # Sınıfları dönüştür ve sırala
        sirali_siniflar = []
        for s in sinif_stats.values():
            ogr_kumesi = s.pop("_ogrenciler")
            s["ogrenci_sayisi"] = len(ogr_kumesi)
            # Sınıfın en başarılı öğrencisi
            sinif_ogrencileri = [o for o in ogrenci_stats.values() if o["sinif"] == s["sinif"]]
            sinif_ogrencileri.sort(key=lambda x: (-x["dogru_soru"], -x["toplam_puan"]))
            s["en_iyi_ogrenci"] = sinif_ogrencileri[0]["ad"] if sinif_ogrencileri else "-"
            s["en_iyi_ogrenci_dogru"] = sinif_ogrencileri[0]["dogru_soru"] if sinif_ogrencileri else 0
            sirali_siniflar.append(s)

        sirali_siniflar.sort(key=lambda s: (-s["dogru_soru"], -s["toplam_puan"], -s["toplam_oyun"], s["sinif"]))
        for i, s in enumerate(sirali_siniflar, 1):
            s["sira"] = i

        # Öğrencileri sırala
        tum_ogrenciler = list(ogrenci_stats.values())
        tum_ogrenciler.sort(key=lambda o: (-o["dogru_soru"], -o["toplam_puan"], -o["galibiyet"], o["ad"]))
        for i, o in enumerate(tum_ogrenciler, 1):
            o["sira"] = i

        duello_ogrencileri = [o for o in tum_ogrenciler if o["duello_oyun"] > 0]
        duello_ogrencileri.sort(key=lambda o: (-o["duello_dogru"], -o.get("en_iyi_seri", 0), -o["galibiyet"]))
        for i, o in enumerate(duello_ogrencileri, 1):
            o["duello_sira"] = i

        takim_ogrencileri = [o for o in tum_ogrenciler if o["takim_oyun"] > 0]
        takim_ogrencileri.sort(key=lambda o: (-o.get("takim_dogru", 0), -o["toplam_puan"]))
        for i, o in enumerate(takim_ogrencileri, 1):
            o["takim_sira"] = i

        sirali_takimlar = list(takim_stats.values())
        sirali_takimlar.sort(key=lambda t: (-t["dogru_soru"], -t["toplam_puan"]))
        for i, t in enumerate(sirali_takimlar, 1):
            t["sira"] = i

        return {
            "gun": gun,
            "olusturma": simdi.isoformat(timespec="seconds"),
            "toplam_oyun": toplam_oyun_sayisi,
            "toplam_dogru_soru": toplam_soru_sayisi,
            "sinif_sayisi": len(sirali_siniflar),
            "ogrenci_sayisi": len(tum_ogrenciler),
            "en_cok_soru_cevaplayan_sinif": sirali_siniflar[0] if sirali_siniflar else None,
            "en_cok_soru_bilen_ogrenci": tum_ogrenciler[0] if tum_ogrenciler else None,
            "siniflar": sirali_siniflar,
            "ogrenciler_genel": tum_ogrenciler[:25],
            "ogrenciler_duello": duello_ogrencileri[:20],
            "ogrenciler_takim": takim_ogrencileri[:20],
            "takimlar": sirali_takimlar[:15],
        }
    finally:
        c.close()


def _json_skor_guncelle(oyun: str, sinif: str, ders: str, katilimcilar: list[dict], simdi: datetime) -> None:
    """Oyun sonucunu yerel JSON dosyalarına (takımlar ve oyuncular) kaydeder."""
    sinif_adi = (sinif or "Genel").strip()
    zaman = simdi.isoformat(timespec="seconds")

    with _JSON_LOCK:
        ana_yol = json_skor_dosyasi()
        ana_veri = {
            "guncelleme": zaman,
            "siniflar": {},
            "genel_takimlar": {},
            "genel_ogrenciler": {},
            "son_oyunlar": [],
        }
        if ana_yol.exists():
            try:
                with open(ana_yol, encoding="utf-8") as f:
                    ana_veri = json.load(f)
            except Exception:
                pass

        sinif_haritasi = ana_veri.setdefault("siniflar", {})
        sinif_verisi = sinif_haritasi.setdefault(sinif_adi, {"takimlar": {}, "ogrenciler": {}, "son_oyunlar": []})
        s_takimlar = sinif_verisi.setdefault("takimlar", {})
        s_ogrenciler = sinif_verisi.setdefault("ogrenciler", {})
        s_son_oyunlar = sinif_verisi.setdefault("son_oyunlar", [])

        genel_takimlar = ana_veri.setdefault("genel_takimlar", {})
        genel_ogrenciler = ana_veri.setdefault("genel_ogrenciler", {})
        genel_son_oyunlar = ana_veri.setdefault("son_oyunlar", [])

        oyun_kaydi = {
            "tarih": zaman,
            "oyun": oyun,
            "sinif": sinif_adi,
            "ders": ders or "Genel",
            "katilimcilar": [],
        }

        for k in katilimcilar or []:
            ad = _kisalt(k.get("ad"))
            if not ad:
                continue
            tur = "ogrenci" if k.get("tur") == "ogrenci" else "takim"
            puan = int(k.get("puan", 0))
            kazanan = bool(k.get("kazanan", False))
            uyeler = [_kisalt(u) for u in (k.get("uyeler") or []) if _kisalt(u)]

            oyun_kaydi["katilimcilar"].append({
                "ad": ad,
                "tur": tur,
                "puan": puan,
                "kazanan": kazanan,
                "uyeler": uyeler,
            })

            if tur == "takim":
                # Sınıf Takım Tablosu
                t_stat = s_takimlar.setdefault(
                    ad,
                    {
                        "ad": ad,
                        "sinif": sinif_adi,
                        "toplam_puan": 0,
                        "oyun_sayisi": 0,
                        "galibiyet": 0,
                        "son_oyun": zaman,
                    },
                )
                t_stat["toplam_puan"] += puan
                t_stat["oyun_sayisi"] += 1
                if kazanan:
                    t_stat["galibiyet"] += 1
                t_stat["son_oyun"] = zaman

                # Genel Takım Tablosu
                gt_anahtar = f"{sinif_adi} - {ad}"
                gt_stat = genel_takimlar.setdefault(
                    gt_anahtar,
                    {
                        "takim": ad,
                        "sinif": sinif_adi,
                        "toplam_puan": 0,
                        "oyun_sayisi": 0,
                        "galibiyet": 0,
                        "son_oyun": zaman,
                    },
                )
                gt_stat["toplam_puan"] += puan
                gt_stat["oyun_sayisi"] += 1
                if kazanan:
                    gt_stat["galibiyet"] += 1
                gt_stat["son_oyun"] = zaman

                # Takım Üyeleri
                for u in uyeler:
                    u_stat = s_ogrenciler.setdefault(
                        u,
                        {
                            "ad": u,
                            "sinif": sinif_adi,
                            "toplam_puan": 0,
                            "oyun_sayisi": 0,
                            "galibiyet": 0,
                            "son_oyun": zaman,
                        },
                    )
                    u_stat["toplam_puan"] += puan
                    u_stat["oyun_sayisi"] += 1
                    if kazanan:
                        u_stat["galibiyet"] += 1
                    u_stat["son_oyun"] = zaman

                    gu_stat = genel_ogrenciler.setdefault(
                        u,
                        {
                            "ad": u,
                            "sinif": sinif_adi,
                            "toplam_puan": 0,
                            "oyun_sayisi": 0,
                            "galibiyet": 0,
                            "son_oyun": zaman,
                        },
                    )
                    gu_stat["toplam_puan"] += puan
                    gu_stat["oyun_sayisi"] += 1
                    if kazanan:
                        gu_stat["galibiyet"] += 1
                    gu_stat["son_oyun"] = zaman
            else:
                # Bireysel Öğrenci
                u_stat = s_ogrenciler.setdefault(
                    ad,
                    {
                        "ad": ad,
                        "sinif": sinif_adi,
                        "toplam_puan": 0,
                        "oyun_sayisi": 0,
                        "galibiyet": 0,
                        "son_oyun": zaman,
                    },
                )
                u_stat["toplam_puan"] += puan
                u_stat["oyun_sayisi"] += 1
                if kazanan:
                    u_stat["galibiyet"] += 1
                u_stat["son_oyun"] = zaman

                gu_stat = genel_ogrenciler.setdefault(
                    ad,
                    {
                        "ad": ad,
                        "sinif": sinif_adi,
                        "toplam_puan": 0,
                        "oyun_sayisi": 0,
                        "galibiyet": 0,
                        "son_oyun": zaman,
                    },
                )
                gu_stat["toplam_puan"] += puan
                gu_stat["oyun_sayisi"] += 1
                if kazanan:
                    gu_stat["galibiyet"] += 1
                gu_stat["son_oyun"] = zaman

        # Son Oyunlar
        s_son_oyunlar.insert(0, oyun_kaydi)
        if len(s_son_oyunlar) > 50:
            s_son_oyunlar.pop()

        genel_son_oyunlar.insert(0, oyun_kaydi)
        if len(genel_son_oyunlar) > 50:
            genel_son_oyunlar.pop()

        ana_veri["guncelleme"] = zaman

        # Ana JSON'a yaz
        tmp_ana = ana_yol.with_suffix(".tmp")
        with open(tmp_ana, "w", encoding="utf-8") as f:
            json.dump(ana_veri, f, ensure_ascii=False, indent=2)
        os.replace(tmp_ana, ana_yol)

        # Sınıf JSON'una yaz
        sinif_yol = json_sinif_skor_dosyasi(sinif_adi)
        sinif_cikti = {
            "sinif": sinif_adi,
            "guncelleme": zaman,
            "takim_liderlik": sorted(
                s_takimlar.values(), key=lambda t: (-t["toplam_puan"], -t["galibiyet"], t["ad"])
            ),
            "ogrenci_liderlik": sorted(
                s_ogrenciler.values(), key=lambda o: (-o["toplam_puan"], -o["galibiyet"], o["ad"])
            ),
            "son_oyunlar": s_son_oyunlar[:15],
        }
        for i, t in enumerate(sinif_cikti["takim_liderlik"], 1):
            t["sira"] = i
        for i, o in enumerate(sinif_cikti["ogrenci_liderlik"], 1):
            o["sira"] = i

        tmp_sinif = sinif_yol.with_suffix(".tmp")
        with open(tmp_sinif, "w", encoding="utf-8") as f:
            json.dump(sinif_cikti, f, ensure_ascii=False, indent=2)
        os.replace(tmp_sinif, sinif_yol)


def json_skorlari_getir(sinif: str | None = None) -> dict:
    """Yerel JSON dosyasından takım ve öğrenci puan tablolarını döner."""
    with _JSON_LOCK:
        ana_yol = json_skor_dosyasi()
        if not ana_yol.exists():
            return {"durum": "ok", "sinif": sinif or "Tümü", "takimlar": [], "ogrenciler": [], "son_oyunlar": []}
        try:
            with open(ana_yol, encoding="utf-8") as f:
                ana_veri = json.load(f)
        except Exception:
            return {"durum": "ok", "sinif": sinif or "Tümü", "takimlar": [], "ogrenciler": [], "son_oyunlar": []}

        if sinif and sinif in ana_veri.get("siniflar", {}):
            s_veri = ana_veri["siniflar"][sinif]
            takimlar = sorted(
                s_veri.get("takimlar", {}).values(),
                key=lambda t: (-t.get("toplam_puan", 0), -t.get("galibiyet", 0), t["ad"]),
            )
            ogrenciler = sorted(
                s_veri.get("ogrenciler", {}).values(),
                key=lambda o: (-o.get("toplam_puan", 0), -o.get("galibiyet", 0), o["ad"]),
            )
            for i, t in enumerate(takimlar, 1):
                t["sira"] = i
            for i, o in enumerate(ogrenciler, 1):
                o["sira"] = i
            return {
                "durum": "ok",
                "sinif": sinif,
                "takimlar": takimlar,
                "takim_liderlik": takimlar,
                "ogrenciler": ogrenciler,
                "ogrenci_liderlik": ogrenciler,
                "son_oyunlar": s_veri.get("son_oyunlar", [])[:15],
            }

        takimlar = sorted(
            ana_veri.get("genel_takimlar", {}).values(),
            key=lambda t: (-t.get("toplam_puan", 0), -t.get("galibiyet", 0), t["takim"]),
        )
        ogrenciler = sorted(
            ana_veri.get("genel_ogrenciler", {}).values(),
            key=lambda o: (-o.get("toplam_puan", 0), -o.get("galibiyet", 0), o["ad"]),
        )
        for i, t in enumerate(takimlar, 1):
            t["sira"] = i
        for i, o in enumerate(ogrenciler, 1):
            o["sira"] = i
        return {
            "durum": "ok",
            "sinif": "Tümü",
            "takimlar": takimlar[:30],
            "takim_liderlik": takimlar[:30],
            "ogrenciler": ogrenciler[:50],
            "ogrenci_liderlik": ogrenciler[:50],
            "son_oyunlar": ana_veri.get("son_oyunlar", [])[:15],
        }

