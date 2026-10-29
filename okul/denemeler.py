"""Harici deneme sonuçları (saf mantık): öğrenciye/veliye gösterim sorguları + toplu yükleme.

Şema `deneme` / `deneme_ogrenci` (db.SEMA_V6). `veri` serbest JSON'dur
({"toplam_net": x, "dersler": {"Türkçe": 19.25}}); sütunlar PDF'e göre değişir.
Başka öğrenciyle karşılaştırma/sıralama burada YOKTUR ve eklenmemelidir.
"""

import json
import sqlite3

import dosyalar
import zaman
from metin import normalize_isim, tr_kucuk


def _coz(satir: sqlite3.Row) -> dict:
    try:
        veri = json.loads(satir["veri"] or "{}")
    except ValueError:
        veri = {}
    if not isinstance(veri, dict):
        veri = {}
    dersler = veri.get("dersler")
    return {
        "id": satir["id"],
        "ad": satir["ad"],
        "tarih": satir["tarih"],
        "ozet": satir["ozet"],
        "toplam_net": veri.get("toplam_net"),
        "siralama": _siralama(veri.get("siralama")),
        "dersler": list(dersler.items()) if isinstance(dersler, dict) else [],
        "analiz": satir["analiz"],
        "tavsiye": satir["tavsiye"],
        "pdf": bool(satir["pdf"]),
        "zayif_kazanimlar": _zayif_kazanimlar(veri.get("kazanimlar")),
    }


