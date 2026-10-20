"""okul.db — şema, sürümlü göç (PRAGMA user_version), bağlantı."""

import sqlite3

from ayarlar import AYAR

SEMA_V1 = """
CREATE TABLE kullanici (
    id              INTEGER PRIMARY KEY,
    rol             TEXT NOT NULL CHECK (rol IN ('ogrenci','veli','ogretmen','yonetici')),
    ad_soyad        TEXT NOT NULL,
    kullanici_adi   TEXT UNIQUE,
    telefon         TEXT,
    sifre_hash      TEXT,
    sifre_degismeli INTEGER NOT NULL DEFAULT 1,
    aktif           INTEGER NOT NULL DEFAULT 1,
    olusturma       TEXT NOT NULL
);
CREATE UNIQUE INDEX kullanici_veli_telefon ON kullanici(telefon) WHERE rol = 'veli';

CREATE TABLE ogrenci (
    id            INTEGER PRIMARY KEY,
    okul_no       INTEGER NOT NULL UNIQUE,
    ad_soyad      TEXT NOT NULL,
    sinif         TEXT NOT NULL,
    kullanici_id  INTEGER UNIQUE REFERENCES kullanici(id)
);

CREATE TABLE veli_ogrenci (
    veli_id     INTEGER NOT NULL REFERENCES kullanici(id),
    ogrenci_id  INTEGER NOT NULL REFERENCES ogrenci(id),
    yakinlik    TEXT,
    PRIMARY KEY (veli_id, ogrenci_id)
);

CREATE TABLE ogretmen_gorev (
    ogretmen_id  INTEGER NOT NULL REFERENCES kullanici(id),
    sinif        TEXT NOT NULL,
    ders         TEXT NOT NULL,
    PRIMARY KEY (ogretmen_id, sinif, ders)
);

CREATE TABLE duyuru (
    id         INTEGER PRIMARY KEY,
    yazar_id   INTEGER NOT NULL REFERENCES kullanici(id),
    baslik     TEXT NOT NULL,
    metin      TEXT NOT NULL,
    hedef_tur  TEXT NOT NULL CHECK (hedef_tur IN ('okul','sinif','rol')),
    hedef      TEXT,
    yayin      TEXT NOT NULL,
    bitis      TEXT
);

CREATE TABLE odev (
    id           INTEGER PRIMARY KEY,
    ogretmen_id  INTEGER NOT NULL REFERENCES kullanici(id),
    sinif        TEXT NOT NULL,
    ders         TEXT NOT NULL,
    tur          TEXT NOT NULL CHECK (tur IN ('klasik','test')),
    baslik       TEXT NOT NULL,
    aciklama     TEXT NOT NULL DEFAULT '',
    teslim       TEXT NOT NULL,
    olusturma    TEXT NOT NULL
);

CREATE TABLE odev_soru (
    id       INTEGER PRIMARY KEY,
    odev_id  INTEGER NOT NULL REFERENCES odev(id) ON DELETE CASCADE,
    sira     INTEGER NOT NULL,
    metin    TEXT NOT NULL,
    siklar   TEXT NOT NULL,
    dogru    INTEGER NOT NULL,
    kazanim  TEXT NOT NULL DEFAULT '',
    kaynak   TEXT NOT NULL DEFAULT 'elle'
);

CREATE TABLE odev_teslim (
    odev_id     INTEGER NOT NULL REFERENCES odev(id) ON DELETE CASCADE,
    ogrenci_id  INTEGER NOT NULL REFERENCES ogrenci(id),
    durum       TEXT NOT NULL CHECK (durum IN ('yapti','tamam')),
    puan        INTEGER,
    cevaplar    TEXT,
    zaman       TEXT NOT NULL,
    PRIMARY KEY (odev_id, ogrenci_id)
);

CREATE TABLE oturum (
    token_hash    TEXT PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    olusturma     TEXT NOT NULL,
    son_gorulme   TEXT NOT NULL,
    cihaz         TEXT
);

CREATE TABLE sms_kod (
    telefon         TEXT PRIMARY KEY,
    kod_hash        TEXT NOT NULL,
    son_gecerlilik  TEXT NOT NULL,
    deneme          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE giris_deneme (
    anahtar   TEXT PRIMARY KEY,
    sayac     INTEGER NOT NULL,
    son_hata  TEXT NOT NULL
);

CREATE TABLE erisim_log (
    id            INTEGER PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL,
    eylem         TEXT NOT NULL,
    ogrenci_id    INTEGER,
    zaman         TEXT NOT NULL,
    ip            TEXT
);

CREATE TABLE aktarim_taslak (
    id         TEXT PRIMARY KEY,
    tur        TEXT NOT NULL,
    veri       TEXT NOT NULL,
    olusturma  TEXT NOT NULL
);
"""

