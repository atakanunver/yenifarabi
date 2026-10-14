"""Anket modülü: hazırlama/kilit, ayrı dağıtım, kapsam (sınıf süzgeci, veli-çocuk), tek yanıt, anonimlik, küçük grup gizleme."""

import sqlite3
import threading
from datetime import timedelta

import anket
import pytest


def _ogrenciler(conn, yeni_kullanici, n, sinif="9-A", baslangic=300):
    kimlikler = []
    for i in range(n):
        kid = yeni_kullanici(conn, "ogrenci", f"Ogr {sinif} {baslangic + i}", str(baslangic + i), sifre="x")
        conn.execute(
            "INSERT INTO ogrenci (okul_no, ad_soyad, sinif, kullanici_id) VALUES (?, ?, ?, ?)",
            (baslangic + i, f"Ogr {baslangic + i}", sinif, kid),
        )
        kimlikler.append(kid)
    conn.commit()
    return kimlikler


def _kisi(conn, kid):
    return conn.execute("SELECT * FROM kullanici WHERE id = ?", (kid,)).fetchone()


@pytest.fixture
def a(conn, ornek):
    """Üç soruluk bir anket: ölçek (herkes), tek seçim (yalnız öğrenci), açık uçlu (isteğe bağlı, herkes)."""
    aid = anket.olustur(conn, ornek["yonetici"], "Okul memnuniyeti", "Kısa anket")
    anket.soru_ekle(conn, aid, "olcek", "Okulu ne kadar seviyorsun?", [], True, ["ogrenci", "veli", "ogretmen"])
    anket.soru_ekle(conn, aid, "tek", "Servis kullanıyor musun?", ["Evet", "Hayır"], True, ["ogrenci"])
    anket.soru_ekle(conn, aid, "metin", "Eklemek istediğin?", [], False, ["ogrenci", "veli", "ogretmen"])
    return aid


def _sid(conn, aid, sira):
    return conn.execute("SELECT id FROM anket_soru WHERE anket_id = ? AND sira = ?", (aid, sira)).fetchone()[0]


def _doldur(conn, k, aid, puan="4", servis="0", metin=""):
    girdi = {_sid(conn, aid, 1): [puan], _sid(conn, aid, 3): [metin]}
    if k["rol"] == "ogrenci":
        girdi[_sid(conn, aid, 2)] = [servis]
    anket.yanitla(conn, _kisi(conn, k["id"]) if not isinstance(k, sqlite3.Row) else k, aid, girdi)


def test_olusturma_dogrulama(conn, ornek):
    with pytest.raises(anket.AnketHatasi):
        anket.olustur(conn, ornek["yonetici"], "   ")
    aid = anket.olustur(conn, ornek["yonetici"], "  Başlık   boşluklu ")
    assert anket.getir(conn, aid)["baslik"] == "Başlık boşluklu"
    for tur, sec in (("tek", ["a"]), ("tek", ["a", "a"]), ("coklu", [str(i) for i in range(11)]), ("x", []), ("tek", [])):
        with pytest.raises(anket.AnketHatasi):
            anket.soru_ekle(conn, aid, tur, "S?", sec, True, ["ogrenci"])
    with pytest.raises(anket.AnketHatasi):
        anket.soru_ekle(conn, aid, "metin", "S?", [], True, [])  # hiçbir gruba sorulmuyor
    with pytest.raises(anket.AnketHatasi):
        anket.soru_ekle(conn, aid, "metin", "", [], True, ["ogrenci"])


def test_sorular_dagitimdan_sonra_degismez(conn, ornek, a):
    anket.dagit(conn, a, "ogrenci")
    with pytest.raises(anket.AnketHatasi):
        anket.soru_ekle(conn, a, "metin", "Yeni?", [], False, ["ogrenci"])
    with pytest.raises(anket.AnketHatasi):
        anket.soru_sil(conn, a, _sid(conn, a, 1))
    with pytest.raises(anket.AnketHatasi):
        anket.sil(conn, a)


def test_taslak_soru_sil_ve_sirala(conn, ornek, a):
    anket.soru_sil(conn, a, _sid(conn, a, 2))
    assert [s["sira"] for s in anket.sorular(conn, a)] == [1, 2]
    anket.sil(conn, a)
    assert anket.getir(conn, a) is None
    assert conn.execute("SELECT count(*) FROM anket_soru").fetchone()[0] == 0


