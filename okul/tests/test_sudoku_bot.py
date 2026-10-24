"""Sudoku botla antrenman: bot süresi, tek açık oyun, günlük sınır, skor/sonuç, günde 1 puan, yetki (404), sızıntı, geri alma."""

import random
import re
import sqlite3
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import auth
import db
import sudoku
import sudoku_bot


def _ogrenci(conn, yeni_kullanici, ad, no, sinif="9-A"):
    kid = yeni_kullanici(conn, "ogrenci", ad, str(no), sifre=f"s{no}")
    conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (?, ?, ?, ?)", (no, ad, sinif, kid))
    conn.commit()
    return kid


@pytest.fixture
def istemci():
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def cozum(conn, oyun_id):
    return conn.execute("SELECT cozum FROM sudoku_bot WHERE id = ?", (oyun_id,)).fetchone()[0]


def sabitle(conn, oyun_id, bot_sure, bot_hata=0):
    conn.execute("UPDATE sudoku_bot SET bot_sure_sn = ?, bot_hata = ? WHERE id = ?", (bot_sure, bot_hata, oyun_id))
    conn.commit()


def bitir(conn, kid, zorluk, saniye, saat, bot_sure):
    """Oyun açar, botu sabitler, saniye geçirip doğru çözümü gönderir; (id, sonuç) döner."""
    oid = sudoku_bot.baslat(conn, kid, zorluk)
    sabitle(conn, oid, bot_sure)
    saat["an"] += timedelta(seconds=saniye)
    return oid, sudoku_bot.gonder(conn, oid, kid, cozum(conn, oid))


def test_bot_hedefi_gecmis_yoksa_taban_civari_ve_deterministik(conn, ornek):
    kid = ornek["ogr1_k"]
    s1 = sudoku_bot.bot_hedefi(conn, kid, "orta", random.Random(7))
    assert s1 == sudoku_bot.bot_hedefi(conn, kid, "orta", random.Random(7))
    t = sudoku_bot.TABAN_SN["orta"]
    assert t * 0.85 - 1 <= s1[0] <= t * 1.15 + 1 and s1[1] in (0, 1, 2)


def test_bot_hedefi_gecmise_uyar_ve_sinirlanir(conn, ornek, saat):
    kid = ornek["ogr1_k"]
    for _ in range(3):  # 3 bitmiş oyun: hepsi ~200 sn
        bitir(conn, kid, "basit", 200, saat, bot_sure=9999)
        saat["an"] += timedelta(hours=4)  # terk eşiğini aş, bir sonraki oyun açılabilsin
    sure, _ = sudoku_bot.bot_hedefi(conn, kid, "basit", random.Random(1))
    assert 200 * 0.85 - 1 <= sure <= 200 * 1.15 + 1
    # çok hızlı geçmiş en az süreye kelepçelenir
    conn.execute("UPDATE sudoku_bot SET sure_sn = 5")
    conn.commit()
    assert sudoku_bot.bot_hedefi(conn, kid, "basit", random.Random(1))[0] == sudoku_bot.EN_AZ_SN["basit"]


def test_baslat_acik_oyunu_dondurur_bot_suresi_degismez(conn, ornek, saat):
    kid = ornek["ogr1_k"]
    a = sudoku_bot.baslat(conn, kid, "basit")
    ilk = conn.execute("SELECT bot_sure_sn, bot_hata, bulmaca FROM sudoku_bot WHERE id = ?", (a,)).fetchone()
    assert sudoku_bot.baslat(conn, kid, "zor") == a  # açık oyun varken yenisi açılmaz
    assert conn.execute("SELECT COUNT(*) FROM sudoku_bot").fetchone()[0] == 1
    assert tuple(conn.execute("SELECT bot_sure_sn, bot_hata, bulmaca FROM sudoku_bot WHERE id = ?", (a,)).fetchone()) == tuple(ilk)
    saat["an"] += timedelta(hours=sudoku_bot.TERK_SAAT, minutes=1)  # terk edilmiş sayılır
    assert sudoku_bot.baslat(conn, kid, "basit") != a


