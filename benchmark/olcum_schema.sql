-- Ölçüm/loglama şeması (docs/mimari.md §13, "Ölçüm ve Loglama") — kitap +
-- chunk_egitim (Faz 0a) ve Faz 1 şeması (faz1_schema.sql) üzerine EKLENİR.
--
-- İKİ TABLO, İKİ AMAÇ, KARIŞTIRILMAZ (CLAUDE.md, "Loglama"):
--   metrik   -> yalnızca süre + durum + skor. İçerik YOK. Sınırsız saklanır.
--   soru_log -> soru/cevap metni YALNIZCA düşük skorlu ok / yetersiz_kaynak /
--               sayi_kontrolu_reddi / iptal / hata durumlarında. 90 gün sonra
--               silinir (bkz. aşağıdaki not — otomatik silme mekanizması bu
--               şemaya dahil değil, ayrı bir görev/cron gerektirir).
--
-- Öğrenci kimliği hiçbir tabloda yok, ses hiçbir tabloda yok (mimari.md §14).

CREATE TABLE IF NOT EXISTS metrik (
    id               BIGSERIAL PRIMARY KEY,
    tahta_id         INTEGER,
    ts               TIMESTAMPTZ NOT NULL DEFAULT now(),
    stt_ms           INTEGER,
    retrieval_ms     INTEGER,
    rerank_ms        INTEGER,
    llm_ilk_token_ms INTEGER,
    llm_toplam_ms    INTEGER,
    tts_ilk_ses_ms   INTEGER,
    toplam_ms        INTEGER,
    sonuc            TEXT NOT NULL,
    en_yuksek_skor   REAL
);

CREATE INDEX IF NOT EXISTS idx_metrik_ts ON metrik(ts);
CREATE INDEX IF NOT EXISTS idx_metrik_tahta_id ON metrik(tahta_id);

CREATE TABLE IF NOT EXISTS soru_log (
    id                BIGSERIAL PRIMARY KEY,
    ts                TIMESTAMPTZ NOT NULL DEFAULT now(),
    tahta_id          INTEGER,
    sinif             SMALLINT,
    ders              TEXT,
    soru_metni        TEXT,
    donen_chunk_idler BIGINT[],
    skorlar           REAL[],
    cevap_metni       TEXT,
    sonuc             TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_soru_log_ts ON soru_log(ts);

-- NOT (2026-08-11): "90 gün sonra otomatik silinir" kuralı burada mekanik
-- olarak kurulmadı — pg_cron ya da harici bir cron betiği gerektirir, bu
-- mimari.md'de yeni bir bağımlılık onayı gerektirebilir (CLAUDE.md Kural 8).
-- Şimdilik elle: DELETE FROM soru_log WHERE ts < now() - interval '90 days';
