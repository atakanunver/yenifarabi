-- soru_havuzu DB'sine uygulanır (elle; calistir.py şema kurmaz).
CREATE TABLE IF NOT EXISTS form_testi (
    id               serial PRIMARY KEY,
    sinif            text NOT NULL,              -- "9-A"
    ders             text NOT NULL,              -- ders anahtarı (soruhavuzu/dersler.py)
    hafta            smallint NOT NULL,          -- yıllık plan hafta no
    kazanim          text NOT NULL,
    soru_idler       jsonb NOT NULL,             -- ["meb:12", "havuz:7", ...]
    form_id          text,
    form_url         text,
    form_kisa_url    text,
    tablo_url        text,
    xlsx_yol         text,
    sms_gonderim_id  text,
    durum            text NOT NULL DEFAULT 'form' CHECK (durum IN ('form', 'sms')),
    olusturma        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (sinif, ders, hafta)
);