def test_gecersiz_zorluk_ve_gunluk_sinir(conn, ornek, saat):
    kid = ornek["ogr1_k"]
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku_bot.baslat(conn, kid, "imkansiz")
    for _ in range(sudoku_bot.GUNLUK_BASLAT_EN_COK):
        oid = sudoku_bot.baslat(conn, kid, "basit")
        sudoku_bot.gonder(conn, oid, kid, cozum(conn, oid))
    with pytest.raises(sudoku.SudokuHatasi, match="Günde en çok"):
        sudoku_bot.baslat(conn, kid, "basit")
    saat["an"] += timedelta(days=1)
    sudoku_bot.baslat(conn, kid, "basit")  # ertesi gün yeniden hak


def test_gonder_kurallari(conn, ornek, saat):
    kid = ornek["ogr1_k"]
    oid = sudoku_bot.baslat(conn, kid, "basit")
    z = cozum(conn, oid)
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku_bot.gonder(conn, oid, kid, "0" + z[1:])  # eksik tahta hata sayılmaz
    yanlis = ("1" if z[0] != "1" else "2") + z[1:]
    assert sudoku_bot.gonder(conn, oid, kid, yanlis) == {"dogru": False, "hata": 1}
    sabitle(conn, oid, 1000)
    saat["an"] += timedelta(seconds=60)
    s = sudoku_bot.gonder(conn, oid, kid, z)
    assert s["dogru"] and s["sure_sn"] == 60 and s["skor"] == 70 and s["bot_skor"] == 1000 and s["sonuc"] == "galibiyet"
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku_bot.gonder(conn, oid, kid, z)  # ikinci kez bitirilemez
    assert sudoku_bot.getir(conn, oid, ornek["ogr2_k"]) is None  # başkası göremez


@pytest.mark.parametrize(("bot_sure", "beklenen"), [(100, "maglubiyet"), (60, "beraberlik"), (30, "galibiyet")])
def test_sonuc_skor_karsilastirmasi(conn, ornek, saat, bot_sure, beklenen):
    # oyuncu 60 sn + 0 hata = 60; bot skoru bot_sure'dan büyükse oyuncu kazanır (düşük skor kazanır)
    kid = ornek["ogr1_k"]
    oid = sudoku_bot.baslat(conn, kid, "basit")
    sabitle(conn, oid, {"galibiyet": 90, "beraberlik": 60, "maglubiyet": 30}[beklenen])
    saat["an"] += timedelta(seconds=60)
    assert sudoku_bot.gonder(conn, oid, kid, cozum(conn, oid))["sonuc"] == beklenen


def test_gunde_yalniz_ilk_galibiyet_puan_yazar(conn, ornek, saat):
    kid = ornek["ogr1_k"]
    hb = "2026-10-12"  # saat fixture'ı 12 Ekim 2026 Pazartesi
    o1, s1 = bitir(conn, kid, "orta", 30, saat, bot_sure=500)
    assert s1["sonuc"] == "galibiyet"
    o2, s2 = bitir(conn, kid, "basit", 30, saat, bot_sure=500)
    assert s2["sonuc"] == "galibiyet"
    assert sudoku_bot.kazanc(conn, conn.execute("SELECT * FROM sudoku_bot WHERE id = ?", (o1,)).fetchone()) == 3 * 2  # orta ×2
    assert sudoku_bot.kazanc(conn, conn.execute("SELECT * FROM sudoku_bot WHERE id = ?", (o2,)).fetchone()) == 0
    v = sudoku._puanlar(conn, hb)[kid]
    assert v["puan"] == 6 and v["galibiyet"] == 1 and v["oynanan"] == 1
    # ertesi gün yeni galibiyet yine puan yazar; liderlikte görünür
    saat["an"] += timedelta(days=1)
    bitir(conn, kid, "basit", 30, saat, bot_sure=500)
    assert sudoku._puanlar(conn, hb)[kid]["puan"] == 6 + 3
    satir = next(x for x in sudoku.liderlik(conn, "9-A", hb) if x["kid"] == kid)
    assert satir["puan"] == 9


def test_maglubiyet_ve_beraberlik_puan_yazmaz_ve_hafta_siniri(conn, ornek, saat):
    kid = ornek["ogr1_k"]
    bitir(conn, kid, "basit", 120, saat, bot_sure=20)  # kaybeder
    assert sudoku._puanlar(conn, "2026-10-12").get(kid) is None
    saat["an"] += timedelta(days=8)  # sonraki haftaya geç
    bitir(conn, kid, "basit", 30, saat, bot_sure=500)  # kazanır
    assert sudoku._puanlar(conn, "2026-10-12").get(kid) is None  # eski hafta etkilenmez
    assert sudoku._puanlar(conn, "2026-10-19")[kid]["puan"] == 3


