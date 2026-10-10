import sqlite3

import db
import pytest


def test_sema_kurulur_ve_tekrar_calistirilabilir(conn):
    db.sema_kur()
    tablolar = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "kullanici",
        "ogrenci",
        "veli_ogrenci",
        "ogretmen_gorev",
        "duyuru",
        "odev",
        "odev_soru",
        "odev_teslim",
        "oturum",
        "sms_kod",
        "giris_deneme",
        "erisim_log",
        "aktarim_taslak",
    } <= tablolar
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.GOCLER)


def test_veli_telefonu_benzersiz_ama_ogretmenle_cakisabilir(conn, yeni_kullanici):
    yeni_kullanici(conn, "veli", "Veli A", telefon="05320000000")
    yeni_kullanici(
        conn, "ogretmen", "Öğr A", kullanici_adi="ogra", telefon="05320000000"
    )
    with pytest.raises(sqlite3.IntegrityError):
        yeni_kullanici(conn, "veli", "Veli B", telefon="05320000000")


def test_rol_kisiti(conn, yeni_kullanici):
    with pytest.raises(sqlite3.IntegrityError):
        yeni_kullanici(conn, "mudur", "X", kullanici_adi="x")
