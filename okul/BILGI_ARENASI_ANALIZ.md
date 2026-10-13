# Bilgi Arenası — Aşama 1 Analiz Raporu

Tarih: 2026-10-13. Kapsam: yalnızca inceleme; kaynak kod değiştirilmedi. Her iddia aşağıdaki dosyalardan veya
salt-okunur sorgulardan (yalnızca toplu sayılar, öğrenci verisi okunmadı) alınmıştır. **Doğrulanmayan** noktalar
açıkça işaretlidir.

## 0. Yönetici özeti (önce bunu oku)

1. **Soru Maratonu zaten var ve Arena'nın çekirdeğini büyük ölçüde karşılıyor.** Sunucu tarafında puanlama, cevap
   anahtarının cevaptan önce gizlenmesi, tekrar gönderim koruması, soru tekrarını azaltan seçim, seri ve haftalık
   liderlik mevcut. **KARAR (kullanıcı, 2026-10-13): iki mod, tek çatı.** Soru Maratonu "Hızlı Mod" olarak aynen
   kalır; Bilgi Arenası "Günlük Görev" modu olarak eklenir; ikisi ortak XP/seviye/rozet katmanını besler (bkz. 6.1).
2. **Soru açıklaması (explanation) veri modelinde yok.** Postgres `soru` tablosunda `aciklama` benzeri bir sütun
   yok. Brief'in "açıklama yoksa uydurma" kuralı gereği Arena MVP'si yalnızca doğru/yanlış + doğru şık gösterir.
3. **Kazanım bağı var ama zayıf ve belirsiz.** `soru.kazanim_id` onaylı soruların %65–85'inde dolu; dolayısıyla
   kazanım bazlı sonuçlar "kesin" değil, "güvenilirlik düzeyiyle" sunulmalı (bkz. 3.4).
4. **Öğrencinin mevcut kazanım hesabı metin anahtarlı**, `kazanim_id` anahtarlı değil. Arena sonuçlarını mevcut
   kazanım ekranına bağlamak için bir eşleme kararı gerekir (bkz. 6).
5. **Kullanıcıdan karar gerektiren çakışmalar** bölüm 9'da: 12. sınıf dondurması, ders saati kilidi, mevcut
   Maraton'un herkese açık liderliği, görsel tema.

## 1. Mevcut mimari

| Katman | Gerçek durum (kanıt) |
|---|---|
| Backend | FastAPI 0.143, uvicorn 0.54 (tek süreç; `systemd/farabi-okul.service` `--workers` içermiyor), Jinja2 3.1 şablonları, sunucu taraflı render |
| Frontend | Vanilla CSS (`static/okul.css`, "kareli defter" teması, tek tasarım sistemi) + küçük vanilla JS dosyaları (`maraton.js`, `saat.js`, `foto.js`, `kurulum.js`, `nabiz.js`). Build sistemi, framework, CDN yok |
| Veritabanı | SQLite `veri/okul.db` (WAL, `busy_timeout=5000`, `foreign_keys=ON`), ORM yok, ham SQL. Şema `db.GOCLER` listesi + `PRAGMA user_version`, her göç tek `BEGIN…COMMIT` |
| Dış veri | PostgreSQL `soru_havuzu` **yalnızca SELECT** (`kaynaklar/kazanim.py::_baglan`, `set_session(readonly=True)`); yoklama SQLite'ı, ders programı/zil JSON dosyaları |
| Auth | Şifre scrypt, `oturum` tablosu (token SHA-256 özeti, 1 yıl kayan çerez), CSRF = oturumdan türetilen token (`auth.csrf_token`), giriş deneme sınırlama (`giris_deneme`, 5 hata/15 dk → 60 sn bekleme) |
| PWA | `static/sw.js` (yalnızca statik dosyalar önbellekte, HTML asla), `manifest.webmanifest`, çevrimdışı sayfa |
| Test | `pytest` (160 test geçiyor), `conftest.py` autouse `gecici_ortam` tüm yolları `tmp_path`'e yönlendirir. **Tarayıcı otomasyonu yok** (venv'de playwright/selenium yok) |
| Lint | Kökten `.venv-tools/bin/ruff` (okul/ kapsam listesinde değil; dokunulan dosya verilir) |
| Bildirim | **Öğrenciye yönelik bildirim altyapısı yok** (push/e-posta yok). SMS yalnızca veli giriş kodu için (`kaynaklar/sms.py`) |
| Dağıtım | `farabi-okul.service` yeniden başlatma; canlı üretim sunucusu (`/home/ata/farabi` master = deploy kaynağı) |