def test_rota_akisi_ve_sizinti(istemci, conn, ornek, saat):
    csrf = giris(istemci, "101", "ali-sifre")
    assert istemci.get("/ogrenci/sudoku").status_code == 200
    r = istemci.post("/ogrenci/sudoku/bot", data={"csrf": csrf, "zorluk": "basit"}, follow_redirects=False)
    assert r.status_code == 303
    oid = conn.execute("SELECT id FROM sudoku_bot").fetchone()[0]
    assert r.headers["location"] == f"/ogrenci/sudoku/bot/{oid}"
    z = cozum(conn, oid)
    sayfa = istemci.get(f"/ogrenci/sudoku/bot/{oid}")
    assert sayfa.status_code == 200 and z not in sayfa.text
    bot = conn.execute("SELECT bot_sure_sn FROM sudoku_bot WHERE id = ?", (oid,)).fetchone()[0]
    assert f"Bot: {bot}" not in sayfa.text and istemci.get(f"/ogrenci/sudoku/bot/{oid}/sonuc", follow_redirects=False).status_code == 303
    js = {"Accept": "application/json"}
    sabitle(conn, oid, 500)
    saat["an"] += timedelta(seconds=20)
    r = istemci.post(f"/ogrenci/sudoku/bot/{oid}/gonder", data={"csrf": csrf, "tahta": ("1" if z[0] != "1" else "2") + z[1:]}, headers=js)
    assert r.json() == {"dogru": False, "hata": 1, "sonraki": f"/ogrenci/sudoku/bot/{oid}"} and z not in r.text
    r = istemci.post(f"/ogrenci/sudoku/bot/{oid}/gonder", data={"csrf": csrf, "tahta": z}, headers=js)
    assert r.json()["dogru"] and r.json()["skor"] == 30 and "bot_skor" not in r.json() and "sonuc" not in r.json()
    son = istemci.get(f"/ogrenci/sudoku/bot/{oid}/sonuc")
    assert son.status_code == 200 and "Botu yendin" in son.text and "+3 puan" in son.text and z not in son.text
    assert istemci.get("/ogrenci/sudoku/liderlik").status_code == 200


def test_rota_yetkisiz_404_ve_csrf(istemci, conn, yeni_kullanici, ornek, saat):
    baskasi = _ogrenci(conn, yeni_kullanici, "Efe Demir", 103)
    oid = sudoku_bot.baslat(conn, baskasi, "basit")
    csrf = giris(istemci, "101", "ali-sifre")
    for yol in (f"/ogrenci/sudoku/bot/{oid}", f"/ogrenci/sudoku/bot/{oid}/sonuc"):
        assert istemci.get(yol).status_code == 404
    assert istemci.post(f"/ogrenci/sudoku/bot/{oid}/gonder", data={"csrf": csrf, "tahta": "1" * 81}, follow_redirects=False).status_code == 404
    giris(istemci, "hoca", "hoca-sifre")
    assert istemci.get(f"/ogrenci/sudoku/bot/{oid}").status_code == 404
    giris(istemci, "101", "ali-sifre")
    assert istemci.post("/ogrenci/sudoku/bot", data={"zorluk": "basit"}, follow_redirects=False).status_code in (400, 403)


def test_geri_al_30(tmp_path):
    from scripts import geri_al

    assert 30 in geri_al.GERI and len(db.GOCLER) >= 30
    c = sqlite3.connect(tmp_path / "t.db")
    c.executescript("\n".join(db.GOCLER))
    assert c.execute("SELECT name FROM sqlite_master WHERE name = 'sudoku_bot'").fetchone()
    c.executescript(geri_al.GERI[30])
    assert not c.execute("SELECT name FROM sqlite_master WHERE name = 'sudoku_bot'").fetchone()


