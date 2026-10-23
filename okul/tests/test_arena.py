"""Bilgi Arenası iş kuralları: XP/seviye, günlük görev, çift ödül engeli, gün sınırı, rozet, Maraton XP, göç."""

import sqlite3
from datetime import timedelta

import arena
import db
import maraton
import pytest
from ayarlar import AYAR
from kaynaklar import KaynakHatasi, arena_soru
from kaynaklar import soru as havuz


@pytest.fixture
def sahte(monkeypatch):
    """Postgres yok: havuz taklit edilir. dogru_index her zaman 1; kazanım 7 (KOD.1) hepsinde."""

    def sorular(sinif, ders, haric, n=5, gorulme=None, yasak=None):
        return [
            {"id": 100 * sinif + i, "konu": "K", "soru": f"S{i}?", "secenekler": ["a", "b", "c"],
             "dogru_index": 1, "kazanim_id": 7, "kazanim_kod": "MAT.9.1", "kazanim_metin": "Metin"}
            for i in range(n + len(haric)) if 100 * sinif + i not in haric
        ][:n]

    monkeypatch.setattr(arena_soru, "sorular", sorular)
    monkeypatch.setattr(havuz, "dersler", lambda s: [("matematik", 40), ("fizik", 20)])
    monkeypatch.setattr(maraton, "kilit", lambda: None)


def _oyna(conn, tur, dogru_say):
    """Sırayla 5 soruyu cevaplar; ilk dogru_say tanesi doğru (şık 1), kalanı yanlış (şık 0)."""
    sonuc = None
    for sira in range(1, 6):
        sonuc = arena.cevapla(conn, tur, sira, 1 if sira <= dogru_say else 0)
    return sonuc


def test_seviye_esikleri():
    assert arena.seviye_hesapla(0)["no"] == 1
    assert arena.seviye_hesapla(49)["no"] == 1
    s = arena.seviye_hesapla(50)
    assert s["no"] == 2 and s["bu_baslangic"] == 50 and s["sonraki"] == 120
    assert arena.seviye_hesapla(10**6)["sonraki"] is None


def test_xp_defteri_tekil(conn, ornek):
    k = ornek["ogr1_k"]
    assert arena.xp_ver(conn, k, "arena_bonus", "1", 10) is True
    assert arena.xp_ver(conn, k, "arena_bonus", "1", 10) is False  # aynı ref ikinci kez eklenmez
    assert arena.xp_ver(conn, k, "arena_bonus", "2", 0) is False
    conn.commit()
    assert arena.toplam_xp(conn, k) == 10


def test_gorev_tamamlama_xp_ve_tek_gun(conn, ornek, sahte):
    k = ornek["ogr1_k"]
    tur = arena.baslat(conn, k, "9-A")
    assert arena.baslat(conn, k, "9-A") == tur  # aynı gün ikinci tur yok
    s = _oyna(conn, tur, 4)
    assert s["bitti"] is True
    assert arena.toplam_xp(conn, k) == 4 * 10 + 10  # 4 doğru + tamamlama bonusu
    t = arena.tur_getir(conn, tur, k)
    assert (t["durum"], t["dogru"], t["xp"]) == ("tamam", 4, 50)
    assert arena.baslat(conn, k, "9-A") == tur  # tamamlandıktan sonra da yeni tur açılmaz
    assert conn.execute("SELECT count(*) FROM bilgi_tur").fetchone()[0] == 1


def test_cift_gonderim_xp_vermez(conn, ornek, sahte):
    k = ornek["ogr1_k"]
    tur = arena.baslat(conn, k, "9-A")
    arena.cevapla(conn, tur, 1, 1)
    with pytest.raises(arena.ArenaHatasi):
        arena.cevapla(conn, tur, 1, 1)
    assert arena.toplam_xp(conn, k) == 10


def test_sira_atlanamaz_ve_gecersiz_sik(conn, ornek, sahte):
    k = ornek["ogr1_k"]
    tur = arena.baslat(conn, k, "9-A")
    with pytest.raises(arena.ArenaHatasi):
        arena.cevapla(conn, tur, 3, 1)
    with pytest.raises(arena.ArenaHatasi):
        arena.cevapla(conn, tur, 1, 9)
    with pytest.raises(arena.ArenaHatasi):
        arena.cevapla(conn, tur, 1, -1)
    assert arena.toplam_xp(conn, k) == 0


def test_baska_kullanici_turu_gorunmez(conn, ornek, sahte):
    tur = arena.baslat(conn, ornek["ogr1_k"], "9-A")
    assert arena.tur_getir(conn, tur, ornek["ogr2_k"]) is None