def _siralama(sr) -> dict | None:
    """Öğrencinin kendi sırası: {sube, kurum, genel: [sıra, katılan], yuzdelik}; bozuk/eksik veri → None."""
    try:
        return {
            "sube": [int(x) for x in sr["sube"]],
            "kurum": [int(x) for x in sr["kurum"]],
            "genel": [int(x) for x in sr["genel"]],
            "yuzdelik": float(sr["yuzdelik"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _zayif_kazanimlar(kazanimlar) -> list[dict]:
    """Öğrencinin kendi kazanımlarından başarısı %50'nin altında olanlar (en düşük önce)."""
    if not isinstance(kazanimlar, list):
        return []
    zayif = []
    for k in kazanimlar:
        try:
            soru = int(k["d"]) + int(k["y"]) + int(k["b"])
            if soru and int(k["d"]) / soru < 0.5:
                zayif.append({"ders": k["ders"], "kazanim": k["kazanim"], "d": k["d"], "y": k["y"], "b": k["b"]})
        except (KeyError, TypeError, ValueError):
            continue
    zayif.sort(key=lambda k: (k["d"] / (k["d"] + k["y"] + k["b"]), k["ders"], k["kazanim"]))
    return zayif


_SORGU = (
    "SELECT d.id, d.ad, d.tarih, d.ozet, o.veri, o.analiz, o.tavsiye,"
    " EXISTS (SELECT 1 FROM deneme_pdf p WHERE p.deneme_id = d.id AND p.okul_no = o.okul_no) AS pdf"
    " FROM deneme d JOIN deneme_ogrenci o ON o.deneme_id = d.id"
    " WHERE d.yayinda = 1 AND o.girdi = 1 AND o.okul_no = ?"
)


def ogrenci_denemeleri(conn: sqlite3.Connection, okul_no: int) -> list[dict]:
    """Yalnızca bu okul_no'nun, yayındaki denemeleri (yeniden eskiye)."""
    satirlar = conn.execute(
        _SORGU + " ORDER BY COALESCE(d.tarih, '') DESC, d.id DESC", (okul_no,)
    ).fetchall()
    return [_coz(s) for s in satirlar]


def ogrenci_denemesi(
    conn: sqlite3.Connection, okul_no: int, deneme_id: int
) -> dict | None:
    s = conn.execute(_SORGU + " AND d.id = ?", (okul_no, deneme_id)).fetchone()
    return _coz(s) if s else None


def deneme_sayisi(conn: sqlite3.Connection, okul_no: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM deneme d JOIN deneme_ogrenci o ON o.deneme_id = d.id"
        " WHERE d.yayinda = 1 AND o.girdi = 1 AND o.okul_no = ?",
        (okul_no,),
    ).fetchone()[0]


def _norm_sinif(s) -> str:
    return "".join(tr_kucuk(str(s or "")).split())


def yukle(
    conn: sqlite3.Connection, belge: dict, kuru: bool = False, yayinla: bool = False
) -> dict:
    """Deneme JSON'unu okul.db'ye uygular. Aynı `ad` tekrar yüklenirse güncellenir; hiçbir şey silinmez.

    okul_no ile öğrenci bulunur; ad_soyad (normalize) ya da sınıf uyuşmazsa satır UYGULANMAZ.
    Dönüş: sayılar + uyuşmayan/eşleşmeyen okul_no listeleri (ad/telefon içermez).
    """
    ad = str(belge.get("ad") or "").strip()
    if not ad:
        raise ValueError("'ad' zorunlu")
    sonuc = {
        "ad": ad,
        "eslesen": 0,
        "eslesmeyen": 0,
        "uyusmayan": 0,
        "eslesmeyen_no": [],
        "uyusmayan_no": [],
    }
    uygulanacak = []
    for s in belge.get("ogrenciler") or []:
        try:
            no = int(s.get("okul_no"))
        except (TypeError, ValueError):
            sonuc["eslesmeyen"] += 1
            continue
        o = conn.execute(
            "SELECT ad_soyad, sinif FROM ogrenci WHERE okul_no = ?", (no,)
        ).fetchone()
        if o is None:
            sonuc["eslesmeyen"] += 1
            sonuc["eslesmeyen_no"].append(no)
        elif normalize_isim(str(s.get("ad_soyad") or "")) != normalize_isim(
            o["ad_soyad"]
        ) or _norm_sinif(s.get("sinif")) != _norm_sinif(o["sinif"]):
            sonuc["uyusmayan"] += 1
            sonuc["uyusmayan_no"].append(no)
        else:
            sonuc["eslesen"] += 1
            uygulanacak.append((no, s))
    if kuru:
        return sonuc

    simdi = zaman.simdi_str()
    veri_alani = belge.get("tarih")
    with conn:
        mevcut = conn.execute("SELECT id FROM deneme WHERE ad = ?", (ad,)).fetchone()
        if mevcut:
            did = mevcut["id"]
            conn.execute(
                "UPDATE deneme SET tarih = ?, ozet = ? WHERE id = ?",
                (veri_alani, str(belge.get("ozet") or ""), did),
            )
            if yayinla:
                conn.execute("UPDATE deneme SET yayinda = 1 WHERE id = ?", (did,))
        else:
            did = conn.execute(
                "INSERT INTO deneme (ad, tarih, ozet, yayinda, olusturma)"
                " VALUES (?, ?, ?, ?, ?)",
                (ad, veri_alani, str(belge.get("ozet") or ""), int(yayinla), simdi),
            ).lastrowid
        for no, s in uygulanacak:
            conn.execute(
                "INSERT INTO deneme_ogrenci (deneme_id, okul_no, girdi, veri, analiz, tavsiye)"
                " VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(deneme_id, okul_no) DO UPDATE SET girdi = excluded.girdi,"
                " veri = excluded.veri, analiz = excluded.analiz, tavsiye = excluded.tavsiye",
                (
                    did,
                    no,
                    0 if s.get("girdi") in (0, False) else 1,
                    json.dumps(s.get("veri") or {}, ensure_ascii=False),
                    str(s.get("analiz") or ""),
                    str(s.get("tavsiye") or ""),
                ),
            )
            if s.get("pdf_yol"):
                _pdf_yukle(conn, did, no, str(s["pdf_yol"]))
    return sonuc


def _pdf_yukle(conn: sqlite3.Connection, deneme_id: int, okul_no: int, yol: str) -> None:
    """Öğrencinin PDF sayfasını depoya alır; varsa eski dosya silinir (her yüklemede rastgele yeni ad)."""
    eski = pdf_dosyasi(conn, deneme_id, okul_no)
    with open(yol, "rb") as f:
        yeni = dosyalar.deneme_pdf_kaydet(f.read())
    pdf_bagla(conn, deneme_id, okul_no, yeni.depo_adi)
    dosyalar.sil("deneme", eski)


MIN_GRUP = 5  # bundan az katılımcılı grubun ortalaması/ortak eksikleri gizlenir (kimlik sızmasın)
EKSIK_ESIK = 0.5  # kazanım başarısı bunun altındaysa "ortak eksik"
EKSIK_AZAMI = 8


def _veri(satir) -> dict:
    try:
        v = json.loads(satir["veri"] or "{}")
    except ValueError:
        return {}
    return v if isinstance(v, dict) else {}


def _ogrenciler(conn, deneme_id: int, sinif: str | None, yalniz_yayinda: bool) -> list[dict]:
    sorgu = (
        "SELECT g.okul_no, g.ad_soyad, g.sinif, o.veri"
        " FROM deneme_ogrenci o JOIN deneme d ON d.id = o.deneme_id"
        " JOIN ogrenci g ON g.okul_no = o.okul_no"
        " WHERE o.deneme_id = ? AND o.girdi = 1"
    )
    ar: list = [deneme_id]
    if yalniz_yayinda:
        sorgu += " AND d.yayinda = 1"
    if sinif is not None:
        sorgu += " AND g.sinif = ?"
        ar.append(sinif)
    sonuc = []
    for s in conn.execute(sorgu, ar):
        v = _veri(s)
        sonuc.append(
            {
                "okul_no": s["okul_no"],
                "ad": s["ad_soyad"],
                "sinif": s["sinif"],
                "net": v.get("toplam_net"),
                "dersler": v.get("dersler") if isinstance(v.get("dersler"), dict) else {},
                "kazanimlar": v.get("kazanimlar") if isinstance(v.get("kazanimlar"), list) else [],
            }
        )
    return sorted(sonuc, key=lambda x: tr_kucuk(x["ad"]))  # ada göre; başarıya göre SIRALAMA YOK


def _ortalama(degerler: list) -> float | None:
    degerler = [d for d in degerler if isinstance(d, (int, float))]
    return round(sum(degerler) / len(degerler), 2) if degerler else None


def _ders_ortalamalari(ogr: list[dict]) -> dict:
    toplam: dict[str, list] = {}
    for o in ogr:
        for ders, net in o["dersler"].items():
            toplam.setdefault(ders, []).append(net)
    return {d: _ortalama(v) for d, v in toplam.items()}


def _ortak_eksikler(ogr: list[dict]) -> list[dict]:
    """Kazanım başına grup toplamı; başarısı EKSIK_ESIK altındakiler, en düşük başarı önce."""
    toplam: dict[tuple, dict] = {}
    for o in ogr:
        for k in o["kazanimlar"]:
            try:
                t = toplam.setdefault(
                    (k["ders"], k["kazanim"]),
                    {"ders": k["ders"], "kazanim": k["kazanim"], "d": 0, "y": 0, "b": 0},
                )
                t["d"] += int(k["d"])
                t["y"] += int(k["y"])
                t["b"] += int(k["b"])
            except (KeyError, TypeError, ValueError):
                continue
    eksik = []
    for t in toplam.values():
        soru = t["d"] + t["y"] + t["b"]
        if soru >= 3 and t["d"] / soru < EKSIK_ESIK:
            eksik.append({**t, "basari": round(t["d"] / soru * 100)})
    eksik.sort(key=lambda t: (t["basari"], t["ders"], t["kazanim"]))
    return eksik[:EKSIK_AZAMI]


def sinif_ozeti(
    conn: sqlite3.Connection, deneme_id: int, sinif: str, yalniz_yayinda: bool = True
) -> dict | None:
    """Tek şubenin özeti. Katılım < MIN_GRUP ise ortalama ve ortak eksikler gizli; öğrenci listesi (ada göre) kalır."""
    ogr = _ogrenciler(conn, deneme_id, sinif, yalniz_yayinda)
    if not ogr:
        return None
    yeterli = len(ogr) >= MIN_GRUP
    return {
        "sinif": sinif,
        "katilim": len(ogr),
        "ortalama_net": _ortalama([o["net"] for o in ogr]) if yeterli else None,
        "ders_ortalamalari": _ders_ortalamalari(ogr) if yeterli else None,
        "ortak_eksikler": _ortak_eksikler(ogr) if yeterli else [],
        "ogrenciler": [
            {"okul_no": o["okul_no"], "ad": o["ad"], "net": o["net"]} for o in ogr
        ],
    }


def okul_ozeti(
    conn: sqlite3.Connection, deneme_id: int, yalniz_yayinda: bool = True
) -> dict | None:
    ogr = _ogrenciler(conn, deneme_id, None, yalniz_yayinda)
    if not ogr:
        return None
    yeterli = len(ogr) >= MIN_GRUP
    subeler = {}
    for o in ogr:
        subeler.setdefault(o["sinif"], []).append(o)
    return {
        "katilim": len(ogr),
        "ortalama_net": _ortalama([o["net"] for o in ogr]) if yeterli else None,
        "ders_ortalamalari": _ders_ortalamalari(ogr) if yeterli else None,
        "ortak_eksikler": _ortak_eksikler(ogr) if yeterli else [],
        "subeler": [
            {
                "sinif": s,
                "katilim": len(v),
                "ortalama_net": _ortalama([o["net"] for o in v]) if len(v) >= MIN_GRUP else None,
            }
            for s, v in sorted(subeler.items())  # şube adına göre; başarıya göre SIRALAMA YOK
        ],
    }


def pdf_bagla(conn: sqlite3.Connection, deneme_id: int, okul_no: int, dosya: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO deneme_pdf (deneme_id, okul_no, dosya) VALUES (?, ?, ?)"
            " ON CONFLICT(deneme_id, okul_no) DO UPDATE SET dosya = excluded.dosya",
            (deneme_id, okul_no, dosya),
        )


def pdf_dosyasi(conn: sqlite3.Connection, deneme_id: int, okul_no: int) -> str | None:
    s = conn.execute(
        "SELECT dosya FROM deneme_pdf WHERE deneme_id = ? AND okul_no = ?", (deneme_id, okul_no)
    ).fetchone()
    return s["dosya"] if s else None


def yorum_yaz(conn: sqlite3.Connection, deneme_id: int, sinif: str, yorum: str) -> None:
    """sinif='' okul geneli yorumudur."""
    with conn:
        conn.execute(
            "INSERT INTO deneme_sinif_yorum (deneme_id, sinif, yorum) VALUES (?, ?, ?)"
            " ON CONFLICT(deneme_id, sinif) DO UPDATE SET yorum = excluded.yorum",
            (deneme_id, sinif, yorum),
        )


def yorum_oku(conn: sqlite3.Connection, deneme_id: int, sinif: str) -> str:
    s = conn.execute(
        "SELECT yorum FROM deneme_sinif_yorum WHERE deneme_id = ? AND sinif = ?",
        (deneme_id, sinif),
    ).fetchone()
    return s["yorum"] if s else ""


def denemeler_listesi(
    conn: sqlite3.Connection, siniflar: list[str] | None, yalniz_yayinda: bool
) -> list[dict]:
    """Öğretmen/yönetici listesi: her deneme için (yetkili) şubeler ve katılım. siniflar=None -> tüm şubeler."""
    sorgu = (
        "SELECT d.id, d.ad, d.tarih, g.sinif, COUNT(*) AS n"
        " FROM deneme d JOIN deneme_ogrenci o ON o.deneme_id = d.id AND o.girdi = 1"
        " JOIN ogrenci g ON g.okul_no = o.okul_no WHERE 1 = 1"
    )
    ar: list = []
    if yalniz_yayinda:
        sorgu += " AND d.yayinda = 1"
    if siniflar is not None:
        if not siniflar:
            return []
        sorgu += f" AND g.sinif IN ({','.join('?' * len(siniflar))})"
        ar += siniflar
    sorgu += " GROUP BY d.id, g.sinif ORDER BY COALESCE(d.tarih, '') DESC, d.id DESC, g.sinif"
    sonuc: dict[int, dict] = {}
    for r in conn.execute(sorgu, ar):
        d = sonuc.setdefault(
            r["id"], {"id": r["id"], "ad": r["ad"], "tarih": r["tarih"], "siniflar": []}
        )
        d["siniflar"].append({"sinif": r["sinif"], "katilim": r["n"]})
    return list(sonuc.values())
