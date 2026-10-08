# Soru havuzu: her soru bir kazanımla — tasarım (2026-10-08)

Kapsam: `soruhavuzu/` (PostgreSQL `soru_havuzu`), tüketici olarak `kazanimtest/`
ve dashboard servis ekranı. Kullanıcı kararı (2026-10-08): "sorular kazanımla
eşleştirilip üretilsin, her zaman soru ve kazanım beraber ele alınsın";
yaklaşım = **geri doldurma + kazanım öncelikli üretim**; kapsam = **yalnızca
yıllık planı olan (düzey, ders)**.

## 1. Neden

2026-10-08 04:03 kapsam ölçümü (`benchmark/kazanim_kapsam`, bge-m3, eşik 0,55,
`/mnt/farabi-data/farabi/kazanim_testleri/rapor/kapsam.json`): yıllık plandaki
**1110 hafta-kazanımın 44'ü** için ≥10 uygun onaylı soru var, 422 zayıf,
**644'ünde hiç yok**. Kök neden yapısal: `uretici.uret(birim)` kitap sayfa
grubundan kazanımı bilmeden üretir; `soru` tablosunda kazanım sütunu yok,
eşleştirme kazanım testi anında benzerlikle (`kazanimtest/secici.py`) yapılıyor.

Başarı ölçütü: aynı ölçümde "yeterli" hafta sayısı her gece artar; ilk hafta
sonunda yaklaşan 4 haftanın tüm planlı kazanımları yeterli (≥10 onaylı).

## 2. Veri modeli (`soruhavuzu/sema.sql`, idempotent `ALTER ... IF NOT EXISTS`)

```sql
CREATE TABLE IF NOT EXISTS kazanim (
    id      serial PRIMARY KEY,
    sinif   smallint NOT NULL,
    ders    text NOT NULL,              -- soruhavuzu.dersler anahtarı (kimya, cografya…)
    hafta   smallint NOT NULL,          -- plan haftası (kazanimlar.json anahtarı)
    kod     text,                       -- 'KİM.9.1.3' (metinden; yoksa NULL)
    metin   text NOT NULL,
    UNIQUE (sinif, ders, hafta, metin)
);
ALTER TABLE soru ADD COLUMN IF NOT EXISTS kazanim_id integer REFERENCES kazanim(id);
ALTER TABLE soru ADD COLUMN IF NOT EXISTS kazanim_skor real;
ALTER TABLE soru ADD COLUMN IF NOT EXISTS kazanim_kaynak text
    CHECK (kazanim_kaynak IN ('uretim', 'etiket'));
CREATE INDEX IF NOT EXISTS soru_kazanim_idx ON soru (kazanim_id, durum);
```

- Kaynak: `tahtayoklama/data/kazanimlar.json` (`kazanim_yukle.py` çıktısı). Bir
  haftadaki `\n` ile ayrılmış birden çok kazanım ayrı satır; ders adı
  `soruhavuzu/dersler.py` eşlemesinden geçer (eşlenemeyen ders atlanır, sayılır).
- Aynı kazanım birden çok haftaya yayılıyorsa (ör. `DEVAM_HAFTALARI`) her hafta
  ayrı satır, ama üretim/etiketleme **metin+sınıf+ders** üzerinden tekilleşir
  (aynı metin iki kez üretilmez).
- Komut: `python -m soruhavuzu.calistir kazanim-yukle [--kuru]`; plan değişince
  yeniden çalıştırılır (UPSERT, silmez).

## 3. Geri doldurma (bir kerelik) — `calistir etiketle [--kuru]`

- Her `durum='onayli'` ve `kazanim_id IS NULL` soru için aynı (sinif, ders)
  kazanımları arasından bge-m3 kosinüsle en yakını; gömme bilgehan
  (`uzak_model.toplu_gomme_modeli`, 2026-10-04 kararı — Farabi CPU'su RAG için
  kullanılmaz). Soru metni = `soru + doğru şık`.
- Skor ≥ 0,55 → `kazanim_id`, `kazanim_skor`, `kazanim_kaynak='etiket'`;
  altı etiketsiz kalır (oyunlarda kullanılmaya devam eder).
- `--kuru`: yazmaz; (sinif, ders) başına etiketlenen / etiketsiz sayısı + skor
  dağılımı basar. Gerçek çalıştırma önce kullanıcıya bu çıktıyla sunulur.

## 4. Kazanım öncelikli üretim (gece) — `calistir uret`

Eski `vt.siradaki_birim` (kitap sayfa grubu) döngüsü **kapanır**; yerine:

1. **Sıra** (`vt.siradaki_kazanim`): yalnızca planlı (sinif, ders); önce okul
   takviminde bu hafta + sonraki 3 haftanın kazanımları (`kazanimlar.json`
   `haftalar` → pazartesi tarihi), sonra onaylı+üretildi soru sayısı en az olan.
   Hedef: kazanım başına **10 onaylı**; `uretildi` (denetim bekleyen) + `onayli`
   ≥ 14 olan kazanım atlanır (denetim reddi payı). Aynı turda bir kazanım
   en çok 2 kez denenir.