def test_gun_siniri_yeni_gun_yeni_gorev(conn, ornek, sahte, saat):
    k = ornek["ogr1_k"]
    t1 = arena.baslat(conn, k, "9-A")
    _oyna(conn, t1, 5)
    saat["an"] = saat["an"] + timedelta(days=1)
    t2 = arena.baslat(conn, k, "9-A")
    assert t2 != t1
    assert arena.gorev_durumu(conn, k, "9-A")["durum"] == "devam"


def test_dunden_kalan_yarim_tur_terk(conn, ornek, sahte, saat):
    k = ornek["ogr1_k"]
    t1 = arena.baslat(conn, k, "9-A")
    arena.cevapla(conn, t1, 1, 1)
    saat["an"] = saat["an"] + timedelta(days=1)
    arena.baslat(conn, k, "9-A")
    assert arena.tur_getir(conn, t1, k)["durum"] == "terk"
    assert arena.toplam_xp(conn, k) == 10  # cevaplananın XP'si korunur, yenisi eklenmez


def test_yetersiz_soru(conn, ornek, monkeypatch):
    monkeypatch.setattr(maraton, "kilit", lambda: None)
    monkeypatch.setattr(havuz, "dersler", lambda s: [("matematik", 40)])
    monkeypatch.setattr(arena_soru, "sorular", lambda *a, **kw: [{"id": 1}] * 3)
    with pytest.raises(arena.ArenaHatasi):
        arena.baslat(conn, ornek["ogr1_k"], "9-A")
    assert conn.execute("SELECT count(*) FROM bilgi_tur").fetchone()[0] == 0


def test_kilit_ve_duzey(conn, ornek, sahte, monkeypatch):
    k = ornek["ogr1_k"]
    monkeypatch.setattr(maraton, "kilit", lambda: {"bit": "10:30", "no": 3})
    assert arena.gorev_durumu(conn, k, "9-A") == {
        "soru_sayisi": 5, "dk": arena.DAKIKA, "durum": "kilit", "kilit_bit": "10:30"}
    with pytest.raises(arena.ArenaHatasi):
        arena.baslat(conn, k, "9-A")
    monkeypatch.setattr(maraton, "kilit", lambda: None)
    with pytest.raises(arena.ArenaHatasi):
        arena.baslat(conn, k, "12-A")  # 12. sınıf donduruldu
    assert arena.gorev_durumu(conn, k, "12-A")["durum"] == "yetersiz"


def test_kaynak_yok(conn, ornek, monkeypatch):
    monkeypatch.setattr(maraton, "kilit", lambda: None)

    def patla(s):
        raise KaynakHatasi("pg")

    monkeypatch.setattr(havuz, "dersler", patla)
    assert arena.gorev_durumu(conn, ornek["ogr1_k"], "9-A")["durum"] == "kaynak_yok"


def test_gunun_dersi_kararli():
    a = arena.gunun_dersi(5, "2026-10-12", ["fizik", "matematik", "kimya"])
    assert a == arena.gunun_dersi(5, "2026-10-12", ["matematik", "kimya", "fizik"])


def test_rozetler_ve_kazanim_ustasi(conn, ornek, sahte, saat):
    k = ornek["ogr1_k"]
    ilk = None
    for gun in range(5):  # 5 ayrı gün, her gün 5/5 doğru, aynı kazanım
        tur = arena.baslat(conn, k, "9-A")
        s = _oyna(conn, tur, 5)
        if gun == 0:
            ilk = s
        saat["an"] = saat["an"] + timedelta(days=1)
    assert [r["ad"] for r in ilk["yeni_rozetler"]] == ["İlk Arena Turu"]
    kodlar = {r["kod"] for r in arena.rozetler(conn, k) if r["kazanildi"]}
    # 25 doğru: İlk 50 Doğru henüz yok; Kazanım Ustası 3. günde 15 soru ≥ %80 ile kazanıldı
    assert "elli_dogru" not in kodlar
    assert {"ilk_tur", "bes_gun", "kazanim_ustasi"} <= kodlar
    # ikinci kez verilmez
    assert arena.rozet_kontrol(conn, k) == []


def test_kazanim_ustasi_az_gun_veya_dusuk_basari(conn, ornek, sahte, saat):
    k = ornek["ogr1_k"]
    for _ in range(2):  # yalnızca 2 gün
        _oyna(conn, arena.baslat(conn, k, "9-A"), 5)
        saat["an"] += timedelta(days=1)
    assert "kazanim_ustasi" not in {r["kod"] for r in arena.rozetler(conn, k) if r["kazanildi"]}
    for _ in range(3):  # 3 gün ama %60 doğru
        _oyna(conn, arena.baslat(conn, k, "9-A"), 0)
        saat["an"] += timedelta(days=1)
    assert "kazanim_ustasi" not in {r["kod"] for r in arena.rozetler(conn, k) if r["kazanildi"]}


