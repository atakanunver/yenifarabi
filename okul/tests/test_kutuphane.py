"""Kütüphane: eser/nüsha kaydı, ISBN/demirbaş doğrulama, ödünç/iade, limit, çift okutma, eşzamanlılık, geri alma."""

import threading
from datetime import date, timedelta

import db
import kutuphane
import pytest

ORNEK = {
    "isbn": "9786052793978",
    "demirbas": "03244",
    "baski_yili": "2025",
    "baslik": "Bahadır : Sirius’un seçimi",
    "basim_sayisi": "3.Basim",
    "yayinevi": "Can Yayınları",
}


def test_ornek_kayit_alanlari_korur(conn):
    kutuphane.nusha_ekle(conn, **ORNEK)
    n = kutuphane.demirbas_bul(conn, "03244")
    assert n["isbn"] == "9786052793978"
    assert n["demirbas"] == "03244"  # baştaki sıfır korunur
    assert n["baski_yili"] == 2025
    assert n["baslik"] == "Bahadır : Sirius’un seçimi"
    assert n["basim_sayisi"] == "3.Basim"
    assert n["yayinevi"] == "Can Yayınları"
    assert n["durum"] == "saglam"
    assert kutuphane.demirbas_bul(conn, "3244") is None


def test_ayni_isbn_ikinci_nusha_ayni_eser(conn):
    a = kutuphane.nusha_ekle(conn, **ORNEK)
    b = kutuphane.nusha_ekle(conn, **{**ORNEK, "demirbas": "03245", "isbn": "978-605-279-397-8", "basim_sayisi": "1.Basim"})
    assert a != b
    assert conn.execute("SELECT COUNT(*) FROM kitap").fetchone()[0] == 1
    assert kutuphane.demirbas_bul(conn, "03245")["basim_sayisi"] == "1.Basim"


def test_isbnsiz_kitap_baslik_yayineviyle_eslenir(conn):
    kutuphane.nusha_ekle(conn, demirbas="1", baslik="Nutuk", yayinevi="Türk Tarih Kurumu")
    kutuphane.nusha_ekle(conn, demirbas="2", baslik="  NUTUK ", yayinevi="türk tarih kurumu")
    kutuphane.nusha_ekle(conn, demirbas="3", baslik="Nutuk", yayinevi="Başka Yayınevi")
    assert conn.execute("SELECT COUNT(*) FROM kitap").fetchone()[0] == 2


def test_cift_demirbas_reddedilir_ve_yarim_kayit_kalmaz(conn):
    kutuphane.nusha_ekle(conn, **ORNEK)
    with pytest.raises(kutuphane.KutuphaneHatasi) as e:
        kutuphane.nusha_ekle(conn, **{**ORNEK, "isbn": None, "baslik": "Başka"})
    assert e.value.kod == 409
    # Hata, yeni eser kaydını da geri almalı.
    assert conn.execute("SELECT COUNT(*) FROM kitap").fetchone()[0] == 1


@pytest.mark.parametrize(
    "alan,deger",
    [("isbn", "9786052793979"), ("isbn", "12345"), ("demirbas", ""), ("demirbas", "03<b>"),
     ("baslik", "  "), ("baski_yili", "iki bin"), ("baski_yili", "3000")],
)
def test_gecersiz_girdi(conn, alan, deger):
    with pytest.raises(kutuphane.KutuphaneHatasi):
        kutuphane.nusha_ekle(conn, **{**ORNEK, alan: deger})
    assert conn.execute("SELECT COUNT(*) FROM nusha").fetchone()[0] == 0


def test_isbn10_ve_bos_isbn():
    assert kutuphane.isbn_normalize("0-306-40615-2") == "0306406152"
    assert kutuphane.isbn_normalize("") is None
    assert kutuphane.isbn_normalize(" - ") is None


