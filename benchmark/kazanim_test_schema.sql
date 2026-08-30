-- MEB ÖDSGM kazanım testleri — yapılandırılmış soru/seçenek/cevap şeması
-- (2026-08-30). chunk_egitim/chunk_tablo'ya BİLEREK dokunmaz, üçüncü
-- bağımsız kaynak tablosu. Aynı sha256-dedup ilkesi embed_kitap.py'den.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kazanim_test_soru (
    id           BIGSERIAL PRIMARY KEY,
    kaynak_dosya TEXT NOT NULL,
    kaynak_hash  TEXT NOT NULL,
    sinif        SMALLINT,
    ders         TEXT,
    konu         TEXT,
    test_no      INTEGER,
    soru_no      INTEGER NOT NULL,
    soru_metni   TEXT NOT NULL,
    secenekler   JSONB,
    cevap        CHAR(1),
    embedding    VECTOR(1024),
    UNIQUE (kaynak_hash, soru_no)
);

CREATE INDEX IF NOT EXISTS idx_kts_ders_sinif ON kazanim_test_soru(ders, sinif);
CREATE INDEX IF NOT EXISTS idx_kts_hash ON kazanim_test_soru(kaynak_hash);
