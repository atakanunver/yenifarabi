-- server/schema_tahta_durum.sql — 10 tahtaya ölçekleme: merkezi tahta durum
-- takibi (analiz raporu §5/§6, kullanıcı onayı 2026-08-18). Yeni bir
-- teknoloji DEĞİL — mevcut PostgreSQL'e eklenen tek bir tablo (CLAUDE.md
-- Kural 8).
--
-- derslik PRIMARY KEY: her tahtanın zaten benzersiz kimliği bu
-- (client/core/tahta.py, config/api_keys.json'daki 'derslik' alanı) — ayrı
-- bir client_id icat edilmedi, mevcut alan yeniden kullanıldı.
--
-- son_guncelleme burada YOK, bilerek: yalnızca 9-A push yapıyor (pilot),
-- server zaten her push'ta git commit atıyor — "son başarılı güncelleme"
-- bilgisi `git log -1 -- client/` ile server tarafında zaten var, ayrı bir
-- kolonda tekrar tutulup senkron dışı kalma riski alınmadı.

CREATE TABLE IF NOT EXISTS tahta_durum (
    derslik       TEXT PRIMARY KEY,
    commit_hash   TEXT,
    hostname      TEXT,
    ip            TEXT,
    son_heartbeat TIMESTAMPTZ NOT NULL DEFAULT now()
);