Not: bu oturumda eklenen **kullanım analitiği** (`analitik.py`, `SEMA_V4`) henüz commit/deploy edilmedi. Arena göçü
V5 olacağından V4'ün önce üretime alınması (veya sıranın bilinçli seçilmesi) gerekir.

## 2. Roller ve yetkilendirme

- Roller: `ogrenci`, `veli`, `ogretmen`, `yonetici` (`kullanici.rol` CHECK kısıtı).
- Rota koruması: `deps.rol(*roller, post=False)`; rol uymazsa **404** (varlık sızdırılmaz), `post=True` CSRF doğrular.
  Öğrenci rotaları `OGRENCI = rol("ogrenci")` kullanır (`rotalar/ogrenci.py`, `rotalar/oyun.py`).
- Öğrenci kimliği istemciden alınmaz: `mevcut_kullanici` oturum çerezinden çözer; `ogrenci` kaydı
  `ogrenci.kullanici_id` ile bağlanır (`_kendisi()` yoksa 404). Sınıf bilgisi `ogrenci.sinif` ("9-A" biçimi).
- Sahiplik kontrolü kalıbı: `maraton.getir(conn, id, kullanici_id)` başkasının kaydında `None` → 404.
- Öğretmen/yönetici yetkisi `yetki.py` (tek yetki merkezi); Arena öğrenci verisi öğretmene/yöneticiye **açılmayacak**
  (isteğe bağlı toplu, kişisiz özet hariç, bkz. 8).

## 3. Kazanım / soru / test veri modeli

