-- Tablo şeması (2026-08-30) — client/tools/tablo_cikar.py çıktısını
-- (icerik/tablolar/<kitap>.json) embed edip pgvector'a yazmak için.
--
-- BİLEREK chunk_egitim'e DOKUNMAZ, ayrı tablo: mevcut RAG yoluna
-- (server/rag.py) sıfır risk — bu FAZ yalnızca çıkarma+saklama+embed,
-- retrieval'a bağlanma ayrı, sonraki bir fazın kararı (bkz. plan notu).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunk_tablo (
    id          BIGSERIAL PRIMARY KEY,
    kitap_id    BIGINT NOT NULL REFERENCES kitap(id) ON DELETE CASCADE,
    sayfa_no    INTEGER NOT NULL CHECK (sayfa_no > 0),
    baslik      TEXT,
    tablo_json  JSONB NOT NULL,
    metin_ozet  TEXT NOT NULL,
    embedding   VECTOR(1024) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunk_tablo_kitap_id ON chunk_tablo(kitap_id);

-- Not: chunk_egitim ile aynı gerekçeyle, yaklaşık (HNSW/IVFFlat) indeks
-- BİLEREK eklenmedi — Kural 10, ölçmeden optimizasyon yapma.
