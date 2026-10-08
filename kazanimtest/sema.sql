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

-- Faz 2 (raporlama): soru anlık görüntüsü + form cevapları.
-- sorular: [{kimlik, soru, secenekler[4], dogru_index, etiket, kazanim_satiri}] (form oluşturulurken yazılır;
-- eski kayıtlar için `calistir.py anlik-doldur`).
ALTER TABLE form_testi ADD COLUMN IF NOT EXISTS sorular jsonb;

-- Aynı okul_no birden çok gönderirse EN ERKEN gönderim sayılır; ilk yazılan kalır (ON CONFLICT DO NOTHING).
-- soru_sira = form_testi.sorular dizisindeki 0 tabanlı sıra. secilen NULL = boş/eşleşmeyen şık (dogru=false).
CREATE TABLE IF NOT EXISTS form_cevap (
    id             serial PRIMARY KEY,
    form_testi_id  int NOT NULL REFERENCES form_testi(id),
    okul_no        int NOT NULL,
    soru_sira      smallint NOT NULL,
    secilen        smallint,
    dogru          boolean NOT NULL,
    zaman          timestamptz NOT NULL,
    UNIQUE (form_testi_id, okul_no, soru_sira)
);

-- Faz 2 adım 5 (aylık veli/öğrenci raporu): (ay, okul_no) başına bir kalıcı token; tekrar çalıştırmada link değişmez.
-- Token Google'a (Kazanım Raporları tablosu) giden kişiye özel gizli kod; isim/telefon tutulmaz.
CREATE TABLE IF NOT EXISTS aylik_rapor (
    id               serial PRIMARY KEY,
    ay               text NOT NULL,              -- "2026-10"
    sinif            text NOT NULL,
    okul_no          int NOT NULL,
    token            text NOT NULL UNIQUE,
    son_gecerlilik   date NOT NULL,
    olusturma        timestamptz NOT NULL DEFAULT now(),
    sms_taslak_id    text,
    sms_gonderim_id  text,
    UNIQUE (ay, okul_no)
);
