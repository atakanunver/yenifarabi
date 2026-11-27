"""Atos'un sabit, parametreli liste ve özet sorguları."""

import dyk
import kulupler
import okul_sql


def _kaynaklar():
    import okul_bilgisi as bilgi

    dsn = bilgi._ayar().get("sql_dsn")
    if not dsn:
        raise okul_sql.SqlHatasi("SQL bağlantısı yapılandırılmamış.")
    tablolar = okul_sql.pg_tablolari(dsn)
    try:
        tablolar.update(okul_sql.sms_tablolari(bilgi.SMS_DB_YOLU))
    except okul_sql.SqlHatasi:
        pass  # Panodaki gibi, SMS rehberi yokken PG veli bilgileri kullanılır.
    tablolar.update(okul_sql.tc_tablosu(bilgi.TC_DIZINI))
    tablolar.update(bilgi._dosya_tablolari())
    tablolar.update(okul_sql.dyk_tablolari(dyk.yukle()))
    tablolar.update(okul_sql.kulup_tablolari(kulupler.yukle()))
    return okul_sql.ogretmen_tablosu(okul_sql.personel_esle(okul_sql.ogrenci_genis(tablolar)))


def _liste(baslik, sorgu, parametreler, tablolar):
    if tablolar is None:
        tablolar = _kaynaklar()
    sonuc = okul_sql.calistir(sorgu, tablolar, azami_satir=None, parametreler=parametreler)
    return {"baslik": baslik, "kolonlar": sonuc["kolonlar"], "satirlar": sonuc["satirlar"],
            "satir_sayisi": len(sonuc["satirlar"])}


def _tek_deger(sonuc, kolon, varsayilan):
    degerler = {satir[kolon] for satir in sonuc["satirlar"]}
    return degerler.pop() if len(degerler) == 1 else varsayilan


def get_sinif_listesi(sinif, sube=None, *, tablolar=None):
    sinif = str(sinif).strip()
    if sube:
        sinif += "-" + str(sube).strip()
    baslik = f"{sinif.upper()} Sınıf Listesi" if "-" in sinif else f"{sinif}. Sınıflar Listesi"
    return _liste(baslik, """
        SELECT okul_no AS "Okul No", ad_soyad AS "Ad Soyad", sinif AS "Sınıf"
        FROM v_sinif_listesi
        WHERE :sinif<>'' AND ara(sinif, :sinif) AND (length(sinif)=length(:sinif)
              OR substr(sinif, 1, instr(sinif, '-') - 1)=:sinif)
        ORDER BY sinif, CAST(okul_no AS INTEGER), ad_soyad""", {"sinif": sinif}, tablolar)


def get_dyk_listesi(ders=None, ogretmen_adi=None, *, tablolar=None):
    sonuc = _liste("DYK Listesi", """
        SELECT ders AS "Ders", ogretmen AS "Öğretmen", sinif_grubu AS "Sınıf Grubu",
               okul_no AS "Okul No", ad_soyad AS "Ad Soyad"
        FROM v_dyk_listesi
        WHERE (:ders IS NULL OR ara(ders, :ders)) AND (:ad IS NULL OR ara(ogretmen, :ad))
        ORDER BY ders, ogretmen, sinif_grubu, CAST(okul_no AS INTEGER), ad_soyad""",
        {"ders": ders, "ad": ogretmen_adi}, tablolar)
    if ders or ogretmen_adi:
        ad = _tek_deger(sonuc, 0 if ders else 1, ders or ogretmen_adi)
        sonuc["baslik"] = f"{ad} DYK Listesi"
    return sonuc


def get_kulup_bilgisi(kulup_adi=None, ogretmen_adi=None, *, tablolar=None):
    sonuc = _liste("Kulüp Üye Listesi", """
        SELECT kulup_ad AS "Kulüp", danisman AS "Danışman", okul_no AS "Okul No",
               ad_soyad AS "Ad Soyad", sinif AS "Sınıf", rol AS "Rol"
        FROM v_kulup_uyeleri
        WHERE (:kulup IS NULL OR ara(kulup_ad, :kulup)) AND (:ad IS NULL OR ara(danisman, :ad))
        ORDER BY kulup_ad, sinif, CAST(okul_no AS INTEGER), ad_soyad""",
        {"kulup": kulup_adi, "ad": ogretmen_adi}, tablolar)
    ad = _tek_deger(sonuc, 0, "Kulüp")
    sonuc["baslik"] = f"{ad} Üye Listesi"
    return sonuc


def get_ogretmen_listesi(brans=None, *, tablolar=None):
    sonuc = _liste("Öğretmen Listesi", """
        SELECT ad_soyad AS "Ad Soyad", brans AS "Branş", gorev AS "Görev", telefon AS "Telefon"
        FROM v_ogretmen_listesi
        WHERE (:brans IS NULL OR ara(brans, :brans)) ORDER BY ad_soyad, brans""",
        {"brans": brans}, tablolar)
    if brans:
        sonuc["baslik"] = f"{_tek_deger(sonuc, 1, brans)} Öğretmen Listesi"
    return sonuc


def get_ogrenci_ozet(okul_no_veya_ad, *, tablolar=None):
    aranan = str(okul_no_veya_ad).strip()
    return _liste("Öğrenci Özeti", """
        SELECT o.okul_no AS "Okul No", o.ad_soyad AS "Ad Soyad", o.sinif AS "Sınıf",
               o.anne_ad_soyad AS "Anne", o.anne_telefon AS "Anne Telefon",
               o.baba_ad_soyad AS "Baba", o.baba_telefon AS "Baba Telefon",
               (SELECT group_concat(ders, ', ') FROM (SELECT DISTINCT ders FROM v_dyk_listesi
                WHERE CAST(okul_no AS TEXT)=CAST(o.okul_no AS TEXT) ORDER BY ders)) AS "DYK",
               (SELECT group_concat(kulup_ad, ', ') FROM (SELECT DISTINCT kulup_ad FROM v_kulup_uyeleri
                WHERE CAST(okul_no AS TEXT)=CAST(o.okul_no AS TEXT) ORDER BY kulup_ad)) AS "Kulüp"
        FROM ogrenci_genis o
        WHERE CASE WHEN :numara THEN CAST(o.okul_no AS TEXT)=:aranan
                   ELSE :aranan<>'' AND ara(o.ad_soyad, :aranan) END
        ORDER BY o.sinif, CAST(o.okul_no AS INTEGER), o.ad_soyad""",
        {"numara": aranan.isdecimal(), "aranan": aranan}, tablolar)
