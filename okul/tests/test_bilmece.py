"""Günün Bilmecesi: 08:00 kapısı, günde tek cevap, aynı gün doğru/yanlış sızmaz, ertesi gün açıklama + XP, havuz, yetki, göç."""

import json
import sqlite3
from datetime import datetime

import auth
import bilmece
import db
import pytest
from fastapi.testclient import TestClient
from scripts import geri_al


def _istemci():
    from app import app

    return TestClient(app)


def _oturum(c, conn, kid):
    c.cookies.set(auth.COOKIE_ADI, auth.oturum_ac(conn, kid))


def _csrf(c, yol):
    return c.get(yol).text.split('name="csrf" value="')[1].split('"')[0]


def _havuz(conn, n=2):
    return [bilmece.ekle(conn, f"Soru {i}?", ["Bir", "İki", "Üç"], i % 3, f"Açıklama {i}") for i in range(n)]


def _xp(conn, kid):
    return conn.execute("SELECT COALESCE(SUM(miktar), 0) FROM bilgi_xp WHERE kullanici_id = ? AND kaynak = 'bilmece'", (kid,)).fetchone()[0]


def test_saat_8den_once_kapali(conn, saat):
    _havuz(conn)
    saat["an"] = datetime(2026, 10, 12, 7, 59, 59)  # noqa: DTZ001
    assert bilmece.bugunku(conn) is None
    with pytest.raises(bilmece.BilmeceHatasi):
        bilmece.cevapla(conn, 1, 0)
    saat["an"] = datetime(2026, 10, 12, 8, 0, 0)  # noqa: DTZ001
    assert bilmece.bugunku(conn)["soru"] == "Soru 0?"


def test_gun_boyu_sabit_ve_dogru_sik_gitmez(conn, saat):
    _havuz(conn, 3)
    b1 = bilmece.bugunku(conn)
    bilmece.ekle(conn, "Sonradan eklenen?", ["a", "b"], 0)
    saat["an"] = datetime(2026, 10, 12, 23, 0, 0)  # noqa: DTZ001
    b2 = bilmece.bugunku(conn)
    assert b1["id"] == b2["id"]
    assert "dogru" not in b1 and "aciklama" not in b1


def test_sira_hic_sorulmamis_once_sonra_en_eski(conn, saat):
    _havuz(conn, 2)
    sorulan = []
    for gun in (12, 13, 14, 15):
        saat["an"] = datetime(2026, 10, gun, 9, 0, 0)  # noqa: DTZ001
        sorulan.append(bilmece.bugunku(conn)["soru"])
    assert sorulan == ["Soru 0?", "Soru 1?", "Soru 0?", "Soru 1?"]


def test_pasif_ve_bos_havuz(conn, saat):
    assert bilmece.bugunku(conn) is None
    (bid,) = _havuz(conn, 1)
    bilmece.aktif_ayarla(conn, bid, False)
    assert bilmece.bugunku(conn) is None


def test_tek_cevap_ve_ertesi_gun_xp(conn, ornek, saat):
    _havuz(conn, 2)  # Soru 0'ın doğrusu 0
    kid, kid2 = ornek["ogr1_k"], ornek["ogr2_k"]
    bilmece.cevapla(conn, kid, 0)
    with pytest.raises(bilmece.BilmeceHatasi) as e:
        bilmece.cevapla(conn, kid, 1)
    assert e.value.kod == 409
    bilmece.cevapla(conn, kid2, 2)
    o = conn.execute("SELECT * FROM ogrenci WHERE kullanici_id = ?", (kid,)).fetchone()
    assert bilmece.odulleri_ver(conn, kid, o["sinif"]) == 0  # aynı gün ödül yok (cevap sızmasın)
    saat["an"] = datetime(2026, 10, 13, 6, 0, 0)  # ertesi gün, yeni bilmece açılmadan  # noqa: DTZ001
    k = bilmece.kart(conn, o)
    assert k["bugun"] is None and not k["acik"]
    assert k["onceki"]["dogru"] == 0 and k["onceki"]["secim"] == 0
    assert (k["onceki"]["cevaplayan"], k["onceki"]["dogru_sayisi"]) == (2, 1)
    assert k["yeni_xp"] == bilmece.XP == _xp(conn, kid)
    assert bilmece.kart(conn, o)["yeni_xp"] == 0 and _xp(conn, kid) == bilmece.XP  # tekrar yazılmaz
    assert bilmece.odulleri_ver(conn, kid2, "9-B") == 0 and _xp(conn, kid2) == 0  # yanlış cevap


def test_12_sinif_cozer_ama_xp_almaz(conn, ornek, saat):
    _havuz(conn, 1)
    conn.execute("UPDATE ogrenci SET sinif = '12-A' WHERE kullanici_id = ?", (ornek["ogr1_k"],))
    conn.commit()
    bilmece.cevapla(conn, ornek["ogr1_k"], 0)
    saat["an"] = datetime(2026, 10, 13, 9, 0, 0)  # noqa: DTZ001
    o = conn.execute("SELECT * FROM ogrenci WHERE kullanici_id = ?", (ornek["ogr1_k"],)).fetchone()
    k = bilmece.kart(conn, o)
    assert k["onceki"]["secim"] == 0 and k["yeni_xp"] == 0 and k["xp"] == 0