def test_kazanimsiz_soru_ustalik_saymaz(conn, ornek, monkeypatch, saat):
    monkeypatch.setattr(maraton, "kilit", lambda: None)
    monkeypatch.setattr(havuz, "dersler", lambda s: [("matematik", 40)])
    monkeypatch.setattr(arena_soru, "sorular", lambda sinif, ders, haric, n=5, g=None, yasak=None: [
        {"id": 900 + len(haric) + i, "konu": "K", "soru": "S?", "secenekler": ["a", "b"], "dogru_index": 1,
         "kazanim_id": None, "kazanim_kod": None, "kazanim_metin": None} for i in range(n)])
    k = ornek["ogr1_k"]
    for _ in range(3):
        _oyna(conn, arena.baslat(conn, k, "9-A"), 5)
        saat["an"] += timedelta(days=1)
    assert "kazanim_ustasi" not in {r["kod"] for r in arena.rozetler(conn, k) if r["kazanildi"]}
    assert arena.kazanim_ozeti(conn, 1) == []


def test_seviye_atlama_bildirilir(conn, ornek, sahte):
    k = ornek["ogr1_k"]
    tur = arena.baslat(conn, k, "9-A")
    for sira in range(1, 5):
        assert arena.cevapla(conn, tur, sira, 1)["seviye_atladi"] is None
    s = arena.cevapla(conn, tur, 5, 1)  # toplam 60 XP → seviye 2
    assert arena.seviye(conn, k)["no"] == 2
    assert arena.seviye_atladi(conn, k, arena.tur_getir(conn, tur, k)) == 2
    assert s["seviye_atladi"] == 2


def test_tekrar_onerisi_ve_ozet(conn, ornek, sahte):
    k = ornek["ogr1_k"]
    tur = arena.baslat(conn, k, "9-A")
    _oyna(conn, tur, 3)
    oz = arena.kazanim_ozeti(conn, tur)
    assert oz == [{"kod": "MAT.9.1", "metin": "Metin", "dogru": 3, "toplam": 5}]
    assert arena.tekrar_onerileri(conn, k) == [{"kod": "MAT.9.1", "metin": "Metin"}]
    assert arena.hafta_ozeti(conn, k)["tur"] == 1
    assert arena.son_tur(conn, k)["dogru"] == 3
    assert sum(g["tamam"] for g in arena.gunler(conn, k)) == 1


# --- Hızlı Mod XP kancası ---


def _maraton(conn, kid, dogru, bitis, duzey=9, terk=False):
    cur = conn.execute(
        "INSERT INTO maraton (kullanici_id, sinif, duzey, ders, basla, bitis, dogru) VALUES (?, ?, ?, 'matematik', ?, ?, ?)",
        (kid, f"{duzey}-A", duzey, bitis, bitis, dogru),
    )
    if terk:
        conn.execute(
            "INSERT INTO maraton_soru (maraton_id, sira, soru_id, soru, secenekler, dogru_index, cevap)"
            " VALUES (?, 1, 1, 's', '[]', 0, -2)", (cur.lastrowid,))
    conn.commit()
    return cur.lastrowid


def test_maraton_xp_idempotent_ve_tavan(conn, ornek):
    k = ornek["ogr1_k"]
    a, *orta, c = (_maraton(conn, k, 7, f"2026-10-12 1{i}:00:00") for i in range(6))
    assert arena.maraton_xp(conn, k, a) == 70
    assert arena.maraton_xp(conn, k, a) == 0  # tekrar
    assert all(arena.maraton_xp(conn, k, m) == 70 for m in orta)
    assert arena.maraton_xp(conn, k, c) == 0  # günde en çok 5 tur
    assert arena.toplam_xp(conn, k) == 350
    gun2 = _maraton(conn, k, 3, "2026-10-13 09:00:00")
    assert arena.maraton_xp(conn, k, gun2) == 30


def test_maraton_xp_terk_sifir_12sinif_yok(conn, ornek):
    k = ornek["ogr1_k"]
    assert arena.maraton_xp(conn, k, _maraton(conn, k, 9, "2026-10-12 10:00:00", terk=True)) == 0
    assert arena.maraton_xp(conn, k, _maraton(conn, k, 0, "2026-10-12 11:00:00")) == 0  # 0 doğru
    assert arena.maraton_xp(conn, k, _maraton(conn, k, 9, "2026-10-12 11:00:00", duzey=12)) == 0
    assert arena.maraton_xp(conn, ornek["ogr2_k"], _maraton(conn, k, 9, "2026-10-12 12:00:00")) == 0  # başkasının
    assert arena.toplam_xp(conn, k) == 0


