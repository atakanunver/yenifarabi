-- Faz 0a şeması: sadece kitap + chunk_egitim (docs/mimari.md §6).
-- kazanim, sinif_kitap, ogretmen vb. Faz 1 tabloları burada YOK.
-- kazanim_kod bu yüzden FK değil, NULL olabilen düz metin kolonu.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kitap (
    id             BIGSERIAL PRIMARY KEY,
    sinif          SMALLINT NOT NULL,
    ders           TEXT NOT NULL,
    yayinevi       TEXT NOT NULL,
    yayin_yili     SMALLINT,
    dosya_yolu     TEXT NOT NULL UNIQUE,
    hash           TEXT NOT NULL UNIQUE,
    indekslendi_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS chunk_egitim (
    id          BIGSERIAL PRIMARY KEY,
    kitap_id    BIGINT NOT NULL REFERENCES kitap(id) ON DELETE CASCADE,
    sayfa_no    INTEGER NOT NULL CHECK (sayfa_no > 0),
    kazanim_kod TEXT,
    metin       TEXT NOT NULL,
    embedding   VECTOR(1024) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunk_egitim_kitap_id ON chunk_egitim(kitap_id);
CREATE INDEX IF NOT EXISTS idx_chunk_egitim_kazanim_kod ON chunk_egitim(kazanim_kod);

-- Not: pgvector için HNSW/IVFFlat (yaklaşık) indeks kasıtlı olarak eklenmedi.
-- Faz 0a tek kitapla, tam (exact) kosinüs taramasıyla çalışır — yaklaşık
-- indeks recall ölçümünü bozar. Kural 10: ölçmeden optimizasyon yapma.
