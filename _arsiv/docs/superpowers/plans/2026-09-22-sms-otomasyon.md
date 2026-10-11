# Zamanlanmış SMS Otomasyonu (Doğum Günü 08:00 + Devamsızlık 09:00) — Uygulama Planı

**Tarih:** 2026-09-22
**Durum:** Plan — hiçbir faz uygulanmadı.
**Plan modeli:** Opus (Kural 11). Uygulama: Sonnet, faz faz.
**Kapsam:** `smssistemi/` (ana iş) + `tahtayoklama/dashboard/`'a TEK yeni okuma endpoint'i.
**İlgili:** kök `CLAUDE.md` (Kural 3/5/8 + "Frontend / Dashboard Tasarım Standartları"),
`smssistemi/CLAUDE.md`, `tahtayoklama/CLAUDE.md`,
`docs/superpowers/plans/2026-09-20-dogum-gunleri-modulu.md`

---

## 0. Ne yapılacak (tek paragraf)

smssistemi servisine, dashboard'daki `_polling_dongusu` desenini birebir
taklit eden tek bir `asyncio` zamanlayıcı döngüsü eklenir. Bu döngü iki iş
çalıştırır: **(A)** her gün 08:00'de, o gün doğan ÖĞRENCİ ve PERSONELe
(veli değil) tebrik SMS'i; **(B)** okul günlerinde 08:55'te 1. dersin
yoklamasını yoklama panosundan HTTP ile okuyup gelmeyen öğrencilerin
velilerine gidecek mesajları hazırlar, panelde gösterir ve **09:00'da
kimse iptal etmediyse** gönderir. Gönderim her zaman mevcut
`_gonderim_calistir` → `sms_gonderici.toplu_gonder` yolundan geçer; ikinci
bir gönderim yolu açılmaz (Kural 5). Varsayılan olarak **kuru çalıştırma
(dry-run) AÇIK** gelir — ilk devreye alışta tek bir SMS bile gitmez.

---

## 1. Temel alınan doğrulanmış gerçekler

Bunlar bu oturumda canlı DB/dosya üzerinden doğrulandı, plan bunlara dayanıyor:

| Olgu | Değer |
|---|---|
| Telefonu olan öğrenci | 101'de **23** |
| Telefonu olan personel | 23'te **1** |
| Veli kaydı | 46 (hepsi bir öğrenciye bağlı) ama yalnızca **25 farklı öğrenciyi** kapsıyor |
| Pilot sınıflar | **10-A** (18 öğrenci), **12-A** (6 öğrenci) — verisi tam olan tek iki sınıf |
| 1. ders | 08:10–08:50 (`tahtayoklama/data/zil.json`) |
| 2. ders | 09:00–09:40 → 08:55 hazırlığı teneffüse denk geliyor |
| Yoklama poll aralığı | `dashboard/app.py:43 POLLING_ARALIGI_SN = 120` |
| Gerçek `kaydedilme_saati` (1. ders) | 08:15 / 08:17 / 08:44 / 08:50:19–08:50:22 |
| `yoklama_onbellek.durum` dağılımı (8 gün) | `alindi` 361, `ders_yok_o_gun` 56, `alinmadi` 26, `tahta_ulasilamaz` 5 |
| İsim eşleşmesi (yalnız `ad_soyad`) | **101/101** |
| İsim+sınıf eşleşmesi | 98/101 — 3 kayıtta sınıf çelişkisi (yazım hatası DEĞİL) |
| Her iki servis de | `User=ata`, `journal_mode=wal`, aynı makine |
| Yoklama sorgusu maliyeti | **0,244 ms** (bağlan+sorgula+kapat, 1000 tekrar), sunucu load avg 0,21 / 24 thread |

⚠️ **`smssistemi/CLAUDE.md`'de bir yanlış satır var:** "/dogum-gunleri
… tek tıkla doğum günü SMS tebriği gönderme" yazıyor ama `app.py`'de böyle
bir route, `dogum_gunleri.html`'de böyle bir form **YOK** (doğrulandı: o
sayfadaki tek POST'lar `/dogum-gunleri/ayarlar` ve
`/dogum-gunleri/kisi/{id}/tarih`). Doğum günü gönderimi bu planda **ilk kez
inşa ediliyor**. Faz 5'te CLAUDE.md'nin bu satırı da düzeltilmeli.

⚠️ `ayarlar` tablosundaki `sms_otomatik='0'` bugün yalnızca **saklanan bir
bayrak** — ona bağlı çalışan hiçbir zamanlayıcı yok. Bu plan onu gerçek bir
ana şaltere dönüştürüyor.

---

## 2. Tasarım kararı D1 — İki servis arasındaki okuma

### Karar: **Dashboard'a yeni bir HTTP endpoint eklenir.** (Kullanıcıyla tartışıldı, onaylandı.)

Üç seçenek değerlendirildi:

