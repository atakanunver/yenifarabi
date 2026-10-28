-- osym veri tabanı (PostgreSQL, rol: osym). Kurşunlu Anadolu Lisesi ÖSYM/YKS okul raporları.
-- Uygulama: osym/venv/bin/python osym_yukle.py --sema   (CREATE ... IF NOT EXISTS)
-- Yalnızca yerel; öğrenci kimliği (TC, ad) içerir, buluta gitmez.

CREATE TABLE IF NOT EXISTS yukleme (
    id         serial PRIMARY KEY,
    yil        integer NOT NULL,          -- raporun başlığındaki "<yıl> YILI SON SINIF ÖĞRENCİLERİ"
    rapor      text    NOT NULL CHECK (rapor IN ('yerlestirme', 'yerlestirme_puani', 'ham_puan', 'dogru_yanlis_tyt', 'dogru_yanlis_ayt')),
    dosya      text    NOT NULL,          -- kaynak dosya adı (klasör yolu olmadan)
    dosya_zamani timestamptz,             -- kaynak dosyanın değişme zamanı
    sha256     text    NOT NULL,
    satir      integer NOT NULL,          -- yüklenen veri satırı
    birincil   boolean NOT NULL DEFAULT false,  -- aynı (yil, rapor) için en yeni dosya
    yuklenme   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (sha256)
);

-- YKS (ÖSYS) YERLEŞTİRME SONUÇLARI
CREATE TABLE IF NOT EXISTS yerlestirme (
    yukleme_id    integer NOT NULL REFERENCES yukleme(id) ON DELETE CASCADE,
    yil           integer NOT NULL,
    tc_kimlik     text    NOT NULL,
    ad_soyad      text    NOT NULL,
    donem         text,
    program_kodu  text,
    program_adi   text,
    universite    text,
    fakulte       text,
    tercih_sirasi integer,
    puan_turu     text,
    puan          numeric,
    obp           numeric,
    meteb         text,
    kont_turu     text,
    ek_puan       text,
    ek_puan_2     text
);
CREATE INDEX IF NOT EXISTS yerlestirme_yil ON yerlestirme (yil);
CREATE INDEX IF NOT EXISTS yerlestirme_tc ON yerlestirme (tc_kimlik);

-- YKS YERLEŞTİRME PUANLARI ve BAŞARI SIRLARI (rapor='yerlestirme_puani') ile
-- YKS PUANLAR ve BAŞARI SIRLARI (rapor='ham_puan'); uzun biçim: öğrenci × puan türü
CREATE TABLE IF NOT EXISTS yks_puan (
    yukleme_id     integer NOT NULL REFERENCES yukleme(id) ON DELETE CASCADE,
    yil            integer NOT NULL,
    rapor          text    NOT NULL,
    tc_kimlik      text    NOT NULL,
    ad_soyad       text    NOT NULL,
    puan_turu      text    NOT NULL,      -- TYT, SAYISAL, SÖZEL, EŞİT AĞIRLIK, YABANCI DİL
    puan           numeric,
    basari_sirasi  integer
);
CREATE INDEX IF NOT EXISTS yks_puan_yil ON yks_puan (yil, rapor);
CREATE INDEX IF NOT EXISTS yks_puan_tc ON yks_puan (tc_kimlik);

-- TYT / AYT TESTLERİ BAZINDA DOĞRU-YANLIŞ SAYILARI; uzun biçim: öğrenci × test
CREATE TABLE IF NOT EXISTS dogru_yanlis (
    yukleme_id integer NOT NULL REFERENCES yukleme(id) ON DELETE CASCADE,
    yil        integer NOT NULL,
    sinav      text    NOT NULL,          -- TYT, AYT, YDT (dosyadaki üst başlık)
    tc_kimlik  text    NOT NULL,
    ad_soyad   text    NOT NULL,
    test       text    NOT NULL,
    dogru      numeric,
    yanlis     numeric,
    bos        numeric,
    ham        numeric
);
CREATE INDEX IF NOT EXISTS dogru_yanlis_yil ON dogru_yanlis (yil, sinav);
CREATE INDEX IF NOT EXISTS dogru_yanlis_tc ON dogru_yanlis (tc_kimlik);

-- SON 15 YIL YERLEŞTİRME SONUÇLARI.docx: okulun yıllık özet tablosu
CREATE TABLE IF NOT EXISTS genel_istatistik (
    yil                 integer PRIMARY KEY,   -- ÖSYM yılı (ör. 2026)
    ogretim_yili        text,
    son_sinif           integer,
    basvuran            integer,
    kazanan             integer,
    tercih_yapan        integer,
    lisans              integer,
    onlisans_sinavsiz   integer,
    onlisans_sinavli    integer,               -- YGS/TYT ile
    aof                 integer,
    toplam_yerlesen     integer,
    kaynak              text
);

-- SON 5 YIL YERLESEN <yıl>.xlsx: okulun kendi özet tablosu (mezun / sınava giren / yerleşen)
CREATE TABLE IF NOT EXISTS ozet_son5 (
    yil           integer PRIMARY KEY,
    mezun         integer,
    sinava_giren  integer,
    yerlesen      integer,
    oran          numeric,     -- dosyadaki "Oran (Mezun-Yerleşen)" olduğu gibi
    kaynak        text
);

-- Mezunlar: ÖSYM raporlarındaki her kişi için tek satır (TC anahtar). Yeniden yüklemede ad/yıl/yerleşme
-- güncellenir, telefon* alanlarına dokunulmaz (ulaşmak için elle/başka kaynaktan doldurulur).
CREATE TABLE IF NOT EXISTS mezun (
    tc_kimlik        text PRIMARY KEY,
    ad_soyad         text NOT NULL,
    mezuniyet_yili   integer NOT NULL,   -- ÖSYM raporunda ilk göründüğü "son sınıf" yılı
    yerlesen_program text,               -- en son yerleştirme: "program - üniversite"
    yerlesme_yili    integer,
    telefon          text,
    telefon_kaynagi  text,
    not_             text,
    guncelleme       timestamptz NOT NULL DEFAULT now()
);

-- Her (yil, rapor) için yalnızca en yeni dosya
CREATE OR REPLACE VIEW yerlestirme_guncel AS
    SELECT y.* FROM yerlestirme y JOIN yukleme u ON u.id = y.yukleme_id WHERE u.birincil;
CREATE OR REPLACE VIEW yks_puan_guncel AS
    SELECT p.* FROM yks_puan p JOIN yukleme u ON u.id = p.yukleme_id WHERE u.birincil;
CREATE OR REPLACE VIEW dogru_yanlis_guncel AS
    SELECT d.* FROM dogru_yanlis d JOIN yukleme u ON u.id = d.yukleme_id WHERE u.birincil;
