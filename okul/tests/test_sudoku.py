"""Sudoku Düellosu: üretici, yaşam döngüsü, sunucu süresi, puan türetimi, yetki (404), geri alma."""

import sqlite3
import time
from datetime import datetime, timedelta

import auth
import db
import oduller
import pytest
import sudoku
from fastapi.testclient import TestClient


def _ogrenci(conn, yeni_kullanici, ad, no, sinif="9-A"):
    kid = yeni_kullanici(conn, "ogrenci", ad, str(no), sifre=f"s{no}")
    conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (?, ?, ?, ?)", (no, ad, sinif, kid))
    conn.commit()
    return kid


@pytest.fixture
def uc(conn, yeni_kullanici, ornek):
    """ornek: ogr1 (9-A) + ogr2 (9-B); ek: aynı sınıftan ikinci ve üçüncü öğrenci."""
    return {"a": ornek["ogr1_k"], "b": _ogrenci(conn, yeni_kullanici, "Can Yıldız", 102),
            "c": _ogrenci(conn, yeni_kullanici, "Efe Demir", 103), "d": ornek["ogr2_k"]}


@pytest.fixture
def istemci():
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def cozulmus(conn, did):
    return conn.execute("SELECT cozum FROM sudoku_duello WHERE id = ?", (did,)).fetchone()[0]


def duello(conn, a, b, zorluk="basit"):
    did = sudoku.meydan_oku(conn, a, "9-A", b, zorluk)
    sudoku.kabul(conn, did, b)
    return did


def oyna(conn, did, kid, hata=0):
    sudoku.baslat(conn, did, kid)
    z = cozulmus(conn, did)
    yanlis = ("1" if z[0] != "1" else "2") + z[1:]
    for _ in range(hata):
        sudoku.gonder(conn, did, kid, yanlis)
    return sudoku.gonder(conn, did, kid, z)


# --- üretici ---

@pytest.mark.parametrize("zorluk", ["basit", "orta", "zor"])
def test_uretici_tek_cozum_ve_ipucu(zorluk):
    t = time.time()
    for tohum in range(4):
        b, c = sudoku.uret(tohum, zorluk)
        assert 81 - b.count("0") == sudoku.ZORLUK[zorluk]
        assert sudoku._say([int(x) for x in b]) == 1
        assert all(bc in ("0", cc) for bc, cc in zip(b, c))  # ipuçları çözümle tutarlı
        assert sorted(c[:9]) == list("123456789")
    assert time.time() - t < 4
    assert sudoku.uret(7, zorluk) == sudoku.uret(7, zorluk)  # deterministik


def test_gecersiz_zorluk():
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku.uret(1, "cok_zor")


# --- yaşam döngüsü ---

def test_meydan_kurallari(conn, uc, saat):
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku.meydan_oku(conn, uc["a"], "9-A", uc["a"], "basit")  # kendisi
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku.meydan_oku(conn, uc["a"], "9-A", uc["d"], "basit")  # başka sınıf
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku.meydan_oku(conn, uc["a"], "9-A", uc["b"], "yok")
    for _ in range(3):
        sudoku.meydan_oku(conn, uc["a"], "9-A", uc["b"], "basit")
    with pytest.raises(sudoku.SudokuHatasi, match="bekleyen"):
        sudoku.meydan_oku(conn, uc["a"], "9-A", uc["b"], "basit")


def test_gunluk_limit(conn, uc, saat):
    for _ in range(5):
        did = sudoku.meydan_oku(conn, uc["a"], "9-A", uc["b"], "basit")
        sudoku.red(conn, did, uc["b"])
    with pytest.raises(sudoku.SudokuHatasi, match="Günde"):
        sudoku.meydan_oku(conn, uc["a"], "9-A", uc["b"], "basit")
    saat["an"] += timedelta(days=1)
    sudoku.meydan_oku(conn, uc["a"], "9-A", uc["b"], "basit")


def test_yalniz_rakip_kabul_eder(conn, uc, saat):
    did = sudoku.meydan_oku(conn, uc["a"], "9-A", uc["b"], "orta")
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku.kabul(conn, did, uc["a"])
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku.baslat(conn, did, uc["b"])  # kabul öncesi oynanmaz
    sudoku.kabul(conn, did, uc["b"])
    d = conn.execute("SELECT * FROM sudoku_duello WHERE id = ?", (did,)).fetchone()
    assert d["durum"] == "surer" and d["son_tarih"] == "2026-10-13 10:00:00"