def test_islem_yetkisi_yalniz_yonetici_ve_yetkili_ogretmen(conn, yeni_kullanici):
    yon = yeni_kullanici(conn, "yonetici", "Yön", "yon")
    ogr = yeni_kullanici(conn, "ogretmen", "Öğr", "ogr")
    ogrenci = yeni_kullanici(conn, "ogrenci", "Öğrenci", "ogrenci")
    kisi = lambda k: conn.execute("SELECT * FROM kullanici WHERE id = ?", (k,)).fetchone()
    assert kutuphane.islem_yetkisi(conn, kisi(yon))
    assert not kutuphane.islem_yetkisi(conn, kisi(ogr))
    assert not kutuphane.islem_yetkisi(conn, kisi(ogrenci))
    conn.execute("INSERT INTO kutuphane_yetkili (kullanici_id, olusturma) VALUES (?, '2026-11-06 10:00:00')", (ogr,))
    assert kutuphane.islem_yetkisi(conn, kisi(ogr))


def _odunc_ortami(conn, yeni_kullanici):
    gorevli = yeni_kullanici(conn, "yonetici", "Görevli", "gorevli")
    conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif) VALUES (101, 'Ali Veli', '9-A')")
    conn.commit()
    ogr = conn.execute("SELECT id FROM ogrenci WHERE okul_no = 101").fetchone()[0]
    nushalar = [kutuphane.nusha_ekle(conn, **{**ORNEK, "demirbas": f"0324{i}"}) for i in range(4)]
    return gorevli, ogr, nushalar


def test_isbn_okutunca_nushalar_ve_durumlari(conn, yeni_kullanici, saat):
    gorevli, ogr, n = _odunc_ortami(conn, yeni_kullanici)
    kutuphane.odunc_ver(conn, n[1], ogr, gorevli)
    liste = kutuphane.kod_coz(conn, "978-605-279-397-8")["isbn"]
    assert [x["demirbas"] for x in liste] == ["03240", "03241", "03242", "03243"]
    assert [x["oduncte"] for x in liste] == [False, True, False, False]


def test_odunc_ver_ve_iade_gecikmesiz(conn, yeni_kullanici, saat):
    gorevli, ogr, n = _odunc_ortami(conn, yeni_kullanici)
    oid = kutuphane.odunc_ver(conn, n[0], ogr, gorevli)
    k = kutuphane.aktif_odunc(conn, n[0])
    assert k["id"] == oid and k["ad_soyad"] == "Ali Veli" and k["son_tarih"] == "2026-10-26"  # 14 gün
    saat["an"] += timedelta(days=14)  # son gün teslim gecikme sayılmaz
    sonuc = kutuphane.iade_al(conn, n[0], gorevli)
    assert sonuc["iade"] and sonuc["gecikme_gun"] == 0
    assert kutuphane.aktif_odunc(conn, n[0]) is None
    kutuphane.odunc_ver(conn, n[0], ogr, gorevli)  # nüsha yeniden verilebilir
    assert conn.execute("SELECT COUNT(*) FROM odunc").fetchone()[0] == 2  # geçmiş silinmez


def test_gecikme_hesaplanir(conn, yeni_kullanici, saat):
    gorevli, ogr, n = _odunc_ortami(conn, yeni_kullanici)
    kutuphane.odunc_ver(conn, n[0], ogr, gorevli)
    saat["an"] += timedelta(days=17)
    assert kutuphane.aktif_odunc(conn, n[0])["gecikme_gun"] == 3
    assert kutuphane.iade_al(conn, n[0], gorevli)["gecikme_gun"] == 3


def test_cift_okutma_tek_islem(conn, yeni_kullanici, saat):
    gorevli, ogr, n = _odunc_ortami(conn, yeni_kullanici)
    kutuphane.odunc_ver(conn, n[0], ogr, gorevli)
    with pytest.raises(kutuphane.KutuphaneHatasi) as e:
        kutuphane.odunc_ver(conn, n[0], ogr, gorevli)
    assert e.value.kod == 409
    kutuphane.iade_al(conn, n[0], gorevli)
    with pytest.raises(kutuphane.KutuphaneHatasi):
        kutuphane.iade_al(conn, n[0], gorevli)
    assert conn.execute("SELECT COUNT(*) FROM odunc").fetchone()[0] == 1