def test_arena_ve_maraton_xp_ortak_toplam(conn, ornek, sahte):
    k = ornek["ogr1_k"]
    _oyna(conn, arena.baslat(conn, k, "9-A"), 5)  # 60
    arena.maraton_xp(conn, k, _maraton(conn, k, 5, "2026-10-12 12:00:00"))  # 50
    assert arena.toplam_xp(conn, k) == 110


# --- Göç ---


def test_v5_gocu_v4_verisini_korur(tmp_path, monkeypatch):
    monkeypatch.setattr(AYAR, "db_yolu", tmp_path / "eski.db")
    conn = sqlite3.connect(AYAR.db_yolu)
    for i in range(4):  # canlıdaki durum: V4
        conn.executescript(f"BEGIN;\n{db.GOCLER[i]}\nPRAGMA user_version = {i + 1};\nCOMMIT;")
    conn.execute(
        "INSERT INTO kullanici (rol, ad_soyad, sifre_hash, sifre_degismeli, olusturma) VALUES ('ogrenci','A','x',0,'t')"
    )
    conn.execute("INSERT INTO olay (kullanici_id, rol, tur, gun, saat) VALUES (1,'ogrenci','giris','2026-10-12',9)")
    conn.commit()
    conn.close()
    db.sema_kur()
    c = db.baglanti()
    assert c.execute("PRAGMA user_version").fetchone()[0] == len(db.GOCLER) >= 5
    assert c.execute("SELECT count(*) FROM olay").fetchone()[0] == 1
    assert c.execute("SELECT count(*) FROM kullanici").fetchone()[0] == 1
    assert {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE name LIKE 'bilgi_%' AND type='table'")} == {
        "bilgi_tur", "bilgi_cevap", "bilgi_xp", "bilgi_rozet"}
    c.close()


def test_geri_alma_betigi(tmp_path, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    yol = tmp_path / "gb.db"
    monkeypatch.setattr(AYAR, "db_yolu", yol)
    db.sema_kur()
    c = sqlite3.connect(yol)
    c.execute("INSERT INTO kullanici (rol, ad_soyad, sifre_hash, sifre_degismeli, olusturma) VALUES ('ogrenci','A','x',0,'t')")
    c.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (1,'arena_bonus','1',10,'g','z')")
    c.commit()
    c.close()
    spec = importlib.util.spec_from_file_location("geri_al", Path(__file__).resolve().parent.parent / "scripts" / "geri_al.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.geri_al(yol, 4, onayla=False) == 0  # kuru çalıştırma
    assert "bilgi_xp silinecek (1 satır)" in capsys.readouterr().out
    assert sqlite3.connect(yol).execute("PRAGMA user_version").fetchone()[0] == len(db.GOCLER)
    assert m.geri_al(yol, 4, onayla=True) == 0
    c = sqlite3.connect(yol)
    assert c.execute("PRAGMA user_version").fetchone()[0] == 4
    assert c.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'bilgi_%'").fetchone()[0] == 0
    assert c.execute("SELECT count(*) FROM kullanici").fetchone()[0] == 1  # eski veri korunur
    c.close()
    db.sema_kur()  # ileri göç yeniden uygulanabilir
    assert sqlite3.connect(yol).execute("PRAGMA user_version").fetchone()[0] == len(db.GOCLER)


def test_gunluk_gorev_pas_ve_hatali(conn, ornek, sahte):
    k = ornek["ogr1_k"]
    tur = arena.baslat(conn, k, "9-A")
    assert arena.gec(conn, tur, 1)["bitti"] is False  # pas
    with pytest.raises(arena.ArenaHatasi):  # pas hakkı 1
        arena.gec(conn, tur, 2)
    for sira in (2, 3, 4):
        arena.gec(conn, tur, sira, hatali=True)
    assert arena.kareler(conn, tur) == ["bos"] * 4 + ["bos"]
    assert arena.gec(conn, tur, 5, hatali=True)["bitti"] is True
    # hiç gerçek cevap yok: bitiş bonusu ve kazanım istatistiği yok
    assert arena.toplam_xp(conn, k) == 0
    assert arena.kazanim_ozeti(conn, tur) == []
    assert arena.tur_getir(conn, tur, k)["durum"] == "tamam"


def test_gunluk_gorev_cevapli_ve_gecili_karisik(conn, ornek, sahte):
    k = ornek["ogr1_k"]
    tur = arena.baslat(conn, k, "9-A")
    arena.gec(conn, tur, 1, hatali=True)
    for sira in range(2, 6):
        arena.cevapla(conn, tur, sira, 1)
    assert arena.toplam_xp(conn, k) == 4 * 10 + 10  # 4 doğru + bonus (en az bir gerçek cevap)
    oz = arena.kazanim_ozeti(conn, tur)
    assert oz[0]["toplam"] == 4 and oz[0]["dogru"] == 4  # hatalı soru istatistiğe girmez