def test_yanlis_hata_dogru_bitirir_sure_sunucuda(conn, uc, saat):
    did = duello(conn, uc["a"], uc["b"])
    sudoku.baslat(conn, did, uc["a"])
    saat["an"] += timedelta(seconds=95)
    z = cozulmus(conn, did)
    yanlis = ("1" if z[0] != "1" else "2") + z[1:]
    assert sudoku.gonder(conn, did, uc["a"], yanlis) == {"dogru": False, "hata": 1}
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku.gonder(conn, did, uc["a"], "0" + z[1:])  # eksik tahta hata sayılmaz
    s = sudoku.gonder(conn, did, uc["a"], z)
    assert s["dogru"] and s["sure_sn"] == 95 and s["skor"] == 105
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku.gonder(conn, did, uc["a"], z)  # ikinci kez bitirilemez
    # tekrar açış saati sıfırlamaz
    sudoku.baslat(conn, did, uc["b"])
    saat["an"] += timedelta(seconds=10)
    assert sudoku.gecen_sn(sudoku.baslat(conn, did, uc["b"])) == 10


def test_sonuc_ve_puan(conn, uc, saat):
    did = duello(conn, uc["a"], uc["b"], "zor")
    sudoku.baslat(conn, did, uc["a"])
    sudoku.baslat(conn, did, uc["b"])
    saat["an"] += timedelta(seconds=60)
    z = cozulmus(conn, did)
    sudoku.gonder(conn, did, uc["a"], z)
    saat["an"] += timedelta(seconds=30)
    sudoku.gonder(conn, did, uc["b"], z)
    d = conn.execute("SELECT * FROM sudoku_duello WHERE id = ?", (did,)).fetchone()
    assert d["durum"] == "bitti"
    assert sudoku.sonuc(conn, d)["kuran"] == "galibiyet"
    hb = oduller.hafta_basi()
    t = {x["kid"]: x for x in sudoku.liderlik(conn, "9-A", hb)}
    assert t[uc["a"]]["puan"] == 9 and t[uc["a"]]["sira"] == 1  # 3 × zor çarpanı 3
    assert t[uc["b"]]["puan"] == 0 and t[uc["b"]]["sira"] == 2 and t[uc["c"]]["sira"] == 2  # eşit sıra
    assert t[uc["b"]]["oynanan"] == 1 and t[uc["c"]]["oynanan"] == 0


def test_beraberlik(conn, uc, saat):
    did = duello(conn, uc["a"], uc["b"], "orta")
    for k in (uc["a"], uc["b"]):
        sudoku.baslat(conn, did, k)
    saat["an"] += timedelta(seconds=40)
    z = cozulmus(conn, did)
    sudoku.gonder(conn, did, uc["a"], z)
    sudoku.gonder(conn, did, uc["b"], z)
    p = {x["kid"]: x["puan"] for x in sudoku.liderlik(conn, "9-A", oduller.hafta_basi())}
    assert p[uc["a"]] == p[uc["b"]] == 2  # 1 × orta çarpanı 2


def test_rakip_baslamazsa_puan_yok(conn, uc, saat):
    did = duello(conn, uc["a"], uc["b"])
    oyna(conn, did, uc["a"])  # yalnızca kuran bitirir
    saat["an"] += timedelta(hours=25)
    assert sudoku.getir(conn, did, uc["a"])["durum"] == "doldu"
    assert all(x["puan"] == 0 for x in sudoku.liderlik(conn, "9-A", oduller.hafta_basi(saat["an"] - timedelta(hours=25))))


def test_baslayip_bitirmeyen_kaybeder(conn, uc, saat):
    did = duello(conn, uc["a"], uc["b"])
    sudoku.baslat(conn, did, uc["b"])
    oyna(conn, did, uc["a"])
    saat["an"] += timedelta(hours=25)
    sudoku.kapat_sureleri(conn)
    d = conn.execute("SELECT * FROM sudoku_duello WHERE id = ?", (did,)).fetchone()
    assert d["durum"] == "bitti" and sudoku.sonuc(conn, d)["kuran"] == "galibiyet"
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku.gonder(conn, did, uc["b"], cozulmus(conn, did))  # süre dolmuş


def test_bekleyen_meydan_okuma_dolar(conn, uc, saat):
    did = sudoku.meydan_oku(conn, uc["a"], "9-A", uc["b"], "basit")
    saat["an"] += timedelta(hours=25)
    assert sudoku.getir(conn, did, uc["b"])["durum"] == "doldu"