def test_ogrenci_limiti(conn, yeni_kullanici, saat):
    gorevli, ogr, n = _odunc_ortami(conn, yeni_kullanici)
    kutuphane.odunc_ver(conn, n[0], ogr, gorevli)
    kutuphane.odunc_ver(conn, n[1], ogr, gorevli)
    with pytest.raises(kutuphane.KutuphaneHatasi, match="2 kitabı"):
        kutuphane.odunc_ver(conn, n[2], ogr, gorevli)
    kutuphane.iade_al(conn, n[0], gorevli)
    kutuphane.odunc_ver(conn, n[2], ogr, gorevli)


def test_hasarli_nusha_ve_bilinmeyen_ogrenci_verilmez(conn, yeni_kullanici, saat):
    gorevli, ogr, n = _odunc_ortami(conn, yeni_kullanici)
    conn.execute("UPDATE nusha SET durum = 'hasarli' WHERE id = ?", (n[0],))
    conn.commit()
    with pytest.raises(kutuphane.KutuphaneHatasi, match="hasarlı"):
        kutuphane.odunc_ver(conn, n[0], ogr, gorevli)
    with pytest.raises(kutuphane.KutuphaneHatasi) as e:
        kutuphane.odunc_ver(conn, n[1], 9999, gorevli)
    assert e.value.kod == 404
    assert conn.execute("SELECT COUNT(*) FROM odunc").fetchone()[0] == 0


def test_iki_cihaz_ayni_anda_ayni_nusha(conn, yeni_kullanici, saat):
    """Laptop ve telefon aynı nüshayı aynı anda verirse yalnızca biri başarılı olur."""
    gorevli, ogr, n = _odunc_ortami(conn, yeni_kullanici)
    conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif) VALUES (102, 'Ayşe Kaya', '9-A')")
    conn.commit()
    ogr2 = conn.execute("SELECT id FROM ogrenci WHERE okul_no = 102").fetchone()[0]
    sonuc, engel = [], threading.Barrier(2)

    def ver(o):
        c = db.baglanti()
        try:
            engel.wait()
            kutuphane.odunc_ver(c, n[0], o, gorevli)
            sonuc.append("tamam")
        except kutuphane.KutuphaneHatasi as e:
            sonuc.append(e.kod)
        finally:
            c.close()

    t = [threading.Thread(target=ver, args=(o,)) for o in (ogr, ogr2)]
    for x in t:
        x.start()
    for x in t:
        x.join()
    assert sorted(map(str, sonuc)) == ["409", "tamam"]
    assert conn.execute("SELECT COUNT(*) FROM odunc WHERE iade IS NULL").fetchone()[0] == 1


def test_gecikme_gun_saf():
    assert kutuphane.gecikme_gun("2026-10-26", date(2026, 10, 26)) == 0
    assert kutuphane.gecikme_gun("2026-10-26", date(2026, 10, 27)) == 1


def test_geri_al_tablolari_siler():
    from scripts import geri_al

    assert all(t in geri_al.GERI[40] for t in ("odunc", "nusha", "kitap", "kutuphane_yetkili"))


def _ogrenci(conn, no, ad):
    conn.execute("INSERT INTO ogrenci (okul_no, ad_soyad, sinif) VALUES (?, ?, '9-A')", (no, ad))
    conn.commit()
    return conn.execute("SELECT id FROM ogrenci WHERE okul_no = ?", (no,)).fetchone()[0]


