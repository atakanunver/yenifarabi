-- Ölçüm/loglama şeması (docs/mimari.md §13, "Ölçüm ve Loglama") — kitap +
-- chunk_egitim (Faz 0a) ve Faz 1 şeması (faz1_schema.sql) üzerine EKLENİR.
--
-- İKİ TABLO, İKİ AMAÇ, KARIŞTIRILMAZ (CLAUDE.md, "Loglama"):
--   metrik   -> yalnızca süre + durum + skor. İçerik YOK. Sınırsız saklanır.
--   soru_log -> soru/cevap metni YALNIZCA düşük skorlu ok / yetersiz_kaynak /
--               sayi_kontrolu_reddi / iptal / hata durumlarında. SÜRESİZ
--               saklanır (bkz. aşağıdaki not — "90 gün sonra silinir" kuralı
--               2026-08-18'de BİLİNÇLİ kaldırıldı, hiç uygulanmamıştı).
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

-- NOT (2026-08-18, kök CLAUDE.md "Loglama" bölümünde de kayıtlı): "90 gün
-- sonra silinir" kuralı BİLİNÇLİ olarak kaldırıldı — hiçbir zaman
-- uygulanmamıştı (crontab'da/kodda buna karşılık gelen bir DELETE hiç
-- yoktu, bir kod incelemesinde bulundu). Kullanıcı bunu hata olarak değil,
-- olması gereken durum olarak onayladı: kimlik zaten tutulmadığı için
-- (§14) süresiz saklamanın ek bir KVKK riski taşımadığı değerlendirmesiyle.
-- Otomatik silme mekanizması YOK, kasıtlı olarak yok — tekrar istenirse
-- kök CLAUDE.md'nin "Loglama" notu güncellenmeli.
