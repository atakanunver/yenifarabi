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

GOCLER = [SEMA_V1, SEMA_V2, SEMA_V3, SEMA_V4, SEMA_V5, SEMA_V6, SEMA_V7, SEMA_V8]


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