def test_dagitim_gruplara_ayri_ve_dogrulama(conn, ornek, a):
    anket.dagit(conn, a, "ogrenci", "9, 9-A")
    with pytest.raises(anket.AnketHatasi):
        anket.dagit(conn, a, "ogrenci")  # aynı gruba ikinci kez
    with pytest.raises(anket.AnketHatasi):
        anket.dagit(conn, a, "veli", "99")  # olmayan sınıf
    with pytest.raises(anket.AnketHatasi):
        anket.dagit(conn, a, "veli", "", "2020-01-01")  # geçmiş tarih
    with pytest.raises(anket.AnketHatasi):
        anket.dagit(conn, a, "veli", "", "yarin")
    with pytest.raises(anket.AnketHatasi):
        anket.dagit(conn, a, "yonetici")
    assert set(anket.hedefler(conn, a)) == {"ogrenci"}  # veli/öğretmen etkilenmedi
    k = _kisi(conn, ornek["ogr1_k"])
    assert [x["id"] for x in anket.kullanicinin_anketleri(conn, k)["bekleyen"]] == [a]
    assert anket.kullanicinin_anketleri(conn, _kisi(conn, ornek["veli1"]))["bekleyen"] == []  # veliye gitmedi
    assert anket.kullanicinin_anketleri(conn, _kisi(conn, ornek["ogretmen"]))["bekleyen"] == []


def test_grup_icin_soru_yoksa_gonderilmez(conn, ornek):
    aid = anket.olustur(conn, ornek["yonetici"], "Sadece öğrenci")
    anket.soru_ekle(conn, aid, "metin", "S?", [], False, ["ogrenci"])
    with pytest.raises(anket.AnketHatasi):
        anket.dagit(conn, aid, "veli")


def test_sinif_suzgeci_kapsam(conn, ornek, a):
    anket.dagit(conn, a, "ogrenci", "9-A")
    assert anket.kullanicinin_anketleri(conn, _kisi(conn, ornek["ogr1_k"]))["bekleyen"]  # 9-A
    assert not anket.kullanicinin_anketleri(conn, _kisi(conn, ornek["ogr2_k"]))["bekleyen"]  # 9-B
    with pytest.raises(anket.AnketHatasi):
        _doldur(conn, _kisi(conn, ornek["ogr2_k"]), a)  # URL'yi bilse de yanıtlayamaz


def test_veli_cocugun_sinifina_gore(conn, ornek, a):
    anket.dagit(conn, a, "veli", "9-A")
    assert anket.kullanicinin_anketleri(conn, _kisi(conn, ornek["veli1"]))["bekleyen"]  # çocuğu 9-A
    anket.dagit(conn, a, "ogretmen")
    assert anket.kullanicinin_anketleri(conn, _kisi(conn, ornek["ogretmen"]))["bekleyen"]
    assert anket.kullanicinin_anketleri(conn, _kisi(conn, ornek["yonetici"])) == {"bekleyen": [], "yanitlanan": []}


def test_veli_cocugu_baska_sinifta_gormez(conn, ornek, a, yeni_kullanici):
    (o10,) = _ogrenciler(conn, yeni_kullanici, 1, "10-A", 900)  # 10. sınıf var, başka velinin çocuğu
    veli2 = yeni_kullanici(conn, "veli", "Veli İki", telefon="05320000000")
    conn.execute("INSERT INTO veli_ogrenci (veli_id, ogrenci_id) VALUES (?, (SELECT id FROM ogrenci WHERE kullanici_id = ?))", (veli2, o10))
    conn.commit()
    anket.dagit(conn, a, "veli", "10")
    assert not anket.kullanicinin_anketleri(conn, _kisi(conn, ornek["veli1"]))["bekleyen"]
    assert anket.kullanicinin_anketleri(conn, _kisi(conn, veli2))["bekleyen"]


