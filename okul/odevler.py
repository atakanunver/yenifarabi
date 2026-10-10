"""Ödevler: klasik (yaptım işareti) ve çoktan seçmeli test (tek seferlik, otomatik puan)."""

import json
import sqlite3
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime

import zaman

AZAMI_ELLE_SORU = 20
SIK_SAYISI = 4


class OdevHatasi(ValueError):
    pass


def teslim_normalize(s: str) -> str:
    s = (s or "").strip()
    for bicim, ek in (
        ("%Y-%m-%dT%H:%M", ""),
        ("%Y-%m-%d %H:%M", ""),
        ("%Y-%m-%d", " 23:59"),
    ):
        try:
            dt = datetime.strptime(s, bicim)
        except ValueError:
            continue
        if ek:
            dt = dt.replace(hour=23, minute=59)
        return dt.strftime(zaman.BICIM)
    raise OdevHatasi("Teslim tarihi anlaşılamadı.")


def form_sorulari(form: Mapping[str, str], havuz: list[dict]) -> list[dict]:
    sorular = []
    for i in range(1, AZAMI_ELLE_SORU + 1):
        metin = (form.get(f"soru_{i}") or "").strip()
        if not metin:
            continue
        siklar = [(form.get(f"sik_{i}_{j}") or "").strip() for j in range(SIK_SAYISI)]
        if not all(siklar):
            raise OdevHatasi(f"{i}. sorunun dört şıkkı da doldurulmalı.")
        try:
            dogru = int(form.get(f"dogru_{i}", ""))
        except ValueError:
            raise OdevHatasi(f"{i}. sorunun doğru şıkkı seçilmeli.") from None
        if not 0 <= dogru < SIK_SAYISI:
            raise OdevHatasi(f"{i}. sorunun doğru şıkkı geçersiz.")
        sorular.append(
            {
                "metin": metin,
                "siklar": siklar,
                "dogru": dogru,
                "kazanim": (form.get(f"kazanim_{i}") or "").strip(),
                "kaynak": "elle",
            }
        )
    for h in havuz:
        sorular.append(
            {
                "metin": h["soru"],
                "siklar": list(h["secenekler"]),
                "dogru": int(h["dogru_index"]),
                "kazanim": h.get("konu") or "",
                "kaynak": f"havuz:{h['id']}",
            }
        )
    return sorular


def odev_olustur(
    conn: sqlite3.Connection,
    ogretmen_id: int,
    sinif: str,
    ders: str,
    tur: str,
    baslik: str,
    aciklama: str,
    teslim: str,
    sorular: list[dict],
) -> int:
    if tur not in ("klasik", "test"):
        raise OdevHatasi("Geçersiz ödev türü.")
    if not baslik.strip():
        raise OdevHatasi("Başlık boş olamaz.")
    if tur == "test" and not sorular:
        raise OdevHatasi("Test için en az bir soru ekleyin.")
    cur = conn.execute(
        "INSERT INTO odev (ogretmen_id, sinif, ders, tur, baslik, aciklama, teslim, olusturma)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ogretmen_id,
            sinif,
            ders,
            tur,
            baslik.strip(),
            aciklama.strip(),
            teslim_normalize(teslim),
            zaman.simdi_str(),
        ),
    )
    odev_id = cur.lastrowid
    if tur == "test":
        for sira, s in enumerate(sorular, 1):
            conn.execute(
                "INSERT INTO odev_soru (odev_id, sira, metin, siklar, dogru, kazanim, kaynak)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    odev_id,
                    sira,
                    s["metin"],
                    json.dumps(s["siklar"], ensure_ascii=False),
                    s["dogru"],
                    s["kazanim"],
                    s["kaynak"],
                ),
            )
    conn.commit()
    return odev_id


