-- Faz 1 şeması (docs/mimari.md §6, "Şema — Faz 1") — kitap + chunk_egitim
-- (benchmark/schema.sql, Faz 0a) üzerine EKLENİR, onu değiştirmez.
--
-- Yalnızca mimari.md'de zaten listelenen tablolar kuruldu — chunk_egitim'e
-- geriye dönük bir FK eklenmedi (kazanim_kod hâlâ NULL olabilen düz metin,
-- Faz 0a'nın kendi gerekçesiyle aynı — mevcut satırlar hâlâ NULL).
--
-- KURULMAYAN: belge_idari, chunk_idari — mimari.md açıkça "FAZ 4, şimdi
-- oluşturulmaz, izolasyon tasarımı için burada listelenmiştir" diyor.
--
-- NOT (2026-08-11, evening'e bırakılan karar): bu şema mekanik olarak
-- kuruldu ama HİÇBİR gerçek veriyle doldurulmadı — ogretmen/sinif_kitap/
-- ders_programi boş. server/'ın API'si hâlâ kitap_id'yi doğrudan istekte
-- alıyor, bu tabloları kullanan bir bağlam-çözümü (tahta_id → kitap_id)
-- henüz YAZILMADI. Bunun nasıl doldurulacağı (gerçek okul verisi mi, test
-- verisi mi) kullanıcı kararı bekliyor.

CREATE TABLE IF NOT EXISTS ogretmen (
    id       BIGSERIAL PRIMARY KEY,
    ad_soyad TEXT NOT NULL,
    brans    TEXT,
    aktif    BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS kazanim (
    kod   TEXT PRIMARY KEY,
    sinif SMALLINT NOT NULL,
    ders  TEXT NOT NULL,
    unite TEXT,
    metin TEXT NOT NULL
);

-- 9/A hangi yayınevinin kitabını kullanıyor. Bu eşleme olmadan aynı ders
-- için iki kitap varsa RAG yanlış kaynaktan cevaplar (mimari.md §6 notu).
CREATE TABLE IF NOT EXISTS sinif_kitap (
    sinif    SMALLINT NOT NULL,
    sube     TEXT NOT NULL,
    ders     TEXT NOT NULL,
    kitap_id BIGINT NOT NULL REFERENCES kitap(id) ON DELETE CASCADE,
    PRIMARY KEY (sinif, sube, ders)
);

CREATE TABLE IF NOT EXISTS yillik_plan (
    id           BIGSERIAL PRIMARY KEY,
    sinif        SMALLINT NOT NULL,
    sube         TEXT NOT NULL,
    ders         TEXT NOT NULL,
    hafta        SMALLINT NOT NULL CHECK (hafta BETWEEN 1 AND 52),
    kazanim_kod  TEXT REFERENCES kazanim(kod),
    ogretmen_id  BIGINT REFERENCES ogretmen(id)
);

-- gun: 1=Pazartesi .. 7=Pazar. NOT: client/core/program.py'nin gerçek gün
-- kodlamasıyla aynı sözleşmede olduğu bu şema kurulurken DOĞRULANMADI —
-- client entegrasyonundan önce kontrol edilmeli.
-- tahta_id: mimari.md'de ayrı bir "tahta" tablosu tanımlanmamış, bu yüzden
-- FK'siz düz kolon olarak bırakıldı.
CREATE TABLE IF NOT EXISTS ders_programi (
    id          BIGSERIAL PRIMARY KEY,
    sinif       SMALLINT NOT NULL,
    sube        TEXT NOT NULL,
    ders        TEXT NOT NULL,
    gun         SMALLINT NOT NULL CHECK (gun BETWEEN 1 AND 7),
    baslangic   TIME NOT NULL,
    bitis       TIME NOT NULL,
    ogretmen_id BIGINT REFERENCES ogretmen(id),
    tahta_id    INTEGER,
    aktif       BOOLEAN NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_ders_programi_tahta_id ON ders_programi(tahta_id);
CREATE INDEX IF NOT EXISTS idx_yillik_plan_kazanim_kod ON yillik_plan(kazanim_kod);