def test_ayarlar_panelden_degisir_ve_uygulanir(conn, yeni_kullanici, saat):
    gorevli, ogr, n = _odunc_ortami(conn, yeni_kullanici)
    assert kutuphane.ayarlar(conn) == {"odunc_gun": 14, "ogrenci_limit": 2, "hatirlatma": 1}
    kutuphane.ayar_kaydet(conn, {"odunc_gun": "7", "ogrenci_limit": "3", "hatirlatma": "0"})
    oid = kutuphane.odunc_ver(conn, n[0], ogr, gorevli)
    assert kutuphane.odunc_kaydi(conn, oid)["son_tarih"] == "2026-10-19"
    kutuphane.odunc_ver(conn, n[1], ogr, gorevli)
    kutuphane.odunc_ver(conn, n[2], ogr, gorevli)  # limit 3
    for kotu in ({"odunc_gun": 0}, {"ogrenci_limit": 11}, {"odunc_gun": "x"}):
        with pytest.raises(kutuphane.KutuphaneHatasi):
            kutuphane.ayar_kaydet(conn, {**kutuphane.AYAR_VARSAYILAN, **kotu})


def test_kod_coz_isbn_ve_demirbas_karismaz(conn):
    kutuphane.nusha_ekle(conn, **ORNEK)
    kutuphane.nusha_ekle(conn, demirbas="9786052793978", baslik="Garip demirbaş")  # ISBN gibi görünen demirbaş
    c = kutuphane.kod_coz(conn, "9786052793978")
    assert [x["demirbas"] for x in c["isbn"]] == ["03244"]
    assert [x["baslik"] for x in c["demirbas"]] == ["Garip demirbaş"]
    e = kutuphane.kod_coz(conn, "KTP-03244")  # bizim QR etiketi: yalnızca demirbaş
    assert [x["demirbas"] for x in e["demirbas"]] == ["03244"] and e["isbn"] == []
    assert kutuphane.kod_coz(conn, "KTP-3244")["demirbas"] == []  # sıfır korunur, 3244 ≠ 03244
    assert kutuphane.kod_coz(conn, "<script>") == {"demirbas": [], "isbn": [], "isbn_kodu": None}


def test_ogrenci_ara_no_ve_ad(conn, yeni_kullanici):
    _ogrenci(conn, 101, "Ali Veli")
    _ogrenci(conn, 1015, "Şükrü Işık")
    assert [x["okul_no"] for x in kutuphane.ogrenci_ara(conn, "101")] == [101, 1015]
    assert [x["ad_soyad"] for x in kutuphane.ogrenci_ara(conn, "şükrü ışı")] == ["Şükrü Işık"]
    assert [x["ad_soyad"] for x in kutuphane.ogrenci_ara(conn, "ŞÜKRÜ")] == ["Şükrü Işık"]
    assert kutuphane.ogrenci_ara(conn, "") == []


def test_katalog_musaitlik(conn, yeni_kullanici, saat):
    gorevli, ogr, n = _odunc_ortami(conn, yeni_kullanici)
    kutuphane.odunc_ver(conn, n[0], ogr, gorevli)
    kutuphane.nusha_durum_ayarla(conn, n[1], "kayip")
    k = kutuphane.katalog(conn, "sirius")
    assert len(k) == 1 and k[0]["nusha"] == 4 and k[0]["rafta"] == 2 and k[0]["oduncte"] == 1
    assert kutuphane.katalog(conn, "yok böyle") == []


def test_ayirtma_sirasi_ve_iade_sonrasi_ayrilir(conn, yeni_kullanici, saat):
    gorevli = yeni_kullanici(conn, "yonetici", "Görevli", "gorevli")
    a, b, c = _ogrenci(conn, 1, "Ali"), _ogrenci(conn, 2, "Banu"), _ogrenci(conn, 3, "Cem")
    nid = kutuphane.nusha_ekle(conn, **ORNEK)
    kitap = kutuphane.demirbas_bul(conn, "03244")["kitap_id"]
    with pytest.raises(kutuphane.KutuphaneHatasi, match="rafta"):
        kutuphane.ayirt(conn, kitap, b)  # rafta varken ayırtılmaz
    kutuphane.odunc_ver(conn, nid, a, gorevli)
    with pytest.raises(kutuphane.KutuphaneHatasi, match="sende"):
        kutuphane.ayirt(conn, kitap, a)
    kutuphane.ayirt(conn, kitap, b)
    kutuphane.ayirt(conn, kitap, c)
    with pytest.raises(kutuphane.KutuphaneHatasi, match="zaten ayırttın"):
        kutuphane.ayirt(conn, kitap, c)
    assert [x["sira"] for x in kutuphane.ayirtmalar(conn, c)] == [2]
    iade = kutuphane.iade_al(conn, nid, gorevli)
    assert iade["ayrilan"]["ad_soyad"] == "Banu"  # personel: rafa koyma, ayır
    with pytest.raises(kutuphane.KutuphaneHatasi, match="Banu için ayrıldı"):
        kutuphane.odunc_ver(conn, nid, c, gorevli)
    assert kutuphane.katalog(conn)[0]["rafta"] == 0
    kutuphane.odunc_ver(conn, nid, b, gorevli)
    assert kutuphane.ayirtmalar(conn, b) == []  # alınınca kapanır
    assert [x["sira"] for x in kutuphane.ayirtmalar(conn, c)] == [1]