def test_tek_yanit_ve_yanitlanan_listesi(conn, ornek, a):
    anket.dagit(conn, a, "ogrenci")
    k = _kisi(conn, ornek["ogr1_k"])
    _doldur(conn, k, a)
    with pytest.raises(anket.AnketHatasi):
        _doldur(conn, k, a)
    assert conn.execute("SELECT count(*) FROM anket_yanit").fetchone()[0] == 1
    liste = anket.kullanicinin_anketleri(conn, k)
    assert liste["bekleyen"] == [] and [x["id"] for x in liste["yanitlanan"]] == [a]


def test_paralel_ayni_kullanici_tek_yanit(tmp_path, conn, ornek, a, monkeypatch):
    anket.dagit(conn, a, "ogrenci")
    sonuc = []

    def gonder():
        c = sqlite3.connect(conn.execute("PRAGMA database_list").fetchone()[2], timeout=5)
        c.row_factory = sqlite3.Row
        k = c.execute("SELECT * FROM kullanici WHERE id = ?", (ornek["ogr1_k"],)).fetchone()
        try:
            _doldur(c, k, a)
            sonuc.append("ok")
        except anket.AnketHatasi:
            sonuc.append("red")
        finally:
            c.close()

    ts = [threading.Thread(target=gonder) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sonuc.count("ok") == 1
    assert conn.execute("SELECT count(*) FROM anket_yanit").fetchone()[0] == 1


def test_yanit_dogrulama(conn, ornek, a):
    anket.dagit(conn, a, "ogrenci")
    k = _kisi(conn, ornek["ogr1_k"])
    s1, s2, s3 = (_sid(conn, a, i) for i in (1, 2, 3))
    for girdi in (
        {s1: ["6"], s2: ["0"]},  # ölçek dışı
        {s1: ["0"], s2: ["0"]},
        {s1: ["x"], s2: ["0"]},
        {s2: ["0"]},  # zorunlu ölçek boş
        {s1: ["3"], s2: ["5"]},  # olmayan seçenek
        {s1: ["3"], s2: ["0", "1"]},  # tek seçimde iki değer
        {s1: ["3"], s2: ["0"], s3: ["x" * 1001]},
    ):
        with pytest.raises(anket.AnketHatasi):
            anket.yanitla(conn, k, a, girdi)
    assert conn.execute("SELECT count(*) FROM anket_katilim").fetchone()[0] == 0  # hata = hiçbir şey yazılmaz
    assert conn.execute("SELECT count(*) FROM anket_cevap").fetchone()[0] == 0
    anket.yanitla(conn, k, a, {s1: ["3"], s2: ["1"]})  # isteğe bağlı açık uçlu boş bırakılabilir
    assert conn.execute("SELECT count(*) FROM anket_cevap").fetchone()[0] == 2


def test_baska_role_sorulan_soru_yoksayilir(conn, ornek, a):
    anket.dagit(conn, a, "veli")
    veli = _kisi(conn, ornek["veli1"])
    s1, s2 = _sid(conn, a, 1), _sid(conn, a, 2)
    anket.yanitla(conn, veli, a, {s1: ["5"], s2: ["0"]})  # s2 öğrencilere özel; veli gönderse de yazılmaz
    assert [r[0] for r in conn.execute("SELECT soru_id FROM anket_cevap")] == [s1]


def test_kapanis_ve_kapatma(conn, ornek, a, saat):
    anket.dagit(conn, a, "ogrenci", "", "2026-10-12")
    k = _kisi(conn, ornek["ogr1_k"])
    saat["an"] = saat["an"] + timedelta(days=1)  # son gün geçti
    assert anket.kullanicinin_anketleri(conn, k)["bekleyen"] == []
    with pytest.raises(anket.AnketHatasi):
        _doldur(conn, k, a)
    saat["an"] = saat["an"] - timedelta(days=1)  # son gün dahil açık
    _doldur(conn, k, a)
    anket.kapat(conn, a, "ogrenci")
    with pytest.raises(anket.AnketHatasi):
        _doldur(conn, _kisi(conn, ornek["ogr2_k"]), a)


def test_anonimlik_semada_ve_verisinde(conn, ornek, a):
    anket.dagit(conn, a, "ogrenci")
    _doldur(conn, _kisi(conn, ornek["ogr1_k"]), a, metin="gizli not")
    for t in ("anket_yanit", "anket_cevap"):
        sut = {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
        assert not sut & {"kullanici_id", "ogrenci_id", "okul_no", "zaman", "tarih", "gun", "oturum", "ip"}
    kid = ornek["ogr1_k"]
    tum = " ".join(str(tuple(r)) for t in ("anket_yanit", "anket_cevap") for r in conn.execute(f"SELECT * FROM {t}"))
    assert str(kid) not in tum.split() and "Ali" not in tum
    yid = conn.execute("SELECT id FROM anket_yanit").fetchone()[0]
    assert yid > 10**6  # sıralı değil, rastgele
    # katılım tablosunda sıra/saat bilgisi yok
    assert {r[1] for r in conn.execute("PRAGMA table_info(anket_katilim)")} == {"anket_id", "kullanici_id", "rol"}


def _yanitlar(conn, yeni_kullanici, aid, n, rol="ogrenci", baslangic=400, puan="4"):
    for k in _ogrenciler(conn, yeni_kullanici, n, "9-A", baslangic):
        _doldur(conn, _kisi(conn, k), aid, puan=puan, servis="1", metin=f"yorum {k}")


def test_kucuk_grup_sonuc_gizli(conn, ornek, a, yeni_kullanici):
    anket.dagit(conn, a, "ogrenci")
    _yanitlar(conn, yeni_kullanici, a, 4)
    oz = anket.katilim_ozeti(conn, a)[0]
    assert oz["yanit"] == 4 and oz["yeterli"] is False
    for s in anket.sonuc(conn, a):
        r = s["roller_sonuc"][0]
        assert r["gizli"] is True and "metinler" not in r and "ortalama" not in r and "secenekler" not in r


def test_esik_ve_toplamlar(conn, ornek, a, yeni_kullanici):
    anket.dagit(conn, a, "ogrenci")
    _yanitlar(conn, yeni_kullanici, a, 5)
    sonuc = {s["sira"]: s["roller_sonuc"][0] for s in anket.sonuc(conn, a)}
    assert sonuc[1]["ortalama"] == 4.0 and sonuc[1]["n"] == 5
    assert [x["sayi"] for x in sonuc[1]["dagilim"]] == [0, 0, 0, 5, 0]
    assert [(x["ad"], x["sayi"], x["yuzde"]) for x in sonuc[2]["secenekler"]] == [("Evet", 0, 0), ("Hayır", 5, 100)]
    assert len(sonuc[3]["metinler"]) == 5


def test_roller_ayri_sonuclanir(conn, ornek, a, yeni_kullanici):
    anket.dagit(conn, a, "ogrenci")
    anket.dagit(conn, a, "ogretmen")
    _yanitlar(conn, yeni_kullanici, a, 5, puan="2")
    s1 = anket.sonuc(conn, a)[0]["roller_sonuc"]
    assert [r["rol"] for r in s1] == ["ogrenci", "ogretmen"]
    assert s1[0]["ortalama"] == 2.0 and s1[1]["gizli"] is True and s1[1]["n"] == 0
    oz = {x["rol"]: x for x in anket.katilim_ozeti(conn, a)}
    assert oz["ogrenci"]["kitle"] == 7 and oz["ogrenci"]["yanit"] == 5  # 2 örnek + 5 yeni öğrenci
    assert oz["ogretmen"]["yanit"] == 0


def test_isteğe_bagli_soruda_az_cevap_gizli(conn, ornek, a, yeni_kullanici):
    anket.dagit(conn, a, "ogrenci")
    for i, k in enumerate(_ogrenciler(conn, yeni_kullanici, 6, "9-A", 500)):
        _doldur(conn, _kisi(conn, k), a, metin="yorum" if i < 3 else "")  # yalnızca 3 kişi yazdı
    metin = anket.sonuc(conn, a)[2]["roller_sonuc"][0]
    assert metin["n"] == 3 and metin["gizli"] is True and "metinler" not in metin


def test_liste_ve_taslak(conn, ornek, a):
    assert anket.anket_listesi(conn)[0]["taslak"] is True
    anket.dagit(conn, a, "ogretmen")
    satir = anket.anket_listesi(conn)[0]
    assert satir["taslak"] is False and satir["gruplar"] == [{"ad": "Öğretmenler", "acik": True}]