# v2 (2026-10-10): vesikalık fotoğraf, yıllık plan, sınav takvimi. Yalnızca ekleme; mevcut veriye dokunmaz.
SEMA_V2 = """
ALTER TABLE kullanici ADD COLUMN foto TEXT;

CREATE TABLE yillik_plan (
    id           INTEGER PRIMARY KEY,
    ogretmen_id  INTEGER NOT NULL REFERENCES kullanici(id),
    sinif        TEXT NOT NULL,
    ders         TEXT NOT NULL,
    dosya_adi    TEXT NOT NULL,
    depo_adi     TEXT NOT NULL,
    tur          TEXT NOT NULL,
    boyut        INTEGER NOT NULL,
    yukleme      TEXT NOT NULL,
    UNIQUE (ogretmen_id, sinif, ders)
);

CREATE TABLE sinav (
    id         INTEGER PRIMARY KEY,
    yazar_id   INTEGER NOT NULL REFERENCES kullanici(id),
    tur        TEXT NOT NULL CHECK (tur IN ('yazili','deneme')),
    baslik     TEXT NOT NULL,
    sinif      TEXT,
    ders       TEXT,
    duzeyler   TEXT NOT NULL DEFAULT '',
    tarih      TEXT NOT NULL,
    ders_no    INTEGER,
    aciklama   TEXT NOT NULL DEFAULT '',
    olusturma  TEXT NOT NULL
);
CREATE INDEX sinav_tarih ON sinav(tarih);
"""

# v3 (2026-10-11): Soru Maratonu. Soru metni/şıklar oyun başlarken kopyalanır (havuz değişse de oyun tutarlı).
# maraton_soru.cevap: NULL = bekliyor, 0..n = şık, -1 = süre doldu, -2 = maraton yarıda bırakıldı.
SEMA_V3 = """
CREATE TABLE maraton (
    id            INTEGER PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    sinif         TEXT NOT NULL,
    duzey         INTEGER NOT NULL,
    ders          TEXT NOT NULL,
    basla         TEXT NOT NULL,
    bitis         TEXT,
    puan          INTEGER NOT NULL DEFAULT 0,
    dogru         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX maraton_kullanici_basla ON maraton(kullanici_id, basla);

CREATE TABLE maraton_soru (
    maraton_id    INTEGER NOT NULL REFERENCES maraton(id) ON DELETE CASCADE,
    sira          INTEGER NOT NULL,
    soru_id       INTEGER NOT NULL,
    soru          TEXT NOT NULL,
    secenekler    TEXT NOT NULL,
    dogru_index   INTEGER NOT NULL,
    konu          TEXT,
    kaynak        TEXT,
    gosterim      TEXT,
    cevap         INTEGER,
    cevap_zamani  TEXT,
    puan          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (maraton_id, sira)
);
CREATE INDEX maraton_soru_soru ON maraton_soru(soru_id);
"""

