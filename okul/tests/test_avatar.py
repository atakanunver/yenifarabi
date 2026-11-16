"""Avatar: SVG güvenliği, seviyeye göre açılma (sunucuda doğrulanır), kayıt, önizleme, bildirimler, yetki."""

from pathlib import Path

import auth
import avatar
import pytest
from fastapi.testclient import TestClient
from kaynaklar import arena_soru, kazanim
from kaynaklar import soru as havuz


def _xp(conn, kid, miktar):
    conn.execute("INSERT INTO bilgi_xp (kullanici_id, kaynak, ref, miktar, gun, zaman) VALUES (?, 'arena_bonus', 'x', ?, '2026-10-12', 'z')", (kid, miktar))
    conn.commit()


@pytest.mark.parametrize("kod", ["<script>", "../x", "ejder-9", "ejder-"])
def test_svg_gecerli_ve_guvenli(kod):
    cfg = avatar.cfg_temiz({"karakter": kod})
    assert cfg == {"karakter": "kasif", "kostum": "1"}
    s = str(avatar.svg({"karakter": kod}, 3, 64))
    assert s.count("/static/avatar/") == 1 and "/static/avatar/kasif-1.webp?v=1" in s
    assert 'width="64"' in s and "Kaşif avatarı, seviye 3" in s
    assert str(avatar.svg(None, 1)) != str(avatar.svg(None, 1))
    assert avatar.cfg_temiz({"karakter": "ejder", "kostum": "9"}) == avatar.VARSAYILAN


def test_gorseller_mevcut():
    dizin = Path(__file__).resolve().parents[1] / "static" / "avatar"
    assert all((dizin / f"{kod}-{n}.webp").is_file() for kod in avatar.KARAKTERLER for n in range(1, 4))


def test_kademe_ve_yildiz():
    assert avatar.kademe(1)[1] == "Çaylak" and avatar.kademe(3)[1] == "Kaşif"
    assert avatar.kademe(10)[1] == "Şampiyon"
    assert str(avatar.svg(None, 1)).count('l1.8 3.6') == 0
    assert str(avatar.svg(None, 9)).count('l1.8 3.6') == 4


def test_acilma_seviyeleri():
    assert avatar.acik_mi("karakter", "kasif", 1)
    assert not avatar.acik_mi("karakter", "ejder", 7) and avatar.acik_mi("karakter", "ejder", 8)
    assert not avatar.acik_mi("kostum", "2", 2, "kasif") and avatar.acik_mi("kostum", "2", 3, "kasif")
    assert not avatar.acik_mi("kostum", "9", 10, "kasif")


def test_kaydet_dogrular(conn, ornek):
    k = ornek["ogr1_k"]
    avatar.kaydet(conn, k, {"karakter": "bilge", "kostum": "1"}, 2)
    with pytest.raises(ValueError, match="henüz açılmadı"):
        avatar.kaydet(conn, k, {"karakter": "ejder", "kostum": "1"}, 7)
    with pytest.raises(ValueError, match="henüz açılmadı"):
        avatar.kaydet(conn, k, {"karakter": "kasif", "kostum": "2"}, 2)
    assert avatar.getir(conn, k) == {"karakter": "bilge", "kostum": "1"}
    conn.execute("UPDATE avatar SET karakter='ejder', sapka='tac' WHERE kullanici_id=?", (k,))
    assert avatar.getir(conn, k) == {"karakter": "ejder", "kostum": "1"}
    avatar.kaydet(conn, k, {"karakter": "ejder", "kostum": "3"}, 10)
    assert avatar.getir(conn, k) == {"karakter": "ejder", "kostum": "3"}
    assert tuple(conn.execute("SELECT karakter, sapka, yuz, sirt FROM avatar WHERE kullanici_id=?", (k,)).fetchone()) == ("ejder-3", "yok", "yok", "yok")


def test_acilanlar_ve_siradaki():
    assert avatar.acilanlar(1, 1) == []
    assert "Bilge Baykuş (karakter)" in avatar.acilanlar(1, 2)
    assert "Kalpaklı Keloğlan (kostüm)" in avatar.acilanlar(2, 3)
    assert "Keloğlan (karakter)" in avatar.acilanlar(0, 1)
    assert "Keloğlan (kostüm)" not in avatar.acilanlar(0, 1)
    assert avatar.siradaki_acilis(1) == (2, avatar.acilanlar(1, 2))
    assert avatar.siradaki_acilis(10) is None


@pytest.fixture
def istemci(monkeypatch):
    monkeypatch.setattr(havuz, "dersler", lambda s: [("matematik", 40)])
    monkeypatch.setattr(arena_soru, "sorular", lambda *a, **k: [])
    monkeypatch.setattr(kazanim, "form_sonuclari", lambda okul_no: [])
    from app import app

    with TestClient(app) as c:
        yield c


def giris(c, kadi, sifre):
    c.cookies.clear()
    assert c.post("/giris", data={"kullanici_adi": kadi, "sifre": sifre}, follow_redirects=False).status_code == 303
    return auth.csrf_token(c.cookies.get(auth.COOKIE_ADI))


