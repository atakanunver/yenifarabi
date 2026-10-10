from datetime import timedelta

import auth


def test_sifre_hash_ve_dogrulama():
    h = auth.sifre_hashle("gizli123")
    assert auth.sifre_dogrula("gizli123", h)
    assert not auth.sifre_dogrula("yanlis", h)
    assert not auth.sifre_dogrula("x", None)
    assert not auth.sifre_dogrula("x", "bozuk")


def test_oturum_ac_oku_kapat(conn, ornek):
    t = auth.oturum_ac(conn, ornek["ogretmen"], "test")
    assert auth.oturum_kullanici(conn, t)["id"] == ornek["ogretmen"]
    auth.oturum_kapat(conn, t)
    assert auth.oturum_kullanici(conn, t) is None
    assert auth.oturum_kullanici(conn, None) is None


def test_pasif_kullanicinin_oturumu_gecersiz(conn, ornek):
    t = auth.oturum_ac(conn, ornek["ogretmen"])
    conn.execute("UPDATE kullanici SET aktif = 0 WHERE id = ?", (ornek["ogretmen"],))
    assert auth.oturum_kullanici(conn, t) is None


def test_son_gorulme_gunde_bir_yenilenir(conn, ornek, saat):
    t = auth.oturum_ac(conn, ornek["ogretmen"])
    ilk = conn.execute("SELECT son_gorulme FROM oturum").fetchone()[0]
    saat["an"] += timedelta(hours=2)
    auth.oturum_kullanici(conn, t)
    assert conn.execute("SELECT son_gorulme FROM oturum").fetchone()[0] == ilk
    saat["an"] += timedelta(days=2)
    auth.oturum_kullanici(conn, t)
    assert conn.execute("SELECT son_gorulme FROM oturum").fetchone()[0] != ilk


def test_diger_oturumlari_kapat(conn, ornek):
    a = auth.oturum_ac(conn, ornek["ogretmen"])
    b = auth.oturum_ac(conn, ornek["ogretmen"])
    auth.diger_oturumlari_kapat(conn, ornek["ogretmen"], a)
    assert auth.oturum_kullanici(conn, a) is not None
    assert auth.oturum_kullanici(conn, b) is None


def test_csrf_token_belirleyici_ve_tokena_bagli():
    assert auth.csrf_token("a") == auth.csrf_token("a")
    assert auth.csrf_token("a") != auth.csrf_token("b")


def test_deneme_sinirlama(conn, saat):
    for _ in range(4):
        auth.hata_kaydet(conn, "u:x")
    assert not auth.engelli_mi(conn, "u:x")
    auth.hata_kaydet(conn, "u:x")
    assert auth.engelli_mi(conn, "u:x")
    saat["an"] += timedelta(seconds=61)
    assert not auth.engelli_mi(conn, "u:x")
    auth.hatalari_temizle(conn, "u:x")
    auth.hata_kaydet(conn, "u:x")
    assert not auth.engelli_mi(conn, "u:x")


def test_deneme_penceresi_gecince_sayac_sifirlanir(conn, saat):
    for _ in range(4):
        auth.hata_kaydet(conn, "ip:1")
    saat["an"] += timedelta(minutes=16)
    auth.hata_kaydet(conn, "ip:1")
    assert not auth.engelli_mi(conn, "ip:1")


def test_sms_kodu(conn, saat):
    kod = auth.kod_uret(conn, "05321112233")
    assert len(kod) == 6 and kod.isdigit()
    assert not auth.kod_dogrula(
        conn, "05321112233", "000000" if kod != "000000" else "111111"
    )
    assert auth.kod_dogrula(conn, "05321112233", kod)
    assert not auth.kod_dogrula(conn, "05321112233", kod)  # tek kullanımlık


def test_sms_kodu_suresi_ve_deneme_siniri(conn, saat):
    kod = auth.kod_uret(conn, "05321112233")
    saat["an"] += timedelta(minutes=6)
    assert not auth.kod_dogrula(conn, "05321112233", kod)
    kod = auth.kod_uret(conn, "05321112233")
    yanlis = "000000" if kod != "000000" else "111111"
    for _ in range(5):
        auth.kod_dogrula(conn, "05321112233", yanlis)
    assert not auth.kod_dogrula(conn, "05321112233", kod)