# Kullanım analitiği (yalnızca sayaç): içerik, IP, cihaz bilgisi YOK. Geçmişe dönük veri yoktur;
# ilk kayıt tarihi MIN(gun)'dür. Tekillik: aynı kullanıcı+tür+nesne+gün+oturum bir kez sayılır.
SEMA_V4 = """
CREATE TABLE olay (
    id            INTEGER PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL,
    rol           TEXT NOT NULL,
    tur           TEXT NOT NULL,
    nesne         TEXT NOT NULL DEFAULT '',
    gun           TEXT NOT NULL,
    saat          INTEGER NOT NULL,
    oturum_k      TEXT NOT NULL DEFAULT '',
    UNIQUE (kullanici_id, tur, nesne, gun, oturum_k)
);
CREATE INDEX olay_gun_tur ON olay(gun, tur);
CREATE INDEX olay_kullanici_tur ON olay(kullanici_id, tur);
ALTER TABLE oturum ADD COLUMN son_nabiz TEXT;
CREATE INDEX oturum_son_nabiz ON oturum(son_nabiz);
"""

# Bilgi Arenası (Günlük Görev + ortak XP/rozet katmanı). XP toplamı/seviyesi defterden türetilir.
# bilgi_tur UNIQUE(kullanici_id, gun): günde bir görev; ödül çoğaltma DB seviyesinde engellenir.
SEMA_V5 = """
CREATE TABLE bilgi_tur (
    id            INTEGER PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    gun           TEXT NOT NULL,
    sinif         TEXT NOT NULL,
    ders          TEXT NOT NULL,
    basla         TEXT NOT NULL,
    bitis         TEXT,
    durum         TEXT NOT NULL DEFAULT 'acik' CHECK (durum IN ('acik', 'tamam', 'terk')),
    dogru         INTEGER NOT NULL DEFAULT 0,
    xp            INTEGER NOT NULL DEFAULT 0,
    UNIQUE (kullanici_id, gun)
);
CREATE INDEX bilgi_tur_kullanici ON bilgi_tur(kullanici_id, gun);
CREATE TABLE bilgi_cevap (
    tur_id        INTEGER NOT NULL REFERENCES bilgi_tur(id) ON DELETE CASCADE,
    sira          INTEGER NOT NULL,
    soru_id       INTEGER NOT NULL,
    kazanim_id    INTEGER,
    kazanim_kod   TEXT,
    kazanim_metin TEXT,
    soru          TEXT NOT NULL,
    secenekler    TEXT NOT NULL,
    dogru_index   INTEGER NOT NULL,
    konu          TEXT,
    cevap         INTEGER,
    cevap_zamani  TEXT,
    PRIMARY KEY (tur_id, sira)
);
CREATE INDEX bilgi_cevap_soru ON bilgi_cevap(soru_id);
CREATE TABLE bilgi_xp (
    id            INTEGER PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    kaynak        TEXT NOT NULL CHECK (kaynak IN ('arena_dogru', 'arena_bonus', 'maraton_tur')),
    ref           TEXT NOT NULL,
    miktar        INTEGER NOT NULL CHECK (miktar > 0),
    gun           TEXT NOT NULL,
    zaman         TEXT NOT NULL,
    UNIQUE (kullanici_id, kaynak, ref)
);
CREATE INDEX bilgi_xp_kullanici ON bilgi_xp(kullanici_id);
CREATE TABLE bilgi_rozet (
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    rozet_kodu    TEXT NOT NULL,
    zaman         TEXT NOT NULL,
    PRIMARY KEY (kullanici_id, rozet_kodu)
);
"""

# Harici deneme sonuçları. `veri` serbest JSON (sütunlar PDF'e göre değişir); okul_no ile öğrenciye bağlanır.
# yayinda=0 iken öğrenci/veli göremez. Başka öğrenciyle karşılaştırma verisi tutulmaz.
SEMA_V6 = """
CREATE TABLE deneme (
    id         INTEGER PRIMARY KEY,
    ad         TEXT NOT NULL UNIQUE,
    tarih      TEXT,
    ozet       TEXT NOT NULL DEFAULT '',
    yayinda    INTEGER NOT NULL DEFAULT 0,
    olusturma  TEXT NOT NULL
);
CREATE TABLE deneme_ogrenci (
    deneme_id  INTEGER NOT NULL REFERENCES deneme(id),
    okul_no    INTEGER NOT NULL,
    girdi      INTEGER NOT NULL DEFAULT 1,
    veri       TEXT NOT NULL DEFAULT '{}',
    analiz     TEXT NOT NULL DEFAULT '',
    tavsiye    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (deneme_id, okul_no)
);
CREATE INDEX deneme_ogrenci_no ON deneme_ogrenci(okul_no);
"""

