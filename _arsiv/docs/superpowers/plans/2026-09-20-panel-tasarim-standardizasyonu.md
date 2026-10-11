# Panel Tasarım Standardizasyonu — Uygulama Planı

**Tarih:** 2026-09-20
**Durum:** Faz 1 UYGULANDI ve doğrulandı (bkz. §11). Faz 2-7/D0-D2 bekliyor.
**Plan modeli:** Opus (Kural 11). Uygulama: Sonnet.

İlgili: kök `CLAUDE.md` → "Frontend / Dashboard Tasarım Standartları" bölümü.

---

## 0. Kapsam ayrımı: iki panel, iki farklı iş

| | `tahtayoklama/dashboard` | `smssistemi` |
|---|---|---|
| Durum | Olgun sistem (773 satır, 3 tema, 24 ikon) | 94 satır ham hex, token yok, ikon yok |
| İş türü | **Dar, ek nitelikli tamamlama** | **Gerçek yeniden tasarım** |
| Risk | Yüksek (7 canlı tahta kullanıyor) | Düşük (yalnız idare kullanıyor) |

Dashboard'da **punto ölçeği konsolidasyonu YAPILMAYACAK** — ölçülen "10 yakın punto"
gerçek bir gürültü ama düzeltmesi onlarca canlı kuralı dokunmak demek: en yüksek
riskli, en düşük getirili kalem. Yeni ölçek smssistemi'de tanımlanır, dashboard'a
yalnızca token olarak (kullanılmadan) backport edilir.

---

## 1. Karar: smssistemi token/tema sistemini nasıl edinecek

**`pano.css`'in üç `:root` tema bloğu (satır 1–86) ve `_ikon_sprite.html`
smssistemi'ye BİREBİR KOPYALANIR — bilinçli fork.**

Gerekçe:
1. **Teknik zorunluluk:** iki ayrı FastAPI app'i, iki ayrı `StaticFiles` mount'u
   (dashboard :8010, smssistemi :8020). Ortak CSS servis edilemez; symlink/build
   adımı yok ve proje build tooling istemiyor.
2. **Repoda zaten bu desen var:** üç bağımsız `ders_programi.json`/`zil.json`
   kopyası, `auth.py`/`db.py`'nin satır satır bağımsız kopyaları.
   `smssistemi/CLAUDE.md`: "Kasıtlı olarak bağımsız."
3. **Görsel süreklilik gereksinim:** `/sms-git` → `/sso` akışı kullanıcıyı
   dashboard'dan tek tıkla SMS paneline atıyor; iki panelin görsel ayrılığı
   bu akışta kırılma yaratır.
