-- server/schema_yks_gosterim.sql — YKS soru gösterimini kalıcı olarak kaydet
-- (2026-08-21, gerçek bir derste bildirilen hata: daha önce çözülmüş bir
-- soru yeni soruymuş gibi tekrar sunuldu — server/yks.py'deki _OTURUMLAR
-- yalnızca bellek-içi, süreç ömrü boyunca, geçmiş derslere hiç bakmıyordu).
--
-- Yeni bir teknoloji DEĞİL — mevcut PostgreSQL'e eklenen tek bir tablo
-- (CLAUDE.md Kural 8), server/schema_tahta_durum.sql ile AYNI kalıp.
--
-- Bu tablo yalnızca "hangi soru hangi derslikte gösterildi" kaydını tutar;
-- server/yks.py bir soru seçmeden önce burayı sorgulayıp daha önce
-- gösterilenleri adaylardan çıkarır (dosya_adi+sayfa ikilisiyle).

CREATE TABLE IF NOT EXISTS yks_gosterim (
    id              BIGSERIAL PRIMARY KEY,
    derslik         TEXT NOT NULL,
    dosya_adi       TEXT NOT NULL,
    sayfa           INTEGER NOT NULL,
    ders            TEXT,
    konu            TEXT,
    gosterim_zamani TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_yks_gosterim_derslik ON yks_gosterim(derslik);

-- Uygulama: tablolar `postgres` sahipliğinde (tahta_durum ile aynı), bu
-- dosya `sudo -u postgres psql -d farabi` ile ÇALIŞTIRILMALI (farabi
-- kullanıcısının CREATE TABLE yetkisi yok). Ardından uygulama kullanıcısına
-- (farabi) en az yetki verilmeli — tahta_durum'daki `farabi=arw` deseniyle
-- aynı (SELECT+INSERT+UPDATE, DELETE yok):
--   GRANT SELECT, INSERT, UPDATE ON yks_gosterim TO farabi;
--   GRANT USAGE, SELECT ON SEQUENCE yks_gosterim_id_seq TO farabi;
