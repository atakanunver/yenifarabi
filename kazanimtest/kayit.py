"""kazanimtest/kayit.py — soru_havuzu DB'de form_testi kaydı (sema.sql)."""

import json

import psycopg2.extras


def var_mi(conn, sinif: str, ders: str, hafta: int) -> dict | None:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM form_testi WHERE sinif=%s AND ders=%s AND hafta=%s", (sinif, ders, hafta))
        return cur.fetchone()


def kaydet(conn, sinif, ders, hafta, kazanim, soru_idler, form: dict, xlsx_yol) -> bool:
    """Yeni kayıt eklenirse True; UNIQUE çakışırsa False."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO form_testi (sinif, ders, hafta, kazanim, soru_idler, form_id, form_url, "
            "form_kisa_url, tablo_url, xlsx_yol) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (sinif, ders, hafta) DO NOTHING RETURNING id",
            (
                sinif, ders, hafta, kazanim, json.dumps(soru_idler), form.get("form_id"),
                form.get("form_url"), form.get("form_kisa_url"), form.get("tablo_url"), str(xlsx_yol),
            ),
        )
        eklendi = cur.fetchone() is not None
    conn.commit()
    return eklendi


def kullanim_artir(conn, soru_idler: list[str]) -> None:
    idler = [int(k.split(":")[1]) for k in soru_idler if k.startswith("havuz:")]
    if not idler:
        return
    with conn.cursor() as cur:
        cur.execute("UPDATE soru SET kullanim_sayisi = kullanim_sayisi + 1 WHERE id = ANY(%s)", (idler,))
    conn.commit()


def sms_isaretle(conn, test_idler: list[int], gonderim_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE form_testi SET sms_gonderim_id=%s, durum='sms' WHERE id = ANY(%s)",
            (gonderim_id, test_idler),
        )
    conn.commit()


def son_kayitlar(conn, n: int = 20) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM form_testi ORDER BY id DESC LIMIT %s", (n,))
        return cur.fetchall()