def test_kaydet_yalniz_bos_hucreler_ve_sabit_ipuclari_degismez(conn, ornek):
    kid = ornek["ogr1_k"]
    oid = sudoku_bot.baslat(conn, kid, "basit")
    bulmaca = conn.execute("SELECT bulmaca FROM sudoku_bot WHERE id = ?", (oid,)).fetchone()[0]
    bos = [i for i, c in enumerate(bulmaca) if c == "0"][:2]
    sabit = bulmaca.index(next(c for c in bulmaca if c != "0"))
    tahta = ["9"] * 81  # sabit hücrelere de 9 yazmayı dene
    sudoku_bot.kaydet(conn, oid, kid, "".join(tahta))
    kayitli = conn.execute("SELECT tahta FROM sudoku_bot WHERE id = ?", (oid,)).fetchone()[0]
    assert kayitli[sabit] == "0" and all(kayitli[i] == "9" for i in bos)  # sabit hücre kaydedilmez, boşlar kaydedilir


def test_kaydet_dogrulama_sahiplik_ve_bitince_kapanir(conn, ornek):
    kid, baskasi = ornek["ogr1_k"], ornek["ogr2_k"]
    oid = sudoku_bot.baslat(conn, kid, "basit")
    for kotu in ("", "1" * 80, "1" * 82, "a" * 81, "١" * 81):
        with pytest.raises(sudoku.SudokuHatasi):
            sudoku_bot.kaydet(conn, oid, kid, kotu)
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku_bot.kaydet(conn, oid, baskasi, "0" * 81)  # başkasının oyunu
    sudoku_bot.gonder(conn, oid, kid, cozum(conn, oid))
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku_bot.kaydet(conn, oid, kid, "0" * 81)  # bitmiş oyuna kayıt yok


def test_rota_kaydet_ve_sayfa_kayitli_rakamlarla_gelir(istemci, conn, yeni_kullanici, ornek, saat):
    csrf = giris(istemci, "101", "ali-sifre")
    istemci.post("/ogrenci/sudoku/bot", data={"csrf": csrf, "zorluk": "basit"}, follow_redirects=False)
    oid = conn.execute("SELECT id FROM sudoku_bot").fetchone()[0]
    bulmaca, z = conn.execute("SELECT bulmaca, cozum FROM sudoku_bot WHERE id = ?", (oid,)).fetchone()
    bos = [i for i, c in enumerate(bulmaca) if c == "0"]
    tahta = ["0"] * 81
    tahta[bos[0]], tahta[bos[1]] = "4", "7"
    r = istemci.post(f"/ogrenci/sudoku/bot/{oid}/kaydet", data={"csrf": csrf, "tahta": "".join(tahta)}, headers={"Accept": "application/json"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    # çıkıp giriş: sayfa kayıtlı rakamlarla gelir, çözüm sayfada yok
    giris(istemci, "101", "ali-sifre")
    sayfa = istemci.get(f"/ogrenci/sudoku/bot/{oid}")
    assert sayfa.status_code == 200 and z not in sayfa.text and f'data-kaydet="/ogrenci/sudoku/bot/{oid}/kaydet"' in sayfa.text
    degerler = re.findall(r'name="h"[^>]*value="(\d?)"', sayfa.text)
    assert len(degerler) == 81 and degerler[bos[0]] == "4" and degerler[bos[1]] == "7" and degerler[bos[2]] == ""
    # geçersiz tahta 400; başkası 404; csrf yok reddedilir
    csrf = giris(istemci, "101", "ali-sifre")
    assert istemci.post(f"/ogrenci/sudoku/bot/{oid}/kaydet", data={"csrf": csrf, "tahta": "x"}).status_code == 400
    assert istemci.post(f"/ogrenci/sudoku/bot/{oid}/kaydet", data={"tahta": "0" * 81}, follow_redirects=False).status_code in (400, 403)
    baska = _ogrenci(conn, yeni_kullanici, "Efe Demir", 103)
    csrf_b = giris(istemci, "103", "s103")
    assert baska and istemci.post(f"/ogrenci/sudoku/bot/{oid}/kaydet", data={"csrf": csrf_b, "tahta": "0" * 81}).status_code == 404


def test_geri_al_31(tmp_path):
    from scripts import geri_al

    assert 31 in geri_al.GERI and len(db.GOCLER) >= 31
    c = sqlite3.connect(tmp_path / "t.db")
    c.executescript("\n".join(db.GOCLER))
    assert "tahta" in [r[1] for r in c.execute("PRAGMA table_info(sudoku_bot)")]
    c.executescript(geri_al.GERI[31])
    assert "tahta" not in [r[1] for r in c.execute("PRAGMA table_info(sudoku_bot)")]