def test_hazir_ayirtma_suresi_dolunca_siradakine_gecer(conn, yeni_kullanici, saat):
    gorevli = yeni_kullanici(conn, "yonetici", "Görevli", "gorevli")
    a, b, c = _ogrenci(conn, 1, "Ali"), _ogrenci(conn, 2, "Banu"), _ogrenci(conn, 3, "Cem")
    nid = kutuphane.nusha_ekle(conn, **ORNEK)
    kitap = kutuphane.demirbas_bul(conn, "03244")["kitap_id"]
    kutuphane.odunc_ver(conn, nid, a, gorevli)
    kutuphane.ayirt(conn, kitap, b)
    kutuphane.ayirt(conn, kitap, c)
    kutuphane.iade_al(conn, nid, gorevli)
    saat["an"] += timedelta(days=kutuphane.HAZIR_GUN, minutes=1)
    durum = {x["ad_soyad"]: x["durum"] for x in kutuphane.ayirtmalar(conn)}
    assert durum == {"Banu": "hazir", "Cem": "bekliyor"}  # liste okuması yazmaz; temizlik ayrı
    kutuphane.ayirtma_temizle(conn)
    assert {x["ad_soyad"]: x["durum"] for x in kutuphane.ayirtmalar(conn)} == {"Cem": "hazir"}


def test_ayirtma_iptal_ve_limit(conn, yeni_kullanici, saat):
    gorevli = yeni_kullanici(conn, "yonetici", "Görevli", "gorevli")
    a, b = _ogrenci(conn, 1, "Ali"), _ogrenci(conn, 2, "Banu")
    kitaplar = []
    for i in range(3):
        nid = kutuphane.nusha_ekle(conn, demirbas=f"9{i}", baslik=f"Kitap {i}")
        kutuphane.odunc_ver(conn, nid, a, gorevli) if i < 2 else kutuphane.odunc_ver(conn, nid, _ogrenci(conn, 9, "X"), gorevli)
        kitaplar.append(kutuphane.demirbas_bul(conn, f"9{i}")["kitap_id"])
    kutuphane.ayirt(conn, kitaplar[0], b)
    kutuphane.ayirt(conn, kitaplar[1], b)
    with pytest.raises(kutuphane.KutuphaneHatasi, match="En çok"):
        kutuphane.ayirt(conn, kitaplar[2], b)
    aid = kutuphane.ayirtmalar(conn, b)[0]["id"]
    with pytest.raises(kutuphane.KutuphaneHatasi):
        kutuphane.ayirtma_iptal(conn, aid, a)  # başkasının ayırtması
    kutuphane.ayirtma_iptal(conn, aid, b)
    kutuphane.ayirt(conn, kitaplar[2], b)


