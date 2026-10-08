"""soruhavuzu/vt.py — soru_havuzu PostgreSQL erişimi (farabi-api ile aynı bağlantı deseni;
şifre ~/.pgpass'tan gelir)."""

import json
from pathlib import Path

import psycopg2
import psycopg2.extras

SEMA = Path(__file__).with_name("sema.sql")


def baglan(dbname: str = "soru_havuzu"):
    return psycopg2.connect(host="127.0.0.1", dbname=dbname, user="farabi")


def sema_kur(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SEMA.read_text(encoding="utf-8"))
    conn.commit()


def birim_ekle(conn, tur, anahtar, ders, sinif, etiket, metin) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO kaynak_birim (tur, anahtar, ders, sinif, etiket, metin) "
            "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (anahtar) DO NOTHING RETURNING id",
            (tur, anahtar, ders, sinif, etiket, metin),
        )
        satir = cur.fetchone()
    conn.commit()
    return satir[0] if satir else None


def siradaki_birim(conn, sinif: int | None = None) -> dict | None:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if sinif is not None:
            cur.execute(
                "SELECT * FROM kaynak_birim WHERE durum = 'bekliyor' AND sinif = %s ORDER BY id LIMIT 1",
                (sinif,),
            )
        else:
            cur.execute(
                "SELECT * FROM kaynak_birim WHERE durum = 'bekliyor' ORDER BY id LIMIT 1"
            )
        return cur.fetchone()


def birim_isaretle(conn, birim_id, durum, hata=None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE kaynak_birim SET durum=%s, hata=%s, islendi_at=now() WHERE id=%s",
            (durum, hata, birim_id),
        )
    conn.commit()


def soru_ekle(conn, birim_id, s: dict) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO soru (birim_id, ders, sinif, konu, soru, kisa_cevap, secenekler, "
            "dogru_index, zorluk, kaynak) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (
                birim_id,
                s["ders"],
                s["sinif"],
                s["konu"],
                s["soru"],
                s["kisa_cevap"],
                json.dumps(s["secenekler"], ensure_ascii=False),
                s["dogru_index"],
                s["zorluk"],
                s["kaynak"],
            ),
        )
        sid = cur.fetchone()[0]
    conn.commit()
    return sid


# En az onaylı sorusu olan (sınıf, ders) önce; eşitlikte yüksek sınıf önce.
DENETLENECEK_SQL = (
    "SELECT s.*, b.metin AS birim_metin FROM soru s JOIN kaynak_birim b ON b.id = s.birim_id "
    "LEFT JOIN (SELECT ders, sinif, count(*) AS n FROM soru WHERE durum = 'onayli' "
    "GROUP BY ders, sinif) o ON o.ders = s.ders AND o.sinif = s.sinif "
    "WHERE s.durum = 'uretildi' "
    "ORDER BY COALESCE(o.n, 0), s.sinif DESC, s.ders, s.birim_id, s.id LIMIT %s"
)


def denetlenecekler(conn, limit: int) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            DENETLENECEK_SQL,
            (limit,),
        )
        return list(cur.fetchall())


def denetim_yaz(conn, soru_id, durum, not_) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE soru SET durum=%s, denetim_notu=%s, denetim_at=now() WHERE id=%s",
            (durum, not_, soru_id),
        )
    conn.commit()


def kazanim_upsert(conn, k: dict) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO kazanim (sinif, ders, hafta, kod, metin) VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT (sinif, ders, hafta, metin) DO UPDATE SET kod = EXCLUDED.kod RETURNING id",
            (k["sinif"], k["ders"], k["hafta"], k["kod"], k["metin"]),
        )
        kid = cur.fetchone()[0]
    conn.commit()
    return kid
