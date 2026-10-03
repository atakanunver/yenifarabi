-- Mevzuat/yönetmelik parçaları (2026-10-03) — Open WebUI Müdür Yardımcısı modu.
-- 2026-08-31 iptali kaldırıldı (DECISIONS.md 2026-10-03). Vektörler
-- chunk_egitim ile aynı: bge-m3, 1024 boyut, normalize.
CREATE TABLE IF NOT EXISTS idari_belge (
    id             bigserial PRIMARY KEY,
    ad             text NOT NULL,
    dosya_yolu     text NOT NULL UNIQUE,
    hash           text NOT NULL,
    tur            text NOT NULL,              -- pdf | docx | gorsel
    indekslendi_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunk_idari (
    id        bigserial PRIMARY KEY,
    belge_id  bigint NOT NULL REFERENCES idari_belge(id) ON DELETE CASCADE,
    sayfa_no  integer NOT NULL,
    metin     text NOT NULL,
    embedding vector(1024) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunk_idari_belge_id ON chunk_idari (belge_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON idari_belge, chunk_idari TO farabi;
GRANT USAGE, SELECT ON SEQUENCE idari_belge_id_seq, chunk_idari_id_seq TO farabi;
