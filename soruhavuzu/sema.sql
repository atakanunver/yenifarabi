CREATE TABLE IF NOT EXISTS kaynak_birim (
    id          serial PRIMARY KEY,
    tur         text NOT NULL CHECK (tur IN ('kitap', 'kazanim', 'yks')),
    anahtar     text NOT NULL UNIQUE,          -- örn. "kitap:36:12-14", "kazanim:12sinif_fizik_8.pdf:3"
    ders        text,                           -- ders anahtarı; yks'de NULL (soru başına gelir)
    sinif       smallint NOT NULL,
    etiket      text NOT NULL,                  -- kaynak etiketi, örn. "Matematik 12, s. 12"
    metin       text NOT NULL,
    durum       text NOT NULL DEFAULT 'bekliyor' CHECK (durum IN ('bekliyor', 'islendi', 'hata')),
    hata        text,
    islendi_at  timestamptz
);
CREATE TABLE IF NOT EXISTS soru (
    id               bigserial PRIMARY KEY,
    birim_id         int NOT NULL REFERENCES kaynak_birim(id),
    ders             text NOT NULL,
    sinif            smallint NOT NULL,
    konu             text NOT NULL,
    soru             text NOT NULL,
    kisa_cevap       text NOT NULL,
    secenekler       jsonb NOT NULL,            -- 4 metin
    dogru_index      smallint NOT NULL CHECK (dogru_index BETWEEN 0 AND 3),
    zorluk           smallint NOT NULL CHECK (zorluk BETWEEN 1 AND 4),
    kaynak           text NOT NULL,
    durum            text NOT NULL DEFAULT 'uretildi'
                     CHECK (durum IN ('uretildi', 'onayli', 'red', 'kopya')),
    denetim_notu     text,
    olusturma        timestamptz NOT NULL DEFAULT now(),
    denetim_at       timestamptz,
    kullanim_sayisi  int NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS soru_oyun_idx ON soru (ders, sinif, durum, zorluk);
CREATE INDEX IF NOT EXISTS birim_durum_idx ON kaynak_birim (durum, id);

CREATE TABLE IF NOT EXISTS kazanim (
    id      serial PRIMARY KEY,
    sinif   smallint NOT NULL,
    ders    text NOT NULL,
    hafta   smallint NOT NULL,
    kod     text,
    metin   text NOT NULL,
    durum   text NOT NULL DEFAULT 'aktif' CHECK (durum IN ('aktif', 'kaynak_yok')),
    UNIQUE (sinif, ders, hafta, metin)
);
ALTER TABLE soru ADD COLUMN IF NOT EXISTS kazanim_id integer REFERENCES kazanim(id);
ALTER TABLE soru ADD COLUMN IF NOT EXISTS kazanim_skor real;
ALTER TABLE soru ADD COLUMN IF NOT EXISTS kazanim_kaynak text CHECK (kazanim_kaynak IN ('uretim', 'etiket'));
CREATE INDEX IF NOT EXISTS soru_kazanim_idx ON soru (kazanim_id, durum);