def test_dogrulama():
    for soru, sec, d in [("", ["a", "b"], 0), ("S?", ["a"], 0), ("S?", ["a", "a"], 0), ("S?", ["a", "b"], 2), ("S?", list("abcde"), 0)]:
        with pytest.raises(bilmece.BilmeceHatasi):
            bilmece.dogrula(soru, sec, d, "")


def test_ogrenci_sayfasi_ayni_gun_dogruyu_sizdirmaz(conn, ornek, saat):
    bilmece.ekle(conn, "Başkent neresi?", ["İstanbul", "Ankara"], 1, "GİZLİ-AÇIKLAMA")
    with _istemci() as c:
        _oturum(c, conn, ornek["ogr1_k"])
        ana = c.get("/ogrenci").text
        assert "Başkent neresi?" in ana and "GİZLİ-AÇIKLAMA" not in ana
        r = c.post("/ogrenci/bilmece", data={"csrf": _csrf(c, "/ogrenci/bilmece"), "secim": "0"}, follow_redirects=False)
        assert r.status_code == 303
        s = c.get("/ogrenci/bilmece").text
        assert "Cevabın kaydedildi" in s and "GİZLİ-AÇIKLAMA" not in s and "Doğru bildin" not in s and "olmadı" not in s
        assert c.post("/ogrenci/bilmece", data={"csrf": _csrf(c, "/ogrenci/bilmece"), "secim": "1"}).status_code == 409
        saat["an"] = datetime(2026, 10, 13, 7, 0, 0)  # noqa: DTZ001
        s = c.get("/ogrenci/bilmece").text
        assert "GİZLİ-AÇIKLAMA" in s and "olmadı" in s and "08:00" in s
    assert [tuple(r) for r in conn.execute("SELECT secim FROM bilmece_cevap")] == [(0,)]


def test_csrf_ve_roller(conn, ornek, saat):
    _havuz(conn, 1)
    with _istemci() as c:
        _oturum(c, conn, ornek["ogr1_k"])
        assert c.post("/ogrenci/bilmece", data={"csrf": "yanlis", "secim": "0"}).status_code == 400
        assert c.get("/yonetici/bilmeceler").status_code == 404
    for rol in ("ogretmen", "veli1", "yonetici"):
        with _istemci() as c:
            _oturum(c, conn, ornek[rol])
            assert c.get("/ogrenci/bilmece").status_code == 404
    assert conn.execute("SELECT COUNT(*) FROM bilmece_cevap").fetchone()[0] == 0


def test_yonetici_ekler_ve_pasiflestirir(conn, ornek, saat):
    with _istemci() as c:
        _oturum(c, conn, ornek["yonetici"])
        csrf = _csrf(c, "/yonetici/bilmeceler")
        r = c.post("/yonetici/bilmeceler", data={"csrf": csrf, "soru": "Yeni?", "secenek": ["", "X", "Y", ""], "dogru": "2", "aciklama": ""},
                   follow_redirects=False)
        assert r.status_code == 303
        b = conn.execute("SELECT * FROM bilmece").fetchone()
        assert json.loads(b["secenekler"]) == ["X", "Y"] and b["dogru"] == 1  # boş kutular atlanır, doğru sıra kayar
        assert c.post("/yonetici/bilmeceler", data={"csrf": csrf, "soru": "Eksik?", "secenek": ["X", "", "", ""], "dogru": "0"}).status_code == 400
        assert c.post(f"/yonetici/bilmeceler/{b['id']}/aktif", data={"csrf": csrf, "aktif": "0"}, follow_redirects=False).status_code == 303
        assert c.post("/yonetici/bilmeceler/999/aktif", data={"csrf": csrf, "aktif": "0"}).status_code == 404
        assert "Yeni?" in c.get("/yonetici/bilmeceler").text
    assert conn.execute("SELECT aktif FROM bilmece").fetchone()[0] == 0


def test_tohum_dosyasi_gecerli():
    from pathlib import Path

    liste = json.loads((Path(__file__).resolve().parent.parent / "config" / "bilmeceler.json").read_text(encoding="utf-8"))
    assert len(liste) >= 30
    assert len({b["soru"] for b in liste}) == len(liste)
    for b in liste:
        bilmece.dogrula(b["soru"], b["secenekler"], b["dogru"], b.get("aciklama", ""))


def test_gocte_xp_korunur_ve_geri_alinir(tmp_path):
    yol = tmp_path / "eski.db"
    c = sqlite3.connect(yol)
    for i, g in enumerate(db.GOCLER[:34]):
        c.executescript(f"BEGIN;\n{g}\nPRAGMA user_version = {i + 1};\nCOMMIT;")
    c.execute("INSERT INTO kullanici (id, rol, ad_soyad, olusturma) VALUES (1, 'ogrenci', 'A', 'x')")
    c.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (1, 'gayret', 'r', 3, 'g', 'z')")
    c.commit()
    c.executescript(f"BEGIN;\n{db.SEMA_V35}\nPRAGMA user_version = 35;\nCOMMIT;")
    assert c.execute("SELECT kaynak, miktar FROM bilgi_xp").fetchall() == [("gayret", 3)]
    c.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (1, 'bilmece', 'g', 10, 'g', 'z')")
    c.commit()
    c.close()
    assert geri_al.geri_al(yol, 34, onayla=True) == 0
    c = sqlite3.connect(yol)
    assert c.execute("SELECT kaynak FROM bilgi_xp").fetchall() == [("gayret",)]
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name = 'bilmece'").fetchone() is None
    c.close()