# Anket modülü: yönetici anket hazırlar, öğrenci/veli/öğretmen kitlesine AYRI AYRI gönderir.
# Yanıtlar ANONİMDİR: anket_katilim "kim yanıtladı"yı (tek yanıt kuralı), anket_yanit/anket_cevap "ne yanıtlandı"yı tutar;
# ikisi arasında bağ yoktur: yanıt id'si rastgele, katılımda sıra/saat yok, anket_cevap WITHOUT ROWID (fiziksel sıra rastgele
# yanit_id'ye göre; ekleme sırası/rowid ile olay kaydına bağlanamaz), yanıtta sınıf gibi dolaylı kimlik sütunu yok.
# Sonuç, 5'ten az yanıtlı grupta gösterilmez.
SEMA_V7 = """
CREATE TABLE anket (
    id          INTEGER PRIMARY KEY,
    baslik      TEXT NOT NULL,
    aciklama    TEXT NOT NULL DEFAULT '',
    olusturan   INTEGER NOT NULL REFERENCES kullanici(id),
    olusturma   TEXT NOT NULL
);
CREATE TABLE anket_soru (
    id          INTEGER PRIMARY KEY,
    anket_id    INTEGER NOT NULL REFERENCES anket(id) ON DELETE CASCADE,
    sira        INTEGER NOT NULL,
    tur         TEXT NOT NULL CHECK (tur IN ('tek', 'coklu', 'olcek', 'metin')),
    metin       TEXT NOT NULL,
    secenekler  TEXT NOT NULL DEFAULT '[]',
    zorunlu     INTEGER NOT NULL DEFAULT 1,
    roller      TEXT NOT NULL DEFAULT 'ogrenci,veli,ogretmen'
);
CREATE INDEX anket_soru_anket ON anket_soru(anket_id, sira);
CREATE TABLE anket_hedef (
    anket_id    INTEGER NOT NULL REFERENCES anket(id) ON DELETE CASCADE,
    rol         TEXT NOT NULL CHECK (rol IN ('ogrenci', 'veli', 'ogretmen')),
    sinif_filtre TEXT NOT NULL DEFAULT '',
    acilis      TEXT NOT NULL,
    kapanis     TEXT,
    kapatildi   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (anket_id, rol)
);
CREATE TABLE anket_katilim (
    anket_id     INTEGER NOT NULL REFERENCES anket(id) ON DELETE CASCADE,
    kullanici_id INTEGER NOT NULL REFERENCES kullanici(id),
    rol          TEXT NOT NULL,
    PRIMARY KEY (anket_id, kullanici_id)
) WITHOUT ROWID;
CREATE TABLE anket_yanit (
    id          INTEGER PRIMARY KEY,
    anket_id    INTEGER NOT NULL REFERENCES anket(id) ON DELETE CASCADE,
    rol         TEXT NOT NULL
);
CREATE INDEX anket_yanit_anket ON anket_yanit(anket_id, rol);
CREATE TABLE anket_cevap (
    yanit_id    INTEGER NOT NULL REFERENCES anket_yanit(id) ON DELETE CASCADE,
    soru_id     INTEGER NOT NULL REFERENCES anket_soru(id) ON DELETE CASCADE,
    deger       TEXT NOT NULL,
    PRIMARY KEY (yanit_id, soru_id, deger)
) WITHOUT ROWID;
CREATE INDEX anket_cevap_soru ON anket_cevap(soru_id);
"""