def test_sayfa_onizleme_ve_kayit(istemci, ornek, conn):
    csrf = giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci/avatar").text
    assert "Avatarım" in t and "Seviye 2'de açılır" in t and "Kayıtlı avatarın bu" in t
    # önizleme: açık seçenek uygulanır, kilitli seçenek yok sayılır
    assert "Bu avatarı kullan" in istemci.get("/ogrenci/avatar?karakter=robi").text
    assert "Bu avatarı kullan" not in istemci.get("/ogrenci/avatar?karakter=ejder").text
    assert "Bu avatarı kullan" not in istemci.get("/ogrenci/avatar?karakter=kasif&kostum=2").text
    r = istemci.post("/ogrenci/avatar", data={"csrf": csrf, "karakter": "kasif", "kostum": "2"})
    assert r.status_code == 400 and "henüz açılmadı" in r.text
    # kilitli kayıt reddedilir
    r = istemci.post("/ogrenci/avatar", data={"csrf": csrf, "karakter": "ejder", "kostum": "1"})
    assert r.status_code == 400 and "henüz açılmadı" in r.text
    assert conn.execute("SELECT count(*) FROM avatar").fetchone()[0] == 0
    r = istemci.post("/ogrenci/avatar", data={"csrf": csrf, "karakter": "robi", "kostum": "1"}, follow_redirects=False)
    assert r.status_code == 303 and "Kaydedildi" in istemci.get("/ogrenci/avatar?tamam=1").text
    assert avatar.getir(conn, ornek["ogr1_k"])["karakter"] == "robi"
    # seviye yükselince yeni seçenek kullanılabilir
    _xp(conn, ornek["ogr1_k"], 120)  # seviye 3
    r = istemci.post("/ogrenci/avatar", data={"csrf": csrf, "karakter": "bilge", "kostum": "1"}, follow_redirects=False)
    assert r.status_code == 303
    r = istemci.post("/ogrenci/avatar", data={"csrf": csrf, "karakter": "kasif", "kostum": "2"}, follow_redirects=False)
    assert r.status_code == 303
    t = istemci.get("/ogrenci/avatar?karakter=robi").text
    assert 'name="kostum" value="1"' in t
    assert 'name="kostum" value="2"' in istemci.get("/ogrenci/avatar?karakter=kasif&kostum=2").text


def test_csrf_yetki_ve_baskasinin_avatari(istemci, ornek, conn):
    giris(istemci, "101", "ali-sifre")
    assert istemci.post("/ogrenci/avatar", data={"karakter": "robi"}).status_code == 400
    for kadi, sifre in (("hoca", "hoca-sifre"), ("mudur", "mudur-sifre")):
        c = giris(istemci, kadi, sifre)
        assert istemci.get("/ogrenci/avatar").status_code == 404
        assert istemci.post("/ogrenci/avatar", data={"csrf": c, "karakter": "robi"}).status_code == 404
    c = giris(istemci, "101", "ali-sifre")
    istemci.post("/ogrenci/avatar", data={"csrf": c, "karakter": "robi", "kostum": "1"})
    giris(istemci, "201", "ayse-sifre")  # başkası kendi avatarını görür, Ali'ninkini değil
    assert avatar.getir(conn, ornek["ogr2_k"])["karakter"] == "kasif"


def test_avatar_arena_ve_ana_ekranda(istemci, ornek, conn):
    giris(istemci, "101", "ali-sifre")
    assert 'class="avatar"' in istemci.get("/ogrenci/arena").text and "Avatarımı değiştir" in istemci.get("/ogrenci/arena").text
    assert 'class="avatar"' in istemci.get("/ogrenci").text


def test_liderlikte_avatar_simgesi(istemci, ornek, conn):
    _xp(conn, ornek["ogr2_k"], 80)
    avatar.kaydet(conn, ornek["ogr2_k"], {"karakter": "robi"}, 1)
    giris(istemci, "101", "ali-sifre")
    t = istemci.get("/ogrenci/arena/liderlik?donem=tum").text
    assert "avatar-mini" in t and "Robi avatarı" in t


def test_seviye_atlayinca_acilan_bildirilir(istemci, ornek, conn, monkeypatch, saat):
    from datetime import timedelta  # noqa: F401
    import arena

    monkeypatch.setattr(arena_soru, "sorular", lambda sinif, ders, haric, n=5, g=None, yasak=None: [
        {"id": 100 + i, "konu": "K", "soru": "S?", "secenekler": ["a", "b"], "dogru_index": 1, "kazanim_id": 1,
         "kazanim_kod": "K.1", "kazanim_metin": "M"} for i in range(n)])
    monkeypatch.setattr(arena.maraton, "kilit", lambda: None)
    csrf = giris(istemci, "101", "ali-sifre")
    tur = int(istemci.post("/ogrenci/arena/basla", data={"csrf": csrf}, follow_redirects=False).headers["location"].rsplit("/", 1)[1])
    for sira in range(1, 6):
        istemci.post(f"/ogrenci/arena/{tur}/cevap", data={"csrf": csrf, "sira": sira, "sec": 1}, headers={"Accept": "application/json"})
    t = istemci.get(f"/ogrenci/arena/{tur}/sonuc").text
    assert "Birincisin!" in t and "Seviye 2'e ulaştın" in t and "Yeni açıldı" in t and "Bilge Baykuş" in t and "Avatarını güzelleştir" in t
