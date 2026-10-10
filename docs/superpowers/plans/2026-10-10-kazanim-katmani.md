# Kazanım Katmanı Düzeltmesi (soru bankası) — Plan

> Uygulayıcı: Sonnet (Kural 11), canlı göç adımları Opus. Onaydan önce kod yazılmaz (Kural 6).

**Amaç:** Soru bankasında her kazanım bir kez, doğru sınıfta, doğru programda ve kalıcı bir kodla dursun;
haftalık plan ayrı bir takvim olsun. Sorular bu tekil kazanımlara bağlansın.

**Kapsam sınırı:** Yalnızca `soruhavuzu/` (+ `kazanimtest/secici.py`, `benchmark/kazanim_kapsam*.py` uyumu).
`tahtayoklama/data/kazanimlar.json` ve onu okuyan tahta/yoklama/Farabi koduna DOKUNULMAZ.

## Teşhis (2026-10-10, canlı DB)

| # | Sorun | Kanıt |
|---|---|---|
| 1 | Programlar tek derse katlanıyor | `kazanimlar.json` programları ayrı tutuyor (`hedef fizik`, `hedef kimya`, `hedef tarih`, `inkılap tarihi ve atatürkçülük`, `çağdaş türk ve dünya tarihi`, `ortak türk tarihi`) ama `soruhavuzu/kazanimlar.oku` → `dersler.ders_anahtari` hepsini `fizik`/`kimya`/`tarih` yapıyor. 12. sınıf fizik/kimya/tarih altında 9-10-11 kodlu 84 kazanım; 10. sınıf tarih altında 33 Ortak Türk Tarihi kazanımı. |
| 2 | Yanlış kitap → boş üretim | 12 tarih "9.3.3 Orta Çağ…" → İnkılap kitabı; 10 tarih Ortak Türk Tarihi → Tarih 10 kitabı. Teşhiste model `{"sorular": []}` döndürdü. Gece 2.651 denemenin 865'i boş. |
| 3 | Kazanım = hafta satırı | 1.559 satır, 915 tekil metin. 19 etiketli soru grubun "tek" satırı dışındaki bir satıra bağlı (sayım kaçağı). |
| 4 | Kod okunmuyor | `KOD_RE` "TDE1.3." ve "ENG.9.2.L1"/"E12.2.L1." biçimlerini kaçırıyor: edebiyat 138/138, İngilizce 141/141 kodsuz. |
| 5 | Yanlış sınıfa bağlı sorular | 106 soru (36 onaylı etiket: fizik 22, tarih 10, kimya 4; 70 yeni üretim 12 tarih). |

## Hedef veri modeli

```
kazanim            -- TEKİL: bir kazanım bir satır
  id (korunur), sinif, ders (oyun/rapor anahtarı: tarih, fizik…), program (kaynak ders adı:
  "tarih", "inkılap tarihi ve atatürkçülük", "ortak türk tarihi", "çağdaş türk ve dünya tarihi"…),
  kod (NULL olabilir), metin, durum ('aktif','kaynak_yok')
  UNIQUE (sinif, program, metin)
kazanim_takvim     -- yıllık plan haftası (bir kazanım birden çok hafta/sınıf takviminde)
  kazanim_id → kazanim(id), takvim_sinif, program, hafta
  UNIQUE (kazanim_id, takvim_sinif, program, hafta)
```

- **Hedef temelli programlar** (`hedef fizik|kimya|tarih`): kendi kazanımını üretmez. Kodun sınıfı
  (9.x → 9) ve dersiyle asıl kazanım aranır (önce `kod` eşleşmesi, yoksa metin); bulunursa yalnızca
  takvim satırı eklenir (`takvim_sinif=12, program='hedef tarih'`). Bulunamazsa kazanım `sinif=kod sınıfı`
  ile oluşturulur. Böylece 12. sınıfa "hedef" haftalarında 9-11 soruları önceliklenir ama sorular asıl
  sınıf kazanımına yazılır.
- **Kitap seçimi programa göre:** `kaynak.kitap_idleri(sinif, program)`. `inkılap…` → İnkılap kitabı;
  `ortak türk tarihi`, `çağdaş…` → kitap yok → `kaynak_yok` (boş üretim denemesi biter). `tarih` (9-11)
  → Tarih kitabı.