# Kişisel Gelişim: öğrencinin kendi koyduğu haftalık çalışma hedefi. İlerleme SAKLANMAZ; gerçek etkinliklerden
# (Arena görevi, Hızlı Mod turu, test ödevi teslimi) her seferinde hesaplanır. Başkasıyla karşılaştırma yoktur.
SEMA_V8 = """
CREATE TABLE hedef (
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    hafta_basi    TEXT NOT NULL,
    hedef_sayi    INTEGER NOT NULL CHECK (hedef_sayi BETWEEN 1 AND 14),
    olusturma     TEXT NOT NULL,
    PRIMARY KEY (kullanici_id, hafta_basi)
);
"""

# Haftalık ödüller (kiosk duyurusu + rozet + haftanın Nescafe'si). Hafta bittikten sonra bir kez yazılır, değişmez.
# odul_hafta: haftanın sonucu yazıldı işareti (kazanan çıkmasa da; sonradan gelen veri sonucu değiştirmesin).
# anahtar = "kullanici_id|sinif" (NULL'lar UNIQUE'i delmesin). Sınıf ödülü satırında kullanici_id NULL'dur.
SEMA_V9 = """
CREATE TABLE odul (
    id            INTEGER PRIMARY KEY,
    hafta_basi    TEXT NOT NULL,
    kategori      TEXT NOT NULL CHECK (kategori IN ('etkinlik', 'istikrar', 'sinif')),
    anahtar       TEXT NOT NULL,
    kullanici_id  INTEGER REFERENCES kullanici(id),
    sinif         TEXT,
    deger         INTEGER NOT NULL,
    ayrinti       TEXT NOT NULL DEFAULT '',
    kahve         INTEGER NOT NULL DEFAULT 0,
    kahve_teslim  TEXT,
    zaman         TEXT NOT NULL,
    UNIQUE (hafta_basi, kategori, anahtar)
);
CREATE INDEX odul_hafta_idx ON odul(hafta_basi);
CREATE TABLE odul_hafta (
    hafta_basi  TEXT PRIMARY KEY,
    kapanis     TEXT NOT NULL
);
"""

# Öğrenci avatarı: seçilen karakter + eşya kodları. Açık olup olmadığı seviyeye göre sunucuda doğrulanır (avatar.py).
SEMA_V10 = """
CREATE TABLE avatar (
    kullanici_id  INTEGER PRIMARY KEY REFERENCES kullanici(id),
    karakter      TEXT NOT NULL,
    sapka         TEXT NOT NULL DEFAULT 'yok',
    yuz           TEXT NOT NULL DEFAULT 'yok',
    sirt          TEXT NOT NULL DEFAULT 'yok',
    guncelleme    TEXT NOT NULL
);
"""

# Web Push abonelikleri (bildirim): cihaz başına bir uç nokta; içerik/kimlik verisi tutulmaz (push.py).
SEMA_V11 = """
CREATE TABLE push_abonelik (
    id            INTEGER PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    uc_nokta      TEXT NOT NULL UNIQUE,
    p256dh        TEXT NOT NULL,
    auth          TEXT NOT NULL,
    olusturma     TEXT NOT NULL,
    son_basari    TEXT,
    hata_sayisi   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX push_abonelik_kullanici ON push_abonelik(kullanici_id);
"""

# Öğretmen+yönetici ortak sohbet odası (yalnızca metin, 30 gün saklanır; sohbet.py). sohbet_okuma: okunmamış sayacı + bildirim sıklığı.
SEMA_V12 = """
CREATE TABLE sohbet_mesaj (
    id         INTEGER PRIMARY KEY,
    yazar_id   INTEGER NOT NULL REFERENCES kullanici(id),
    metin      TEXT NOT NULL,
    olusturma  TEXT NOT NULL
);
CREATE INDEX sohbet_mesaj_zaman ON sohbet_mesaj(olusturma);
CREATE TABLE sohbet_okuma (
    kullanici_id  INTEGER PRIMARY KEY REFERENCES kullanici(id),
    son_id        INTEGER NOT NULL DEFAULT 0,
    son_push      TEXT
);
"""

