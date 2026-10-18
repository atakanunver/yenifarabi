"""Şekil/grafik atıflı soru karantinası (2026-10-18)."""
import json

import pytest

from soruhavuzu import calistir, sekil, vt
from soruhavuzu.tests.conftest import ORNEK_SORU


@pytest.mark.parametrize(
    "soru",
    [
        "Şekildeki cismin ivmesi kaçtır?",
        "Verilen grafiğe göre hız kaç m/s'dir?",
        "Aşağıdaki tabloda hangi element yer alır?",
        "Haritada gösterilen bölge neresidir?",
    ],
)
def test_atif_yakalanir(soru):
    assert sekil.sekil_atfi(soru)


@pytest.mark.parametrize(
    "soru",
    [
        "Bir şekilde çözüm bulunamaz mı?",
        "Periyodik tabloda 17. grup elementleri nelerdir?",
        "Kare şeklindeki bir zeminin alanı 64 ise kenarı kaçtır?",
        "Grafik tasarım hangi alanın konusudur?",
        "log2(8) kaçtır?",
    ],
)
def test_normal_kullanim_atif_degil(soru):
    assert not sekil.sekil_atfi(soru)


def test_sik_icindeki_atif_da_yakalanir():
    assert sekil.sekil_atfi("Hangisi doğrudur?", ["Şekildeki ok", "b", "c", "d"])


def test_tara_kuru_yazmaz_uygula_askiya_alir_geri_al(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(calistir, "VERI", tmp_path)
    bid = vt.birim_ekle(conn, "kitap", "k:1", "fizik", 10, "E", "m")
    a = vt.soru_ekle(conn, bid, {**ORNEK_SORU, "sinif": 10, "soru": "Şekildeki cismin ivmesi nedir?"})
    b = vt.soru_ekle(conn, bid, {**ORNEK_SORU, "sinif": 10, "soru": "Newton'un ikinci yasası nedir?"})
    with conn.cursor() as cur:
        cur.execute("UPDATE soru SET durum='onayli'")
    conn.commit()

    r = calistir.sekil_tara(conn)
    assert [x["id"] for x in r["bulunan"]] == [a] and r["dosya"] is None
    with conn.cursor() as cur:
        cur.execute("SELECT durum FROM soru WHERE id=%s", (a,))
        assert cur.fetchone()[0] == "onayli"

    r = calistir.sekil_tara(conn, uygula=True)
    with conn.cursor() as cur:
        cur.execute("SELECT id, durum FROM soru ORDER BY id")
        assert cur.fetchall() == [(a, "askida"), (b, "onayli")]
    assert json.loads(open(r["dosya"], encoding="utf-8").read())[0]["onceki"] == "onayli"
    assert calistir.sekil_tara(conn, uygula=True)["bulunan"] == []  # idempotent

    assert calistir.sekil_geri_al(conn, r["dosya"]) == 1
    with conn.cursor() as cur:
        cur.execute("SELECT durum FROM soru WHERE id=%s", (a,))
        assert cur.fetchone()[0] == "onayli"