### 3.1 Soru kaynağı
Postgres `soru_havuzu.soru` (kolonlar: `id, ders, sinif(smallint), konu, soru, kisa_cevap, secenekler(jsonb),
dogru_index, zorluk(1–4), kaynak, durum, kazanim_id, kazanim_skor, kazanim_kaynak, kullanim_sayisi, …`).
Maraton'un kullandığı süzgeç: `durum='onayli' AND secenekler IS NOT NULL AND dogru_index IS NOT NULL AND
jsonb_array_length(secenekler) >= 2` (`kaynaklar/soru.py::_FILTRE`).

Onaylı soru sayıları (salt-okunur sayım): 9. sınıf 4370, 10. sınıf 4752, 11. sınıf 4483, **12. sınıf 7846**.

### 3.2 Açıklama
`aciklama`/`gerekce` sütunu **yok**. `kisa_cevap` dolu (ortalama 17 karakter, en uzun 1053) ama bunun bir *açıklama*
mı yoksa kısa doğru cevap metni mi olduğu **doğrulanmadı**; örneklenmeden gösterilmemeli. `denetim_notu` iç
denetim notudur, öğrenciye gösterilmemeli.

### 3.3 Cevap kontrolü
Sunucuda. Maraton, soruları havuzdan `maraton_soru`'ya **kopyalar** (`dogru_index` dahil), şablon yalnızca cevap
sonrası doğru şıkkı döndürür (`oyun.py::cevap`). Ödev testleri (`odev_soru.dogru`) de sunucuda puanlanır
(`odevler.test_teslim_et`). İstemcide doğru cevap kontrolü yok.

### 3.4 Kazanım ilişkisi
- Havuz içi: `soru.kazanim_id → kazanim(id)`; `kazanim` tablosunda `kod`, `metin` (metin "KOD. açıklama" biçiminde),
  `sinif`, `ders`, `hafta`, `durum` (`aktif` / `kaynak_yok`). 9–11. sınıfta 938 aktif kazanım var.
- Kapsam: onaylı sorularda `kazanim_id` dolu oranı 9: %81, 10: %81, 11: %74, 12: %35. **Atama kaynağı ağırlıkla LLM**
  (`kazanim_kaynak`: llm 10623, etiket 2422, uretim 408, boş 7998). `kazanim_skor ≥ 0.5` olan soru sayısı sınıf
  başına yalnızca ~1000–1200. → Kazanım bazlı çıkarımlar "tahmini eşleşme" olarak etiketlenmeli.
- Derinlik (9–11): 507 farklı kazanımda soru var; kazanım başına medyan 16, en az 1, en çok 129 soru.
  `almanca`, `gorsel_sanatlar` (9–11), `ingilizce` (10, 11) ve `felsefe` (11) derslerinde `kazanim_id` hiç yok
  (0 dolu) → bu derslerde kazanım çeşitliliği garanti edilemez.
- **Öğrencinin mevcut kazanım hesabı farklı anahtar kullanır:** `kaynaklar/kazanim.ozet()` Google Form testlerini
  (`form_testi.kazanim`, serbest metin, bazen çok satırlı) ve platform ödev testlerini (`odev_soru.kazanim`, metin)
  `(ders, kazanım metni)` anahtarıyla birleştirir; başarı eşiği `AYAR.kazanim_esik = 0.7`. Örneklenen 3 tek
  kazanımlı `form_testi` kaydında metin `kazanim.metin` ile birebir eşleşti (**örneklem çok küçük, genelleme
  doğrulanmadı**).
- Maraton `maraton_soru` tablosuna `kazanim_id` **yazmıyor** (`soru_id, konu, kaynak` yazıyor); yanlış yapılan
  kazanım yalnızca `soru_id → Postgres` join'iyle sonradan bulunabilir.

### 3.5 Sonuç saklama
- Ödev testi: `odev_teslim` (öğrenci başına tek kayıt, `cevaplar` JSON, `puan`).
- Maraton: `maraton` + `maraton_soru` (SEMA_V3): `cevap` NULL=bekliyor, ≥0 şık, −1 süre doldu, −2 terk.
- Form testi: Postgres `form_cevap` (okul_no ile, platform dışı).

## 4. Yeniden kullanılabilecek servisler

| Parça | Yer | Arena'da kullanım |
|---|---|---|
| Soru çekme + tekrar azaltma | `kaynaklar/soru.py::sorular(sinif, ders, haric_ids, n, gorulme)` | Temel; **kazanım çeşitliliği ve `kazanim_id` dönmüyor** → genişletme gerekir |
| Görülmüş soru sayacı | `maraton.gorulme(conn, kullanici_id)` | Mantık kopyalanır (Arena kendi tablosundan) |
| Çift puanlamaya karşı koruma | `UPDATE … WHERE cevap IS NULL` + `rowcount != 1 → rollback` (`maraton.cevapla`) | Aynen kalıp |
| Zaman | `zaman.simdi()` (Europe/Istanbul, naive), testlerde yamalanır | Gün sınırı = yerel 00:00 |
| Ders saati kilidi | `maraton.kilit()` (zil çizelgesi) | Politika kararı (bkz. 9) |
| Hata/yetki | `HTTPException(404)` kalıbı, `db_conn`, `render` | Aynen |
| Statik varlık sürümü | `okul.css?v=N`, `sw.js` SURUM/STATIK | Aynen |
| Olay sayacı | `analitik.kaydet` / `OZELLIKLER` (yeni, uncommitted) | Arena olayları buraya eklenir |

## 5. Eksikler ve teknik riskler

1. **Açıklama verisi yok** → geri bildirim yalnızca doğru/yanlış (4.2).
2. **Kazanım eşlemesi LLM kaynaklı** → "Kazanım Ustası" gibi rozetler kesin ustalık iddiası taşımamalı; birden çok
   günde, birden çok soruyla ve eşiğe bağlı olmalı; belirsizlik metni gerekir.
3. **Yeterli soru yok durumları gerçek:** `MIN_SORU=10`; ders×sınıf bazında yetersiz havuz Maraton'da zaten
   `MaratonHatasi("Bu derste yeterli soru yok.")` verir. Arena'da 5 soru için eşik düşer ama aynı güvenli çıkış gerekir.
4. **Genel hız sınırlama yok** (yalnızca giriş denemeleri). Arena'da çoğaltma riski, hız sınırından değil **idempotent
   durum makinesinden** karşılanmalı (Maraton kalıbı); ek istek başına sınır gerekiyorsa sonraki aşamada.
5. **Geri alınabilir göç:** proje yalnızca ileri göç kullanır (down göç yok). Yeni göç yalnızca `CREATE TABLE/INDEX`
   olacağı için mevcut veriye dokunmaz; geri alma = tabloları DROP + `user_version` düşürme, bir betik + yedek
   (`sqlite3 .backup`) ile belgelenmeli. Bu, projenin mevcut yaklaşımından bir sapmadır, onay gerekir.
6. **Çakışma:** `soru_kullanim.oyun` içinde `sinif_arena` (tahta tarafı, 48 kayıt), `hexafetih`, `duello` var;
   `kullanim_sayisi` o oyunların alanıdır (kod yorumları: "arena'nın alanları"). Okul portalı bu tabloya **yazmaz**
   (kural). Adlandırma karışıklığı için SQLite tablolarında `arena_` yerine `bilgi_` önerilir ve UI adı "Bilgi Arenası" kalır.
7. **Tarayıcı testi yok:** mobil taşma/erişilebilirlik için otomatik test altyapısı yok. Seçenek: `chrome` MCP ile
   elle doğrulama ve raporlama; kalıcı otomasyon yeni bağımlılık gerektirir (onay).
8. **Kirli çalışma ağacı:** `kaynaklar/soru.py` (almanca eklendi) ve `soruhavuzu/*` bu işten bağımsız değişiklikler;
   Arena'nın `soru.py` genişletmesiyle karışmamalı.
9. **Eşzamanlılık:** tek uvicorn süreci + SQLite WAL; yine de kalıcı garanti `UNIQUE` kısıtları ve
   `INSERT OR IGNORE`/koşullu `UPDATE` ile verilmeli (süreç sayısına güvenilmemeli).

## 6. Önerilen oyun mimarisi

### 6.1 Karar: Bilgi Arenası = tek çatı, iki mod

| | Hızlı Mod (mevcut Soru Maratonu) | Günlük Görev (yeni Arena modu) |
|---|---|---|
| Kural | Değişmez: 10 soru x 30 sn, hız puanı | 5 soru, süre baskısı yok, günde bir tur |
| Sonuç | Mevcut tur puanı + haftalık liderlik (olduğu gibi) | Doğru/yanlış, yanlışlarda kazanım özeti |
| Ortak katman | **XP, seviye, rozet** (yeni, kişisel) | **XP, seviye, rozet** |
| Günlük hedef | Sayılmaz | Tek "günlük görev" budur |

- **Giriş:** tek merkez ekran `/ogrenci/arena` (iki kart: Günlük Görev, Hızlı Mod). Mevcut `/ogrenci/maraton*` ve
  `/ogrenci/liderlik` URL'leri **aynen çalışır** (geriye uyum, SW/yer imleri bozulmaz). Ana sayfadaki Maraton kartı
  merkez ekrana bağlanır.
- **Maraton'a tek dokunuş:** `rotalar/oyun.py::cevap` içinde tur bittiği an (`sonuc["bitti"]`) XP defterine
  idempotent kayıt: `arena.xp_ver(kaynak='maraton_tur', ref=maraton_id)`; UNIQUE kısıtı çift ödülü engeller. `maraton.py`
  sorguları (`liderlik`, `seri`, `_TAMAM`) **değişmez**. Terk edilen tur XP vermez.
- **Maraton XP kuralı (öneri, onay bekliyor):** hız puanı (100–190/soru) XP değildir; XP = tamamlanan turda doğru
  sayısı x 10 (Günlük Görev ile aynı oran), **günlük tavan 2 Hızlı Mod turu** (anlamsız tekrarı teşvik etmemek için).
  Rozet/XP için **geçmiş Maraton turları geriye dönük işlenmez**; XP yayın tarihinden itibaren birikir.
- **Günlük katılım/rozet:** yalnızca Günlük Görev turu "anlamlı etkinlik" sayılır; "İlk 50 Doğru" Arena + Hızlı Mod
  doğrularının toplamıdır (yayın tarihinden itibaren); "Kazanım Ustası" yalnızca Günlük Görev'dir, çünkü
  `maraton_soru` tablosunda `kazanim_id` yok.
- **Liderlik:** Hızlı Mod'un haftalık liderliği olduğu gibi kalır (kısa ad). XP, seviye ve rozet **hiçbir sıralamada
  yer almaz**. (Liderliğin brief'in "küçük düşüren sıralama olmasın" ilkesiyle gerilimi bölüm 9'da karar bekliyor.)
- **Ders saati kilidi:** Hızlı Mod'da mevcut kilit sürer. Günlük Görev için karar bekliyor (bölüm 9).

**Öneri: Arena'yı Maraton'dan ayrı, hafif bir modül olarak yap; Maraton'un tablolarına ve sorgularına dokunma.**
Gerekçe: `maraton.liderlik/seri/_TAMAM` tüm `maraton` satırlarını sayar; aynı tabloya Arena turu eklemek bu
sorguları bozar veya her birine `mod` süzgeci gerektirir (regresyon riski).

- `arena.py` (iş kuralları: görev, tur, XP, seviye, rozet) — saf, `maraton.py` üslubunda, `zaman.simdi()` kullanır.
- `arena_ayar` (modül düzeyi sabitler, `ayarlar.py`'ye değil modül başına; bkz. 8): tur başına 5 soru, doğru başı 10 XP,
  tamamlama bonusu 10 XP, seviye eşikleri listesi, rozet koşulları. `AYAR` dataclass'ı yol/ortam içindir; oyun
  sabitlerini oraya taşımak testlerde yamalamayı zorlaştırır. Alternatif: `AYAR`'a alan eklemek (karar bekliyor).
- `kaynaklar/soru.py::arena_sorulari(...)`: `kazanim_id` ve `kazanim kodu` dönen, mümkünse **farklı kazanımlardan**
  seçen yeni fonksiyon (mevcut `sorular()` imzası değişmez).
- `rotalar/arena.py` + `templates/ogrenci/arena*.html` + `static/arena.js` (cevap sonrası geri bildirim için küçük JS,
  JS'siz form akışı yedek — Maraton gibi).
- Soru seçimi: öğrencinin sınıf düzeyi (9–11), seçili/atanmış ders(ler), daha önce görülmeyenler, kazanım çeşitliliği.
  Günlük görevin dersi: kurala bağlı (örn. öğrencinin bugünkü programındaki ders → yoksa en az çalışılan ders);
  tam kural karar bekliyor (bkz. 9).
- Cevap anahtarı **istemciye gitmez**; tur başlarken sorular `okul.db`'ye kopyalanır (Maraton gibi); doğru şık
  yalnızca cevaptan sonra döner. Havuz sonradan değişse de tur tutarlı kalır.

## 7. Yeni tablo ihtiyacı (SEMA_V5, yalnızca ekleme)

Mevcut tabloların hiçbiri Arena'nın XP/rozet/günlük görev ihtiyacını karşılamıyor (kontrol edildi: `maraton*`
puanı tur içi hız puanıdır, kalıcı XP/seviye yok; rozet/görev tablosu yok).

```
bilgi_tur       id, kullanici_id → kullanici, gun (YYYY-MM-DD, yerel), sinif, ders, basla, bitis NULL,
                durum('acik','tamam','terk'), dogru, xp
                UNIQUE (kullanici_id, gun)   -- günde bir günlük mücadele; ödül çoğaltmayı DB seviyesinde engeller
bilgi_cevap     tur_id → bilgi_tur ON DELETE CASCADE, sira, soru_id, kazanim_id NULL, kazanim_kod NULL, soru,
                secenekler(JSON), dogru_index, konu, cevap NULL, cevap_zamani, PK(tur_id, sira)
bilgi_xp        id, kullanici_id, kaynak('arena_dogru','arena_bonus','maraton_tur'), ref (tur/maraton id), miktar, gun, zaman
                UNIQUE (kullanici_id, kaynak, ref)  -- XP defteri; toplam = SUM, seviye hesaplanır (saklanmaz)
                -- Maraton günlük tavanı: aynı gun için kaynak='maraton_tur' satır sayısı <= 2 (iş kuralı + test)
bilgi_rozet     kullanici_id, rozet_kodu, kazanma_zamani, PK(kullanici_id, rozet_kodu)
INDEX bilgi_tur(kullanici_id, gun), bilgi_cevap(soru_id), bilgi_xp(kullanici_id)
```
- Toplam XP/seviye türetilir (defterden), böylece "istemciden gelen XP'ye güvenme" ve tutarlılık kendiliğinden sağlanır.
- Ayrı "istatistik" tablosu yok: toplamlar `bilgi_xp`/`bilgi_cevap` sorgularından; performans sorun olursa sonra eklenir.
- Silme: kullanıcı silinmez (yalnızca `aktif=0`); `bilgi_cevap` tura bağlı CASCADE.
- Günlük görev ayrı tablo değil: `bilgi_tur` satırı (UNIQUE(kullanici_id, gun)) görev + tur kaydıdır. İlk sürüm için
  gereksiz karmaşıklık yok.

## 8. API, ekran ve analitik planı (`/ogrenci/arena` altında, `OGRENCI` rolü, tümü 404/CSRF kalıbında)

| Metot / yol | İş | Sözleşme |
|---|---|---|
| GET `/ogrenci/arena` | Merkez ekran: seviye, XP, **Günlük Görev** kartı + **Hızlı Mod** (Maraton) kartı, son tur özeti, tekrar çalışma bağlantısı | 200; havuz erişilemezse "şu an alınamıyor" kartı (diğer kartlar çalışır) |
| POST `/ogrenci/arena/basla` | Bugünün turunu başlat/devam ettir | Aynı gün ikinci kez → mevcut tura yönlendirir (yeni tur/ödül yok); soru yetersiz → 200 sade mesaj, tur oluşmaz |
| GET `/ogrenci/arena/{id}` | Sıradaki soru | Sahip değilse 404; bitmişse sonuca yönlendirir |
| POST `/ogrenci/arena/{id}/cevap` | Cevap gönder | Geçersiz şık 400; aynı soruya ikinci gönderim 409 ve **XP yok** (`WHERE cevap IS NULL`) |
| GET `/ogrenci/arena/{id}/sonuc` | Sonuç + yanlış inceleme + kazanım özeti | Bitmemişse soruya yönlendirir |
| GET `/ogrenci/arena/ilerleme` | XP, seviye, rozetler, haftalık özet | Yalnızca kendi verisi |

- Tamamlama tek işlemde: son cevap → tur `tamam` + bonus XP `INSERT OR IGNORE` (UNIQUE) → rozet koşulu kontrolü.
  Ayrı "tamamla" endpoint'i yok; böylece tekrar gönderimle çift ödül yolu kapanır.
- Analitik: `analitik.OZELLIKLER`'e `arena_goruntule`, `arena_basla`, `arena_tamamla` (+ terk, tekrar çalışma geçişi)
  eklenir; **içerik/cevap kaydedilmez**. Ürün metrikleri (başlayan, tamamlayan, ertesi gün dönen, yanlış
  yaptığı kazanımda tekrar çalışan) `bilgi_tur`/`bilgi_cevap` verisinden hesaplanır, bu veri **akademik başarı
  göstergesinden ayrı** raporlanır. Geçmişe dönük veri uydurulmaz; tüm oranlar yayın tarihinden başlar.
- Gizlilik: Arena'da **herkese açık sıralama ve isim yok**. (Mevcut Maraton liderliği kısa ad gösteriyor; bu
  ayrı karar, Arena ile karıştırılmayacak.)
- Öğretmen/yönetici: ilk sürümde Arena'ya erişim yok. İleride yalnızca sınıf düzeyinde toplu/kişisiz özet (küçük
  grup eşiğiyle).

Zaman: gün sınırı `zaman.simdi().date()` (Europe/Istanbul 00:00); testler `zaman.simdi`'yi yamalar. Seri, kaçırılan
gün için ceza uygulamaz; ilk sürümde "Beş Gün Katılım" toplam gün sayısıdır (ardışık zorunlu değil), seri **eklenmez**.

Rozet koşulları (sunucuda test edilebilir): İlk Arena Turu = ilk `tamam` tur; Beş Gün Katılım = 5 farklı günde
`tamam` tur (yalnızca giriş sayılmaz); İlk 50 Doğru Cevap = toplam doğru ≥ 50; Kazanım Ustası = **belirsizlik
nedeniyle önerilen tanım:** aynı `kazanim_id`'den, en az 3 ayrı günde, toplam ≥ 6 sorunun ≥ %80'i doğru (tek doğru
cevap kalıcı edinim sayılmaz; `kazanim_id` olmayan sorular sayılmaz).

## 9. Kullanıcıdan karar bekleyen konular

1. **12. sınıf:** proje kuralı "ikinci emre kadar dokunulmaz". Maraton şu an 12. sınıfa da açık görünüyor
   (`maraton.duzey` herhangi bir düzeyi kabul eder; **12. sınıf öğrencisi olup olmadığı veritabanından kontrol
   edilmedi**). Öneri: Arena yalnızca 9–11.
2. **Ders saati kilidi:** Maraton ders sırasında kapalı (`maraton.kilit`). Arena için aynı kural mı?
3. **Görsel tema:** istenen koyu lacivert/neon, mevcut açık "kareli defter" temasından farklı. Öneri: yalnızca
   `.arena` kapsayıcısında koyu tema değişkenleri (mevcut `.oyun` sınıflarını genişleterek), kontrast WCAG AA.
4. **Göç geri alma betiği** (bölüm 5.5) ve sabitlerin yeri (modül sabitleri vs `AYAR`).
5. **Günlük görev dersi seçim kuralı** (bölüm 6).
6. **Hızlı Mod liderliği:** olduğu gibi mi kalsın, yoksa isimsiz/yalnızca kendi sıran gibi yumuşatılsın mı? (Varsayılan: olduğu gibi kalır.)
   **Maraton XP kuralı:** doğru x 10 XP, günde en fazla 2 tur — onay?
7. **Tarayıcı otomasyonu** yeni bağımlılık gerektirir; bunun yerine manuel (chrome MCP) doğrulama kabul mü?

## 10. Aşamalı geliştirme ve test planı

| Aşama | İçerik | Test / doğrulama |
|---|---|---|
| 0 | Bekleyen: analitik (V4, **üretimde çalışıyor ama commit edilmedi**) ve kirli ağaç temizliği | mevcut 160 test |
| 1 | Bu analiz | — |
| 2 | UI taslağı: `.arena` tema değişkenleri, statik HTML maketi (sunucu mantığı yok) | mobil genişlik elle kontrol |
| 3 | `SEMA_V5` + `arena.py` iş kuralları (XP, seviye, görev, rozet) | birim testleri: XP formülü, seviye eşikleri, UNIQUE çift ödül, gün sınırı (yamalı saat), yarım/tam tur ayrımı, eksik soru |
| 4 | `kaynaklar/soru.py::arena_sorulari` + rotalar + günlük görev akışı | web testleri: yetkisiz 404, başkasının turu 404, geçersiz şık, tekrar cevap, paralel istek (iki iş parçacığı), havuz erişilemez |
| 5 | Sonuç ekranı, yanlış inceleme, kazanım özeti. **Hızlı Mod XP kancası** (`oyun.py::cevap`, idempotent, günlük tavan) | sonuç doğruluğu; Maraton turu bitince XP bir kez; tekrar gönderim ve terk XP vermez; mevcut 19 maraton testi değişmeden geçer |
| 6 | Rozet + ilerleme ekranı | rozet koşul testleri, kazanım rozeti belirsizlik |
| 7 | Analitik olayları + ürün metrikleri | olay tekilleştirme, metrik sorguları |
| 8 | Güvenlik, erişilebilirlik, mobil, regresyon | tüm mevcut testler; klavye/odak/aria elle (chrome MCP); göç testi: V4 veritabanı üzerinde V5 uygulanır, mevcut satırlar korunur |
| 9 | Dağıtım: `sqlite3 .backup`, `systemctl restart farabi-okul` (onayla), geri alma betiği | canlıda kısa duman testi |

Her aşamada: değiştirilen dosyalar, gerekçe ve **çalıştırılan** testler raporlanır; çalıştırılmayan test başarılı
sayılmaz. Yüksek riskli adımlar (üretim göçü, yeniden başlatma) için onay istenecektir.

## 11. Bu analizin sınırları

- Öğrenci düzeyinde veri okunmadı (yalnızca havuz sayıları); gerçek öğrenci/12. sınıf dağılımı ölçülmedi.
- `kisa_cevap` içeriği ve `form_testi.kazanim ↔ kazanim.metin` eşleşmesi küçük örnekle bakıldı, genellenemez.
- Sayfa performansı ve düşük donanımlı telefon davranışı ölçülmedi (kural: ölçmeden optimizasyon yok).