- **Kod:** `KOD_RE` genişletilir: `TDE1.3`, `ENG.9.2.L1`, `E12.2.L1`, `KİM.9.1.1`, `10.1.3` yakalanır.

## Görevler

### Görev 1 — Okuyucu: program + kod (`kazanimlar.py`, `dersler.py`)
- `oku()` her satıra `program` (json'daki ders adı, küçük harf) ekler; `ders` anahtarı aynı kalır.
- `hedef_mi(program)`; hedef satırlarına `kod_sinif` (kodun sınıfı) eklenir.
- `KOD_RE` genişletmesi + testler (yukarıdaki 5 biçim, "HÖREN 1." kod değil).

### Görev 2 — Şema + göç (`sema.sql`, `vt.py`, yeni `gocler/2026-10-10-kazanim-tekil.sql` ya da Python göç fonksiyonu)
- `kazanim.program`, `kazanim_takvim` tablosu.
- Göç (tek işlem, `--kuru` destekli `calistir kazanim-goc`):
  1. Her (sinif, ders, metin) grubu için kanonik id = mevcut `DISTINCT ON … ORDER BY hafta, id` satırı
     (üretim bağlantılarının tamamı zaten bu satırda; 19 etiket kaçağı buna taşınır).
  2. Diğer satırlar → `kazanim_takvim`; sorular kanonik id'ye; fazla satırlar silinir.
  3. `program` doldurulur (json'dan yeniden okunarak), hedef satırları asıl sınıf kazanımına birleştirilir.
  4. Yanlış sınıfa bağlı 106 soru: kazanım bağı korunur (artık doğru, asıl sınıf kazanımı), ancak
     `soru.sinif` ≠ `kazanim.sinif` olanlar raporlanır; 70 üretim sorusu (12 tarih ↔ İnkılap kaynağı)
     `durum='askida'` yapılır — kaynağı kazanımla uyumsuz üretildi.
  5. Göç öncesi `pg_dump soru_havuzu` yedeği `/mnt/farabi-data/farabi/soru_havuzu/yedek/` altına.
- `kazanim_upsert` → tekil upsert + takvim satırı.

### Görev 3 — Tüketiciler
- `vt.siradaki_kazanim`: hafta önceliği `kazanim_takvim`'den (takvim_sinif bu hafta ± 3); hedef = tekil
  kazanım başına soru sayısı (DISTINCT ON kalkar).
- `kaynak.kitap_idleri(sinif, program)`; `uret` kazanımın `program`'ını geçirir.
- `etiketle`, `siniflandir`: aday kümesi tekil `kazanim` (DISTINCT ON kalkar).
- `kazanimtest/secici.kazanim_adaylari`: `k.metin = ANY(...)` aynı kalır (metin tekil satırda); test.
- `benchmark/kazanim_kapsam*.py`: tekil kazanım sayımı.

### Görev 4 — Canlı göç (Opus)
1. Gece üretimi çalışmıyorken (`systemctl is-active soru-havuzu-uret` = inactive).
2. Yedek → `kazanim-goc --kuru` çıktısı kullanıcıya → onay → `kazanim-goc`.
3. Doğrulama: satır sayıları (tekil ≈ 915 − birleşen hedef), kodsuz sayısı, 0 sayım kaçağı, testler.
4. `DECISIONS.md`, `soruhavuzu/CLAUDE.md`.

## Kabul
- `soruhavuzu/tests`, `kazanimtest/tests` geçer.
- Canlıda: her (sinif, program, metin) tek satır; 12. sınıf fizik/kimya/tarih altında 9-11 kodlu kazanım 0;
  edebiyat/İngilizce kodsuz oranı < %10; `soru.kazanim_id` hepsi var olan satıra işaret eder.
- Sonraki gece: 10/12 tarih boş üretim denemesi ~0 (kaynak_yok ya da doğru kitap).

## Risk / geri dönüş
- Göç tek işlem; hata → otomatik geri alma. Sonradan sorun → `pg_dump` yedeğinden `soru_havuzu` geri yüklenir.
- `kazanim.id` korunur → kazanimtest'in önceki formları (soru id + metin kopyası saklı) etkilenmez.