4. **Birebir olması denetlenebilirlik için:** kopya `/* === BEGIN pano.css kopya === */`
   … `/* === END pano.css kopya === */` arasına hiç değiştirilmeden konur:
   ```bash
   diff <(sed -n '1,86p' tahtayoklama/dashboard/static/pano.css) \
        <(sed -n '/=== BEGIN pano.css kopya ===/,/=== END pano.css kopya ===/p' \
              smssistemi/static/stil.css | sed '1d;$d')
   ```
   Aynı desen `_ikon_sprite.html` için de geçerli — komut dosyanın içine
   YAZILMAZ (kendine referans hatası: docstring'in kendisi marker string'ini
   içerince `sed` aralığı docstring'ten başlar, bu Faz 1'de fiilen yaşandı
   ve düzeltildi). Sprite senkron komutu (`awk` — `sed` aralık deseni
   self-reference'a düşürüyordu):
   ```bash
   diff <(awk '/BEGIN pano sprite kopya/{f=1;next}/END pano sprite kopya/{f=0}f' \
              smssistemi/templates/_ikon_sprite.html) \
        <(sed -n '2,83p' tahtayoklama/dashboard/templates/_ikon_sprite.html)
   ```
   2026-09-20'de çalıştırıldı: **SENKRON, birebir aynı.**

**Maliyet (açıkça):** iki token kopyası olur, biri değişince diğeri OTOMATİK
güncellenmez. `ders_programi.json` üç-kopya sorununun aynısı; aynı disiplinle
yönetilir. Not düşülecek üç yer: `stil.css` başı, `pano.css` başı (karşı-not),
`smssistemi/CLAUDE.md` + kök `CLAUDE.md`'nin çok-kopya uyarı listesi.

---

## 2. Sıralama: önce smssistemi, backport sona

Soyut seçilen boşluk/punto değerleri tahmindir; gerçek KPI kartları ve tablolar
karşısında kalibre edilir. Bu yüzden `--bosluk-*`/`--punto-*` önce smssistemi'de
`/* sms-özel — backport adayı */` bölgesinde yaşar, Faz D0'da iki dosyada
eşzamanlı olarak işaretli bölgeye taşınır.

---

## 3. Faz 0 — Sözleşmeyi dondur (kod değişikliği yok)

smssistemi'nin JS'i CSS sınıf/ID adlarına bağlı. Önce envanter:

```bash
grep -n "getElementById\|querySelector\|classList\|dataset\.\|innerHTML" \
     smssistemi/templates/*.html
```

**DEĞİŞTİRİLMESİ YASAK küme (doğrulandı):**

- `gonder.html` — JS'in okuduğu 16 ID: `panel-sinif`, `panel-tur`,
  `panel-kisi-listesi`, `panel-yukleniyor`, `tumunu-sec-chk`, `gorunen-sayisi`,
  `secilen-sayisi`, `secilenler-bos`, `secilenler-etiketler`,
  `secilenleri-temizle-btn`, `secilen-kisi-ids`, `duzelt-btn`, `duzelt-durum`,
  `mesaj-alani`, `numaralar-alani`, `gonder-form`
- `gonder.html` — JS'in ürettiği/sorguladığı sınıflar: `kisi-chk`,
  `alici-sil-btn`, `kisi-karti`, `telefonsuz`, `kisi-bilgi`, `kisi-ad`,
  `kisi-detay`, `sinif-rozet`, `tel-metin`, `ogr-rozet`, `ogr-rozet eslesmedi`,
  `alici-etiket`, `hata`, `ipucu`
- `durum.html`: `durum-govde`, `durdur-btn`, `tekrar-btn`, `durum-tablo` +
  `<tr class="${s.durum}">` — `s.durum` yalnız `gonderildi` veya `hata`
  (`sms_gonderici.py:140,142`).
- `rehber.html`: JS yok ama `form="duzenle-{{ k.id }}"` HTML form-attribute
  bağlaması var; boş `<form id="duzenle-N">` elemanları kaldırılamaz/taşınamaz.

**Doğrulama yöntemi:** aynı `grep` her fazın ÖNCESİNDE ve SONRASINDA çalıştırılır,
çıktılar bit-bit karşılaştırılır.

---

## 4. `.hata` kuralı — planın en kritik tek maddesi

`.hata` üç uyumsuz şekilde kullanılıyor: hata paragrafı (`<p>`), başarı mesajı
İÇİNDE satır içi `<span>` (`rehber.html:16`), tablo satırı (`<tr>`), ve JS'in
inline `style="padding:10px"` ile enjekte ettiği hali (`gonder.html:136`).

**Kural:** `.hata` yalnızca **renk taşıyan bir utility** kalır (`color` +
`font-weight`). Arka plan/padding/kenarlık/radius ASLA verilmez — verilirse
kutulanmış bir tablo satırı ve kutulanmış bir `<span>` elde edilir.

Banner görünümü ayrı sınıfla: `.uyari-kutusu.uyari-hata` / `.uyari-basari`.
Tablo durumu `tr.hata td` ve **`tr.gonderildi td`** olarak kapsamlanır —
`tr.gonderildi` bugün **hiç kuralı yok**, başarılı satırlar tamamen stilsiz.

---

## 5. JS'in inline `style` yazdığı yerler — CSS'te dokunulmayacak özellikler

`solPaneliGuncelle()` → `#secilenler-bos` ve `#secilenleri-temizle-btn` üzerine
`style.display` yazıyor. `renderAdayListesi()` → `style="padding:10px|12px"`.

**Kural:** bu elemanlara CSS'te **`display` ve `padding` YAZILMAZ.** Renk,
zemin, kenarlık, punto, radius serbest; yerleşim JS'e aittir. Aksi halde
empty-state kaybolur ve bu bir JS hatası gibi görünür.

---

## 6. Fazlar

### Faz 1 — smssistemi temel katmanı (token + sprite + kabuk)
Saf ikame commit'i: renkleri token'a bağla, **hiçbir ölçüyü değiştirme.**
- `smssistemi/static/stil.css` (~94 → ~180 satır): kopya-notu, işaretli kopya
  bölgesi, `--bosluk-1..5` / `--punto-kucuk|govde|baslik|kpi` (dashboard'ın
  fiilî kullanımından türetildi, yeni ölçek icat edilmedi), `box-sizing`,
  her ham hex → token (`#f5f5f7`→`--renk-zemin`, `#226`→`--renk-birincil-koyu`,
  `#b00020`→`--renk-kirmizi`, `#0a7d2c`→`--renk-yesil`, …).
- `button:disabled { opacity:.5; cursor:not-allowed }` — `#tekrar-btn` sayfa
  açılışında `disabled` geliyor ama bugün tıklanabilir görünüyor (**canlı UX hatası**).
- `smssistemi/templates/_ikon_sprite.html` (YENİ): 24 sembol birebir +
  sms-özel bölge (`ik-zarf`, `ik-gonder`, `ik-kivilcim`, `ik-filtre`, `ik-cop`,
  `ik-onay`, `ik-yukle`, `ik-telefon`, `ik-durdur`, `ik-gelen-kutusu`) — hepsi
  aynı konvansiyonda elle SVG, paket/font/CDN YOK.
- `taban.html`: sprite include, `📨` → `ik-zarf`, nav ikonları, sticky kompakt
  üst çubuk, `<head>`'e FOUC satırı (şimdilik sabit `klasik`).
- `giris.html`: `ik-kilit`, padding `32px` → `var(--bosluk-5)`.

### Faz 2 — `gonder.html` (ana CTA sayfası, en riskli)
**`<script>` bloğuna (97–354) HİÇ DOKUNULMAZ**, yalnızca 1–95 arası HTML.
Hiyerarşi: Başlık → "SMS Gönder" CTA → seçili alıcı sayısı (KPI) → listeler.
Dondurulmuş ID/sınıflar korunur, yeni stil sınıfları **yanına** eklenir.
`#secilen-sayisi` KPI rozetine, `#secilenler-bos` empty-state'e (`display`/
`padding` CSS'te verilmez), `✨` → `ik-kivilcim`. Yoğunluk: `main` padding
20px→`--bosluk-4`, `.gonder-izgara` gap 24px→`--bosluk-4`.

### Faz 3 — `durum.html` (canlı durum)
`<script>` dokunulmaz. Canlı gösterge `.nokta-canli` (yeşil pulse).
`:has()` KULLANILMAZ (eski donanım/tarayıcı). Tablo `.tablo-sarici` içine:
sabit başlık, **pagination değil akıcı dikey kaydırma** (`max-height:60vh`).
`tr.gonderildi td` yeşil sol kenarlık (bugün yok).

### Faz 4 — `kayitlar.html` (KPI vitrini)
Üstte 3 `.durum-kart`: toplam / başarılı / hatalı — **backend'e dokunmadan**
Jinja toplamı ile. Rozetler, `ik-ok-sag`, `{% if not ozetler %}` empty-state.

### Faz 5 — `rehber.html`
`form="duzenle-{{ k.id }}"` bağlamaları aynen korunur. Butonlara ikon,
yükleme mesajları `.uyari-kutusu`'na, kompakt filtre + dikey kaydırma.

### Faz 6 — smssistemi erişilebilirlik
`@media (prefers-reduced-motion: reduce)` + `:focus-visible`
(`outline: 2px solid var(--renk-birincil); outline-offset: 1px` — dashboard'ın
mevcut konvansiyonu). smssistemi'de bugün **sıfır** odak stili var.

### Faz 7 (opsiyonel, ayrı karar) — smssistemi tema seçici
Üç tema Faz 1'de kopyalandı ama yalnızca `klasik` yayında. `tema.js` kopyası
(`ANAHTAR = "farabi_sms_tema"`) + `.tema-secici`.
**Bilinmesi gereken:** :8010 ve :8020 farklı origin → `localStorage` ayrıdır,
dashboard'da seçilen tema SMS paneline **asla taşınmaz.** Hata değil, tarayıcı
davranışı; `smssistemi/CLAUDE.md`'ye yazılır.

### Faz D0 — `pano.css`'e backport (dashboard'a ilk dokunuş)
`--bosluk-*`/`--punto-*` `:root` sonuna eklenir. **Hiçbir mevcut kural bunları
kullanmaz — sıfır piksel değişimi.** Restart sonrası görsel olarak hiçbir şey
değişmemiş olmalı; değiştiyse backport'ta hata vardır.

### Faz D1 — dashboard a11y (saf ek, sıfır risk)
`prefers-reduced-motion` (kapsanacaklar: `@keyframes nabiz` 382-383, `.toast`
400-417, `.tiklanabilir:hover` 395-396, `body` transition 96) + `:focus-visible`
kapsamını mevcut konvansiyonla genişlet.

### Faz D2 — dashboard ikon kapsamı (5 ince sayfa)
Hiçbir sınıf/CSS kuralı değişmez, yalnızca `<svg class="ikon"><use .../></svg>`
eklenir. **Yalnızca mevcut 24 sembol kullanılır** (yeni sembol eklenirse
`stil.css` kopyasıyla senkron borcu doğar).
`uzaktan_yonetim.html` (1→~9), `admin_tahtalar.html` (1→~4),
`admin_sinif_ogrenciler.html` (1→~3), `admin_siniflar.html` (2→~3),
`admin_rapor.html` (2→~4).

---

## 7. Doğrulama matrisi

| Faz | Test | Servis | Gözle kontrol |
|---|---|---|---|
| 0 | `grep` envanteri | — | — |
| 1 | `pytest -q` | restart sms | 6 sayfa açılıyor, düzen bozulmamış |
| 2 | `pytest -q` + `grep` diff | restart sms | Kişi seçim paneli uçtan uca; AI Düzelt |
| 3 | `pytest -q` + `grep` diff | restart sms | Polling sürüyor, disabled mantığı |
| 4 | `pytest -q` | restart sms | KPI toplamları kolon toplamlarıyla uyuşuyor |
| 5 | `pytest -q` | restart sms | CRUD + CSV/XLSX yükleme |
| 6 | — | restart sms | Tab gezintisi; "hareketi azalt" |
| D0 | `diff` senkron | restart dashboard | **Hiçbir şey değişmemiş olmalı** |
| D1 | — | restart dashboard | Tab gezintisi; reduced-motion |
| D2 | — | restart dashboard | 5 sayfada ikonlar render oluyor |

⚠️ **Testler hakkında kritik uyarı:** `test_auth/db/eslestirme/gonderim.py`
tamamı backend/saf fonksiyon testidir. Şablon yeniden yazımından sonra
`pytest -q` geçmesi bu planla ilgili **hiçbir şey kanıtlamaz** — yalnızca
"dokunulmamış backend bozulmadı" kalkanıdır. Gerçek kapı §3'teki `grep`
sözleşme kontrolü ve canlı tarayıcı doğrulamasıdır.

**Fiziksel tahtada son kabul testi Atakan'a aittir, otomatikleştirilmez.**
Özellikle D0/D1/D2 sonrası en az bir eski i3-2330M tahtada doğrulanır.

---

## 8. Riskler

1. **`gonder.html` JS kırılması (en yüksek)** — `<script>`'e dokunulmaz,
   16 ID + 13 sınıf dondurulur, `grep` diff'i her fazda.
2. **`.hata` üç anlamlı sınıf (§4)** — renk-only kuralı, ayrı `.uyari-kutusu`.
3. **JS'in inline `style` yazması (§5)** — `display`/`padding` yasak listesi.
4. **`durum.html` polling** — JS'e dokunulmuyor; durum sözlüğü sabit.
5. **SSO akışı** — her fazdan sonra dashboard → `/sms-git` → SMS paneli denenir.
6. **Token kopyasının eskimesi** — çift yönlü not + `diff` + CLAUDE.md kayıtları.
7. **Canlı üretim** — her faz tek commit, restart sonrası duman testi;
   sorunda `git revert` + restart.

---

## 9. Kapsam dışı — YAPILMAYACAKLAR

Kural 8 + okul ağı kısıtı (MEB-CERT-TTVPN SSL incelemesi, eski i3-2330M →
CDN'e bağlı her çözüm sessizce boş ekran verir) gereği:

- **Tailwind / herhangi bir CSS framework'ü yok.** Bootstrap yok.
- **İkon fontu / Lucide npm paketi / ikon CDN'i yok** — semboller elle SVG.
- **Grafik kütüphanesi yok** (Chart.js, D3, ApexCharts). KPI çubukları saf CSS.
- **React/Alpine/htmx yok** — Jinja2 + vanilla JS devam.
- **Build adımı yok** (PostCSS, Sass, minify, bundler).
- **Uzak `@import` / Google Fonts yok** — `--yazi-tipi` sistem font yığını kalır.
- **`:has()` kullanılmaz.**
- **İki paneli ortak modüle birleştirmek yok.**
- **Backend değişikliği yok** — `app.py`/`db.py`/`gonderim.py`/`auth.py`
  hiç dokunulmaz; KPI'lar mevcut context'ten Jinja ile türetilir.
- **Dashboard'da punto ölçeği konsolidasyonu yok** (§0).
- **Gerçek SMS gönderimi ile test yok** — modem köprüsü canlı ve kırılgan.

---

## 10. Faz 1 sonuç raporu (2026-09-20)

Uygulandı: `smssistemi/static/stil.css` (token blok kopyası + tüm ham hex →
token, `button:disabled`, `tr.gonderildi td`), `smssistemi/templates/
_ikon_sprite.html` (YENİ, 24 pano-kopya + 12 sms-özel sembol),
`smssistemi/templates/taban.html` (sprite include, 6 ikon, sticky üst çubuk),
`smssistemi/templates/giris.html` (sprite include, `ik-kilit`, padding
`32px`→`var(--bosluk-5)`).

⚠️ **Kapsam düzeltmesi (uygulama sırasında yapıldı):** İlk taslak dosya
yazımında Faz 2-6'ya ait sınıflar (`.kpi-rozet`, `.bos-durum`,
`.nokta-canli`+`@keyframes nabiz`, `.tablo-sarici`, `.uyari-kutusu`,
genel `.pill`, `:focus-visible`, `prefers-reduced-motion`) yanlışlıkla
Faz 1 commit'ine erkenden eklenmişti — hiçbiri o an hiçbir şablon
tarafından kullanılmıyordu. Planın kendi "Faz 1 = saf ikame, incelemesi
kolay" ilkesine ve Kural 3'e aykırı bulunup GERİ ALINDI; her biri kendi
fazında (şablonu değiştiren fazda) eklenecek. `--bosluk-*`/`--punto-*`
token TANIMLARI kaldı (Faz1 dosyasının parçası) ama kullanımı yalnızca
`.giris-form` padding'i ile sınırlı — plandaki tek açık istisna.

**Doğrulama (hepsi geçti):**
- Sprite senkron: `awk` tabanlı diff → birebir aynı (§1'deki komut).
- Faz 0 sözleşme (`grep` envanteri, 17 ID + 2 sınıf): öncesi/sonrası
  bit-bit aynı.
- Kullanılan 6 `#ik-*` referansının 6'sı da sprite'ta tanımlı (`comm -23`
  boş çıktı).
- `venv/bin/python -m pytest -q`: **38/38 geçti.**
- Geçici dev sunucu (`:8099`) ile `/giris` render: HTTP 200, ikonlar
  HTML'de mevcut.
- `sudo systemctl restart farabi-smssistemi` — Pazar 10:44 TR, ders saati
  dışı (tahtayoklama/CLAUDE.md Kural 7 ile aynı disiplin uygulandı).
- Üretim duman testi: `/giris` 200, `/static/stil.css` 200,
  `/`/`/rehber`/`/kayitlar` 303 (auth yönlendirmesi — mevcut, değişmedi).

**Yapılmadı / bilerek ertelendi:** `gonder.html`/`durum.html`/
`kayitlar.html`/`rehber.html` görsel olarak henüz değişmedi (Faz 2-5).
Gerçek tarayıcıda görsel kontrol yapılmadı — **fiziksel/görsel son kabul
Atakan'a ait** (Kural 8, tahtayoklama/CLAUDE.md aynı ilke).

## 11. Bu planın KAPSAMADIĞI: kamera modülü

Kamera isteği bu plan başlatıldıktan sonra geldi, planda YOK. Ayrı ele alınacak.
Tespit edilenler (2026-09-20, ölçüldü):

- NVR `192.168.23.99` ayakta, port 554 açık; 10 kanal (`channel=1..9,11`),
  `subtype=1` (substream, düşük çözünürlük — yük açısından iyi).
- **Hiçbir tarayıcı `rtsp://` oynatamaz** → araya transcode katmanı şart.
- `ffmpeg`/`go2rtc`/`mediamtx` bu makinede **kurulu değil** → yeni servis =
  **Kural 8 onayı gerekir.**
- GPU 0: ~7,8 GB boş / GPU 1: ~2,3 GB boş.
- ⚠️ **Kamera kimlik bilgisi (`admin:<şifre>`) repoya ASLA girmez** (Kural 9) —
  gitignore'lu `config/kameralar.json`, commit'e yalnızca `.example.json`.
  Şifre sohbet geçmişine düz metin girdiği için NVR'da değiştirilmesi önerilir.
