-- Mevcut 4 şıklı sorular korunur; YKS için E dahil 8'e kadar şık kullanılabilir.
BEGIN;
ALTER TABLE soru DROP CONSTRAINT IF EXISTS soru_dogru_index_check;
ALTER TABLE soru ADD CONSTRAINT soru_dogru_index_check
    CHECK (dogru_index >= 0 AND dogru_index < jsonb_array_length(secenekler) AND dogru_index < 8);

-- Görsel soru_havuzu veritabanında saklanır, böylece pg_dump ile birlikte yedeklenir.
CREATE TABLE IF NOT EXISTS soru_gorsel (
    soru_id bigint PRIMARY KEY REFERENCES soru(id) ON DELETE CASCADE,
    icerik bytea NOT NULL,
    mime text NOT NULL CHECK (mime IN ('image/png', 'image/jpeg', 'image/webp')),
    kaynak_sha256 text NOT NULL,
    kaynak_sayfa integer NOT NULL CHECK (kaynak_sayfa > 0),
    olusturma timestamptz NOT NULL DEFAULT now()
);
COMMIT;