# Duyuru okuma kaydı: kullanıcı /duyurular sayfasını açınca görünen duyurular için bir kez yazılır (yönetici raporu).
SEMA_V13 = """
CREATE TABLE duyuru_okuma (
    duyuru_id     INTEGER NOT NULL REFERENCES duyuru(id) ON DELETE CASCADE,
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    zaman         TEXT NOT NULL,
    PRIMARY KEY (duyuru_id, kullanici_id)
);
"""

# Dilek/istek/şikayet kutusu (öğrenci+öğretmen → yönetici; adlı; yönetici yalnızca durum işaretler; kutu.py).
SEMA_V14 = """
CREATE TABLE kutu_kayit (
    id            INTEGER PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    tur           TEXT NOT NULL CHECK (tur IN ('dilek', 'istek', 'sikayet')),
    metin         TEXT NOT NULL,
    durum         TEXT NOT NULL DEFAULT 'yeni' CHECK (durum IN ('yeni', 'okundu', 'cozuldu')),
    olusturma     TEXT NOT NULL,
    guncelleme    TEXT
);
CREATE INDEX kutu_kayit_durum ON kutu_kayit(durum, olusturma);
CREATE INDEX kutu_kayit_kullanici ON kutu_kayit(kullanici_id, olusturma);
"""

# Acil durum: okul portalından basılan alarm izi + öğretmen/yönetici konum paylaşımı (acil.py). Konumlar 24 saat sonra silinir.
SEMA_V15 = """
CREATE TABLE acil_olay (
    id            INTEGER PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    tur           TEXT NOT NULL,
    yer           TEXT,
    tatbikat      INTEGER,
    basarili      INTEGER NOT NULL DEFAULT 0,
    sonuc_json    TEXT,
    jeton         TEXT NOT NULL UNIQUE,
    olusturma     TEXT NOT NULL,
    kapanis       TEXT
);
CREATE INDEX acil_olay_zaman ON acil_olay(olusturma);
CREATE TABLE acil_konum (
    id            INTEGER PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    yer           TEXT NOT NULL,
    enlem         REAL,
    boylam        REAL,
    dogruluk_m    REAL,
    olusturma     TEXT NOT NULL
);
CREATE INDEX acil_konum_zaman ON acil_konum(olusturma);
"""

# Öğrenci acil bildirimi: yalnızca yöneticiler görür, 24 saat sonra silinir (acil.py).
SEMA_V16 = """
CREATE TABLE acil_ogrenci (
    id            INTEGER PRIMARY KEY,
    kullanici_id  INTEGER NOT NULL REFERENCES kullanici(id),
    enlem         REAL,
    boylam        REAL,
    dogruluk_m    REAL,
    olusturma     TEXT NOT NULL
);
CREATE INDEX acil_ogrenci_zaman ON acil_ogrenci(olusturma);
"""

# Acil durum: panel/Telegram/tahta kaynaklı (okul dışı) olaylar — push + şerit için (acil.py). acil_olay okul kullanıcısı gerektirir.
SEMA_V17 = """
CREATE TABLE acil_dis_olay (
    id         INTEGER PRIMARY KEY,
    tur        TEXT NOT NULL,
    tatbikat   INTEGER NOT NULL DEFAULT 0,
    kaynak     TEXT NOT NULL,
    olusturma  TEXT NOT NULL,
    kapanis    TEXT
);
CREATE INDEX acil_dis_olay_zaman ON acil_dis_olay(olusturma);
"""

