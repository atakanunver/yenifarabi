"""Harici deneme sonuçları (saf mantık): öğrenciye/veliye gösterim sorguları + toplu yükleme.

Şema `deneme` / `deneme_ogrenci` (db.SEMA_V6). `veri` serbest JSON'dur
({"toplam_net": x, "dersler": {"Türkçe": 19.25}}); sütunlar PDF'e göre değişir.
Başka öğrenciyle karşılaştırma/sıralama burada YOKTUR ve eklenmemelidir.
"""

import json
import sqlite3

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
        "dersler": list(dersler.items()) if isinstance(dersler, dict) else [],
        "analiz": satir["analiz"],
        "tavsiye": satir["tavsiye"],
    }


_SORGU = (
    "SELECT d.id, d.ad, d.tarih, d.ozet, o.veri, o.analiz, o.tavsiye"
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
    return sonuc