def test_kutuphanem_hatirlatma_iki_gun_once(conn, yeni_kullanici, saat):
    gorevli, ogr, n = _odunc_ortami(conn, yeni_kullanici)
    kutuphane.odunc_ver(conn, n[0], ogr, gorevli)
    assert kutuphane.kutuphanem(conn, ogr)["aktif"][0]["uyari"] is False
    saat["an"] += timedelta(days=12)  # 2 gün kaldı
    k = kutuphane.kutuphanem(conn, ogr)
    assert k["aktif"][0]["kalan_gun"] == 2 and k["aktif"][0]["uyari"] is True
    kutuphane.ayar_kaydet(conn, {**kutuphane.AYAR_VARSAYILAN, "hatirlatma": 0})
    assert kutuphane.kutuphanem(conn, ogr)["aktif"][0]["uyari"] is False
    kutuphane.iade_al(conn, n[0], gorevli)
    k = kutuphane.kutuphanem(conn, ogr)
    assert k["aktif"] == [] and len(k["gecmis"]) == 1


def _xlsx(satirlar, demirbas_bicim=None):
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    for s in satirlar:
        wb.active.append(s)
    if demirbas_bicim:
        for c in wb.active["B"][1:]:
            c.number_format = demirbas_bicim
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_excel_ice_aktar(conn):
    basliks = ["ISBN", "Demirbas", "BaskiYili", "Baslik", "BasimSayisi", "Yayinevi"]
    veri = _xlsx([basliks, ["9786052793978", "03244", 2025, "Bahadır : Sirius’un seçimi", "3.Basim", "Can Yayınları"],
                  [9786052793978, 3245, 2024, "Bahadır : Sirius’un seçimi", "1.Basim", "Can Yayınları"],
                  ["123", "03246", 2025, "Kötü ISBN", "", ""], [None, "03244", None, "Tekrar", None, None], [None] * 6])
    s = kutuphane.ice_aktar(conn, veri)
    assert s["eklenen"] == 3 and [n for n, _ in s["atlanan"]] == [5] and s["sifir_supheli"] == 1
    assert s["isbn_gecersiz"] == [(4, "123")] and kutuphane.demirbas_bul(conn, "03246")["isbn"] is None
    assert kutuphane.demirbas_bul(conn, "03244")["basim_sayisi"] == "3.Basim"
    assert kutuphane.ice_aktar(conn, veri)["eklenen"] == 0  # ikinci yükleme bir şey eklemez
    s = kutuphane.ice_aktar(conn, _xlsx([basliks, [None, 7, None, "Sıfırlı", None, None]], demirbas_bicim="00000"))
    assert s["eklenen"] == 1 and kutuphane.demirbas_bul(conn, "00007")
    with pytest.raises(kutuphane.KutuphaneHatasi, match="Eksik sütun"):
        kutuphane.ice_aktar(conn, _xlsx([["ISBN", "Yazar"]]))
    with pytest.raises(kutuphane.KutuphaneHatasi):
        kutuphane.ice_aktar(conn, b"bozuk")


def test_rapor_ve_excel(conn, yeni_kullanici, saat):
    import io

    import openpyxl

    gorevli, ogr, n = _odunc_ortami(conn, yeni_kullanici)
    kutuphane.nusha_ekle(conn, demirbas="77", baslik="Hiç alınmayan")
    kutuphane.odunc_ver(conn, n[0], ogr, gorevli)
    saat["an"] += timedelta(days=20)
    r = kutuphane.rapor(conn)
    assert (r["eser"], r["nusha"], r["oduncte"], r["geciken"], r["rafta"]) == (2, 5, 1, 1, 4)
    assert [x["baslik"] for x in r["hic_alinmamis"]] == ["Hiç alınmayan"]
    assert r["siniflar"] == [("9-A", 1)]
    wb = openpyxl.load_workbook(io.BytesIO(kutuphane.rapor_xlsx(conn)))
    assert "Nüshalar" in wb.sheetnames and wb["Nüshalar"]["A2"].value in {"03240", "77"}


def test_etiket_araligi_sifirlari_korur(conn):
    for d in ("03240", "03241", "03250", "77"):
        kutuphane.nusha_ekle(conn, demirbas=d, baslik="K")
    assert [n["demirbas"] for n in kutuphane.etiket_nushalari(conn, "3240", "3245")] == ["03240", "03241"]
    assert [n["demirbas"] for n in kutuphane.etiket_nushalari(conn, "03250")] == ["03250"]
    assert kutuphane.etiket_nushalari(conn) == []
