# Doğum Günleri Modülü — Uygulama Planı

**Tarih:** 2026-09-20
**Durum:** Plan — uygulanmadı. Faz 0 (karar onayı) kullanıcıda.
**Plan modeli:** Opus (Kural 11). Uygulama: Sonnet.
**İlgili:** `smssistemi/CLAUDE.md`, kök `CLAUDE.md` → "Frontend / Dashboard Tasarım Standartları", `docs/superpowers/specs/2026-09-19-smssistemi-design.md`

---

## 0. Mimari kararı — (c): modül `smssistemi/`'ye eklenir

Görev tanımındaki başlangıç önerisi ("dogum/ kendi 4. servisi olsun + HTTP
köprüsü") REDDEDİLDİ. Gerekçe, keşifte bulunan üç somut olgu:

**Olgu 1 — Telefon listesi HİÇBİR YERDE yok.** `smssistemi/veri/smssistemi.db`
canlı sorgusu: 101 öğrenciden **0**'ının telefonu dolu, 1 veli telefonu var.
Kullanıcının "telefon listesi yüklenecek zaten öğrencilerin" dediği iş henüz
hiç yapılmamış — bu planın en önemli sıralama kısıtı.

**Olgu 2 — Zaten İKİ öğrenci listesi var, ikisi de aynı 101 kişi**
(`tahtayoklama/dashboard/veri/yoklama_pano.db::ogrenciler` ve
`smssistemi/veri/smssistemi.db::kisiler`, `roster_ice_aktar.py` ile
aktarılmış). Ayrı bir 4. servis bunu ÜÇE çıkarırdı — telefon listesi iki
ayrı arayüzden iki kez yüklenir, her değişiklikte iki yerde güncellenir.

**Olgu 3 — Personel (23 kişi) hiçbir listede yok.** `Dogum.xlsx`'te doğum
yılı ≤1999 olan 23 kişi var, ne dashboard'da ne smssistemi'de kayıtlı.
Var olan `kisiler` tablosuna eklemek, idareye "personele de SMS" yeteneğini
bedavaya kazandırır; ayrı DB bunu imkânsız kılar.

**Modem yakınlığı SONUÇ, gerekçe değil.** Asıl gerekçe tek-kişi-listesi.
Modem tek süreçte kalması otomatik gelir ve görev tanımının istediği ayrı
"SMS köprüsü" endpoint'ine ihtiyacı büyük ölçüde ortadan kaldırır.

Bedavaya gelenler: `stil.css` zaten pano.css'in 3 temasını içeriyor,
`_ikon_sprite.html` hazır, `auth.py`+cookie+`/sso` çalışıyor, `gonderimler`
tablosu SMS'leri zaten denetlenebilir kılıyor.

**`tahtayoklama/dashboard`'a DOKUNULMAZ** — telefon kavramı yok, SMS
yeteneği yok, 7 canlı tahta bağımlı (en yüksek regresyon riski). Kullanıcının
"dashboard" demesi zaten `/sms-git` linkiyle karşılanıyor.

**"Bot olarak kalsın" korunuyor:** `dogum/dogum.py` bağımsız script kalır.
Tek değişiklik: Excel yerine smssistemi'nin HTTP API'sinden veri okur.

---

## 1. Hedef mimari — veri akışı

```
                  smssistemi :8020 (MEVCUT SERVİS, yeni bölüm eklenir)
                  ┌──────────────────────────────────────────────┐
  İdare (tarayıcı)│  /dogum-gunleri  → CRUD + yaklaşanlar + ayar  │
  ───────────────▶│  /rehber         → telefon toplu yükleme      │
     (cookie/SSO) │  kisiler tablosu: ad_soyad, telefon,          │
                  │                   dogum_tarihi, tur, sinif_id │
                  │  ayarlar tablosu: sms_otomatik = 0|1          │
                  └───────┬───────────────────────┬──────────────┘
                          │ GET /api/dogum/bugun   │ POST /api/dogum/sms
                          │ (HMAC imzalı)          │ (HMAC imzalı)
                  ┌───────┴───────────────────────┴──────────────┐
  systemd timer ─▶│  dogum/dogum.py  (BOT — bağımsız script)      │
  (08:15 günlük)  │  1. bugünün listesini API'den çek             │
                  │  2. Ollama ile kişiye özel mesaj üret         │
                  │  3. Telegram'a gönder  (DEĞİŞMEZ davranış)    │
                  │  4. sms_otomatik=1 ise POST /api/dogum/sms    │
                  └──────────────────────────────────────────────┘
```

Modeme hiçbir zaman ikinci bir süreç bağlanmaz — `dogum.py` "şu kişilere şu
metni gönder" der, gönderim smssistemi'nin kendi `_gonderim_calistir` →
`toplu_gonder` yolundan yapılır.

---

## 2. Veritabanı kararı ve şema

**Karar: SQLite, mevcut `smssistemi/veri/smssistemi.db`.** Yeni DB dosyası
açılmaz.

### 2.1 `kisiler` tablosuna eklenen sütun
```sql
ALTER TABLE kisiler ADD COLUMN dogum_tarihi TEXT;   -- ISO 'YYYY-MM-DD', NULL olabilir
```

### 2.2 `tur` CHECK kısıtı — planın en dikkat isteyen adımı

SQLite CHECK kısıtını `ALTER TABLE` ile değiştiremiyor. `'personel'`
eklemek 12 adımlı tablo yeniden kurulumu gerektirir (yeni tablo → veri
kopyala → eskiyi sil → yeniden adlandır). **Idempotanlık koruması
zorunlu:** migration öncesi `sqlite_master`'dan tablo tanımı okunup
`'personel'` zaten varsa atlanır (yoksa her restart'ta yeniden kurulur).
**Yedek zorunlu:** migration öncesi `veri/smssistemi.db` →
`veri/yedek/smssistemi_<tarih>_dogum_oncesi.db`.

**Reddedilen alternatif:** personeli `tur='ogrenci'` + `sinif='Personel'`
olarak tutmak — tablo rebuild'inden kaçınır ama arayüzde "Öğrenci" yazar,
semantik olarak yanlış. Kullanıcı rebuild istemezse B planı (bkz. §11 S1).

### 2.3 `sinif_id` — sahte sınıf, NULL YAPILMAZ

Personel için `siniflar` tablosuna **"Personel"** satırı eklenir. NULL
yapılırsa `db.kisiler_listele()`'nin INNER JOIN'i personeli sessizce
listeden düşürür (Kural 5 ihlali niteliğinde). "Personel" doğal olarak
sınıf listesinin sonuna düşer, silme koruması zaten var.

### 2.4 Yeni tablo: `ayarlar`
```sql
CREATE TABLE IF NOT EXISTS ayarlar (anahtar TEXT PRIMARY KEY, deger TEXT NOT NULL);
INSERT OR IGNORE INTO ayarlar VALUES ('sms_otomatik', '0');
INSERT OR IGNORE INTO ayarlar VALUES ('dogum_sms_sablonu', 'Sevgili {isim}, ...');
```
⚠️ **`sms_otomatik` varsayılanı `'0'` (KAPALI)** — güvenlik kısıtı, bkz. §9.

---

## 3. Doğum tarihi veri modeli

- `dogum_tarihi TEXT`, ISO `YYYY-MM-DD`. Yıl bilinmiyorsa NULL.
- Bugünün doğum günleri: `substr(dogum_tarihi, 6, 5) = 'MM-DD'` (indekslenebilir, `strftime` gerekmez).
- Yaklaşanlar (7/30 gün): SQL'de değil Python'da hesaplanır (yıl sonu sarması SQL'de kırılgan; 132 satır için performans sorunu yok).
- 29 Şubat: veride sıfır kayıt, yine de savunmacı — artık olmayan yıllarda 28 Şubat'a düşer.

---

## 4. `Dogum.xlsx` tek seferlik içe aktarım — `scripts/dogum_ice_aktar.py`

Model: `smssistemi/scripts/roster_ice_aktar.py` (idempotan). Esnek başlık
tanıma KULLANILMAZ — sütunlar sabit/bilinen, dosyada 10 Excel formül
artığı sütun var, esnek tanıyıcı bunlarla boğuşur.

**Ölçülen veri gerçekleri:** 133 satır, 1 tamamen boş (GÜN=0) → **132 gerçek
kişi**. `DOĞUM TARİHİ`: 127 datetime + 5 metin (`DD/MM/YYYY`) + 1 NaN — GÜN/AY
sütunları hepsinde doğru, oradan güvenilir. Doğum yılı: 1967–1999 arası 23
kişi (personel), 2007–2012 arası 109 kişi (öğrenci), **2000–2006 arası
SIFIR** — temiz ayrım. 132/132 tam ad benzersiz.

**Algoritma:** sabit 5 sütunu oku → boş satırları atla → yıl çıkar (metin
tarihte `DD/MM/YYYY` son parça) → **tür sezgisi: yıl ≤2004→personel,
≥2005→öğrenci** → `db.kisi_bul_isimle_sinifsiz()` (YENİ, sınıftan bağımsız
eşleştirme) ile eşleştir → eşleşen öğrencide SADECE `dogum_tarihi` UPDATE
edilir (telefon/sinif_id dokunulmaz); eşleşmeyen ~8 öğrenci "Bilinmeyen
Sınıf"a; 23 personel "Personel" sınıfına yeni satır. Özet: "eşleşti: N •
yeni öğrenci: N • yeni personel: N • sınıfı bilinmeyen: N". Tekrar
çalıştırmak güvenli.

**Gelecekte web'den doğum tarihi yükleme (Faz 5):** `_baslik_*_sutunu_mu`
ailesine `dogum` tanıyıcısı eklenir, `/rehber/yukle` aynı dosyadan telefon+
doğum tarihini birlikte alabilir.

---

## 5. `dogum.py` ↔ smssistemi köprüsü (2 endpoint, HMAC auth)

### 5.1 Auth
`auth.sso_dogrula()`'nın birebir kardeşi: paylaşılan hex secret + zaman
damgası + HMAC-SHA256 + `compare_digest`. `smssistemi/config/dogum_api.json`
(gitignore'lu, dizin joker'i YOK — tek tek eklenmeli, **Faz 4'ün onay
şartı**) ↔ `dogum/.env`'de `DOGUM_API_SECRET`. Pencere 120sn (SSO'nun 30sn'si
yerine, Ollama üretimi yavaş olabilir).

### 5.2 `GET /api/dogum/bugun?t=..&s=..`
Döner: tarih, `sms_otomatik`, şablon, kişi listesi (`ad_soyad`, `tur`,
`sinif_ad`, **`telefon_var: bool`** — numara ASLA dönmez, KVKK + `dogum.py`
numaraya ihtiyaç duymuyor).

### 5.3 `POST /api/dogum/sms`
`{kisi_ids, mesajlar?}`. Sunucu: imza doğrula → **`ayarlar.sms_otomatik`
DB'den TEKRAR okunur, `'0'` ise hiçbir şey göndermez** (istemciye
güvenilmez — ikinci kilit) → `db.kisiler_id_ile()` zaten telefonsuzları
eler → mevcut `_gonderim_calistir` aynen çağrılır, yeni modem kodu
YAZILMAZ. Sonuç `gonderimler` tablosuna düşer → `/kayitlar`'da görünür,
`/durdur/{id}` ile durdurulabilir.

### 5.4 SMS metni — KARAR: sabit şablon
Ollama'nın Telegram mesajı REDDEDİLDİ: emoji → UCS2 → segment başına 70
karakter (2-3 kredi/kişi), üstelik ton yanlış (arkadaşça, okul-idare
SMS'ine uymuyor). smssistemi'nin `/api/mesaj-duzelt` akışı REDDEDİLDİ —
prompt'u "veli SMS'i resmileştirme" için yazılmış, deterministik değil.
**Sabit şablon** (`ayarlar.dogum_sms_sablonu`, `{isim}` yer tutucu,
`gonderim.kisisellestir()`), ASCII-güvenli varsayılan, arayüzde canlı
segment sayacı. Telegram tarafı DEĞİŞMEZ (Ollama'nın emoji'li kişisel
mesajı orada kalır) — iki kanal, iki register.

---

## 6. Mevcut davranışa etki (Kural 5)

`tur`'a 3. değer eklenmesinin etki haritası çıkarıldı: `kisiler_listele`/
`kisi_bul_isimle`/`kisiler_telefonlu`/`kisiler_id_ile` parametreli veya
zaten `='ogrenci'` sabiti kullanıyor — regresyon riski düşük. Değişmesi
gerekenler: `rehber.html`'deki **5 ayrı** `<select name="tur">`'e
`personel` seçeneği, `gonder.html`'deki `#panel-tur`'e aynısı (varsayılan
`veli` KALIR), `app.py`'de tur doğrulaması beyaz listeye `personel` eklenir.

---

## 7. Fazlar

Sıralama ilkesi: **hiçbir telefon numarası ve `sms_otomatik` arayüzü
olmadan DB'ye girmez.**

**Faz 0** — Karar onayı (kod yok). Kullanıcıya: (c) mimari, `tur` rebuild,
sabit-şablon SMS, `sms_otomatik` varsayılan-kapalı.

**Faz 1** — Şema + migration (arayüz yok, davranış değişmez). `db.py`:
yedek + guard'lı rebuild + `dogum_tarihi` ADD COLUMN + "Personel"/"Bilinmeyen
Sınıf" seed + `ayarlar` seed + yeni sorgu fonksiyonları + testler.
Doğrulama: pytest, yedek dosyası gözle, satır sayısı 102→102, restart
(17:00 sonrası), `/rehber`+`/gonder` eskisi gibi, ikinci restart'ta guard
çalışıyor.

**Faz 2** — Excel tek seferlik aktarım. `scripts/dogum_ice_aktar.py` +
testler. Doğrulama: `--kuru-calistir` zorunlu önce, özet sayıları
(132/~23/~109), telefon sayısı hâlâ 1, ikinci çalıştırma "yeni:0".

**Faz 3** — Web arayüzü `/dogum-gunleri` (SMS YOK, salt veri). KPI şeridi
+ otomatik-SMS anahtarı + şablon kutusu (segment sayaçlı) + yaklaşanlar +
tam liste. Kişi ekle/sil AYRI FORM YAZILMAZ — `/rehber` zaten CRUD sunuyor,
`/dogum-gunleri` yalnızca doğum tarihini düzenler. Yeni ikon: `ik-pasta`
(Lucide cake, sprite'ta yok). Yeni CSS değişkeni/punto üretilmez.

**Faz 4** — API köprüsü + `dogum.py` uyarlaması + systemd timer.
`auth.dogum_api_dogrula()`, `scripts/dogum_api_anahtari.py`, 2 endpoint,
`.gitignore`'a `dogum_api.json`. `dogum.py`: Excel yerine API'den okur ama
**Excel yolu SİLİNMEZ** (API'ye ulaşılamazsa geri düşüş — "servis çökerse
iş durmaz" ilkesi). `pandas`/`openpyxl` bağımlılığı DÜŞER (`urllib.request`
stdlib yeterli, `requests` eklenmez). systemd timer `OnCalendar=*-*-* 08:15`,
`Persistent=true`, `Type=oneshot`, `After=farabi-smssistemi.service` ama
`Wants=` YOK (smssistemi kapalıyken de Telegram gitsin).

**Faz 5** — Telefon toplu yükleme (kasıtlı olarak EN SON). `/rehber/yukle`
formatına `dogum_tarihi` tanıyıcısı eklenir. Önce sahte dosyayla test,
sonra gerçek liste, `sms_otomatik` hâlâ Kapalı olduğu gözle doğrulanır.

**Faz 6** — Canlı SMS devreye alma (KULLANICI YAPAR). İdare listeyi
gözden geçirir → kendi numarasına test SMS'i → metin doğruysa
`sms_otomatik`'i elle açar → ertesi sabah `/kayitlar`'dan sonucu kontrol
eder.

---

## 8. Doğrulama matrisi

| Faz | Otomatik test | Servis | Gözle | Regresyon kapısı |
|---|---|---|---|---|
| 1 | pytest + migration idempotans | restart (17:00 sonrası) | yedek dosyası, satır 102 | `/rehber`+`/gonder` eskisi gibi |
| 2 | pytest + `--kuru-calistir` | — | özet 132/23/109 | telefon sayısı değişmedi |
| 3 | — | restart | 3 temada sayfa, KPI'lar | `/gonder` varsayılan filtre `veli` |
| 4 | pytest + `systemd-analyze verify` | timer enable | curl JSON'da telefon YOK | `gonderimler` satır artmadı |
| 5 | pytest | — | numaralar normalize | `sms_otomatik` hâlâ Kapalı |
| 6 | — | — | **kullanıcı** | — |

**Hiçbir fazda gerçek modeme SMS gönderilmez.**

---

## 9. Riskler

**R1 — Gerçek kişilere kazara SMS (EN KRİTİK).** Dört bağımsız kilit:
(1) Faz 1-4 boyunca DB'de sıfır öğrenci telefonu — hedef matematiksel
olarak boş; (2) `sms_otomatik` varsayılanı `'0'`; (3) sunucu tarafı
istemciye güvenmeyen ikinci kontrol; (4) SMS anahtarı arayüzü (Faz 3)
telefon yüklemesinden (Faz 5) önce gelir.

**R2 — Üretim tablosu rebuild'i.** Yedek + atomik + guard + satır sayısı
doğrulaması. Geri alma: servisi durdur, yedeği geri kopyala, başlat.

**R3 — Modem çakışması.** Bu mimaride ORTADAN KALKIYOR — `dogum.py`
modeme hiç bağlanmaz. Kalan risk (aynı süreçte iki eşzamanlı gönderim
thread'i) bugün de mevcut, plan yeni risk getirmiyor.

**R4/R5** — Sınıf ataması / tür sezgisi hataları düşük etkili (yalnızca
etiket, idare `/rehber`'den düzeltir).

**R6 — `.gitignore` unutulması.** Faz 4 doğrulamasında `git check-ignore`
kapı olarak tanımlı.

**R7 — Excel yolu bayatlar.** Geri düşüşte log uyarısı.

**R8 — CSS senkronu.** Yeni sayfa mevcut token kullanır, yeni değişken
yok → senkron riski doğurmuyor.

---

## 10. Kapsam dışı

1. `dogum/`'un 4. bir servise dönüştürülmesi (§0'da reddedildi).
2. `dogum.py`'nin web sunucusuna dönüştürülmesi — bot kalıyor.
3. `tahtayoklama/dashboard`'a dokunuş — nav linki bile eklenmiyor (bu plan
   kapsamında; NOT: dashboard'a "Doğum Günleri" nav linki bu plandan
   BAĞIMSIZ olarak zaten eklendi, bkz. commit `d47b342` — kullanıcı ayrıca
   istedi).
4. Yeni kütüphane (`requests`, `python-dotenv`, APScheduler) — hiçbiri.
5. SMS için Ollama metin üretimi — sabit şablon seçildi.
6. Veli doğum günleri.
7. Gönderim thread'i için kilit — mevcut durumun iyileştirmesi, ayrı konu.
8. `/gonder`'in doğum günü farkındalığı.
9. KVKK/saklama politikası, erişim logu.
10. `ayarlar` tablosunun genel ayar sayfasına dönüşmesi.

---

## 11. Kullanıcıya sorulacak açık kararlar

*(Planı bloklamaz — her birinin gerekçeli varsayılanı var.)*

- **S1 — `kisiler` rebuild'i kabul mü?** Varsayılan: EVET (yedekli+atomik).
  Hayırsa B planı: personel `tur='ogrenci'`+`sinif='Personel'`.
- **S2 — SMS şablonu tam metni + okul adı.** Varsayılan ASCII şablon var,
  okul adı kullanıcıdan alınmalı.
- **S3 — Günlük tetikleme saati.** Varsayılan: 08:15, her gün.
- **S4 — Öğrencinin kendi numarası mı, veli numarası mı?** Plan öğrencinin
  kendi telefonunu varsayıyor. Veliye gitmesi isteniyorsa `ogrenci_kisi_id`
  üzerinden yönlendirme gerekir — Faz 4'ten önce netleşmeli.
- **S5 — Doğum yılı bilinmeyen 1 kayıt.** Varsayılan: eklenir,
  `dogum_tarihi=NULL`.
- **S6 — Personel `/gonder` panelinde görünsün mü?** Varsayılan: evet.

---

### Uygulama için kritik dosyalar
- `smssistemi/db.py` — şema, migration, tüm yeni sorgular
- `smssistemi/app.py` — `/dogum-gunleri` + 2 HMAC API endpoint'i
- `dogum/dogum.py` — Excel yerine API + SMS tetikleme (bot kalır)
- `smssistemi/scripts/roster_ice_aktar.py` — `dogum_ice_aktar.py`'nin modeli
- `smssistemi/templates/rehber.html` — `tur` seçeneklerinin 5 yeri (regresyon riski burada yoğun)