| Seçenek | Artı | Eksi | Sonuç |
|---|---|---|---|
| **(a) Doğrudan SQLite salt-okunur** (`file:…yoklama_pano.db?mode=ro`) | Dashboard'a hiç dokunulmaz (Kural 3/5 açısından en ucuz); ağ yok, auth yok; teknik olarak mümkün (aynı kullanıcı `ata`, dosya izni `-rw-r--r--`) | Dosya yolu bağımlılığı; WAL modundaki bir DB'yi başka süreç yazarken `mode=ro` ile açmak `-shm` dosyasına yazma izni ister (aralıklı `SQLITE_CANTOPEN` riski); **asıl kusur:** `durum`un 6 değerinin anlamı ve `izinli_isimleri` düşümü yoklama servisinin ALAN BİLGİSİdir — smssistemi'ye kopyalanırsa mantık iki yere dağılır, biri güncellenmeyi unutulursa **sessizce yanlış veliye "çocuğunuz gelmedi" gider**; ayrıca okuyucu taze veri talep EDEMEZ | ❌ RED |
| **(b) İki servisi birleştir** | Tek süreç, tek DB, köprü yok | Arıza yarıçapı: SMS yolu kırılgan (WifiHttpProxy.exe elle başlatılan bir .exe, servis değil, kronik `BadStatusLine` geçmişi) ve para harcıyor; yoklama ise 2 dk'da bir 7 tahtaya SSH atan operasyonel servis — birleşirlerse SMS kaynaklı bir hata/restart yoklama izlemeyi de durdurur. Ayrıca Kural 6 (büyük refactor + onay), iki ayrı venv, iki ayrı test çatısı (pytest ↔ unittest) | ❌ RED |
| **(c) Dashboard'da HTTP endpoint** | Yorumlama (durum + izinli düşümü) sahibinde kalır, tek yerde; `?taze=1` ile **çağrıda bulunan taraf taze bir tarama tetikleyebilir** → 120 sn'lik bayatlık payı tamamen ortadan kalkar; ulaşılamazlık açık bir hata sinyali olur (fail-closed'ı mümkün kılar); auth deseni zaten kurulu (HMAC/SSO) | Dashboard'a dokunmak gerekir (küçük, additive); ağ çağrısı bir hata yüzeyi ekler (zaman aşımı yönetilmeli) | ✅ **SEÇİLDİ** |

**"Performans gerekçesiyle doğrudan DB" argümanı kapatıldı:** sorgu maliyeti
0,244 ms, iş günde **1 kez** çağırıyor, load avg 0,21/24 thread, tek makine
— tek instance olduğu için load balancing kavramı hiç devreye girmiyor.
Yük bu kararda bir kısıt değildir.

**"İki servis kod paylaşmaz" kuralı veri okumayı kapsar mı?** Kural, *kod*
paylaşımını yasaklar (ortak modül import'u, ortak DB dosyası). İki servis
arasında zaten sözleşmeli bir bağ var: `/sms-git` ve `/dogum` route'ları +
paylaşılan HMAC anahtarı. HTTP endpoint bu mevcut deseni genişletir, ihlal
etmez — bağ **sözleşme** düzeyindedir, **uygulama** düzeyinde değil. Doğrudan
DB okuması ise tam tersine şema düzeyinde gizli bir bağ kurardı.

### 2.1 Endpoint sözleşmesi

```
GET /api/yoklama/gelmeyenler?tarih=YYYY-MM-DD&ders_no=1&t=<zaman>&s=<imza>[&taze=1]
```
Yanıt (200):
```json
{
  "tarih": "2026-09-22",
  "ders_no": 1,
  "uretim_zamani": "2026-09-22T08:55:04+03:00",
  "taze_tarama_yapildi": true,
  "siniflar": [
    {"sinif": "10-A", "veri_var": true, "durum": "alindi",
     "kaynak_tahta": "10-A", "kaydedilme_saati": "08:44:12",
     "gelmeyenler": ["Ali Veli"], "izinli_sayisi": 1, "aciklama": null},
    {"sinif": "12-A", "veri_var": false, "durum": "tahta_ulasilamaz",
     "kaynak_tahta": null, "kaydedilme_saati": null,
     "gelmeyenler": [], "izinli_sayisi": 0,
     "aciklama": "Tahtaya ulaşılamadı — yoklama okunamadı."}
  ]
}
```

Kurallar:
- `veri_var` **yalnızca** `durum == 'alindi'` iken `true`. Diğer beş durumda
  (`alinmadi`, `tahta_ulasilamaz`, `tahta_atanmamis`, `henuz_baslamadi`,
  `ders_yok_o_gun`) `false` ve `gelmeyenler` **her zaman boş dizi** —
  çağıran taraf ham `durum`u yorumlamak zorunda kalmaz.
- `gelmeyenler` = `yok_isimleri` − `izinli_isimleri` (düşüm **dashboard'da**
  yapılır; izinli öğrencinin velisine "gelmemiştir" gitmez).
- `aciklama` Türkçe, insan-okunur tek cümledir; panelde doğrudan gösterilir.
- Kimlik doğrulama: **yeni mekanizma icat edilmez**, mevcut HMAC/SSO deseni
  kullanılır (`dashboard/config/sms_sso.json` ↔ `smssistemi/config/sso.json`,
  aynı anahtar). Dashboard'a `auth.sms_sso_dogrula(t, s)` (smssistemi'deki
  `sso_dogrula`'nın aynadaki eşi), smssistemi'ye `auth.sso_token()`
  (dashboard'daki `sms_sso_token`'ın eşi) eklenir. Her iki fonksiyon da
  ~10 satır, mevcut kopyalanmış-desen konvansiyonuna uygun.
  Geçerlilik 30 sn (mevcut `SSO_GECERLILIK_SN`), aynı makine olduğu için
  saat kayması sorun değil.
- Oturum çerezi de kabul edilir (tarayıcıdan elle açılıp bakılabilsin diye):
  `auth.dogrula(request, conn) or auth.sms_sso_dogrula(t, s)`.
- `taze=1` verilirse okumadan önce `await yoklayici.bir_tur_calistir(conn, tarih)`
  çalıştırılır. Bu, dashboard'un kendi 120 sn'lik poll'üyle eşzamanlı
  koşabilir — `yoklama_onbellek` UPSERT'i idempotent ve `alindi`'yi koruyan
  `WHERE` kilidine sahip olduğu için güvenlidir.
- Okuma, `/api/durum`'un SELECT'inin ikinci bir kopyası olmamalı: sorgu
  `devamsizlik_ozeti.py` içindeki tek fonksiyondan geçer.

### 2.2 Fail-closed davranışı (kusur değil, istenen davranış)

Dashboard'a ulaşılamazsa (bağlantı hatası, 401, zaman aşımı, bozuk JSON):
**o gün devamsızlık mesajı GÖNDERİLMEZ.** Koşu `kacirildi` durumuna geçer,
panelde "Yoklama servisine ulaşılamadı — mesaj gönderilmedi" olarak
gösterilir, `print("[otomasyon] …")` ile journal'a düşer. Veli telefonuna
yanlışlıkla giden tek bir mesaj, gitmeyen bir mesajdan çok daha pahalıdır.

İstemci iki aşamalı dener: önce `taze=1` (zaman aşımı 30 sn — SSH taraması
sürebilir), o başarısızsa `taze` olmadan önbellekten (zaman aşımı 5 sn); o da
başarısızsa `YoklamaUlasilamadi` fırlatılır → `kacirildi`.

---

## 3. Tasarım kararı D2 — Bekleyen gönderim (iptal penceresi) nerede saklanacak

### Karar: **İki yeni tablo** (`CREATE TABLE IF NOT EXISTS`, migration adımı yok).

Bellek kesinlikle kullanılamaz: 08:58'deki bir restart pencereyi ya kaybeder
ya çift gönderime yol açar.

`gonderimler.durum` serbest metin olduğu için oraya `bekliyor`/`iptal`
yazmak cazip ama **iki somut engel** var:
1. `gonderimler`de `kisi_id` **yok** ve hiçbir UNIQUE kısıt yok — "aynı kişiye
   aynı gün ikinci kez gönderme" kilidi ifade edilemez.
2. `gonderimler.telefon TEXT NOT NULL` — "telefon yok" atlama satırı
   saklanamaz. Oysa panelde atlananları göstermek kullanıcının açık isteği.

Ayrıca mevcut gönderim yolu (`toplu_gonder` → `kaydet` → `gonderim_kaydet`)
her satır için **yeni INSERT** yapar; önceden `bekliyor` satırı koysaydık aynı
`gonderim_id` altında mükerrer satırlar oluşurdu ve `kayitlar` sayfasının
özetleri bozulurdu (Kural 5 ihlali).

Bu yüzden: **koşu durumu ve hedef/atlama listesi yeni tablolarda tutulur,
gerçek gönderim satırları her zamanki gibi `gonderimler`e yazılır** ve ikisi
`gonderim_id` ile bağlanır. `kayitlar`/`durum` sayfaları hiç değişmeden
otomasyon gönderimlerini de gösterir.

```sql
CREATE TABLE IF NOT EXISTS otomasyon_kosulari (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    is_turu            TEXT NOT NULL,   -- 'dogum' | 'devamsizlik'
    tarih              TEXT NOT NULL,   -- İSTANBUL yerel tarihi, YYYY-MM-DD
    durum              TEXT NOT NULL,   -- hazirlaniyor|bekliyor|gonderiliyor|
                                        -- gonderildi|iptal|kacirildi|atlandi|hata
    kuru               INTEGER NOT NULL DEFAULT 0,
    gonderim_id        TEXT,            -- gonderimler.gonderim_id ile bağ
    hedef_sayisi       INTEGER NOT NULL DEFAULT 0,
    atlanan_sayisi     INTEGER NOT NULL DEFAULT 0,
    gonderilen_sayisi  INTEGER NOT NULL DEFAULT 0,
    hata_sayisi        INTEGER NOT NULL DEFAULT 0,
    planlanan_gonderim TEXT,            -- '2026-09-22T09:00:00+03:00'
    hazirlik_zamani    TEXT,
    bitis_zamani       TEXT,
    not_metni          TEXT,
    UNIQUE (is_turu, tarih)             -- ← "bugün zaten yapıldı" koruması
);

CREATE TABLE IF NOT EXISTS otomasyon_hedefleri (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kosu_id     INTEGER NOT NULL REFERENCES otomasyon_kosulari (id),
    is_turu     TEXT NOT NULL,
    tarih       TEXT NOT NULL,
    kisi_id     INTEGER,      -- ALICI (veli / kutlanan kişi). Atlananlarda NULL olabilir.
    ad_soyad    TEXT NOT NULL,-- alıcı adı; atlananlarda ilgili kişinin adı
    telefon     TEXT,         -- atlananlarda NULL
    sinif       TEXT,
    ilgili_ad   TEXT,         -- devamsızlıkta öğrencinin adı (veli mesajı için)
    mesaj       TEXT,
    durum       TEXT NOT NULL,-- bekliyor|gonderildi|hata|iptal|atlandi|kuru
    neden       TEXT,         -- atlama nedeni kodu (aşağıdaki sabit liste)
    hata_metni  TEXT,
    UNIQUE (is_turu, tarih, kisi_id)    -- ← aynı kişiye aynı gün ikinci mesaj yok
);
```

Notlar:
- SQLite'ta UNIQUE içindeki NULL'lar birbirinden farklı sayılır; `kisi_id IS NULL`
  olan **atlama** satırları bu kilidin dışında kalır (istenen davranış —
  hazırlık zaten günde bir kez, koşu satırıyla korunuyor).
- `_AYARLAR_VARSAYILAN` sözlüğü `INSERT OR IGNORE` ile yazıldığı için yeni
  ayar anahtarları **canlı DB'ye bir sonraki restart'ta güvenli varsayılanla**
  düşer; ayrı bir migration adımı gerekmez.
- **Tüm zaman damgaları İstanbul-aware ISO metin olarak Python'dan yazılır.**
  `datetime('now')` (UTC) KULLANILMAZ — yoksa panelde "hazırlık 05:55" görünür.
  (Mevcut `gonderimler.zaman` UTC'dir; panelde onunla bu tablonun zamanları
  yan yana gösterilmemeli.)

### 3.1 "Bugün zaten gönderildi" koruması ve durum makinesi

```
   (yok)
     │ 08:55 hazırlık
     ▼
hazirlaniyor ──► bekliyor ──► gonderiliyor ──► gonderildi
     │              │                │
     │              ├──► iptal       └──► hata
     │              │   (insan bastı)
     ├──► atlandi   └──► (09:00 geçti, iptal yok → gonderiliyor)
     │   (hedef yok / pilot sınıf yok / okul günü değil)
     └──► kacirildi (servis geç ayağa kalktı, yoklama alınamadı, dashboard yok)
```

- Koşu satırı **tarih anahtarlıdır** (`UNIQUE(is_turu, tarih)`). Servis 09:00'da
  restart olursa satır zaten `gonderildi`/`gonderiliyor` olduğu için ikinci kez
  gönderilmez.
- Gönderime geçiş **atomik durum geçişiyle** yapılır:
  `UPDATE … SET durum='gonderiliyor' WHERE is_turu=? AND tarih=? AND durum='bekliyor'`
  → `cursor.rowcount == 1` ise devam edilir, değilse hiçbir şey yapılmaz.
- **`gonderiliyor`da kalmış bir koşu ASLA otomatik yeniden denenmez** (gönderim
  ortasında çökme). Panelde sarı "Yarım kalmış olabilir — `/kayitlar`'dan
  kontrol edin" uyarısı çıkar, gerekirse insan `/tekrar-gonder`'i kullanır.
  Çift korkutmaktansa eksik göndermek tercih edilir.

---

## 4. Tasarım kararı D3 — Zamanlayıcı döngüsü, uyanma sıklığı, kaçan iş

**Kural 8 gereği APScheduler / Celery / cron / systemd timer KULLANILMAZ.**
`tahtayoklama/dashboard/app.py:46-76`'daki desen birebir taklit edilir:
`lifespan` içinde `asyncio.create_task(...)` ile sonsuz bir döngü.

```python
OTOMASYON_ARALIGI_SN = 30   # uyanma sıklığı
```
30 sn'lik uyanma, 09:00 gönderimini en fazla 09:00:29'a kaydırır — kabul
edilebilir. Daha sık uyanmak gereksiz (döngü uyanışta yalnızca 2 küçük
SELECT yapıyor).

`smssistemi/app.py` bugün `@app.on_event("startup")` kullanıyor (deprecated).
Faz 4'te dashboard'la aynı `lifespan` desenine çevrilir; `db.semayi_kur()`
çağrısı aynen korunur (davranış değişmez).

### 4.1 Karar fonksiyonu saf tutulur (testin can damarı)

```python
# otomasyon.py — ağ/DB yok, yalnızca karar
def ne_yapmali(simdi: datetime, ayarlar: dict, kosular: dict) -> list[str]
```
`kosular = {"dogum": <koşu satırı|None>, "devamsizlik": <koşu satırı|None>}`.
Döndürdüğü eylem kodları: `dogum_gonder`, `devamsizlik_hazirla`,
`devamsizlik_gonder`, `devamsizlik_kacirildi`, `dogum_kacirildi`.
Bu fonksiyon donmuş saatlerle (08:00, 07:59, 08:55, 08:57, 09:00, 09:16,
cumartesi, ana şalter kapalı …) `sleep` olmadan tamamen test edilir.

### 4.2 Doğum günü işi — zamanlama

- Hedef saat: `dogum_gonderim_saati` (varsayılan `08:00`).
- **`okul_gunu_mu()` UYGULANMAZ** — hafta sonu/tatil ayrımı yok, her gün gider
  (kullanıcı kararı).
- Kaçma toleransı: `dogum_gecikme_toleransi_dk` (varsayılan `240` = 12:00'ye
  kadar). Servis 09:30'da ayağa kalkarsa doğum günü mesajı **yine gider**
  (gecikmeli kutlama zararsızdır), koşuya `not_metni='gecikmeli'` yazılır.
  Tolerans aşılmışsa koşu `kacirildi` olur ve panelde görünür.

### 4.3 Devamsızlık işi — zamanlama ve kaçan iş mantığı

- `devamsizlik_gonderim_saati` (varsayılan `09:00`),
  `devamsizlik_hazirlik_dk` (varsayılan `5`) → hazırlık 08:55.
- **`okul_gunu_mu(bugün)` BU İŞE UYGULANIR** (yalnızca Pazartesi-Cuma).
  Hafta sonu hiç koşu satırı açılmaz. (Bu, doğum günü işinin tersi —
  ikisini karıştırma.)
- Hazırlık penceresi `[hazırlık_saati, gönderim_saati)`:
  - Servis bu pencere içinde uyanırsa → normal hazırlık, `bekliyor`.
  - Servis pencereyi kaçırıp **gönderim saatinden sonra** ilk kez uyanırsa
    (ör. 08:57 restart 09:01'de tamamlandı): koşu satırı **`kacirildi`**
    açılır, mesaj gönderilmez, panelde "Hazırlık penceresi kaçırıldı"
    yazar ve **"Şimdi Hazırla"** butonu görünür (insan onaylı kurtarma).
    Otomatik gecikmeli gönderim BİLEREK yapılmaz: 09:40'ta düşen bir
    "öğrenciniz okula gelmemiştir" mesajı çoktan derse girmiş bir öğrenci
    için yanlış olur. (Bkz. AÇIK SORULAR §13.3.)
  - `bekliyor` durumundaki bir koşu, gönderim saati geçtiğinde `gonderiliyor`a
    atomik geçişle taşınır. Servis 08:58'de restart olsa bile satır DB'de
    `bekliyor` durduğu için 09:00'da gönderim yine yapılır — **pencere
    restart'a dayanıklıdır**, bunun tek nedeni durumun DB'de olmasıdır.
  - `bekliyor` koşusu gönderim saatinden **çok** sonra bulunursa
    (`devamsizlik_gonderim_gecikme_toleransi_dk`, varsayılan `15`) gönderilmez,
    `kacirildi` olur. Yani servis 11:00'de ayağa kalkarsa sabahki bekleyen
    gönderim otomatik fırlamaz.

---

## 5. Tasarım kararı D4 — Panel / iptal düğmesi

### 5.1 Yeni sayfa: `/otomasyon` (smssistemi, port 8020)

`taban.html` navigasyonuna "Otomasyon" girişi eklenir
(`<use href="#ik-zil"/>` — sprite'ta **mevcut**, yeni ikon gerekmez).
Kim görecek: smssistemi'nin mevcut tek ortak şifresiyle giren herkes; ayrı
rol/yetki modeli YOK (mevcut desen, bilinçli).

Sayfa sırası kök CLAUDE.md'deki hiyerarşiye uyar
(**Başlık > birincil eylem > KPI > tablo**):

1. **Başlık** — "Otomasyon" + sağda ana şalter rozeti
   (`rozet-yesil` "Otomasyon açık" / `rozet-gri` "Kapalı") ve kuru mod açıkken
   tüm sayfanın üstünde `rozet-turuncu` şerit:
   **"KURU ÇALIŞTIRMA AÇIK — hiçbir SMS gönderilmiyor."**
2. **Bugünün devamsızlık koşusu kartı** (`kart-vurgulu`):
   - Durum rozeti + geri sayım ("Gönderime 3 dk 12 sn").
   - **Büyük kırmızı "Gönderimi İptal Et" butonu** — yalnızca `durum='bekliyor'`
     iken etkin; 09:00 geçtikten sonra `disabled` olur ve yerine
     "Gönderildi (N alıcı)" / "İptal edildi" / "Kaçırıldı" metni geçer.
     Tıklayınca `confirm()` onayı ister (yanlışlıkla basmayı önler).
   - Hedef tablosu: Veli · Telefon · Öğrenci · Sınıf · Mesaj önizleme.
   - Atlananlar tablosu: Kişi · Sınıf · **Neden** (Türkçe etiket).
     ⚠️ `pilot_disi` satırları **tek tek listelenmez** — her sabah 5 sınıf için
     kalıcı gürültü olurdu. Tek bir katlanmış satırda özetlenir:
     "Pilot dışı: 5 sınıf (9-A, 9-B, 11-A, 11-B, 12-B) — otomasyon kapalı".
   - Sınıf bazında veri durumu şeridi: "10-A ✓ yoklama alındı (08:44) ·
     12-A ✗ tahtaya ulaşılamadı → mesaj gönderilmedi".
3. **Bugünün doğum günü koşusu kartı** — gönderilenler + "telefon yok" listesi.
4. **Ayarlar bölümü** (form → `POST /otomasyon/ayarlar`): ana şalter, kuru mod,
   iki işin ayrı açma/kapaması, pilot sınıf listesi (virgülle ayrık metin
   kutusu — **kod değişikliği olmadan sınıf eklenebilir**), saatler, şablonlar.
5. **Son 14 günün koşu geçmişi** tablosu.

Boş durumlar (`empty-state`): "Bugün doğum günü olan kimse yok." /
"Bugün 1. derste gelmeyen öğrenci bulunmadı — mesaj gönderilmeyecek."
Özür dileyen değil, ne olduğunu söyleyen metin.

**Beklenen hacim panelde açıkça yazılmalı:** 23/101 öğrenci ve 1/23 personel
telefonu olduğu için tipik bir sabah **0-1 doğum günü gönderimi + birkaç
"telefon yok" satırı** demektir. Atlananlar belirgin gösterilmezse kullanıcı
"çalışmıyor" sonucuna varır.

CSS: **ham hex renk yazılmaz**; mevcut `stil.css` token'ları
(`--renk-yesil/-amber/-kirmizi/-gri` ve `-zemin` karşılıkları) ile hazır
sınıflar (`.rozet-*`, `.kart-*`) kullanılır. CDN yok, yeni yazı tipi yok,
yeni punto değeri uydurulmaz. Geri sayım animasyonu eklenirse
`prefers-reduced-motion` bloğu da eklenir (kök CLAUDE.md uyarısı).

### 5.2 Endpoint'ler

| Yöntem | Yol | İş |
|---|---|---|
| GET | `/otomasyon` | HTML sayfa |
| GET | `/api/otomasyon/bugun` | Panelin polladığı JSON (koşular + hedefler + atlananlar + kalan saniye) |
| POST | `/api/otomasyon/devamsizlik/iptal` | `bekliyor → iptal` atomik geçiş; `{"iptal_edildi": true|false}` |
| POST | `/api/otomasyon/devamsizlik/simdi-hazirla` | Elle hazırlık (kaçırılan koşu kurtarma / kuru modda test) |
| POST | `/otomasyon/ayarlar` | Ayar formu (mevcut `/dogum-gunleri/ayarlar` deseniyle aynı) |

Polling: `durum='bekliyor'` iken 5 sn, diğer hâllerde 30 sn
(mevcut `durum.html` polling deseni izlenir).

### 5.3 Dashboard'dan erişim

Yoklamayı izleyen kişi büyük ihtimalle 08:55'te **8010**'a bakıyordur, 8020'ye
değil. Bu yüzden dashboard'a mevcut `/dogum` route'unun birebir eşi olan
`/otomasyon` yönlendirmesi (HMAC SSO ile `:8020/sso?…&hedef=/otomasyon`) ve
sol menüye bir link eklenir — 5 satır, kanıtlanmış desen.
Dashboard panosuna canlı geri sayım şeridi eklemek **kapsam dışı** (ters yönde
ikinci bir servis çağrısı gerektirir).

⚠️ Dürüst uyarı: 5 dakikalık pencere, ekrana o anda bakan biri yoksa fiilen
"iptal yok" demektir. `devamsizlik_hazirlik_dk` bir **ayar** olduğu için
pencere yalnızca yapılandırmayla 8-10 dakikaya çıkarılabilir; `taze=1`
sayesinde hazırlık artık 120 sn'lik poll'e bağımlı değil, yani erken hazırlık
veri tazeliğini bozmaz. Karar kullanıcıya bırakıldı → §13.2.

---

## 6. Tasarım kararı D5 — Emniyet kilitleri (hepsi zorunlu)

Sırayla kontrol edilir; herhangi biri düşerse gönderim yapılmaz:

1. **Ana şalter** — `ayarlar.sms_otomatik != '1'` → döngü hiçbir iş yapmaz
   (koşu satırı bile açmaz). Tek satırlık kapatma şalteri budur.
2. **İş bazlı şalter** — `dogum_otomasyon` / `devamsizlik_otomasyon` ayrı ayrı.
3. **Kuru mod** — `otomasyon_kuru='1'` iken modem HİÇ çağrılmaz.
4. **Gün kontrolü** — devamsızlık: `zil`den taşınan `okul_gunu_mu` mantığı
   (Pazartesi-Cuma); doğum günü: kontrol YOK.
5. **Veri kilidi** — `veri_var == false` (yani `durum != 'alindi'`) olan sınıf
   için **hiçbir mesaj üretilmez**; o sınıf panelde "veri yok" olarak görünür.
   Bu **sınıf bazındadır**: 10-A `alindi` iken 12-A `tahta_ulasilamaz` olabilir
   → 10-A gönderilir, 12-A atlanır. Toptan iptal DEĞİL.
6. **İzinli düşümü** — dashboard tarafında yapılır (§2.1).
7. **Pilot sınıf kilidi** — sınıf `devamsizlik_pilot_siniflar` listesinde
   değilse hiç işlenmez (10-A, 12-A ile başlar).
8. **Tekil eşleşme kilidi** — öğrenci adı `kisiler`de **tam olarak 1** kayıtla
   eşleşmezse (0 veya >1) o öğrenci atlanır ve loglanır. Aynı adlı iki
   öğrenci yüzünden yanlış veliye mesaj gitmesi kabul edilemez.
9. **Günde tek mesaj kilidi** — `UNIQUE(is_turu, tarih, kisi_id)`.
10. **Telefon kilidi** — telefonu olmayan kişiye mesaj yok; doğum gününde
    **veliye yönlendirme YAPILMAZ** (kullanıcı kararı), "telefon yok" olarak
    listelenir. Aynısı personel için de geçerli.
11. **Fail-closed** — yoklama servisi ulaşılamazsa gönderim yok (§2.2).

### 6.1 Atlama nedeni kodları (sabit liste, panelde Türkçe etiketiyle gösterilir)

| Kod | Panel etiketi |
|---|---|
| `pilot_disi` | Pilot dışı sınıf |
| `yoklama_verisi_yok` | Yoklama alınmadı / okunamadı |
| `roster_eksik` | Sınıf listesinde numara karşılığı yok |
| `ogrenci_bulunamadi` | Rehberde öğrenci kaydı yok |
| `ad_belirsiz` | Aynı adlı birden fazla öğrenci — elle kontrol gerekli |
| `veli_yok` | Öğrenciye bağlı veli kaydı yok |
| `veli_telefonu_yok` | Veli telefonu boş |
| `telefon_yok` | Telefon yok (doğum günü) |

`pilot_disi` yalnızca `devamsizlik_pilot_siniflar` **boş değilken** üretilir
ve panelde sınıf başına değil, tek bir özet satırında gösterilir (§5.1).
Liste boşaltılırsa (tüm okul kapsama alınırsa) bu neden hiç üretilmez.

⚠️ **`roster_eksik` ayrı bir neden olmak zorunda:** dashboard'un
`yoklayici._yok_isimlerini_coz` fonksiyonu roster'da numara bulamazsa
`"No 12"` gibi bir metin üretir. Bu metin hiçbir zaman `kisiler.ad_soyad` ile
eşleşmez. `^No\s+\d+$` deseni önceden yakalanmazsa bir roster boşluğu,
"öğrenci bulunamadı" ile aynı görünür ve kimse gidip düzeltmez.

### 6.2 Çoklu veli ve kardeş durumu

46 veli yalnızca 25 öğrenciyi kapsıyor → **öğrenci başına ~1,8 veli**, yani
çoklu veli istisna değil, **normal durum**.
- `devamsizlik_tum_veliler` ayarı (varsayılan `'1'` = telefonu olan TÜM veliler).
- Aynı veli birden fazla gelmeyen öğrenciye bağlıysa (kardeşler) **tek mesaj**
  üretilir, `{ogrenci_adi}` yerine isimler " ve " ile birleştirilir.
- Aynı normalize telefon numarası birden fazla veli kaydında görünüyorsa
  numaraya göre tekilleştirilir (aynı telefona iki mesaj gitmez).

---

## 7. Tasarım kararı D6 — Gözlemlenebilirlik

- **Panel** (§5.1): gönderilen / atlanan / sınıf bazında veri durumu.
- **`/kayitlar`**: otomasyon gönderimleri `gonderim_id` = `oto-dev-20260922` /
  `oto-dgn-20260922` ile mevcut sayfada görünür, tıklanınca
  `/durum/{gonderim_id}` satır satır sonucu gösterir. Ek kod gerekmez —
  deterministik `gonderim_id` bunu bedavaya verir.
- **Log** (journalctl): dashboard'un `[polling]` desenine paralel tek satırlık
  `print` çıktıları —
  `[otomasyon] devamsizlik hazirlik: 2 hedef, 4 atlandi (veli_telefonu_yok=3, ad_belirsiz=1), gonderim 09:00`
  `[otomasyon] devamsizlik KURU: 2 mesaj uretildi, modem cagrilmadi`
  `[otomasyon] devamsizlik IPTAL edildi (panelden)`
  `[otomasyon] hata: yoklama servisine ulasilamadi -> kacirildi`
  Okuma: `journalctl -u farabi-smssistemi -S today | grep otomasyon`.
- Hiçbir log satırına telefon numarasının tamamı yazılmaz (gizlilik): son 4
  hane maskelenir (`0532***4512`).

---

## 8. Yeni `ayarlar` anahtarları

`_AYARLAR_VARSAYILAN` sözlüğüne eklenir (`INSERT OR IGNORE` → canlı DB'ye
güvenli varsayılanla düşer, migration yok).

| Anahtar | Varsayılan | Açıklama |
|---|---|---|
| `sms_otomatik` | `0` (mevcut) | **ANA ŞALTER** — tüm otomasyon |
| `otomasyon_kuru` | **`1`** | Kuru çalıştırma AÇIK başlar — hiç SMS gitmez |
| `dogum_otomasyon` | `1` | Doğum günü işi (ana şaltere tabi) |
| `dogum_gonderim_saati` | `08:00` | |
| `dogum_gecikme_toleransi_dk` | `240` | |
| `dogum_sms_sablonu` | (mevcut) | `{isim}` yer tutuculu |
| `devamsizlik_otomasyon` | `1` | Devamsızlık işi (ana şaltere tabi) |
| `devamsizlik_gonderim_saati` | `09:00` | |
| `devamsizlik_hazirlik_dk` | `5` | → hazırlık 08:55 |
| `devamsizlik_gonderim_gecikme_toleransi_dk` | `15` | Sonrası: gönderme, `kacirildi` |
| `devamsizlik_ders_no` | `1` | |
| `devamsizlik_pilot_siniflar` | `10-A,12-A` | **Kod değiştirmeden sınıf eklenir** |
| `devamsizlik_tum_veliler` | `1` | 0 = yalnızca ilk veli |
| `devamsizlik_sms_sablonu` | aşağıdaki metin | |
| `yoklama_servis_url` | `http://127.0.0.1:8010` | DNS'e bağımlı olmamak için IP |

⚠️ **`devamsizlik_ders_no` ile `devamsizlik_hazirlik_dk` birbirine bağlıdır.**
08:55 hazırlığını güvenli kılan şey, `zil.json`'da 1. dersin **08:50**'de
bitmesidir (gerçek `kaydedilme_saati` örnekleri: 08:15 / 08:17 / 08:44 /
08:50:2x). Ders numarası değiştirilirse hazırlık ve gönderim saatleri
`zil.json`'daki o dersin bitiş saatine göre **elle yeniden hesaplanmalıdır**;
sistem bunu kendiliğinden yapmaz ve yanlış ayar sessizce "yoklama henüz
alınmamış" sonucu üretir.

Önerilen devamsızlık şablonu (`app.py`'deki Ollama örneğiyle aynı cümle —
kullanıcı onayına tabi, §13.6):

> `Sayin {isim}, bu mesajin gonderildigi saat itibariyla ogrencimiz {ogrenci_adi} okula gelmemistir. Bilgilerinize sunariz. Okul Idaresi`

⚠️ **Şablonlar ASCII tutulmalı.** `sms_gonderici` Türkçe karakter içeren
mesajı UCS2 modunda gönderiyor; UCS2'de tek SMS sınırı 160 değil **70
karakter**. Mevcut `dogum_sms_sablonu` zaten bilinçli ASCII
("dogum gununuzu kutlar…"); devamsızlık şablonu da öyle yazılmalı, yoksa
her mesaj 2-3 kontöre mal olur.

---

## 9. Fazlar

Her faz: **tek modül**, tek başına test edilebilir, tek başına commit
edilebilir, kendi başına geri alınabilir. Uygulama sırası bağlayıcıdır
(Faz 0 hariç).

### Faz 0 — Veri düzeltme (bağımlılık DEĞİL, hijyen)

3 öğrencinin sınıf ataması `smssistemi`de yanlış; yoklama panosu doğru kaynak
(kullanıcı teyidi: "yoklamadaki öğrenci adı ve sayısı güncel"):

| Öğrenci | Pano (doğru) | smssistemi (yanlış) |
|---|---|---|
| Öğrenci A | 11-A | 11-B |
| Öğrenci B | 11-B | 11-A |
| Öğrenci C | 11-B | 11-A |

- Dosya: `smssistemi/scripts/sinif_celiskisi_duzelt.py` (mevcut `scripts/`
  konvansiyonu: elle çalıştırılan, tekrar çalıştırması güvenli).
- **Varsayılan kuru**, `--uygula` ile yazar; önce `db._dosya_yedekle` çağırır.
- ⚠️ **Bu faz pilotu bloklamaz:** çelişkiler 11-A/11-B'de, pilot 10-A/12-A'da
  ve eşleştirme zaten yalnızca isme bakıyor. Sıra beklemeden yapılabilir.
- Test: `test_sinif_celiskisi_duzelt.py` — geçici DB'de 3 kaydı kurar, kuru
  modda 0 değişiklik, `--uygula` ile 3 değişiklik, ikinci çalıştırmada 0.
- Manuel: `sqlite3 veri/smssistemi.db "SELECT k.ad_soyad, s.ad FROM kisiler k JOIN siniflar s ON s.id=k.sinif_id WHERE k.ad_soyad IN (…)"`

### Faz 1 — `smssistemi/db.py`: şema + ayarlar + sorgular

- Dosya: `smssistemi/db.py` (tek modül).
- Eklenecekler: `SEMA`ya iki `CREATE TABLE IF NOT EXISTS` (§3),
  `_AYARLAR_VARSAYILAN`a §8'deki anahtarlar,
  `_ISTANBUL_ZAMAN()` yardımcısı (aware ISO metin üretir),
  ve fonksiyonlar:
  `otomasyon_kosu_oku`, `otomasyon_kosu_olustur`, `otomasyon_kosu_gecis`
  (atomik, `bool` döner), `otomasyon_kosu_sayaclari_guncelle`,
  `otomasyon_hedef_ekle`, `otomasyon_hedefleri_listele`,
  `otomasyon_hedef_durum_guncelle`, `son_kosular`,
  `ogrenciler_isimle` (tr_norm ile **liste** döner — tekillik kararını
  çağıran verir), `veliler_ogrenci_icin`.
- Testler (`test_db.py`'ye eklenir, mevcut `tmp_path`/`monkeypatch` deseni):
  - şema iki kez kurulunca hata vermiyor (idempotan),
  - `UNIQUE(is_turu,tarih)` ikinci koşuyu engelliyor,
  - `UNIQUE(is_turu,tarih,kisi_id)` aynı kişiye ikinci hedefi engelliyor,
  - `otomasyon_kosu_gecis` yanlış beklenen durumda `False` dönüyor ve satırı
    değiştirmiyor (çift gönderim korumasının çekirdek testi),
  - `ogrenciler_isimle` 0/1/2 eşleşme senaryoları (büyük-küçük harf ve
    Türkçe "İ/ı" farkı dahil),
  - yeni ayar anahtarları varsayılanla geliyor, mevcut `sms_otomatik`
    değeri **ezilmiyor** (`INSERT OR IGNORE`).
- Manuel: servis restart'ı sonrası
  `sqlite3 veri/smssistemi.db ".tables"` ve `SELECT * FROM ayarlar;`

### Faz 2a — Dashboard: yoklama özeti endpoint'i

- Dosyalar: **yeni** `tahtayoklama/dashboard/devamsizlik_ozeti.py`,
  `dashboard/app.py` (ince route), `dashboard/auth.py` (+`sms_sso_dogrula`).
- ℹ️ **Bu faz üç dosyaya dokunur — Kural 3'ün ("tek seferde tek modül")
  bilinçli, dar bir istisnası.** Gerekçe: route (~15 satır) ve HMAC doğrulama
  yardımcısı (~10 satır) tek başlarına anlamsız; üçü birlikte tek bir
  mantıksal birim (bir okuma sözleşmesi) oluşturuyor ve birlikte geri
  alınabiliyorlar. Asıl mantık tek modülde (`devamsizlik_ozeti.py`), diğer
  ikisi saf sarmalayıcı.
- **Yanıt kapsamı:** endpoint, `yoklama_onbellek`'te o tarih+ders için satırı
  olan **tüm aktif sınıfları** döner. Dashboard pilot listesini BİLMEZ ve
  bilmemelidir (pilot kavramı smssistemi'nin iş kuralı) — süzme çağıran
  tarafta yapılır.
- Fonksiyonlar:
  - `devamsizlik_ozeti.gelmeyenleri_coz(satirlar: list[dict]) -> list[dict]`
    — **saf**, DB/ağ yok: `durum=='alindi'` kontrolü, `yok − izinli` düşümü,
    Türkçe `aciklama` üretimi.
  - `devamsizlik_ozeti.DURUM_ACIKLAMALARI: dict[str, str]`
  - `app.py::api_yoklama_gelmeyenler(request, tarih, ders_no=1, taze=0, t=None, s=None)`
- Testler (**unittest**, dashboard konvansiyonu):
  `test_devamsizlik_ozeti.py` — 6 `durum` değeri için `veri_var` doğru mu,
  izinli düşümü, izinli==yok (boş liste) hâli, bozuk JSON'a dayanıklılık,
  bilinmeyen `durum` değeri.
- Manuel: tarayıcıda oturum açıkken
  `http://farabi.local:8010/api/yoklama/gelmeyenler?tarih=2026-09-22&ders_no=1`
  → 10-A ve 12-A satırlarını gözle doğrula; `&taze=1` ile yanıt süresini ölç.
- ⚠️ Servis restart'ı **ders saatleri dışında** (tahtayoklama Kural 7).

### Faz 2b — smssistemi: yoklama köprüsü istemcisi

- Dosyalar: **yeni** `smssistemi/yoklama_kopru.py`, `smssistemi/auth.py`
  (+`sso_token()`).
- Fonksiyonlar: `gelmeyenleri_getir(tarih, ders_no, taze=True) -> dict`
  (iki aşamalı deneme + zaman aşımı), istisna `YoklamaUlasilamadi`.
  `urllib.request` kullanılır — **yeni kütüphane yok**, `app.py` Ollama
  çağrısında zaten bu deseni kullanıyor.
- **Yardımcı CLI:** `smssistemi/scripts/yoklama_sorgula.py` — imzalı isteği
  atıp JSON'u ekrana basar. Hem manuel doğrulama hem günlük teşhis için.
- Testler (pytest): `test_yoklama_kopru.py` — `urllib.request.urlopen`
  monkeypatch'lenerek: başarılı yanıt, 401, zaman aşımı → `taze`siz ikinci
  deneme, ikisi de düşerse `YoklamaUlasilamadi`, bozuk JSON.
- Manuel: `venv/bin/python scripts/yoklama_sorgula.py --tarih $(date +%F) --ders 1`

### Faz 3 — `smssistemi/devamsizlik.py` (saf iş mantığı, SMS YOK)

- Dosya: **yeni** `smssistemi/devamsizlik.py`.
- Fonksiyonlar:
  - `pilot_siniflar(conn) -> list[str]`
  - `ogrenci_coz(conn, ad_soyad) -> tuple[dict|None, str|None]`
    (`^No\s+\d+$` → `roster_eksik`; 0 → `ogrenci_bulunamadi`; >1 → `ad_belirsiz`)
  - `alicilari_coz(conn, ogrenci, tum_veliler) -> tuple[list[dict], str|None]`
  - `hedefleri_hazirla(conn, yoklama_yaniti, sablon, ayarlar) -> dict`
    → `{"hedefler": [...], "atlananlar": [...], "sinif_durumlari": [...], "ozet": {...}}`
    (kardeş birleştirme + telefon tekilleştirme burada)
  - Mesaj üretimi mevcut `gonderim.kisisellestir` ile yapılır, yeni bir
    şablon motoru yazılmaz.
- Testler (pytest, `test_devamsizlik.py`) — **bu fazın testleri en kritik olanlar**:
  1. Mutlu yol: 10-A'da 1 gelmeyen + telefonlu veli → 1 hedef.
  2. `veri_var=false` sınıf → 0 hedef, 1 `yoklama_verisi_yok` atlaması.
  3. 10-A `alindi` + 12-A `tahta_ulasilamaz` → **kısmi gönderim** (10-A gider).
  4. Pilot dışı sınıf (9-A) → `pilot_disi`, hedef yok.
  5. Aynı adlı iki öğrenci → `ad_belirsiz`, mesaj YOK.
  6. `"No 12"` ismi → `roster_eksik`.
  7. Velisi olmayan öğrenci → `veli_yok`.
  8. Velisi var, telefonu boş → `veli_telefonu_yok`.
  9. İki velili öğrenci, `tum_veliler=1` → 2 hedef; `=0` → 1 hedef.
  10. Kardeşler: aynı veli 2 gelmeyen öğrenciye bağlı → **1 mesaj**, metinde
      iki isim.
  11. Aynı telefon iki veli kaydında → 1 hedef.
  12. Mesajda `{isim}` ve `{ogrenci_adi}` doğru dolduruluyor.
- Manuel: kuru modda `scripts/yoklama_sorgula.py` çıktısı bu fonksiyona
  verilip üretilen hedef/atlama listesi gözle doğrulanır (SMS yok).

### Faz 4 — `smssistemi/otomasyon.py` + `app.py` zamanlayıcı

- Dosyalar: **yeni** `smssistemi/otomasyon.py`, `smssistemi/app.py`.
- `otomasyon.py` (saf + conn alan yardımcılar):
  `ne_yapmali(simdi, ayarlar, kosular) -> list[str]`,
  `gonderim_id_uret(is_turu, tarih)`, `ayarlari_oku(conn) -> dict`
  (tipli/doğrulanmış ayar sözlüğü; bozuk saat değeri varsayılana düşer),
  `saat_ayristir(metin) -> time`.
- `app.py`:
  - `@app.on_event("startup")` → `lifespan` (davranış korunur),
  - `OTOMASYON_ARALIGI_SN = 30`, `_otomasyon_dongusu()`, `_otomasyon_turu()`,
    `_devamsizlik_hazirla()`, `_devamsizlik_gonder()`,
  - `_gonderim_calistir(..., kuru: bool = False, ek_kaydet=None)` —
    **varsayılanlar mevcut davranışı birebir korur**; `/gonder` ve
    `/tekrar-gonder` çağrıları değişmez. `kuru=True` iken modem hiç
    çağrılmaz, her satır `durum='kuru'` olarak kaydedilir.
  - Döngü asla servisi düşürmez: `except Exception` + `print("[otomasyon] hata: …")`
    (dashboard'un `[polling]` deseni).
  - **Zamanlayıcı yeni bir gönderim yolu açmaz** — hedef listesini hazırlayıp
    mevcut `threading.Thread(target=_gonderim_calistir, …)` yolundan geçirir.
- Testler (pytest, `test_otomasyon.py`):
  - `ne_yapmali` donmuş saatlerle: 07:59 / 08:00 / 08:05 / 12:01 (doğum
    toleransı aşımı) / 08:54 / 08:55 / 08:57 (restart) / 08:59 / 09:00 /
    09:01 / 09:16 (gönderim toleransı aşımı) / Cumartesi (devamsızlık YOK,
    doğum VAR) / ana şalter kapalı (hiçbir eylem) / iş şalteri kapalı.
  - `gonderim_id_uret` deterministik.
  - Çift gönderim: `gonderildi` durumundaki koşu için `ne_yapmali` boş döner.
  - `_gonderim_calistir(kuru=True)` `sms_gonderici.toplu_gonder`'i **hiç
    çağırmıyor** (monkeypatch ile "çağrıldı mı" bayrağı).
  - Mevcut `test_gonderim.py` ve `test_dogum_app.py` **kırılmadan geçmeli**
    (lifespan değişikliğinin regresyon testi).
- Manuel:
  1. `otomasyon_kuru='1'`, `sms_otomatik='1'`, saatleri geçici olarak
     "şimdi + 2 dk" yap → panelde koşunun hazırlanıp `bekliyor`a düştüğünü,
     geri sayımı ve gönderim sonrası `gonderildi (kuru)` olduğunu gör.
  2. Aynı denemeyi 08:5x'te **servisi restart ederek** tekrarla → pencere
     korunuyor mu, çift gönderim oluyor mu.
  3. `journalctl -u farabi-smssistemi -f | grep otomasyon`

### Faz 5 — Doğum günü işi

- Dosyalar: `smssistemi/dogum_mantik.py` (+`dogum_hedefleri_hazirla`),
  `app.py` (`_dogum_gonder`), `smssistemi/CLAUDE.md` (yanlış satır düzeltmesi).
- `dogum_hedefleri_hazirla(conn, bugun, sablon) -> dict` mevcut
  `db.dogum_gunu_olanlar(conn, ay, gun)`'u kullanır — o fonksiyon **zaten**
  `tur IN ('ogrenci','personel')` süzüyor, yani veli doğal olarak dışarıda.
  Telefonu olmayan → `telefon_yok` atlaması, **veliye yönlendirme YOK**.
  Yaş kuralı (`ogrenci_yasi_mi`/`personel_yasi_mi`) burada **kullanılmaz ve
  yeniden yazılmaz** — o kural Excel içe aktarımında sınıflandırma içindir;
  gönderim anında `tur` zaten kayıtlıdır.
- Testler (`test_dogum_mantik.py`'ye eklenir): bugün doğan öğrenci+personel
  seçiliyor; veli **hiçbir koşulda** seçilmiyor; telefonsuz kişi atlanıyor;
  29 Şubat kaydı 28 Şubat'ta yakalanıyor (mevcut davranış korunuyor);
  hafta sonu tarihinde de hedef üretiliyor (`okul_gunu_mu` uygulanmıyor).
- Manuel: kuru modda bir test kişisine bugünün tarihi girilip panelde
  göründüğü doğrulanır, sonra geri alınır.

### Faz 6 — Panel (`/otomasyon`)

- Dosyalar: **yeni** `smssistemi/templates/otomasyon.html`,
  `smssistemi/static/stil.css` (yalnızca ekleme), `templates/taban.html`
  (nav girişi), `app.py` (§5.2'deki 5 route).
- Testler (pytest, `test_otomasyon_app.py`, mevcut `test_dogum_app.py`
  deseni — `TestClient`): oturumsuz `/otomasyon` → `/giris`'e 303;
  `/api/otomasyon/bugun` oturumsuz → 401; iptal `bekliyor`da `true`,
  `gonderildi`de `false` döner ve durumu **değiştirmez**; ayar formu pilot
  sınıf listesini normalize ediyor (`" 10-a , 12-A "` → `10-A,12-A`).
- Manuel: üç temada (`klasik`/`yumusak`/`koyu`) göz kontrolü, iptal
  butonunun 09:00 sonrası `disabled` olması, boş durum metinleri.

### Faz 7 — Dashboard'dan erişim (küçük)

- Dosyalar: `dashboard/app.py` (`/otomasyon` yönlendirmesi, `/dogum`'un eşi),
  `dashboard/templates/pano.html` (sol menü linki).
- Test: mevcut dashboard testleri kırılmıyor; oturumsuz `/otomasyon` →
  `/giris`.
- Manuel: dashboard'dan tek tıkla `:8020/otomasyon` açılıyor, şifre sorulmuyor.

### Faz 8 — Kontrollü devreye alma (kod yok, prosedür)

1. `sms_otomatik='1'`, `otomasyon_kuru='1'` → **en az 3 okul günü kuru koşu.**
   Her sabah panelden: hedefler doğru mu, atlananların nedenleri makul mü,
   12-A/10-A veri durumu ne çıkıyor?
2. Kuru koşu listesi kullanıcı tarafından **onaylandıktan sonra**
   `otomasyon_kuru='0'`. İlk gerçek gün, gönderim saatinde panelin başında
   bir insan bulunur.
3. İlk hafta sonunda `/kayitlar` üzerinden hata oranı ve kontör tüketimi
   gözden geçirilir; ancak ondan sonra pilot dışı sınıflar
   `devamsizlik_pilot_siniflar`'a eklenir (kod değişikliği gerekmez).

---

## 10. Doğrulama matrisi (uçtan uca)

| Senaryo | Beklenen |
|---|---|
| Hafta içi, 10-A yoklama alındı, 1 gelmeyen, velisi telefonlu | 09:00'da 1 SMS |
| Aynı senaryo, 08:57'de servis restart | 09:00'da **yine 1** SMS (2 değil) |
| Aynı senaryo, 08:58'de panelden iptal | 0 SMS, koşu `iptal` |
| 12-A tahtaya ulaşılamadı | 12-A için 0 SMS, panelde "veri yok" |
| Yoklama servisi kapalı | 0 SMS, koşu `kacirildi`, log satırı |
| Hafta sonu | Devamsızlık koşusu **yok**, doğum günü koşusu **var** |
| `sms_otomatik='0'` | Hiçbir koşu satırı açılmıyor |
| `otomasyon_kuru='1'` | Koşu tam işliyor, modem hiç çağrılmıyor |
| Doğum günü, telefonu olmayan öğrenci | 0 SMS, panelde "telefon yok" |
| Doğum günü, veli | **Hiçbir koşulda** mesaj yok |
| Aynı gün ikinci kez elle hazırlık | `UNIQUE` engelliyor, çift mesaj yok |

---

## 11. Riskler ve geri alma

| # | Risk | Etki | Azaltma |
|---|---|---|---|
| R1 | Aynı adlı iki öğrenci → yanlış veliye "çocuğunuz gelmedi" | Çok yüksek (itibar) | Tekil eşleşme zorunlu, aksi hâlde `ad_belirsiz` atlaması + panelde kırmızı |
| R2 | Yoklama alınmamışken mesaj | Yüksek | `veri_var` kilidi, sınıf bazında; fail-closed |
| R3 | Restart → çift gönderim | Yüksek (para + korku) | Tarih anahtarlı `UNIQUE` + atomik durum geçişi + `gonderiliyor` asla yeniden denenmez |
| R4 | Kontör/para israfı | Orta | Kuru mod **varsayılan açık**, pilot 2 sınıf, panel önizleme, 3 gün kuru koşu |
| R5 | `taze=1` SSH taraması uzun sürer / dashboard yavaş | Orta | 30 sn zaman aşımı → önbellekten okuma (5 sn) → fail-closed |
| R6 | `lifespan` dönüşümü mevcut startup davranışını bozar | Orta | Faz 4 tek başına; mevcut test paketi (61 test) regresyon kapısı |
| R7 | Saat dilimi karışması (UTC/İstanbul) | Orta | Yeni tablolara **aware ISO** yazılır, `datetime('now')` yasak; `ne_yapmali` testleri açık `+03:00` ile |
| R8 | Türkçe karakter → UCS2 → 70 karakter sınırı, mesaj 2-3 kontör | Düşük-orta | Şablonlar ASCII; panelde karakter sayacı |
| R9 | Resmi tatil (29 Ekim vb.) `okul_gunu_mu`'dan geçer | Düşük | Tahtalar kapalı → `tahta_ulasilamaz` → fail-closed, mesaj gitmez (mimari bunu doğal kapsıyor). Yine de §13.8 |
| R10 | Çoklu veli → beklenenin 1,8 katı mesaj | Düşük (para) | `devamsizlik_tum_veliler` ayarı + kuru koşuda gerçek sayı görülür |
| R11 | `alindi` ama tahta açık unutulmuş → "herkes var" sahte kaydı (tahtayoklama §8.4) | Düşük | Bu **var olan** bir belirsizlik; otomasyon yalnızca mesaj **göndermeme** yönünde etkilenir (gelmeyen listesi boş çıkar) — yanlış mesaj üretmez |

### Geri alma yolları

1. **Tek satırlık kapatma şalteri (restart gerekmez, döngü her uyanışta okur):**
   ```
   sqlite3 /home/ata/farabi/smssistemi/veri/smssistemi.db \
     "UPDATE ayarlar SET deger='0' WHERE anahtar='sms_otomatik';"
   ```
2. Yalnızca devamsızlığı durdur: aynı komut, `devamsizlik_otomasyon`.
3. Para harcamayı durdur ama izlemeye devam et: `otomasyon_kuru='1'`.
4. Kod geri alma: her faz ayrı commit → `git revert <sha>`; Faz 4 geri
   alınırsa zamanlayıcı tamamen kalkar, tablolar boş kalır (zararsız).
5. Tablolar asla `DROP` edilmez — geçmiş koşu kaydı denetim izidir.

---

## 12. Kapsam dışı (bu planda YAPILMAYACAK)

- Veli doğum günü (veri tutulmuyor, kullanıcı kararı).
- 2. ve sonraki derslerin devamsızlığı (yalnızca `devamsizlik_ders_no=1`).
- Devamsızlık mesajı için Ollama ile metin üretimi (şablon sabit; AI düzeltme
  yalnızca elle gönderimde kalır — otomatik yolda öngörülemez metin istenmez).
- Dashboard panosuna canlı geri sayım şeridi.
- e-Okul / resmi devamsızlık kaydına yazma.
- Resmi tatil takvimi tablosu (§13.8'e bağlı).
- İki servisin birleştirilmesi (§2, reddedildi).

---

## 13. AÇIK SORULAR (koddan çözülemez — kullanıcıya sorulmalı)

1. **Çoklu veli:** 46 veli yalnızca 25 öğrenciyi kapsıyor (öğrenci başına
   ~1,8 veli). Gelmeyen öğrencinin **tüm** velilerine mi gitsin (plan
   varsayılanı: evet), yoksa yalnızca birine mi? Kontör iki katına yakın çıkar.
2. **İptal penceresi 5 dakika ve kimse o ekrana bakmıyor olabilir.**
   (a) 08:55/09:00 aynen kalsın mı, (b) hazırlık 08:52 + gönderim 09:05 ile
   ~13 dakikaya mı çıkarılsın, (c) iptal yalnızca 8020'de mi kalsın yoksa
   dashboard'a da bir uyarı şeridi mi eklensin? (`taze=1` sayesinde erken
   hazırlık artık veri tazeliğini bozmuyor.)
3. **Kaçırılan devamsızlık koşusu:** servis 09:01'de ayağa kalktı. Plan
   varsayılanı "gönderme, panelde göster, insan isterse 'Şimdi Hazırla'ya
   bassın". Alternatif: 09:15'e kadar otomatik gecikmeli gönder. Hangisi?
4. **Doğum günü gecikme toleransı:** 08:00 kaçırılırsa 12:00'ye kadar
   gecikmeli gönderim uygun mu, yoksa "kaçtıysa kaçsın" mı?
5. **Personel doğum günü fiilen çalışmayacak:** 23 personelden yalnızca
   **1'inin** telefonu var. Personel telefonları girilecek mi, yoksa personel
   otomasyonu şimdilik kapatılsın mı?
6. **Devamsızlık mesaj metni onayı** — §8'deki taslak cümle aynen kullanılsın
   mı? İmza "Okul Idaresi" mi, okul adı mı? (ASCII kalmalı — UCS2 tuzağı.)
7. **Pilot dışındaki 76 öğrencinin ulaşılabilir velisi yok.** Panelde bu
   "kapsanmayan öğrenci" sayısı sürekli gösterilsin mi (veri toplamayı
   hatırlatıcı olarak), yoksa gürültü mü olur?
8. **Resmi tatil takvimi istiyor musunuz?** Plan, tatilde tahtaların kapalı
   olması → `tahta_ulasilamaz` → fail-closed zinciriyle bu riski zaten
   kapatıyor (R9); soru sadece şu: `ayarlar`a elle girilen bir "tatil
   günleri" listesi ayrıca istenir mi (panelde "bugün tatil" yazması ve
   boşuna SSH taraması yapılmaması için)?
9. **`sms_otomatik` artık iki sayfadan (`/dogum-gunleri` ve `/otomasyon`)
   yazılıyor** — aynı anahtarı iki form kontrol ediyor. Tek ana şalter olarak
   kalsın mı (plan varsayılanı; `/dogum-gunleri`'ndeki etiket "tüm otomatik
   SMS" olarak güncellenecek), yoksa doğum gününe ayrı bir şalter mi?
10. **Zamanlayıcının kendi sağlığı:** döngü sessizce ölürse (beklenmedik
    hata) kimse fark etmez. Panelde "son uyanma zamanı" göstergesi yeterli mi,
    yoksa sabah 09:05'te hiç koşu yoksa uyarı SMS'i mi istenir?

---

### Uygulama için kritik dosyalar

- `/home/ata/farabi/smssistemi/app.py` — zamanlayıcı döngüsü, lifespan, route'lar, `_gonderim_calistir`
- `/home/ata/farabi/smssistemi/db.py` — iki yeni tablo, ayar anahtarları, sorgular
- `/home/ata/farabi/tahtayoklama/dashboard/app.py` — `/api/yoklama/gelmeyenler` endpoint'i
- `/home/ata/farabi/tahtayoklama/dashboard/yoklayici.py` — `durum` ve `yok/izinli` alan bilgisinin kaynağı (okunacak, değiştirilmeyecek)
- `/home/ata/farabi/smssistemi/dogum_mantik.py` — doğum günü hedef üretimi (var olan mantık kullanılacak)
