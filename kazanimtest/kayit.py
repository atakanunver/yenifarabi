"""kazanimtest/kayit.py — soru_havuzu DB'de form_testi kaydı (sema.sql)."""

import json

import psycopg2.extras


def var_mi(conn, sinif: str, ders: str, hafta: int) -> dict | None:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM form_testi WHERE sinif=%s AND ders=%s AND hafta=%s", (sinif, ders, hafta))
        return cur.fetchone()


def kaydet(conn, sinif, ders, hafta, kazanim, soru_idler, form: dict, xlsx_yol, sorular=None) -> bool:
    """Yeni kayıt eklenirse True; UNIQUE çakışırsa False."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO form_testi (sinif, ders, hafta, kazanim, soru_idler, form_id, form_url, "
            "form_kisa_url, tablo_url, xlsx_yol, sorular) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (sinif, ders, hafta) DO NOTHING RETURNING id",
            (
                sinif, ders, hafta, kazanim, json.dumps(soru_idler), form.get("form_id"),
                form.get("form_url"), form.get("form_kisa_url"), form.get("tablo_url"), str(xlsx_yol),
                json.dumps(sorular, ensure_ascii=False) if sorular is not None else None,
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


def anliksiz_kayitlar(conn) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM form_testi WHERE sorular IS NULL ORDER BY id")
        return cur.fetchall()


def anlik_yaz(conn, test_id: int, sorular: list[dict]) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE form_testi SET sorular=%s WHERE id=%s", (json.dumps(sorular, ensure_ascii=False), test_id))
    conn.commit()


def son_gun_formlari(conn, gun: int) -> list[dict]:
    """Son `gun` günde oluşturulmuş, Google formu olan kayıtlar."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM form_testi WHERE form_id IS NOT NULL "
            "AND olusturma >= now() - make_interval(days => %s) ORDER BY id",
            (gun,),
        )
        return cur.fetchall()


def cevap_yaz(conn, test_id: int, satirlar: list[tuple]) -> int:
    """satirlar: (okul_no, soru_sira, secilen|None, dogru, zaman). İlk yazılan kalır; yeni eklenen satır sayısı döner."""
    yeni = 0
    with conn.cursor() as cur:
        for okul_no, sira, secilen, dogru, zaman in satirlar:
            cur.execute(
                "INSERT INTO form_cevap (form_testi_id, okul_no, soru_sira, secilen, dogru, zaman) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (form_testi_id, okul_no, soru_sira) DO NOTHING",
                (test_id, okul_no, sira, secilen, dogru, zaman),
            )
            yeni += max(cur.rowcount, 0)
    conn.commit()
    return yeni