2. **Kaynak bulma**: o (sinif, ders) kitabının `chunk_egitim` parçaları
   arasından kazanım metnine en yakın 3 parça (farabi DB, pgvector, bilgehan
   bge-m3 ile sorgu vektörü; `kitap_id` filtresi). Kitap yoksa ya da en iyi
   skor < 0,45 → kazanım `kaynak_yok` işaretlenir (üretilmez, raporlanır).
3. **Kaynak birimi**: seçilen parçalar `kaynak_birim`e `tur='kitap'`,
   `anahtar='kazanim:<kazanim_id>:<chunk_idler>'` ile yazılır (denetçi aynı
   KAYNAK metnini görür; mevcut şema yeterli).
4. **Üretim istemi** (`uretici.istem_kazanim`): sistem istemi aynı (MEB lise
   öğretmeni, Türkçe, 4 şık, tek doğru); kullanıcı istemine "KAZANIM: <kod>
   <metin>" + kaynak metin + "Her soru bu kazanımı ölçmeli; kazanımla ilgisiz
   ama metinde geçen bilgiyi sorma." 5 soru/çağrı (bugünkü çıktı boyutu).
5. Kayıt: `vt.soru_ekle(..., kazanim_id=k, kazanim_kaynak='uretim')`;
   `kazanim_skor` = soru ile kazanım arasındaki kosinüs (bilgi amaçlı).
6. Korunanlar: ders saati penceresi (`zaman.uretim_serbest`), kopya eleme
   (`tekrar.Eleyici` ≥0,92), Ollama 500 tekrar, tek kazanımın hatası geceyi
   durdurmaz, artımlı denetim bütçesi, E2BIG düzeltmesi (`ISTEM_AZAMI_BAYT`).

## 5. Denetim (AGY) — `denetci.istem`

- Soru bloğuna `Kazanım: <kod> <metin>` satırı (varsa) eklenir; kural metnine:
  "Kazanımı belirtilmiş soru o kazanımı ölçmüyorsa GEÇERSİZ (neden: kazanım dışı)."
- Kazanımsız eski `uretildi` sorular eski kuralla denetlenir.

## 6. Tüketiciler

- `kazanimtest/secici.havuz_adaylari`: önce `kazanim_id` ile eşleşen onaylı
  sorular (o haftanın kazanım satır(lar)ı); yetmezse bugünkü benzerlik
  aramasına düşer. Yanıt şekli değişmez.
- Arena (`havuz.jeopardy_seti`, `petek_sorulari`): değişmez (ileride kazanım filtresi).
- `benchmark/kazanim_kapsam`: `kazanim_id` sayımı ek sütun olarak raporlar.

## 7. Dashboard bağlantısı (dashboard planına girer)

`/servisler` soru havuzu kartı: zamanlayıcı aç/kapat + şimdi çalıştır (spec
2026-10-08-dashboard…), **son hata** (birim `failed` ise journal'ın son
Traceback'inin son satırı, ör. `OSError: [Errno 7] Argument list too long`),
**kazanım kapsamı** (yeterli / zayıf / boş, `calistir durum --json` çıktısından).

## 8. Test (pytest, `soruhavuzu/tests`, gerçek DB'ye değil test DB fixture'ına)

- `kazanim-yukle`: çok satırlı hafta bölünür, ders eşlenir, ikinci çalıştırma
  satır çoğaltmaz.
- `etiketle`: eşik altı etiketsiz kalır; sahte gömücüyle doğru kazanım seçilir;
  `--kuru` yazmaz.
- `siradaki_kazanim`: yaklaşan hafta önce; hedefe ulaşmış kazanım atlanır;
  plansız ders hiç gelmez.
- Üretim: sahte Ollama + sahte kaynak bulucu → sorular `kazanim_id`'li yazılır;
  `kaynak_yok` işaretlenir.
- Denetim istemi kazanım satırını içerir.
- `kazanimtest.secici`: `kazanim_id` eşleşmesi benzerlikten önce gelir.

## 9. Sıralama ve riskler

1. `soruhavuzu/calistir.py`, `vt.py` ve birim dosyasında **başka bir oturumun
   commit'lenmemiş değişiklikleri** var — uygulama onlar commit'lendikten sonra
   başlar.
2. Şema → kazanim-yukle → etiketle (`--kuru` → kullanıcı onayı → gerçek) →
   kazanım öncelikli üretim → denetim istemi → kazanimtest seçici → kapsam ölçümü.
3. Risk: kitapta kazanıma uygun parça yoksa (`kaynak_yok`) o kazanım boş kalır —
   raporda görünür, ayrı karar (ör. YKS/kazanım testi PDF'lerinden kaynak).
4. Risk: üretim hızı — bugün ~5 soru/birim/çağrı; 1066 boş/zayıf kazanım × 3
   çağrı ≈ birkaç gece. Sıra yaklaşan haftaları önce bitirir.
