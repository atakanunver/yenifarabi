-- Atos Hafızası (2026-10-16) — Open WebUI "Atos" okul hafızası. Aditif: mevcut tablolara dokunmaz.
-- Gömme chunk_egitim/chunk_idari ile aynı: bge-m3, 1024 boyut, normalize. embedding NULL olabilir
-- (gömme servisi kapalıyken yazılan kayıt tam-metin aramasıyla bulunur).
-- Uygulama: sudo -u postgres psql -d farabi -f server/schema_hafiza.sql
CREATE TABLE IF NOT EXISTS atos_hafiza (
    id              bigserial PRIMARY KEY,
    tur             text NOT NULL DEFAULT 'bilgi' CHECK (tur IN ('bilgi', 'karar', 'tercih', 'belge')),
    baslik          text NOT NULL CHECK (char_length(baslik) BETWEEN 1 AND 80),
    icerik          text NOT NULL CHECK (char_length(icerik) BETWEEN 1 AND 600),
    kaynak          text NOT NULL DEFAULT '' CHECK (char_length(kaynak) <= 120),
    sabit           boolean NOT NULL DEFAULT false,         -- çekirdek not: her mesajda enjekte edilir
    son_gecerlilik  date,                                    -- NULL = süresiz
    durum           text NOT NULL DEFAULT 'aktif' CHECK (durum IN ('aktif', 'arsiv')),
    yerine_gecen_id bigint REFERENCES atos_hafiza(id),
    olusturma       timestamptz NOT NULL DEFAULT now(),
    guncelleme      timestamptz NOT NULL DEFAULT now(),
    embedding       vector(1024)
);

CREATE INDEX IF NOT EXISTS idx_atos_hafiza_durum ON atos_hafiza (durum, sabit);

GRANT SELECT, INSERT, UPDATE, DELETE ON atos_hafiza TO farabi;
GRANT USAGE, SELECT ON SEQUENCE atos_hafiza_id_seq TO farabi;