# Sudoku Düellosu (eşzamansız, sınıf içi). Puan saklanmaz; biten düellolardan türetilir. bilgi_xp'den bağımsız.
SEMA_V18 = """
CREATE TABLE sudoku_duello (
    id         INTEGER PRIMARY KEY,
    sinif      TEXT NOT NULL,
    zorluk     TEXT NOT NULL CHECK (zorluk IN ('basit','orta','zor')),
    bulmaca    TEXT NOT NULL,
    cozum      TEXT NOT NULL,
    kuran_kid  INTEGER NOT NULL REFERENCES kullanici(id),
    rakip_kid  INTEGER NOT NULL REFERENCES kullanici(id),
    durum      TEXT NOT NULL CHECK (durum IN ('bekliyor','surer','bitti','red','doldu')),
    olusturma  TEXT NOT NULL,
    son_tarih  TEXT
);
CREATE INDEX sudoku_duello_kuran ON sudoku_duello(kuran_kid, durum);
CREATE INDEX sudoku_duello_rakip ON sudoku_duello(rakip_kid, durum);
CREATE TABLE sudoku_oyun (
    duello_id    INTEGER NOT NULL REFERENCES sudoku_duello(id),
    kullanici_id INTEGER NOT NULL REFERENCES kullanici(id),
    baslama      TEXT NOT NULL,
    bitis        TEXT,
    hata         INTEGER NOT NULL DEFAULT 0,
    sure_sn      INTEGER,
    UNIQUE (duello_id, kullanici_id)
);
"""

# Öğretmenin sınıfa gönderdiği PDF + ödevin PDF eki (sayfa aralığı) + öğrencinin tek foto teslimi.
# Foto teslimi odev_teslim'e 'yapti' olarak da yazılır (mevcut listeler değişmeden çalışır).
SEMA_V19 = """
CREATE TABLE sinif_pdf (
    id          INTEGER PRIMARY KEY,
    ogretmen_id INTEGER NOT NULL REFERENCES kullanici(id),
    sinif       TEXT NOT NULL,
    ders        TEXT NOT NULL,
    baslik      TEXT NOT NULL,
    dosya_adi   TEXT NOT NULL,
    depo_adi    TEXT NOT NULL,
    boyut       INTEGER NOT NULL,
    zaman       TEXT NOT NULL
);
CREATE INDEX sinif_pdf_sinif ON sinif_pdf(sinif, zaman);
CREATE TABLE odev_pdf (
    odev_id   INTEGER PRIMARY KEY REFERENCES odev(id) ON DELETE CASCADE,
    pdf_id    INTEGER NOT NULL REFERENCES sinif_pdf(id) ON DELETE CASCADE,
    sayfa_bas INTEGER,
    sayfa_bit INTEGER
);
CREATE TABLE odev_foto (
    odev_id    INTEGER NOT NULL REFERENCES odev(id) ON DELETE CASCADE,
    ogrenci_id INTEGER NOT NULL REFERENCES ogrenci(id),
    depo_adi   TEXT NOT NULL,
    tur        TEXT NOT NULL,
    zaman      TEXT NOT NULL,
    PRIMARY KEY (odev_id, ogrenci_id)
);
"""

# Öğrencinin "bu soruda sorun var" bildirimi (havuz Postgres'te salt-okunur olduğu için okul.db'de tutulur).
# Kişisel veri yok: yalnızca kim/hangi soru/tür; aynı öğrenci aynı soruyu bir kez bildirir.
SEMA_V20 = """
CREATE TABLE soru_bildirim (
    id           INTEGER PRIMARY KEY,
    soru_id      INTEGER NOT NULL,
    kullanici_id INTEGER NOT NULL REFERENCES kullanici(id),
    tur          TEXT NOT NULL CHECK (tur IN ('sekil','cevap','anlasilmiyor')),
    zaman        TEXT NOT NULL,
    UNIQUE (soru_id, kullanici_id)
);
CREATE INDEX soru_bildirim_soru ON soru_bildirim(soru_id);
"""

# Öğretmen PDF'inden soru havuzuna katkı (soruhavuzu gece turunda işler; durum okul API'siyle geri yazılır).
SEMA_V21 = """
ALTER TABLE sinif_pdf ADD COLUMN soru_uret INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sinif_pdf ADD COLUMN soru_durum TEXT NOT NULL DEFAULT 'yok'
    CHECK (soru_durum IN ('yok','bekliyor','isleniyor','bitti','hata'));
ALTER TABLE sinif_pdf ADD COLUMN soru_bas INTEGER;
ALTER TABLE sinif_pdf ADD COLUMN soru_bit INTEGER;
ALTER TABLE sinif_pdf ADD COLUMN soru_onayli INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sinif_pdf ADD COLUMN soru_red INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sinif_pdf ADD COLUMN soru_not TEXT;
ALTER TABLE sinif_pdf ADD COLUMN soru_zaman TEXT;
"""