def test_ayni_cift_gunluk_puan_siniri(conn, uc, saat):
    for _ in range(3):
        did = duello(conn, uc["a"], uc["b"])
        oyna(conn, did, uc["a"])
        saat["an"] += timedelta(seconds=5)
        oyna(conn, did, uc["b"], hata=1)
    t = {x["kid"]: x for x in sudoku.liderlik(conn, "9-A", oduller.hafta_basi())}
    assert t[uc["a"]]["oynanan"] == 2 and t[uc["a"]]["puan"] == 6  # 3. düello sayılmaz


def test_hafta_siniri_ve_sinif_ozeti(conn, uc, saat):
    did = duello(conn, uc["a"], uc["b"])
    oyna(conn, did, uc["a"])
    oyna(conn, did, uc["b"], hata=1)
    ozet = {s["sinif"]: s for s in sudoku.sinif_ozetleri(conn, oduller.hafta_basi())}
    assert ozet["9-A"]["katilan"] == 2 and ozet["9-A"]["mevcut"] == 3 and ozet["9-A"]["oran"] == 67
    assert ozet["9-A"]["ort_puan"] == 1.5 and ozet["9-B"]["katilan"] == 0
    gelecek = (datetime(2026, 10, 12) + timedelta(days=7)).strftime("%Y-%m-%d")  # noqa: DTZ001
    assert all(x["puan"] == 0 for x in sudoku.liderlik(conn, "9-A", gelecek))


# --- rotalar ---

def test_rota_akisi_ve_sizinti(istemci, conn, uc, saat):
    csrf = giris(istemci, "101", "ali-sifre")
    r = istemci.post("/ogrenci/sudoku/meydan-oku", data={"csrf": csrf, "rakip": uc["b"], "zorluk": "basit"}, follow_redirects=False)
    assert r.status_code == 303
    did = conn.execute("SELECT id FROM sudoku_duello").fetchone()[0]
    z = cozulmus(conn, did)
    assert istemci.get("/ogrenci/sudoku").status_code == 200
    # rakip kabul eder
    csrf_b = giris(istemci, "102", "s102")
    assert istemci.post(f"/ogrenci/sudoku/{did}/kabul", data={"csrf": csrf_b}, follow_redirects=False).status_code == 303
    sayfa = istemci.get(f"/ogrenci/sudoku/{did}")
    assert sayfa.status_code == 200 and z not in sayfa.text  # çözüm sayfada yok
    saat["an"] += timedelta(seconds=20)
    js = {"Accept": "application/json"}
    r = istemci.post(f"/ogrenci/sudoku/{did}/gonder", data={"csrf": csrf_b, "tahta": ("1" if z[0] != "1" else "2") + z[1:]}, headers=js)
    assert r.json()["dogru"] is False and z not in r.text
    r = istemci.post(f"/ogrenci/sudoku/{did}/gonder", data={"csrf": csrf_b, "tahta": z}, headers=js)
    assert r.json()["dogru"] and r.json()["skor"] == 30
    assert istemci.get(f"/ogrenci/sudoku/{did}/sonuc").status_code == 200
    assert istemci.get("/ogrenci/sudoku/liderlik").status_code == 200


def test_rota_yetkisiz_404(istemci, conn, uc, ornek, saat):
    did = duello(conn, uc["a"], uc["b"])
    csrf = giris(istemci, "103", "s103")  # aynı sınıf ama katılımcı değil
    for yol in (f"/ogrenci/sudoku/{did}", f"/ogrenci/sudoku/{did}/sonuc"):
        assert istemci.get(yol).status_code == 404
    for yol in ("kabul", "red", "gonder"):
        assert istemci.post(f"/ogrenci/sudoku/{did}/{yol}", data={"csrf": csrf, "tahta": "1" * 81}, follow_redirects=False).status_code == 404
    # başka sınıfa meydan okuma: iş kuralı hatası, düello oluşmaz
    csrf_a = giris(istemci, "101", "ali-sifre")
    istemci.post("/ogrenci/sudoku/meydan-oku", data={"csrf": csrf_a, "rakip": uc["d"], "zorluk": "basit"}, follow_redirects=False)
    assert conn.execute("SELECT COUNT(*) FROM sudoku_duello").fetchone()[0] == 1
    # öğretmen erişemez
    giris(istemci, "hoca", "hoca-sifre")
    assert istemci.get("/ogrenci/sudoku").status_code == 404
    # csrf yok
    giris(istemci, "101", "ali-sifre")
    assert istemci.post("/ogrenci/sudoku/meydan-oku", data={"rakip": uc["b"], "zorluk": "basit"}, follow_redirects=False).status_code in (400, 403)


