# Plan: Kazanım testi raporlama (Faz 2)

Tarih: 2026-10-08 · Önceki faz: `kazanimtest/` (form + SMS, `bbd1686`…`88e006f`)

## Amaç
Google Form cevaplarından:
- **Sınıf analizi** — hangi kazanımı sınıfın çoğunluğu anlamamış (öğretmen, panoda).
- **Bireysel analiz** — "Ayşe'nin eksik kazanımları", güçlü yanları, tekrar edeceği kitap sayfaları.
- **Veli + öğrenci geri bildirimi** — ayda bir, kişiye özel tahmin edilemez link SMS ile.

## Kullanıcı kararları (2026-10-08)
- Öğretmen raporu **panoda** (`tahtayoklama/dashboard`).
- Veli/öğrenci raporu **Google'da** (Apps Script sayfası), **kişiye özel link** (gizli kod) — numara yazdırılmaz.
- Sıklık **aylık**. Aynı link **öğrenciye de** gider (telefonu kayıtlıysa).

## Gizlilik sınırı (değişmez)
Google'da: okul no + sorular + cevaplar + kazanım sonuçları. **İsim, telefon, roster Google'a gitmez.**
İsim eşleşmesi yalnızca sunucuda: pano kendi roster'ından (`ogrenciler.no`), SMS metni smssistemi'nde.

## Veri akışı
```
Google Form cevapları ──(gece, proxy)──► kazanimtest.sonuc ──► soru_havuzu PG: form_cevap
                                                             │
                                          kazanimtest.analiz ┴─► /mnt/farabi-data/farabi/kazanim_testleri/rapor/<sinif>.json
                                                                      │ (pano okur, ismi kendi roster'ından ekler)
                                                                      ▼
                                                               Pano /kazanim-rapor
Ayda bir: kazanimtest.aylik ──► Apps Script "rapor_yaz" (token → okul no + sonuç, isim yok)
                            └──► smssistemi /api/arac/kisisel-taslak → kisisel-gonder (öğrenci + veliler)
                                 SMS: "<Ad>'ın Ekim kazanım raporu: <script_url>?r=<token>"
```

## Adımlar (Kural 3: her adım tek modül; kodu Sonnet yazar, Kural 11)

### 1. `kazanimtest/` — cevap çekme + soru↔kazanım bağı
- `Code.gs`: `doPost {islem:"sonuclar", form_id}` → `[{zaman, okul_no, cevaplar:[seçilen şık metni…]}]`.
  Mevcut `islem` yok = form oluştur (geriye uyumlu).
- Form oluştururken `form_testi.sorular` (jsonb anlık görüntü: metin, şıklar, doğru, kaynak, **kazanım satırı**) yazılır.
  Kazanım satırı = sorunun bge-m3 ile en benzer kazanım satırı (zaten hesaplanan embedding'ler). Eski kayıt (id=1) → test düzeyi kazanım.
- `sema.sql`: `form_cevap(form_testi_id, okul_no, soru_sira, secilen int NULL, dogru bool, zaman)`,
  `UNIQUE(form_testi_id, okul_no, soru_sira)` — aynı numara birden çok gönderirse **ilk** gönderim sayılır.
- `calistir.py sonuc` komutu + `kazanim-test-sonuc.timer` (her gece 21:00 UTC): son 30 günün formlarını çeker.

### 2. `kazanimtest/analiz.py` — rapor JSON'u
- Sınıf × kazanım: katılım, doğru oranı, **"zorlanılan"** = oran < %50 (ayarlanabilir).
- Öğrenci × kazanım (okul no): soru sayısı, doğru oranı; **eksik** = ≥2 soruda oran < %50; **güçlü** = ≥2 soruda ≥ %80.
- Eksik kazanım için öneri: yanlış yapılan soruların kaynak sayfaları ("Kimya 9, s. 54-55").
- Çıktı `rapor/<sinif>.json` (veri diski, repo değil), gece sonuç çekiminden sonra.

### 3. Pano `/kazanim-rapor` (`tahtayoklama/dashboard/`)
- Yeni router `kazanim_rapor.py` + şablon `kazanim_rapor.html` (`taban.html`, `pano.css` token'ları, CDN yok, empty-state).
- Sınıf seç → **kazanım tablosu** (doğru oranı, zorlanılanlar üstte) → **öğrenci listesi** (no + ad roster'dan, eksik kazanım sayısı) → öğrenci detayı.
- Oturum: mevcut `auth.dogrula` deseni. Menüye bağlantı.
- Veri: yalnızca JSON dosyasını okur — servisler arası yeni DB bağı yok.

### 4. smssistemi — kişiye özel SMS ucu
- `POST /api/arac/kisisel-taslak` `{ogeler:[{sinif, okul_no, metin_sablon}]}` → öğrenci `okul_no+sinif` ile bulunur,
  alıcı = öğrenci (telefonu varsa) + `veliler_ogrenci_ile`; `{ad}` sunucuda doldurulur; `test_telefon` desteği.
  `POST /api/arac/kisisel-gonder {taslak_id}`. Telefonlar smssistemi'nden çıkmaz.
- Önkoşul doğrulama: pano `ogrenciler.no` ile smssistemi `kisiler.okul_no` 96 öğrencide tutarlı mı (salt-okunur karşılaştırma; tutarsızlar listelenir, düzeltilmeden SMS yok).

### 5. Aylık veli/öğrenci raporu
- `Code.gs`: `doPost {islem:"rapor_yaz", raporlar:[{token, ay, sinif, okul_no, veri}]}` → "Raporlar" tablosu;
  `doGet?r=<token>` → HtmlService ile mobil uyumlu rapor (isimsiz: "9-A, no 123"; ders → kazanım çubukları, eksikler + çalışılacak sayfalar, güçlü yanlar, sınıf ortalamasıyla kıyas). Token `secrets.token_urlsafe(16)`, 90 gün geçerli.
- `calistir.py aylik [--ay 2026-10] [--sms | --sms-test]` + timer (ayın 1'i 07:00 UTC, önceki ay). **İlk ay SMS'siz**; Atakan raporları kontrol edince açılır.

## Doğrulama
- Birim testleri her adımda (Apps Script çağrıları mock; analiz eşik/kenar durumları; pano boş/dolu veri; SMS uçları mock).
- Canlı: 9-A Kimya formuna 3-4 farklı okul no ile cevap → `sonuc` → panoda görünür → `aylik --sms-test` ile 05059399303'e link → telefonda rapor açılır, başka token ile başkasının raporu açılmaz.

## Açık riskler
- Öğrenci formu farklı/yanlış numara ile doldurursa eşleşmez → panoda "eşleşmeyen numaralar" listesi.
- Apps Script günlük kotaları (tüketici hesap: e-posta yok, URL fetch yok — yalnızca Forms/Sheets; sorun beklenmiyor).
- Proxy kapalıysa gece çekimi atlanır, ertesi gece tekrar dener (UNIQUE sayesinde güvenli).