# Soru bildirimi genişletildi: öğretmen/yönetici/tahta bildirimi, yeni sebepler, rol ağırlığı, yönetici iptali.
# SQLite CHECK değiştirilemediği için tablo yeniden kurulur; eski satırlar rol='ogrenci' olarak taşınır.
SEMA_V22 = """
CREATE TABLE soru_bildirim_yeni (
    id           INTEGER PRIMARY KEY,
    soru_id      INTEGER NOT NULL,
    kullanici_id INTEGER REFERENCES kullanici(id),
    tur          TEXT NOT NULL CHECK (tur IN ('sekil','cevap','anlasilmiyor','alakasiz','sacma')),
    zaman        TEXT NOT NULL,
    rol          TEXT NOT NULL DEFAULT 'ogrenci' CHECK (rol IN ('ogrenci','ogretmen','yonetici','tahta')),
    kaynak       TEXT NOT NULL DEFAULT '',
    sube         TEXT,
    iptal        INTEGER NOT NULL DEFAULT 0
);
INSERT INTO soru_bildirim_yeni (id, soru_id, kullanici_id, tur, zaman)
    SELECT id, soru_id, kullanici_id, tur, zaman FROM soru_bildirim;
DROP TABLE soru_bildirim;
ALTER TABLE soru_bildirim_yeni RENAME TO soru_bildirim;
CREATE UNIQUE INDEX soru_bildirim_kisi ON soru_bildirim(soru_id, kullanici_id) WHERE kullanici_id IS NOT NULL;
CREATE UNIQUE INDEX soru_bildirim_tahta ON soru_bildirim(soru_id, sube, substr(zaman, 1, 10)) WHERE kullanici_id IS NULL;
CREATE INDEX soru_bildirim_soru ON soru_bildirim(soru_id);
"""

# Öğretmenin günlük 5 soru incelemesi: gün başına sabit set; sonuç dogru|hatali|pas (hatalı ayrıca soru_bildirim'e yazılır).
SEMA_V23 = """
CREATE TABLE soru_inceleme (
    ogretmen_id INTEGER NOT NULL REFERENCES kullanici(id),
    gun         TEXT NOT NULL,
    sira        INTEGER NOT NULL,
    soru_id     INTEGER NOT NULL,
    sonuc       TEXT CHECK (sonuc IN ('dogru','hatali','pas')),
    zaman       TEXT,
    PRIMARY KEY (ogretmen_id, gun, sira),
    UNIQUE (ogretmen_id, gun, soru_id)
);
CREATE INDEX soru_inceleme_soru ON soru_inceleme(soru_id);
"""

GOCLER = [
    SEMA_V1, SEMA_V2, SEMA_V3, SEMA_V4, SEMA_V5, SEMA_V6, SEMA_V7, SEMA_V8, SEMA_V9, SEMA_V10,
    SEMA_V11, SEMA_V12, SEMA_V13, SEMA_V14, SEMA_V15, SEMA_V16, SEMA_V17,
    SEMA_V18, SEMA_V19, SEMA_V20, SEMA_V21, SEMA_V22, SEMA_V23,
]


def baglanti() -> sqlite3.Connection:
    AYAR.db_yolu.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(AYAR.db_yolu, timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def sema_kur() -> None:
    conn = baglanti()
    try:
        surum = conn.execute("PRAGMA user_version").fetchone()[0]
        for i in range(surum, len(GOCLER)):
            # Göç + sürüm numarası tek işlemde: yarıda kalırsa ikisi birden geri alınır.
            conn.executescript(
                f"BEGIN;\n{GOCLER[i]}\nPRAGMA user_version = {i + 1};\nCOMMIT;"
            )
    finally:
        conn.close()