def test_geri_al_18(tmp_path):
    from scripts import geri_al

    assert 18 in geri_al.GERI and len(db.GOCLER) >= 18
    conn = sqlite3.connect(":memory:")
    conn.executescript(db.GOCLER[17])
    conn.executescript(geri_al.GERI[18])
    assert not conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'sudoku%'").fetchall()


# --- düello: otomatik kayıt (şema V32) ---

def test_kaydet_yalniz_bos_hucreler_katilimci_ve_acik_oyun(conn, uc, saat):
    did = duello(conn, uc["a"], uc["b"])
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku.kaydet(conn, did, uc["a"], "0" * 81)  # önce bulmacayı aç
    sudoku.baslat(conn, did, uc["a"])
    bulmaca = conn.execute("SELECT bulmaca FROM sudoku_duello WHERE id = ?", (did,)).fetchone()[0]
    sabit = next(i for i, c in enumerate(bulmaca) if c != "0")
    bos = next(i for i, c in enumerate(bulmaca) if c == "0")
    sudoku.kaydet(conn, did, uc["a"], "9" * 81)
    kayitli = sudoku.oyun(conn, did, uc["a"])["tahta"]
    assert kayitli[sabit] == "0" and kayitli[bos] == "9"
    for kotu in ("", "1" * 80, "x" * 81):
        with pytest.raises(sudoku.SudokuHatasi):
            sudoku.kaydet(conn, did, uc["a"], kotu)
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku.kaydet(conn, did, uc["c"], "0" * 81)  # katılımcı değil
    oyna(conn, did, uc["a"])
    with pytest.raises(sudoku.SudokuHatasi):
        sudoku.kaydet(conn, did, uc["a"], "0" * 81)  # bitirince kayıt yok


def test_rota_kaydet_ve_sayfa_kayitli_rakamlarla_gelir(istemci, conn, uc, saat):
    import re

    did = duello(conn, uc["a"], uc["b"])
    csrf = giris(istemci, "101", "ali-sifre")
    istemci.get(f"/ogrenci/sudoku/{did}")  # bulmacayı açar
    bulmaca = conn.execute("SELECT bulmaca FROM sudoku_duello WHERE id = ?", (did,)).fetchone()[0]
    bos = [i for i, c in enumerate(bulmaca) if c == "0"]
    tahta = ["0"] * 81
    tahta[bos[0]], tahta[bos[1]] = "4", "7"
    r = istemci.post(f"/ogrenci/sudoku/{did}/kaydet", data={"csrf": csrf, "tahta": "".join(tahta)}, headers={"Accept": "application/json"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    csrf = giris(istemci, "101", "ali-sifre")  # çıkıp giriş
    sayfa = istemci.get(f"/ogrenci/sudoku/{did}")
    z = cozulmus(conn, did)
    assert sayfa.status_code == 200 and z not in sayfa.text and f'data-kaydet="/ogrenci/sudoku/{did}/kaydet"' in sayfa.text
    degerler = re.findall(r'name="h"[^>]*value="(\d?)"', sayfa.text)
    assert len(degerler) == 81 and degerler[bos[0]] == "4" and degerler[bos[1]] == "7" and degerler[bos[2]] == ""
    assert istemci.post(f"/ogrenci/sudoku/{did}/kaydet", data={"csrf": csrf, "tahta": "x"}).status_code == 400
    csrf_c = giris(istemci, "103", "s103")  # katılımcı olmayan: 404
    assert istemci.post(f"/ogrenci/sudoku/{did}/kaydet", data={"csrf": csrf_c, "tahta": "0" * 81}).status_code == 404


def test_geri_al_32(tmp_path):
    from scripts import geri_al

    assert 32 in geri_al.GERI and len(db.GOCLER) >= 32
    c = sqlite3.connect(tmp_path / "t.db")
    c.executescript("\n".join(db.GOCLER))
    assert "tahta" in [r[1] for r in c.execute("PRAGMA table_info(sudoku_oyun)")]
    c.executescript(geri_al.GERI[32])
    assert "tahta" not in [r[1] for r in c.execute("PRAGMA table_info(sudoku_oyun)")]