def odev_getir(conn: sqlite3.Connection, odev_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM odev WHERE id = ?", (odev_id,)).fetchone()


def sorular(conn: sqlite3.Connection, odev_id: int) -> list[dict]:
    return [
        {**dict(r), "siklar": json.loads(r["siklar"])}
        for r in conn.execute(
            "SELECT * FROM odev_soru WHERE odev_id = ? ORDER BY sira", (odev_id,)
        )
    ]


def teslim_getir(
    conn: sqlite3.Connection, odev_id: int, ogrenci_id: int
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM odev_teslim WHERE odev_id = ? AND ogrenci_id = ?",
        (odev_id, ogrenci_id),
    ).fetchone()


def test_puanla(
    sorular: list[dict], cevaplar: Mapping[int, int | None]
) -> tuple[int, int, int]:
    dogru = sum(1 for s in sorular if cevaplar.get(s["id"]) == s["dogru"])
    toplam = len(sorular)
    return dogru, toplam, round(100 * dogru / toplam) if toplam else 0


def test_teslim_et(
    conn: sqlite3.Connection,
    odev: sqlite3.Row,
    ogrenci_id: int,
    cevaplar: Mapping[int, int | None],
) -> int:
    if odev["tur"] != "test":
        raise OdevHatasi("Bu ödev test değil.")
    if teslim_getir(conn, odev["id"], ogrenci_id):
        raise OdevHatasi("Bu testi zaten çözdün.")
    s = sorular(conn, odev["id"])
    _, _, puan = test_puanla(s, cevaplar)
    temiz = {str(x["id"]): cevaplar.get(x["id"]) for x in s}
    conn.execute(
        "INSERT INTO odev_teslim (odev_id, ogrenci_id, durum, puan, cevaplar, zaman) VALUES (?, ?, 'tamam', ?, ?, ?)",
        (odev["id"], ogrenci_id, puan, json.dumps(temiz), zaman.simdi_str()),
    )
    conn.commit()
    return puan


def yapti_isaretle(
    conn: sqlite3.Connection, odev: sqlite3.Row, ogrenci_id: int
) -> None:
    if odev["tur"] != "klasik":
        raise OdevHatasi("Test ödevleri çözülerek teslim edilir.")
    conn.execute(
        "INSERT OR IGNORE INTO odev_teslim (odev_id, ogrenci_id, durum, zaman) VALUES (?, ?, 'yapti', ?)",
        (odev["id"], ogrenci_id, zaman.simdi_str()),
    )
    conn.commit()


def ogrenci_odevleri(
    conn: sqlite3.Connection, ogrenci: sqlite3.Row
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT o.*, t.durum, t.puan, u.ad_soyad AS ogretmen FROM odev o"
        " JOIN kullanici u ON u.id = o.ogretmen_id"
        " LEFT JOIN odev_teslim t ON t.odev_id = o.id AND t.ogrenci_id = ?"
        " WHERE o.sinif = ? ORDER BY (t.durum IS NOT NULL), o.teslim",
        (ogrenci["id"], ogrenci["sinif"]),
    ).fetchall()


def ogretmen_odevleri(conn: sqlite3.Connection, k: sqlite3.Row) -> list[sqlite3.Row]:
    sql = (
        "SELECT o.*, (SELECT count(*) FROM odev_teslim t WHERE t.odev_id = o.id) AS teslim_sayisi,"
        " (SELECT count(*) FROM ogrenci g WHERE g.sinif = o.sinif) AS sinif_mevcudu FROM odev o"
    )
    if k["rol"] == "yonetici":
        return conn.execute(sql + " ORDER BY o.olusturma DESC").fetchall()
    return conn.execute(
        sql + " WHERE o.ogretmen_id = ? ORDER BY o.olusturma DESC", (k["id"],)
    ).fetchall()


def sonuc_tablosu(conn: sqlite3.Connection, odev: sqlite3.Row) -> dict:
    ogrenciler = conn.execute(
        "SELECT g.id, g.okul_no, g.ad_soyad, t.durum, t.puan, t.cevaplar FROM ogrenci g"
        " LEFT JOIN odev_teslim t ON t.ogrenci_id = g.id AND t.odev_id = ?"
        " WHERE g.sinif = ? ORDER BY g.okul_no",
        (odev["id"], odev["sinif"]),
    ).fetchall()
    kazanim: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    if odev["tur"] == "test":
        s = sorular(conn, odev["id"])
        for o in ogrenciler:
            if not o["cevaplar"]:
                continue
            cevap = json.loads(o["cevaplar"])
            for soru in s:
                anahtar = soru["kazanim"] or f"Soru {soru['sira']}"
                kazanim[anahtar][0] += int(cevap.get(str(soru["id"])) == soru["dogru"])
                kazanim[anahtar][1] += 1
    return {
        "ogrenciler": ogrenciler,
        "kazanimlar": [(k, d, n) for k, (d, n) in kazanim.items()],
        "teslim_sayisi": sum(1 for o in ogrenciler if o["durum"]),
    }


def ogrenci_kazanim_satirlari(
    conn: sqlite3.Connection, ogrenci_id: int
) -> list[tuple[str, str, bool]]:
    satirlar = []
    for t in conn.execute(
        "SELECT o.id, o.ders, o.baslik, t.cevaplar FROM odev_teslim t JOIN odev o ON o.id = t.odev_id"
        " WHERE t.ogrenci_id = ? AND o.tur = 'test' AND t.cevaplar IS NOT NULL",
        (ogrenci_id,),
    ):
        cevap = json.loads(t["cevaplar"])
        for s in sorular(conn, t["id"]):
            satirlar.append(
                (
                    t["ders"],
                    s["kazanim"] or t["baslik"],
                    cevap.get(str(s["id"])) == s["dogru"],
                )
            )
    return satirlar
